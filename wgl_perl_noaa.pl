# wgl_perl_noaa.pl
# Weather Gleaner for NOAA webpages.
# Jim Miller, 10:45 AM Sat July 5, 2025

use LWP::Simple;
use Time::Local;
use Date::Calc qw(Decode_Date_US Now Today);
use Date::Manip qw(ParseDate DateCalc UnixDate);
use DateTime;
use JSON;

use lib '.';
use wgl_perl_module qw(connect_database get_null execute_sql close_database
               add_google_sheet_row clear_google_sheet_data 
               get_google_sheet_row_count send_to_google_sheet open_log_file);

use strict;

# Global variables
my ($WindDir, $WindAvg, $WindMax, $TempAvg, $DewPoint, $BPAvg);
my $log_fh; # Global filehandle for logging
my $googleSheet_data;
my %shortNames;
my $TelemOK;
my $cnTelem;
my $database_type;
my $null;
my $content;
my @thelines;
my $nlines;
my @thewords;
my $foundPage;
my ($TheCity, $StationNumber, $PressureStuff, $FirstLetter, $thetime, $ParsedDate, $PSTDate, $err);
my ($TheDate, $TheHour, $TheMin);
my $TZ;
my $WindDir_string;
my $Gust;
my $WindStuff;
my $PerlTime;
my $sql;
my $NextDayDate;

# \\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\

# Subroutines

sub cS {
   # clearString (cS)
   # This prepares values before writing to the Google sheet.
   # It translates the database NULL value to an empty string.
   my $stringValue = $_[0];
   
   if ($stringValue eq $null) {
      $stringValue = "";
   } 
   return $stringValue;
}

