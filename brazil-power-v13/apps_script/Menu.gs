/**
 * Enterprise Commodity Modeling — Google Sheets Custom Menu & Button Bindings (FR-A06)
 * Updated for the 31-button layout on General!B42:N52.
 */

var GENERAL_BUTTON_MAP = {
  "43:2": "lcoe_exec",
  "42:3": "calcule_tir1",
  "42:4": "calcule_tir2",
  "42:5": "calcule_tir3",
  "42:6": "calcule_tir4",
  "42:7": "calcule_tir5",
  "42:8": "calcule_tir6",
  "42:9": "calcule_tir7",
  "42:10": "calcule_tir8",
  "42:11": "calcule_tir9",
  "42:12": "calcule_tir10",
  "42:13": "calcule_tir11",
  "42:14": "calcule_tir12",
  "45:3": "calculo_cvu1",
  "45:4": "calculo_cvu2",
  "45:5": "calculo_cvu3",
  "45:6": "calculo_cvu4",
  "45:7": "calculo_cvu5",
  "45:8": "calculo_cvu6",
  "45:9": "calculo_cvu7",
  "45:10": "calculo_cvu8",
  "45:11": "calculo_cvu9",
  "45:12": "calculo_cvu10",
  "45:13": "calculo_cvu11",
  "45:14": "calculo_cvu12",
  "48:4": "calculo_cvu2bi",
  "48:6": "calculo_cvu4bi",
  "48:7": "calculo_capexvscf",
  "48:8": "calculo_priceirr",
  "52:7": "calculo_capexvscfbi",
  "52:8": "calculo_priceirr_bi"
};

function onOpen() {
  var ui = SpreadsheetApp.getUi();
  ui.createMenu("Commodity Modeling")
    .addItem("Run Full LCOE & Dispatch Suite (lcoe_exec)", "lcoe_exec")
    .addItem("Run Multi-Decade LCOE Forecast (lcoe_forecast)", "lcoe_forecast")
    .addItem("Run Fator-i Calibration (fator_i)", "fator_i")
    .addItem("Refresh BigQuery ML LT Forecasts (Capex / Fuel / CF)", "refreshBqmlForecasts")
    .addSeparator()
    .addSubMenu(
      ui.createMenu("Tornado IRR Solvers (calcule_tir 1..12)")
        .addItem("Tech 01 — Gas CCGT (calcule_tir1)", "calcule_tir1")
        .addItem("Tech 02 — Biomass (calcule_tir2)", "calcule_tir2")
        .addItem("Tech 03 — Biogas (calcule_tir3)", "calcule_tir3")
        .addItem("Tech 04 — Wind Onshore (calcule_tir4)", "calcule_tir4")
        .addItem("Tech 05 — Solar Utility (calcule_tir5)", "calcule_tir5")
        .addItem("Tech 06 — Small Hydro PCH (calcule_tir6)", "calcule_tir6")
        .addItem("Tech 07 — Local Coal (calcule_tir7)", "calcule_tir7")
        .addItem("Tech 08 — Imported Coal (calcule_tir8)", "calcule_tir8")
        .addItem("Tech 09 — Woodchip (calcule_tir9)", "calcule_tir9")
        .addItem("Tech 10 — Gas OCGT (calcule_tir10)", "calcule_tir10")
        .addItem("Tech 11 — Solar DG Res (calcule_tir11)", "calcule_tir11")
        .addItem("Tech 12 — Solar DG Comm (calcule_tir12)", "calcule_tir12")
    )
    .addSubMenu(
      ui.createMenu("CVU Sweep Solvers (calculo_cvu 1..12)")
        .addItem("Tech 01 CVU (calculo_cvu1)", "calculo_cvu1")
        .addItem("Tech 02 CVU (calculo_cvu2)", "calculo_cvu2")
        .addItem("Tech 03 CVU (calculo_cvu3)", "calculo_cvu3")
        .addItem("Tech 04 CVU (calculo_cvu4)", "calculo_cvu4")
        .addItem("Tech 05 CVU (calculo_cvu5)", "calculo_cvu5")
        .addItem("Tech 06 CVU (calculo_cvu6)", "calculo_cvu6")
        .addItem("Tech 07 CVU (calculo_cvu7)", "calculo_cvu7")
        .addItem("Tech 08 CVU (calculo_cvu8)", "calculo_cvu8")
        .addItem("Tech 09 CVU (calculo_cvu9)", "calculo_cvu9")
        .addItem("Tech 10 CVU (calculo_cvu10)", "calculo_cvu10")
        .addItem("Tech 11 CVU (calculo_cvu11)", "calculo_cvu11")
        .addItem("Tech 12 CVU (calculo_cvu12)", "calculo_cvu12")
    )
    .addSubMenu(
      ui.createMenu("1D & 2D Sensitivity Matrices")
        .addItem("Biomass 2D BI LCOE (calculo_cvu2bi)", "calculo_cvu2bi")
        .addItem("Wind 2D BI LCOE (calculo_cvu4bi)", "calculo_cvu4bi")
        .addItem("Solar 1D Capex vs IRR (calculo_capexvscf)", "calculo_capexvscf")
        .addItem("Hydro 1D Price vs IRR (calculo_priceirr)", "calculo_priceirr")
        .addItem("Solar 2D BI LCOE (calculo_capexvscfbi)", "calculo_capexvscfbi")
        .addItem("Hydro 2D BI LCOE (calculo_priceirr_bi)", "calculo_priceirr_bi")
    )
    .addSeparator()
    .addSubMenu(
      ui.createMenu("Admin Controls")
        .addItem("Enable 4-Ws Governance Audit Triggers (Edit + Change)", "installEditTrigger")
        .addItem("Auto-Bind, Snap & Size Drawing Buttons", "autoBindGeneralDrawingButtons")
        .addItem("Toggle Freeze Button Deck (Row 52 / Row 5)", "toggleFreezeButtonDeck")
        .addItem("Connect & Refresh BigQuery / BQML Tabs (Connected Sheets)", "setupBigQueryConnectedSheets")
    )
    .addToUi();
}

