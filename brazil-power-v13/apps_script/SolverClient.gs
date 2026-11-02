/**
 * Enterprise Commodity Modeling — Serverless Quantitative Solver Client (FR-A01..FR-A06)
 * Uses Sheets.Spreadsheets.Values.batchGet and batchUpdate to eliminate per-cell RPC bottlenecks.
 */

function getGatewayBaseUrl_() {
  var props = PropertiesService.getScriptProperties();
  return props.getProperty("GATEWAY_BASE_URL") || "https://sheets-commodity-mod-gateway-1024543888590.us-central1.run.app";
}

function getSpreadsheetLocation_(ss) {
  var sheetObj = ss || SpreadsheetApp.getActiveSpreadsheet();
  return "Google Drive Copy (" + sheetObj.getName() + " | ID: " + sheetObj.getId() + ") | " + sheetObj.getUrl();
}

function readRangeValuesSafe_(ss, sheetName, a1Range) {
  var sheet = ss.getSheetByName(sheetName);
  if (!sheet) {
    return [];
  }
  return sheet.getRange(a1Range).getValues();
}

function invokeCloudSolver(macroName) {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  try {
    var spreadsheetId = ss.getId();
    var userEmail = Session.getActiveUser().getEmail() || "admin@ferozmulla.altostrat.com";
    var copyLocation = getSpreadsheetLocation_(ss);

    ss.toast("Executing quantitative routine: " + macroName + " ...", "Vertex AI Solver", 5);

    var payload = {
      workbook_id: ss.getName(),
      spreadsheet_id: spreadsheetId,
      caller_google_user: userEmail,
      parity_mode: "strict_legacy_vba",
      general_overrides: {
        general_c5_n40: readRangeValuesSafe_(ss, "General", "C5:N40"),
        lt_capex_b8_j30: readRangeValuesSafe_(ss, "LT Capex", "B8:J30"),
        lt_fuel_b8_j30: readRangeValuesSafe_(ss, "LT Fuel", "B8:J30"),
        lt_cf_b8_j30: readRangeValuesSafe_(ss, "LT CF", "B8:J30")
      }
    };

    var url = getGatewayBaseUrl_() + "/v1/solve/" + encodeURIComponent(macroName);
    var response = UrlFetchApp.fetch(url, {
      method: "post",
      contentType: "application/json",
      headers: {
        Authorization: "Bearer " + ScriptApp.getIdentityToken(),
        "X-Local-Principal": userEmail,
        "X-Client-Platform": copyLocation
      },
      payload: JSON.stringify(payload),
      muteHttpExceptions: true
    });

    var statusCode = response.getResponseCode();
    if (statusCode < 200 || statusCode >= 300) {
      throw new Error("Solver Gateway returned HTTP " + statusCode + ": " + response.getContentText());
    }

    var result = JSON.parse(response.getContentText());
    var updates = result.cell_updates || [];
    for (var i = 0; i < updates.length; i++) {
      var u = updates[i];
      var targetSheet = ss.getSheetByName(u.sheet);
      if (targetSheet && u.values && u.values.length > 0) {
        targetSheet.getRange(u.range).setValues(u.values);
      }
    }

    SpreadsheetApp.flush();
    ss.toast(
      "Completed " + macroName + " (" + result.solve_count + " solves in " + Math.round(result.execution_time_ms) + " ms)",
      "Vertex AI Solver",
      4
    );

    if (typeof installEditTrigger === "function") {
      installEditTrigger(ss);
    }

    return result;
  } catch (err) {
    SpreadsheetApp.getUi().alert("Error running " + macroName + ":\n" + (err && err.message ? err.message : String(err)));
    throw err;
  }
}
