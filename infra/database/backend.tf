# Expensive stack: switched on and off ONLY by the manual 'lab' workflow
# (or from the laptop), never by a merge.
terraform {
  backend "s3" {
    key          = "database/terraform.tfstate"
    region       = "eu-west-2"
    encrypt      = true
    use_lockfile = true
  }
}
