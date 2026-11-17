import time

import boto3
from lib import result

TITLE = "S3 GetObjectAttributes without s3:GetObject"
CATEGORY = "S3"
AWS_EXPECTED = ("GetObjectAttributes needs s3:GetObject as well as s3:GetObjectAttributes (unversioned objects); with "
                "only the latter it is AccessDenied (seen on AWS: 'no identity-based policy allows the s3:GetObject "
                "action'). ListObjectsV2 still returns Size/LastModified/StorageClass.")
FINDINGS = ["s3-getobjectattributes-no-getobject-check"]


def check(outputs, row):
    if not outputs:
        return result("gap", "apply failed: " + str((row.get("apply") or {}).get("error"))[:300])
    time.sleep(1)
    k = outputs["key"]
    s3 = boto3.Session(aws_access_key_id=k["id"], aws_secret_access_key=k["secret"]).client("s3")
    c = {}
    for name, fn in {
        "ListObjectsV2": lambda: s3.list_objects_v2(Bucket=outputs["bucket"]),
        "GetObjectAttributes": lambda: s3.get_object_attributes(Bucket=outputs["bucket"], Key="data/x.txt",
                                                                ObjectAttributes=["ObjectSize"]),
        "GetObject": lambda: s3.get_object(Bucket=outputs["bucket"], Key="data/x.txt"),
    }.items():
        try:
            fn()
            c[name] = "allowed"
        except Exception as e:  # noqa: BLE001
            c[name] = type(e).__name__ + (": AccessDenied" if "AccessDenied" in str(e) else "")
    good = {"list allowed": c["ListObjectsV2"] == "allowed",
            "GetObject denied": c["GetObject"] != "allowed",
            "GetObjectAttributes denied (needs s3:GetObject)": c["GetObjectAttributes"] != "allowed"}
    n = sum(good.values())
    return result("works" if n == len(good) else ("partial" if n else "gap"),
                  "; ".join(f"{k}: {v}" for k, v in c.items()), checks=good)
