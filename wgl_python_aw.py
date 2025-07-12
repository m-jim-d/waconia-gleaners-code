#!/usr/bin/env python3

"""
wgl_python_aw.py

Description: An XML gleaner for collecting MN, WI, and IA METAR weather data.
Written by: Jim Miller (7/6/2025)

"""


"""
An example of an XML report from a single station.

Here is an example of a single-site query:
https://aviationweather.gov/cgi-bin/data/dataserver.php?dataSource=metars&requestType=retrieve&format=xml&mostrecentforeachstation=constraint&hoursBeforeNow=2&stationString=KMKT

And the XML report:
<response version="1.2" xsi:noNamespaceSchemaLocation="http://aviationweather.gov/adds/schema/metar1_2.xsd">
    <request_index>2337556</request_index>
    <data_source name="metars"/>
    <request type="retrieve"/>
    <errors/>
    <warnings/>
    <time_taken_ms>3</time_taken_ms>
    <data num_results="1">
        <METAR>
            <raw_text>
                KMKT 292235Z AUTO 03013G19KT 10SM CLR 19/M02 A2998 RMK AO1
            </raw_text>
            <station_id>KMKT</station_id>
            <observation_time>2015-04-29T22:35:00Z</observation_time>
            <latitude>44.22</latitude>
            <longitude>-93.92</longitude>
            <temp_c>19.0</temp_c>
            <dewpoint_c>-2.0</dewpoint_c>
            <wind_dir_degrees>30</wind_dir_degrees>
            <wind_speed_kt>13</wind_speed_kt>
            <wind_gust_kt>19</wind_gust_kt>
            <visibility_statute_mi>10.0</visibility_statute_mi>
            <altim_in_hg>29.97933</altim_in_hg>
            <quality_control_flags>
                <auto>TRUE</auto>
                <auto_station>TRUE</auto_station>
            </quality_control_flags>
            <sky_condition sky_cover="CLR"/>
            <flight_category>VFR</flight_category>
            <metar_type>METAR</metar_type>
            <elevation_m>311.0</elevation_m>
        </METAR>
    </data>
</response>
"""


"""
Import supporting modules
"""

import sys
import requests
from xml.dom.minidom import parse
from io import BytesIO # This helps convert the response content to a file-like object
import time
import datetime
from xml.dom.minidom import parse # In support of XML parsing

from wgl_python_module import (write_to_spreadsheet, openConnections, closeConnections, enterInLog, 
    runSQL, attemptWriteToDaysGleaned, updateMaxStationDateTime
)

"""
Functions
"""

def nZS( string):
    # When writing to the spreadsheet, zero-length strings should be represented as None 
    if (string == ""):
        value = None
    else:
        value = string
    return value
    
    
def utc( timeTuple):
    timeString = "%d/%d/%d %d:%d:%d" % (timeTuple[1], timeTuple[2], timeTuple[0], timeTuple[3], timeTuple[4], timeTuple[5])
    return timeString


