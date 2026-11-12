# Cognito user pool: one group per role, an app client for USER_PASSWORD_AUTH, demo users.
terraform {
  required_providers {
    aws    = { source = "hashicorp/aws" }
    random = { source = "hashicorp/random" }
  }
}

variable "name" { type = string }
variable "groups" { type = list(string) }
variable "users" { type = map(list(string)) }

resource "aws_cognito_user_pool" "this" {
  name                     = "${var.name}-users"
  username_attributes      = []
  deletion_protection      = "INACTIVE"
  mfa_configuration        = "OFF"
  auto_verified_attributes = []
  password_policy {
    minimum_length                   = 12
    require_lowercase                = true
    require_uppercase                = true
    require_numbers                  = true
    require_symbols                  = true
    temporary_password_validity_days = 7
  }
  admin_create_user_config {
    allow_admin_create_user_only = true
  }
}

resource "aws_cognito_user_pool_client" "api" {
  name                          = "${var.name}-api"
  user_pool_id                  = aws_cognito_user_pool.this.id
  generate_secret               = false
  explicit_auth_flows           = ["ALLOW_USER_PASSWORD_AUTH", "ALLOW_REFRESH_TOKEN_AUTH"]
  prevent_user_existence_errors = "ENABLED"
  access_token_validity         = 60
  id_token_validity             = 60
  refresh_token_validity        = 30
  token_validity_units {
    access_token  = "minutes"
    id_token      = "minutes"
    refresh_token = "days"
  }
}

resource "aws_cognito_user_group" "role" {
  for_each     = toset(var.groups)
  name         = each.value
  user_pool_id = aws_cognito_user_pool.this.id
  description  = "Role: ${each.value}"
}

resource "random_password" "user" {
  for_each         = var.users
  length           = 20
  special          = true
  override_special = "!#%+-=_"
  min_upper        = 2
  min_lower        = 2
  min_numeric      = 2
  min_special      = 2
}

resource "aws_cognito_user" "this" {
  for_each       = var.users
  user_pool_id   = aws_cognito_user_pool.this.id
  username       = each.key
  password       = random_password.user[each.key].result # permanent password, no FORCE_CHANGE
  message_action = "SUPPRESS"
  attributes = {
    email          = "${each.key}@example.com"
    email_verified = "true"
  }
}

locals {
  memberships = merge([for u, gs in var.users : { for g in gs : "${u}:${g}" => { user = u, group = g } }]...)
}

resource "aws_cognito_user_in_group" "this" {
  for_each     = local.memberships
  user_pool_id = aws_cognito_user_pool.this.id
  username     = aws_cognito_user.this[each.value.user].username
  group_name   = aws_cognito_user_group.role[each.value.group].name
}

output "user_pool_id" { value = aws_cognito_user_pool.this.id }
output "user_pool_arn" { value = aws_cognito_user_pool.this.arn }
output "client_id" { value = aws_cognito_user_pool_client.api.id }
output "passwords" {
  value     = { for u, p in random_password.user : u => p.result }
  sensitive = true
}
