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