def processMultipleStations_xml(station_dictionary):
    # Build the URL string to get data from Multiple stations by making one query to the server.
    # (returned on one page).

    # Single station query for KMKT
    # https://aviationweather.gov/cgi-bin/data/dataserver.php?dataSource=metars&requestType=retrieve&format=xml&mostrecentforeachstation=constraint&hoursBeforeNow=2&stationString=KMKT
    # 
    # https://aviationweather.gov/cgi-bin/data/dataserver.php (current server)
    # https://aviationweather.gov/adds/dataserver_current/httpparam (old)
    
    url_base = ("https://aviationweather.gov/cgi-bin/data/dataserver.php?" + 
                    "dataSource=metars&" + 
                    "requestType=retrieve&" +
                    "format=xml&" +
                    "mostrecentforeachstation=constraint&" + 
                    "hoursBeforeNow=2&" +
                    "stationString=")

    # Get count of stations
    station_count = len(station_dictionary)
    
    # Join all station names with commas
    station_names = ",".join(station_dictionary.keys())
    
    # Build the complete URL
    webpage_url = url_base + station_names

    try:
        # Fetch the XML
        response = requests.get(webpage_url)
    except: 
        message_str = "Error opening url ::: %s ==> %s" % (sys.exc_info()[0], sys.exc_info()[1])
        enterInLog( message_str)
        print(message_str)
        # Stop here.
        return ''

    try:
        # Parse the XML
        dom_object = parse(BytesIO(response.content))
    except: 
        message_str = "Error parsing XML ::: %s ==> %s" % (sys.exc_info()[0], sys.exc_info()[1])
        enterInLog( message_str)
        print(message_str)
        # Stop here.
        return ''

    rowsForSpreadsheet = []

    # Check for error and warning messages in the XML. If found, write to log
    # and exit subroutine.

    message_error = getXMLvalueFirstElement(dom_object, "error")    
    message_warning = getXMLvalueFirstElement(dom_object, "warning")     

    if (message_error != '') or (message_warning != ''):
        # Send warnings to log file (and should also email a message).
        message_str = "Warning = %s \nError = %s" % (message_warning, message_error) 
        enterInLog( message_str) 
        print(message_str)

        # If there is an error (i.e., no data to work with), exit this function. 
        if (message_error != ''): 
            return ''

    # Check an attribute in the XML to find the number of sites that return
    # data.
    n_data = int(dom_object.getElementsByTagName("data")[0].attributes["num_results"].value)

    # Write data for each station
    write_count = 0
    for data_index in range(n_data):  # range of 0 to n_data-1
        try:
            # Develop SQL statement
            sqlForStation = buildSQL_xml(dom_object, data_index) 

            # Run the SQL (send formal SQL string and info list). If a
            # successful write is indicated, bump up the counter.
            if (runSQL( sqlForStation[0], sqlForStation[1])):
                write_count = write_count + 1
                
                rowsForSpreadsheet.append( sqlForStation[2])

        except Exception as e:
            # Get station name for better error reporting
            station_name = getXMLvalueInStationGroup(dom_object, data_index, "station_id")
            
            # Use f-string for cleaner formatting
            message_str = f"general error in Station loop ::: {type(e).__name__} ==> {str(e)}, \nStation name = {station_name}"
            enterInLog(message_str)
            print(message_str)        

    # If there was a successful write to database, make entry in log showing
    # the number of successful gleans from the web site and the number of
    # successful writes to the database.
    # W = Writes
    # G = Gleans
    # P = Possible (number of stations collecting from)
    if (write_count > 0):
        message_str = "New data added: %sW %sG %sP" % (write_count, n_data, station_count) 
        enterInLog( message_str) 
        attemptWriteToDaysGleaned(database_type)
        
        write_to_spreadsheet("aw-test", rowsForSpreadsheet)
        
    else:
        print("")
        print("url = %s" % (webpage_url))

    print("%s successful writes from %s of %s stations returning data." % (write_count, n_data, station_count))
    #print("station names = ", station_names)


def getXMLvalueFirstElement(dom_object, itemName):
    """
    Get the value of the first element with the specified name.
    
    Args:
        dom_object: XML DOM object to search in
        itemName: Name of the element to find
        
    Returns:
        String value of the element or empty string if not found
    """
    try:
        value = dom_object.getElementsByTagName(itemName)[0].childNodes[0].data
    except Exception as e:
        # More specific exception handling - could log the exception type if needed
        value = ''
    
    return value


def getXMLvalueInStationGroup(dom_object, data_index, itemName):
    """
    Get a value from within a specific METAR station group.
    
    This approach avoids the problem associated with the Wind Gust data.
    It's not always present in each metar group, so if you search directly
    for wind gust data using getElementsByTagName and index, data associations
    will get confused. This approach is better as it only searches for
    data from within an individual metar group.
    
    Args:
        dom_object: XML DOM object to search in
        data_index: Index of the METAR group to search within
        itemName: Name of the element to find within the METAR group
        
    Returns:
        String value of the element or empty string if not found
    """
    try:
        nth_metar_group = dom_object.getElementsByTagName("METAR")[data_index]
        value = nth_metar_group.getElementsByTagName(itemName)[0].childNodes[0].data
    except Exception as e:
        value = ''
    
    return value


