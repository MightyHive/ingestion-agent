variable "project_id" {
  type = string
}

variable "cloud_functions" {
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