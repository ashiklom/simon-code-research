# A Python Lambda packaged from lambdas/<name>/*.py + lambdas/common/*.py, with its own role,
# log group and least-privilege inline policy.
terraform {
  required_providers {
    aws     = { source = "hashicorp/aws" }
    archive = { source = "hashicorp/archive" }
  }
}

variable "name" { type = string }
variable "src_dir" { type = string }
variable "common_dir" {
  type    = string
  default = null
}
variable "environment" {
  type    = map(string)
  default = {}
}
variable "memory_size" {
  type    = number
  default = 512
}
variable "timeout" {
  type    = number
  default = 29 # API Gateway REST integrations time out at 29 s
}
variable "runtime" {
  type    = string
  default = "python3.12"
}
variable "policy_statements" {
  type = list(object({
    actions   = list(string)
    resources = list(string)
  }))
  default = []
}

locals {
  common_dir = coalesce(var.common_dir, "${var.src_dir}/../common")
  files = merge(
    { for f in fileset(local.common_dir, "*.py") : f => "${local.common_dir}/${f}" },
    { for f in fileset(var.src_dir, "*.py") : f => "${var.src_dir}/${f}" },
  )
}

data "archive_file" "zip" {
  type        = "zip"
  output_path = "${path.root}/../build/${var.name}.zip"
  dynamic "source" {
    for_each = local.files
    content {
      filename = source.key
      content  = file(source.value)
    }
  }
}

data "aws_iam_policy_document" "assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "this" {
  name               = "${var.name}-role"
  assume_role_policy = data.aws_iam_policy_document.assume.json
}

resource "aws_cloudwatch_log_group" "this" {
  name              = "/aws/lambda/${var.name}"
  retention_in_days = 7
}

data "aws_iam_policy_document" "inline" {
  statement {
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.this.arn}:*"]
  }
  dynamic "statement" {
    for_each = var.policy_statements
    content {
      actions   = statement.value.actions
      resources = statement.value.resources
    }
  }
}

resource "aws_iam_role_policy" "inline" {
  name   = "${var.name}-inline"
  role   = aws_iam_role.this.id
  policy = data.aws_iam_policy_document.inline.json
}

resource "aws_lambda_function" "this" {
  function_name    = var.name
  role             = aws_iam_role.this.arn
  runtime          = var.runtime
  handler          = "handler.handler"
  filename         = data.archive_file.zip.output_path
  source_code_hash = data.archive_file.zip.output_base64sha256
  memory_size      = var.memory_size
  timeout          = var.timeout
  architectures    = ["arm64"]
  environment {
    variables = var.environment
  }
  logging_config {
    log_format = "Text"
    log_group  = aws_cloudwatch_log_group.this.name
  }
  depends_on = [aws_iam_role_policy.inline]
}

output "function_name" { value = aws_lambda_function.this.function_name }
output "arn" { value = aws_lambda_function.this.arn }
output "invoke_arn" { value = aws_lambda_function.this.invoke_arn }
output "role_name" { value = aws_iam_role.this.name }
