terraform {
  required_version = ">= 1.15"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

provider "google" {
    project = var.project_id
    region = var.region
}

module "apis" {
    source = "./modules/apis"
    project_id = var.project_id
}

module "iam" {
    source = "./modules/iam"
    project_id = var.project_id
}