def cent_to_far(temp_c):
    if temp_c == '':
        t_far = '' 
    else:
        t_far = round(((9.0/5.0) * float(temp_c)) + 32.0, 1)
    return t_far 


def buildSQL_xml(dom_object, data_index):
    # Read the station name in the nth hunk of data.
    station_name = getXMLvalueInStationGroup(dom_object, data_index, "station_id")
    print("\nStation = ", station_name)
    # Use the dictionary to look up the station number.
    station_number = station_dic[station_name]['ID']

    # Time (some necessary labor)

    # Get the ISO time string from the XML. This time stamp, in the XML, is not a local time,
    # but rather is in UTC time (formally known as Greenwich Mean time, GMT). In other words
    # this is not the local time of the weather station recording the data.
    time_ISO_UTC = getXMLvalueInStationGroup(dom_object, data_index, "observation_time")
    #print("time_ISO_UTC=", time_ISO_UTC)
    
    # Parse the time string, which is in an ISO format, into a tuple. First, slice off the 
    # trailing "Z" in the time string. Note that the Z is for Zulu time, or also known as UTC time.
    # (year, month, day, hour, minute, second, weekday, yearday, daylightSavingAdjustment) 
    time_tuple_UTC = time.strptime(time_ISO_UTC[:-1], "%Y-%m-%dT%H:%M:%S")
    print("time_tuple_UTC =", time_tuple_UTC)
    
    # The Unix epoch (or Unix time or POSIX time or Unix timestamp) is the number of seconds 
    # that have elapsed since January 1, 1970 (midnight UTC/GMT), not counting leap seconds 
    # (in ISO 8601: 1970-01-01T00:00:00Z).
    
    # Convert to seconds since the epoch. First it is important to know that 
    # mktime expects a local time, not a UTC time, and we have gotten a UTC 
    # time from the XML. So to correct for that, we must subtract off the 
    # timezones (in seconds) to correctly form the epoch time. Time.timezone 
    # is the offset of the local (non-DST) timezone, in seconds west of UTC. I 
    # know this seems ugly, but this is the simplest way to convert from UTC 
    # to epoch.
    
    # BUT, seems to me that this isn't a true EPOCH value. When I past the KMKT
    # value into an EPOCH to time converter it gives a value that is one hour behind
    # in the summer. Something is not right here...
    
    time_epoch = time.mktime(time_tuple_UTC) - time.timezone 
    #print("time_epoch =", time_epoch)

    # Side Note: This localtime function (using the time module) properly
    # determines if there is daylight savings time or not. You can use the
    # last value in the tuple to establish if DLS. As of March 2007, the times
    # in the database will be in local (to the weather station) standard time.

    time_tuple_gleaner = time.localtime(float(time_epoch)) 
    #print("time_tuple_gleaner =", time_tuple_gleaner)

    # This ASCII version might be handy for printing. Not currently used
    # anywhere else.
    time_tuple_gleaner_ascii = time.asctime(time_tuple_gleaner)
    #print("time_tuple_gleaner_ascii =", time_tuple_gleaner_ascii)

    # Create a datetime version of the time object. This will be in a timezone local
    # to the computer that is running this code (the gleaner). Apparently this always
    # returns a local (gleaner) standard time.
    time_datetime_gleaner_std = datetime.datetime.fromtimestamp(float(time_epoch)) 
    #print("time_datetime_gleaner_std =", time_datetime_gleaner_std)
    
    # Check for daylight savings time and properly generate a DLS version of
    # the local time. That is, spring forward if during DLS. This is needed
    # for updating the daysGleaned table in the database. Otherwise data
    # gleaned during the first hour after midnight will not trigger a new day
    # in the daysGleaned table (because standard time doesn't consider this
    # data a new day). And the website won't let you get at the new data
    # because there is no corresponding date in the "days" control. Confusing;
    # I know. This little juggle must be done because the web site plots in DLS
    # and the data is stored in the database as standard time. 

    # One issue here is that you have to use the gleaner time zone when doing this.
    # Probably would be better if used the native time zone.
    
    # If the last part of this tuple is equal to 1, then it's daylightsavings time. 
    if (time_tuple_gleaner[-1] == 1):
        timeshift = datetime.timedelta(hours=1)
        time_datetime_gleaner_dls = time_datetime_gleaner_std + timeshift 
    else:
        time_datetime_gleaner_dls = time_datetime_gleaner_std
    #print("time_datetime_gleaner_dls =", time_datetime_gleaner_dls)     
    
    # Shift the gleaner times to the native time zone (the local time zone where the sensor is).
    TZ_shift_net = station_dic[station_name]['TZS_MN'] - TZShift_gleanermoved
    time_datetime_native_std = time_datetime_gleaner_std + datetime.timedelta(hours=TZ_shift_net)
    time_datetime_native_dls = time_datetime_gleaner_dls + datetime.timedelta(hours=TZ_shift_net)
    #print("time_datetime_native_std =", time_datetime_native_std)
    
    # Update the global variable that keeps the latest DLS datetime value (a
    # datetime object).
    updateMaxStationDateTime(time_datetime_native_dls)
    
    # Here is a way to create a time tuple from a datetime object. TLS is just
    # a short name that is handy in the string-builder code below.
    tls = time_datetime_native_std.timetuple()
    #print("tls =", tls)

    # Build date strings that will work with the database operation (insert):
    if database_type == "Access":
        # Access format (MM/DD/YYYY)
        datetime_string = "%d/%d/%d %d:%d:%d" % (tls[1], tls[2], tls[0], tls[3], tls[4], 0)
        MDY_string = "%d/%d/%d" % (tls[1], tls[2], tls[0])
    else:
        # MySQL format (YYYY-MM-DD)
        datetime_string = "%d-%02d-%02d %02d:%02d:%02d" % (tls[0], tls[1], tls[2], tls[3], tls[4], 0)
        MDY_string = "%d-%02d-%02d" % (tls[0], tls[1], tls[2])
    
    # print("Datetime string = ", datetime_string)

    Hr_string = "%d" % (tls[3]) 
    Min_string = "%d" % (tls[4]) 

    # Get the rest of the data
    wind_dir_degrees = getXMLvalueInStationGroup(dom_object, data_index, "wind_dir_degrees")
    
    knots_to_mph = 1.15078030303 
    wind_speed_kt = getXMLvalueInStationGroup(dom_object, data_index, "wind_speed_kt")
    if (wind_speed_kt == ''):
        wind_speed_mph = ''
        wind_dir_degrees = ''
    else:
        wind_speed_mph = round(float(wind_speed_kt) * knots_to_mph, 0)
        if (wind_speed_mph == 0.0):
            wind_dir_degrees = ''

    if wind_dir_degrees != '':
        print("wind_dir_degrees = ", wind_dir_degrees)
        # Handle non-numeric wind directions like 'VRB' (variable)
        try:
            if (float(wind_dir_degrees) < 0.0):
                wind_dir_degrees = ''
        except ValueError:
            # If wind direction is not a number (e.g., 'VRB'), set to ''. This
            # will effectively remove it from the SQL string.
            wind_dir_degrees = ''
            
    wind_gust_kt = getXMLvalueInStationGroup(dom_object, data_index, "wind_gust_kt")
    if (wind_gust_kt == ''): 
        wind_gust_mph = wind_speed_mph 
    else:
        wind_gust_mph = round(float(wind_gust_kt) * knots_to_mph, 0)
        
    temp_c = getXMLvalueInStationGroup(dom_object, data_index, "temp_c")
    temp_f = cent_to_far(temp_c)
    
    dewpoint_c = getXMLvalueInStationGroup(dom_object, data_index, "dewpoint_c")
    dewpoint_f = cent_to_far(dewpoint_c) 
    
    altim_in_hg = getXMLvalueInStationGroup(dom_object, data_index, "altim_in_hg")

    # Construct the string: this block of code loops through the values
    # building up the SQL string as long as there are no empty string values.
    # This is one way to insert NULL values into the database (i.e. just
    # take them completely out of the SQL string)

    sql_data_raw = ( 
        str(time_epoch), datetime_string, time_ISO_UTC, MDY_string, Hr_string, Min_string,
        str(station_number), station_name, str(wind_dir_degrees), str(wind_speed_mph), str(wind_gust_mph),
        str(temp_f), str(dewpoint_f), str(altim_in_hg) )
   
    sql_names_raw = (
        'PerlTime', 'DateTimeStamp', 'LiteralDateTimeStamp', 'TimeMDY', 'TimeHr', 'TimeMin', 
        'StationNumber', 'StationName', 'WindDirection', 'WindSpeed', 'WindGust', 
        'TempAvg', 'DewPoint', 'Pressure') 
        
    spreadSheetRow = [station_name, utc( time_tuple_UTC), nZS( temp_f), nZS( dewpoint_f), nZS( wind_dir_degrees), nZS( wind_speed_mph), nZS( wind_gust_mph), nZS( altim_in_hg)]

    sql_names = "INSERT INTO FifteenMinData ("
    sql_format = "VALUES ("
    sql_data = () # Empty tuple
    index = 0
    for data_value in sql_data_raw:
        if data_value != '':
            sql_names = sql_names + sql_names_raw[index] + ", "
            # Add a value to the tuple; note a single value tuple must be represented with a comma..
            sql_data = sql_data + (data_value,)
            # Note: best practice would be to not quote numeric values, quote only strings and dates.
            sql_format = sql_format + "'%s'," 
        index = index + 1
    # remove the last comma and append a ")" 
    sql_format = sql_format[:-1] + ")"
    sql_names = sql_names[:-2] + ") " 

    # Nice to see this at the console (when manually running).
    print(sql_data)
    
    # Apply the formatting operation. Note this sql_data MUST be a tuple for
    # this formatting approach to work.
    sql_data_formatted = sql_format % sql_data  

    sql_string = sql_names + sql_data_formatted
    print("SQL string = ", sql_string)

    # Return SQL string and data list (to be used with error messages)
    return (sql_string, sql_data, spreadSheetRow)


