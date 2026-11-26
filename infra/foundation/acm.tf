# ---------------------------------------------------------------------------
# TLS certificate for every Deskville host (layer 5.4, D33, D38): the domain
# and *.domain (api., wigan., bury. ...), validated through DNS in the hosted
# zone, which Terraform only reads. Free and always on, so it lives here and
# survives the lab cycle; the load balancer that uses it is in the lab stack.
# ---------------------------------------------------------------------------
data "aws_route53_zone" "main" {
  name         = var.domain_name
  private_zone = false
}

resource "aws_acm_certificate" "main" {
  domain_name               = var.domain_name
  subject_alternative_names = ["*.${var.domain_name}"]
  validation_method         = "DNS"
  key_algorithm             = "RSA_2048"

  lifecycle {
    create_before_destroy = true
  }
}

# The domain and its wildcard share one validation record, hence allow_overwrite.
resource "aws_route53_record" "acm_validation" {
  for_each = {
    for o in aws_acm_certificate.main.domain_validation_options : o.domain_name => {
      name   = o.resource_record_name
      type   = o.resource_record_type
      record = o.resource_record_value
    }
  }
  zone_id         = data.aws_route53_zone.main.zone_id
  name            = each.value.name
  type            = each.value.type
  records         = [each.value.record]
  ttl             = 300
  allow_overwrite = true
}

resource "aws_acm_certificate_validation" "main" {
  certificate_arn         = aws_acm_certificate.main.arn
  validation_record_fqdns = [for r in aws_route53_record.acm_validation : r.fqdn]
}
