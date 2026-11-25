# ---------------------------------------------------------------------------
# Content bucket (Layer 4, D28). Git is the source of truth; CI copies each
# council's documents here on merge. One prefix per council:
#   <tenant>/docs/           documents (synced from content/<tenant>/)
#   <tenant>/cache/titan-v2/ embeddings already computed, keyed by chunk hash
# Always-on and cheap (a few hundred KB), so it lives in foundation and
# survives the lab cycle.
#
# The name uses bucket_prefix (random suffix) instead of the account ID:
# CI logs of a public repo are public.
# ---------------------------------------------------------------------------
data "aws_caller_identity" "current" {}

locals {
  account      = data.aws_caller_identity.current.account_id
  tenants      = ["wigan", "bury"]
  boundary_arn = "arn:aws:iam::${local.account}:policy/deskville-boundary"
  titan_arn    = "arn:aws:bedrock:${var.region}::foundation-model/amazon.titan-embed-text-v2:0"
}

resource "aws_s3_bucket" "content" {
  bucket_prefix = "${var.name}-content-"
  force_destroy = false
}

resource "aws_s3_bucket_public_access_block" "content" {
  bucket                  = aws_s3_bucket.content.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "content" {
  bucket = aws_s3_bucket.content.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_versioning" "content" {
  bucket = aws_s3_bucket.content.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "content" {
  bucket = aws_s3_bucket.content.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "content" {
  bucket = aws_s3_bucket.content.id
  rule {
    id     = "expire-old-versions"
    status = "Enabled"
    filter {}
    noncurrent_version_expiration {
      noncurrent_days = 30
    }
    abort_incomplete_multipart_upload {
      days_after_initiation = 1
    }
  }
  depends_on = [aws_s3_bucket_versioning.content]
}

resource "aws_s3_bucket_policy" "content" {
  bucket = aws_s3_bucket.content.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "HttpsOnly"
      Effect    = "Deny"
      Principal = "*"
      Action    = "s3:*"
      Resource  = [aws_s3_bucket.content.arn, "${aws_s3_bucket.content.arn}/*"]
      Condition = { Bool = { "aws:SecureTransport" = "false" } }
    }]
  })
  depends_on = [aws_s3_bucket_public_access_block.content]
}

# ---------------------------------------------------------------------------
# Ingestion role with attribute-based access control (ABAC).
# It can only be assumed with a session tag tenant=<a known council>, and its
# policy only reaches ${aws:PrincipalTag/tenant}/... in the bucket. One policy
# for any number of councils; a Wigan session cannot read or list bury/.
# Today it is assumed from the laptop; in layer 5 the tag will come from the
# platform, never from the caller's request.
# ---------------------------------------------------------------------------
resource "aws_iam_role" "ingest" {
  name                 = "${var.name}-ingest"
  description          = "Ingestion for one council at a time (session tag tenant)"
  max_session_duration = 3600
  permissions_boundary = local.boundary_arn
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "OnlyWithAKnownTenantTag"
      Effect    = "Allow"
      Principal = { AWS = "arn:aws:iam::${local.account}:root" }
      Action    = ["sts:AssumeRole", "sts:TagSession"]
      Condition = {
        StringEquals                = { "aws:RequestTag/tenant" = local.tenants }
        "ForAllValues:StringEquals" = { "aws:TagKeys" = ["tenant"] }
      }
    }]
  })
}

resource "aws_iam_role_policy" "ingest" {
  name = "own-tenant-only"
  role = aws_iam_role.ingest.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "ListOwnPrefixOnly"
        Effect    = "Allow"
        Action    = "s3:ListBucket"
        Resource  = aws_s3_bucket.content.arn
        Condition = { StringLike = { "s3:prefix" = ["$${aws:PrincipalTag/tenant}/*"] } }
      },
      {
        Sid      = "ReadOwnPrefix"
        Effect   = "Allow"
        Action   = "s3:GetObject"
        Resource = "${aws_s3_bucket.content.arn}/$${aws:PrincipalTag/tenant}/*"
      },
      {
        Sid      = "WriteOwnCache"
        Effect   = "Allow"
        Action   = "s3:PutObject"
        Resource = "${aws_s3_bucket.content.arn}/$${aws:PrincipalTag/tenant}/cache/*"
      },
      {
        Sid      = "EmbedWithTitanV2"
        Effect   = "Allow"
        Action   = "bedrock:InvokeModel"
        Resource = local.titan_arn
      }
    ]
  })
}
