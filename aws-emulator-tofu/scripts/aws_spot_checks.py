#!/usr/bin/env python3
"""Spot-check emulator findings against REAL AWS, through a live Cognito user pool -> identity
pool -> IAM role setup of the same shape as this experiment's stack (the YCGS service-credentials
stack used by `ycgs-aws-creds`).

Needs: the aws CLI, `ycgs-aws-creds`, profiles ycgs-all-buckets-reader / -writer in ~/.aws/config,
YCGS_AWS_RO_PASS. Writes results/aws_spot_checks.json. Everything it creates (one scratch S3
object of 20 MB) is deleted again. Run: python3 scripts/aws_spot_checks.py

Only checks that need no deploy permissions are possible: the available roles can read/write S3
buckets, nothing else, so API Gateway / Lambda / CloudFront findings stay emulator-only.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import subprocess
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
OUT = HERE / "results" / "aws_spot_checks.json"
READER, WRITER = "ycgs-all-buckets-reader", "ycgs-all-buckets-writer"
PUBLIC_BUCKET = "ycgs-use1-public"
PRIVATE_BUCKET = "ycgs-aws-misc"
SCRATCH = "simon-code-research/_aws_spot_checks"


def run(*cmd, check=False, env=None):
    p = subprocess.run(cmd, capture_output=True, text=True, env={**os.environ, **(env or {})})
    if check and p.returncode:
        raise RuntimeError(f"{cmd}: {p.stderr}")
    return p


def aws(profile, *args):
    return run("aws", "--profile", profile, *args)


def check_off_group_role():
    """cognito-identity-pool-roles: a CustomRoleArn outside the user's groups is refused."""
    p = run("ycgs-aws-creds", "--role", "all-buckets-writer", "--user", "read-cost",
            "--password-cmd", "printenv YCGS_AWS_RO_PASS")
    ok = p.returncode != 0 and ("InvalidIdentityPoolConfiguration" in p.stderr or "not" in p.stderr.lower())
    return ok, (p.stderr or p.stdout).strip().splitlines()[-1][:300]


def check_session_shape():
    """cognito-identity-pool-roles: sessions are assumed-role/<role>/CognitoIdentityCredentials, ~1 h."""
    arn = json.loads(aws(READER, "sts", "get-caller-identity").stdout)["Arn"]
    creds = json.loads(aws(READER, "configure", "export-credentials", "--format", "process").stdout)
    exp = dt.datetime.fromisoformat(creds["Expiration"].replace("Z", "+00:00"))
    ok = arn.endswith(":assumed-role/all-buckets-reader/CognitoIdentityCredentials")
    return ok, f"{arn.split(':', 5)[-1]}; credentials expire in <= {round((exp - dt.datetime.now(dt.timezone.utc)).total_seconds() / 60)} min (cached)"


def check_implicit_deny():
    """iam/cognito: the reader role's policy has no s3:PutObject -> implicit deny."""
    with tempfile.NamedTemporaryFile() as f:
        f.write(b"x")
        f.flush()
        p = aws(READER, "s3api", "put-object", "--bucket", PRIVATE_BUCKET, "--key", f"{SCRATCH}/reader.txt", "--body", f.name)
    msg = p.stderr.strip().splitlines()[-1] if p.stderr else ""
    return p.returncode != 0 and "no identity-based policy allows the s3:PutObject action" in msg, msg[-220:]


def check_explicit_deny():
    """Explicit Deny in a bucket policy (aws:SecureTransport=false) beats the role's Allow."""
    p = aws(WRITER, "s3api", "get-object", "--bucket", PUBLIC_BUCKET, "--key", "_healthcheck.txt",
            "--endpoint-url", "http://s3.us-east-1.amazonaws.com", "/dev/null")
    msg = (p.stderr or "").strip().splitlines()[-1] if p.stderr else "succeeded"
    return p.returncode != 0 and "explicit deny" in msg, msg[-260:]


