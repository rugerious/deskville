resource "aws_db_subnet_group" "main" {
  name       = "${var.name}-db"
  subnet_ids = data.aws_subnets.private.ids
}

resource "aws_db_parameter_group" "pg18" {
  name   = "${var.name}-pg18"
  family = "postgres18"

  parameter {
    name         = "rds.force_ssl"
    value        = "1"
    apply_method = "pending-reboot" # what RDS records for this parameter; without it every plan shows a diff
  }
}

resource "aws_db_instance" "main" {
  identifier     = "${var.name}-db"
  engine         = "postgres"
  engine_version = var.engine_version
  instance_class = var.instance_class

  allocated_storage = var.allocated_storage_gb
  storage_type      = "gp3"
  storage_encrypted = true

  db_name  = "deskville"
  username = "deskville_admin"
  # RDS creates and keeps the password in Secrets Manager.
  # Terraform never sees it, so it never reaches the state.
  manage_master_user_password = true

  # The application role has no password at all: it logs in with a 15-minute
  # token signed by its IAM role (requires SSL, which is forced).
  iam_database_authentication_enabled = true

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.db.id]
  parameter_group_name   = aws_db_parameter_group.pg18.name
  publicly_accessible    = false
  multi_az               = false

  # Lab with an up/down routine: nothing to keep between sessions.
  backup_retention_period    = 1
  skip_final_snapshot        = true
  deletion_protection        = false
  auto_minor_version_upgrade = false
  apply_immediately          = true
  copy_tags_to_snapshot      = true

  performance_insights_enabled = false
  monitoring_interval          = 0
}
