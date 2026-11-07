-- BigQuery ML Models: ARIMA_PLUS Driver Trajectories & Vertex AI Model Registry Crack-Spread Surrogate
-- Project: comm-model-mod | Dataset: eulr_commodity_mod_governance

CREATE TABLE IF NOT EXISTS `comm-model-mod.eulr_commodity_mod_governance.historical_driver_trajectories` (
  driver_category STRING NOT NULL,
  series_mnemonic STRING NOT NULL,
  year_date DATE NOT NULL,
  value FLOAT64 NOT NULL
);

CREATE OR REPLACE MODEL `comm-model-mod.eulr_commodity_mod_governance.bqml_eulr_drivers_forecast_v1`
OPTIONS (
  model_type = 'ARIMA_PLUS',
  time_series_timestamp_col = 'year_date',
  time_series_data_col = 'value',
  time_series_id_col = 'series_mnemonic',
  auto_arima = TRUE,
  data_frequency = 'YEARLY'
) AS
SELECT
  year_date,
  series_mnemonic,
  value
FROM `comm-model-mod.eulr_commodity_mod_governance.historical_driver_trajectories`;

CREATE TABLE IF NOT EXISTS `comm-model-mod.eulr_commodity_mod_governance.solver_surrogate_training_grid` (
  dated_brent_usd_bbl FLOAT64 NOT NULL,
  eu_ets_eur_tco2 FLOAT64 NOT NULL,
  urals_diff_usd_bbl FLOAT64 NOT NULL,
  nwe_fcc_margin_usd_bbl FLOAT64 NOT NULL
);

CREATE OR REPLACE MODEL `comm-model-mod.eulr_commodity_mod_governance.bqml_eulr_margin_surrogate_v1`
OPTIONS (
  model_type = 'LINEAR_REG',
  input_label_cols = ['nwe_fcc_margin_usd_bbl'],
  model_registry = 'VERTEX_AI',
  vertex_ai_model_id = 'eulr-sheets-mod-margin-surrogate'
) AS
SELECT
  dated_brent_usd_bbl,
  eu_ets_eur_tco2,
  urals_diff_usd_bbl,
  nwe_fcc_margin_usd_bbl
FROM `comm-model-mod.eulr_commodity_mod_governance.solver_surrogate_training_grid`;
