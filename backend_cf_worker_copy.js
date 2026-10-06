// Cloudflare worker: weather-api
// Handles GET /weather (time-range query),
//         GET /weather/current (latest per station),
//         POST /weather (insert),
//         and scheduled cleanup

const FREE_D1_READ_LIMIT = 5_000_000;

// Min/max aggregate gating thresholds (daily rows read)
const AGG_BLOCK_10D = 4_000_000;   // 80% - block 10-day min/max
const AGG_BLOCK_5D  = 4_250_000;   // 85% - block 5-day and 10-day min/max
const AGG_BLOCK_ALL = 4_750_000;   // 95% - block all min/max queries

// D1 returns execution metadata with every query. meta.rows_read is the number
// of rows D1 scanned and is the value Cloudflare uses for rows-read billing.
// After each API query, the Worker reads today's UTC total from read_usage,
// returns the total plus the current query in response headers, then asynchronously
// updates read_usage and appends a detailed row to read_usage_log.
//
// ctx is the Cloudflare Worker execution context passed to fetch() and scheduled().
// ctx.waitUntil(promise) keeps the Worker alive until background work finishes,
// even after the HTTP response has been returned. This lets usage accounting run
// without adding its write latency to the browser request. Scheduled cleanup uses
// await instead because there is no HTTP response whose latency needs minimizing.

export default {
  // Scheduled cleanup - runs on cron trigger
  async scheduled(event, env, ctx) {
    // Delete records older than n_days
    const n_days = 200;
    const cutoffDate = new Date(Date.now() - n_days * 24 * 60 * 60 * 1000)
      .toISOString()
      .replace('T', ' ')
      .slice(0, 19);  // Format: "YYYY-MM-DD HH:MM:SS"

    const result = await env.DB.prepare(
      "DELETE FROM weather_data WHERE datetime_utc < ?"
    ).bind(cutoffDate).run();

    const logResult = await env.DB.prepare(
      "DELETE FROM read_usage_log WHERE queried_at < ?"
    ).bind(cutoffDate).run();

    const rowsRead = (result.meta.rows_read || 0) + (logResult.meta.rows_read || 0);
    await recordUsage(env, rowsRead);
    await logQuery(env, '/weather/cleanup', {
      n_days,
      deleted: result.meta.changes,
      deleted_log: logResult.meta.changes
    }, rowsRead);

    console.log(`Cleanup: deleted ${result.meta.changes} old records, ${logResult.meta.changes} old log entries, read ${rowsRead} rows`);
  },

  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    // CORS headers for browser requests
    const corsHeaders = {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type, X-API-Key",
      "Access-Control-Expose-Headers": "X-Rows-Read-Query, X-Rows-Read-Today, X-Rows-Read-Limit",
    };

    // Handle preflight
    if (request.method === "OPTIONS") {
      return new Response(null, { headers: corsHeaders });
    }

    try {
      if (request.method === "GET" && url.pathname === "/weather") {
        return await handleQuery(url, env, ctx, corsHeaders);
      }

      if (request.method === "GET" && url.pathname === "/weather/current") {
        return await handleCurrent(url, env, ctx, corsHeaders);
      }

      if (request.method === "GET" && url.pathname === "/weather/aggregate") {
        return await handleAggregate(url, env, ctx, corsHeaders);
      }

      if (request.method === "GET" && url.pathname === "/weather/usage") {
        return await handleUsage(env, corsHeaders);
      }

      if (request.method === "POST" && url.pathname === "/weather") {
        return await handleInsert(request, env, corsHeaders);
      }

      return new Response("Not Found", { status: 404, headers: corsHeaders });

    } catch (error) {
      console.error("Worker error:", error);
      return new Response(JSON.stringify({ error: error.message, stack: error.stack }), {
        status: 500,
        headers: { ...corsHeaders, "Content-Type": "application/json" }
      });
    }
  }
};

