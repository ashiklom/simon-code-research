data "archive_file" "layer" {
  type        = "zip"
  output_path = "${path.module}/build/layer.zip"
  source {
    filename = "python/probe_layer_mod.py"
    content  = "VALUE = 'from-layer'\n"
  }
}
resource "aws_lambda_layer_version" "l" {
  layer_name          = "probe-layer"
  filename            = data.archive_file.layer.output_path
  source_code_hash    = data.archive_file.layer.output_base64sha256
  compatible_runtimes = ["python3.12"]
}
data "archive_file" "fn" {
  type        = "zip"
  output_path = "${path.module}/build/fn.zip"
  source {
    filename = "app.py"
    content  = "def handler(e, c):\n    import probe_layer_mod\n    return {'value': probe_layer_mod.VALUE}\n"
  }
}
resource "aws_iam_role" "r" {
  name               = "probe-layer"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}
resource "aws_lambda_function" "f" {
  function_name    = "probe-layer"
  role             = aws_iam_role.r.arn
  runtime          = "python3.12"
  handler          = "app.handler"
  filename         = data.archive_file.fn.output_path
  source_code_hash = data.archive_file.fn.output_base64sha256
  layers           = [aws_lambda_layer_version.l.arn]
}
output "fn" { value = aws_lambda_function.f.function_name }
