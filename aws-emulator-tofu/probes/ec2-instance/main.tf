data "aws_ssm_parameter" "al2023" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
}
resource "aws_vpc" "v" { cidr_block = "10.65.0.0/16" }
resource "aws_subnet" "s" {
  vpc_id     = aws_vpc.v.id
  cidr_block = "10.65.1.0/24"
}
resource "aws_instance" "i" {
  ami           = nonsensitive(data.aws_ssm_parameter.al2023.value)
  instance_type = "t3.micro"
  subnet_id     = aws_subnet.s.id
  user_data     = "#!/bin/bash\necho probe-userdata-ran > /dev/console\n"
  tags          = { Name = "probe" }
}
output "id" { value = aws_instance.i.id }
output "ami" { value = nonsensitive(data.aws_ssm_parameter.al2023.value) }