function setupBigQueryConnectedSheets() {
  SpreadsheetApp.enableBigQueryExecution();
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var projectId = "comm-model-mod";
  var datasetId = "sheets_commodity_mod_governance";

  var oldCombined = ss.getSheetByName("LT_BQML_Formatted");
  if (oldCombined) {
    ss.deleteSheet(oldCombined);
  }

  var extractTabName = "BQML_LT_Forecasts";
  var existingExtract = ss.getSheetByName(extractTabName);
  var dsTable = null;

  if (existingExtract && !existingExtract.asDataSourceSheet()) {
    var existingTables = existingExtract.getDataSourceTables();
    if (existingTables && existingTables.length > 0) {
      dsTable = existingTables[0];
    }
  }

  if (!dsTable) {
    if (existingExtract) {
      ss.deleteSheet(existingExtract);
    }
    var forecastSpec = SpreadsheetApp.newDataSourceSpec()
      .asBigQuery()
      .setProjectId(projectId)
      .setRawQuery(
        "SELECT * FROM `" +
          projectId +
          "." +
          datasetId +
          ".vw_connected_sheets_lt_forecasts` ORDER BY curve_sheet, Yr"
      )
      .build();
    var extractSheet = ss.insertSheetWithDataSourceTable(forecastSpec);
    extractSheet.setName(extractTabName);
    dsTable = extractSheet.getDataSourceTables()[0];
    dsTable.waitForCompletion(60);
    extractSheet.hideSheet();
  } else {
    dsTable.forceRefreshData();
    dsTable.waitForCompletion(60);
    existingExtract.hideSheet();
  }

  var bqmlTabs = [
    {
      name: "LT_Capex_BQML",
      btnCol: 13,
      formulas: [
        { cell: "A8", f: '=FILTER(BQML_LT_Forecasts!B2:B150, BQML_LT_Forecasts!A2:A150="1. LT Capex (R$/kW)")' },
        { cell: "B8", f: '=FILTER(BQML_LT_Forecasts!D2:N150, BQML_LT_Forecasts!A2:A150="1. LT Capex (R$/kW)")' },
        { cell: "M8", f: '=FILTER(BQML_LT_Forecasts!C2:C150, BQML_LT_Forecasts!A2:A150="1. LT Capex (R$/kW)")' }
      ]
    },
    {
      name: "LT_Fuel_BQML",
      btnCol: 13,
      formulas: [
        { cell: "A8", f: '=FILTER(BQML_LT_Forecasts!B2:B150, BQML_LT_Forecasts!A2:A150="2. LT Fuel (R$/kW)")' },
        { cell: "B8", f: '=FILTER(BQML_LT_Forecasts!D2:N150, BQML_LT_Forecasts!A2:A150="2. LT Fuel (R$/kW)")' },
        { cell: "M8", f: '=FILTER(BQML_LT_Forecasts!C2:C150, BQML_LT_Forecasts!A2:A150="2. LT Fuel (R$/kW)")' }
      ]
    },
    {
      name: "LT_CF_BQML",
      btnCol: 8,
      formulas: [
        { cell: "A8", f: '=FILTER(BQML_LT_Forecasts!B2:B150, BQML_LT_Forecasts!A2:A150="3. LT Capacity Factor (%)")' },
        { cell: "F8", f: '=ARRAYFORMULA(FILTER(BQML_LT_Forecasts!H2:H150, BQML_LT_Forecasts!A2:A150="3. LT Capacity Factor (%)") / 100)' },
        { cell: "G8", f: '=ARRAYFORMULA(FILTER(BQML_LT_Forecasts!I2:I150, BQML_LT_Forecasts!A2:A150="3. LT Capacity Factor (%)") / 100)' },
        { cell: "H8", f: '=FILTER(BQML_LT_Forecasts!C2:C150, BQML_LT_Forecasts!A2:A150="3. LT Capacity Factor (%)")' }
      ]
    }
  ];

  var btnBlob = getButton3dOverlayBlob_();
  var attached = [];
  for (var t = 0; t < bqmlTabs.length; t++) {
    var cfg = bqmlTabs[t];
    var tabSheet = ss.getSheetByName(cfg.name);
    if (!tabSheet) continue;
    for (var q = 0; q < cfg.formulas.length; q++) {
      tabSheet.getRange(cfg.formulas[q].cell).setFormula(cfg.formulas[q].f);
    }

    var existingImgs = tabSheet.getImages();
    for (var m = 0; m < existingImgs.length; m++) {
      try {
        if (existingImgs[m].getAnchorCell().getRow() <= 2 && existingImgs[m].getAnchorCell().getColumn() >= cfg.btnCol - 1) {
          existingImgs[m].remove();
        }
      } catch (e) {}
    }

    tabSheet.setRowHeight(1, 36);
    var btnCell = tabSheet.getRange(1, cfg.btnCol);
    btnCell
      .setValue("Refresh BQML")
      .setBackground("#1B365D")
      .setFontColor("#FFFFFF")
      .setFontFamily("Calibri")
      .setFontSize(10)
      .setFontWeight("bold")
      .setHorizontalAlignment("center")
      .setVerticalAlignment("middle")
      .setBorder(false, false, false, false, false, false);

    var btnOverlay = tabSheet.insertImage(btnBlob, cfg.btnCol, 1, 0, 0);
    btnOverlay.setWidth(tabSheet.getColumnWidth(cfg.btnCol) + 1);
    btnOverlay.setHeight(tabSheet.getRowHeight(1) + 1);
    btnOverlay.assignScript("refreshBqmlForecasts");
    attached.push(cfg.name);
  }

  var definitions = [
    {
      tabName: "BQML_LCOE_Surrogate",
      tableId: "vw_bqml_lcoe_surrogate_predictions"
    },
    {
      tabName: "BQ_4Ws_Audit_Log",
      tableId: "vw_audit_4w_summary"
    }
  ];

  for (var i = 0; i < definitions.length; i++) {
    var def = definitions[i];
    var existingSheet = ss.getSheetByName(def.tabName);
    var dsSheet = existingSheet ? existingSheet.asDataSourceSheet() : null;

    if (!dsSheet) {
      if (existingSheet) {
        ss.deleteSheet(existingSheet);
      }
      var spec = SpreadsheetApp.newDataSourceSpec()
        .asBigQuery()
        .setProjectId(projectId)
        .setTableProjectId(projectId)
        .setDatasetId(datasetId)
        .setTableId(def.tableId)
        .build();
      dsSheet = ss.insertDataSourceSheet(spec);
      dsSheet.asSheet().setName(def.tabName);
    }

    try {
      dsSheet.refreshData();
    } catch (refreshErr) {}
    attached.push(def.tabName);
  }

  SpreadsheetApp.flush();
  ss.toast(
    "Wired live Connected Sheets refresh on: " + attached.join(", "),
    "Connected Sheets Active",
    6
  );
}

