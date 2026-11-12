# One CloudFront distribution in front of all service APIs; path behaviour /<service>/* -> API.
terraform {
  required_providers {
    aws = { source = "hashicorp/aws" }
  }
}

variable "name" { type = string }
variable "region" { type = string }
variable "apis" {
  type = map(object({ id = string, stage = string }))
}
variable "default_api" { type = string }

# Forward the bearer token and all query strings. On AWS the Authorization header reaches the
# origin only if it is part of the cache key, which also makes cached responses per-token (safe).
# TTLs: default 0 (honour origin Cache-Control), so authenticated responses aren't shared.
resource "aws_cloudfront_cache_policy" "api" {
  name        = "${var.name}-api-token-keyed"
  min_ttl     = 0
  default_ttl = 0
  max_ttl     = 3600
  parameters_in_cache_key_and_forwarded_to_origin {
    enable_accept_encoding_gzip   = true
    enable_accept_encoding_brotli = true
    headers_config {
      header_behavior = "whitelist"
      headers {
        items = ["Authorization", "X-Auth-Token"]
      }
    }
    query_strings_config {
      query_string_behavior = "all"
    }
    cookies_config {
      cookie_behavior = "none"
    }
  }
}

locals {
  origin_id = { for k, _ in var.apis : k => "api-${k}" }
}

resource "aws_cloudfront_distribution" "this" {
  enabled         = true
  comment         = "${var.name} authenticated geospatial APIs"
  is_ipv6_enabled = true
  price_class     = "PriceClass_100"

  dynamic "origin" {
    for_each = var.apis
    content {
      origin_id   = local.origin_id[origin.key]
      domain_name = "${origin.value.id}.execute-api.${var.region}.amazonaws.com"
      origin_path = "/${origin.value.stage}"
      custom_origin_config {
        http_port              = 80
        https_port             = 443
        origin_protocol_policy = "https-only"
        origin_ssl_protocols   = ["TLSv1.2"]
      }
    }
  }

  default_cache_behavior {
    target_origin_id       = local.origin_id[var.default_api]
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"]
    cached_methods         = ["GET", "HEAD"]
    cache_policy_id        = aws_cloudfront_cache_policy.api.id
    compress               = true
  }

  dynamic "ordered_cache_behavior" {
    for_each = var.apis
    content {
      path_pattern           = "/${ordered_cache_behavior.key}/*"
      target_origin_id       = local.origin_id[ordered_cache_behavior.key]
      viewer_protocol_policy = "redirect-to-https"
      allowed_methods        = ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"]
      cached_methods         = ["GET", "HEAD"]
      cache_policy_id        = aws_cloudfront_cache_policy.api.id
      compress               = true
    }
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }
}

output "distribution_id" { value = aws_cloudfront_distribution.this.id }
output "domain_name" { value = aws_cloudfront_distribution.this.domain_name }
