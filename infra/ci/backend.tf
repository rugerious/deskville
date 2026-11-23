# Bootstrap stack: applied from the laptop ONLY, never by CI.
# CI cannot create or widen its own trust.
terraform {
  backend "s3" {
    key          = "ci/terraform.tfstate"
    region       = "eu-west-2"
    encrypt      = true
    use_lockfile = true
  }
}
