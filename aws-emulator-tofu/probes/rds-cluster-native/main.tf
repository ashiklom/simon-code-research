resource "aws_vpc" "v" { cidr_block = "10.61.0.0/16" }
data "aws_availability_zones" "az" {}
resource "aws_subnet" "s" {
  count             = 2
  vpc_id            = aws_vpc.v.id
  cidr_block        = cidrsubnet(aws_vpc.v.cidr_block, 8, count.index)
  availability_zone = data.aws_availability_zones.az.names[count.index]
}
resource "aws_db_subnet_group" "g" {
  name       = "probe-native"
  subnet_ids = aws_subnet.s[*].id
}
resource "aws_rds_cluster" "c" {
  cluster_identifier          = "probe-native"
  engine                      = "aurora-postgresql"
  engine_mode                 = "provisioned"
  engine_version              = "16.6"
  database_name               = "probe"
  master_username             = "probeadmin"
  manage_master_user_password = true
  enable_http_endpoint        = true
  db_subnet_group_name        = aws_db_subnet_group.g.name
  skip_final_snapshot         = true
  serverlessv2_scaling_configuration {
    min_capacity = 0.5
    max_capacity = 2
  }
}