sub WriteToMDB {
   my $TheDate_mysql;
   my $DateTimeStamp;
   my $DateTimeStamp_mysql;
   my $LiteralDateTimeStamp;
   
   my ($Waconia_Year, $Waconia_Month, $Waconia_Day, $Waconia_Hour, $Waconia_Min, $Waconia_Sec);
   
   my @newRow_googleSheet;

   ($Waconia_Hour, $Waconia_Min, $Waconia_Sec) = Now();
   ($Waconia_Year, $Waconia_Month, $Waconia_Day) = Today();

   # The following scaler, PerlTime, is useful for having a single field to
   # characterize time. Note this function expects months to start at zero and
   # years to be relative to 1900.
   $PerlTime = timelocal(0,($Waconia_Min),($Waconia_Hour),$Waconia_Day,($Waconia_Month-1),($Waconia_Year));

   # Create the sql statement for inserting a record of data into the mdb file.

   # If there is a funny 24 in the time stamp, convert it to a more normal 0 to 23 convention...
   # (apparently this never gets used...)
   if ($TheHour == 24) {
      $TheDate = UnixDate( Date::Manip::DateCalc( $TheDate, "+ 1 days" ), "%m/%d/%Y"); 
      $TheHour = 0;
   } 
   
   # If there's no data (i.e. N/A), set it to the database-appropriate NULL value.
   if ($WindDir eq "N/A") {$WindDir = $null};
   if ($WindAvg eq "N/A") {$WindAvg = $null};
   if ($WindMax eq "N/A") {$WindMax = $null};
   if ($TempAvg eq "N/A") {$TempAvg = $null};
   if ($DewPoint eq "N/A") {$DewPoint = $null};
   if ($BPAvg eq "N/A") {$BPAvg = $null};

   $DateTimeStamp = $TheDate . " " . $TheHour . ":" . $TheMin;
   # Format $LiteralDateTimeStamp to a more standard format
   $LiteralDateTimeStamp = UnixDate($ParsedDate, "%Y-%m-%d %H:%M:%S");
   
   # Note that in the VALUES part of the SQL, strings and dates are quoted, numbers are not.
   $sql = "INSERT INTO FifteenMinData (PerlTime, DateTimeStamp, LiteralDateTimeStamp, TimeMDY, TimeHr, TimeMin, StationNumber, StationName, ";
   $sql .= "WindDirection, WindSpeed, WindGust, ";
   $sql .= "TempAvg, DewPoint, Pressure) ";
   
   # Handle different date formats for MySQL vs Access
   if ($database_type eq "access") {
      $sql .= "VALUES ($PerlTime,'$DateTimeStamp','$LiteralDateTimeStamp','$TheDate',$TheHour,$TheMin,$StationNumber,'$TheCity',";
   } elsif ($database_type eq "mysql") {
       # MySQL format (YYYY-MM-DD)
       # Convert from MM/DD/YYYY to YYYY-MM-DD
       my ($month, $day, $year) = split('/', $TheDate);
       
       # Now that we're using %Y in UnixDate, we always get 4-digit years
       $TheDate_mysql = sprintf("%04d-%02d-%02d", $year, $month, $day);
       $DateTimeStamp_mysql = sprintf("%04d-%02d-%02d %02d:%02d:00", $year, $month, $day, $TheHour, $TheMin);
       $sql .= "VALUES ($PerlTime,'$DateTimeStamp_mysql','$LiteralDateTimeStamp','$TheDate_mysql',$TheHour,$TheMin,$StationNumber,'$TheCity',";
    }
   
   $sql .= "$WindDir,$WindAvg,$WindMax,";
   $sql .= "$TempAvg,$DewPoint,$BPAvg)";

   #print "SQL = $sql\n";

   # If all numeric values are reasonable, write the record...
   # Note: one of these raw values may be an "N/A" string. Those cases always evaluate true and do not block the write. 
   if ((($TempAvg >= -20) && ($TempAvg <=  120)) && 
       (($WindAvg >=   0) && ($WindAvg <=  110)) &&
       (($WindMax >=   0) && ($WindMax <=  130)) &&
       ((($BPAvg >= 28.50) && ($BPAvg <= 31.00)) || ($BPAvg == 0)) &&
       (($TheHour >= 0) && ($TheHour <= 24)) &&
       (($TheMin >= 0) && ($TheMin <= 59)) ) {

      # Print the intended write to the database.
      print "$TheDate, $TheHour, $TheMin, $StationNumber, $TheCity, $TempAvg, $DewPoint, $WindStuff, $WindDir, $WindAvg, $WindMax, $BPAvg\n";

      # Execute the sql using the module function
      if ($TelemOK) {
         my ($success, $error) = execute_sql($sql, $log_fh);
         
         if ($success) {            
            # Prepare to add a new row to the googleSheet_data array.
            my ($TheYear, $TheMonth, $TheDay) = Decode_Date_US($TheDate);
            
            # Add row to Google Sheet data using the module function
            # The module will handle DateTime creation and UTC conversion
            add_google_sheet_row(
                $shortNames{$TheCity},  # station
                $TheYear,               # year
                $TheMonth,              # month
                $TheDay,                # day
                $TheHour,               # hour
                $TheMin,                # minute
                cS($TempAvg),           # temp_avg
                cS($DewPoint),          # dew_point
                cS($WindDir),           # wind_dir
                cS($WindAvg),           # wind_avg
                cS($WindMax),           # wind_max
                cS($BPAvg),             # bp_avg_sl
                $log_fh                 # log_file_handle
            );
         }
      }
      
      # Write out the TimeMDY date to a special table that is used to quickly
      # populate the date combo box
      if ($database_type eq "access") {
         $sql = "INSERT INTO DaysGleaned (TimeMDY) VALUES ('$TheDate')";
      } elsif ($database_type eq "mysql") {
         $sql = "INSERT INTO DaysGleaned (TimeMDY) VALUES ('$TheDate_mysql')";
      }

      if ($TelemOK) {
         # For DaysGleaned table, we don't care about duplicate entries
         # Pass quiet=1 to suppress console output
         execute_sql($sql, $log_fh, 1);
      }

   } else { # Here is the corresponding else of the if-values-are-reasonable block.
      print "$TheDate, $TheHour, $TheMin, $StationNumber, $TheCity, $TempAvg, $DewPoint, $WindStuff, $WindDir, $WindAvg, $WindMax, $BPAvg\n";
      print "  Record failed reasonable test\n";
   }
}

sub getpage {
   my $URL = $_[0];

   # The next 9 elements passed in are supplied by the Now array in the main
   # body of this script.
   my @Now = ($_[1],$_[2],$_[3],$_[4],$_[5],$_[6],$_[7],$_[8],$_[9]);

   # Get the page of data. Note the get function from 'LWP::Simple' returns
   # undefined on error, so check for errors as follows....
   $foundPage = 1;
   unless (defined ($content = get $URL)) {
      print $log_fh localtime(time) . " Timestamp = @Now[5,4,3,2,1]\n";
      print $log_fh localtime(time) . " Could not get $URL\n";
      $foundPage = 0;
   }
}

sub dir360 {
   my $dirString = $_[0];
   my $dirAngle;

   if    ($dirString eq "N" ) { $dirAngle = 360; } 
   elsif ($dirString eq "NE") { $dirAngle =  45; } 
   elsif ($dirString eq "E" ) { $dirAngle =  90; } 
   elsif ($dirString eq "SE") { $dirAngle = 135; } 
   elsif ($dirString eq "S" ) { $dirAngle = 180; } 
   elsif ($dirString eq "SW") { $dirAngle = 225; } 
   elsif ($dirString eq "W" ) { $dirAngle = 270; } 
   elsif ($dirString eq "NW") { $dirAngle = 315; } 
   else                       { $dirAngle = "N/A"; }
   
   return $dirAngle;
}