function refreshBqmlForecasts() {
  SpreadsheetApp.enableBigQueryExecution();
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  ss.toast("Refreshing BigQuery ML (ARIMA_PLUS) forecasts into LT_Capex_BQML, LT_Fuel_BQML & LT_CF_BQML...", "BigQuery ML", 5);
  var extractSheet = ss.getSheetByName("BQML_LT_Forecasts");
  if (!extractSheet || extractSheet.getDataSourceTables().length === 0) {
    setupBigQueryConnectedSheets();
    return;
  }
  var dsTable = extractSheet.getDataSourceTables()[0];
  dsTable.forceRefreshData();
  dsTable.waitForCompletion(60);
  SpreadsheetApp.flush();
  ss.toast("LT_Capex_BQML, LT_Fuel_BQML & LT_CF_BQML updated with latest BigQuery ML forecasts.", "BigQuery ML Refreshed", 5);
}

function getButton3dOverlayBlob_() {
  var button3dFrameBase64 = "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";
  return Utilities.newBlob(
    Utilities.base64Decode(button3dFrameBase64),
    "image/png",
    "solver_btn_3d_overlay.png"
  );
}

var GENERAL_BUTTON_SPECS = [
  { row: 43, col: 2,  macro: "lcoe_exec",          label: "Forecast LCOE", bg: "#1B365D" },
  { row: 42, col: 3,  macro: "calcule_tir1",       label: "Tornado 1",     bg: "#1F4E79" },
  { row: 42, col: 4,  macro: "calcule_tir2",       label: "Tornado 2",     bg: "#1F4E79" },
  { row: 42, col: 5,  macro: "calcule_tir3",       label: "Tornado 3",     bg: "#1F4E79" },
  { row: 42, col: 6,  macro: "calcule_tir4",       label: "Tornado 4",     bg: "#1F4E79" },
  { row: 42, col: 7,  macro: "calcule_tir5",       label: "Tornado 5",     bg: "#1F4E79" },
  { row: 42, col: 8,  macro: "calcule_tir6",       label: "Tornado 6",     bg: "#1F4E79" },
  { row: 42, col: 9,  macro: "calcule_tir7",       label: "Tornado 7",     bg: "#1F4E79" },
  { row: 42, col: 10, macro: "calcule_tir8",       label: "Tornado 8",     bg: "#1F4E79" },
  { row: 42, col: 11, macro: "calcule_tir9",       label: "Tornado 9",     bg: "#1F4E79" },
  { row: 42, col: 12, macro: "calcule_tir10",      label: "Tornado 10",    bg: "#1F4E79" },
  { row: 42, col: 13, macro: "calcule_tir11",      label: "Tornado 11",    bg: "#1F4E79" },
  { row: 42, col: 14, macro: "calcule_tir12",      label: "Tornado 12",    bg: "#1F4E79" },
  { row: 45, col: 3,  macro: "calculo_cvu1",       label: "Fuel/CVU1",     bg: "#2E6B8E" },
  { row: 45, col: 4,  macro: "calculo_cvu2",       label: "Fuel/CVU2",     bg: "#2E6B8E" },
  { row: 45, col: 5,  macro: "calculo_cvu3",       label: "Fuel/CVU3",     bg: "#2E6B8E" },
  { row: 45, col: 6,  macro: "calculo_cvu4",       label: "Fuel/CVU4",     bg: "#2E6B8E" },
  { row: 45, col: 7,  macro: "calculo_cvu5",       label: "Fuel/CVU5",     bg: "#2E6B8E" },
  { row: 45, col: 8,  macro: "calculo_cvu6",       label: "Fuel/CVU6",     bg: "#2E6B8E" },
  { row: 45, col: 9,  macro: "calculo_cvu7",       label: "Fuel/CVU7",     bg: "#2E6B8E" },
  { row: 45, col: 10, macro: "calculo_cvu8",       label: "Fuel/CVU8",     bg: "#2E6B8E" },
  { row: 45, col: 11, macro: "calculo_cvu9",       label: "Fuel/CVU9",     bg: "#2E6B8E" },
  { row: 45, col: 12, macro: "calculo_cvu10",      label: "Fuel/CVU10",    bg: "#2E6B8E" },
  { row: 45, col: 13, macro: "calculo_cvu11",      label: "Fuel/CVU11",    bg: "#2E6B8E" },
  { row: 45, col: 14, macro: "calculo_cvu12",      label: "Fuel/CVU12",    bg: "#2E6B8E" },
  { row: 48, col: 4,  macro: "calculo_cvu2bi",     label: "BI LCOE",       bg: "#3B4990" },
  { row: 48, col: 6,  macro: "calculo_cvu4bi",     label: "BI LCOE",       bg: "#3B4990" },
  { row: 48, col: 7,  macro: "calculo_capexvscf",  label: "Capex vs IRR",  bg: "#1D6F72" },
  { row: 48, col: 8,  macro: "calculo_priceirr",   label: "Price vs IRR",  bg: "#1D6F72" },
  { row: 52, col: 7,  macro: "calculo_capexvscfbi",label: "BI LCOE",       bg: "#3B4990" },
  { row: 52, col: 8,  macro: "calculo_priceirr_bi",label: "BI LCOE",       bg: "#3B4990" }
];

