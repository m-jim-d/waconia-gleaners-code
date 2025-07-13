# Weather Gleaner Scripts

A collection of Python and Perl scripts for collecting weather data from various online sources and storing it in a database for visualization and analysis.

## Overview

These scripts collect weather data (temperature, wind speed/direction, barometric pressure) from multiple sources and store it in a database. The data is then used by the Waconia weather charting application to generate visualizations and analysis.

## Data Sources

The scripts collect data from four main sources:

1. **Hanford Meteorological Station (HMS)** - Weather data from the Hanford site in Washington state
2. **NOAA** - Weather data from Washington and Oregon, particularly in the Columbia River basin
3. **Aviation Weather (AW)** - METAR data from airports, primarily in Minnesota
4. **Mesonet/Synoptic Data** - JSON-based weather data from the Mesonet API

## Script Organization

The scripts follow a naming convention with `wgl_` prefix (Weather Gleaner):

### Perl Scripts
- `wgl_perl_module.pm` - Shared Perl module with common functions
- `wgl_perl_hanford.pl` - Collects data from the Hanford Meteorological Station
- `wgl_perl_noaa.pl` - Collects data from NOAA weather pages
- `wgl_perl_hanford_URLfetch.py` - Python helper for the Hanford Perl script
- `wgl_perl_postToSheet.py` - Python helper for posting data

### Python Scripts
- `wgl_python_module.py` - Shared Python module with common functions
- `wgl_python_aw.py` - Collects METAR data from Aviation Weather XML feeds
- `wgl_python_meso.py` - Collects data from the Mesonet JSON API

## Database Structure

The scripts store data in a database with tables including:
- `fifteenmindata` - Main weather data with timestamps, station information, and measurements
- `daysgleaned` - Record of data collection activity

## Batch Files

- `wgl_runAll.bat` - Runs all scripts in sequence
- `wgl_runAll_log.txt` - Log file (console output) from one run of all scripts

The batch files are scheduled to run every 5-15 minutes to collect current weather data.

In Windows scheduled tasks, the "actions" tab fields have the following values:

- **Script:** `C:\Users\[your name]\Documents\webcontent\waconia\wgl_runAll.bat`
- **Arguments:** `\> C:\Users\[your name]\Documents\webcontent\waconia\wgl_runAll_log.txt 2>&1`

## Usage

The scripts are typically run via scheduled tasks every 5-15 minutes to collect current weather data. Each script:

1. Connects to its respective data source
2. Parses the retrieved data
3. Stores the processed data in the database
4. Handles errors and logging

## Requirements

- Python 3.x
- Perl 5.x
- Database access (originally MS Access, with MySQL support)
- Internet connection to access weather data sources

## License

MIT License

## Author

Jim Miller

---

*This repository contains the data collection components of the Waconia weather charting system. For more information about the complete system, visit the [Waconia website](https://waconia.timetocode.org).*