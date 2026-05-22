output "function_urls" {
  description = "URLs de las Cloud Functions"
  value       = { for k, v in google_cloudfunctions2_function.functions : k => v.service_config[0].uri }
}