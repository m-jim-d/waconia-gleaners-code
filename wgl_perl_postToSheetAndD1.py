#!/usr/bin/env python3

# wgl_perl_postToSheetAndD1.py
# Jim Miller, 9:31 PM Tue March 21, 2023
# Updated to always post to both Google Sheet and Cloudflare D1

import sys, os
import requests # HTML posting
import json
try:
    import pywintypes # exceptions names
except ImportError:
    print("Warning: pywintypes module not found. Windows-specific functionality may be limited.")

from wgl_python_module import write_to_cloudflare

# This pulls in JSON data from a file, as specified in a command line argument, and posts it to the spreadsheet
# and Cloudflare D1. The JSON has a key for the sheet name.
# This is used by the Perl weather gleaners to post to the Google sheet and D1. 

sheet_url = "https://script.google.com/macros/s/AKfycbze77MbV3O3Trx2UuhX3Ru7xYIWcYocDDOCU4VW9VrRsgVy1PrMT4R3Ag1DRVnlBW6V/exec" # weather-perl


def convert_perl_datetime(dt_str):
    """
    Convert Perl datetime format "MM/DD/YYYY HH:MM:SS" to ISO format "YYYY-MM-DD HH:MM:SS"
    Note: Use space separator (not T) for consistent SQLite string comparison in D1 queries
    """
    try:
        from datetime import datetime
        dt = datetime.strptime(dt_str, "%m/%d/%Y %H:%M:%S")
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except:
        return dt_str  # Return as-is if parsing fails

def convert_perl_to_d1(postDict):
    """
    Convert Perl gleaner JSON format to Cloudflare D1 format.
    Perl format: {"sheetName": "hanford", "weatherData": [[station, datetime_utc, temp, dew, wind_dir, wind_speed, wind_gust, pressure], ...]}
    D1 format: [{"station_name": ..., "datetime_utc": ..., ...}, ...]
    """
    rows = postDict.get("weatherData", [])
    d1_records = []
    
    for row in rows:
        if len(row) >= 8:
            d1_records.append({
                'station_name': row[0],
                'datetime_utc': convert_perl_datetime(row[1]),
                'dry_bulb': row[2] if row[2] else None,
                'dew_point': row[3] if row[3] else None,
                'wind_dir': row[4] if row[4] else None,
                'wind_speed': row[5] if row[5] else None,
                'wind_gust': row[6] if row[6] else None,
                'barometer': row[7] if row[7] else None
            })
    
    return d1_records

if (len(sys.argv) > 1): 
    # The first argument is the full path to the JSON file
    filePath = sys.argv[1]
    print("file path =", filePath)

    try:
        with open(filePath, "r") as f:
            json_string = f.read()

        postDict = json.loads(json_string)
        print("sheetName =", postDict["sheetName"])
         
        try:
            # Send with POST. Note: the postDict dictionary gets converted back to a JSON string.
            jsonRequest = requests.post(sheet_url, json=postDict)

            # Format and print the response
            print(json.dumps(jsonRequest.json(), indent=2))
            
            # Write to Cloudflare D1
            sheetName = postDict.get("sheetName", "perl")
            d1_records = convert_perl_to_d1(postDict)
            if d1_records:
                write_to_cloudflare(d1_records, source=sheetName)
            
        except Exception as e: 
            print("Error opening spreadsheet.")
            print(f"Error details: {e}")
    except FileNotFoundError:
        print(f"Error: Could not find file {filePath}")
    except json.JSONDecodeError:
        print(f"Error: Invalid JSON format in {filePath}")
    except Exception as e:
        print(f"Unexpected error: {e}")
else:
    print("Error: No filename provided. Usage: python3 wgl_perl_postToSheetAndD1.py <filename>")
