output "cloud_run_gateway_uri" {
  description = "URL of the deployed eulr-equilibrium-gateway service"
  value       = google_cloud_run_v2_service.eulr_gateway.uri
}

output "bigquery_dataset_id" {
  description = "BigQuery governance & BQML dataset ID"
  value       = google_bigquery_dataset.eulr_governance.dataset_id
}

output "gcs_snapshot_bucket_name" {
  description = "Cloud Storage bucket for EULR baseline tensors and per-spreadsheet override masks"
  value       = google_storage_bucket.eulr_snapshots.name
}
