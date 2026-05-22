terraform {
  required_version = ">= 1.15"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }

  backend "gcs" {
    bucket = "monks-mds-tfstate"
    prefix = "terraform/state"
  }
}

provider "google" {
    project = var.project_id
    region = var.region
}

module "apis" {
    source = "../../modules/apis"
    project_id = var.project_id
    apis = var.apis
}

module "iam" {
    source = "../../modules/iam"
    project_id = var.project_id
    service_accounts = var.service_accounts
}

# module "storage" {
#     source = "./../modules/storage"
#     project_id = var.project_id
# }

module "cloud_functions" {
  source = "../../modules/cloud_functions"
  project_id = var.project_id
  cloud_functions=var.cloud_functions
}

# module "bigquery" {
#   source = "../../modules/bigquery"
#   project_id = var.project_id
# }

