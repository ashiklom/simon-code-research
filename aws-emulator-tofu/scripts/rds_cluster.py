"""Create/delete the Aurora cluster outside the AWS provider (aws-emulator escape hatch).

Why: with hashicorp/aws 6.x, every read of `aws_rds_cluster` (engine_mode provisioned) calls
DescribeGlobalClusters with a `db-cluster-id` filter. aws-emulator rejects that filter
(InvalidParameterValue: "the only supported filter is region"), so the resource can never finish
creating. CloudFormation and Cloud Control on aws-emulator report success without creating the
cluster, so they are no alternative. infra/modules/database calls this script from a
`terraform_data` resource and reads the result back with the `aws_rds_cluster` data source.

  python scripts/rds_cluster.py ensure '<json spec>'
  python scripts/rds_cluster.py delete '<json spec>'
"""
import json
import sys
import time

import boto3


def ensure(spec):
    rds = boto3.client("rds")
    cid = spec["cluster_identifier"]
    try:
        rds.describe_db_clusters(DBClusterIdentifier=cid)
    except rds.exceptions.DBClusterNotFoundFault:
        rds.create_db_cluster(
            DBClusterIdentifier=cid, Engine="aurora-postgresql", EngineMode="provisioned",
            EngineVersion=spec["engine_version"], DatabaseName=spec["database_name"],
            MasterUsername=spec["master_username"], ManageMasterUserPassword=True, EnableHttpEndpoint=True,
            DBSubnetGroupName=spec["subnet_group"], StorageEncrypted=True, DeletionProtection=False,
            ServerlessV2ScalingConfiguration={"MinCapacity": 0.5, "MaxCapacity": 2},
            Tags=[{"Key": "project", "Value": "aws-emulator-tofu"}])
    for _ in range(120):
        if rds.describe_db_clusters(DBClusterIdentifier=cid)["DBClusters"][0]["Status"] == "available":
            break
        time.sleep(1)
    iid = f"{cid}-1"
    try:
        rds.describe_db_instances(DBInstanceIdentifier=iid)
    except rds.exceptions.DBInstanceNotFoundFault:
        rds.create_db_instance(DBInstanceIdentifier=iid, DBClusterIdentifier=cid,
                               DBInstanceClass="db.serverless", Engine="aurora-postgresql")
    print(f"cluster {cid} ready")


def delete(spec):
    rds = boto3.client("rds")
    cid = spec["cluster_identifier"]
    try:
        rds.delete_db_instance(DBInstanceIdentifier=f"{cid}-1", SkipFinalSnapshot=True)
    except rds.exceptions.DBInstanceNotFoundFault:
        pass
    for _ in range(120):
        try:
            rds.describe_db_instances(DBInstanceIdentifier=f"{cid}-1")
            time.sleep(1)
        except rds.exceptions.DBInstanceNotFoundFault:
            break
    try:
        rds.delete_db_cluster(DBClusterIdentifier=cid, SkipFinalSnapshot=True)
    except rds.exceptions.DBClusterNotFoundFault:
        pass
    for _ in range(120):  # the subnet group can only be deleted once the cluster is gone
        try:
            rds.describe_db_clusters(DBClusterIdentifier=cid)
            time.sleep(1)
        except rds.exceptions.DBClusterNotFoundFault:
            break
    print(f"cluster {cid} deleted")


if __name__ == "__main__":
    {"ensure": ensure, "delete": delete}[sys.argv[1]](json.loads(sys.argv[2]))
