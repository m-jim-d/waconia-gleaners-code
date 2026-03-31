#!/usr/bin/env python3

# wgl_sync_d1_to_sheet.py
# Read from Google Sheet and Write to Cloudflare D1
# Designed for stepwise backfill: adjust START_DATE and END_DATE each run.

import sys
import os
import requests
import json
import re
import datetime
import time

# ============================================================
# CONFIGURATION — edit these before each run
# ============================================================

# Start date for the fetch window (UTC date, inclusive from start of that day).
# Set to None to use (END_DATE - 1 day) as a single-day fetch.
START_DATE = "2026-02-03"  # e.g. "2026-03-01"

# End date for the fetch window (UTC date, inclusive through end of that day).
# Set to None to use today's UTC date.
END_DATE = "2026-03-26"  # e.g. "2026-03-20"

# Records per POST batch to Cloudflare D1.
BATCH_SIZE = 100

# Retry settings for HTTP errors (e.g. 503 rate limits).
MAX_RETRIES = 5
RETRY_DELAY_BASE = 10  # seconds; doubles each retry

# Inter-batch delay to avoid rate limiting (seconds).
INTER_BATCH_DELAY = 5

# Stop early if this many consecutive batches are all duplicates (0 = disabled).
MAX_CONSECUTIVE_DUP_BATCHES = 0

# Sheet tabs to sync. Options: "meso", "aw", "hanford", "noaa"
SHEETS = ["noaa"]

# ============================================================
# CONSTANTS
# ============================================================

# Google Spreadsheet IDs
WORKBOOK_PYTHON = "1o6-x2GLbAt3XbBRaMEcGkO7e7gGcCdIu-uwHy5PybwI"  # meso, aw
WORKBOOK_PERL   = "1WIhBWjSpB7atJ3_k0-rR93e7AQ_fZib2aeTvnI0DRXQ"   # hanford, noaa

SHEET_WORKBOOK = {
    "meso":    WORKBOOK_PYTHON,
    "aw":      WORKBOOK_PYTHON,
    "hanford": WORKBOOK_PERL,
    "noaa":    WORKBOOK_PERL,
}

# Google Visualization Query API endpoint template
# tq= is the query, tqx=out:json returns JSON wrapped in a callback
GVZ_URL = "https://docs.google.com/spreadsheets/d/{book_id}/gviz/tq?sheet={sheet}&tqx=out:json&tq={query}"

# Sheet column layout (A=station_name, B=datetime_utc, C=dry_bulb, D=dew_point,
#                      E=wind_dir, F=wind_speed, G=wind_gust, H=barometer)
# select returns: col0=B, col1=C, col2=D, col3=F, col4=G, col5=E, col6=H, col7=A
# (same order as wcharts.js: select B, C, D, F, G, E, H, A)


