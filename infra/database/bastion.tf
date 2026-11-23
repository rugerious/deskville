# A tiny SSM-only bastion: the only way into a database that has no route to
# the internet. No SSH, no inbound ports; port-forwarding through Session Manager.

data "aws_caller_identity" "current" {}

data "aws_ssm_parameter" "al2023_arm64" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-arm64"
}

# One public subnet, chosen by AZ on purpose. ids[0] of a list has no guaranteed
# order: on 23 Nov it landed in eu-west-2b, which had no t4g.nano capacity.
data "aws_subnet" "bastion" {
  vpc_id            = data.aws_vpc.main.id
  availability_zone = var.bastion_az
  tags              = { Tier = "public" }
}

locals {
  boundary_arn = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:policy/deskville-boundary"
}

resource "aws_iam_role" "bastion" {
  name                 = "${var.name}-bastion"
  description          = "SSM Session Manager for the database bastion"
  permissions_boundary = local.boundary_arn
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "bastion_ssm" {
  role       = aws_iam_role.bastion.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_instance_profile" "bastion" {
  name = "${var.name}-bastion"
  role = aws_iam_role.bastion.name
}

resource "aws_instance" "bastion" {
  # SSM parameter values are marked sensitive by the provider; an AMI ID is public.
  ami                         = nonsensitive(data.aws_ssm_parameter.al2023_arm64.value)
  instance_type               = var.bastion_instance_type
  subnet_id                   = data.aws_subnet.bastion.id
  vpc_security_group_ids      = [aws_security_group.bastion.id]
  iam_instance_profile        = aws_iam_instance_profile.bastion.name
  associate_public_ip_address = true # the SSM agent needs a way out; there is no NAT

  metadata_options {
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
  }

  root_block_device {
    volume_type = "gp3"
    encrypted   = true
  }

  tags = { Name = "${var.name}-bastion" }

  lifecycle {
    ignore_changes = [ami]
  }
}
