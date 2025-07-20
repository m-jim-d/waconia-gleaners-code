#!/usr/bin/env python3

"""
wgl_python_meso.py

Description: a JSON gleaner for collecting weather data
Written by: Jim Miller

6/26/2025
"""

import requests
import json
import math
import time
import datetime

from wgl_python_module import (write_to_spreadsheet, openConnections, closeConnections, enterInLog, 
    runSQL, attemptWriteToDaysGleaned, updateMaxStationDateTime
)

"""
Functions
"""

def inQu( string):
    # Put everything but NULL into single quotes for the SQL string.
    # Note: best practice would be to not quote numeric values, quote only strings and dates.
    if (string == "NULL"):
        finalString = string
    else:
        finalString = "'" + str( string) + "'"
    return finalString
  
  
def nN( string):
    # When writing to the spreadsheet, NULLs should be represented as None 
    if (string == "NULL"):
        value = None
    else:
        value = string
    return value
    
    
def utc( localTimeString):
    # e.g. "2022-12-12T11:35:00-0600"
    #                          54321
    dateTimeFromStamp = datetime.datetime.strptime( localTimeString[:-5], "%Y-%m-%dT%H:%M:%S")
    hoursFromUTC = int( localTimeString[-5:-2])
    utcTime = dateTimeFromStamp - datetime.timedelta( hours=hoursFromUTC)
    utcTimeString = str( utcTime)
    return utcTimeString
  
    
def getSensorDataDict( stationData, sensorName):
    sensorDict = stationData["SENSOR_VARIABLES"].get( sensorName, "no report")
    if (sensorDict != "no report"):
        # Python 3 update: dict.keys() returns a view object, not a list
        sensorValueName = list(sensorDict.keys())[0]
        sensorDataDict = stationData["OBSERVATIONS"][sensorValueName]
    else:
        sensorDataDict = {'value':'NULL'}
    return sensorDataDict