function autoBindGeneralDrawingButtons() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = ss.getSheetByName("General");
  if (!sheet) {
    throw new Error("Worksheet 'General' not found.");
  }

  var drawings = sheet.getDrawings();
  var removedDrawings = 0;
  for (var i = 0; i < drawings.length; i++) {
    try {
      var d = drawings[i];
      var r = d.getContainerInfo().getAnchorRow();
      if (r >= 40 && r <= 54) {
        d.remove();
        removedDrawings++;
      }
    } catch (err) {
      // Ignore if already removed
    }
  }

  var images = sheet.getImages();
  for (var j = 0; j < images.length; j++) {
    try {
      var existingImg = images[j];
      var anchorRow = existingImg.getAnchorCell().getRow();
      if (anchorRow >= 40 && anchorRow <= 54) {
        existingImg.remove();
      }
    } catch (err) {
      // Ignore if already removed
    }
  }

  var btnRows = [42, 43, 45, 48, 52];
  for (var b = 0; b < btnRows.length; b++) {
    sheet.setRowHeight(btnRows[b], 36);
  }

  var pngBlob = getButton3dOverlayBlob_();

  for (var k = 0; k < GENERAL_BUTTON_SPECS.length; k++) {
    var spec = GENERAL_BUTTON_SPECS[k];
    var cell = sheet.getRange(spec.row, spec.col);
    cell
      .setValue(spec.label)
      .setBackground(spec.bg)
      .setFontColor("#FFFFFF")
      .setFontFamily("Calibri")
      .setFontSize(10)
      .setFontWeight("bold")
      .setHorizontalAlignment("center")
      .setVerticalAlignment("middle")
      .setBorder(false, false, false, false, false, false);

    var colW = sheet.getColumnWidth(spec.col);
    var rowH = sheet.getRowHeight(spec.row);
    var overlay = sheet.insertImage(pngBlob, spec.col, spec.row, 0, 0);
    overlay.setWidth(colW + 1);
    overlay.setHeight(rowH + 1);
    overlay.assignScript(spec.macro);
  }

  SpreadsheetApp.flush();
  onOpen();
  if (typeof installEditTrigger === "function") {
    installEditTrigger(ss);
  }
  ss.toast(
    "Configured 31 permanent native cell buttons with transparent click overlays (removed " +
      removedDrawings +
      " opaque drawings).",
    "Commodity Modeling",
    6
  );
}

