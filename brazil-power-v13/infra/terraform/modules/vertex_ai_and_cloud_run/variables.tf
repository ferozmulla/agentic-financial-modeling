variable "project_id" {
  type = string
}

variable "region" {
  type = string
}

variable "gemini_location" {
  type = string
}

variable "gemini_api_endpoint" {
  type = string
}

variable "app_prefix" {
  type = string
}

variable "common_labels" {
  type = map(string)
}

variable "vpc_connector_id" {
  type = string
}

variable "gateway_sa_email" {
  type = string
}

variable "vertex_sa_email" {
  type = string
}

variable "snapshot_bucket_name" {
  type = string
}

variable "artifacts_bucket_name" {
  type = string
}
