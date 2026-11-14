# User pool groups -> IAM roles -> identity pool (Token role mapping, Deny when
# ambiguous): the AWS-native "log in, pick one of your roles, get STS credentials".
resource "aws_s3_bucket" "b" {
  bucket        = "probe-identity-pool"
  force_destroy = true
}

resource "aws_s3_object" "o" {
  for_each = toset(["data/ok.txt", "secret/no.txt"])
  bucket   = aws_s3_bucket.b.id
  key      = each.key
  content  = "x"
}

resource "aws_cognito_user_pool" "p" {
  name = "probe-identity-pool"
}

resource "aws_cognito_user_pool_client" "c" {
  name                = "probe"
  user_pool_id        = aws_cognito_user_pool.p.id
  explicit_auth_flows = ["ALLOW_USER_PASSWORD_AUTH", "ALLOW_REFRESH_TOKEN_AUTH"]
}

resource "aws_cognito_user" "u" {
  user_pool_id   = aws_cognito_user_pool.p.id
  username       = "probe"
  password       = "Probe-Passw0rd-Identity!"
  message_action = "SUPPRESS"
}

resource "aws_cognito_identity_pool" "i" {
  identity_pool_name               = "probe_identity_pool"
  allow_unauthenticated_identities = false
  cognito_identity_providers {
    client_id               = aws_cognito_user_pool_client.c.id
    provider_name           = aws_cognito_user_pool.p.endpoint
    server_side_token_check = true
  }
}

data "aws_iam_policy_document" "trust" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity", "sts:TagSession"]
    principals {
      type        = "Federated"
      identifiers = ["cognito-identity.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "cognito-identity.amazonaws.com:aud"
      values   = [aws_cognito_identity_pool.i.id]
    }
    condition {
      test     = "ForAnyValue:StringLike"
      variable = "cognito-identity.amazonaws.com:amr"
      values   = ["authenticated"]
    }
  }
}

# reader: the user's group. writer: a group the user is NOT in. fallback: pool default.
resource "aws_iam_role" "r" {
  for_each           = toset(["reader", "writer", "fallback"])
  name               = "probe-idpool-${each.key}"
  assume_role_policy = data.aws_iam_policy_document.trust.json
}

resource "aws_iam_role_policy" "reader" {
  role = aws_iam_role.r["reader"].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect = "Allow", Action = ["s3:GetObject", "s3:ListBucket"], Resource = [aws_s3_bucket.b.arn, "${aws_s3_bucket.b.arn}/*"] },
      { Effect = "Deny", Action = "s3:*", Resource = "${aws_s3_bucket.b.arn}/secret/*" },
    ]
  })
}

resource "aws_iam_role_policy" "writer" {
  role = aws_iam_role.r["writer"].id
  policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Action = "s3:*", Resource = ["${aws_s3_bucket.b.arn}/*"] }]
  })
}

resource "aws_cognito_user_group" "g" {
  for_each     = toset(["reader", "writer"])
  name         = each.key
  user_pool_id = aws_cognito_user_pool.p.id
  role_arn     = aws_iam_role.r[each.key].arn
}

resource "aws_cognito_user_in_group" "m" {
  user_pool_id = aws_cognito_user_pool.p.id
  username     = aws_cognito_user.u.username
  group_name   = aws_cognito_user_group.g["reader"].name
}

resource "aws_cognito_identity_pool_roles_attachment" "a" {
  identity_pool_id = aws_cognito_identity_pool.i.id
  roles            = { authenticated = aws_iam_role.r["fallback"].arn }
  role_mapping {
    identity_provider         = "${aws_cognito_user_pool.p.endpoint}:${aws_cognito_user_pool_client.c.id}"
    type                      = "Token"
    ambiguous_role_resolution = "Deny"
  }
}

output "pool" { value = aws_cognito_user_pool.p.id }
output "client" { value = aws_cognito_user_pool_client.c.id }
output "identity_pool" { value = aws_cognito_identity_pool.i.id }
output "bucket" { value = aws_s3_bucket.b.id }
output "roles" { value = { for k, r in aws_iam_role.r : k => r.arn } }
