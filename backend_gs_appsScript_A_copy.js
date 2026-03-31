/* 
Google Apps Script
Weather Data (receiver for Python gleaners)

Pick "Manage deployments" from the "Deploy" select element, upper right.
The "Web app" url does not give general access to your account. It only allows the web user to submit parameters
to the doGet function below.

To deploy an update to this script (without changing the URL for the app) do the following:
save it (ctrl-s) / Deploy / Manage deployments / click the edit icon / select new version / click Deploy in the pop-up
*/

// m_ indicates a module level global.

// Create a new property service to maintain variables across instances.
//var m_SCRIPT_PROP = PropertiesService.getScriptProperties();

// Similar to the one above, but associated with the document.
var m_savedValues = PropertiesService.getDocumentProperties();

var m_doc = SpreadsheetApp.getActiveSpreadsheet();

function doGet( e) {
    // This is only for testing, doPost is used for receiving data.
    let message = {
      'result':'from doGet',
      'e': e
    }
    return ContentService.createTextOutput( JSON.stringify( message) ).setMimeType( ContentService.MimeType.JSON);
}

function doPost(e) {
    //var wholeThing = JSON.stringify(e);
    var jsonData = JSON.parse( e.postData.contents);

    return addWeatherRows( jsonData['sheetName'], jsonData['weatherData'], false);
}

/*
This test function doesn't require publishing and/or calling from a web page. It presents
the results returned from addWeatherRows (called with debug parameter set to true).
Use the menu (run/debug) if you want to run this with break points.
Click the "Execution log" button to toggle the display of the log output (from manual runs, not from web requests).
You might have to comment out the locking stuff during debugging. Generally not.
*/
function testDoPost() {
    Logger.log("log output from testDoGet...");

    var rowsOfWeather = [[1,1,1,1],[2,2,2,2],[3,3,3,3]];
    return addWeatherRows( "test3", rowsOfWeather, true);
}

function addWeatherRows( sheetName, weatherData, debug) {
    // Get the named sheet.
    var sheet = m_doc.getSheetByName( sheetName);
    
    // A script lock, one that locks out all but one invocation. Forces one-at-a-time (wait your turn) operation.
    // http://googleappsdeveloper.blogspot.co.uk/2011/10/concurrency-and-google-apps-script.html
    var lock = LockService.getScriptLock();
    
    // Attempt to acquire the lock, timing out with an exception after the specified number of milliseconds.
    lock.waitLock(30000); // 30 seconds
    
    try {
        // Try inserting an array of the row arrays...
        
        let nRows = weatherData.length;
        let nCols = weatherData[0].length;
        
        // Add blank rows after the header
        sheet.insertRows(2, nRows);
        
        // Put the new data into those blank rows.
        sheet.getRange(2, 1, nRows, nCols).setValues( weatherData);
        
        return ContentService.createTextOutput(JSON.stringify( {'result':'ok'} )).setMimeType(ContentService.MimeType.JSON);
        
    } catch (e) {
        var errorSummary = {"result":"error2", "error": e};
        if (debug) {
            return errorSummary;    
        } else {  
            return ContentService.createTextOutput(JSON.stringify( errorSummary)).setMimeType(ContentService.MimeType.JSON);
        }
        
    } finally {
        lock.releaseLock();
    }
}

function sortAndTrim( sheetName, ageLimit_days=60, lastColumn=8) {
    // Sort the sheet by timestamp (column 2), descending, then station name (column 1), ascending.
    let sheet = m_doc.getSheetByName( sheetName);
    let lastRow = sheet.getLastRow();
    
    // Considering the header row, the number of rows and colums in the range.
    let nRows = lastRow-1;
    let nColumns = lastColumn; // number of weather-data columns
    let range = sheet.getRange(2, 1, nRows, nColumns);

    range.sort([ {column:2, ascending:false},
                 {column:1, ascending:true } ]);

    Logger.log("sort finished: on the '" + sheetName + "' sheet in the '" + m_doc.getName() + "' document");

    let msecPerDay = 1000 * 60 * 60 * 24;

    let dateMostRecent = sheet.getRange('B2').getValue();
    let dateOldest = sheet.getRange('B'+lastRow).getValue();

    // For now, this try-catch will inhibit failed-execution entries from getting in the triggers log.
    try {
        // age relative to the most recent data
        let ageOldest_days = (dateMostRecent.getTime() - dateOldest.getTime()) / msecPerDay;
        Logger.log("ageOldest_days = " + ageOldest_days);

        let recordsPerDay = (lastRow-1) / ageOldest_days;
        Logger.log("recordsPerDay = " + recordsPerDay);

        // trim off 1.5 times what comes in per day on average
        let recordsToDelete = Math.floor( recordsPerDay * 1.5);

        if (ageOldest_days > ageLimit_days) {
            sheet.deleteRows( lastRow-(recordsToDelete-1), recordsToDelete);
            Logger.log("old records deleted = " + recordsToDelete);
        } else {
            Logger.log("old records deleted = 0");
        }
        Logger.log("-------------------");      

    } catch(err) {
        Logger.log("error message = " + err);
        Logger.log("dateMostRecent = " + dateMostRecent);
        Logger.log("dateOldest = " + dateOldest);        
    }
}

