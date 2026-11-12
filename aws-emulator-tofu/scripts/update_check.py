"""Has aws-emulator changed since the version these findings were produced with? (see UPDATE.md)

  pixi run python scripts/update_check.py                 # compare against the latest .deb release
  pixi run python scripts/update_check.py --ref main      # compare against a git ref (for source builds)
  pixi run python scripts/update_check.py --record-no-change   # write last_checked (no relevant changes)

Steps:
 1. Latest release = highest entry in downloads.aws.com/.../LTS/versions.json; its commit = the
    `v<version>` tag on github.com/aws/aws-emulator (git ls-remote; no API token needed).
 2. Same commit as results/emulator-version.json -> "UNCHANGED" (exit 0).
 3. Otherwise shallow-fetch both commits into .emulator/src-check and diff them, restricted to the
    crate paths and issue files listed in findings.toml; also list issue files that moved from
    issues/things-that-do-not-work/ to issues/things-that-now-work/.
 4. Print + write results/update-check.json: affected findings (exit 10) or none (exit 0).
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
import tomllib
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERSIONS = "https://downloads.aws.com/aws-emulator/packages/aws-emulator/LTS/versions.json"
REPO = "https://github.com/aws/aws-emulator"
SRC = ROOT / ".emulator" / "src-check"
REC = ROOT / "results" / "emulator-version.json"
OUT = ROOT / "results" / "update-check.json"


def sh(*a, cwd=None, check=True):
    return subprocess.run(a, cwd=cwd, check=check, capture_output=True, text=True).stdout


def vkey(v):
    return tuple(int(x) for x in v.split("."))


def latest_release():
    vs = [x["version"] for x in json.load(urllib.request.urlopen(VERSIONS))["versions"]]
    full = max(vs, key=vkey)                      # e.g. 1.0.336.1  (= deb 1.0.336-1)
    version = ".".join(full.split(".")[:3])
    tags = sh("git", "ls-remote", "--tags", REPO, f"refs/tags/v{version}", f"refs/tags/v{version}^{{}}")
    commits = dict(reversed(line.split("\t")) for line in tags.strip().splitlines())
    commit = commits.get(f"refs/tags/v{version}^{{}}") or commits.get(f"refs/tags/v{version}")
    return version, commit


def ref_commit(ref):
    out = sh("git", "ls-remote", REPO, ref).split()
    return out[0] if out else ref


def fetch(*commits):
    if not (SRC / ".git").exists():
        SRC.mkdir(parents=True, exist_ok=True)
        sh("git", "init", "-q", cwd=SRC)
        sh("git", "remote", "add", "origin", REPO, cwd=SRC)
    for c in commits:
        sh("git", "fetch", "-q", "--depth", "1", "--filter=blob:none", "origin", c, cwd=SRC)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", help="compare against this git ref instead of the latest .deb release")
    ap.add_argument("--record-no-change", action="store_true",
                    help="record this check in results/emulator-version.json (after confirming no relevant change)")
    a = ap.parse_args()

    rec = json.loads(REC.read_text())
    old = rec["commit"]
    if a.ref:
        new_version, new = f"source@{a.ref}", ref_commit(a.ref)
    else:
        new_version, new = latest_release()
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    report = {"checked_at": now, "tested": {"version": rec["version"], "commit": old},
              "candidate": {"version": new_version, "commit": new}}

    if new == old:
        report.update(status="UNCHANGED", affected_findings=[], changed_paths=[])
    else:
        findings = tomllib.loads((ROOT / "findings.toml").read_text())["finding"]
        fetch(old, new)
        names = sh("git", "diff", "--name-status", "-M", old, new, cwd=SRC).splitlines()
        changed = [ln.split("\t") for ln in names]
        paths = [p for row in changed for p in row[1:]]
        moved_fixed = [row[2] for row in changed if row[0].startswith("R")
                       and "things-that-do-not-work/" in row[1] and "things-that-now-work/" in row[2]]
        affected = []
        for f in findings:
            hits = sorted({p for p in paths for c in f.get("crates", []) if p.startswith(c)})
            fixed = [m for m in moved_fixed for i in f.get("issues", []) if Path(m).name == Path(i).name]
            if hits or fixed:
                affected.append({"id": f["id"], "title": f["title"], "status": f["status"],
                                 "changed_files": len(hits), "sample": hits[:5], "issues_now_fixed": fixed})
        report.update(status="AFFECTED" if affected else "NO_RELEVANT_CHANGES",
                      n_changed_paths=len(paths), issues_moved_to_now_work=len(moved_fixed),
                      affected_findings=affected)
    OUT.write_text(json.dumps(report, indent=1))
    print(json.dumps({k: v for k, v in report.items() if k != "affected_findings"}, indent=1))
    for f in report.get("affected_findings", []):
        print(f"  - {f['id']} ({f['status']}): {f['changed_files']} changed files, now-fixed issues: {f['issues_now_fixed']}")
    if a.record_no_change or report["status"] == "UNCHANGED":
        rec["last_checked"] = {"at": now, "candidate_version": new_version, "candidate_commit": new,
                               "result": report["status"] if report["status"] != "AFFECTED" else "AFFECTED (not re-run)"}
        REC.write_text(json.dumps(rec, indent=2))
        print(f"recorded last_checked in {REC.relative_to(ROOT)}")
    sys.exit(10 if report["status"] == "AFFECTED" else 0)


if __name__ == "__main__":
    main()
