resource "google_cloudfunctions2_function" "functions" {
  for_each = var.cloud_functions

  name     = each.key
  location = each.value.region
  project  = var.project_id

  build_config {
    runtime     = each.value.runtime
    entry_point = each.value.entry_point

    source {
      storage_source {
        bucket = each.value.source_bucket
        object = each.value.source_object
      }
    }
  }

  service_config {
    service_account_email            = each.value.service_account_email
    available_memory                 = each.value.available_memory
    timeout_seconds                  = each.value.timeout_seconds
    max_instance_count               = each.value.max_instance_count
    max_instance_request_concurrency = each.value.max_instance_request_concurrency
    ingress_settings                 = each.value.ingress_settings
    all_traffic_on_latest_revision   = true
    environment_variables            = each.value.environment_variables
  }
}