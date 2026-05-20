output "enabled_apis" {
  value = keys(google_project_service.apis)
}