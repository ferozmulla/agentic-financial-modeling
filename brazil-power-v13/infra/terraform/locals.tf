locals {
  app_prefix = "sheets-commodity-mod"

  common_labels = {
    app        = "sheets-commodity-mod"
    project    = "enterprise-commodity-modernization"
    env        = var.environment
    managed-by = "terraform"
  }

  gemini_api_endpoint = "${var.gemini_location}-aiplatform.googleapis.com"

  required_apis = [
    "aiplatform.googleapis.com",
    "alloydb.googleapis.com",
    "artifactregistry.googleapis.com",
    "bigquery.googleapis.com",
    "bigqueryconnection.googleapis.com",
    "cloudkms.googleapis.com",
    "compute.googleapis.com",
    "iam.googleapis.com",
    "pubsub.googleapis.com",
    "run.googleapis.com",
    "secretmanager.googleapis.com",
    "servicenetworking.googleapis.com",
    "sheets.googleapis.com",
    "storage.googleapis.com",
    "vpcaccess.googleapis.com",
  ]
}
