variable "project_id" {
  type        = string
  description = "GCP project ID"
}

variable "service_accounts" {
  type = map(object({
    display_name = string
    roles        = list(string)
  }))
  description = "Service accounts and their roles"
  default = {}
}