from lib import client, result

TITLE = "aws_rds_cluster (Aurora PostgreSQL Serverless v2) via the AWS provider"
CATEGORY = "OpenTofu provider x emulator"
AWS_EXPECTED = "Cluster created; provider's DescribeGlobalClusters(Filters=[db-cluster-id]) succeeds."
FINDINGS = ["rds-describeglobalclusters-filter"]
EXPECT_APPLY_FAILURE = True


def check(outputs, row):
    ids = [c["DBClusterIdentifier"] for c in client("rds").describe_db_clusters()["DBClusters"]]
    if row["apply"]["ok"]:
        return result("works", "aws_rds_cluster applied")
    return result("gap", f"apply failed: {row['apply']['error'][:300]} | cluster exists in emulator anyway: "
                         f"{'probe-native' in ids} (tofu marks it tainted)")
