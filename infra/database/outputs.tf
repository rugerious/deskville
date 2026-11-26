output "db_address" {
  value = aws_db_instance.main.address
}

output "db_port" {
  value = aws_db_instance.main.port
}

output "db_name" {
  value = aws_db_instance.main.db_name
}

output "db_master_username" {
  value = aws_db_instance.main.username
}

# The ARN of the secret, never its value.
output "db_master_secret_arn" {
  value = aws_db_instance.main.master_user_secret[0].secret_arn
}

output "bastion_instance_id" {
  value = aws_instance.bastion.id
}

output "api_url" {
  value = "https://${local.api_host}"
}

output "api_image" {
  description = "The image digest the API tasks run"
  value       = data.aws_ecr_image.api.image_digest
}
