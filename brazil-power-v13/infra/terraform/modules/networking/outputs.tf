output "vpc_self_link" {
  value = google_compute_network.vpc.self_link
}

output "private_vpc_connection_id" {
  value = google_service_networking_connection.private_vpc_connection.id
}

output "serverless_vpc_connector_id" {
  value = google_vpc_access_connector.serverless_connector.id
}
