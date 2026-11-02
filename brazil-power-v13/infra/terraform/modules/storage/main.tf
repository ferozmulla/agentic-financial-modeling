resource "google_storage_bucket" "snapshots" {
  name                        = "${var.project_id}-sheets-mod-snapshots"
  project                     = var.project_id
  location                    = var.region
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  force_destroy               = true
  labels                      = var.common_labels

  versioning {
    enabled = true
  }
}

resource "google_storage_bucket" "artifacts" {
  name                        = "${var.project_id}-sheets-mod-artifacts"
  project                     = var.project_id
  location                    = var.region
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  force_destroy               = true
  labels                      = var.common_labels
}

resource "google_pubsub_topic" "checkpoint_events" {
  name    = "${var.app_prefix}-checkpoint-events"
  project = var.project_id
  labels  = var.common_labels
}

resource "google_pubsub_topic" "realtime_edit_events" {
  name    = "${var.app_prefix}-realtime-edit-events"
  project = var.project_id
  labels  = var.common_labels
}
