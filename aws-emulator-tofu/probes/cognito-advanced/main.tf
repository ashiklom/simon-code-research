data "archive_file" "fn" {
  type        = "zip"
  output_path = "${path.module}/build/fn.zip"
  source {
    filename = "app.py"
    content  = <<-PY
      def handler(event, context):
          print("PRETOKEN", event.get("triggerSource"), event.get("version"))
          event["response"] = {"claimsAndScopeOverrideDetails": {
              "idTokenGeneration": {"claimsToAddOrOverride": {"custom_role": "tiler"}},
              "accessTokenGeneration": {"claimsToAddOrOverride": {"custom_role": "tiler"}, "scopesToAdd": ["tiler/read"]}}}
          return event
    PY
  }
}
resource "aws_iam_role" "r" {
  name               = "probe-pretoken"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}
resource "aws_lambda_function" "f" {
  function_name    = "probe-pretoken"
  role             = aws_iam_role.r.arn
  runtime          = "python3.12"
  handler          = "app.handler"
  filename         = data.archive_file.fn.output_path
  source_code_hash = data.archive_file.fn.output_base64sha256
}
resource "aws_cognito_user_pool" "p" {
  name      = "probe-adv"
  user_pool_tier = "ESSENTIALS"
  schema {
    name                = "department"
    attribute_data_type = "String"
    mutable             = true
    string_attribute_constraints {
      min_length = 1
      max_length = 32
    }
  }
  lambda_config {
    pre_token_generation_config {
      lambda_arn     = aws_lambda_function.f.arn
      lambda_version = "V2_0"
    }
  }
}
resource "aws_lambda_permission" "cog" {
  statement_id  = "cognito"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.f.function_name
  principal     = "cognito-idp.amazonaws.com"
  source_arn    = aws_cognito_user_pool.p.arn
}
resource "aws_cognito_user_pool_domain" "d" {
  domain       = "probe-adv-${substr(md5(aws_cognito_user_pool.p.id), 0, 8)}"
  user_pool_id = aws_cognito_user_pool.p.id
}
resource "aws_cognito_resource_server" "rs" {
  identifier   = "tiler"
  name         = "tiler"
  user_pool_id = aws_cognito_user_pool.p.id
  scope {
    scope_name        = "read"
    scope_description = "read tiles"
  }
}
resource "aws_cognito_user_pool_client" "user" {
  name                = "probe-adv-user"
  user_pool_id        = aws_cognito_user_pool.p.id
  explicit_auth_flows = ["ALLOW_USER_PASSWORD_AUTH", "ALLOW_REFRESH_TOKEN_AUTH", "ALLOW_USER_SRP_AUTH"]
}
resource "aws_cognito_user_pool_client" "m2m" {
  name                                 = "probe-adv-m2m"
  user_pool_id                         = aws_cognito_user_pool.p.id
  generate_secret                      = true
  allowed_oauth_flows                  = ["client_credentials"]
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_scopes                 = ["tiler/read"]
  supported_identity_providers         = ["COGNITO"]
  depends_on                           = [aws_cognito_resource_server.rs]
}
resource "aws_cognito_user" "u" {
  user_pool_id   = aws_cognito_user_pool.p.id
  username       = "probe"
  password       = "Probe-Passw0rd!"
  message_action = "SUPPRESS"
  attributes     = { "custom:department" = "geo" }
}
output "pool" { value = aws_cognito_user_pool.p.id }
output "client" { value = aws_cognito_user_pool_client.user.id }
output "m2m_id" { value = aws_cognito_user_pool_client.m2m.id }
output "m2m_secret" {
  value     = aws_cognito_user_pool_client.m2m.client_secret
  sensitive = true
}
output "domain" { value = aws_cognito_user_pool_domain.d.domain }