async function handleQuery(url, env, ctx, corsHeaders) {
  const station = url.searchParams.get("station");
  const start = url.searchParams.get("start");
  const end = url.searchParams.get("end");

  if (!station || !start || !end) {
    return new Response(JSON.stringify({ error: "Missing required params: station, start, end" }), {
      status: 400,
      headers: { ...corsHeaders, "Content-Type": "application/json" }
    });
  }

  const sql = `
    SELECT datetime_utc, dry_bulb, dew_point, wind_speed, wind_gust, wind_dir, barometer, station_name
    FROM weather_data
    WHERE station_name = ? AND datetime_utc >= ? AND datetime_utc <= ?
    ORDER BY datetime_utc DESC
  `;

  const results = await env.DB.prepare(sql).bind(station, start, end).all();
  const queryRows = results.meta.rows_read || 0;
  const priorRows = await getTodayUsage(env);
  const todayRows = priorRows + queryRows;

  ctx.waitUntil(Promise.all([
    recordUsage(env, queryRows),
    logQuery(env, '/weather', { station, start, end }, queryRows)
  ]));

  return new Response(JSON.stringify(results.results), {
    headers: { ...corsHeaders, "Content-Type": "application/json", ...usageHeaders(queryRows, todayRows) }
  });
}

async function handleCurrent(url, env, ctx, corsHeaders) {
  // Return the most recent record for each station, within the last 48 hours.
  const cutoff = new Date(Date.now() - 48 * 60 * 60 * 1000)
    .toISOString()
    .replace('T', ' ')
    .slice(0, 19);

  let stationNames = [];
  const stationsParam = url.searchParams.get("stations");
  if (stationsParam && stationsParam.trim()) {
    stationNames = stationsParam.split(',').map(s => s.trim()).filter(Boolean);
  }

  let queryRows = 0;
  let results = [];

  if (stationNames.length > 0) {
    // Pass the station list as a JSON array so we stay well under D1's
    // 100-parameter and compound-SELECT limits. The correlated subquery uses
    // the composite index (station_name, datetime_utc) to read roughly one
    // row per station, then joins by primary key to get the full record.
    const sql = `
      WITH station_list AS (
        SELECT value AS station_name FROM json_each(?)
      )
      SELECT w.datetime_utc, w.dry_bulb, w.dew_point, w.wind_speed, w.wind_gust, w.wind_dir, w.barometer, w.station_name
      FROM station_list s
      JOIN weather_data w ON w.id = (
        SELECT id
        FROM weather_data
        WHERE station_name = s.station_name AND datetime_utc >= ?
        ORDER BY datetime_utc DESC
        LIMIT 1
      )
      ORDER BY w.station_name
    `;
    const dbResult = await env.DB.prepare(sql).bind(JSON.stringify(stationNames), cutoff).all();
    results = dbResult.results;
    queryRows += dbResult.meta.rows_read || 0;
  } else {
    // Fallback when no station list is provided: discover active stations in the window.
    const activeResult = await env.DB.prepare(
      "SELECT DISTINCT station_name FROM weather_data WHERE datetime_utc >= ?"
    ).bind(cutoff).all();
    stationNames = activeResult.results.map(r => r.station_name);
    queryRows += activeResult.meta.rows_read || 0;

    if (stationNames.length > 0) {
      const sql = `
        WITH station_list AS (
          SELECT value AS station_name FROM json_each(?)
        )
        SELECT w.datetime_utc, w.dry_bulb, w.dew_point, w.wind_speed, w.wind_gust, w.wind_dir, w.barometer, w.station_name
        FROM station_list s
        JOIN weather_data w ON w.id = (
          SELECT id
          FROM weather_data
          WHERE station_name = s.station_name AND datetime_utc >= ?
          ORDER BY datetime_utc DESC
          LIMIT 1
        )
        ORDER BY w.station_name
      `;
      const dbResult = await env.DB.prepare(sql).bind(JSON.stringify(stationNames), cutoff).all();
      results = dbResult.results;
      queryRows += dbResult.meta.rows_read || 0;
    }
  }

  const priorRows = await getTodayUsage(env);
  const todayRows = priorRows + queryRows;

  ctx.waitUntil(Promise.all([
    recordUsage(env, queryRows),
    logQuery(env, '/weather/current', { stations: stationNames.length }, queryRows)
  ]));

  return new Response(JSON.stringify(results), {
    headers: { ...corsHeaders, "Content-Type": "application/json", ...usageHeaders(queryRows, todayRows) }
  });
}

