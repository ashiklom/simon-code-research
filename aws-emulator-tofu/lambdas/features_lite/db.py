"""Database access through the RDS Data API (HTTPS; no sockets needed, so it works on
aws-emulator's RustPython Lambda runtime, where asyncpg/psycopg cannot run)."""
import os


def _param(name, v):
    if v is None:
        val = {"isNull": True}
    elif isinstance(v, bool):
        val = {"booleanValue": v}
    elif isinstance(v, int):
        val = {"longValue": v}
    elif isinstance(v, float):
        val = {"doubleValue": v}
    else:
        val = {"stringValue": str(v)}
    return {"name": name, "value": val}


def _value(f):
    if f.get("isNull"):
        return None
    for k in ("stringValue", "longValue", "doubleValue", "booleanValue"):
        if k in f:
            return f[k]
    return None


class DataAPI:
    def __init__(self, cluster_arn=None, secret_arn=None, database=None):
        import boto3
        self.client = boto3.client("rds-data")
        self.cluster_arn = cluster_arn or os.environ["DB_CLUSTER_ARN"]
        self.secret_arn = secret_arn or os.environ["DB_SECRET_ARN"]
        self.database = database or os.environ.get("DB_NAME", "features")

    def query(self, sql, params=None):
        r = self.client.execute_statement(
            resourceArn=self.cluster_arn, secretArn=self.secret_arn, database=self.database, sql=sql,
            parameters=[_param(k, v) for k, v in (params or {}).items()], includeResultMetadata=True)
        cols = [c["label"] or c["name"] for c in r.get("columnMetadata", [])]
        return [dict(zip(cols, (_value(f) for f in rec))) for rec in r.get("records", [])]