sub parseandwrite {
   $TheCity = $_[0];
   
   # This offset is used to handle city names that have two words, for example "THE DALLES"
   my $offset = $_[1];

   $StationNumber = $_[2];

   # Split the page into lines
   @thelines = split (/\n/, $content);
   $nlines = @thelines;

   # Initialize the sensor values.
   $WindDir = "N/A";
   $WindAvg = "N/A";
   $WindMax = "N/A";
   $TempAvg = "N/A";
   $DewPoint = "N/A";
   $BPAvg = "N/A";

   # Parse it
   foreach (@thelines) {

      if (/PDT/ or /PST/) {

         # Split the line into words.
         @thewords = split(" ", $_);

         # Set this timezone parameter so the call to ParseDate works.
         # 
         # Note that this does NOT override the TZ value that is set in 
         # C:\Perl\site\lib\Date\manip.pm
         # I only set it here in case it is removed in manip.pm, then I correct
         # for the 2 hour difference down below where I shift back to 
         # standard time.
         #
         # Changes for MN (from PST8PDT)
         # PST8PDT, Pacific time. MST7MDT, Mountain time. CST6CDT, Central time. EST5EDT, Eastern time
         #$TZ = "PST8PDT";
         $TZ = "CST6CDT";

         # Substitute, so can get that silly ":" in there. First grab the
         # first 4 characters. Note there is a space at the beginning of the
         # line so must go 1 to 5 not 0 to 4

         $thetime = substr($_,1,5);
         #print " thetime = $thetime \n";
	 
         # If 1000, 10:00, do a special form of the substitution.
         if ($thetime =~ /000/) { 
            $_ =~ s/000/0:00/;
         } else {
            $_ =~ s/00/:00/;
         }
         #print " Raw stuff = $_ \n";

         # Parse the date to get around the problem of their am/pm format.
         #print "TZ = $ENV{'TZ'}\n";
         $ParsedDate = ParseDate($_);

         # Subtract an hour to get back to standard time.
         # And subtract two hours to get back to Pacific time because DateCalc
         # tries to present the result in the local time zone.
         if ($thewords[2] eq "PDT") {
            $PSTDate = DateCalc($ParsedDate,"- 3hours",\$err);
         } else {
            $PSTDate = DateCalc($ParsedDate,"- 2hours",\$err);
         }
         #print "PSTDate = $PSTDate \n";

         # Use this formatting function to return a date string.
         $TheDate = UnixDate($PSTDate, "%m/%d/%Y");
 
         # Finally get the hour and min with a simple substring call
         $TheHour = substr($PSTDate,8,2) + 0;
         $TheMin = substr($PSTDate,11,2) + 0;
         #print " $TheDate, $TheHour, $TheMin \n";
      }

      # Look for the first occurrence of the city where the NOT AVBL string is
      # absent. Not that the LAST statement below will cause a break out of
      # the for loop; that is the mechanism I use to prevent the city from
      # being parsed twice if it shows more than once on the page.

      # Also if you're worried about getting the wrong date associated with a
      # city match farther down on the page, don't. If a city match is made in
      # a secondary report on the page, the date match will have been updated
      # also; it keeps trying to update the date for each line in the for loop.
      # So don't be afraid to use urls that have multiple reports on the page.

      if ((/$TheCity/) && !(/NOT AVBL/)) {
         # The sky cover is two words only for "LGT RAIN"
         if (/LGT RAIN/ || /LGT SNOW/) {$offset++}
         @thewords = split(" ", $_);

         # If there's a letter at the end of the pressure string, remove it.
         # Otherwise just take the whole thing.
         $PressureStuff = $thewords[6 + $offset];
         $PressureStuff =~ /[a-zA-Z]/g;
         
         if (defined ($FirstLetter = pos($PressureStuff))) {
            $BPAvg = substr($PressureStuff, 0, $FirstLetter - 1);
         } else {
            $BPAvg = $PressureStuff;
         }
	
         # Not using this anymore, but left here as an example... The
         # following use of substr returns all but the last character in the
         # target string (If the third parameter is negative, it leaves that
         # many off the end of the target string). Target, offset, length. 
         #$BPAvg = substr($thewords[6 + $offset],0,-1);

         $TempAvg = $thewords[2 + $offset];
         $DewPoint = $thewords[3 + $offset];
         $WindStuff = $thewords[5 + $offset];

         # Interpret the windstuff string.

         # Check for CALM
         if ( ($WindStuff =~ /CALM/g) || ($WindStuff =~ /MISG/g) ) { 
            $WindAvg = 0;
            $WindMax = 0;
            $WindDir = "N/A";
            
         } else {
            # Split up the windstring into 4 parts.
            ($WindDir_string,$WindAvg,$Gust,$WindMax) = $WindStuff =~ /(\D+)(\d+)(\D+)?(\d+)?/;

            # Translate the winddirection string into a number.
            $WindDir = &dir360($WindDir_string);

            # If can't find the G (for Gust) in the wind string, just set the
            # max to the avg value
            if (!defined($Gust)) { 
               $WindMax = $WindAvg;
            }
         }

         # The following call, to write out to the database, only gets run if
         # the city match above was successful. 
         WriteToMDB;

         # Use this "last" statement to exit the for loop. Because there are
         # multiple line with these city strings. This way we only use the
         # first find with data.
         last;
      }

   }

}