async function handleAggregate(url, env, ctx, corsHeaders) {
  const mode = (url.searchParams.get("mode") || "maximum").toLowerCase();
  const daysParam = url.searchParams.get("days");

  // Determine hours from days param ("24h" => 24, "2" => 48, "5" => 120, etc.)
  let hours;
  if (daysParam && daysParam.endsWith('h')) {
    hours = parseInt(daysParam, 10) || 24;
  } else {
    hours = Math.round((parseFloat(daysParam) || 1) * 24);
  }

  const aggFn = (mode === 'minimum') ? 'MIN' : 'MAX';

  // Gate expensive min/max queries based on today's running total.
  // Debug: ?gatingTest=4.6M simulates 4,600,000 rows read (a floor, never a bypass).
  const testUsage = parseUsageValue(url.searchParams.get('gatingTest'));
  const priorRows = Math.max(await getTodayUsage(env), testUsage);
  const isHourly = daysParam && daysParam.endsWith('h');
  const daysNum = parseFloat(daysParam) || 1;

  let blockedReason = null;
  if (priorRows >= AGG_BLOCK_ALL) {
    blockedReason = `all min/max queries (daily read budget nearly exhausted)`;
  } else if (!isHourly && daysNum >= 10 && priorRows >= AGG_BLOCK_10D) {
    blockedReason = `10-day min/max queries`;
  } else if (!isHourly && daysNum >= 5 && priorRows >= AGG_BLOCK_5D) {
    blockedReason = `5-day and 10-day min/max queries`;
  }

  if (blockedReason) {
    return new Response(JSON.stringify({
      error: `Query blocked: ${blockedReason} are temporarily disabled because today's D1 read usage (${priorRows.toLocaleString()} rows) is above ${Math.round(100 * priorRows / FREE_D1_READ_LIMIT)}% of the daily limit. Please use Current or a shorter duration, or try again after midnight UTC.`
    }), {
      status: 429,
      headers: { ...corsHeaders, "Content-Type": "application/json", ...usageHeaders(0, priorRows) }
    });
  }

  const cutoff = new Date(Date.now() - hours * 60 * 60 * 1000)
    .toISOString()
    .replace('T', ' ')
    .slice(0, 19);

  const sql = `
    SELECT station_name,
           ${aggFn}(dry_bulb)   AS dry_bulb,
           ${aggFn}(dew_point)  AS dew_point,
           ${aggFn}(wind_speed) AS wind_speed,
           ${aggFn}(wind_gust)  AS wind_gust,
           ${aggFn}(barometer)  AS barometer,
           MAX(datetime_utc)   AS datetime_utc
    FROM weather_data INDEXED BY idx_weather_data_datetime_utc
    WHERE datetime_utc >= ?
    GROUP BY station_name
    ORDER BY station_name
  `;

  const results = await env.DB.prepare(sql).bind(cutoff).all();
  const queryRows = results.meta.rows_read || 0;
  const todayRows = priorRows + queryRows;

  ctx.waitUntil(Promise.all([
    recordUsage(env, queryRows),
    logQuery(env, '/weather/aggregate', { mode, days: daysParam }, queryRows)
  ]));

  return new Response(JSON.stringify(results.results), {
    headers: { ...corsHeaders, "Content-Type": "application/json", ...usageHeaders(queryRows, todayRows) }
  });
}