def processMultipleStations_json( station_dictionary):
    # Build the URL string to run a query for multiple stations.
    # (returned on one page).
    
    # First, here are some examples of single-station queries.
    # Old XML query:
    # http://www.wrh.noaa.gov/mesowest/getobextXml.php?num=1&sid=KRLD
    # Using their JSON feed and a token:
    # https://api.synopticdata.com/v2/stations/latest?vars=air_temp,dew_point_temperature,wind_speed,wind_direction,wind_gust,sea_level_pressure&obtimezone=local&output=json&units=english&token=HIDDEN&stid=KMKT
    
    
    # Get API token from config file
    try:
        from wgl_python_config import SYNOPTIC_API_TOKEN
        api_token = SYNOPTIC_API_TOKEN
    except ImportError:
        message_str = "Error: wgl_python_config.py not found. Create this file from wgl_python_config_template.py"
        enterInLog(message_str)
        print(message_str)
        return
    except AttributeError:
        message_str = "Error: SYNOPTIC_API_TOKEN not defined in wgl_python_config.py"
        enterInLog(message_str)
        print(message_str)
        return

    url_base = ("https://api.synopticdata.com/v2/stations/latest?" + 
               "vars=air_temp,dew_point_temperature,wind_speed,wind_direction,wind_gust,sea_level_pressure" + 
               "&obtimezone=local&output=json&units=english" + 
               f"&token={api_token}&stid=")

    # Get count of stations
    station_count = len(station_dictionary)
    
    # Join all station names with commas
    station_names = ",".join(station_dictionary.keys())
    
    # Build the complete URL
    webpage_url = url_base + station_names
    print("url = " + webpage_url)

    try:
        # Fetch the JSON page
        jsonRequest = requests.get( webpage_url)
        jsonObject = jsonRequest.json()
        #formatedJson = json.dumps( jsonObject, indent=2)
        #print(formatedJson)
    except: 
        message_str = "Error opening json url"
        enterInLog( message_str)
        print(message_str + ", URL = " + webpage_url)

    rowsForSpreadsheet = []
    write_count = 0
    
    for stationData in jsonObject["STATION"]:
        print("")
        print(stationData["STID"])
        print(stationData["NAME"])
        for sensorName in stationData["SENSOR_VARIABLES"]:
            sensorData = getSensorDataDict( stationData, sensorName)
            print(sensorName + ", " + str( sensorData["value"]) + ", " + sensorData["date_time"])
    
        # Do conversions and then populated the weather dictionary
        temp_f = getSensorDataDict( stationData, "air_temp")["value"]
        dewPoint_f = getSensorDataDict( stationData, "dew_point_temperature")["value"]
        
        # 2020-12-01T11:05:00-0600
        timestamp_literal = getSensorDataDict( stationData, "air_temp")["date_time"]
        
        # 2021-03-19 07:56:00
        dateTimeFromStamp = datetime.datetime.strptime( timestamp_literal[:-5], "%Y-%m-%dT%H:%M:%S")
        
        # This check for daylight savings time (dst) uses local gleaner time (T=1, F=0). 
        # So, if the gleaner computer sees dst, and the station is in an area where dst is used (everywhere but Hawaii), 
        # then change it back to standard time.
        dstFlag = time.localtime()[-1]
        if (dstFlag and station_dic[ stationData['STID']]['dst']):
            dateTimeFromStamp_std = dateTimeFromStamp - datetime.timedelta( hours=1)
        else:
            dateTimeFromStamp_std = dateTimeFromStamp
        # 2021-03-19 07:56:00
        dateTimeFromStamp_std_string = str( dateTimeFromStamp_std)
        
        updateMaxStationDateTime( dateTimeFromStamp_std)
        
        timestamp_date = dateTimeFromStamp_std_string.split(" ")[0]
        dateParts = timestamp_date.split("-")
        ts_year = dateParts[0]
        ts_month = dateParts[1]
        ts_day = dateParts[2]
        
        timestamp_time = dateTimeFromStamp_std_string.split(" ")[1]
        timeParts = timestamp_time.split(":")
        ts_hour = timeParts[0]
        ts_min = timeParts[1]
        ts_sec = timeParts[2]
        
        # Format timestamp based on database type
        if database_type == "MySQL":
            # MySQL format: YYYY-MM-DD HH:MM:SS
            timestamp = "%s-%s-%s %s:%s:%s" % (ts_year, ts_month, ts_day, ts_hour, ts_min, ts_sec)
            # MySQL format for date: YYYY-MM-DD
            mdy = "%s-%s-%s" % (ts_year, ts_month, ts_day)
        else:
            # Access format: MM/DD/YYYY HH:MM:SS
            timestamp = "%s/%s/%s %s:%s:%s" % (ts_month, ts_day, ts_year, ts_hour, ts_min, ts_sec)
            # Access format for date: MM/DD/YYYY
            mdy = "%s/%s/%s" % (ts_month, ts_day, ts_year)
            
        windDirection_deg = getSensorDataDict( stationData, "wind_direction")["value"]
        windDirection_timeStamp = getSensorDataDict( stationData, "wind_direction")["date_time"]
        
        windSpeed_mph = round( getSensorDataDict( stationData, "wind_speed")["value"] * knots_to_mph, 1)
        windGust_timeStamp = getSensorDataDict( stationData, "wind_gust")["date_time"]
        if (windGust_timeStamp == windDirection_timeStamp):
            windGust_mph = round( getSensorDataDict( stationData, "wind_gust")["value"] * knots_to_mph, 1)
        else:
            windGust_mph = windSpeed_mph
        
        # Some stations don't have a pressure sensor
        pressure_raw = getSensorDataDict( stationData, "sea_level_pressure")["value"]
        if (pressure_raw != 'NULL'):
            pressure_inHg = round( pressure_raw * 0.02953, 2) # from millibars
        else:
            pressure_inHg = "NULL"
            
        stationName = station_dic[ stationData['STID']]['longName']
            
        # Populate the weather dictionary: time and sensor data.
        weather_dic = {'station_number': inQu( station_dic[ stationData['STID']]['ID']),
                       'station_name': inQu( stationName),
                       'epoch_at_write': inQu( math.trunc( time.time())),
                       'timeStamp_on_drybulb': inQu( timestamp_literal),
                       'time_native_std': inQu( timestamp),
                       'MDY': inQu( mdy),
                       'Hr': inQu( ts_hour), 
                       'Min': inQu( ts_min),  
                       'T_drybulb': inQu( temp_f),  
                       'T_dewpoint': inQu( dewPoint_f),
                       'wind_direction': inQu( windDirection_deg),
                       'DDCARD':'NULL',
                       'wind_speed': inQu( windSpeed_mph),
                       'wind_gust': inQu( windGust_mph),
                       'ALTSE': inQu( pressure_inHg),
                       'P':'NULL'}
        
        print(json.dumps( weather_dic, indent=2))
        
        try:
            # Develop SQL string
            sqlForStation = build_SQL_string( weather_dic) 

            # Run the SQL (send formal SQL string and info list). If a
            # successful write is indicated, bump up the counter.
            if (runSQL( sqlForStation[0], sqlForStation[1])):
                write_count += 1
                
                # Add this station's record to the spreadsheet array.
                newRow = [stationName, utc( timestamp_literal), nN( temp_f), nN( dewPoint_f), nN( windDirection_deg), nN( windSpeed_mph), nN( windGust_mph), nN( pressure_inHg)]
                rowsForSpreadsheet.append( newRow)
                
        except Exception as e:
            message_str = f"Error in station {stationName} (ID: {station_dic[stationData['STID']]['ID']}): {type(e).__name__} ==> {str(e)}"
            enterInLog(message_str)
            print(message_str)
            print("SQL construction or execution failed.")
    
    
    # If there was a successful write to database, make entry in log showing
    # the number of successful gleans from the web site and the number of
    # successful writes to the database.
    # W = Writes
    # P = Possible (number of stations collecting from)
    print("")
    message_str = "Data write record: %s P, %s W" % ( station_count, write_count)
    print(message_str)
    
    if (write_count > 0):
        enterInLog( message_str) 
        attemptWriteToDaysGleaned(database_type)
        
        write_to_spreadsheet("meso", rowsForSpreadsheet)
        

