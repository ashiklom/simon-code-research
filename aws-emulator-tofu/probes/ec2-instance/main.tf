data "aws_ssm_parameter" "al2023" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
}
resource "aws_vpc" "v" { cidr_block = "10.65.0.0/16" }
data "aws_availability_zones" "az" {}
resource "aws_subnet" "s" {
  vpc_id            = aws_vpc.v.id
  cidr_block        = "10.65.1.0/24"
  availability_zone = data.aws_availability_zones.az.names[0]
}
# No availability_zone: AWS picks one; recorded by check.py.
resource "aws_subnet" "noaz" {
  vpc_id     = aws_vpc.v.id
  cidr_block = "10.65.2.0/24"
}
resource "aws_instance" "i" {
  ami           = nonsensitive(data.aws_ssm_parameter.al2023.value)
  instance_type = "t3.micro"
  subnet_id     = aws_subnet.s.id
  # aws-emulator rejects the provider's empty Placement.AvailabilityZone; set it explicitly.
  availability_zone = aws_subnet.s.availability_zone
  user_data     = "#!/bin/bash\necho probe-userdata-ran > /dev/console\n"
  tags          = { Name = "probe" }
}
output "id" { value = aws_instance.i.id }
output "ami" { value = nonsensitive(data.aws_ssm_parameter.al2023.value) }
output "noaz_subnet" { value = aws_subnet.noaz.id }
