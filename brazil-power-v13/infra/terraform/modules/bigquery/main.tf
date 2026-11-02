resource "google_bigquery_dataset" "governance" {
  dataset_id                 = "sheets_commodity_mod_governance"
  project                    = var.project_id
  location                   = var.bq_location
  delete_contents_on_destroy = true
  labels                     = var.common_labels
}

resource "google_bigquery_table" "audit_events" {
  dataset_id          = google_bigquery_dataset.governance.dataset_id
  table_id            = "audit_events"
  project             = var.project_id
  deletion_protection = false
  labels              = var.common_labels
}

resource "google_bigquery_table" "solver_run_telemetry" {
  dataset_id          = google_bigquery_dataset.governance.dataset_id
  table_id            = "solver_run_telemetry"
  project             = var.project_id
  deletion_protection = false
  labels              = var.common_labels
}

resource "google_bigquery_connection" "cloud_run_remote_fn" {
  connection_id = "sheets-solver-conn"
  project       = var.project_id
  location      = var.bq_location
  friendly_name = "Cloud Run Solver Remote Function Connection (us-central1)"

  cloud_resource {}
}

resource "google_bigquery_connection" "vertex_gemini_us" {
  connection_id = "vertex-gemini-us-conn"
  project       = var.project_id
  location      = var.gemini_location
  friendly_name = "Vertex AI Gemini US Multi-Region Connection"

  cloud_resource {}
}
