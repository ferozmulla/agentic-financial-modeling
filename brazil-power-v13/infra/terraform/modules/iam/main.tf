# Least-privilege dedicated service accounts (INFRA-05 & INFRA-06 additive-only bindings)

resource "google_service_account" "gateway_sa" {
  account_id   = "sa-sheets-gateway"
  display_name = "Sheets Commodity Modeling FastAPI Gateway SA"
  project      = var.project_id
}

resource "google_service_account" "vertex_solver_sa" {
  account_id   = "sa-vertex-solver"
  display_name = "Vertex AI Quantitative Solver Prediction SA"
  project      = var.project_id
}

resource "google_service_account" "bq_remote_fn_sa" {
  account_id   = "sa-bq-remote-fn"
  display_name = "BigQuery Remote Function Invoker SA"
  project      = var.project_id
}

locals {
  gateway_roles = [
    "roles/aiplatform.user",
    "roles/alloydb.client",
    "roles/bigquery.dataEditor",
    "roles/pubsub.publisher",
    "roles/secretmanager.secretAccessor",
    "roles/storage.objectAdmin",
  ]
  vertex_roles = [
    "roles/artifactregistry.reader",
    "roles/logging.logWriter",
    "roles/monitoring.metricWriter",
    "roles/storage.objectViewer",
  ]
}

resource "google_project_iam_member" "gateway_bindings" {
  for_each = toset(local.gateway_roles)
  project  = var.project_id
  role     = each.value
  member   = "serviceAccount:${google_service_account.gateway_sa.email}"
}

resource "google_project_iam_member" "vertex_bindings" {
  for_each = toset(local.vertex_roles)
  project  = var.project_id
  role     = each.value
  member   = "serviceAccount:${google_service_account.vertex_solver_sa.email}"
}

resource "google_project_iam_member" "bq_remote_run_invoker" {
  project = var.project_id
  role    = "roles/run.invoker"
  member  = "serviceAccount:${google_service_account.bq_remote_fn_sa.email}"
}
