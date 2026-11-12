resource "aws_vpc" "v" { cidr_block = "10.64.0.0/16" }
resource "aws_subnet" "s" {
  vpc_id     = aws_vpc.v.id
  cidr_block = "10.64.1.0/24"
}
# Route to the internet so the (modelled) image pull can succeed.
resource "aws_internet_gateway" "g" { vpc_id = aws_vpc.v.id }
resource "aws_route_table" "rt" {
  vpc_id = aws_vpc.v.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.g.id
  }
}
resource "aws_route_table_association" "a" {
  subnet_id      = aws_subnet.s.id
  route_table_id = aws_route_table.rt.id
}
resource "aws_ecs_cluster" "c" { name = "probe-ecs" }
resource "aws_iam_role" "exec" {
  name = "probe-ecs-exec"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Action = "sts:AssumeRole", Principal = { Service = "ecs-tasks.amazonaws.com" } }] })
}
resource "aws_ecs_task_definition" "t" {
  family                   = "probe-task"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "256"
  memory                   = "512"
  execution_role_arn       = aws_iam_role.exec.arn
  container_definitions = jsonencode([{
    name = "main", image = "public.ecr.aws/docker/library/busybox:latest", essential = true,
    command = ["sh", "-c", "echo probe-ecs-ran; sleep 2"]
  }])
}
output "cluster" { value = aws_ecs_cluster.c.name }
output "taskdef" { value = aws_ecs_task_definition.t.arn }
output "subnet" { value = aws_subnet.s.id }
