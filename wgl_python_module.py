"""
wgl_python_module.py

Description: A module for the xml and json weather gleaners.
Written by: Jim Miller (7/6/2025)

"""

#!/usr/bin/env python3

import sys, os
import datetime
import requests
import json
import pyodbc
import mysql.connector

# Global variables
logFile = None
database_conn = None
version_number = "1.0"

print("Version Number = ", version_number)

# This global is used for triggering a new day in the database's daysgleaned table.
stationDateTime_maxValue = datetime.datetime(2001,1,1) # initialize to some old date

def updateMaxStationDateTime( stationDateTime):
    # Check to see if stationDateTime is later than what's in the global. 
    # and update the value in the global if it is...

    # Must declare locally to change a global. If no global declaration, the
    # ASSIGNMENT statement will force this variable to be local here in this
    # function.
    
    global stationDateTime_maxValue

    if (stationDateTime > stationDateTime_maxValue):
        stationDateTime_maxValue = stationDateTime


def openConnections(database_type, logFileName):
    global logFile, database_conn

    # Open logFile and Database connection

    # The getcwd os function returns the current working directory. Another
    # similar command is os.path.abspath(""). Note that if this is running as a
    # system AT job, this will return something like "C:\\winnt\\system32"

    #logFileDir = os.getcwd()
    logFileDir = "C:\\Users\\Jim\\Documents\\webcontent\\waconia"
    
    #logFileName = "ws_richland_log.txt"
    logFilePath = logFileDir + "\\" + logFileName 

    # Check for the file and create a new one if none is found.
    # Note: os.curdir doesn't work as a way to find the current directory when
    # if this task is scheduled. So I use the absolute paths above.
    if logFileName not in os.listdir( logFileDir):
        try: 
            logFile = open(logFilePath, 'w')  # create and write 
        except:
            sys.exit("Error when opening log file to write. Script stopped!!!")  # Shutdown if no way to log...

        # Header in file.
        logFile.write('==============VERSION '+ version_number +'========================' + '\n')
        logFile.write('File created: ' + str(datetime.datetime.today()) + '\n')
        logFile.write('=================================================' + '\n')
        logFile.write('=================================================' + '\n')
        logFile.write('=================================================' + '\n')
    else:
        try:
            logFile = open(logFilePath, 'a')  # append
        except:
            sys.exit("Error when opening log file to append. Script stopped!!!")  # Shutdown if no way to log...

    if (database_type == "Access"):
        # Open Database connection using pyodbc
        
        # Path to the Access database
        db_path = r'C:/Users/Jim/Documents/webcontent/waconia/data/telem.mdb'
        
        try:
            # Connect using the Access Driver
            # Note: We're using a direct connection string instead of a DSN
            conn_str = (
                r'DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};'
                f'DBQ={db_path};'
            )
            database_conn = pyodbc.connect(conn_str)

        except Exception as e:
            exc_type = type(e).__name__
            exc_value = str(e)
            enterInLog(f"Error ::: {exc_type} ==> {exc_value}")
            # Close logFile on the way out.
            logFile.close() 
            sys.exit(f"Error when opening database connection: {exc_value}. Script stopped!!!")
    
    elif (database_type == "MySQL"):
        # Open Database connection using mysql.connector
        
        MYSQL_CONFIG = {
            'host': 'localhost',
            'user': 'root',
            'password': 'xwI6CxGgu7GGWrjvJMOG',
            'database': 'telem'
        }
        
        try:
            database_conn = mysql.connector.connect(**MYSQL_CONFIG)
            enterInLog("Successfully connected to MySQL database")

        except Exception as e:
            exc_type = type(e).__name__
            exc_value = str(e)
            enterInLog(f"Error ::: {exc_type} ==> {exc_value}")
            # Close logFile on the way out.
            logFile.close() 
            sys.exit(f"Error when opening database connection: {exc_value}. Script stopped!!!")


def closeConnections():
    database_conn.close()
    logFile.close()


def runSQL( sql_string, row_ascii):
    # row_ascii: Contains the variable names and is useful in constructing error messages.

    successful_execution = False 

    # Execute SQL string
    try:
        cursor = database_conn.cursor()
        cursor.execute(sql_string)
        database_conn.commit()
        cursor.close()
        successful_execution = True 
        
        # For testing
        #print("SQL = ", sql_string)
        #print("row_ascii = ", row_ascii)

    except pyodbc.Error as e:
        # Check for duplicate entry errors based on database type
        error_message = str(e).lower()
        is_duplicate_error = (
            ("duplicate data" in error_message) or  # MS Access error message
            ("duplicate entry" in error_message)    # MySQL error message
        )
        
        # If only a duplicate data error, don't write to the log file
        if is_duplicate_error:
            print("Data already in database (sql warning).")
        else:
            message_str = f"SQL error ::: {type(e).__name__} ==> {str(e)}, \nData value = {row_ascii}" 
            enterInLog(message_str)
            print(message_str)
        return successful_execution

    except Exception as e:
        message_str = f"general error ::: {type(e).__name__} ==> {str(e)}, \nData value = {row_ascii}" 
        enterInLog(message_str)
        print(message_str)
        return successful_execution

    else:  # Run this block if no errors...   
        print("Successful SQL execution!")
        return successful_execution


def attemptWriteToDaysGleaned(database_type):
    # This serves to keep the DaysGleaned table up to date. If this gleaner is
    # the first to cross into a new day this should produce a successful write.

    # Make a local tuple out of the global stationDateTime_maxValue
    dT = stationDateTime_maxValue.timetuple()

    # Format SQL string based on database type
    if database_type == "MySQL":
        # MySQL format: YYYY-MM-DD
        sql_string = "INSERT INTO DaysGleaned (TimeMDY) VALUES ('%s-%s-%s')" % (dT[0], dT[1], dT[2])
    else:
        # Access format: MM/DD/YYYY with square brackets for field names
        sql_string = "INSERT INTO DaysGleaned ([TimeMDY]) VALUES ('%s/%s/%s')" % (dT[1], dT[2], dT[0])
        
    try:
        cursor = database_conn.cursor()
        cursor.execute(sql_string)
        database_conn.commit()
        cursor.close()
        
    except Exception as e:
        # Check for duplicate entry errors based on database type
        error_message = str(e).lower()
        is_duplicate_error = (
            ("duplicate data" in error_message) or  # MS Access error message
            ("duplicate entry" in error_message)    # MySQL error message
        )
        
        # If duplicate data error, just print a warning
        if is_duplicate_error:
            print("Day already in DaysGleaned table (sql warning).")
        # If not a duplicate data error, write to the log file
        else:
            enterInLog(f"Error ::: {type(e).__name__} ==> {str(e)}")


def enterInLog( logentry):
    logFile.write('==============' + str(datetime.datetime.today()) + '====V ' + version_number + '\n')
    logFile.write( logentry + '\n')


def write_to_spreadsheet(sheetName, data):
    sheet_url = "https://script.google.com/macros/s/AKfycbzoEtsp1DLhvtt8OVrgwkhAzab5D6bYN1Mr_AKwzWvm9IfTXyHXmNFoxlSAnb0a_QlZLQ/exec"
    
    postDict = {"sheetName":sheetName, "weatherData":data}
 
    try:        
        # Send with POST. Note: the postDict dictionary gets converted to a JSON string.
        jsonRequest = requests.post( sheet_url, json=postDict)

        # Format and print the response
        print(json.dumps(jsonRequest.json(), indent=2))
        
    except:
        message_str = "Error opening URL."
        print(message_str + ", URL = " + sheet_url)
