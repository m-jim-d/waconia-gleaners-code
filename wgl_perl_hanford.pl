# wgl_perl_hanford.pl
# Weather Gleaner for Hanford webpages.
# Jim Miller, 10:34 AM Sat July 5, 2025

use LWP::Simple;
use Time::Local;
use Date::Calc qw(Decode_Date_US Now Today Delta_Days Delta_DHMS System_Clock);
use DBI;
use Win32::ODBC;
use DateTime;
use Date::Manip qw(ParseDate DateCalc UnixDate Delta_Format);
use POSIX qw(floor);
use JSON;

use lib '.';
use wgl_perl_module qw(connect_database get_null execute_sql close_database
               add_google_sheet_row clear_google_sheet_data 
               get_google_sheet_row_count send_to_google_sheet open_log_file);

use strict;

#-------------------------------------------
#-----Globals-------------------------------
#-------------------------------------------

my @Now;
my $URL;

my $content;
my @thelines;
my $nlines;
my @thewords;

my $database_type;
my $DSN;
my $TelemOK;
my $cnTelem;
my $null;

my $StationNumber;
my $StationNumber_lastletter;
my $Station;
my $Station_state;

my $TheRawDate;
my $TheRawTime;
my @TheRawTime_parts;
my $TheCorrectedDateTime;
my @WeirdTime;

my ($TheDate, $TheYear, $TheMonth, $TheDay, $TheHour, $TheMin, $TheSec);
my $TheDate_mysql;
my $DateTimeStamp_mysql;

my ($WindDir, $WindAvg, $WindMax, $BPAvg, $BPAvg_sl, $TempAvg, $TempMax, $TempMin, $DewPoint);
my $Alt_ft;

my $googleSheet_data;

my $log_fh;

# \\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\

# Subroutines

sub parseTemperature {
   # Consider the case where temperatures are over 100F and the fixed formatting will produce
   # text like this (see below) where there is no space after the = sign. If you don't parse this, the
   # Celsius value will be used inadvertently.

=pod
                          Celsius
   Ave Temp =100.3          34.06
   Max Temp =102.4          34.66
   Min Temp = 99.8          33.79

=cut

   my $dryBulb;
   # Input parameters:
   my $equalSign_raw = $_[0];
   my $dryBulb_raw = $_[1];

   if (length($equalSign_raw) > 1) {
      $dryBulb = substr( $equalSign_raw, 1, length($equalSign_raw) - 1);
   } else {
      $dryBulb = $dryBulb_raw;
   }
   return $dryBulb;
}

sub SnapTo15 { 
   # This routine is used to snap any date/time string to the nearest 15
   # minutes. This is useful for insuring common timestamps when doing SQL
   # joins needed for the delta-p plot on Waconia. The only input is a
   # date/time string. For example:  "5/5/2000 23:16"; It returns one
   # date/time string of the format generally returned by ParseDate.

   my $ParsedDate;
   my $DeltaDate;
   my $DeltaInHours;
   my $DeltaIn15mins;
   my $Rounded;
   my $CorrectedHoursDelta;
   my $JustTheHoursDelta;
   my $JustTheMinsDelta;
   my $AdderString;
   my $TheFixedDate;

   # Here is the input parameter...
   my $TheDateAndTime = $_[0];

   # First generate a parsedate date string;

   $ParsedDate = Date::Manip::ParseDate($TheDateAndTime);
   #print "$ParsedDate\n";
   #print Date::Manip::ParseDate("1/1/2000"), "\n";

   # Calculate the difference between that date and a reference date, 1/1/2000;

   $DeltaDate = DateCalc(Date::Manip::ParseDate("1/1/2000"), $ParsedDate, 0);
   #print " The delta = $DeltaDate \n";

   # Convert that difference string into a delta in hours.

   $DeltaInHours = Date::Manip::Delta_Format($DeltaDate, 5, "%ht");
   #print " The delta in hours = $DeltaInHours \n";

   # And next to a difference in 15-min chunks of time;

   $DeltaIn15mins = $DeltaInHours * 4.0;
   #print " The delta in 15-mins = $DeltaIn15mins \n";

   # Now round that number to the nearest integer. This is the magical step
   # that causes the snap-to-15 event.

   $Rounded = sprintf("%.0f",$DeltaIn15mins);
   #print " The rounded version = $Rounded \n";

   # Now convert back to hours;

   $CorrectedHoursDelta = $Rounded / 4.0;
   #print " The rounded hours = $CorrectedHoursDelta \n";

   # Now calculate the pure hours and pure minutes parts 

   $JustTheHoursDelta = POSIX::floor($Rounded / 4.0); 
   #print "Just the hours = $JustTheHoursDelta \n";
   $JustTheMinsDelta = 60 * ($CorrectedHoursDelta - $JustTheHoursDelta);
   #print "Just the minutes = $JustTheMinsDelta \n";

   # Make an adder string (in hours and minutes) to use relative to the 1/1/2000 date;

   $AdderString = "+ " . $JustTheHoursDelta . "Hours " . $JustTheMinsDelta . "Minutes";
   #print " $AdderString \n";

   # Use the adder string to calcualate the fixed (snapped to 15) date;

   $TheFixedDate = Date::Manip::DateCalc("1/1/2000",$AdderString);
   #print "$TheFixedDate \n"; 

   return $TheFixedDate;
}

