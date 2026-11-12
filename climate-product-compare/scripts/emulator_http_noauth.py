"""Icechunk HTTPS (read-only) backend against an S3-style origin: second emulator with --auth off.

Copies the subset repos made by emulator_check.py into a bucket of the auth-off emulator, then
reads them with Icechunk's HTTP storage (anonymous range GETs) and compares with the S3 reads.
Usage: uv run --with boto3 python scripts/emulator_http_noauth.py --port 9298
"""
import argparse, json, os, sys, tempfile, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
import emulator_check as E  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=9298)
    a = ap.parse_args()
    env = E.emulator_env(a.port)
    for k in ("AWS_SESSION_TOKEN", "AWS_PROFILE"):
        os.environ.pop(k, None)
    os.environ.update(env)
    import boto3
    import icechunk

    icechunk.set_logs_filter("error")
    from cpc import store

    local_root = f"file://{tempfile.mkdtemp(prefix='cpc-subsets-')}"
    subsets = E.build_subsets(local_root, print)
    s3 = boto3.client("s3")
    if "cpc-http" not in [b["Name"] for b in s3.list_buckets().get("Buckets", [])]:
        s3.create_bucket(Bucket="cpc-http")
    # new buckets (and the account) block public policies by default, as on AWS
    s3.delete_public_access_block(Bucket="cpc-http")
    try:
        boto3.client("s3control").delete_public_access_block(AccountId="000000000000")
    except Exception as e:
        print("account-level public access block:", repr(e)[:200])
    s3.put_bucket_policy(Bucket="cpc-http", Policy=json.dumps({"Version": "2012-10-17", "Statement": [{
        "Sid": "PublicRead", "Effect": "Allow", "Principal": "*", "Action": "s3:GetObject",
        "Resource": "arn:aws:s3:::cpc-http/*"}]}))
    store.copy_store(local_root, f"s3://cpc-http/store?region=us-east-1&endpoint={env['AWS_ENDPOINT_URL']}&force_path_style=1")
    out = {}
    base = f"{env['AWS_ENDPOINT_URL']}/cpc-http/store"
    for kind, name, path, n in subsets:
        t = time.time()
        try:
            remote = store.read_group(store.open_repo(store.repo_name(kind, name), base, create=False).readonly_session("main"), path)
            diff = E.compare(store.read_group(store.readonly(kind, name, local_root), path), remote)
            out[f"{kind}-{name}"] = {"read_seconds": round(time.time() - t, 2), "max_abs_diff": diff}
        except Exception as e:
            out[f"{kind}-{name}"] = {"error": repr(e)[:300]}
        print(f"HTTPS (auth-off emulator) {kind}-{name}: {out[f'{kind}-{name}']}")
    p = ROOT / "results" / "emulator_check.json"
    rep = json.loads(p.read_text())
    rep["https_auth_off_emulator"] = {"base_url": base, **out}
    p.write_text(json.dumps(rep, indent=1, default=str))


if __name__ == "__main__":
    main()
