resource "aws_cloudformation_stack" "db" {
  name = "probe-cfn-db"
  template_body = jsonencode({
    Resources = {
      Cluster = {
        Type = "AWS::RDS::DBCluster"
        Properties = {
          DBClusterIdentifier = "probe-cfn", Engine = "aurora-postgresql", EngineVersion = "16.6",
          MasterUsername = "probeadmin", ManageMasterUserPassword = true, EnableHttpEndpoint = true,
          DatabaseName = "probe"
        }
      }
    }
    Outputs = {
      Arn    = { Value = { "Fn::GetAtt" = ["Cluster", "DBClusterArn"] } }
      Secret = { Value = { "Fn::GetAtt" = ["Cluster", "MasterUserSecret.SecretArn"] } }
    }
  })
}
output "stack_outputs" { value = aws_cloudformation_stack.db.outputs }