sub CheckForWeirdLoggerTimeStamps {
   # The arguments passed
   my $SnappedTime = $_[0];
   my $RawHour = $_[1];   # The first element in the array passed

   # Local variables
   my $CorrectedDateTime;
   my $DD; 
   my $DH; 
   my $DM; 
   my $DS;

   my $TheDate = UnixDate($SnappedTime, "%m/%d/%Y");  
   my $TheHour = substr($SnappedTime,8,2);
   my $TheMin = substr($SnappedTime,11,2);
   my $TheSec = substr($SnappedTime,14,2);
  
   my $DecimalDayDiff;

   # Check for weird time stamps (around midnight) that are used by some of the
   # HMS data loggers. Look at the difference between the system clock and the 
   # snapped time.

   ($DD,$DH,$DM,$DS) = Delta_DHMS(Today(), Now(), 
                                  Decode_Date_US($TheDate), $TheHour, $TheMin, $TheSec);   

   # This DecimalDayDiff calc should really be done after the time correction is made and account for
   # daylight savings time.
   $DecimalDayDiff = $DD + $DH/24.0 + $DM/(24.0*60.0);

   # If there is more than a 5 hour difference and its around midnight
   # it must be a one of the suspect loggers.

   if (  (abs($DH) > 5) && (($RawHour==23) || ($RawHour==24))   ) {
      $CorrectedDateTime = Date::Manip::DateCalc($SnappedTime,"- 1 days"); 
      print " Differences from system clock (d,h,m,s):  $DD,$DH,$DM,$DS  $CorrectedDateTime  \n";
      return ($CorrectedDateTime, $DecimalDayDiff);  # return an array with two elements...
   } else {
      return ($SnappedTime, $DecimalDayDiff);
   }
}

sub cS {
   # clearString (cS)
   # This prepares values before writing to the Google sheet.
   # It translates the Null to an empty string.
   my $stringValue = $_[0];
   
   if ($stringValue eq $null) {
      $stringValue = "";
   } 
   return $stringValue;
}

# sub addRowToGoogleSheet {
#     # Prepare to add a new row to the googleSheet_data array.
#     my $pt_time = DateTime->new(
#         year => $TheYear,
#         month => $TheMonth,
#         day => $TheDay,
#         hour => $TheHour,
#         minute => $TheMin,
#         second => 0,
#     );
    
#     my $pt_string = $pt_time->strftime('%m/%d/%Y %H:%M:%S');
#     print "PST= $pt_string, ";
    
#     my $utc_time = $pt_time->clone->add(hours => 8);
    
#     my $utc_string = $utc_time->strftime('%m/%d/%Y %H:%M:%S');
#     print "UTC= $utc_string\n\n";
                
#     my @newRow = ( $Station, $utc_string, cS($TempAvg), cS($DewPoint), cS($WindDir), cS($WindAvg), cS($WindMax), cS($BPAvg_sl) );
#     push @$googleSheet_data, \@newRow;
# }

