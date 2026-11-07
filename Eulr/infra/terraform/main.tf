# Non-destructive API enablement (INFRA-06: disable_on_destroy = false)
resource "google_project_service" "enabled_apis" {
  for_each           = toset(local.required_apis)
  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}

# Least-privilege Service Account for eulr-equilibrium-gateway
resource "google_service_account" "eulr_gateway_sa" {
  project      = var.project_id
  account_id   = "eulr-equilibrium-gw-sa"
  display_name = "EULR Equilibrium Cloud Run Gateway SA"
  depends_on   = [google_project_service.enabled_apis]
}

# Cloud Storage Bucket for compiled baseline tensors, peer workbooks, and per-spreadsheet override masks
resource "google_storage_bucket" "eulr_snapshots" {
  project                     = var.project_id
  name                        = "${var.project_id}-eulr-snapshots"
  location                    = var.region
  uniform_bucket_level_access = true
  force_destroy               = false
  labels                      = local.common_labels
  depends_on                  = [google_project_service.enabled_apis]
}

# BigQuery Governance & BQML Dataset (100% Serverless — Zero AlloyDB/Cloud SQL)
resource "google_bigquery_dataset" "eulr_governance" {
  project                    = var.project_id
  dataset_id                 = "eulr_commodity_mod_governance"
  location                   = var.bq_location
  delete_contents_on_destroy = false
  labels                     = local.common_labels
  depends_on                 = [google_project_service.enabled_apis]
}

# Cloud Run v2 Service: eulr-equilibrium-gateway
resource "google_cloud_run_v2_service" "eulr_gateway" {
  project  = var.project_id
  name     = "eulr-equilibrium-gateway"
  location = var.region
  labels   = local.common_labels

  template {
    service_account = google_service_account.eulr_gateway_sa.email
    containers {
      image = var.gateway_image
      env {
        name  = "GCP_PROJECT_ID"
        value = var.project_id
      }
      env {
        name  = "GCP_REGION"
        value = var.region
      }
      env {
        name  = "GEMINI_LOCATION"
        value = var.gemini_location
      }
      env {
        name  = "GEMINI_MODEL_ID"
        value = "gemini-3.8-flash"
      }
      env {
        name  = "BIGQUERY_DATASET"
        value = google_bigquery_dataset.eulr_governance.dataset_id
      }
      env {
        name  = "GCS_SNAPSHOT_BUCKET"
        value = google_storage_bucket.eulr_snapshots.name
      }
      resources {
        limits = {
          cpu    = "2"
          memory = "2Gi"
        }
      }
    }
  }

  depends_on = [
    google_storage_bucket.eulr_snapshots,
    google_bigquery_dataset.eulr_governance,
  ]
}
