/**
 * EULR (Eulr202409) Google Sheets Bound Apps Script (V8 Runtime)
 * - 5-Button 3D OverGridImage Execution Deck at KeyInputs!B2:N5
 * - 3 Breakout BQML Refresh Handlers (Macro_BQML, Crudes_BQML, Freight_BQML)
 * - Silent Distributed 4-Ws Governance & #FEF3C7 Pinned Price Overrides (Zero Popups/Notes)
 */

const EULR_CONFIG = {
  GATEWAY_BASE_URL: PropertiesService.getScriptProperties().getProperty("EULR_GATEWAY_URL") ||
    "https://eulr-equilibrium-gateway-1024543888590.us-central1.run.app",
  CENTRAL_SPREADSHEET_ID: "1rXSFn7dACfy7RTaNHxinstJAgk54ojMgDPsoxoZRgQk",
  GCP_PROJECT_ID: "comm-model-mod",
  BIGQUERY_DATASET: "eulr_commodity_mod_governance",
  PRICING_SHEETS: ["Crudes", "NWE Cif", "MED Cif", "NWE Fob", "MED Fob", "IMOfuels"],
  OVERRIDE_AMBER_HEX: "#FEF3C7"
};

function onOpen() {
  const ui = SpreadsheetApp.getUi();
  ui.createMenu("⚡ Commodity Modeling — EULR")
    .addItem("1. Solve 10-Pass Equilibrium", "runTenPassEquilibriumSolve")
    .addItem("2. Run 4-Way Scenario & Carbon Matrix", "runFourWayScenarioCarbonMatrix")
    .addItem("3. Sync Upstream Peer Workbooks (Uslr / Felr / Tankerlr)", "syncUpstreamPeerWorkbooks")
    .addItem("4. Revert Pinned Price Overrides (#FEF3C7)", "revertPinnedPriceOverrides")
    .addItem("5. Publish UPLOAD (1,273) & Links Out (234) to BigQuery", "publishUploadAndLinksOut")
    .addSeparator()
    .addItem("Refresh Macro_BQML Forecast", "refreshMacroBQML")
    .addItem("Refresh Crudes_BQML Forecast", "refreshCrudesBQML")
    .addItem("Refresh Freight_BQML Forecast", "refreshFreightBQML")
    .addSeparator()
    .addItem("Install Silent 4-Ws Governance Triggers", "ensureGovernedTriggersInstalled")
    .addToUi();
}

function ensureGovernedTriggersInstalled() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const triggers = ScriptApp.getUserTriggers(ss);
  const existingFns = triggers.map(t => t.getHandlerFunction());
  if (existingFns.indexOf("onGovernedSheetEdit") === -1) {
    ScriptApp.newTrigger("onGovernedSheetEdit").forSpreadsheet(ss).onEdit().create();
  }
  if (existingFns.indexOf("onGovernedSheetChange") === -1) {
    ScriptApp.newTrigger("onGovernedSheetChange").forSpreadsheet(ss).onChange().create();
  }
}

function callEulrGateway_(path, payload) {
  const url = EULR_CONFIG.GATEWAY_BASE_URL + path;
  const options = {
    method: "post",
    contentType: "application/json",
    payload: JSON.stringify(payload),
    muteHttpExceptions: true
  };
  const response = UrlFetchApp.fetch(url, options);
  return JSON.parse(response.getContentText());
}

function applyDeltaRanges_(ssId, deltaRanges) {
  if (!deltaRanges || !deltaRanges.length) return;
  const data = deltaRanges.map(d => ({
    range: "'" + d.sheet_name + "'!" + d.a1_range,
    values: d.values
  }));
  Sheets.Spreadsheets.Values.batchUpdate(
    { valueInputOption: "USER_ENTERED", data: data },
    ssId
  );
}

function runTenPassEquilibriumSolve() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const keyInputs = ss.getSheetByName("KeyInputs");
  const carbon = ss.getSheetByName("Carbon");
  const sensVal = keyInputs ? Number(keyInputs.getRange("AU10").getValue() || 0) : 0;
  const carbonMode = carbon ? String(carbon.getRange("A5").getValue() || "Sensitivity with EU ETS cost and pass-through") : "Sensitivity with EU ETS cost and pass-through";

  const resp = callEulrGateway_("/v1/eulr/solve", {
    spreadsheet_id: ss.getId(),
    scenario_mode: sensVal === 1 ? "sensitivity" : "base",
    carbon_mode: carbonMode,
    upstream_source_mode: "eulr_baseline_cached",
    max_iterations: 10,
    actor_email: Session.getActiveUser().getEmail() || "analyst@spglobal.com"
  });
  applyDeltaRanges_(ss.getId(), resp.delta_ranges);
  ss.toast("10-Pass Equilibrium converged in " + resp.compute_ms + " ms (NWE EN590 2025: $" + resp.key_prices_2025_usd_mt.NWE_Diesel_EN590_CIF_ARA + "/mt)", "EULR Solver", 4);
}

