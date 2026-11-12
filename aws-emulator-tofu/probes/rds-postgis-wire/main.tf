# Aurora PostgreSQL via the escape-hatch script (see infra/modules/database), then probe SQL features.
resource "aws_vpc" "v" { cidr_block = "10.66.0.0/16" }
data "aws_availability_zones" "az" {}
resource "aws_subnet" "s" {
  count             = 2
  vpc_id            = aws_vpc.v.id
  cidr_block        = cidrsubnet(aws_vpc.v.cidr_block, 8, count.index)
  availability_zone = data.aws_availability_zones.az.names[count.index]
}
resource "aws_db_subnet_group" "g" {
  name       = "probe-pg"
  subnet_ids = aws_subnet.s[*].id
}
resource "terraform_data" "cluster" {
  input = jsonencode({ cluster_identifier = "probe-pg", engine_version = "16.6", database_name = "probe",
  master_username = "probeadmin", subnet_group = aws_db_subnet_group.g.name })
  provisioner "local-exec" {
    command     = "pixi run python scripts/rds_cluster.py ensure '${self.input}'"
    working_dir = "${path.module}/../.."
  }
  provisioner "local-exec" {
    when        = destroy
    command     = "pixi run python scripts/rds_cluster.py delete '${self.input}'"
    working_dir = "${path.module}/../.."
  }
}
data "aws_rds_cluster" "c" {
  cluster_identifier = "probe-pg"
  depends_on         = [terraform_data.cluster]
}
output "arn" { value = data.aws_rds_cluster.c.arn }
output "secret" { value = data.aws_rds_cluster.c.master_user_secret[0].secret_arn }
output "endpoint" { value = data.aws_rds_cluster.c.endpoint }
output "port" { value = data.aws_rds_cluster.c.port }
