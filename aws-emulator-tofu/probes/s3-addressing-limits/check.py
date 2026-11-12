import os

from botocore.config import Config

from lib import ENDPOINT, client, result, session

import boto3

TITLE = "S3: presigned URLs, virtual-host addressing, Range GET, object size/bucket capacity"
CATEGORY = "S3"
AWS_EXPECTED = ("Presigned GET works; virtual-hosted URL works; Range GET -> 206; a 70 MiB object and a 130 MiB "
                "total upload succeed (5 TB object limit, unlimited bucket).")
FINDINGS = ["s3-capacity-limits", "s3-virtual-host-tls"]


def check(outputs, row):
    b = outputs["bucket"]
    s3 = client("s3")
    S = session()
    c = {}
    url = s3.generate_presigned_url("get_object", Params={"Bucket": b, "Key": "hello.txt"}, ExpiresIn=60)
    r = S.get(url)
    c["presigned GET"] = f"{r.status_code} {r.text[:10]}"
    r = S.get(ENDPOINT + f"/{b}/hello.txt", headers={"Range": "bytes=1-3"})
    c["anonymous GET (private bucket)"] = r.status_code
    rr = s3.get_object(Bucket=b, Key="hello.txt", Range="bytes=1-3")
    c["Range GET"] = f"{rr['ResponseMetadata']['HTTPStatusCode']} {rr['Body'].read()!r}"
    # botocore silently uses path style for IP-literal endpoints, so use a hostname endpoint.
    vh = boto3.client("s3", endpoint_url=ENDPOINT.replace("127.0.0.1", "localhost"),
                      config=Config(s3={"addressing_style": "virtual"}, retries={"max_attempts": 1}))
    try:
        vh.head_object(Bucket=b, Key="hello.txt")
        c["virtual-host addressing"] = "ok"
    except Exception as e:  # noqa: BLE001
        c["virtual-host addressing"] = f"{type(e).__name__}: {str(e)[:90]}"
    big = os.urandom(70 * 1024 * 1024)
    try:
        s3.put_object(Bucket=b, Key="big70.bin", Body=big)
        c["70 MiB object"] = "ok"
    except Exception as e:  # noqa: BLE001
        c["70 MiB object"] = f"{type(e).__name__}: {str(e)[:120]}"
    tot = 0
    err = None
    for i in range(14):
        try:
            s3.put_object(Bucket=b, Key=f"chunk{i}.bin", Body=big[: 10 * 1024 * 1024])
            tot += 10
        except Exception as e:  # noqa: BLE001
            err = f"{type(e).__name__}: {str(e)[:120]}"
            break
    c["total stored in 10 MiB objects before error (MiB)"] = f"{tot} ({err})"
    good = (c["presigned GET"].startswith("200") and c["virtual-host addressing"] == "ok" and c["70 MiB object"] == "ok"
            and err is None)
    for o in s3.list_object_versions(Bucket=b).get("Versions", []):
        if o["Key"] != "hello.txt":  # keep the tofu-managed object
            s3.delete_object(Bucket=b, Key=o["Key"], VersionId=o["VersionId"])
    return result("works" if good else "partial", "; ".join(f"{k}: {v}" for k, v in c.items()))
