variable "project_id" {
  type        = string
  description = "GCP project ID"
}

variable "apis" {
  type        = list(string)
  description = "Lista de APIs a habilitar"
}