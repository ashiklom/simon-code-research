data "archive_file" "fn" {
  type        = "zip"
  output_path = "${path.module}/build/fn.zip"
  source {
    filename = "app.py"
    content  = "import json\ndef handler(e, c):\n    print('PROBE-EVENT ' + json.dumps(e)[:2000])\n    return {'ok': True}\n"
  }
}
resource "aws_iam_role" "r" {
  name               = "probe-schedule"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}
resource "aws_iam_role_policy" "p" {
  role   = aws_iam_role.r.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Action = ["logs:*", "sqs:*", "dynamodb:*"], Resource = "*" }] })
}
resource "aws_cloudwatch_log_group" "lg" {
  name              = "/aws/lambda/probe-schedule"
  retention_in_days = 1
}
resource "aws_lambda_function" "f" {
  function_name    = "probe-schedule"
  role             = aws_iam_role.r.arn
  runtime          = "python3.12"
  handler          = "app.handler"
  filename         = data.archive_file.fn.output_path
  source_code_hash = data.archive_file.fn.output_base64sha256
  depends_on       = [aws_iam_role_policy.p, aws_cloudwatch_log_group.lg]
}
output "log_group" { value = aws_cloudwatch_log_group.lg.name }
resource "aws_cloudwatch_event_rule" "r" {
  name                = "probe-every-minute"
  schedule_expression = "rate(1 minute)"
}
resource "aws_cloudwatch_event_target" "t" {
  rule = aws_cloudwatch_event_rule.r.name
  arn  = aws_lambda_function.f.arn
}
resource "aws_lambda_permission" "ev" {
  statement_id  = "events"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.f.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.r.arn
}
