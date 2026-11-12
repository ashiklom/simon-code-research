from lib import client, result

TITLE = "aws_s3_bucket with default provider settings (S3 Control tag read)"
CATEGORY = "OpenTofu provider x emulator"
AWS_EXPECTED = "Bucket created in seconds; tags read via {account}.s3-control.<region>.amazonaws.com."
FINDINGS = ["tofu-s3control-host-prefix"]
TF_VARS = {"skip_account_id": "false"}
APPLY_TIMEOUT = 90
EXPECT_APPLY_FAILURE = True


def check(outputs, row):
    exists = "probe-s3control-tagging" in [b["Name"] for b in client("s3").list_buckets()["Buckets"]]
    if row["apply"]["ok"]:
        return result("works", "apply finished")
    client("s3").delete_bucket(Bucket="probe-s3control-tagging") if exists else None
    return result("gap", f"apply never finished (provider retries S3 Control ListTagsForResource against "
                         f"000000000000.127.0.0.1:9297); bucket itself was created: {exists}. Workaround: "
                         "skip_credentials_validation + skip_requesting_account_id.")
