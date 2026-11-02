output "dataset_id" {
  value = google_bigquery_dataset.governance.dataset_id
}

output "remote_connection_id" {
  value = google_bigquery_connection.cloud_run_remote_fn.name
}

output "gemini_us_connection_id" {
  value = google_bigquery_connection.vertex_gemini_us.name
}
