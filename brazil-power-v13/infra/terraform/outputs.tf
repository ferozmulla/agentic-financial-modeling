output "project_id" {
  description = "Target GCP Project ID"
  value       = var.project_id
}

output "region" {
  description = "Primary GCP service region"
  value       = var.region
}

output "gemini_location" {
  description = "US multi-region endpoint location for Gemini LLMs"
  value       = var.gemini_location
}

output "gemini_api_endpoint" {
  description = "Vertex AI US multi-region endpoint hostname for Gemini models"
  value       = local.gemini_api_endpoint
}

output "gateway_service_uri" {
  description = "Cloud Run Gateway HTTPS URL"
  value       = module.vertex_ai_and_cloud_run.gateway_service_uri
}

output "vertex_endpoint_id" {
  description = "Vertex AI Custom Prediction Endpoint ID"
  value       = module.vertex_ai_and_cloud_run.vertex_endpoint_id
}

output "snapshot_bucket_name" {
  description = "GCS immutable workbook snapshot bucket"
  value       = module.storage.snapshot_bucket_name
}

output "bigquery_dataset_id" {
  description = "BigQuery governance & BQML dataset ID"
  value       = module.bigquery.dataset_id
}
