# One IAM user per AWS-managed policy ARN: one the emulator's catalog has
# (ViewOnlyAccess), one real AWS policy it lacks (AWSBillingReadOnlyAccess) and one
# that exists nowhere. On AWS the last attachment fails with NoSuchEntity, so
# `tofu apply` fails on AWS; the probe exists to show what the emulator does.
locals {
  policies = {
    catalog = "arn:aws:iam::aws:policy/job-function/ViewOnlyAccess"
    missing = "arn:aws:iam::aws:policy/AWSBillingReadOnlyAccess"
    bogus   = "arn:aws:iam::aws:policy/ProbeNoSuchManagedPolicy"
  }
}

resource "aws_s3_bucket" "b" {
  bucket        = "probe-iam-managed-policy"
  force_destroy = true
}

resource "aws_iam_user" "u" {
  for_each = local.policies
  name     = "probe-managed-${each.key}"
}

resource "aws_iam_user_policy_attachment" "a" {
  for_each   = local.policies
  user       = aws_iam_user.u[each.key].name
  policy_arn = each.value
}

resource "aws_iam_access_key" "k" {
  for_each = local.policies
  user     = aws_iam_user.u[each.key].name
}

output "bucket" { value = aws_s3_bucket.b.id }
output "policies" { value = local.policies }
output "keys" {
  value     = { for k, v in aws_iam_access_key.k : k => { id = v.id, secret = v.secret } }
  sensitive = true
}
