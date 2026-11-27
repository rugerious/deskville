# ---------------------------------------------------------------------------
# The councils' sites (layer 7, D46): one private bucket, one CloudFront
# distribution answering wigan.<domain> and bury.<domain>, on CloudFront's Free
# flat-rate plan ($0: CDN, WAF with 5 rules incl. rate limiting, DDoS, TLS).
# The site's address chooses only how the page looks; which data a resident
# sees still comes from their token alone (D33).
# The plan subscription itself is made in the console (not in Terraform); the
# plan attaches its own web ACL, which Terraform therefore ignores. The plan
# creates its rules in Count mode: scripts/waf-enforce.py turns them to Block
# and adds a per-IP rate limit (D46).
# ---------------------------------------------------------------------------
locals {
  site_hosts = [for c in var.councils : "${c}.${var.domain_name}"]
}

# Same names as the London certificate; ACM gives one domain the same DNS
# validation record in every region, so the existing records validate this one
# too. The precondition proves it instead of assuming it.
resource "aws_acm_certificate" "cloudfront" {
  provider                  = aws.us_east_1
  domain_name               = var.domain_name
  subject_alternative_names = ["*.${var.domain_name}"]
  validation_method         = "DNS"
  key_algorithm             = "RSA_2048"

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_acm_certificate_validation" "cloudfront" {
  provider                = aws.us_east_1
  certificate_arn         = aws_acm_certificate.cloudfront.arn
  validation_record_fqdns = [for r in aws_route53_record.acm_validation : r.fqdn]

  timeouts {
    create = "20m"
  }

  lifecycle {
    precondition {
      condition = (toset([for o in aws_acm_certificate.cloudfront.domain_validation_options : o.resource_record_name]) ==
      toset([for o in aws_acm_certificate.main.domain_validation_options : o.resource_record_name]))
      error_message = "The us-east-1 certificate needs a different DNS validation record from the London one."
    }
  }
}

resource "aws_s3_bucket" "site" {
  bucket_prefix = "${var.name}-site-"
  force_destroy = true # the site is rebuilt from Git; nothing in it is unique
}

resource "aws_s3_bucket_public_access_block" "site" {
  bucket                  = aws_s3_bucket.site.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "site" {
  bucket = aws_s3_bucket.site.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "site" {
  bucket = aws_s3_bucket.site.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_cloudfront_origin_access_control" "site" {
  name                              = "${var.name}-site"
  description                       = "CloudFront signs every request to the private site bucket"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

data "aws_cloudfront_cache_policy" "optimized" {
  name = "Managed-CachingOptimized"
}

data "aws_cloudfront_response_headers_policy" "security" {
  name = "Managed-SecurityHeadersPolicy"
}

resource "aws_cloudfront_distribution" "site" {
  enabled             = true
  comment             = "Deskville council sites (unofficial demo)"
  aliases             = local.site_hosts
  default_root_object = "index.html"
  is_ipv6_enabled     = true
  http_version        = "http2and3"
  price_class         = "PriceClass_All" # set by the Free flat-rate plan, which serves from every edge location

  origin {
    origin_id                = "site-bucket"
    domain_name              = aws_s3_bucket.site.bucket_regional_domain_name
    origin_access_control_id = aws_cloudfront_origin_access_control.site.id
  }

  default_cache_behavior {
    target_origin_id           = "site-bucket"
    viewer_protocol_policy     = "redirect-to-https"
    allowed_methods            = ["GET", "HEAD"]
    cached_methods             = ["GET", "HEAD"]
    compress                   = true
    cache_policy_id            = data.aws_cloudfront_cache_policy.optimized.id
    response_headers_policy_id = data.aws_cloudfront_response_headers_policy.security.id
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    acm_certificate_arn      = aws_acm_certificate_validation.cloudfront.certificate_arn
    ssl_support_method       = "sni-only"
    minimum_protocol_version = "TLSv1.2_2021"
  }

  lifecycle {
    ignore_changes = [web_acl_id] # attached by the Free plan subscription (D46)
  }
}

# Only this distribution may read the bucket, and only over TLS.
resource "aws_s3_bucket_policy" "site" {
  bucket = aws_s3_bucket.site.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "CloudFrontOnly"
        Effect    = "Allow"
        Principal = { Service = "cloudfront.amazonaws.com" }
        Action    = "s3:GetObject"
        Resource  = "${aws_s3_bucket.site.arn}/*"
        Condition = { StringEquals = { "AWS:SourceArn" = aws_cloudfront_distribution.site.arn } }
      },
      {
        Sid       = "HttpsOnly"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:*"
        Resource  = [aws_s3_bucket.site.arn, "${aws_s3_bucket.site.arn}/*"]
        Condition = { Bool = { "aws:SecureTransport" = "false" } }
      }
    ]
  })
  depends_on = [aws_s3_bucket_public_access_block.site]
}

resource "aws_route53_record" "site" {
  for_each = toset(flatten([for h in local.site_hosts : [for t in ["A", "AAAA"] : "${h}|${t}"]]))
  zone_id  = data.aws_route53_zone.main.zone_id
  name     = split("|", each.value)[0]
  type     = split("|", each.value)[1]

  alias {
    name                   = aws_cloudfront_distribution.site.domain_name
    zone_id                = aws_cloudfront_distribution.site.hosted_zone_id
    evaluate_target_health = false
  }
}

# Sign-in for the sites: Cognito's hosted login page, authorization code + PKCE.
# The browser never sees a password field of ours and never holds a client secret.
resource "aws_cognito_user_pool_domain" "residents" {
  domain                = "${var.name}-residents"
  user_pool_id          = aws_cognito_user_pool.residents.id
  managed_login_version = 1 # classic hosted UI: the Lite tier
}
