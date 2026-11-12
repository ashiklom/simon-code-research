resource "aws_vpc" "v" { cidr_block = "10.63.0.0/16" }
data "aws_availability_zones" "az" {}
resource "aws_subnet" "s" {
  count             = 2
  vpc_id            = aws_vpc.v.id
  cidr_block        = cidrsubnet(aws_vpc.v.cidr_block, 8, count.index)
  availability_zone = data.aws_availability_zones.az.names[count.index]
}
data "archive_file" "fn" {
  type        = "zip"
  output_path = "${path.module}/build/fn.zip"
  source {
    filename = "app.py"
    content  = "def handler(e, c):\n    return {'statusCode': 200, 'statusDescription': '200 OK', 'isBase64Encoded': False, 'headers': {'content-type': 'text/plain'}, 'body': 'alb-ok ' + e.get('path', '')}\n"
  }
}
resource "aws_iam_role" "r" {
  name               = "probe-alb"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}
resource "aws_lambda_function" "f" {
  function_name    = "probe-alb"
  role             = aws_iam_role.r.arn
  runtime          = "python3.12"
  handler          = "app.handler"
  filename         = data.archive_file.fn.output_path
  source_code_hash = data.archive_file.fn.output_base64sha256
}
# No aws_security_group (see ec2-security-group probe): the ALB uses the VPC default SG.
resource "aws_lb" "a" {
  name               = "probe-alb"
  internal           = true
  load_balancer_type = "application"
  subnets            = aws_subnet.s[*].id
}
resource "aws_lb_target_group" "t" {
  name        = "probe-alb-fn"
  target_type = "lambda"
}
resource "aws_lambda_permission" "alb" {
  statement_id  = "alb"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.f.function_name
  principal     = "elasticloadbalancing.amazonaws.com"
  source_arn    = aws_lb_target_group.t.arn
}
resource "aws_lb_target_group_attachment" "a" {
  target_group_arn = aws_lb_target_group.t.arn
  target_id        = aws_lambda_function.f.arn
  depends_on       = [aws_lambda_permission.alb]
}
resource "aws_lb_listener" "l" {
  load_balancer_arn = aws_lb.a.arn
  port              = 80
  protocol          = "HTTP"
  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.t.arn
  }
}
output "dns" { value = aws_lb.a.dns_name }
