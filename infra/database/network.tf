# The VPC and subnets come from the foundation stack, found by their tags
# (no cross-stack state reads).

data "aws_vpc" "main" {
  tags = { Name = "${var.name}-vpc" }
}

data "aws_subnets" "private" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.main.id]
  }
  tags = { Tier = "private" }
}

# Database: accepts PostgreSQL only from the bastion. No egress at all
# (Terraform removes the default allow-all egress rule).
resource "aws_security_group" "db" {
  name        = "${var.name}-db"
  description = "PostgreSQL, reachable only from allowed security groups"
  vpc_id      = data.aws_vpc.main.id
  tags        = { Name = "${var.name}-db" }
}

resource "aws_vpc_security_group_ingress_rule" "db_from_bastion" {
  security_group_id            = aws_security_group.db.id
  referenced_security_group_id = aws_security_group.bastion.id
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
  description                  = "PostgreSQL from the bastion"
}

# Bastion: no inbound rules at all (access is through SSM Session Manager).
# Outbound: HTTPS for the SSM agent, and PostgreSQL to the database only.
resource "aws_security_group" "bastion" {
  name        = "${var.name}-bastion"
  description = "SSM-only bastion: no inbound"
  vpc_id      = data.aws_vpc.main.id
  tags        = { Name = "${var.name}-bastion" }
}

resource "aws_vpc_security_group_egress_rule" "bastion_https" {
  security_group_id = aws_security_group.bastion.id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
  description       = "SSM agent and AWS APIs"
}

resource "aws_vpc_security_group_egress_rule" "bastion_to_db" {
  security_group_id            = aws_security_group.bastion.id
  referenced_security_group_id = aws_security_group.db.id
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
  description                  = "PostgreSQL to the database"
}
