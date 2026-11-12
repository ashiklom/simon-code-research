from lib import client, result

TITLE = "Aurora cluster through aws_cloudformation_stack (AWS::RDS::DBCluster)"
CATEGORY = "CloudFormation"
AWS_EXPECTED = "Stack CREATE_COMPLETE creates a real cluster visible to rds:DescribeDBClusters; outputs resolve."
FINDINGS = ["cfn-rds-not-materialized"]


def check(outputs, row):
    ids = [c["DBClusterIdentifier"] for c in client("rds").describe_db_clusters()["DBClusters"]]
    if not row["apply"]["ok"]:
        return result("gap", row["apply"]["error"])
    if "probe-cfn" in ids:
        return result("works", "stack created a real cluster")
    return result("gap", f"stack CREATE_COMPLETE but no RDS cluster exists; outputs={outputs.get('stack_outputs')}")
