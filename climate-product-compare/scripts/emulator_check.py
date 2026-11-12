"""Check the S3 and HTTPS (CloudFront-in-front-of-S3) store backends against AWS Emulator.

Usage (emulator already running, e.g. `aws-emulator -p 9297 --telemetry off`):
    uv run --with boto3 python scripts/emulator_check.py [--port 9297]

1. Builds small subset repos (a few sites, a couple of years) from the local store.
2. Creates a bucket in the emulator and copies them there with store.copy_store (s3://... root).
3. Reads them back through the s3:// backend and compares with the local subset.
4. Creates a CloudFront distribution with the bucket as origin and tries to read the same
   repos through Icechunk's read-only HTTP storage (https:// root).
Writes results/emulator_check.md.
"""

from __future__ import annotations

import argparse
import configparser
import json
import os
import sys
import tempfile
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

SUBSETS = [  # (kind, name, sites, t0, t1)
    ("products", "chirps3", ["USCRN:03047", "USCRN:04223", "USCRN:94645"], "2020-01-01", "2021-12-31"),
    ("products", "era5land", ["USCRN:03047", "USCRN:04223", "USCRN:94645"], "2020-01-01", "2021-12-31"),
    ("products", "hrrr", ["USCRN:03047", "USCRN:04223"], "2023-01-01", "2023-12-31"),
    ("obs", "USCRN", ["USCRN:03047", "USCRN:04223", "USCRN:94645"], "2020-01-01", "2021-12-31"),
]
BUCKET = "cpc-store-test"
PREFIX = "store"


def emulator_env(port: int) -> dict:
    d = Path.home() / ".aws" / "emulator" / str(port)
    cred = configparser.ConfigParser()
    cred.read(d / "emulator_credentials")
    # with --auth off the emulator writes no keys; any key works then
    sec = cred[cred.sections()[0]] if cred.sections() else {"aws_access_key_id": "test", "aws_secret_access_key": "test"}
    # trust both the agent proxy CA (for normal internet traffic) and the emulator's self-signed CA
    bundle = Path(tempfile.gettempdir()) / f"cpc-emulator-{port}-bundle.pem"
    base = os.environ.get("SSL_CERT_FILE") or os.environ.get("REQUESTS_CA_BUNDLE") or "/etc/ssl/certs/ca-certificates.crt"
    bundle.write_text(Path(base).read_text() + "\n" + (d / "ca.pem").read_text())
    return {
        "AWS_ENDPOINT_URL": f"https://127.0.0.1:{port}",
        "AWS_ACCESS_KEY_ID": sec["aws_access_key_id"],
        "AWS_SECRET_ACCESS_KEY": sec["aws_secret_access_key"],
        "AWS_REGION": "us-east-1", "AWS_DEFAULT_REGION": "us-east-1",
        "AWS_EC2_METADATA_DISABLED": "true", "AWS_DISABLE_HOST_PREFIX_INJECTION": "true",
        "AWS_CA_BUNDLE": str(bundle), "SSL_CERT_FILE": str(bundle), "REQUESTS_CA_BUNDLE": str(bundle),
    }


def build_subsets(local_root: str, log) -> list[tuple]:
    import numpy as np  # noqa: F401
    import pandas as pd

    from cpc import store
    from cpc.products import registry

    done = []
    for kind, name, sites, t0, t1 in SUBSETS:
        freq = registry.get(name).freq if kind == "products" else "1h"
        path = store.group_path(kind, name, freq)
        src = store.readonly(kind, name)
        ds = store.read_group(src, path, sites=sites, t0=t0, t1=t1)
        repo = store.open_repo(store.repo_name(kind, name), local_root)
        s = repo.writable_session("main")
        w = store.GroupWriter(s, path, freq, has_px=(kind == "products"),
                              attrs={k: v for k, v in ds.attrs.items() if k not in ("site_end",)})
        if kind == "products":
            w.write_stencil(list(ds.site.values), ds.px_lat.values, ds.px_lon.values, ds.w.values,
                            ds.get("px_elev", None) if "px_elev" in ds else None)
        vmeta = ds.attrs.get("variables", {})
        specs = {v: store.VarSpec(v, m.get("kind"), m.get("units", ""), {}) for v, m in vmeta.items() if v in ds}
        w.write(list(ds.site.values), pd.DatetimeIndex(ds.time.values), {v: ds[v].values for v in specs}, specs)
        s.commit(f"subset of {name}")
        n = sum(ds[v].size for v in specs)
        log(f"subset {kind}-{name}: {len(sites)} sites, {ds.sizes['time']} steps, {len(specs)} vars, {n:,} values")
        done.append((kind, name, path, n))
    return done


