variable "project_id" {
  type = string
}

variable "region" {
  type = string
}

variable "zone" {
  type = string
}

variable "app_prefix" {
  type = string
}

variable "common_labels" {
  type = map(string)
}

variable "network_self_link" {
  type = string
}

variable "psa_connection_id" {
  type = string
}

variable "alloydb_initial_password" {
  type      = string
  sensitive = true
}
