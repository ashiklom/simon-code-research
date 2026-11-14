import time

import boto3
from lib import client, result

TITLE = "IAM: AWS-managed policy catalog (attach, GetPolicy, and what an unknown managed ARN grants)"
CATEGORY = "IAM"
AWS_EXPECTED = ("Every arn:aws:iam::aws:policy/* policy exists (GetPolicy 200) and grants exactly its document "
                "(ViewOnlyAccess: list/describe only; AWSBillingReadOnlyAccess: billing reads only). Attaching an "
                "ARN that names no policy fails with NoSuchEntity.")
FINDINGS = ["iam-unknown-managed-policy-fails-open"]


def as_user(key, service):
    return boto3.Session(aws_access_key_id=key["id"], aws_secret_access_key=key["secret"]).client(service)


def allowed(fn):
    try:
        fn()
        return True
    except Exception as e:  # noqa: BLE001
        if "AccessDenied" in str(e) or "not authorized" in str(e):
            return False
        return f"error: {type(e).__name__}: {str(e)[:80]}"


def check(outputs, row):
    if not outputs:
        return result("gap", "apply failed: " + str((row.get("apply") or {}).get("error"))[:300])
    time.sleep(1)
    iam, bucket, c = client("iam"), outputs["bucket"], {}
    for name, arn in outputs["policies"].items():
        try:
            iam.get_policy(PolicyArn=arn)
            got = "200"
        except iam.exceptions.NoSuchEntityException:
            got = "NoSuchEntity"
        k = outputs["keys"][name]
        c[name] = {
            "GetPolicy": got,
            "iam:ListRoles": allowed(lambda: as_user(k, "iam").list_roles()),
            "iam:CreateUser": allowed(lambda: as_user(k, "iam").create_user(UserName=f"probe-victim-{name}")),
            "s3:PutObject": allowed(lambda: as_user(k, "s3").put_object(Bucket=bucket, Key=f"{name}.txt", Body=b"x")),
        }
        for u in (f"probe-victim-{name}",):
            try:
                iam.delete_user(UserName=u)
            except Exception:  # noqa: BLE001
                pass
    good = {
        "catalog policy enforced": c["catalog"]["iam:ListRoles"] is True and c["catalog"]["iam:CreateUser"] is False,
        "missing AWS policy readable": c["missing"]["GetPolicy"] == "200",
        "missing AWS policy grants no writes": c["missing"]["iam:CreateUser"] is False
        and c["missing"]["s3:PutObject"] is False,
        "bogus ARN refused (AWS: apply fails)": False,  # it was attached if we got here
        "bogus ARN grants nothing": c["bogus"]["iam:CreateUser"] is False and c["bogus"]["s3:PutObject"] is False,
    }
    n = sum(good.values())
    return result("works" if n == len(good) else ("partial" if n else "gap"),
                  "; ".join(f"{k}: {v}" for k, v in c.items()), checks=good)