"""
Main program
"""

# global variables (any variables in Main that get assigned)

#database_type = "Access"
database_type = "MySQL"

# This global is used for triggering a new day in the database's daysgleaned table.
time_datetime_maxDLSdate = datetime.datetime(2001,1,1) # initialize to some old date

# This global is used to shift the time-zone shifts if the gleaner is ever
# moved from MN.
TZShift_gleanermoved = 0

# The airport site name/number dictionary
station_dic = {
   # Sites near Saint Peter.                  
   'KMKT':{'ID':'101','TZS_MN':0},  # Mankato
   'KMML':{'ID':'102','TZS_MN':0},  # Marshall
   'KFRM':{'ID':'103','TZS_MN':0},  # Fairmont
   'KHCD':{'ID':'104','TZS_MN':0},  # Hutchinson
   'KULM':{'ID':'105','TZS_MN':0},  # New Ulm
   
   'KFBL':{'ID':'106','TZS_MN':0},  # Faribault
   'KAEL':{'ID':'107','TZS_MN':0},  # Albert Lea
   'KOWA':{'ID':'108','TZS_MN':0},  # Owatonna

   # Sites near Waconia.                                                       
   'KLVN':{'ID':'110','TZS_MN':0},  # Lakeville
   'KGYL':{'ID':'111','TZS_MN':0},  # Glencoe
   'KLJF':{'ID':'112','TZS_MN':0},  # Litchfield
   'KBDH':{'ID':'113','TZS_MN':0},  # Willmar
   'KPEX':{'ID':'114','TZS_MN':0},  # Paynesville

   # Sites near Worthington.
   'KOTG':{'ID':'120','TZS_MN':0},  # Worthington
   'KSPW':{'ID':'121','TZS_MN':0},  # Spencer, IA
   
   # Sites near Mille Lacs (Aitkin).
   'KAIT':{'ID':'130','TZS_MN':0},  # Aitkin
   'KJMR':{'ID':'131','TZS_MN':0},  # Mora
   
   # Sites in general.
   'KFGN':{'ID':'140','TZS_MN':0},  # Flag Island
   'KDYT':{'ID':'141','TZS_MN':0},  # Duluth
   'KLSE':{'ID':'142','TZS_MN':0},  # La Cross
   'KONA':{'ID':'143','TZS_MN':0},  # Winona
   'KRGK':{'ID':'144','TZS_MN':0},  # Red Wing
                         
   'KCFE':{'ID':'145','TZS_MN':0},  # Buffalo Muni
   'KAXN':{'ID':'146','TZS_MN':0},  # Alexandria
   'KFFM':{'ID':'147','TZS_MN':0},  # Fergus Falls
   'KADC':{'ID':'148','TZS_MN':0},  # Wadena Muni
   'KGHW':{'ID':'149','TZS_MN':0},  # Glenwood
   
   'KBRD':{'ID':'150','TZS_MN':0},  # Brainerd
   'KLXL':{'ID':'151','TZS_MN':0},  # Little Falls
   
   # Sites near White Bear and Saint Croix River.
   'KRNH':{'ID':'160','TZS_MN':0},  # New Richmond
   'KANE':{'ID':'161','TZS_MN':0},  # Blaine
   'KSTP':{'ID':'162','TZS_MN':0},  # Saint Paul
   
   # Fritz's sites on the cape...
   'KCQX':{'ID':'163','TZS_MN':1},  # Chatham, MA
   
   # Alaska...
   'PABR':{'ID':'200','TZS_MN':-3}, # Barrow, AK
   
   # Hatteras
   'KHSE':{'ID':'205','TZS_MN': 1}, # Cape Hatteras, NC

   # Pasco,WA airport...
   'KPSC':{'ID':'165','TZS_MN':-2}, # Pasco, WA 

   # Antarctica
   'NZSP':{'ID':'380','TZS_MN':18},  # AMUNDSEN-SCOTT

   # Japan
   'RJTT':{'ID':'385','TZS_MN':15},  # TOKYO INTL AIRPO 
   
   # Near Bob Douglas in GA
   'KSSI':{'ID':'386','TZS_MN': 1}   # GA BRUNSWICK
} 