# \\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\
# Main Program
# \\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\

# Open the log file using the module function
my $log_file_path = 'C:\Users\Jim\Documents\webcontent\waconia\wgl_perl_noaa_log.txt';
my ($log_success, $fh, $log_error) = open_log_file($log_file_path, 'NOAA Weather Data Collection Log');
$log_fh = $fh; # Assign to our variable

if (!$log_success) {
    die "Failed to open log file: $log_error";
}

# Write a timestamp to the log file each time the script is run.
print $log_fh localtime(time) . " from wgl_perl_noaa.pl " . "\n";

# Initialize the Google-sheet array that will add a row of data for each successful SQL write.
clear_google_sheet_data();

%shortNames = ('NORTH BEND' => 'NBend', 'MOSES LAKE'  => 'MLake', 
               'ELLENSBURG' => 'EBurg', 'WALLA WALLA' => 'Walla',
               'HERMISTON'  => 'Hermi', 'PASCO'       => 'Pasco',
               'THE DALLES' => 'Dalle', 'PORTLAND'    => 'PLand');

# Make a database connection to the Access (mdb) file or MySQL database using the module
$database_type = "mysql"; # "mysql" or "access"
($TelemOK, $cnTelem, my $error) = connect_database($database_type, $log_fh);

# Get NULL value from the module
$null = get_null($database_type);

if (!$TelemOK) {
   print $log_fh localtime(time) . " Error connecting to $database_type database\n";
   print $log_fh "Error: $error\n";
   warn "Error connecting to $database_type database: $error\n";
} else {
   print "Connected to $database_type database\n\n";
}

# Get the data and send it to the database.
my @Now = localtime(time);

#getpage("http://iwin.nws.noaa.gov/iwin/wa/hourly.html", @Now);
#getpage("http://www.weather.gov/view/prodsByState.php?state=WA&prodtype=hourly", @Now);
getpage("http://forecast.weather.gov/product.php?site=CRH&product=RWR&issuedby=WA", @Now);

if ($foundPage) {
   parseandwrite("PORTLAND",    1, 51);
   parseandwrite("THE DALLES",  2, 52);
   parseandwrite("PASCO",       0, 53);
   parseandwrite("HERMISTON",   1, 54);
   parseandwrite("WALLA WALLA", 1, 55);
   parseandwrite("ELLENSBURG",  0, 56);
   parseandwrite("MOSES LAKE",  1, 57);
}

# getpage("http://www.wrh.noaa.gov/pendleton/data/text/pdxhwrsch.html", @Now);
# if ($foundPage){
#    parseandwrite("BOARDMAN",    1, 58);
#    parseandwrite("IRRIGON",     1, 60);
#    parseandwrite("UMATILLA",    1, 61);
#    parseandwrite("ROOSEVELT",   0, 62);
#    parseandwrite("CELILO",      1, 63);
#    parseandwrite("RUFUS",       1, 64);
# }

#getpage("http://iwin.nws.noaa.gov/iwin/or/hourly.html", @Now);
#getpage("http://www.weather.gov/view/prodsByState.php?state=OR&prodtype=hourly", @Now);
getpage("http://forecast.weather.gov/product.php?site=CRH&product=RWR&issuedby=OR", @Now);

if ($foundPage) {
   parseandwrite("NORTH BEND",  1, 65);
}

# The following two lines of code are useful for testing the regular expression.
# It's just a test page on a local server.

#getpage("http://waconia.pnl.gov/TestWaconiaParse.htm", @Now);
#parseandwrite("RUFUS2",       1, 64);

# Close the database connection using the module
if ($TelemOK) {
   close_database();
}

# Send the array of successful writes to the Google sheet using the module
my $row_count = get_google_sheet_row_count();
print "row_count = $row_count\n";
if ($row_count > 0) {
   send_to_google_sheet('noaa-test', 
                      "C:\\Users\\Jim\\Documents\\webcontent\\waconia\\wgl_perl_noaa_data.json", 
                      "C:\\Users\\Jim\\Documents\\webcontent\\waconia\\wgl_perl_postToSheet.py",
                      $log_fh);
}

# Close the log file
close($log_fh);