def build_SQL_string( wd):
    # Input parameter is the weather dictionary (wd is short for weather_dic)

    # Format SQL field names based on database type
    if database_type == "MySQL":
        # MySQL doesn't need square brackets
        sql_names = "INSERT INTO FifteenMinData (" +\
                    "PerlTime, DateTimeStamp, LiteralDateTimeStamp, TimeMDY, TimeHr, TimeMin, " +\
                    "StationNumber, StationName, WindDirection, WindSpeed, WindGust, " +\
                    "TempAvg, DewPoint, Pressure) "
    else:
        # Access uses square brackets for field names
        sql_names = "INSERT INTO FifteenMinData (" +\
                    "[PerlTime], [DateTimeStamp], [LiteralDateTimeStamp], [TimeMDY], [TimeHr], [TimeMin], " +\
                    "[StationNumber], [StationName], [WindDirection], [WindSpeed], [WindGust], " +\
                    "[TempAvg], [DewPoint], [Pressure]) "
    
    sql_values = "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)" % (
                    wd['epoch_at_write'], wd['time_native_std'], wd['timeStamp_on_drybulb'], wd['MDY'], wd['Hr'], wd['Min'], 
                    wd['station_number'], wd['station_name'], wd['wind_direction'], wd['wind_speed'], wd['wind_gust'], 
                    wd['T_drybulb'], wd['T_dewpoint'], wd['ALTSE'])

    sql_string = sql_names + sql_values
    print("SQL string = ", sql_string)

    # Return SQL string and data list (to be used with error messages)
    return (sql_string, sql_values)


"""
Main program
"""

database_type = "MySQL" # "Access" or "MySQL"