function toggleFreezeButtonDeck() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = ss.getSheetByName("General");
  var currentFrozen = sheet.getFrozenRows();
  if (currentFrozen < 52) {
    sheet.setFrozenRows(52);
    sheet.setFrozenColumns(2);
    ss.toast("Frozen Rows 1..52 and Columns A..B so all 31 buttons stay locked while scrolling.", "Freeze Active", 4);
  } else {
    sheet.setFrozenRows(5);
    sheet.setFrozenColumns(2);
    ss.toast("Restored Frozen Header Rows 1..5 and Columns A..B (use row group [-] on left to collapse rows 6..40).", "Header Freeze Active", 5);
  }
}

// 31 Button Bindings on General!B42:N52
function calcule_tir1() { invokeCloudSolver("calcule_tir1"); }
function calcule_tir2() { invokeCloudSolver("calcule_tir2"); }
function calcule_tir3() { invokeCloudSolver("calcule_tir3"); }
function calcule_tir4() { invokeCloudSolver("calcule_tir4"); }
function calcule_tir5() { invokeCloudSolver("calcule_tir5"); }
function calcule_tir6() { invokeCloudSolver("calcule_tir6"); }
function calcule_tir7() { invokeCloudSolver("calcule_tir7"); }
function calcule_tir8() { invokeCloudSolver("calcule_tir8"); }
function calcule_tir9() { invokeCloudSolver("calcule_tir9"); }
function calcule_tir10() { invokeCloudSolver("calcule_tir10"); }
function calcule_tir11() { invokeCloudSolver("calcule_tir11"); }
function calcule_tir12() { invokeCloudSolver("calcule_tir12"); }

