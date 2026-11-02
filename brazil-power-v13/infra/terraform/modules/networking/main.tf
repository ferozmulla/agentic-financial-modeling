resource "google_compute_network" "vpc" {
  name                    = "${var.app_prefix}-vpc"
  project                 = var.project_id
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "primary" {
  name                     = "${var.app_prefix}-subnet-${var.region}"
  project                  = var.project_id
  region                   = var.region
  network                  = google_compute_network.vpc.id
  ip_cidr_range            = "10.24.0.0/20"
  private_ip_google_access = true
}

resource "google_compute_global_address" "private_ip_alloc" {
  name          = "${var.app_prefix}-psa-range"
  project       = var.project_id
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = 16
  network       = google_compute_network.vpc.id
  labels        = var.common_labels
}

resource "google_service_networking_connection" "private_vpc_connection" {
  network                 = google_compute_network.vpc.id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.private_ip_alloc.name]
  deletion_policy         = "ABANDON"
}

resource "google_vpc_access_connector" "serverless_connector" {
  name          = "sheets-mod-vpc-conn"
  project       = var.project_id
  region        = var.region
  network       = google_compute_network.vpc.name
  ip_cidr_range = "10.25.0.0/28"
}
