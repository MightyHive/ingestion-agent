variable "project_id" {
  type = string
}

variable "region" {
  type = string
  default = "us-central1"
}

variable "apis" {
  type = list(string)
  default = []
}

variable "service_accounts" {
  type = map(object({
    display_name = string
    roles        = list(string)
    sa_description = optional(string, "")
  }))
  default = {}
}

variable "cloud_functions" {
  description = "Map of Cloud Functions v2 to deploy"
  type = map(object({
    region      = string
    runtime     = string
    entry_point = string

    source_bucket = string
    source_object = string

    service_account_email = string

    available_memory                 = string
    timeout_seconds                  = number
    max_instance_count               = number
    max_instance_request_concurrency = number
    ingress_settings                 = string

    environment_variables = map(string)
  }))
  default = {}
}