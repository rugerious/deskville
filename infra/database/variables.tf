variable "name" {
  type    = string
  default = "deskville"
}

variable "engine_version" {
  description = "PostgreSQL minor version (on RDS since 26 Aug 2026; >= 14 days)"
  type        = string
  default     = "18.6"
}

variable "instance_class" {
  type    = string
  default = "db.t4g.micro"
}

variable "allocated_storage_gb" {
  type    = number
  default = 20
}

# If AWS reports InsufficientInstanceCapacity, switch the AZ or the size here
# (a PR), instead of waiting for the provider to retry for an hour.
variable "bastion_az" {
  type    = string
  default = "eu-west-2a"
}

variable "bastion_instance_type" {
  type    = string
  default = "t4g.nano"
}
