variable "project_id" {
  description = "Existing Google Cloud Project ID (shared project isolation INFRA-06)"
  type        = string
  default     = "comm-model-mod"
}

variable "region" {
  description = "Primary GCP compute and storage region (us-central1)"
  type        = string
  default     = "us-central1"
}

variable "zone" {
  description = "Primary GCP compute zone (us-central1-a)"
  type        = string
  default     = "us-central1-a"
}

variable "bq_location" {
  description = "BigQuery dataset and remote connection location (us-central1)"
  type        = string
  default     = "us-central1"
}

variable "gemini_location" {
  description = "US multi-region endpoint for Gemini LLMs (us-aiplatform.googleapis.com)"
  type        = string
  default     = "us"
}

variable "environment" {
  description = "Deployment environment tag"
  type        = string
  default     = "mvp"
}

variable "alloydb_initial_password" {
  description = "Initial password for AlloyDB postgres superuser (injected via TF_VAR_alloydb_initial_password)"
  type        = string
  sensitive   = true
  default     = "CHANGE_ME_VIA_SECRET_MANAGER"
}