# global variables (any variable in Main that get assigned)
knots_to_mph = 1.15078030303

# Dictionary of dictionaries data structure used identify all the stations
# to be gleaned and associated parameters. Add more stations here if you like...

station_dic = {
    # Washington
    'KRLD':{'ID':'318','longName':'KRLD','dst':True},    # Richland, WA
    'KMWH':{'ID':'357','longName':'KMWH','dst':True},    # Moses Lake, WA
    'KEAT':{'ID':'365','longName':'KEAT','dst':True},    # Wenatchee, WA
    'KNOW':{'ID':'366','longName':'KNOW','dst':True},    # Port Angeles, WA
    'K0S9':{'ID':'367','longName':'K0S9','dst':True},    # Port Townsend, WA

    # Alaska
    #'PAWI':{'ID':'389','longName':'PAWI','dst':True},    # Wainwright AP, AK
    'PABR':{'ID':'390','longName':'PABR.2','dst':True},  # Utqiaġvik (formerly Barrow), AK
    'PAQT':{'ID':'391','longName':'PAQT','dst':True},    # Nuiqsut, AK
    'PASI':{'ID':'392','longName':'PASI','dst':True},    # Sitka, AK
    'PAFA':{'ID':'393','longName':'PAFA','dst':True},    # Fairbanks Int AP, AK
    'PATQ':{'ID':'394','longName':'PATQ','dst':True},    # Atqasuk, AK
    'PANC':{'ID':'395','longName':'PANC','dst':True},    # Anchorage, AK

    # BC Canada
    'CYAZ':{'ID':'368','longName':'CYAZ','dst':True},    # Tofino, BC

    # Oregon
    'HOXO':{'ID':'354','longName':'HOXO','dst':True},    # Hood River, OR
    'KOTH':{'ID':'356','longName':'KOTH','dst':True},    # North Bend, OR
        
    # Fritz's sites on the cape...
    'KHSE':{'ID':'358','longName':'KHSE.2','dst':True},  # Cape Hatteras, NC
    'KCQX':{'ID':'359','longName':'KCQX.2','dst':True},  # Chatham, MA

    # Hawaii
    'PHOG':{'ID':'351','longName':'PHOG','dst':False},   # Maui Airport, HI
    'PHJR':{'ID':'352','longName':'PHJR','dst':False},   # Oahu, Kalaeloa Airport, HI
    'PHBK':{'ID':'353','longName':'PHBK','dst':False},   # Kauai, Barking Sands Airport, HI

    # Kansas  
    'KOJC':{'ID':'388','longName':'KOJC','dst':True},    # Johnson County Executive Airport, Olathe, KS

    # Missouri
    'KSTL':{'ID':'360','longName':'KSTL','dst':True},    # Saint Louis, MO
    'KJLN':{'ID':'387','longName':'KJLN','dst':True},    # Joplin Regional Airport, MO

    # MN
    'KMKT':{'ID':'355','longName':'KMKT.2','dst':True},  # Mankato, MN
    'KSOM5':{'ID':'361','longName':'KSOM5','dst':True},  # Kasota Prairie, MN
    'MN073':{'ID':'362','longName':'MN073','dst':True},  # Mankato, MN

    # Columbia River (for delta-p chart)
    'KDLS':{'ID':'166','longName':'KDLS','dst':True},    # Dalles, WA 
    'KTTD':{'ID':'167','longName':'KTTD','dst':True},    # Troutdale, OR 
    'KHRI':{'ID':'168','longName':'KHRI','dst':True},    # Hermiston, OR 

    # Florida
    'KAPF':{'ID':'396','longName':'KAPF','dst':True},    # Naples, FL 
    'KSRQ':{'ID':'397','longName':'KSRQ','dst':True}     # Sarasota, FL 
}

# Prepare to write to database and log file.
openConnections(database_type, "wgl_python_meso_log.txt")

# Make a single JSON request for all the stations. Parse and write to database, once for each station. 
processMultipleStations_json( station_dic)

# Close connections to database and log file.
closeConnections()
