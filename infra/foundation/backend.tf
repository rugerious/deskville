# The bucket name lives in backend.hcl (not committed). See backend.hcl.example.
terraform {
  backend "s3" {
    key          = "foundation/terraform.tfstate"
    region       = "eu-west-2"
    encrypt      = true
    use_lockfile = true # native S3 locking, no DynamoDB table needed
  }
}
