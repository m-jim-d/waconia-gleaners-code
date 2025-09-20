# wgl_perl_module.pm
# Jim Miller, July 24, 2025

package wgl_perl_module;

use strict;
use warnings;
use Exporter qw(import);
use DBI;
use Win32::ODBC;

our @EXPORT_OK = qw(connect_database get_null execute_sql close_database 
                    add_google_sheet_row clear_google_sheet_data 
                    get_google_sheet_row_count send_to_google_sheet open_log_file);

# Module-level globals (not visible outside the module)
my $database_handle;
my $connection_ok = 0;
my $db_type;
my $log_file;
my @google_sheet_data = ();

# Connect to database and store the handle internally
sub connect_database {
    my ($type, $log_file_handle) = @_;
    $db_type = $type;
    $log_file = $log_file_handle;
    my $error = "";
    
    if ($type eq "access") {
        my $dsn = "DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};DBQ=C:/Users/Jim/Documents/webcontent/waconia/data/telem.mdb;UID=admin";
        $database_handle = new Win32::ODBC($dsn);
        if (!$database_handle) {
            $error = Win32::ODBC::Error();
            $connection_ok = 0;
            return ($connection_ok, $database_handle, $error);
        }
        $connection_ok = 1;
    } elsif ($type eq "mysql") {
        my $dsn = "DBI:ODBC:MySQL_telem_for_Perl";
        my $username = "Jim";
        my $password = "irKmmZXgwkFNzy3boKZd";
        
        eval {
            $database_handle = DBI->connect($dsn, $username, $password, {
                PrintError => 0,
                RaiseError => 1,
                AutoCommit => 1
            });
        };
        if ($@) {
            print "Error connecting to MySQL database: $@\n";
            $error = $@;
            $connection_ok = 0;
            return ($connection_ok, $database_handle, $error);
        }
        $connection_ok = 1;
    } else {
        $error = "Unknown database type: $type";
        $connection_ok = 0;
        return ($connection_ok, $database_handle, $error);
    }
    
    return ($connection_ok, $database_handle, $error);
}

# Get the database handle
sub get_handle {
    return $database_handle;
}

sub execute_sql {
    my ($sql, $log_file_handle, $quiet) = @_;
    
    # Use the passed filehandle if provided, otherwise use module-level one
    my $log_fh = $log_file_handle || $log_file;

    return (0, "No database connection") unless $connection_ok;    

    if ($db_type eq "access") {
        if ($database_handle->Sql($sql)) {
            unless ($quiet) {
                print "  Waconia: SQL failed (probably the record already exists).\n";
            }
            # If not the -1605 error message (duplicate records) then log it.
            if ( ! ($database_handle->Error() =~ /-1605/)) {
                print $log_fh localtime(time) . " Waconia SQL failure, Error: " . $database_handle->Error() . " SQL=$sql\n";
                return (0, $database_handle->Error());
            } else {
                return (0, "duplicate entry error");
            }
        } else {
                print "SQL write to Access succeeded.\n";
            return (1, "");
        }

    } elsif ($db_type eq "mysql") {
        # MySQL execution
        my $success = 1;
        my $error_msg = "";

        eval {
            $database_handle->do($sql);
            # Success handling
                print "SQL write to MySQL succeeded.\n";
        };
        if ($@) {
            # Error handling
            $success = 0;
            $error_msg = $@;
            unless ($quiet) {
                print "SQL write to MySQL failed (probably the record already exists): $@\n";
            }
            # Don't log duplicate entry errors
            if ( ! ($@ =~ /Duplicate entry/)) {
                print $log_fh localtime(time) . " MySQL SQL failure, Error: $@ SQL=$sql\n";
            }
        }

        return ($success, $error_msg);

    } else {
        if ($log_fh) {
            print $log_fh localtime(time) . " Error: Unknown database type: $db_type\n";
        }
        return (0, "Unknown database type: $db_type");
    }
}

# Get appropriate NULL value for database type
sub get_null {
    # For other database types, might someday need a different NULL value.
    # Example: "Null" for Access and "NULL" for MySQL.
    # return ($db_type eq "mysql") ? "NULL" : "Null";
    return "NULL";
}

