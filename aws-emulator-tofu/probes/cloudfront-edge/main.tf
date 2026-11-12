# Echo API behind CloudFront with the edge features a real deployment would use.
data "archive_file" "fn" {
  type        = "zip"
  output_path = "${path.module}/build/fn.zip"
  source {
    filename = "app.py"
    content  = <<-PY
      import json, uuid
      def handler(e, c):
          return {"statusCode": 200,
                  "headers": {"Content-Type": "text/x-probe", "Cache-Control": "max-age=60", "X-Origin-Header": "kept"},
                  "body": json.dumps({"nonce": str(uuid.uuid4()), "path": e.get("path"),
                                      "query": e.get("queryStringParameters"),
                                      "headers": {k.lower(): v for k, v in (e.get("headers") or {}).items()}})}
    PY
  }
}
resource "aws_iam_role" "r" {
  name               = "probe-cf-echo"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}
resource "aws_lambda_function" "f" {
  function_name    = "probe-cf-echo"
  role             = aws_iam_role.r.arn
  runtime          = "python3.12"
  handler          = "app.handler"
  filename         = data.archive_file.fn.output_path
  source_code_hash = data.archive_file.fn.output_base64sha256
}
resource "aws_api_gateway_rest_api" "a" { name = "probe-cf-echo" }
resource "aws_api_gateway_resource" "p" {
  rest_api_id = aws_api_gateway_rest_api.a.id
  parent_id   = aws_api_gateway_rest_api.a.root_resource_id
  path_part   = "{proxy+}"
}
resource "aws_api_gateway_method" "m" {
  rest_api_id   = aws_api_gateway_rest_api.a.id
  resource_id   = aws_api_gateway_resource.p.id
  http_method   = "ANY"
  authorization = "NONE"
}
resource "aws_api_gateway_integration" "i" {
  rest_api_id             = aws_api_gateway_rest_api.a.id
  resource_id             = aws_api_gateway_resource.p.id
  http_method             = aws_api_gateway_method.m.http_method
  type                    = "AWS_PROXY"
  integration_http_method = "POST"
  uri                     = aws_lambda_function.f.invoke_arn
}
resource "aws_api_gateway_deployment" "d" {
  rest_api_id = aws_api_gateway_rest_api.a.id
  depends_on  = [aws_api_gateway_integration.i]
}
resource "aws_api_gateway_stage" "s" {
  rest_api_id   = aws_api_gateway_rest_api.a.id
  deployment_id = aws_api_gateway_deployment.d.id
  stage_name    = "prod"
}
resource "aws_lambda_permission" "p" {
  statement_id  = "apigw"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.f.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "arn:aws:execute-api:us-east-1:${local.account_id}:${aws_api_gateway_rest_api.a.id}/*/*"
}

resource "aws_cloudfront_function" "addhdr" {
  name    = "probe-add-header"
  runtime = "cloudfront-js-2.0"
  publish = true
  code    = <<-JS
    function handler(event) {
      event.request.headers['x-cf-function'] = { value: 'ran' };
      return event.request;
    }
  JS
}
resource "aws_cloudfront_response_headers_policy" "rhp" {
  name = "probe-rhp"
  custom_headers_config {
    items {
      header   = "X-Probe-RHP"
      value    = "added"
      override = true
    }
  }
}
resource "aws_cloudfront_cache_policy" "cache60" {
  name        = "probe-cache60"
  min_ttl     = 0
  default_ttl = 60
  max_ttl     = 300
  parameters_in_cache_key_and_forwarded_to_origin {
    headers_config { header_behavior = "none" }
    query_strings_config { query_string_behavior = "all" }
    cookies_config { cookie_behavior = "none" }
  }
}
resource "aws_cloudfront_origin_request_policy" "orp" {
  name = "probe-orp"
  headers_config {
    header_behavior = "whitelist"
    headers { items = ["X-Custom", "Authorization"] }
  }
  query_strings_config { query_string_behavior = "all" }
  cookies_config { cookie_behavior = "none" }
}
resource "aws_wafv2_web_acl" "w" {
  name  = "probe-waf"
  scope = "CLOUDFRONT"
  default_action {
    allow {}
  }
  rule {
    name     = "block-blocked-path"
    priority = 1
    action {
      block {}
    }
    statement {
      byte_match_statement {
        search_string         = "/blocked"
        positional_constraint = "STARTS_WITH"
        field_to_match {
          uri_path {}
        }
        text_transformation {
          priority = 0
          type     = "NONE"
        }
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = false
      metric_name                = "blocked"
      sampled_requests_enabled   = false
    }
  }
  visibility_config {
    cloudwatch_metrics_enabled = false
    metric_name                = "probe-waf"
    sampled_requests_enabled   = false
  }
}
resource "aws_cloudfront_distribution" "d" {
  enabled    = true
  web_acl_id = aws_wafv2_web_acl.w.arn
  origin {
    origin_id   = "api"
    domain_name = "${aws_api_gateway_rest_api.a.id}.execute-api.us-east-1.amazonaws.com"
    origin_path = "/prod"
    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "https-only"
      origin_ssl_protocols   = ["TLSv1.2"]
    }
  }
  default_cache_behavior {
    target_origin_id           = "api"
    viewer_protocol_policy     = "redirect-to-https"
    allowed_methods            = ["GET", "HEAD", "OPTIONS"]
    cached_methods             = ["GET", "HEAD"]
    cache_policy_id            = aws_cloudfront_cache_policy.cache60.id
    origin_request_policy_id   = aws_cloudfront_origin_request_policy.orp.id
    response_headers_policy_id = aws_cloudfront_response_headers_policy.rhp.id
    function_association {
      event_type   = "viewer-request"
      function_arn = aws_cloudfront_function.addhdr.arn
    }
  }
  restrictions {
    geo_restriction { restriction_type = "none" }
  }
  viewer_certificate { cloudfront_default_certificate = true }
}
output "id" { value = aws_cloudfront_distribution.d.id }
output "domain" { value = aws_cloudfront_distribution.d.domain_name }
