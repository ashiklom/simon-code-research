# Shared by every probe (symlinked). Endpoint, CA bundle and credentials come from the
# environment set by `eval "$(scripts/emulator.sh env)"`: AWS_ENDPOINT_URL, AWS_CA_BUNDLE,
# AWS_SHARED_CREDENTIALS_FILE. Only the flags that cannot be set by env vars are here.
terraform {
  required_providers {
    aws     = { source = "hashicorp/aws", version = "~> 6.73" }
    archive = { source = "hashicorp/archive", version = "~> 2.8" }
    random  = { source = "hashicorp/random", version = "~> 3.9" }
  }
}

variable "skip_account_id" {
  description = "false only for the probe that demonstrates the S3 Control tagging hang"
  type        = bool
  default     = true
}

provider "aws" {
  region                      = "us-east-1"
  s3_use_path_style           = true
  skip_metadata_api_check     = true
  skip_credentials_validation = var.skip_account_id
  skip_requesting_account_id  = var.skip_account_id
}

data "aws_caller_identity" "me" {}

locals {
  account_id = data.aws_caller_identity.me.account_id
}

data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}
