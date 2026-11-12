# One REST API for one service, rooted at /<service>:
#   /<service>/<public_path>   -> Lambda, no auth      (e.g. /auth/token)
#   /<service>, /<service>/{proxy+} -> Lambda, shared Lambda REQUEST authorizer
# Adding a future API = one more instance of this module (+ a CloudFront behaviour). Its path
# prefix becomes the permission name; admin ("*") already covers it.
terraform {
  required_providers {
    aws = { source = "hashicorp/aws" }
  }
}

variable "name" { type = string }
variable "service" { type = string }
variable "public_paths" {
  type    = list(string)
  default = []
}
variable "function_name" { type = string }
variable "function_invoke_arn" { type = string }
variable "authorizer_function_name" { type = string }
variable "authorizer_invoke_arn" { type = string }
variable "authorizer_ttl" { type = number }
variable "authorizer_identity_source" { type = string }
variable "region" { type = string }
variable "account_id" { type = string }
variable "stage_name" {
  type    = string
  default = "prod"
}

resource "aws_api_gateway_rest_api" "this" {
  name               = var.name
  description        = "${var.service} API (Lambda proxy, Cognito-JWT Lambda authorizer)"
  binary_media_types = ["*/*"] # pass PNG tiles through; avoids Accept-header dependent behaviour
  endpoint_configuration {
    types = ["REGIONAL"]
  }
}

locals {
  # Built explicitly: the provider's execution_arn has an empty account id when
  # skip_requesting_account_id = true (needed on aws-emulator, see providers.tf).
  execution_arn = "arn:aws:execute-api:${var.region}:${var.account_id}:${aws_api_gateway_rest_api.this.id}"
}

resource "aws_api_gateway_authorizer" "jwt" {
  name                             = "${var.name}-jwt"
  rest_api_id                      = aws_api_gateway_rest_api.this.id
  type                             = "REQUEST"
  authorizer_uri                   = var.authorizer_invoke_arn
  identity_source                  = var.authorizer_identity_source
  authorizer_result_ttl_in_seconds = var.authorizer_ttl
}

resource "aws_lambda_permission" "authorizer" {
  statement_id  = "apigw-authorizer-${aws_api_gateway_rest_api.this.id}"
  action        = "lambda:InvokeFunction"
  function_name = var.authorizer_function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${local.execution_arn}/authorizers/${aws_api_gateway_authorizer.jwt.id}"
}

resource "aws_lambda_permission" "backend" {
  statement_id  = "apigw-${aws_api_gateway_rest_api.this.id}"
  action        = "lambda:InvokeFunction"
  function_name = var.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${local.execution_arn}/*/*"
}

resource "aws_api_gateway_resource" "root" {
  rest_api_id = aws_api_gateway_rest_api.this.id
  parent_id   = aws_api_gateway_rest_api.this.root_resource_id
  path_part   = var.service
}

resource "aws_api_gateway_resource" "proxy" {
  rest_api_id = aws_api_gateway_rest_api.this.id
  parent_id   = aws_api_gateway_resource.root.id
  path_part   = "{proxy+}"
}

resource "aws_api_gateway_resource" "public" {
  for_each    = toset(var.public_paths)
  rest_api_id = aws_api_gateway_rest_api.this.id
  parent_id   = aws_api_gateway_resource.root.id
  path_part   = each.value
}

locals {
  protected = {
    root  = aws_api_gateway_resource.root.id
    proxy = aws_api_gateway_resource.proxy.id
  }
}

resource "aws_api_gateway_method" "protected" {
  for_each      = local.protected
  rest_api_id   = aws_api_gateway_rest_api.this.id
  resource_id   = each.value
  http_method   = "ANY"
  authorization = "CUSTOM"
  authorizer_id = aws_api_gateway_authorizer.jwt.id
}

resource "aws_api_gateway_integration" "protected" {
  for_each                = local.protected
  rest_api_id             = aws_api_gateway_rest_api.this.id
  resource_id             = each.value
  http_method             = aws_api_gateway_method.protected[each.key].http_method
  type                    = "AWS_PROXY"
  integration_http_method = "POST"
  uri                     = var.function_invoke_arn
}

resource "aws_api_gateway_method" "public" {
  for_each      = aws_api_gateway_resource.public
  rest_api_id   = aws_api_gateway_rest_api.this.id
  resource_id   = each.value.id
  http_method   = "ANY"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "public" {
  for_each                = aws_api_gateway_resource.public
  rest_api_id             = aws_api_gateway_rest_api.this.id
  resource_id             = each.value.id
  http_method             = aws_api_gateway_method.public[each.key].http_method
  type                    = "AWS_PROXY"
  integration_http_method = "POST"
  uri                     = var.function_invoke_arn
}

# JSON bodies for authorizer rejections (API Gateway's defaults are {"message": ...}).
resource "aws_api_gateway_gateway_response" "unauthorized" {
  rest_api_id   = aws_api_gateway_rest_api.this.id
  response_type = "UNAUTHORIZED"
  status_code   = "401"
  response_templates = {
    "application/json" = jsonencode({ detail = "Unauthorized: missing or invalid bearer token" })
  }
}

resource "aws_api_gateway_gateway_response" "denied" {
  rest_api_id   = aws_api_gateway_rest_api.this.id
  response_type = "ACCESS_DENIED"
  status_code   = "403"
  response_templates = {
    "application/json" = jsonencode({ detail = "Forbidden: your roles do not grant this API" })
  }
}

locals {
  redeploy_input = jsonencode({
    resources    = [aws_api_gateway_resource.root.id, aws_api_gateway_resource.proxy.id, [for r in aws_api_gateway_resource.public : r.id]]
    methods      = [for m in concat(values(aws_api_gateway_method.protected), values(aws_api_gateway_method.public)) : [m.id, m.authorization, m.authorizer_id == null ? "" : m.authorizer_id]]
    integrations = [for i in concat(values(aws_api_gateway_integration.protected), values(aws_api_gateway_integration.public)) : [i.id, i.uri, i.type]]
    authorizer   = [aws_api_gateway_authorizer.jwt.id, var.authorizer_ttl, var.authorizer_identity_source, var.authorizer_invoke_arn]
    responses    = [aws_api_gateway_gateway_response.unauthorized.response_templates, aws_api_gateway_gateway_response.denied.response_templates]
  })
}

resource "aws_api_gateway_deployment" "this" {
  rest_api_id = aws_api_gateway_rest_api.this.id
  triggers = {
    # Hash configured inputs only. Hashing whole resource objects also picks up computed
    # attributes, which aws-emulator reports differently from AWS (e.g. provider_arns = [] vs null,
    # authorizer_id = "" vs null on NONE methods) and would force a new deployment on every plan.
    redeploy = sha1(local.redeploy_input)
  }
  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_api_gateway_stage" "this" {
  rest_api_id   = aws_api_gateway_rest_api.this.id
  deployment_id = aws_api_gateway_deployment.this.id
  stage_name    = var.stage_name
}

output "rest_api_id" { value = aws_api_gateway_rest_api.this.id }
output "execution_arn" { value = local.execution_arn }
output "stage_name" { value = aws_api_gateway_stage.this.stage_name }
output "invoke_url" { value = aws_api_gateway_stage.this.invoke_url }
