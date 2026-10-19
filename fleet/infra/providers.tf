# Credentials come from the environment (AWS_PROFILE, SSO, access keys, ...).
provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project   = "open-lutra"
      ManagedBy = "terraform"
    }
  }
}
