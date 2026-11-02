# Enable required Google Cloud APIs non-destructively (INFRA-06: disable_on_destroy = false)
resource "google_project_service" "enabled_apis" {
  for_each           = toset(local.required_apis)
  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}

module "networking" {
  source        = "./modules/networking"
  project_id    = var.project_id
  region        = var.region
  app_prefix    = local.app_prefix
  common_labels = local.common_labels
  depends_on    = [google_project_service.enabled_apis]
}

module "iam" {
  source     = "./modules/iam"
  project_id = var.project_id
  app_prefix = local.app_prefix
  depends_on = [google_project_service.enabled_apis]
}

module "storage" {
  source        = "./modules/storage"
  project_id    = var.project_id
  region        = var.region
  app_prefix    = local.app_prefix
  common_labels = local.common_labels
  depends_on    = [google_project_service.enabled_apis]
}

module "alloydb" {
  source                   = "./modules/alloydb"
  project_id               = var.project_id
  region                   = var.region
  zone                     = var.zone
  app_prefix               = local.app_prefix
  common_labels            = local.common_labels
  network_self_link        = module.networking.vpc_self_link
  psa_connection_id        = module.networking.private_vpc_connection_id
  alloydb_initial_password = var.alloydb_initial_password
  depends_on               = [module.networking]
}

module "vertex_ai_and_cloud_run" {
  source                = "./modules/vertex_ai_and_cloud_run"
  project_id            = var.project_id
  region                = var.region
  gemini_location       = var.gemini_location
  gemini_api_endpoint   = local.gemini_api_endpoint
  app_prefix            = local.app_prefix
  common_labels         = local.common_labels
  vpc_connector_id      = module.networking.serverless_vpc_connector_id
  gateway_sa_email      = module.iam.gateway_sa_email
  vertex_sa_email       = module.iam.vertex_solver_sa_email
  snapshot_bucket_name  = module.storage.snapshot_bucket_name
  artifacts_bucket_name = module.storage.artifacts_bucket_name
  depends_on            = [module.networking, module.iam, module.storage]
}

module "bigquery" {
  source                = "./modules/bigquery"
  project_id            = var.project_id
  bq_location           = var.bq_location
  gemini_location       = var.gemini_location
  app_prefix            = local.app_prefix
  common_labels         = local.common_labels
  cloud_run_gateway_uri = module.vertex_ai_and_cloud_run.gateway_service_uri
  depends_on            = [module.vertex_ai_and_cloud_run]
}
