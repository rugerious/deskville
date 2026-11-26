variable "region" {
  type    = string
  default = "eu-west-2"
}

variable "name" {
  description = "Prefix for resource names"
  type        = string
  default     = "deskville"
}

variable "vpc_cidr" {
  type    = string
  default = "10.20.0.0/16"
}

variable "budget_limit_usd" {
  description = "Monthly cost alarm for Project=deskville, in USD"
  type        = number
  default     = 10
}

variable "alert_email" {
  description = "Where budget alerts go (must be a verified budget recipient)"
  type        = string
}

variable "domain_name" {
  description = "The project's domain; its Route 53 hosted zone is created by hand (D33)"
  type        = string
  default     = "deskville.co.uk"
}
