data "archive_file" "fn" {
  type        = "zip"
  output_path = "${path.module}/build/fn.zip"
  source {
    filename = "app.py"
    content  = "import json\ndef handler(e, c):\n    print('PROBE-EVENT ' + json.dumps(e)[:2000])\n    return {'ok': True}\n"
  }
}
resource "aws_iam_role" "r" {
  name               = "probe-sfn-task"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}
resource "aws_iam_role_policy" "p" {
  role   = aws_iam_role.r.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Action = ["logs:*", "sqs:*", "dynamodb:*"], Resource = "*" }] })
}
resource "aws_cloudwatch_log_group" "lg" {
  name              = "/aws/lambda/probe-sfn-task"
  retention_in_days = 1
}
resource "aws_lambda_function" "f" {
  function_name    = "probe-sfn-task"
  role             = aws_iam_role.r.arn
  runtime          = "python3.12"
  handler          = "app.handler"
  filename         = data.archive_file.fn.output_path
  source_code_hash = data.archive_file.fn.output_base64sha256
  depends_on       = [aws_iam_role_policy.p, aws_cloudwatch_log_group.lg]
}
output "log_group" { value = aws_cloudwatch_log_group.lg.name }
resource "aws_iam_role" "sfn" {
  name = "probe-sfn"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Action = "sts:AssumeRole", Principal = { Service = "states.amazonaws.com" } }] })
}
resource "aws_iam_role_policy" "sfn" {
  role   = aws_iam_role.sfn.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Action = "lambda:InvokeFunction", Resource = aws_lambda_function.f.arn }] })
}
resource "aws_sfn_state_machine" "m" {
  name     = "probe-sfn"
  role_arn = aws_iam_role.sfn.arn
  definition = jsonencode({
    StartAt = "Shape"
    States = {
      Shape  = { Type = "Pass", Parameters = { "input.$" = "$.value", constant = 7 }, Next = "Choose" }
      Choose = { Type = "Choice", Choices = [{ Variable = "$.constant", NumericGreaterThan = 5, Next = "Call" }], Default = "Fail" }
      Call   = { Type = "Task", Resource = aws_lambda_function.f.arn, End = true }
      Fail   = { Type = "Fail" }
    }
  })
}
output "sm" { value = aws_sfn_state_machine.m.arn }