# Close database connection
sub close_database {
    return unless $connection_ok;
    
    if ($db_type eq "access") {
        $database_handle->Close();
    } elsif ($db_type eq "mysql") {
        $database_handle->disconnect();
    }
    $connection_ok = 0;
    print "Database connection closed.\n";
}


# Add a row to the Google Sheet data array
sub add_google_sheet_row {
    my ($station, $year, $month, $day, $hour, $min, 
        $temp_avg, $dew_point, $wind_dir, $wind_avg, $wind_max, $bp_avg_sl, $log_file_handle) = @_;
    
    my $log_fh = $log_file_handle || $log_file;
    
    # Create DateTime object
    my $pt_time = DateTime->new(
        year => $year,
        month => $month,
        day => $day,
        hour => $hour,
        minute => $min,
        second => 0,
    );
    
    my $pt_string = $pt_time->strftime('%m/%d/%Y %H:%M:%S');
    print "PST= $pt_string, ";
    
    # Convert to UTC (adding 8 hours)
    my $utc_time = $pt_time->clone->add(hours => 8);
    my $utc_string = $utc_time->strftime('%m/%d/%Y %H:%M:%S');
    print "UTC= $utc_string\n\n";
    
    # Create and add the new row
    my @new_row = ($station, $utc_string, $temp_avg, $dew_point, $wind_dir, $wind_avg, $wind_max, $bp_avg_sl);
    push @google_sheet_data, \@new_row;
    
    return 1;
}

# Clear the Google Sheet data array
sub clear_google_sheet_data {
    @google_sheet_data = ();
    return 1;
}

# Get the count of rows in the Google Sheet data array
sub get_google_sheet_row_count {
    return scalar @google_sheet_data;
}

# Send the data to Google Sheets
sub send_to_google_sheet {
    my ($sheet_name, $json_file_path, $python_script_path, $log_file_handle) = @_;
    
    my $log_fh = $log_file_handle || $log_file;
    my $row_count = scalar @google_sheet_data;
    
    if ($row_count <= 0) {
        if ($log_fh) {
            print $log_fh localtime(time) . " No data to send to Google Sheet\n";
        }
        return (0, "No data to send");
    }
    
    eval {
        require JSON;
        JSON->import('encode_json');
        
        # Create JSON data structure
        my $json_data = {
            'sheetName' => $sheet_name,
            'weatherData' => \@google_sheet_data
        };
        
        # Convert to JSON string
        my $json_string = encode_json($json_data);
        
        # Write to file
        open(my $fh, '>', $json_file_path) or die "Can't open file: $!";
        print $fh $json_string;
        close $fh;
        
        # Execute Python script
        my $cmd = "$python_script_path $json_file_path";
        system($cmd);
    };
    
    if ($@) {
        if ($log_fh) {
            print $log_fh localtime(time) . " Error sending data to Google Sheet: $@\n";
        }
        return (0, $@);
    }
    
    if ($log_fh) {
        print $log_fh localtime(time) . " Successfully sent $row_count rows to Google Sheet\n";
    }
    
    # Clear the data after sending
    @google_sheet_data = ();
    
    return (1, "");
}

# Open a log file, creating it with header if it doesn't exist
sub open_log_file {
    my ($log_file_path, $log_title) = @_;
    
    # Default title if not provided
    $log_title ||= 'Waconia Data Collection Log';
    
    # Check if file exists
    my $file_exists = -e $log_file_path;
    
    # Open filehandle
    my $log_fh;
    open($log_fh, '>>:encoding(UTF-8)', $log_file_path) or do {
        my @now = localtime(time);
        print "Timestamp = @now[5,4,3,2,1]\n";
        print "Could not open or create log file: $log_file_path\n";
        return (0, undef, "Error opening log file: $!");
    };
    
    # If this is a new file, write a header
    if (!$file_exists) {
        my $timestamp = localtime(time);
        print $log_fh "# $log_title\n";
        print $log_fh "# Created: $timestamp\n";
        print $log_fh "# This file contains timestamps and events from the data collection process\n";
        print $log_fh "# Format: [Timestamp] [Source] [Event Description]\n";
        print $log_fh "#" . "-" x 80 . "\n\n";
        print "Created new log file with header at $log_file_path\n";
    }
    
    # Write initial timestamp
    print localtime(time) . " Log file opened\n";
    
    return (1, $log_fh, "");
}

1;  # Required for all Perl modules