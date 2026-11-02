resource "google_artifact_registry_repository" "containers" {
  repository_id = "${var.app_prefix}-repo"
  project       = var.project_id
  location      = var.region
  format        = "DOCKER"
  labels        = var.common_labels
}

resource "google_vertex_ai_endpoint" "solver_endpoint" {
  name         = "sheets-solver-ep"
  display_name = "${var.app_prefix}-solver-ep"
  project      = var.project_id
  location     = var.region
  labels       = var.common_labels

  # INFRA-04: Undeploy all models before endpoint destruction so terraform destroy succeeds cleanly
  provisioner "local-exec" {
    when    = destroy
    command = <<-EOT
      for dm in $(gcloud ai endpoints describe ${self.name} --project=${self.project} --region=${self.location} --format="value(deployedModels.id)" 2>/dev/null); do
        gcloud ai endpoints undeploy-model ${self.name} --project=${self.project} --region=${self.location} --deployed-model-id="$dm" --quiet || true
      done
    EOT
  }
}

resource "google_cloud_run_v2_service" "gateway" {
  name                = "${var.app_prefix}-gateway"
  project             = var.project_id
  location            = var.region
  deletion_protection = false
  labels              = var.common_labels

  template {
    service_account = var.gateway_sa_email

    vpc_access {
      connector = var.vpc_connector_id
      egress    = "PRIVATE_RANGES_ONLY"
    }

    containers {
      image = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.containers.repository_id}/gateway:latest"

      env {
        name  = "ENV"
        value = "gcp"
      }
      env {
        name  = "GCP_PROJECT_ID"
        value = var.project_id
      }
      env {
        name  = "GCP_REGION"
        value = var.region
      }
      env {
        name  = "BQ_LOCATION"
        value = var.region
      }
      env {
        name  = "GEMINI_LOCATION"
        value = var.gemini_location
      }
      env {
        name  = "GEMINI_API_ENDPOINT"
        value = var.gemini_api_endpoint
      }
      env {
        name  = "GCS_SNAPSHOT_BUCKET"
        value = var.snapshot_bucket_name
      }
      env {
        name  = "GCS_ARTIFACTS_BUCKET"
        value = var.artifacts_bucket_name
      }
      env {
        name  = "VERTEX_ENDPOINT_ID"
        value = google_vertex_ai_endpoint.solver_endpoint.name
      }
    }
  }
}
