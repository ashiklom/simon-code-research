"""Run capability probes: tofu apply -> check.py -> drift plan -> destroy, per probe dir.

  pixi run python probes/run.py            # all probes
  pixi run python probes/run.py name ...   # selected probes (results merged into results/probes.json)

Each probe dir has main.tf (+ symlinked provider.tf) and check.py defining:
  TITLE, CATEGORY, AWS_EXPECTED (what real AWS does), FINDINGS (ids in findings.toml),
  optional APPLY_TIMEOUT (s), EXPECT_APPLY_FAILURE (the probe demonstrates a deploy failure),
  optional TF_VARS (dict), and check(outputs) -> lib.result(...)
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = ROOT / "results" / "probes.json"
sys.path.insert(0, str(HERE))
os.environ.setdefault("TF_PLUGIN_CACHE_DIR", str(Path.home() / ".cache" / "tofu-plugins"))
Path(os.environ["TF_PLUGIN_CACHE_DIR"]).mkdir(parents=True, exist_ok=True)
ANSI = re.compile(r"\x1b\[[0-9;]*m")


def tofu(d, *args, timeout=300, tfvars=None):
    cmd = ["tofu", *args, "-no-color", "-input=false"]
    for k, v in (tfvars or {}).items():
        cmd += ["-var", f"{k}={v}"]
    t0 = time.time()
    try:
        p = subprocess.run(cmd, cwd=d, capture_output=True, text=True, timeout=timeout)
        return p.returncode, ANSI.sub("", p.stdout + p.stderr), time.time() - t0
    except subprocess.TimeoutExpired as e:
        out = (e.stdout or b"").decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
        return "timeout", ANSI.sub("", out), time.time() - t0


def first_error(text):
    m = re.search(r"Error: (.+?)(?:\n\n|\Z)", text, re.S)
    return re.sub(r"\s+", " ", m.group(1)).strip()[:600] if m else text.strip()[-600:]


def load_meta(d):
    spec = importlib.util.spec_from_file_location(f"probe_{d.name}", d / "check.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run_probe(d):
    meta = load_meta(d)
    tfvars = getattr(meta, "TF_VARS", None)
    row = {"name": d.name, "title": meta.TITLE, "category": meta.CATEGORY, "aws_expected": meta.AWS_EXPECTED,
           "findings": getattr(meta, "FINDINGS", []), "expect_apply_failure": getattr(meta, "EXPECT_APPLY_FAILURE", False)}
    for f in d.glob("terraform.tfstate*"):
        f.unlink()
    if hasattr(meta, "prepare"):
        try:
            row["prepare"] = meta.prepare(d)
        except Exception as e:  # noqa: BLE001
            row["apply"] = {"ok": False, "error": f"prepare failed: {e}"[:600]}
            row["check"] = {"status": "gap", "detail": row["apply"]["error"]}
            return row
    rc, out, _ = tofu(d, "init", timeout=300)
    if rc != 0:
        row["apply"] = {"ok": False, "error": "init: " + first_error(out)}
        return row
    rc, out, dt = tofu(d, "apply", "-auto-approve", timeout=getattr(meta, "APPLY_TIMEOUT", 300), tfvars=tfvars)
    row["apply"] = {"ok": rc == 0, "seconds": round(dt, 1),
                    "error": None if rc == 0 else ("TIMEOUT after %ds: " % dt if rc == "timeout" else "") + first_error(out)}
    outputs = {}
    if rc != "timeout":
        p = subprocess.run(["tofu", "output", "-json"], cwd=d, capture_output=True, text=True)
        try:
            outputs = {k: v["value"] for k, v in json.loads(p.stdout or "{}").items()}
        except ValueError:
            outputs = {}
    try:
        row["check"] = meta.check(outputs, row)
    except Exception as e:  # noqa: BLE001
        row["check"] = {"status": "gap", "detail": f"check raised {type(e).__name__}: {e}"[:600]}
    if rc == 0:
        prc, pout, _ = tofu(d, "plan", "-detailed-exitcode", timeout=300, tfvars=tfvars)
        attrs = re.findall(r"^\s+[~+-] (\w+)\s+= (.{0,80})", pout, re.M) if prc == 2 else []
        row["drift"] = {"no_changes": prc == 0,
                        "resources": re.findall(r"^  # (\S+) (?:will be|must be)", pout, re.M) if prc == 2 else [],
                        "attributes": [f"{a} = {v.strip()}" for a, v in attrs if a not in ("id", "arn")][:12],
                        "error": first_error(pout) if prc not in (0, 2) else None}
    if rc == "timeout":
        row["destroy"] = {"ok": None, "error": "skipped (apply timed out; restart the emulator to clean up)"}
    else:
        drc, dout, ddt = tofu(d, "destroy", "-auto-approve", timeout=300, tfvars=tfvars)
        row["destroy"] = {"ok": drc == 0, "seconds": round(ddt, 1), "error": None if drc == 0 else first_error(dout)}
    return row


def main(names):
    dirs = sorted(p for p in HERE.iterdir() if p.is_dir() and (p / "check.py").exists())
    if names:
        dirs = [d for d in dirs if d.name in names]
    existing = json.loads(OUT.read_text()) if OUT.exists() else {"probes": []}
    rows = {r["name"]: r for r in existing.get("probes", [])}
    for d in dirs:
        print(f"=== {d.name}", flush=True)
        r = run_probe(d)
        r["ran_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        rows[d.name] = r
        print(json.dumps({k: r.get(k) for k in ("apply", "check", "drift", "destroy")})[:900], flush=True)
        OUT.write_text(json.dumps({
            "emulator": json.loads((ROOT / "results" / "emulator-version.json").read_text()),
            "probes": [rows[k] for k in sorted(rows)]}, indent=1))


if __name__ == "__main__":
    main(sys.argv[1:])