# Prepare to write to database and log file.
openConnections(database_type, "wgl_python_aw_log.txt")

# Fetch one page, then parse and write to database once for each site 
processMultipleStations_xml(station_dic)

# Run cleanup query. Old records are deleted from the database.
nDaysBack = datetime.date.today() - datetime.timedelta(days=+366)
nDB = nDaysBack.timetuple()
print("\nSQL initiated to remove old records from two tables.")

if database_type == "Access":
    # MS Access syntax
    access_date = f"{nDB[0]}/{nDB[1]}/{nDB[2]}"  # Format as YYYY/MM/DD
    runSQL(f"DELETE * FROM [FifteenMinData] WHERE ([TimeMDY] < #{access_date}#)", "")
    runSQL(f"DELETE * FROM [DaysGleaned] WHERE ([TimeMDY] < #{access_date}#)", "")
else:
    # MySQL syntax
    mysql_date = f"{nDB[0]}-{nDB[1]:02d}-{nDB[2]:02d}"  # Format as YYYY-MM-DD
    runSQL(f"DELETE FROM FifteenMinData WHERE TimeMDY < '{mysql_date}'", "")
    runSQL(f"DELETE FROM DaysGleaned WHERE TimeMDY < '{mysql_date}'", "")

# Close connections to database and log file.
closeConnections()