sub WriteToMDB {
   my $DateTimeStamp;
   my $LiteralDateTimeStamp;
   
   my ($Waconia_Year, $Waconia_Month, $Waconia_Day, $Waconia_Hour, $Waconia_Min, $Waconia_Sec);

   my $PerlTime;
   my $DateTimeStamp;
   my $LiteralDateTimeStamp;
   my $sql;

   my @SystemClock;
   my $NextDayDate;
   
   my $t_c;
   my $h_m;

   # Here is the HMS data date
   ($TheYear, $TheMonth, $TheDay) = Decode_Date_US($TheDate);

   # Here is the server date and time 
   ($Waconia_Year, $Waconia_Month, $Waconia_Day) = Today();
   ($Waconia_Hour, $Waconia_Min, $Waconia_Sec) = Now();

   #Timelocal requires that months start with zero.
   $PerlTime = timelocal(0,($Waconia_Min),($Waconia_Hour),($Waconia_Day),($Waconia_Month-1),$Waconia_Year);

   # Create the SQL statement for inserting a record of data into the mdb file.
  
   $DateTimeStamp = $TheMonth . "/" . $TheDay . "/" . $TheYear . " " . $TheHour . ":" . $TheMin;
   $LiteralDateTimeStamp = $TheRawDate . " " . $TheRawTime;

   # Check for bad values.
   # This puts an unquoted Null in the SQL string if there is a bad value.
   
   # Correct the pressure reading to be at sea-level altitude
   # Note: here are two different ways to do this correction. This syntax is python.
   # h_m = 390 / 3.28084
   # p_station = 29.565
   # t_k = (81.6 +  459.67) * 5.0/9.0
   # t_c = (81.6 - 32.0) * 5.0/9.0
   # A power-law model form:
   # p_sl = p_station * ((1 - ((0.0065*h_m)/(t_c + (0.0065*h_m) + 273.15))) ** (-5.257))
   # An exponential model form:
   # p_sl = p_station / math.exp(-h_m/(t_k*29.263))
   
   $t_c = ($TempAvg - 32.0) * 5.0/9.0;
   $h_m = $Alt_ft / 3.28084;
   
   if ($BPAvg ne $null) {
      # Using the power-law correction:
      $BPAvg_sl = $BPAvg * ((1 - ((0.0065*$h_m)/($t_c + (0.0065*$h_m) + 273.15))) ** (-5.257));
      # Round to 4 digits.
      $BPAvg_sl = sprintf("%.4f", $BPAvg_sl);
      #print "t_c=$t_c, Alt_ft=$Alt_ft, h_m=$h_m, P_raw=$BPAvg, P_SL=$BPAvg_sl\n";
      
      # Check for extreme BPAvg_sl values.
      if ( ($BPAvg_sl < 29.0) || ($BPAvg_sl > 31.0) ) {
         print "Pressure value, $BPAvg_sl, nulled for station $Station.\n";
         $BPAvg_sl = $null;
      }
   } else {
      $BPAvg_sl = $null;
   }
   
   # Check for extreme TempMin values. 
   if ( abs($TempAvg - $TempMin) > 20) {
      $TempMin = $null;
   }
   # Null out the direction value for any calm readings.
   if ( ($WindAvg == 0) && ($WindMax == 0) ) {
      $WindDir = $null;
   }

   # Note that in the VALUES part of the SQL, strings and dates are quoted, numbers are not.
   $sql = "INSERT INTO FifteenMinData (PerlTime, DateTimeStamp, LiteralDateTimeStamp, TimeMDY, TimeHr, TimeMin, StationNumber, ";
   $sql .= "StationName, WindDirection, WindSpeed, WindGust, ";
   $sql .= "TempAvg, TempMax, TempMin, Pressure, DewPoint) ";
   if ($database_type eq "access") {
      $sql .= "VALUES ($PerlTime,'$DateTimeStamp','$LiteralDateTimeStamp','$TheDate',$TheHour,$TheMin,$StationNumber,";
   } elsif ($database_type eq "mysql") {
      # MySQL format (YYYY-MM-DD)
      # Convert from MM/DD/YYYY to YYYY-MM-DD
      my ($month, $day, $year) = split('/', $TheDate);
      $TheDate_mysql = sprintf("%04d-%02d-%02d", $year, $month, $day);
      $DateTimeStamp_mysql = sprintf("%04d-%02d-%02d %02d:%02d:00", $year, $month, $day, $TheHour, $TheMin);
      $sql .= "VALUES ($PerlTime,'$DateTimeStamp_mysql','$LiteralDateTimeStamp','$TheDate_mysql',$TheHour,$TheMin,$StationNumber,";
   }
   $sql .= "'$Station',$WindDir,$WindAvg,$WindMax,$TempAvg,$TempMax,$TempMin,$BPAvg_sl,$DewPoint)";

   # If all numeric values are reasonable, write the record... Note: one or more
   # of these raw values may be $null, the null string. Strings are converted to
   # 0 in the numeric checks. So in these specific cases, these clauses always
   # evaluate true and do not block the write.
   if (  (($TempAvg >= -20) && ($TempAvg <=  120)) && 
         (($TempMax >= -20) && ($TempMax <=  120)) &&
         (($WindAvg >=   0) && ($WindAvg <=  130)) &&
         (($WindMax >=   0) && ($WindMax <=  150)) &&
         (($WindDir >=   0) && ($WindDir <=  360)) && 
         ( ($StationNumber ne "19a") ) &&
         ( ($StationNumber ne "6a") ) &&
         (($TheHour >= 0) && ($TheHour <= 23)) &&
         (($TheMin >= 0) && ($TheMin <= 59)) &&
         ($WeirdTime[1] < 100.00)   ) {  # Decimal day check for dead loggers that are dragging their time stamps into the next day...

      print "$TheDate, $TheHour, $TheMin, $StationNumber, $Station, WIND: $WindDir, $WindAvg, $WindMax, PRESSURE: $BPAvg_sl, TEMP: $TempAvg, $TempMax, $TempMin, $DewPoint\n";

      # Execute the SQL. Write weather data to the database.
      
      # Error checking here: the SQL method returns undefined if it is
      # successful and a non-zero integer error number if it fails.

      if ($TelemOK) {
         my ($success, $error) = execute_sql($sql);
         if ($success) {
            # Add a new row to the googleSheet array in the module.
            #addRowToGoogleSheet();
            add_google_sheet_row($Station, $TheYear, $TheMonth, $TheDay, $TheHour, $TheMin, 
                              cS($TempAvg), cS($DewPoint), cS($WindDir), cS($WindAvg), 
                              cS($WindMax), cS($BPAvg_sl), $log_fh);            
         }
      }

      # Write out the TimeMDY date to a special table that is used to quickly populate the date combo box.
      # Check for special case of Daylight Savings time AND the PST hour of 23. 
      # Otherwise you won't be able to request a chart from midnight to 1AM.
      # The ninth element in the returned array is a boolean for daylight savings time...
      
      @SystemClock = System_Clock(); 
      if (($SystemClock[8]) && ($TheHour==23)) {
         if ($database_type eq "access") {
            $NextDayDate = UnixDate( Date::Manip::DateCalc( $TheDate, "+ 1 days" ), "%m/%d/%Y"); 
         } elsif ($database_type eq "mysql") {
            $NextDayDate = UnixDate( Date::Manip::DateCalc( $TheDate, "+ 1 days" ), "%Y-%m-%d"); 
         }
         $sql = "INSERT INTO DaysGleaned (TimeMDY) VALUES ('$NextDayDate')";
      } else {
         if ($database_type eq "access") {
            $sql = "INSERT INTO DaysGleaned (TimeMDY) VALUES ('$TheDate')";
         } elsif ($database_type eq "mysql") {
            $sql = "INSERT INTO DaysGleaned (TimeMDY) VALUES ('$TheDate_mysql')";
         }  
      }
      
      if ($TelemOK) {
         # For DaysGleaned table, we don't care about duplicate entries
         # Pass quiet=1 to suppress console output
         execute_sql($sql, $log_fh, 1);
      }

   } else {
      print "Record failed reasonable test\n";
      print "  $TheDate, $TheHour, $TheMin, $StationNumber, $Station, WIND: $WindDir, $WindAvg, $WindMax, PRESSURE: $BPAvg_sl, TEMP: $TempAvg, $TempMax, $TempMin, $DewPoint\n";
   }
   
}