def check_virtual_host_and_range():
    """s3-virtual-host-tls: virtual-hosted-style HTTPS, Range GET 206, presigned GET on a private bucket."""
    key = f"{SCRATCH}/range.txt"
    with tempfile.NamedTemporaryFile() as f:
        f.write(b"0123456789" * 10)
        f.flush()
        aws(WRITER, "s3api", "put-object", "--bucket", PRIVATE_BUCKET, "--key", key, "--body", f.name)
    url = aws(WRITER, "s3", "presign", f"s3://{PRIVATE_BUCKET}/{key}", "--expires-in", "300").stdout.strip()
    host_ok = url.startswith(f"https://{PRIVATE_BUCKET}.s3.")
    req = urllib.request.Request(url, headers={"Range": "bytes=10-19"})
    with urllib.request.urlopen(req, timeout=30) as r:
        status, body = r.status, r.read()
    try:
        urllib.request.urlopen(f"https://{PRIVATE_BUCKET}.s3.amazonaws.com/{key}", timeout=30)
        anon = "200 (unexpected)"
    except urllib.error.HTTPError as e:
        anon = str(e.code)
    aws(WRITER, "s3api", "delete-object", "--bucket", PRIVATE_BUCKET, "--key", key)
    ok = host_ok and status == 206 and body == b"0123456789" and anon == "403"
    return ok, f"presigned host {url.split('/')[2]}; ranged GET {status} {body!r}; anonymous GET on private bucket {anon}"


def check_multipart_etag():
    """s3-multipart-etag: a multipart upload's ETag is '<hex>-<parts>', not the file MD5."""
    key = f"{SCRATCH}/multipart.bin"
    with tempfile.NamedTemporaryFile() as f:
        data = os.urandom(20 * 1024 * 1024)
        f.write(data)
        f.flush()
        aws(WRITER, "s3", "cp", f.name, f"s3://{PRIVATE_BUCKET}/{key}", "--only-show-errors")
    etag = json.loads(aws(WRITER, "s3api", "head-object", "--bucket", PRIVATE_BUCKET, "--key", key).stdout)["ETag"].strip('"')
    aws(WRITER, "s3api", "delete-object", "--bucket", PRIVATE_BUCKET, "--key", key)
    md5 = hashlib.md5(data).hexdigest()
    return ("-" in etag and etag != md5), f"ETag {etag} vs MD5 {md5} (20 MiB via aws s3 cp, 8 MiB parts)"


def check_identity_pool_roles_api():
    """GetIdentityPoolRoles (needed to learn the pool's fallback role) is an IAM-authorized call."""
    cfg = json.loads(Path(os.path.expanduser("~/.config/ycgs-aws-creds/config.json")).read_text())
    p = aws(READER, "cognito-identity", "get-identity-pool-roles", "--identity-pool-id", cfg["identity_pool_id"])
    msg = (p.stderr or p.stdout).strip().splitlines()[-1][:200]
    return None, f"{'denied' if p.returncode else 'allowed'}: {msg.split(':')[0] if p.returncode else 'roles listed'}"


CHECKS = [
    ("cognito-identity-pool-roles", "role outside the user's groups is refused", check_off_group_role),
    ("cognito-identity-pool-roles", "session ARN and lifetime", check_session_shape),
    ("cognito-identity-pool-roles", "implicit deny enforced on S3 for the vended role", check_implicit_deny),
    ("iam-enforced-in-lambda", "explicit Deny (bucket policy) beats the role's Allow", check_explicit_deny),
    ("s3-virtual-host-tls", "virtual-hosted HTTPS, presigned URL, ranged GET, anonymous 403", check_virtual_host_and_range),
    ("s3-multipart-etag", "multipart ETag is not the MD5", check_multipart_etag),
    ("cognito-identity-pool-roles", "fallback-role check possible? (GetIdentityPoolRoles)", check_identity_pool_roles_api),
]


def main():
    out = []
    for fid, what, fn in CHECKS:
        try:
            ok, detail = fn()
        except Exception as e:  # record, keep going
            ok, detail = False, f"error: {e!r}"[:300]
        out.append({"finding": fid, "check": what, "matches_documented_aws": ok, "detail": detail})
        print(f"{'PASS' if ok else ('INFO' if ok is None else 'FAIL')}  {fid}: {what}\n      {detail}")
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps({"date": dt.date.today().isoformat(), "account": "YCGS (Cognito service-credentials stack)",
                               "checks": out}, indent=1) + "\n")
    print(f"wrote {OUT.relative_to(HERE)}")


if __name__ == "__main__":
    main()
