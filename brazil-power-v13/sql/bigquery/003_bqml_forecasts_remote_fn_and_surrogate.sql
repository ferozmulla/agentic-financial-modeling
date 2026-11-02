-- 003_bqml_forecasts_remote_fn_and_surrogate.sql
-- BigQuery ML Time-Series Forecasting (ARIMA_PLUS), Remote Function (fn_solve_lcoe in us-central1), and LCOE Surrogate Model

-- 1. BigQuery ML Time-Series Forecasting Model for Long-Term Capex, Fuel & Capacity Factor Curves
-- Trained on <= 2025 Historical Actuals to forecast the 15-Year Horizon (2026..2040) matching the workbook
CREATE OR REPLACE MODEL `sheets_commodity_mod_governance.bqml_lt_trajectories_forecast_v1`
OPTIONS (
  model_type = 'ARIMA_PLUS',
  time_series_timestamp_col = 'forecast_year_date',
  time_series_data_col = 'trajectory_value',
  time_series_id_col = ['curve_family', 'technology_code'],
  auto_arima = TRUE,
  data_frequency = 'YEARLY'
) AS
SELECT
  forecast_year_date,
  curve_family,       -- 'LT_CAPEX', 'LT_FUEL', or 'LT_CF'
  technology_code,    -- 'CCGT', 'Bio_CHP', 'Bio_retro', 'Bio_WC', 'Wind', 'Solar', 'Coal_PC', 'SHP', 'Coal_CFBC', 'GDPV_RES', 'GDPV_COM'
  trajectory_value
FROM `sheets_commodity_mod_governance.historical_lt_trajectories`
WHERE EXTRACT(YEAR FROM forecast_year_date) <= 2025;

-- Connected Sheets Live View for Pivoted 2018-2040 Trajectories (Actuals <=2025 + BQML Forecast 2026-2040)
CREATE OR REPLACE VIEW `sheets_commodity_mod_governance.vw_connected_sheets_lt_forecasts` AS
WITH combined_series AS (
  SELECT
    curve_family,
    technology_code,
    EXTRACT(YEAR FROM forecast_year_date) AS yr,
    'Historical Actual (<=2025)' AS data_source,
    trajectory_value AS val
  FROM `sheets_commodity_mod_governance.historical_lt_trajectories`
  WHERE EXTRACT(YEAR FROM forecast_year_date) <= 2025

  UNION ALL

  SELECT
    curve_family,
    technology_code,
    EXTRACT(YEAR FROM forecast_timestamp) AS yr,
    'BQML ARIMA_PLUS Forecast (2026-2040)' AS data_source,
    forecast_value AS val
  FROM ML.FORECAST(
    MODEL `sheets_commodity_mod_governance.bqml_lt_trajectories_forecast_v1`,
    STRUCT(15 AS horizon, 0.95 AS confidence_level)
  )
)
SELECT
  CASE curve_family
    WHEN 'LT_CAPEX' THEN '1. LT Capex (R$/kW)'
    WHEN 'LT_FUEL'  THEN '2. LT Fuel (R$/kW)'
    WHEN 'LT_CF'    THEN '3. LT Capacity Factor (%)'
    ELSE curve_family
  END AS curve_sheet,
  yr AS Yr,
  data_source AS Data_Source,
  ROUND(MAX(IF(technology_code = 'CCGT',      val, NULL)), 2) AS CCGT,
  ROUND(MAX(IF(technology_code = 'Bio_CHP',   val, NULL)), 2) AS Bio_CHP,
  ROUND(MAX(IF(technology_code = 'Bio_retro', val, NULL)), 2) AS Bio_retro,
  ROUND(MAX(IF(technology_code = 'Bio_WC',    val, NULL)), 2) AS Bio_WC,
  ROUND(MAX(IF(technology_code = 'Wind',      IF(curve_family = 'LT_CF', val * 100.0, val), NULL)), 2) AS Wind,
  ROUND(MAX(IF(technology_code = 'Solar',     IF(curve_family = 'LT_CF', val * 100.0, val), NULL)), 2) AS Solar,
  ROUND(MAX(IF(technology_code = 'Coal_PC',   val, NULL)), 2) AS Coal_PC,
  ROUND(MAX(IF(technology_code = 'SHP',       val, NULL)), 2) AS SHP,
  ROUND(MAX(IF(technology_code = 'Coal_CFBC', val, NULL)), 2) AS Coal_CFBC,
  ROUND(MAX(IF(technology_code = 'GDPV_RES',  val, NULL)), 2) AS GDPV_RES,
  ROUND(MAX(IF(technology_code = 'GDPV_COM',  val, NULL)), 2) AS GDPV_COM
FROM combined_series
GROUP BY curve_family, yr, data_source
ORDER BY curve_sheet, Yr;

-- 2. BigQuery Remote Function invoking the Cloud Run / Vertex AI Vectorized Solver in us-central1
CREATE OR REPLACE FUNCTION `sheets_commodity_mod_governance.fn_solve_lcoe`(
  macro_name STRING,
  payload_json JSON
) RETURNS JSON
REMOTE WITH CONNECTION `us-central1.sheets-mod-vertex-conn`
OPTIONS (
  endpoint = '${CLOUD_RUN_GATEWAY_URL}/v1/bqml/solve',
  max_batching_rows = 25
);

-- 3. BigQuery ML LCOE Surrogate Model registered in Vertex AI Model Registry
CREATE OR REPLACE MODEL `sheets_commodity_mod_governance.bqml_lcoe_surrogate_v1`
OPTIONS (
  model_type = 'LINEAR_REG',
  input_label_cols = ['solved_lcoe'],
  model_registry = 'vertex_ai',
  vertex_ai_model_id = 'sheets-commodity-mod-bqml-surrogate',
  vertex_ai_model_version_aliases = ['mvp-surrogate']
) AS
SELECT
  technology_code,
  capex_multiplier,
  fuel_cost_multiplier,
  capacity_factor_multiplier,
  wacc_rate,
  economic_life_yrs,
  solved_lcoe
FROM `sheets_commodity_mod_governance.solver_training_grid`;

-- Connected Sheets Live View for BQML LCOE Surrogate Predictions vs Exact Solver
CREATE OR REPLACE VIEW `sheets_commodity_mod_governance.vw_bqml_lcoe_surrogate_predictions` AS
SELECT
  technology_code,
  capex_multiplier,
  fuel_cost_multiplier,
  capacity_factor_multiplier,
  wacc_rate,
  economic_life_yrs,
  ROUND(solved_lcoe, 4) AS exact_solver_lcoe,
  ROUND(predicted_solved_lcoe, 4) AS bqml_predicted_lcoe,
  ROUND(predicted_solved_lcoe - solved_lcoe, 4) AS residual_diff
FROM ML.PREDICT(
  MODEL `sheets_commodity_mod_governance.bqml_lcoe_surrogate_v1`,
  TABLE `sheets_commodity_mod_governance.solver_training_grid`
)
ORDER BY technology_code, capex_multiplier, fuel_cost_multiplier, capacity_factor_multiplier, wacc_rate;

