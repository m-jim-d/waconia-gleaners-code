# Weather Gleaner Scripts

A collection of Python and Perl scripts for collecting weather data from various online sources and storing it in a database for visualization and analysis.

## Overview

These scripts collect weather data (temperature, wind speed/direction, barometric pressure) from multiple sources and store it in a database. The data is then used by the Waconia weather charting application to generate visualizations and analysis.

## Related Repositories

- **Client Web Site:** [https://github.com/m-jim-d/waconia](https://github.com/m-jim-d/waconia) - The weather charting client web application that visualizes the collected weather data

## Data Sources

The scripts collect data from four main sources:

1. **Hanford Meteorological Station (HMS)** - Weather data from the Hanford site in Washington state
2. **NOAA** - Weather data from Washington and Oregon, particularly in the Columbia River basin
3. **Aviation Weather (AW)** - METAR data from airports, primarily in Minnesota
4. **Mesonet/Synoptic Data** - JSON-based weather data from the Mesonet API

## Backend Architecture

The system supports multiple database backends for data storage and synchronization:

### Primary Database
- **MySQL** - Primary local database for weather data storage
- **Tables:** `fifteenmindata` (main weather data), `daysgleaned` (collection activity logs)

### Cloudflare D1 Backend
- **Cloudflare D1** - Serverless SQLite database for cloud storage and web application access
- **Synchronization:** Data is automatically synced from MySQL to Cloudflare D1
- **Benefits:** Enables fast web application access, reduces server load, provides data redundancy

### Google Sheets Backend
- **Google Sheets** - Cloud-based spreadsheet for data backup and analysis
- **Integration:** Provides accessible data view and additional backup layer
- **Features:** Supports data visualization, sharing, and collaborative analysis
- **Synchronization:** Data flows from MySQL → Cloudflare D1 → Google Sheets

### Backend Scripts

#### Google Apps Script Integration
- `backend_gs_appsScript_B.js` - Google Apps Script that runs on Google Sheets to handle incoming data requests and manage sheet operations
- `backend_gs_appsScript_B_copy.js` - Backup copy of the Google Apps Script for version control

#### Data Synchronization Scripts
- `wgl_perl_postToSheetAndD1.py` - Python script that posts collected weather data to both Google Sheets and Cloudflare D1 simultaneously
- `wgl_sync_d1_to_sheet.py` - Python script that synchronizes data from Cloudflare D1 to Google Sheets for backup and analysis
- `wgl_perl_postToSheet.py` - Legacy Python helper for posting data to Google Sheets (deprecated in favor of dual posting script)

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
3. Stores the processed data in the primary MySQL database
4. Synchronizes data to Cloudflare D1 for web application access
5. Handles errors and logging

### Data Flow
1. **Collection:** Weather data is collected from various sources and stored in MySQL
2. **Synchronization:** New data is automatically synced to Cloudflare D1
3. **Web Access:** Web applications read from Cloudflare D1 for fast performance
4. **Backup:** Google Sheets integration provides additional data backup

## Requirements

- Python 3.x
- Perl 5.x
- Database access (originally MS Access, with MySQL support)
- Internet connection to access weather data sources
- Cloudflare account (for D1 backend)
- Google account (for Sheets integration)
- Required Python packages:
  - `mysql-connector-python` or similar for MySQL access
  - `requests` for HTTP requests
  - `gspread` for Google Sheets integration
  - Cloudflare D1 SDK or API access

## License

MIT License

## Author

Jim Miller

---

*This repository contains the data collection components of the Waconia weather charting system. For more information about the complete system, visit the [Waconia website](https://waconia.timetocode.org).*