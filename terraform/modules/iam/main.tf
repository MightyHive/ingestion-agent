resource "google_service_account" "service_accounts" {
    for_each = var.service_accounts
    account_id = each.key
    display_name = each.value.display_name
    description = each.value.sa_description
    project = var.project_id
}


resource "google_project_iam_member" "sa_roles" {
  for_each = {
    for pair in flatten([
      for sa_key, sa in var.service_accounts : [
        for role in sa.roles : {
          key  = "${sa_key}__${replace(role, "/", "_")}"
          role = role
          sa   = "${sa_key}@${var.project_id}.iam.gserviceaccount.com"
        }
      ]
    ]) : pair.key => pair
  }
  project = var.project_id
  role    = each.value.role
  member = "serviceAccount:${each.value.sa}"
}