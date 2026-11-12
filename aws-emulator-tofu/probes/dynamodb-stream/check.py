from lib import client, logs_contain, result

TITLE = "DynamoDB table + stream -> Lambda"
CATEGORY = "Event sources"
AWS_EXPECTED = "PutItem produces an INSERT stream record delivered to the Lambda."
FINDINGS = []


def check(outputs, row):
    ddb = client("dynamodb")
    ddb.put_item(TableName=outputs["table"], Item={"pk": {"S": "ddb-probe-item"}})
    got = ddb.get_item(TableName=outputs["table"], Key={"pk": {"S": "ddb-probe-item"}}).get("Item")
    hit = logs_contain(outputs["log_group"], "ddb-probe-item", timeout=45)
    if got and hit:
        return result("works", "CRUD ok; stream record delivered")
    return result("partial" if got else "gap", f"get_item={bool(got)} stream_delivered={bool(hit)}")
