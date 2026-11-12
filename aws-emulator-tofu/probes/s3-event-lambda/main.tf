data "archive_file" "fn" {
  type        = "zip"
  output_path = "${path.module}/build/fn.zip"
  source {
    filename = "app.py"
    content  = "import json\ndef handler(e, c):\n    print('PROBE-EVENT ' + json.dumps(e)[:2000])\n    return {'ok': True}\n"
  }
}
resource "aws_iam_role" "r" {
  name               = "probe-s3-event"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}
resource "aws_iam_role_policy" "p" {
  role   = aws_iam_role.r.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Action = ["logs:*", "sqs:*", "dynamodb:*"], Resource = "*" }] })
}
resource "aws_cloudwatch_log_group" "lg" {
  name              = "/aws/lambda/probe-s3-event"
  retention_in_days = 1
}
resource "aws_lambda_function" "f" {
  function_name    = "probe-s3-event"
  role             = aws_iam_role.r.arn
  runtime          = "python3.12"
  handler          = "app.handler"
  filename         = data.archive_file.fn.output_path
  source_code_hash = data.archive_file.fn.output_base64sha256
  depends_on       = [aws_iam_role_policy.p, aws_cloudwatch_log_group.lg]
}
output "log_group" { value = aws_cloudwatch_log_group.lg.name }
resource "aws_s3_bucket" "b" {
  bucket        = "probe-s3-event"
  force_destroy = true
}
resource "aws_lambda_permission" "s3" {
  statement_id  = "s3"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.f.function_name
  principal     = "s3.amazonaws.com"
  source_arn    = aws_s3_bucket.b.arn
}
resource "aws_s3_bucket_notification" "n" {
  bucket = aws_s3_bucket.b.id
  lambda_function {
    lambda_function_arn = aws_lambda_function.f.arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = "incoming/"
  }
  depends_on = [aws_lambda_permission.s3]
}
output "bucket" { value = aws_s3_bucket.b.id }
