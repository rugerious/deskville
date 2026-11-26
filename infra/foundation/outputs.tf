output "vpc_id" {
  value = aws_vpc.main.id
}

output "public_subnet_ids" {
  value = aws_subnet.public[*].id
}

output "private_subnet_ids" {
  value = aws_subnet.private[*].id
}

output "availability_zones" {
  value = local.azs
}

output "content_bucket" {
  description = "Content bucket (random suffix, no account ID)"
  value       = aws_s3_bucket.content.bucket
}

output "ingest_role_arn" {
  description = "Assume with a session tag tenant=<council>"
  value       = aws_iam_role.ingest.arn
}

output "api_repository_name" {
  value = aws_ecr_repository.api.name
}

output "cognito_user_pool_id" {
  value = aws_cognito_user_pool.residents.id
}

output "cognito_app_client_id" {
  value = aws_cognito_user_pool_client.web.id
}

output "domain_name" {
  value = var.domain_name
}

output "guardrail_id" {
  value = aws_bedrock_guardrail.residents.guardrail_id
}

output "guardrail_version" {
  value = aws_bedrock_guardrail_version.residents.version
}
