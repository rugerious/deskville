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
