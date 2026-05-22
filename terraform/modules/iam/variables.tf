variable "project_id" {
  type        = string
  description = "GCP project ID"
}

variable "service_accounts" {
  type = map(object({
    display_name = string
    sa_description = optional(string, "")
    roles        = list(string)
  }))
  default = {}
}