function runFourWayScenarioCarbonMatrix() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const resp = callEulrGateway_("/v1/eulr/scenario-matrix", {
    spreadsheet_id: ss.getId(),
    upstream_source_mode: "eulr_baseline_cached",
    actor_email: Session.getActiveUser().getEmail() || "analyst@spglobal.com"
  });
  const compSheet = ss.getSheetByName("Scenario_Comparison");
  if (compSheet && resp.comparison_table_rows && resp.comparison_table_rows.length) {
    compSheet.getRange(4, 1, resp.comparison_table_rows.length, resp.comparison_table_rows[0].length)
      .setValues(resp.comparison_table_rows);
    compSheet.getRange("A11").setValue(resp.ai_attribution_summary);
    ss.setActiveSheet(compSheet);
  }
}

function syncUpstreamPeerWorkbooks() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const resp = callEulrGateway_("/v1/eulr/sync-upstream", {
    spreadsheet_id: ss.getId(),
    target_mode: "peer_xlsx",
    actor_email: Session.getActiveUser().getEmail() || "analyst@spglobal.com"
  });
  if (resp.solve_result) {
    applyDeltaRanges_(ss.getId(), resp.solve_result.delta_ranges);
  }
  ss.toast("Synced " + resp.updated_peer_cells + " updated peer cells across Uslr, Felr & Tankerlr and re-converged 10 passes.", "Upstream Link Hub", 4);
}

function revertPinnedPriceOverrides() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const resp = callEulrGateway_("/v1/eulr/override/revert", {
    spreadsheet_id: ss.getId(),
    actor_email: Session.getActiveUser().getEmail() || "analyst@spglobal.com"
  });
  if (resp.reverted_cells && resp.reverted_cells.length) {
    resp.reverted_cells.forEach(cellKey => {
      const parts = cellKey.split("!");
      const sh = ss.getSheetByName(parts[0]);
      if (sh && parts[1]) {
        sh.getRange(parts[1]).setBackground(null);
      }
    });
  }
  if (resp.solve_result) {
    applyDeltaRanges_(ss.getId(), resp.solve_result.delta_ranges);
  }
  ss.toast("Reverted " + (resp.reverted_cells ? resp.reverted_cells.length : 0) + " pinned overrides to baseline equilibrium.", "Override Governance", 4);
}

function publishUploadAndLinksOut() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const resp = callEulrGateway_("/v1/eulr/publish", {
    spreadsheet_id: ss.getId(),
    vintage_tag: "202409",
    actor_email: Session.getActiveUser().getEmail() || "analyst@spglobal.com"
  });
  ss.toast("Published " + resp.upload_series_count + " UPLOAD series & " + resp.links_out_series_count + " Links out series to BigQuery.", "BigQuery Publisher", 4);
}

function refreshMacroBQML() { refreshBQMLTab_("Macro_BQML"); }
function refreshCrudesBQML() { refreshBQMLTab_("Crudes_BQML"); }
function refreshFreightBQML() { refreshBQMLTab_("Freight_BQML"); }

function refreshBQMLTab_(tabName) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const resp = callEulrGateway_("/v1/eulr/bqml/refresh", {
    tab_name: tabName,
    horizon_end_year: 2050
  });
  const sh = ss.getSheetByName(tabName);
  if (sh && resp.series_rows && resp.series_rows.length) {
    sh.getRange(5, 1, resp.series_rows.length, resp.series_rows[0].length).setValues(resp.series_rows);
  }
}

function onGovernedSheetEdit(e) {
  if (!e || !e.range) return;
  const sh = e.range.getSheet();
  const sheetName = sh.getName();
  const cellA1 = e.range.getA1Notation();
  const ss = e.source;

  // Apply subtle #FEF3C7 amber fill immediately on pricing sheets (zero popups or hover notes)
  if (EULR_CONFIG.PRICING_SHEETS.indexOf(sheetName) !== -1 && e.range.getColumn() >= 4) {
    e.range.setBackground(EULR_CONFIG.OVERRIDE_AMBER_HEX);
  }

  callEulrGateway_("/v1/ingest/edit-event", {
    spreadsheet_id: ss.getId(),
    copy_location_url: ss.getUrl(),
    actor_email: Session.getActiveUser().getEmail() || "trader@spglobal.com",
    sheet_name: sheetName,
    cell_a1: cellA1,
    before_value: e.oldValue !== undefined ? e.oldValue : null,
    new_value: e.value !== undefined ? e.value : null,
    new_formula: e.range.getFormula() || null
  });
}

function onGovernedSheetChange(e) {
  if (!e || !e.changeType) return;
  if (["INSERT_ROW", "REMOVE_ROW", "INSERT_GRID", "REMOVE_GRID"].indexOf(e.changeType) === -1) return;
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  callEulrGateway_("/v1/ingest/edit-event", {
    spreadsheet_id: ss.getId(),
    copy_location_url: ss.getUrl(),
    actor_email: Session.getActiveUser().getEmail() || "analyst@spglobal.com",
    sheet_name: ss.getActiveSheet().getName(),
    cell_a1: "A1",
    structural_change_type: e.changeType
  });
}
