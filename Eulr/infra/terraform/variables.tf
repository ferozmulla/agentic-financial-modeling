variable "project_id" {
  description = "Target Google Cloud Project ID"
  type        = string
  default     = "comm-model-mod"
}

variable "region" {
  description = "Primary GCP compute and storage region"
  type        = string
  default     = "us-central1"
}

variable "bq_location" {
  description = "BigQuery dataset location"
  type        = string
  default     = "US"
}

variable "gemini_location" {
  description = "Vertex AI Gemini endpoint location"
  type        = string
  default     = "us"
}

variable "env" {
  description = "Deployment environment label"
  type        = string
  default     = "dev"
}

variable "gateway_image" {
  description = "Container image URI for eulr-equilibrium-gateway"
  type        = string
  default     = "us-central1-docker.pkg.dev/comm-model-mod/eulr-repo/eulr-equilibrium-gateway:latest"
}
