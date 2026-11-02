output "cluster_id" {
  value = google_alloydb_cluster.governance_cluster.id
}

output "primary_instance_ip" {
  value = google_alloydb_instance.primary.ip_address
}