# \\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\

# Main Program Body

# Open the log file using the module function
my $log_file_path = 'C:\Users\Jim\Documents\webcontent\waconia\wgl_perl_hanford_log.txt';
(my $log_success, $log_fh, my $log_error) = open_log_file($log_file_path, 'Waconia Weather Data Collection Log');

if (!$log_success) {
    die "Failed to open log file: $log_error";
}

# Write a timestamp to the log file each time the script is run.
print $log_fh localtime(time) . " from wgl_perl_hanford.pl " . "\n";

# 5:14 PM Tue February 28, 2023. Yesterday the Perl "get" stopped working for the Hanford page. Left it here in
# comments. Replaced it with a call to a little Python script that fetches the page and puts it in a file.

# Get the page of data. Note the get function from 'LWP::Simple' returns undefined on error, so check for
# errors as follows....
#$URL = "http://hms.rl.gov/stainfo.htm";
#$URL = "http://hms.pnl.gov/stainfo.htm";

#$URL = "https://www.hanford.gov/c.cfm/hms/realtime.cfm";
# unless (defined ($content = get $URL)) {
   # my @now = localtime(time);
   # print $log_fh "Timestamp = @now[5,4,3,2,1]\n";
   # print $log_fh "Could not get $URL\n";
   # close($log_fh); 
   # my $error_message = getprint($URL);
   # die "Could not get $URL\n $error_message\n";
