"""Measure an OpenTofu deploy cycle against aws-emulator -> results/deploy.json.

fresh state -> apply (timed) -> plan -detailed-exitcode (drift) -> destroy (timed) -> leftover scan
-> apply again (so later steps have a stack). Assumes the emulator env is loaded
(eval "$(scripts/emulator.sh env)").
"""
from __future__ import annotations

import collections
import json
import re
import subprocess
import time
from pathlib import Path

import boto3

ROOT = Path(__file__).resolve().parent.parent
INFRA = ROOT / "infra"


def tofu(*args, check=True):
    t0 = time.time()
    p = subprocess.run(["tofu", *args, "-no-color", "-input=false"], cwd=INFRA, capture_output=True, text=True)
    dt = time.time() - t0
    if check and p.returncode not in (0, 2):
        print(p.stdout[-4000:], p.stderr[-4000:])
        raise SystemExit(f"tofu {args[0]} failed")
    return p, dt


def leftovers():
    """Resources of the stack's kinds still present after destroy."""
    out = {}
    out["lambda_functions"] = [f["FunctionName"] for f in boto3.client("lambda").list_functions()["Functions"]]
    out["rest_apis"] = [a["name"] for a in boto3.client("apigateway").get_rest_apis()["items"]]
    out["user_pools"] = [p["Name"] for p in boto3.client("cognito-idp").list_user_pools(MaxResults=60)["UserPools"]]
    out["buckets"] = [b["Name"] for b in boto3.client("s3").list_buckets()["Buckets"]]
    out["db_clusters"] = [c["DBClusterIdentifier"] for c in boto3.client("rds").describe_db_clusters()["DBClusters"]]
    out["distributions"] = [d["Id"] for d in (boto3.client("cloudfront").list_distributions()["DistributionList"].get("Items") or [])]
    out["iam_roles"] = [r["RoleName"] for r in boto3.client("iam").list_roles()["Roles"] if r["RoleName"].startswith("aet-")]
    out["log_groups"] = [g["logGroupName"] for g in boto3.client("logs").describe_log_groups()["logGroups"]]
    out["secrets"] = [s["Name"] for s in boto3.client("secretsmanager").list_secrets()["SecretList"]]
    out["vpcs"] = [v["VpcId"] for v in boto3.client("ec2").describe_vpcs()["Vpcs"] if not v.get("IsDefault")]
    return {k: v for k, v in out.items() if v}


def main():
    for f in INFRA.glob("terraform.tfstate*"):
        f.unlink()
    p, t_apply = tofu("apply", "-auto-approve")
    m = re.search(r"Resources: (\d+) added, (\d+) changed, (\d+) destroyed", p.stdout)
    state = subprocess.run(["tofu", "state", "list"], cwd=INFRA, capture_output=True, text=True).stdout.split()
    types = collections.Counter(re.sub(r"\[.*", "", s).split(".")[-2] for s in state if not s.startswith("data."))
    p_plan, t_plan = tofu("plan", "-detailed-exitcode", check=False)
    drift = re.findall(r"^  # (\S+) (?:will be|must be)", p_plan.stdout, re.M)
    p_destroy, t_destroy = tofu("destroy", "-auto-approve", check=False)
    md = re.search(r"Resources: (\d+) destroyed", p_destroy.stdout)
    left = leftovers()
    p2, t_apply2 = tofu("apply", "-auto-approve")
    out = {
        "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "emulator": json.loads((ROOT / "results" / "emulator-version.json").read_text()),
        "tofu_version": subprocess.run(["tofu", "version", "-json"], capture_output=True, text=True, cwd=INFRA).stdout,
        "apply": {"seconds": round(t_apply, 1), "added": int(m.group(1)) if m else None,
                  "managed_resources": sum(types.values()), "resource_types": dict(sorted(types.items()))},
        "plan_after_apply": {"seconds": round(t_plan, 1), "exit_code": p_plan.returncode,
                             "no_changes": p_plan.returncode == 0, "drifting_resources": drift},
        "destroy": {"seconds": round(t_destroy, 1), "ok": p_destroy.returncode == 0,
                    "destroyed": int(md.group(1)) if md else None, "leftovers": left,
                    "error_tail": None if p_destroy.returncode == 0 else p_destroy.stdout[-1500:] + p_destroy.stderr[-1500:]},
        "reapply": {"seconds": round(t_apply2, 1)},
    }
    out["tofu_version"] = json.loads(out["tofu_version"])["terraform_version"]
    (ROOT / "results" / "deploy.json").write_text(json.dumps(out, indent=1))
    print(json.dumps({k: v for k, v in out.items() if k not in ("emulator",)}, indent=1)[:3000])


if __name__ == "__main__":
    main()
