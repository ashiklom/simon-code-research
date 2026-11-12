# Aurora PostgreSQL Serverless v2 with the RDS Data API (HTTPS) enabled and the master password
# managed in Secrets Manager. Lambdas use the Data API, so they need no VPC attachment.
terraform {
  required_providers {
    aws = { source = "hashicorp/aws" }
  }
}

variable "name" { type = string }
variable "vpc_id" { type = string }
variable "subnet_ids" { type = list(string) }
variable "via_script" {
  description = "Create the Aurora cluster with scripts/rds_cluster.py (aws-emulator workaround)."
  type        = bool
  default     = false
}
variable "create_security_group" {
  type    = bool
  default = true
}
variable "engine_version" {
  type    = string
  default = "16.6"
}

resource "aws_db_subnet_group" "this" {
  name       = "${var.name}-db"
  subnet_ids = var.subnet_ids
}

resource "aws_security_group" "db" {
  count       = var.create_security_group ? 1 : 0
  name        = "${var.name}-db"
  description = "Aurora: no inbound by default (Data API is used)"
  vpc_id      = var.vpc_id
}

resource "aws_rds_cluster" "this" {
  count                       = var.via_script ? 0 : 1
  cluster_identifier          = "${var.name}-features"
  engine                      = "aurora-postgresql"
  engine_mode                 = "provisioned"
  engine_version              = var.engine_version
  database_name               = "features"
  master_username             = local.master_username
  manage_master_user_password = true
  enable_http_endpoint        = true # RDS Data API
  db_subnet_group_name        = aws_db_subnet_group.this.name
  vpc_security_group_ids      = aws_security_group.db[*].id
  storage_encrypted           = true
  skip_final_snapshot         = true
  apply_immediately           = true
  serverlessv2_scaling_configuration {
    min_capacity = 0.5
    max_capacity = 2
  }
}

resource "aws_rds_cluster_instance" "writer" {
  count              = var.via_script ? 0 : 1
  identifier         = "${var.name}-features-1"
  cluster_identifier = aws_rds_cluster.this[0].id
  instance_class     = "db.serverless"
  engine             = aws_rds_cluster.this[0].engine
  engine_version     = aws_rds_cluster.this[0].engine_version
}

# aws-emulator workaround: every read of `aws_rds_cluster` (provisioned) calls
# DescribeGlobalClusters with a `db-cluster-id` filter, which aws-emulator rejects (it enforces the
# documented "only `region`" rule; real AWS accepts the filter), so the resource never finishes
# creating. aws-emulator's CloudFormation and Cloud Control report success *without* creating the
# cluster, so the escape hatch is a script run by terraform_data, read back by the data source
# (which makes no global-cluster call).
locals {
  script_spec = jsonencode({
    cluster_identifier = "${var.name}-features"
    engine_version     = var.engine_version
    database_name      = "features"
    master_username    = local.master_username
    subnet_group       = aws_db_subnet_group.this.name
  })
}

resource "terraform_data" "cluster_via_script" {
  count = var.via_script ? 1 : 0
  input = local.script_spec
  provisioner "local-exec" {
    command     = "pixi run python scripts/rds_cluster.py ensure '${self.input}'"
    working_dir = "${path.root}/.."
  }
  provisioner "local-exec" {
    when        = destroy
    command     = "pixi run python scripts/rds_cluster.py delete '${self.input}'"
    working_dir = "${path.root}/.."
  }
}

data "aws_rds_cluster" "scripted" {
  count              = var.via_script ? 1 : 0
  cluster_identifier = "${var.name}-features"
  depends_on         = [terraform_data.cluster_via_script]
}

locals {
  master_username = "featuresadmin"
  scripted        = var.via_script ? data.aws_rds_cluster.scripted[0] : null
}

locals {
  cluster = var.via_script ? local.scripted : aws_rds_cluster.this[0]
}

output "cluster_arn" { value = local.cluster.arn }
output "secret_arn" { value = local.cluster.master_user_secret[0].secret_arn }
output "database_name" { value = local.cluster.database_name }
output "endpoint" { value = local.cluster.endpoint }
output "port" { value = local.cluster.port }
