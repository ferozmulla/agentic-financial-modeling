locals {
  app_prefix = "eulr-sheets-mod"

  common_labels = {
    env         = var.env
    app         = "eulr-sheets-mod"
    owner       = "quant-platform"
    cost-center = "commodities-r-and-d"
  }

  required_apis = [
    "run.googleapis.com",
    "bigquery.googleapis.com",
    "bigqueryconnection.googleapis.com",
    "aiplatform.googleapis.com",
    "storage.googleapis.com",
    "artifactregistry.googleapis.com",
    "cloudbuild.googleapis.com",
  ]
}
