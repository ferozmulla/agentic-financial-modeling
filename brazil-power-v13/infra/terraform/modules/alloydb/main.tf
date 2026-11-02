resource "google_alloydb_cluster" "governance_cluster" {
  cluster_id      = "${var.app_prefix}-alloydb"
  project         = var.project_id
  location        = var.region
  deletion_policy = "FORCE"
  labels          = var.common_labels

  network_config {
    network = var.network_self_link
  }

  initial_user {
    user     = "postgres"
    password = var.alloydb_initial_password
  }

  automated_backup_policy {
    enabled = false
  }
}

resource "google_alloydb_instance" "primary" {
  cluster       = google_alloydb_cluster.governance_cluster.name
  instance_id   = "${var.app_prefix}-alloydb-primary"
  instance_type = "PRIMARY"
  labels        = var.common_labels

  machine_config {
    cpu_count = 2
  }
}
