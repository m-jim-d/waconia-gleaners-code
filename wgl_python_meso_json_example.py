# Sample JSON output (see URL query for JSON feed below):
# https://api.synopticdata.com/v2/stations/latest?vars=air_temp,dew_point_temperature,wind_speed,wind_direction,wind_gust,sea_level_pressure&obtimezone=local&output=json&units=english&token=45d3bd33f12c4d87aed5925e0f4da854&stid=KMKT

{
  "STATION": [
    {
      "ID": "5015",
      "STID": "KMKT",
      "NAME": "Mankato, Mankato Regional Airport",
      "ELEVATION": "1020.0",
      "LATITUDE": "44.21667",
      "LONGITUDE": "-93.91667",
      "STATUS": "ACTIVE",
      "MNET_ID": "1",
      "STATE": "MN",
      "TIMEZONE": "America/Chicago",
      "ELEV_DEM": "1013.8",
      "PERIOD_OF_RECORD": {
        "start": "2002-08-14T00:00:00Z",
        "end": "2025-06-26T20:30:00Z"
      },
      "UNITS": {
        "position": "ft",
        "elevation": "ft"
      },
      "OBSERVATIONS": {
        "air_temp_value_1": {
          "value": 66.2,
          "date_time": "2025-06-26T15:41:00-0500"
        },
        "wind_speed_value_1": {
          "value": 14,
          "date_time": "2025-06-26T15:41:00-0500"
        },
        "wind_direction_value_1": {
          "value": 70,
          "date_time": "2025-06-26T15:41:00-0500"
        },
        "wind_gust_value_1": {
          "value": 19,
          "date_time": "2025-06-25T16:39:00-0500"
        },
        "sea_level_pressure_value_1": {
          "value": 1010.8,
          "date_time": "2025-06-26T14:56:00-0500"
        },
        "sea_level_pressure_value_1d": {
          "date_time": "2025-06-26T15:41:00-0500",
          "value": 1009.71
        },
        "dew_point_temperature_value_1d": {
          "date_time": "2025-06-26T15:41:00-0500",
          "value": 64.4
        }
      },
      "SENSOR_VARIABLES": {
        "air_temp": {
          "air_temp_value_1": {

          }
        },
        "wind_speed": {
          "wind_speed_value_1": {

          }
        },
        "wind_direction": {
          "wind_direction_value_1": {

          }
        },
        "wind_gust": {
          "wind_gust_value_1": {

          }
        },
        "sea_level_pressure": {
          "sea_level_pressure_value_1": {

          },
          "sea_level_pressure_value_1d": {
            "derived_from": [
              "pressure_value_1d",
              "air_temp_value_1",
              "relative_humidity_value_1"
            ]
          }
        },
        "dew_point_temperature": {
          "dew_point_temperature_value_1d": {
            "derived_from": [
              "air_temp_value_1",
              "relative_humidity_value_1"
            ]
          }
        }
      },
      "QC_FLAGGED": false,
      "RESTRICTED": false,
      "RESTRICTED_METADATA": false
    }
  ],
  "SUMMARY": {
    "NUMBER_OF_OBJECTS": 1,
    "RESPONSE_CODE": 1,
    "RESPONSE_MESSAGE": "OK",
    "METADATA_PARSE_TIME": "0.2 ms",
    "METADATA_DB_QUERY_TIME": "2.5 ms",
    "QUERY_TIME": "3.8 ms",
    "DB_QUERY_TIME": "0 ms",
    "QC_QUERY_TIME": "0 ms",
    "DATA_PARSING_TIME": "0.8 ms",
    "TOTAL_DATA_TIME": "4.6 ms",
    "VERSION": "v2.27.0"
  },
  "QC_SUMMARY": {
    "QC_CHECKS_APPLIED": [
      "sl_range_check"
    ],
    "TOTAL_OBSERVATIONS_FLAGGED": 0,
    "PERCENT_OF_TOTAL_OBSERVATIONS_FLAGGED": 0,
    "QC_NAMES": {
      "1": "SynopticLabs Range Check"
    },
    "QC_SHORTNAMES": {
      "1": "sl_range_check"
    },
    "QC_SOURCENAMES": {
      "1": "SynopticLabs"
    }
  },
  "UNITS": {
    "air_temp": "Fahrenheit",
    "wind_speed": "knots",
    "wind_direction": "Degrees",
    "wind_gust": "knots",
    "sea_level_pressure": "Millibars",
    "dew_point_temperature": "Fahrenheit"
  }
}

