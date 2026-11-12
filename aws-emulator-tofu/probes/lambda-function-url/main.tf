data "archive_file" "fn" {
  type        = "zip"
  output_path = "${path.module}/build/fn.zip"
  source {
    filename = "app.py"
    content  = "import json\ndef handler(e, c):\n    return {'statusCode': 200, 'headers': {'content-type': 'application/json'}, 'body': json.dumps({'hello': 'url', 'path': e.get('rawPath')})}\n"
  }
}
resource "aws_iam_role" "r" {
  name               = "probe-furl"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}
resource "aws_lambda_function" "f" {
  function_name    = "probe-furl"
  role             = aws_iam_role.r.arn
  runtime          = "python3.12"
  handler          = "app.handler"
  filename         = data.archive_file.fn.output_path
  source_code_hash = data.archive_file.fn.output_base64sha256
}
resource "aws_lambda_function_url" "u" {
  function_name      = aws_lambda_function.f.function_name
  authorization_type = "NONE"
}
output "url" { value = aws_lambda_function_url.u.function_url }
resource "aws_lambda_permission" "public" {
  statement_id           = "public-url"
  action                 = "lambda:InvokeFunctionUrl"
  function_name          = aws_lambda_function.f.function_name
  principal              = "*"
  function_url_auth_type = "NONE"
}
