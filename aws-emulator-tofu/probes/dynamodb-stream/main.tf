data "archive_file" "fn" {
  type        = "zip"
  output_path = "${path.module}/build/fn.zip"
  source {
    filename = "app.py"
    content  = "import json\ndef handler(e, c):\n    print('PROBE-EVENT ' + json.dumps(e)[:2000])\n    return {'ok': True}\n"
  }
}
resource "aws_iam_role" "r" {
  name               = "probe-ddb-stream"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}
resource "aws_iam_role_policy" "p" {
  role   = aws_iam_role.r.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Action = ["logs:*", "sqs:*", "dynamodb:*"], Resource = "*" }] })
}
resource "aws_cloudwatch_log_group" "lg" {
  name              = "/aws/lambda/probe-ddb-stream"
  retention_in_days = 1
}
resource "aws_lambda_function" "f" {
  function_name    = "probe-ddb-stream"
  role             = aws_iam_role.r.arn
  runtime          = "python3.12"
  handler          = "app.handler"
  filename         = data.archive_file.fn.output_path
  source_code_hash = data.archive_file.fn.output_base64sha256
  depends_on       = [aws_iam_role_policy.p, aws_cloudwatch_log_group.lg]
}
output "log_group" { value = aws_cloudwatch_log_group.lg.name }
resource "aws_dynamodb_table" "t" {
  name             = "probe-ddb"
  billing_mode     = "PAY_PER_REQUEST"
  hash_key         = "pk"
  stream_enabled   = true
  stream_view_type = "NEW_IMAGE"
  attribute {
    name = "pk"
    type = "S"
  }
  point_in_time_recovery { enabled = true }
}
resource "aws_lambda_event_source_mapping" "m" {
  event_source_arn  = aws_dynamodb_table.t.stream_arn
  function_name     = aws_lambda_function.f.arn
  starting_position = "LATEST"
}
output "table" { value = aws_dynamodb_table.t.name }
