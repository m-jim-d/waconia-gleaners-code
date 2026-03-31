/* 
Google Apps Script
Weather Data (receiver for Perl gleaners)
This uses a library, pad (python add data) from the sister sheets document, weather-python.

Pick "Manage deployments" from the "Deploy" select element, upper right.
The "Web app" url does not give general access to your account. It only allows the web user to submit parameters
to the doGet function below.

To deploy an update to this script (without changing the URL for the app) do the following:
save it (ctrl-s) / Deploy / Manage deployments / click the edit icon / select new version / click Deploy in the pop-up
*/

// m_ indicates a module level global.

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

    return pad.addWeatherRows( jsonData['sheetName'], jsonData['weatherData'], false);
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
    return pad.addWeatherRows( "test3", rowsOfWeather, true);
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
    return pad.sheetCellCount( sheetName);
}

function updateCellCount() {
    pad.updateCellCount();
}

function probeProperties() {
    //pad.m_savedValues.setProperty("values","testing...");
    // This demonstrates that this will get the values stored with the perl document even
    // though the library is in the python document.
    Logger.log( "perl = " + pad.m_savedValues.getProperty("values") );
}

function checkForOldRecords() {
    let utilitySheet = m_doc.getSheetByName('util');
    let countCell = utilitySheet.getRange('B2');
    //pad.sortAndTrim_clean('test300', 33);
    pad.sortAndTrim_clean('hanford', 39); // sortAndTrim_clean or sortAndTrim
    pad.sortAndTrim_clean('noaa', 199);
    countCell.setValue( countCell.getValue() + 1);
}
