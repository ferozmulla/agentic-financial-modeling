output "gateway_sa_email" {
  value = google_service_account.gateway_sa.email
}

output "vertex_solver_sa_email" {
  value = google_service_account.vertex_solver_sa.email
}

output "bq_remote_fn_sa_email" {
  value = google_service_account.bq_remote_fn_sa.email
}
