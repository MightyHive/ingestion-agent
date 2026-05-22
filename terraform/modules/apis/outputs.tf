output "enabled_apis" {
  value = {for k, v in google_project_service.apis : k => v.service}
}