async function handleUsage(env, corsHeaders) {
  const todayRows = await getTodayUsage(env);
  const day = new Date().toISOString().slice(0, 10);

  return new Response(JSON.stringify({ day, rowsRead: todayRows, limit: FREE_D1_READ_LIMIT }), {
    headers: { ...corsHeaders, "Content-Type": "application/json", ...usageHeaders(0, todayRows) }
  });
}

// Cloudflare resets the free D1 allowance at 00:00 UTC, so the counter key is
// the UTC date. The one-row lookup itself consumes a small number of D1 reads;
// those bookkeeping reads are not recursively added to the counter.
function parseUsageValue(value) {
  if (!value) return 0;
  const match = String(value).trim().match(/^([0-9]+(?:\.[0-9]+)?)\s*([KM]?)$/i);
  if (!match) return 0;
  const multiplier = match[2].toUpperCase() === 'M' ? 1_000_000 :
                     match[2].toUpperCase() === 'K' ? 1_000 : 1;
  return Math.round(Number(match[1]) * multiplier);
}

async function getTodayUsage(env) {
  const day = new Date().toISOString().slice(0, 10);
  const result = await env.DB.prepare("SELECT rows_read FROM read_usage WHERE day = ?").bind(day).first();
  return result ? Number(result.rows_read) : 0;
}

// Add the API query's meta.rows_read value to today's running total. The upsert
// is one D1 write and creates the day's row automatically after midnight UTC.
function recordUsage(env, rowsRead) {
  const day = new Date().toISOString().slice(0, 10);
  return env.DB.prepare(
    `INSERT INTO read_usage (day, rows_read) VALUES (?, ?)
     ON CONFLICT(day) DO UPDATE SET rows_read = rows_read + excluded.rows_read`
  ).bind(day, Math.max(0, rowsRead)).run();
}

// Keep a per-query audit trail for diagnosing usage spikes. This table is not
// read during normal requests and is pruned by the scheduled cleanup.
function logQuery(env, endpoint, params, rowsRead) {
  const now = new Date().toISOString();
  const paramsJson = params ? JSON.stringify(params) : null;
  return env.DB.prepare(
    "INSERT INTO read_usage_log (queried_at, endpoint, params, rows_read) VALUES (?, ?, ?, ?)"
  ).bind(now, endpoint, paramsJson, Math.max(0, rowsRead)).run();
}

function usageHeaders(queryRows, todayRows) {
  return {
    "X-Rows-Read-Query": String(queryRows),
    "X-Rows-Read-Today": String(todayRows),
    "X-Rows-Read-Limit": String(FREE_D1_READ_LIMIT)
  };
}

async function handleInsert(request, env, corsHeaders) {
  // Verify API key
  const apiKey = request.headers.get("X-API-Key");
  if (apiKey !== env.API_KEY) {
    return new Response(JSON.stringify({ error: "Unauthorized" }), {
      status: 401,
      headers: { ...corsHeaders, "Content-Type": "application/json" }
    });
  }

  const data = await request.json();

  // Support single record or array of records
  const records = Array.isArray(data) ? data : [data];

  let inserted = 0;
  let duplicates = 0;

  for (const record of records) {
    try {
      await env.DB.prepare(`
        INSERT INTO weather_data (station_name, datetime_utc, dry_bulb, dew_point, wind_speed, wind_gust, wind_dir, barometer, source)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
      `).bind(
        record.station_name,
        record.datetime_utc,
        record.dry_bulb ?? null,
        record.dew_point ?? null,
        record.wind_speed ?? null,
        record.wind_gust ?? null,
        record.wind_dir ?? null,
        record.barometer ?? null,
        record.source ?? null
      ).run();
      inserted++;
    } catch (e) {
      if (e.message.includes("UNIQUE constraint")) {
        duplicates++;
      } else {
        throw e;
      }
    }
  }

  return new Response(JSON.stringify({ inserted, duplicates }), {
    headers: { ...corsHeaders, "Content-Type": "application/json" }
  });
}