# }

my $cmd = "C:\\Users\\Jim\\Documents\\webcontent\\waconia\\wgl_perl_hanford_URLfetch.py";
system($cmd);  
# Note the "system" call is blocking and so this next statement won't run until the fetch completes.
#print "After system call to fetch the Hanford page.\n";

# Read in the txt file.
open(my $fh, '<', 'C:\\Users\\Jim\\Documents\\webcontent\\waconia\\wgl_perl_hanford_URLdump.txt') or die "Could not open file: $!";
my $content = do { local $/; <$fh> };
close($fh);

# Split the contents into lines.
@thelines = split (/\n/, $content);
$nlines = @thelines;

$database_type = "mysql"; # "mysql" or "access"

# Make a database connection to the Access (mdb) file or MySQL database using the module
($TelemOK, $cnTelem, my $error) = connect_database($database_type, $log_fh);

# Get NULL value from the module
$null = get_null($database_type);

if ( ! $TelemOK) {
   print $log_fh localtime(time) . " Error connecting to $database_type database\n";
   print $log_fh "Error: $error\n";
   warn "Error connecting to $database_type database: $error\n";
} else {
   print "Connected to $database_type database\n\n";
}

# Note: I have left rain gauge out of this data collection script. It is hard
# to include because it is the last entry in each section and/but some sections
# don't have it at all. The list of those that don't have it are EDNA, FRNK,
# GABL, PFP, GABW, VERN, HAMR. The write statement has to trigger on something
# that is common to all sections. Otherwise that section will just not get
# printed out. To make this work you would have to extend the 2 tier code that
# groups on those that are like FFTP and those that are not, to a 3 tier
# grouping: (1) like FFTP, (2a) not like FFTP and with Rain gauge, (2b) not
# like FFTP and without Rain gauge. 

$Station = $null;
$Alt_ft = 0;

# Initialize the Google-sheet array that will add a row of data for each successful SQL write.
$googleSheet_data = [];

