#!/usr/bin/env python3

# wgl_perl_postToSheet.py
# Jim Miller, 9:31 PM Tue March 21, 2023

import sys, os
import requests # HTML posting
import json
try:
    import pywintypes # exceptions names
except ImportError:
    print("Warning: pywintypes module not found. Windows-specific functionality may be limited.")

# This pulls in JSON data from a file, as specified in a command line argument, and posts it to the spreadsheet.
# The JSON has a key for the sheet name.
# This is used by the Perl weather gleaners to post to the Google sheet. 

sheet_url = "https://script.google.com/macros/s/AKfycbze77MbV3O3Trx2UuhX3Ru7xYIWcYocDDOCU4VW9VrRsgVy1PrMT4R3Ag1DRVnlBW6V/exec" # weather-perl

if (len(sys.argv) > 1): 
    # The single argument is the full path to the JSON file
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
    print("Error: No filename provided. Usage: python3 pythonPostToSheet.py <filename>")