function sortAndTrim_clean( sheetName="target", ageLimit_days=60, lastColumn=8, useMidNight=false) {
    let sheet = m_doc.getSheetByName( sheetName);
    
    let lastRow = sheet.getLastRow();
    //Logger.log("lastRow = " + lastRow);
    
    // Considering the header row, the number of rows and columns in the range.
    let nRows = lastRow-1;
    let nColumns = lastColumn; // number of weather-data columns
    let range = sheet.getRange(2, 1, nRows, nColumns);

    // Sort the sheet by timestamp (column 2), descending, then station name (column 1), ascending.
    range.sort([ {column:2, ascending:false},
                 {column:1, ascending:true } ]);
    Logger.log("sort finished: on the '" + sheetName + "' sheet in the '" + m_doc.getName() + "' document");

    let msecPerDay = 1000 * 60 * 60 * 24;

    Logger.log("getting values, please wait");
    let values = sheet.getRange(2, 2, nRows, 1).getValues();
    Logger.log("rows in values = " + values.length);

    let dateMostRecent = sheet.getRange('B2').getValue();
    Logger.log("dateMostRecent = " + dateMostRecent);
    let startDate;
    if (useMidNight) {
        // The beginning of this date (midnight):
        startDate = new Date(dateMostRecent.getFullYear(), dateMostRecent.getMonth(), dateMostRecent.getDate(), 0,0,0);
    } else {
        startDate = dateMostRecent;
    } 
    Logger.log("start date = " + startDate);

    let n_oldRecords = 0;
    for (var i = 0; i < values.length; i++) { 
        // Calculate age relative to startDate.
        // Consider the case where ageLimit_days is 2.
        //    If useMidNight==true,  it will delete anything older than the prior 2 days.
        //    If useMidNight==false, it will delete anything older than 2 * 24 hours before the most recent record.
        let age_days = (startDate.getTime() - values[i][0].getTime()) / msecPerDay;
        //Logger.log("age_days = " + age_days);
        if (age_days > ageLimit_days) {
            n_oldRecords++;
        }
    }

    if (n_oldRecords > 0) {
        sheet.deleteRows( lastRow-(n_oldRecords-1), n_oldRecords);
        Logger.log("old records deleted = " + n_oldRecords);
    } else {
        Logger.log("old records deleted = 0");
    }

    Logger.log("---finished---");
}

function checkForOldRecords() {
    let utilitySheet = m_doc.getSheetByName('util');
    let countCell = utilitySheet.getRange('B2');
    //sortAndTrim_clean('test2', 33);
    sortAndTrim_clean('meso', 29);
    sortAndTrim_clean('aw', 49);
    countCell.setValue( countCell.getValue() + 1);
}

// Update the formatted time-string column. Call this from the "Run" menu.
function formatTimeStamps() {
    // Reference a sheet by index.
    var sheet = m_doc.getSheets()[0];
    
    var lastRow = sheet.getLastRow();
    var nRows = lastRow - 1; // the header, -1
    var range = sheet.getRange(2, 2, nRows, 1);
    
    range.setNumberFormat("mmm d, YYY ddd hh:mm:ss");
    range.setBackground('white');
}

function sheetCellCount( sheetName) {
    let sheet = m_doc.getSheetByName( sheetName);
    let n_rows = sheet.getMaxRows();
    let n_cols = sheet.getMaxColumns();
    let n_cells = n_rows * n_cols;
    return n_cells;
}

function updateCellCount() {
    // This triggers a recalculation of the cell counts by erasing and then re-writing 
    // the sheet-name cells that feed the cell-count cells.

    let utilitySheet = m_doc.getSheetByName('util');
    let firstSheetName = utilitySheet.getRange('A4').getValue();

    let sheetNameRange = utilitySheet.getRange('A4:A10');
    let cellCountRange = utilitySheet.getRange('B4:D11');

    Logger.log("A4=" + firstSheetName);

    if (firstSheetName != "") {
        let values = utilitySheet.getRange('A4:A10').getValues();
        m_savedValues.setProperty("sheetNames", JSON.stringify( values));
        sheetNameRange.clear();
        cellCountRange.setFontColor('white'); // try to hide the warnings
        // Now, run this function again. This will cause the else block to execute, repopulating the sheet-names
        // and triggering the update.
        updateCellCount(); 

    } else {
        let oldValues = JSON.parse( m_savedValues.getProperty("sheetNames"));
        sheetNameRange.setValues( oldValues);
        cellCountRange.setFontColor('black');
    }
}

/*
// Initialize
function setup() {  
    // Get the document
    var doc = SpreadsheetApp.getActiveSpreadsheet();
    
    // Save the spreadsheet's document ID for later 
    m_SCRIPT_PROP.setProperty("key", doc.getId());
    
    // Reference a sheet by index.
    var sheet = doc.getSheets()[3];
    
    // An array of labels
    var row = [["timestamp","time string", "event"]];
    
    // Initialize the header row
    let lastColumn = 8;
    sheet.getRange(1, 1, 1, lastColumn).setValues(row);
}
*/