foreach (@thelines) {
   
   if (/Station\#/) { 
      @thewords = split(" ", $_);
      
      # Some stations might be listed on the page but be decommissioned or temporarily down.
      # This flag can be used to make note if there is an indication given that it's not active.
      $Station_state = "ON"; 
      
      $StationNumber = $thewords[1];
      if ($StationNumber eq "19a"){
        # Remove the letter from StationNumber (i.e., the a).
        #$StationNumber_lastletter = chop($StationNumber)
        
        # Or better yet, just use 31, the old number for this site. Can't use 19 because the database
        # key includes the station number and 19 is already being used.
        $StationNumber = 31;
      }
      
      if ($thewords[2] eq "(") { 
         # Case with spaces, e.g. (  345) or ( 2345)
         # Remove the ")" at the end of the station name string.
         $Station = substr($thewords[3], 0,-1); 
         $Alt_ft = $thewords[5];
      } else {
         # Case where there are no spaces, e.g.: (12345)
         $Station = substr($thewords[2], 1, 5);
         $Alt_ft = $thewords[4];
      }
      # Ignore the following station-name strings
      if (($thewords[2] eq "Telemetry") or ("yes" eq "no")) {
         $Station_state = "OFF";
      }
      
      # Each time you find a new station section on the page initialize sensor values. Note that
      # not every sensor type is available at all stations, so it's important to set to Null here
      # in those cases.      
      $WindDir = $null;
      $WindAvg = $null;
      $WindMax = $null;
      
      $BPAvg = $null;
      
      $TempMin = $null;
      $TempAvg = $null;
      $TempMax = $null;
      
      $DewPoint = $null;
   }

   if (/Time:/) {
      @thewords = split(" ", $_);
      $TheRawDate = $thewords[4];
      $TheRawTime = $thewords[1];

      # If there's not a problem with the timestamp, run SnapTo15..
      # Note that this check is applied here (to avoid errors in SnapTo15) and also
      # below in the next block...
      
      @TheRawTime_parts = split(":", $TheRawTime);       
      
      if ($TheRawTime_parts[0] ne "99") {
	 
         # Nudge the date/time to the nearest 15 minutes.

         $TheCorrectedDateTime = SnapTo15($TheRawDate . " " . $TheRawTime);

         @WeirdTime = CheckForWeirdLoggerTimeStamps($TheCorrectedDateTime, @TheRawTime_parts);
         $TheCorrectedDateTime = @WeirdTime[0]; # The first array element is the fixed time...

         $TheDate = UnixDate($TheCorrectedDateTime, "%m/%d/%Y");  
         $TheHour = substr($TheCorrectedDateTime,8,2);
         $TheMin = substr($TheCorrectedDateTime,11,2);
         $TheSec = substr($TheCorrectedDateTime,14,2);
      }
   }

   # Look for the strings that indicate whether or not station is collecting data.
   if ((/Temporarily Unavailable/) || (/Decommissioned/)) {$Station_state = "OFF"}
   
   # Don't process this station if it has a bad date or if it is OFF for some reason.
   if (($TheRawTime_parts[0] ne "99") && ($Station_state eq "ON")) {
      
      # This block does the main parsing by looking for defining strings in each line.
      
      # Split the line up by the spaces in it.
      @thewords = split(" ", $_);  
            
      # Divide stations into two categories. The first group is contains 3 stations 
      # that have more detailed reporting and use a slightly different nomenclature
      # because of sensors positioned at various heights.
      if (($Station eq "FFTF") || ($Station eq "300A") || ($Station eq "100N")) {
	
         if (/Ave Wind Direction 10m/) {
            $WindDir = $thewords[5];
            if ($WindDir eq "-999") { $WindDir = ""; }
            
         } elsif (/Ave Wind Speed 10m/) {
            $WindAvg = $thewords[5];
            if ($WindAvg eq "-999") { $WindAvg = ""; } 
            
         } elsif (/Max Wind Speed 10m/) {
            $WindMax = $thewords[5];
            if ($WindMax eq "-999") { $WindMax = ""; }
            
         } elsif (/Ave BP/) {
            $BPAvg = $thewords[3];
            #print "Pressure reading at " . $Station . " = " . $BPAvg . "\n";
            
         } elsif (/Ave Temp 2m/) {
            $TempAvg = $thewords[4];
            $DewPoint = $thewords[8];
            
         } elsif (/Max Temp 2m/) {
            $TempMax = $thewords[4];
            
         } elsif (/Min Temp 2m/) {
            $TempMin = $thewords[4];
         
         }
      
      # This second group covers the remainder of the stations on the page.
      } else {
         if (/Ave Wind Direction/) {
            $WindDir = $thewords[4];
            if ($WindDir eq "-999") {$WindDir = ""; }
            
         } elsif (/Ave Wind Speed/) {
            $WindAvg = $thewords[4];
            if ($WindAvg eq "-999") {$WindAvg = ""; }
            
         } elsif (/Max Wind Speed/) {
            $WindMax = $thewords[4];
            if ($WindMax eq "-999") {$WindMax = ""; }
            
         } elsif (/Ave BP/) {
            $BPAvg = $thewords[3];
            #print "Pressure reading at " . $Station . " = " . $BPAvg . "\n";

         } elsif (/Ave Temp/) {
            # This forces the first Ave Temp reading within each station group. Some
            # stations have second building, so this prevents that temperature reading
            # from being used.
            if ($TempAvg eq $null) {$TempAvg = parseTemperature( $thewords[2], $thewords[3]);}
            
            if ($Station eq "200E") {
               $DewPoint = $thewords[7];
            }
            
         } elsif (/Max Temp/) {
            $TempMax = parseTemperature( $thewords[2], $thewords[3]); 
            
         } elsif (/Min Temp/) {
            $TempMin = parseTemperature( $thewords[2], $thewords[3]); 
         
         } elsif (/Dew Point/) {
            # RMTN
            $DewPoint = $thewords[3]; 
         
         } elsif ((/DewPt/)&&(/RH/)) {
            # HMS
            $DewPoint = $thewords[2]; 
         
         }
         
      } # divide stations into two categories...  

      # Write to the database at the end of each station section on the web page.
      if ((/Return to Map/) && ($Station ne $null)) {
         WriteToMDB();
         $Station = $null;
      }   
      
   } # Check for bad date
} #For each line...

# Close the database connection.
close_database();

my $row_count = get_google_sheet_row_count();
if ($row_count > 0) {
    # Let the module handle error reporting
    send_to_google_sheet('hanford-test', 
                        "C:\\Users\\Jim\\Documents\\webcontent\\waconia\\wgl_perl_hanford_data.json", 
                        "C:\\Users\\Jim\\Documents\\webcontent\\waconia\\wgl_perl_postToSheet.py",
                        $log_fh);
}

close($log_fh);