# The real tipg (FastAPI + asyncpg + pydantic-core) packaged as a zip Lambda behind Mangum.
resource "aws_s3_bucket" "art" {
  bucket        = "probe-real-tipg-artifacts"
  force_destroy = true
}
resource "aws_s3_object" "zip" {
  bucket      = aws_s3_bucket.art.id
  key         = "tipg.zip"
  source      = "${path.module}/build/tipg.zip"
  source_hash = filemd5("${path.module}/build/tipg.zip")
}
resource "aws_iam_role" "r" {
  name               = "probe-real-tipg"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}
resource "aws_lambda_function" "f" {
  function_name = "probe-real-tipg"
  role          = aws_iam_role.r.arn
  runtime       = "python3.12"
  handler       = "handler.handler"
  s3_bucket     = aws_s3_object.zip.bucket
  s3_key        = aws_s3_object.zip.key
  memory_size   = 1024
  timeout       = 30
  environment {
    variables = { DATABASE_URL = "postgresql://user:pass@example.invalid:5432/db" }
  }
}
output "fn" { value = aws_lambda_function.f.function_name }