def compare(a, b) -> float:
    import numpy as np

    worst = 0.0
    for v in a.data_vars:
        x, y = a[v].values, b[v].values
        if x.shape != y.shape:
            return float("inf")
        m = np.isfinite(x) | np.isfinite(y)
        if m.any():
            worst = max(worst, float(np.nanmax(np.abs(np.where(m, x, 0) - np.where(m, y, 0)))))
    return worst


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=9297)
    args = ap.parse_args()
    env = emulator_env(args.port)
    for k in ("AWS_SESSION_TOKEN", "AWS_PROFILE", "AWS_SECURITY_TOKEN"):  # never mix in real credentials
        os.environ.pop(k, None)
    os.environ.update(env)
    lines: list[str] = []

    def log(msg):
        print(msg, flush=True)
        lines.append(msg)

    import boto3
    import icechunk

    icechunk.set_logs_filter("error")
    from cpc import store

    report = {"s3": {}, "cloudfront": {}}
    local = tempfile.mkdtemp(prefix="cpc-subsets-")
    local_root = f"file://{local}"
    subsets = build_subsets(local_root, log)

    # ---- S3 ------------------------------------------------------------------------------
    s3 = boto3.client("s3")
    if BUCKET not in [b["Name"] for b in s3.list_buckets().get("Buckets", [])]:
        s3.create_bucket(Bucket=BUCKET)
    s3_root = f"s3://{BUCKET}/{PREFIX}?region=us-east-1&endpoint={env['AWS_ENDPOINT_URL']}&force_path_style=1"
    t = time.time()
    try:
        store.copy_store(local_root, s3_root)
        report["s3"]["copy_seconds"] = round(time.time() - t, 1)
        objs = s3.get_paginator("list_objects_v2").paginate(Bucket=BUCKET, Prefix=PREFIX)
        keys = [o for page in objs for o in page.get("Contents", [])]
        report["s3"]["objects"] = len(keys)
        report["s3"]["bytes"] = sum(o["Size"] for o in keys)
        log(f"S3 copy: {len(keys)} objects, {report['s3']['bytes'] / 1e6:.1f} MB in {report['s3']['copy_seconds']} s")
        for kind, name, path, n in subsets:
            t = time.time()
            remote = store.read_group(store.readonly(kind, name, s3_root), path)
            dt = time.time() - t
            local_ds = store.read_group(store.readonly(kind, name, local_root), path)
            diff = compare(local_ds, remote)
            report["s3"][f"{kind}-{name}"] = {"read_seconds": round(dt, 2), "max_abs_diff": diff, "values": n}
            log(f"S3 read {kind}-{name}: {dt:.2f} s, max |diff| vs local = {diff}")
        report["s3"]["ok"] = all(v["max_abs_diff"] == 0 for k, v in report["s3"].items() if isinstance(v, dict))
    except Exception as e:
        report["s3"]["error"] = repr(e)
        log("S3 FAILED: " + traceback.format_exc())

    # ---- CloudFront in front of the bucket (Origin Access Control, private bucket) -----------
    import requests

    def http_read_all(base: str, label: str, section: dict):
        for kind, name, path, n in subsets:
            t = time.time()
            try:
                sess = store.open_repo(store.repo_name(kind, name), base, create=False).readonly_session("main")
                remote = store.read_group(sess, path)
                diff = compare(store.read_group(store.readonly(kind, name, local_root), path), remote)
                section[f"{kind}-{name}"] = {"read_seconds": round(time.time() - t, 2), "max_abs_diff": diff}
                log(f"{label} read {kind}-{name}: {time.time() - t:.2f} s, max |diff| vs local = {diff}")
            except Exception as e:
                section[f"{kind}-{name}"] = {"error": repr(e)[:300]}
                log(f"{label} read {kind}-{name} FAILED: {e!r}"[:300])

    cf = boto3.client("cloudfront")
    rep = report["cloudfront"]
    try:
        oac = cf.create_origin_access_control(OriginAccessControlConfig={
            "Name": f"cpc-oac-{int(time.time())}", "SigningProtocol": "sigv4", "SigningBehavior": "always",
            "OriginAccessControlOriginType": "s3"})["OriginAccessControl"]
        dist = cf.create_distribution(DistributionConfig={
            "CallerReference": str(time.time()), "Comment": "cpc store test", "Enabled": True,
            "Origins": {"Quantity": 1, "Items": [{
                "Id": "s3", "DomainName": f"{BUCKET}.s3.us-east-1.amazonaws.com",
                "S3OriginConfig": {"OriginAccessIdentity": ""}, "OriginAccessControlId": oac["Id"]}]},
            "DefaultCacheBehavior": {"TargetOriginId": "s3", "ViewerProtocolPolicy": "allow-all",
                                     "ForwardedValues": {"QueryString": False, "Cookies": {"Forward": "none"}},
                                     "MinTTL": 0, "TrustedSigners": {"Enabled": False, "Quantity": 0}},
        })["Distribution"]
        rep["distribution"] = {"Id": dist["Id"], "DomainName": dist["DomainName"], "ARN": dist["ARN"], "Status": dist["Status"]}
        log(f"CloudFront distribution {dist['Id']} at {dist['DomainName']} (status {dist['Status']}), OAC {oac['Id']}")
        s3.put_bucket_policy(Bucket=BUCKET, Policy=json.dumps({"Version": "2012-10-17", "Statement": [{
            "Sid": "AllowCloudFrontOAC", "Effect": "Allow", "Principal": {"Service": "cloudfront.amazonaws.com"},
            "Action": "s3:GetObject", "Resource": f"arn:aws:s3:::{BUCKET}/*",
            "Condition": {"StringEquals": {"AWS:SourceArn": dist["ARN"]}}}]}))
        key = f"{PREFIX}/products-chirps3.icechunk/repo"
        for scheme in ("https", "http"):
            url = f"{scheme}://{dist['DomainName']}/{key}"
            try:
                r = requests.get(url, timeout=20, verify=env["AWS_CA_BUNDLE"])
                rep[f"GET {scheme}"] = {"status": r.status_code, "bytes": len(r.content), "x-cache": r.headers.get("x-cache"),
                                        "body": r.text[:150] if r.status_code != 200 else ""}
                log(f"CloudFront {scheme} GET {key}: HTTP {r.status_code}, {len(r.content)} B, x-cache={r.headers.get('x-cache')}")
            except Exception as e:
                rep[f"GET {scheme}"] = {"error": repr(e)[:200]}
                log(f"CloudFront {scheme} GET failed: {e!r}"[:300])
        ok = [sch for sch in ("https", "http") if rep.get(f"GET {sch}", {}).get("status") == 200]
        if ok:
            http_read_all(f"{ok[0]}://{dist['DomainName']}/{PREFIX}", "CloudFront/Icechunk-HTTP", rep)
            # second pass: should come from the CloudFront cache
            r = requests.get(f"{ok[0]}://{dist['DomainName']}/{key}", timeout=20, verify=env["AWS_CA_BUNDLE"])
            rep["second_GET_x-cache"] = r.headers.get("x-cache")
        # the bucket itself must stay private: anonymous GET on the S3 endpoint should be denied
        r = requests.get(f"{env['AWS_ENDPOINT_URL']}/{BUCKET}/{key}", timeout=20, verify=env["AWS_CA_BUNDLE"])
        rep["anonymous_direct_S3_GET_status"] = r.status_code
        log(f"Anonymous direct S3 GET (bucket private, OAC only): HTTP {r.status_code}")
    except Exception as e:
        rep["error"] = repr(e)
        log("CloudFront FAILED: " + traceback.format_exc())

    # ---- Public-read bucket read directly over HTTPS (no CloudFront) ------------------------
    pub = report["https_public_bucket"] = {}
    try:
        pb = BUCKET + "-public"
        if pb not in [b["Name"] for b in s3.list_buckets().get("Buckets", [])]:
            s3.create_bucket(Bucket=pb)
        try:
            s3.delete_public_access_block(Bucket=pb)
        except Exception:
            pass
        s3.put_bucket_policy(Bucket=pb, Policy=json.dumps({"Version": "2012-10-17", "Statement": [{
            "Sid": "PublicRead", "Effect": "Allow", "Principal": "*", "Action": "s3:GetObject",
            "Resource": f"arn:aws:s3:::{pb}/*"}]}))
        store.copy_store(local_root, f"s3://{pb}/{PREFIX}?region=us-east-1&endpoint={env['AWS_ENDPOINT_URL']}&force_path_style=1")
        http_read_all(f"{env['AWS_ENDPOINT_URL']}/{pb}/{PREFIX}", "Public bucket/Icechunk-HTTP", pub)
    except Exception as e:
        pub["error"] = repr(e)
        log("Public bucket FAILED: " + traceback.format_exc())

    out = ROOT / "results" / "emulator_check.json"
    out.write_text(json.dumps(report, indent=1, default=str))
    log(f"wrote {out}")


if __name__ == "__main__":
    main()