function calculo_cvu1() { invokeCloudSolver("calculo_cvu1"); }
function calculo_cvu2() { invokeCloudSolver("calculo_cvu2"); }
function calculo_cvu3() { invokeCloudSolver("calculo_cvu3"); }
function calculo_cvu4() { invokeCloudSolver("calculo_cvu4"); }
function calculo_cvu5() { invokeCloudSolver("calculo_cvu5"); }
function calculo_cvu6() { invokeCloudSolver("calculo_cvu6"); }
function calculo_cvu7() { invokeCloudSolver("calculo_cvu7"); }
function calculo_cvu8() { invokeCloudSolver("calculo_cvu8"); }
function calculo_cvu9() { invokeCloudSolver("calculo_cvu9"); }
function calculo_cvu10() { invokeCloudSolver("calculo_cvu10"); }
function calculo_cvu11() { invokeCloudSolver("calculo_cvu11"); }
function calculo_cvu12() { invokeCloudSolver("calculo_cvu12"); }

function lcoe_exec() { invokeCloudSolver("lcoe_exec"); }
function lcoe_forecast() { invokeCloudSolver("lcoe_forecast"); }
function fator_i() { invokeCloudSolver("fator_i"); }

function calculo_cvu2bi() { invokeCloudSolver("calculo_cvu2bi"); }
function calculo_cvu4bi() { invokeCloudSolver("calculo_cvu4bi"); }
function calculo_capexvscf() { invokeCloudSolver("calculo_capexvscf"); }
function calculo_priceirr() { invokeCloudSolver("calculo_priceirr"); }
function calculo_capexvscfbi() { invokeCloudSolver("calculo_capexvscfbi"); }
function calculo_priceirr_bi() { invokeCloudSolver("calculo_priceirr_bi"); }
