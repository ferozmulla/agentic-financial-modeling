output "gateway_service_uri" {
  value = google_cloud_run_v2_service.gateway.uri
}

output "vertex_endpoint_id" {
  value = google_vertex_ai_endpoint.solver_endpoint.name
}

output "artifact_registry_id" {
  value = google_artifact_registry_repository.containers.id
}