def compute_window():
    """Return (start_dt, end_dt) as UTC datetime objects."""
    if END_DATE is None:
        end_dt = datetime.datetime.now(datetime.timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
    else:
        end_dt = datetime.datetime.strptime(END_DATE, "%Y-%m-%d")

    # end_dt is UTC midnight of the end date; we want data through end of that day
    end_dt_inclusive = end_dt + datetime.timedelta(days=1) - datetime.timedelta(seconds=1)

    if START_DATE is None:
        start_dt = end_dt
    else:
        start_dt = datetime.datetime.strptime(START_DATE, "%Y-%m-%d")

    return start_dt, end_dt_inclusive


def build_gviz_url(sheet_name, start_dt, end_dt):
    """Build Google Visualization Query API URL for the given sheet and time window."""
    book_id = SHEET_WORKBOOK[sheet_name]

    # Format datetimes for GViz: datetime 'YYYY-MM-DD HH:MM:SS'
    start_str = start_dt.strftime("%Y-%m-%d %H:%M:%S")
    end_str   = end_dt.strftime("%Y-%m-%d %H:%M:%S")

    # Query: select all 8 columns within the time window, ordered by datetime asc
    tq = (
        "select A, B, C, D, E, F, G, H "
        "where (B >= datetime '{start}') and (B <= datetime '{end}') "
        "order by B asc"
    ).format(start=start_str, end=end_str)

    import urllib.parse
    url = GVZ_URL.format(
        book_id=book_id,
        sheet=urllib.parse.quote(sheet_name),
        query=urllib.parse.quote(tq)
    )
    return url


def parse_gviz_response(text):
    """
    Parse the Google Visualization Query API response.
    The response is a JSONP-like string:
      google.visualization.Query.setResponse({...});
    Returns list of row dicts with keys matching D1 column names.
    """
    # Strip the JSONP wrapper: google.visualization.Query.setResponse({...});
    match = re.search(r'google\.visualization\.Query\.setResponse\((.*)\);?\s*$', text, re.DOTALL)
    if not match:
        # Sometimes it's just plain JSON (when tqx=out:json is honored strictly)
        json_str = text.strip()
    else:
        json_str = match.group(1)

    data = json.loads(json_str)

    if data.get("status") == "error":
        errors = data.get("errors", [])
        raise RuntimeError("GViz query error: " + str(errors))

    table = data.get("table", {})
    cols = table.get("cols", [])
    rows = table.get("rows", [])

    # Build column label index: label -> position
    # Labels come back as the column letters (A, B, ...) or as the select aliases
    # We selected: A(station_name), B(datetime_utc), C(dry_bulb), D(dew_point),
    #              E(wind_dir), F(wind_speed), G(wind_gust), H(barometer)
    # Column order in response matches our select order.
    col_names = ["station_name", "datetime_utc", "dry_bulb", "dew_point",
                 "wind_dir", "wind_speed", "wind_gust", "barometer"]

    records = []
    for row in rows:
        if row is None:
            continue
        cells = row.get("c", [])
        rec = {}
        for i, col_name in enumerate(col_names):
            if i >= len(cells) or cells[i] is None:
                rec[col_name] = None
                continue
            cell = cells[i]
            val = cell.get("v", None)

            if col_name == "datetime_utc":
                # GViz returns datetime as "Date(year,month0,day,h,m,s)" JS constructor string
                # OR as a Python-parseable string if tqx=out:json
                if isinstance(val, str) and val.startswith("Date("):
                    # Parse: Date(2026,2,24,2,35,0) — month is 0-indexed
                    nums = re.findall(r'\d+', val)
                    if len(nums) >= 6:
                        yr, mo0, dy, hr, mn, sc = (int(n) for n in nums[:6])
                        dt = datetime.datetime(yr, mo0 + 1, dy, hr, mn, sc)
                        rec[col_name] = dt.strftime("%Y-%m-%d %H:%M:%S")
                    else:
                        rec[col_name] = None
                elif val is None:
                    rec[col_name] = None
                else:
                    # Already a string in some usable format
                    rec[col_name] = str(val)
            else:
                # Numeric or string value; pass through, None stays None
                rec[col_name] = val

        # Skip rows with no station or no datetime
        if rec.get("station_name") and rec.get("datetime_utc"):
            records.append(rec)

    return records


def fetch_sheet_records(sheet_name, start_dt, end_dt):
    """Fetch records from one sheet tab for the given time window."""
    url = build_gviz_url(sheet_name, start_dt, end_dt)
    print(f"  Fetching {sheet_name}: {start_dt.date()} to {end_dt.date()} ...")
    print(f"  URL: {url}")

    try:
        resp = requests.get(url, timeout=60)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"  ERROR fetching {sheet_name}: {e}")
        return []

    try:
        records = parse_gviz_response(resp.text)
    except Exception as e:
        print(f"  ERROR parsing {sheet_name} response: {e}")
        # Print first 500 chars of response for debugging
        print(f"  Response preview: {resp.text[:500]}")
        return []

    print(f"  Parsed {len(records)} records from {sheet_name}")
    return records


