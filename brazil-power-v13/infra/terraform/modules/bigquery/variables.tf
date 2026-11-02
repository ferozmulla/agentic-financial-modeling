variable "project_id" {
  type = string
}

variable "bq_location" {
  type = string
}

variable "gemini_location" {
  type = string
}

variable "app_prefix" {
  type = string
}

variable "common_labels" {
  type = map(string)
}

variable "cloud_run_gateway_uri" {
  type = string
}
