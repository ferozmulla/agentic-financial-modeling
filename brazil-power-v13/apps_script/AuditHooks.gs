/**
 * Enterprise Commodity Modeling — Hybrid Governance Audit Hooks (FR-B05, FR-B06, FR-B08)
 * Path 1: Installable onGovernedSheetEdit(e) and onGovernedSheetChange(e) real-time hooks.
 * Path 2: commitGovernedCheckpoint() full OpenXML/Grid snapshot archival and R1C1 diffing.
 */

function installEditTrigger(ss) {
  try {
    var sheetObj = (ss && typeof ss.getId === "function") ? ss : SpreadsheetApp.getActiveSpreadsheet();
    var currentId = sheetObj.getId();
    var props = PropertiesService.getScriptProperties();
    if (props.getProperty("GOVERNED_TRIGGERS_V2_ID") === currentId) {
      return;
    }

    var triggers = ScriptApp.getProjectTriggers();
    var hasEditTrigger = false;
    var hasChangeTrigger = false;
    for (var i = 0; i < triggers.length; i++) {
      var fn = triggers[i].getHandlerFunction();
      if (fn === "onGovernedSheetEdit") {
        hasEditTrigger = true;
      } else if (fn === "onGovernedSheetChange") {
        hasChangeTrigger = true;
      }
    }

    if (!hasEditTrigger) {
      ScriptApp.newTrigger("onGovernedSheetEdit")
        .forSpreadsheet(sheetObj)
        .onEdit()
        .create();
    }
    if (!hasChangeTrigger) {
      ScriptApp.newTrigger("onGovernedSheetChange")
        .forSpreadsheet(sheetObj)
        .onChange()
        .create();
    }
    props.setProperty("GOVERNED_TRIGGERS_V2_ID", currentId);
  } catch (err) {
    // Non-blocking so solver execution never fails if trigger creation is restricted
  }
}

function onGovernedSheetEdit(e) {
  if (!e || !e.range) {
    return;
  }
  var sheet = e.range.getSheet();
  var ss = e.source || SpreadsheetApp.getActiveSpreadsheet();
  var cellCoord = e.range.getA1Notation();
  var formula = e.range.getFormula();
  var userEmail = Session.getActiveUser().getEmail() || "admin@ferozmulla.altostrat.com";
  var copyLocation = "Google Drive Copy (" + ss.getName() + " | ID: " + ss.getId() + ") | " + ss.getUrl();

  var payload = {
    spreadsheet_id: ss.getId(),
    workbook_name: ss.getName(),
    spreadsheet_url: ss.getUrl(),
    sheet_name: sheet.getName(),
    cell_coord: cellCoord,
    row_num: e.range.getRow(),
    col_num: e.range.getColumn(),
    old_value: e.oldValue !== undefined ? String(e.oldValue) : null,
    new_value: e.value !== undefined ? String(e.value) : null,
    new_formula: formula ? formula : null,
    who_google_user: userEmail,
    when_event_utc: new Date().toISOString()
  };

  var url = getGatewayBaseUrl_() + "/v1/ingest/edit-event";
  UrlFetchApp.fetch(url, {
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
}

function onGovernedSheetChange(e) {
  if (!e || !e.changeType) {
    return;
  }
  var trackedTypes = {
    INSERT_ROW: true,
    REMOVE_ROW: true,
    INSERT_COLUMN: true,
    REMOVE_COLUMN: true,
    INSERT_GRID: true,
    REMOVE_GRID: true
  };
  if (!trackedTypes[e.changeType]) {
    return;
  }

  var ss = e.source || SpreadsheetApp.getActiveSpreadsheet();
  var activeSheet = ss.getActiveSheet();
  var activeRange = ss.getActiveRange();
  var sheetName = activeSheet ? activeSheet.getName() : "Workbook";
  var cellCoord = activeRange ? activeRange.getA1Notation() : "A1";
  var userEmail = Session.getActiveUser().getEmail() || "admin@ferozmulla.altostrat.com";
  var copyLocation = "Google Drive Copy (" + ss.getName() + " | ID: " + ss.getId() + ") | " + ss.getUrl();

  var payload = {
    spreadsheet_id: ss.getId(),
    workbook_name: ss.getName(),
    spreadsheet_url: ss.getUrl(),
    sheet_name: sheetName,
    cell_coord: cellCoord,
    row_num: activeRange ? activeRange.getRow() : 1,
    col_num: activeRange ? activeRange.getColumn() : 1,
    old_value: null,
    new_value: e.changeType + " on " + sheetName + " (" + cellCoord + ")",
    new_formula: null,
    structural_change_type: e.changeType,
    who_google_user: userEmail,
    when_event_utc: new Date().toISOString()
  };

  var url = getGatewayBaseUrl_() + "/v1/ingest/edit-event";
  UrlFetchApp.fetch(url, {
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
}

function commitGovernedCheckpoint() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var ui = SpreadsheetApp.getUi();
  var promptRes = ui.prompt(
    "Commit Governed Model Checkpoint",
    "Enter a brief description of structural or scenario changes:",
    ui.ButtonSet.OK_CANCEL
  );
  if (promptRes.getSelectedButton() !== ui.Button.OK) {
    return;
  }

  var comment = promptRes.getResponseText() || "Manual analyst checkpoint";
  var spreadsheetId = ss.getId();
  var exportUrl = "https://docs.google.com/spreadsheets/d/" + spreadsheetId + "/export?format=xlsx";
  var xlsxBlob = UrlFetchApp.fetch(exportUrl, {
    headers: {
      Authorization: "Bearer " + ScriptApp.getOAuthToken()
    }
  }).getBlob();

  var payload = {
    spreadsheet_id: spreadsheetId,
    workbook_name: ss.getName(),
    xlsm_base64: Utilities.base64Encode(xlsxBlob.getBytes()),
    commit_comment: comment,
    who_google_user: Session.getActiveUser().getEmail() || "analyst@enterprise.com"
  };

  var url = getGatewayBaseUrl_() + "/v1/ingest/checkpoint";
  var response = UrlFetchApp.fetch(url, {
    method: "post",
    contentType: "application/json",
    headers: {
      Authorization: "Bearer " + ScriptApp.getIdentityToken()
    },
    payload: JSON.stringify(payload),
    muteHttpExceptions: true
  });

  var result = JSON.parse(response.getContentText());
  ss.toast(
    "Committed Version #" + result.version_seq_num + " (" + result.structural_mutation_count + " structural changes)",
    "Governance Engine",
    5
  );
}
