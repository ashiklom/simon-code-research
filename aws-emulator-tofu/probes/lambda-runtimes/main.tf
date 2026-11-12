resource "aws_iam_role" "r" {
  name               = "probe-runtimes"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}
locals {
  fns = {
    "python3-12" = { runtime = "python3.12", handler = "app.handler", file = "app.py", code = "def handler(e, c):\n    import sys\n    return {'ok': True, 'impl': sys.implementation.name, 'version': sys.version}\n" }
    "python3-13" = { runtime = "python3.13", handler = "app.handler", file = "app.py", code = "def handler(e, c):\n    import sys\n    return {'ok': True, 'impl': sys.implementation.name}\n" }
    "nodejs22"   = { runtime = "nodejs22.x", handler = "index.handler", file = "index.mjs", code = "export const handler = async () => ({ ok: true, node: typeof process !== 'undefined' ? process.version : 'n/a' });\n" }
    "provided"   = { runtime = "provided.al2023", handler = "bootstrap", file = "bootstrap", code = "#!/bin/sh\necho hi\n" }
    "ruby33"     = { runtime = "ruby3.3", handler = "app.handler", file = "app.rb", code = "def handler(event:, context:)\n  { ok: true }\nend\n" }
    "java21"     = { runtime = "java21", handler = "example.Handler::handleRequest", file = "README", code = "no jar" }
  }
}
data "archive_file" "z" {
  for_each    = local.fns
  type        = "zip"
  output_path = "${path.module}/build/${each.key}.zip"
  source {
    filename = each.value.file
    content  = each.value.code
  }
}
resource "aws_lambda_function" "f" {
  for_each         = local.fns
  function_name    = "probe-rt-${each.key}"
  role             = aws_iam_role.r.arn
  runtime          = each.value.runtime
  handler          = each.value.handler
  filename         = data.archive_file.z[each.key].output_path
  source_code_hash = data.archive_file.z[each.key].output_base64sha256
}
output "functions" { value = { for k, f in aws_lambda_function.f : k => f.function_name } }
