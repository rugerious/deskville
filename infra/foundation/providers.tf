terraform {
  required_version = "~> 1.16.6"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "6.72.0"
    }
  }
}

provider "aws" {
  region = var.region
  default_tags {
    tags = {
      Project     = "deskville"
      Environment = "lab"
      Stack       = "foundation"
      ManagedBy   = "terraform"
    }
  }
}

# CloudFront only accepts certificates from us-east-1 (layer 7, D46).
provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"
  default_tags {
    tags = {
      Project     = "deskville"
      Environment = "lab"
      Stack       = "foundation"
      ManagedBy   = "terraform"
    }
  }
}
