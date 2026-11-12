variable "emulator_endpoint" {
  type    = string
  default = "https://127.0.0.1:9297"
}
resource "aws_cognito_user_pool" "p" { name = "probe-v2" }
resource "aws_cognito_user_pool_client" "c" {
  name                = "probe-v2"
  user_pool_id        = aws_cognito_user_pool.p.id
  explicit_auth_flows = ["ALLOW_USER_PASSWORD_AUTH", "ALLOW_REFRESH_TOKEN_AUTH"]
}
resource "aws_cognito_user" "u" {
  user_pool_id   = aws_cognito_user_pool.p.id
  username       = "probe"
  password       = "Probe-Passw0rd!"
  message_action = "SUPPRESS"
}
data "archive_file" "fn" {
  type        = "zip"
  output_path = "${path.module}/build/fn.zip"
  source {
    filename = "app.py"
    content  = "import json\ndef handler(e, c):\n    a = (e.get('requestContext') or {}).get('authorizer') or {}\n    return {'statusCode': 200, 'body': json.dumps({'claims': (a.get('jwt') or {}).get('claims', {}).get('username')})}\n"
  }
}
resource "aws_iam_role" "r" {
  name               = "probe-v2"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}
resource "aws_lambda_function" "f" {
  for_each         = toset(["withperm", "noperm"])
  function_name    = "probe-v2-${each.key}"
  role             = aws_iam_role.r.arn
  runtime          = "python3.12"
  handler          = "app.handler"
  filename         = data.archive_file.fn.output_path
  source_code_hash = data.archive_file.fn.output_base64sha256
}
resource "aws_apigatewayv2_api" "a" {
  name          = "probe-v2"
  protocol_type = "HTTP"
}
resource "aws_apigatewayv2_authorizer" "jwt" {
  api_id           = aws_apigatewayv2_api.a.id
  authorizer_type  = "JWT"
  name             = "cognito"
  identity_sources = ["$request.header.Authorization"]
  jwt_configuration {
    audience = [aws_cognito_user_pool_client.c.id]
    # aws-emulator puts the endpoint the client called into `iss`.
    issuer = "${var.emulator_endpoint}/${aws_cognito_user_pool.p.id}"
  }
}
resource "aws_apigatewayv2_integration" "i" {
  for_each               = aws_lambda_function.f
  api_id                 = aws_apigatewayv2_api.a.id
  integration_type       = "AWS_PROXY"
  integration_uri        = each.value.invoke_arn
  payload_format_version = "2.0"
}
resource "aws_apigatewayv2_route" "r" {
  for_each           = aws_lambda_function.f
  api_id             = aws_apigatewayv2_api.a.id
  route_key          = "GET /${each.key}"
  target             = "integrations/${aws_apigatewayv2_integration.i[each.key].id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.jwt.id
}
resource "aws_apigatewayv2_stage" "s" {
  api_id      = aws_apigatewayv2_api.a.id
  name        = "$default"
  auto_deploy = true
}
resource "aws_lambda_permission" "p" {
  statement_id  = "v2"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.f["withperm"].function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "arn:aws:execute-api:us-east-1:${local.account_id}:${aws_apigatewayv2_api.a.id}/*/*"
}
output "endpoint" { value = aws_apigatewayv2_api.a.api_endpoint }
output "pool" { value = aws_cognito_user_pool.p.id }
output "client" { value = aws_cognito_user_pool_client.c.id }
