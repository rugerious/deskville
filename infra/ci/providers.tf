terraform {
  required_version = "~> 1.16.6"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "6.73.0"
    }
  }
}

provider "aws" {
  region = "eu-west-2"
  default_tags {
    tags = {
      Project     = "deskville"
      Environment = "lab"
      Stack       = "ci"
      ManagedBy   = "terraform"
    }
  }
}