def write_records_to_d1(records, sheet_name):
    """Write records to D1 in batches. Returns (total_inserted, total_duplicates)."""
    from wgl_python_module import write_to_cloudflare
    from wgl_python_config import CLOUDFLARE_API_KEY, CLOUDFLARE_WORKER_URL

    total_inserted = 0
    total_duplicates = 0
    total_batches = 0
    consecutive_dup_batches = 0

    for i in range(0, len(records), BATCH_SIZE):
        batch = records[i : i + BATCH_SIZE]
        batch_num = (i // BATCH_SIZE) + 1

        # Tag each record with the source sheet
        for rec in batch:
            rec["source"] = sheet_name

        headers = {
            "Content-Type": "application/json",
            "X-API-Key": CLOUDFLARE_API_KEY
        }

        success = False
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = requests.post(CLOUDFLARE_WORKER_URL, json=batch, headers=headers, timeout=60)

                if response.status_code == 200:
                    result = response.json()
                    ins = result.get("inserted", 0)
                    dup = result.get("duplicates", 0)
                    total_inserted += ins
                    total_duplicates += dup
                    total_batches += 1
                    datetimes = [r["datetime_utc"] for r in batch if r.get("datetime_utc")]
                    earliest_dt = min(datetimes) if datetimes else "?"
                    try:
                        earliest_utc = datetime.datetime.strptime(earliest_dt, "%Y-%m-%d %H:%M:%S")
                        # DST: 2nd Sun Mar to 1st Sun Nov -> CDT (UTC-5); else CST (UTC-6)
                        yr = earliest_utc.year
                        dst_start = datetime.datetime(yr, 3, 8) + datetime.timedelta(days=(6 - datetime.datetime(yr, 3, 8).weekday()) % 7)
                        dst_end   = datetime.datetime(yr, 11, 1) + datetime.timedelta(days=(6 - datetime.datetime(yr, 11, 1).weekday()) % 7)
                        if dst_start <= earliest_utc < dst_end:
                            ct_offset = datetime.timedelta(hours=-5)
                            ct_label = "CDT"
                        else:
                            ct_offset = datetime.timedelta(hours=-6)
                            ct_label = "CST"
                        earliest_ct = earliest_utc + ct_offset
                        earliest_ct_str = earliest_ct.strftime("%Y-%m-%d %H:%M:%S") + " " + ct_label
                    except Exception:
                        earliest_ct_str = "?"
                    print(f"    Batch {total_batches} ({len(batch)} records): inserted={ins}, duplicates={dup}  [data from: {earliest_dt} UTC / {earliest_ct_str}]")
                    if ins == 0 and dup > 0:
                        consecutive_dup_batches += 1
                    else:
                        consecutive_dup_batches = 0
                    success = True
                    break
                elif response.status_code in (429, 503):
                    delay = RETRY_DELAY_BASE * attempt
                    print(f"    Batch {batch_num} attempt {attempt}: {response.status_code} - retrying in {delay}s...")
                    time.sleep(delay)
                else:
                    print(f"    Batch {batch_num} ERROR: {response.status_code} - {response.text[:200]}")
                    break

            except Exception as e:
                delay = RETRY_DELAY_BASE * attempt
                print(f"    Batch {batch_num} attempt {attempt} EXCEPTION: {type(e).__name__} ==> {e} - retrying in {delay}s...")
                time.sleep(delay)

        if not success:
            print(f"    Batch {batch_num} FAILED after {MAX_RETRIES} attempts — aborting to avoid gaps in D1 data.")
            sys.exit(1)

        if MAX_CONSECUTIVE_DUP_BATCHES > 0 and consecutive_dup_batches >= MAX_CONSECUTIVE_DUP_BATCHES:
            print(f"    {consecutive_dup_batches} consecutive all-duplicate batches — data already in D1, stopping early.")
            break

        time.sleep(INTER_BATCH_DELAY)

    return total_inserted, total_duplicates


def main():
    start_dt, end_dt = compute_window()

    print("=" * 60)
    print("Sheet -> D1 Backfill Sync")
    print(f"  Window : {start_dt.strftime('%Y-%m-%d %H:%M:%S')} UTC  to")
    print(f"           {end_dt.strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print(f"  Sheets : {', '.join(SHEETS)}")
    print(f"  Batch  : {BATCH_SIZE} records/POST")
    print("=" * 60)

    grand_inserted = 0
    grand_duplicates = 0
    grand_fetched = 0

    for sheet_name in SHEETS:
        print(f"\n--- Sheet: {sheet_name} ---")
        records = fetch_sheet_records(sheet_name, start_dt, end_dt)

        if not records:
            print(f"  No records found for {sheet_name}, skipping.")
            continue

        grand_fetched += len(records)
        ins, dup = write_records_to_d1(records, sheet_name)
        grand_inserted += ins
        grand_duplicates += dup

        print(f"  {sheet_name} total: fetched={len(records)}, inserted={ins}, duplicates={dup}")

    print("\n" + "=" * 60)
    print("GRAND TOTAL")
    print(f"  Fetched   : {grand_fetched}")
    print(f"  Inserted  : {grand_inserted}")
    print(f"  Duplicates: {grand_duplicates}")
    print(f"  D1 writes used this run: {grand_inserted}")
    print("=" * 60)


if __name__ == "__main__":
    main()