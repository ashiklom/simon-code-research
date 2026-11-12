resource "aws_kms_key" "k" {
  description             = "probe"
  deletion_window_in_days = 7
  enable_key_rotation     = true
}
resource "aws_kms_alias" "a" {
  name          = "alias/probe"
  target_key_id = aws_kms_key.k.key_id
}
resource "aws_secretsmanager_secret" "s" {
  name                    = "probe/secret"
  kms_key_id              = aws_kms_key.k.arn
  recovery_window_in_days = 0
}
resource "aws_secretsmanager_secret_version" "v" {
  secret_id     = aws_secretsmanager_secret.s.id
  secret_string = jsonencode({ user = "u", password = "p" })
}
output "key" { value = aws_kms_key.k.arn }
output "secret" { value = aws_secretsmanager_secret.s.arn }
