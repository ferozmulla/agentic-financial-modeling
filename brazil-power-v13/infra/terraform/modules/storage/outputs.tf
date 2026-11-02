output "snapshot_bucket_name" {
  value = google_storage_bucket.snapshots.name
}

output "artifacts_bucket_name" {
  value = google_storage_bucket.artifacts.name
}

output "checkpoint_topic_id" {
  value = google_pubsub_topic.checkpoint_events.id
}
