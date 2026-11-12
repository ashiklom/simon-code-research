"""Generate report/_generated/*.md tables from committed results + findings.toml; copy figures.

Standard library only (Python >= 3.11) so the site build needs no pixi environment:
    uv run --no-project --python 3.12 scripts/make_report_assets.py
"""
from __future__ import annotations

import json
import re
import shutil
import tomllib
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RES = ROOT / "results"
GEN = ROOT / "report" / "_generated"
GH = "https://github.com/aws/aws-emulator"
REPO = "https://github.com/ashiklom/simon-code-research/blob/main/aws-emulator-tofu"


def load(name):
    p = RES / name
    return json.loads(p.read_text()) if p.exists() else None


def esc(s):
    return str(s).replace("|", "\\|").replace("\n", " ")


def badge(status):
    label = {"works": "works", "partial": "partial", "gap": "gap"}.get(status, status)
    return f'[{label}]{{.status-{status}}}'


def write(name, text):
    (GEN / name).write_text(text.strip() + "\n")


def evidence_link(e):
    kind, _, ref = e.partition(":")
    if kind == "probe":
        return f"[probe `{ref}`](probes.qmd#{ref})"
    if kind == "e2e":
        return f"[e2e `{ref}`](auth-api.qmd#results-on-aws-emulator)"
    if kind == "deploy":
        return f"[deploy `{ref}`](emulator.qmd#deploy-cycle)"
    if kind == "unit":
        return f"unit `{ref}`"
    if kind == "source":
        if ref.startswith(("services/", "vendor/", "core/")):
            return f"[source]({GH}/blob/{COMMIT}/{ref})"
        return f"[`{ref}`]({REPO}/{ref})"
    return e


def version_box(v):
    lc = v.get("last_checked")
    last = ""
    if lc:
        last = (f" Last update check: **{lc['at'][:10]}** against {lc['candidate_version']} "
                f"([`{lc['candidate_commit'][:10]}`]({GH}/commit/{lc['candidate_commit']})): {lc['result']}.")
    write("version-box.md", f"""
::: {{.versionbox}}
Results produced with **aws-emulator {v['version']}** (released {v['release_date']}, commit
[`{v['commit'][:10]}`]({GH}/commit/{v['commit']}), source `{v['source']}`, .deb sha256 `{v['deb_sha256'][:12]}…`),
OpenTofu {DEPLOY.get('tofu_version', '?') if DEPLOY else '?'}, hashicorp/aws provider 6.73.{last}
See [UPDATE.md]({REPO}/UPDATE.md) for how to re-check.
:::
""")


def e2e_tables(e):
    routes = {"apigw": "API Gateway direct, `Authorization`", "cf-authz": "CloudFront, `Authorization`",
              "cf-xauth": "CloudFront, `X-Auth-Token`"}
    s = ["| Route | Cases | Status as expected on AWS |", "|---|---:|---:|"]
    for r, label in routes.items():
        x = e["summary"][r]
        s.append(f"| {label} | {x['n']} | **{x['match']}** / {x['n']} |")
    s += ["", "| Other check | Observed | As on AWS? |", "|---|---|---|"]
    for c in e["extra_checks"]:
        s.append(f"| {esc(c['check'])} | `{esc(c['observed'])}` | {'yes' if c['match'] else '**no**'} |")
    write("e2e-summary.md", "\n".join(s))

    eps = list(dict.fromkeys(r["endpoint"] for r in e["rows"]))
    callers = list(dict.fromkeys(r["caller"] for r in e["rows"]))
    out = ["::: {.panel-tabset}"]
    for r, label in routes.items():
        cells = {(x["caller"], x["endpoint"]): x for x in e["rows"] if x["route"] == r}
        out += [f"## {label}", "", "| caller | " + " | ".join(f"`{p}`" for p in eps) + " |",
                "|---|" + "---|" * len(eps)]
        for c in callers:
            row = []
            for p in eps:
                x = cells[(c, p)]
                row.append(f"{x['observed']}" if x["match"] else f"**{x['observed']}** ✗ (AWS: {x['expected']})")
            out.append(f"| {c} | " + " | ".join(row) + " |")
        out.append("")
    out.append(":::")
    write("e2e-matrix.md", "\n".join(out))

    s = ["Latency of authorized calls through API Gateway on aws-emulator (wall clock, including the "
         "authorizer Lambda's pure-Python ES256 verification on RustPython):", "",
         "| endpoint | n | median (s) | max (s) |", "|---|---:|---:|---:|"]
    for ep, v in e["latency"].items():
        s.append(f"| `{ep}` | {v['n']} | {v['median_s']} | {v['max_s']} |")
    mint = e.get("token_minting", {})
    if mint:
        secs = sorted(m["seconds"] for m in mint.values())
        s += ["", f"Minting a token through `POST /auth/token` took {secs[0]}–{secs[-1]} s."]
    write("latency.md", "\n".join(s))


def deploy_tables(d):
    a, p, x = d["apply"], d["plan_after_apply"], d["destroy"]
    types = ", ".join(f"`{k}` ×{v}" for k, v in a["resource_types"].items()
                      if not k.startswith(("aws_iam_policy_document", "archive_file", "aws_availability"))
                      and k != "module")
    left = x.get("leftovers") or {}
    write("deploy.md", f"""
| Step | Result |
|---|---|
| `tofu apply` (fresh emulator, empty state) | **{a['added']} resources created in {a['seconds']} s**, no errors (with the workarounds below) |
| `tofu plan -detailed-exitcode` right after | {'**no changes** (exit 0)' if p['no_changes'] else 'drift: ' + ', '.join(p['drifting_resources'])} in {p['seconds']} s |
| `tofu destroy` | {'**ok**' if x['ok'] else 'FAILED'}: {x['destroyed']} destroyed in {x['seconds']} s |
| Leftovers after destroy | {', '.join(f'{k}: `{v}`' for k, v in left.items()) or 'none'} |
| Re-apply | {d['reapply']['seconds']} s |

Managed resource types: {types}.
""")


def workarounds(findings):
    s = ["| Emulator-only setting | Why | Finding |", "|---|---|---|"]
    for f in findings:
        if f.get("infra_switch"):
            s.append(f"| {esc(f['infra_switch'])} | {esc(f['title'])} | [{f['id']}](differences.qmd#{f['id']}) |")
    write("workarounds.md", "\n".join(s))


def differences(findings):
    order = ["Lambda", "API Gateway", "CloudFront", "Cognito", "RDS / Aurora", "S3", "IAM", "Networking",
             "Compute", "CloudFormation", "OpenTofu provider x emulator", "Operations",
             "Design notes (also true on AWS)"]
    by = defaultdict(list)
    for f in findings:
        by[f["category"]].append(f)
    cats = [c for c in order if c in by] + [c for c in by if c not in order]
    sev = {"major": 0, "moderate": 1, "minor": 2, "info": 3}
    out = []
    n_gap = sum(f["status"] != "works" and f["emulator_only"] for f in findings)
    out.append(f"{len(findings)} findings: {n_gap} emulator-only gaps or partial behaviours, "
               f"{sum(f['status'] == 'works' for f in findings)} confirmed to behave like AWS, "
               f"{sum(not f['emulator_only'] for f in findings)} also true on real AWS.\n")
    out += ["| | Finding | Scope | Severity | Status |", "|---|---|---|---|---|"]
    for c in cats:
        for f in sorted(by[c], key=lambda f: sev[f["severity"]]):
            scope = "emulator only" if f["emulator_only"] else "**also on AWS**"
            out.append(f"| {c} | [{esc(f['title'])}](#{f['id']}) | {scope} | {f['severity']} | {badge(f['status'])} |")
    out.append("")
    for c in cats:
        anchor = re.sub(r"[^a-z0-9]+", "-", c.lower()).strip("-")
        out.append(f"### {c} {{#{anchor}}}\n")
        for f in sorted(by[c], key=lambda f: sev[f["severity"]]):
            scope = "emulator only" if f["emulator_only"] else "also true on real AWS"
            ev = ", ".join(evidence_link(e) for e in f.get("evidence", []))
            issues = ", ".join(f"[`{i[:40]}…`]({GH}/blob/{COMMIT}/issues/things-that-do-not-work/{i})"
                               for i in f.get("issues", []))
            out.append(f"#### {f['title']} {{#{f['id']}}}\n")
            out.append(f"{badge(f['status'])} · {f['severity']} · {scope} · id `{f['id']}` · "
                       f"verified on {f['last_verified_version']}\n")
            out.append(f"- **AWS:** {f['aws']}")
            out.append(f"- **aws-emulator:** {f['emulator']}")
            out.append(f"- **Workaround:** {f['workaround']}")
            out.append(f"- **Evidence:** {ev}" + (f"; upstream issue(s): {issues}" if issues else ""))
            out.append("")
    write("differences.md", "\n".join(out))


def probes(pr, findings):
    fid = {f["id"]: f for f in findings}
    rows = sorted(pr["probes"], key=lambda r: (r["category"], r["name"]))
    s = ["| Probe | Category | tofu apply | plan drift | destroy | Behaviour vs AWS |", "|---|---|---|---|---|---|"]

    def yn(v):
        return "–" if v is None else ("ok" if v else "**fail**")
    for r in rows:
        ap = r.get("apply", {})
        apply_s = ("ok" if ap.get("ok") else ("**timeout**" if "TIMEOUT" in str(ap.get("error")) else "**fail**"))
        if not ap.get("ok") and r.get("expect_apply_failure"):
            apply_s += " (the finding)"
        dr = r.get("drift")
        drift_s = "–" if not dr else ("none" if dr["no_changes"] else "**" + ", ".join(dr["resources"]) + "**")
        de = r.get("destroy") or {}
        s.append(f"| [{r['name']}](#{r['name']}) | {r['category']} | {apply_s} | {drift_s} | {yn(de.get('ok'))} | "
                 f"{badge(r['check']['status'])} |")
    s.append("")
    for r in rows:
        ch = r["check"]
        ids = [f["id"] for f in findings if f"probe:{r['name']}" in f.get("evidence", [])]
        links = ", ".join(f"[{i}](differences.qmd#{i})" for i in ids)
        s.append(f"### {r['title']} {{#{r['name']}}}\n")
        s.append(f"{badge(ch['status'])} · `probes/{r['name']}/` · ran {r.get('ran_at', '?')}\n")
        s.append(f"- **Real AWS:** {r['aws_expected']}")
        if not r.get("apply", {}).get("ok"):
            s.append(f"- **tofu apply:** {esc(r['apply'].get('error'))}")
        s.append(f"- **Observed:** {esc(ch['detail'])}")
        if r.get("drift") and not r["drift"]["no_changes"]:
            attrs = r["drift"].get("attributes") or []
            s.append(f"- **Drift after apply:** {', '.join(r['drift']['resources'])}"
                     + (f" ({esc('; '.join(f'`{a}`' for a in attrs))})" if attrs else ""))
        if links:
            s.append(f"- **Findings:** {links}")
        s.append("")
    write("probes.md", "\n".join(s))
    counts = defaultdict(int)
    for r in rows:
        counts[r["check"]["status"]] += 1
    write("probe-counts.md", f"{len(rows)} probes: {counts['works']} work like AWS, {counts['partial']} partially, "
                             f"{counts['gap']} don't.")


def changes(cur_probes, cur_e2e, cur_deploy, v):
    """Compare current results with the newest snapshot in results/history/<version>/."""
    hist = sorted((RES / "history").glob("*/probes.json"), key=lambda p: [int(x) for x in p.parent.name.split(".")])
    hist = [h for h in hist if h.parent.name != v["version"]]
    if not hist:
        write("changes.md", "No earlier emulator version has been recorded yet.")
        return
    prev_dir = hist[-1].parent
    prev = json.loads((prev_dir / "probes.json").read_text())
    pv = json.loads((prev_dir / "emulator-version.json").read_text())
    old = {r["name"]: r for r in prev["probes"]}
    new = {r["name"]: r for r in (cur_probes or {}).get("probes", [])}
    out = [f"Compared with the previous run on **aws-emulator {pv['version']}** "
           f"([`{pv['commit'][:10]}`]({GH}/commit/{pv['commit']})), kept in `results/history/{pv['version']}/`:", ""]
    rows = []
    for name in sorted(set(old) | set(new)):
        a, b = old.get(name), new.get(name)
        sa = a["check"]["status"] if a else "–"
        sb = b["check"]["status"] if b else "–"
        da = (a or {}).get("check", {}).get("detail", "")
        db = (b or {}).get("check", {}).get("detail", "")
        if sa != sb or (a and b and bool(a.get("apply", {}).get("ok")) != bool(b.get("apply", {}).get("ok"))):
            rows.append(f"| [{name}](probes.qmd#{name}) | {badge(sa) if a else '–'} | {badge(sb) if b else '–'} | {esc(db[:220])} |")
        elif a and b and da != db and sa != "works":
            rows.append(f"| [{name}](probes.qmd#{name}) | {badge(sa)} | {badge(sb)} (details changed) | {esc(db[:220])} |")
    if rows:
        out += [f"| Probe | {pv['version']} | {v['version']} | Now |", "|---|---|---|---|", *rows]
    else:
        out.append("No probe changed status.")
    pe = prev_dir / "e2e.json"
    if pe.exists() and cur_e2e:
        a, b = json.loads(pe.read_text())["summary"], cur_e2e["summary"]
        out += ["", "End-to-end matrix (cases as expected on AWS): " + "; ".join(
            f"`{r}` {a[r]['match']}/{a[r]['n']} → {b[r]['match']}/{b[r]['n']}" for r in b)]
    pd = prev_dir / "deploy.json"
    if pd.exists() and cur_deploy:
        a, b = json.loads(pd.read_text()), cur_deploy
        out += ["", f"Deploy cycle: apply {a['apply']['seconds']} s → {b['apply']['seconds']} s; "
                    f"plan after apply clean: {a['plan_after_apply']['no_changes']} → {b['plan_after_apply']['no_changes']}; "
                    f"destroy ok: {a['destroy']['ok']} → {b['destroy']['ok']}, leftovers "
                    f"{sum(len(x) for x in (a['destroy']['leftovers'] or {}).values())} → "
                    f"{sum(len(x) for x in (b['destroy']['leftovers'] or {}).values())}."]
    write("changes.md", "\n".join(out))


def main():
    global COMMIT, DEPLOY
    GEN.mkdir(parents=True, exist_ok=True)
    v = load("emulator-version.json")
    COMMIT = v["commit"]
    DEPLOY = load("deploy.json")
    findings = tomllib.loads((ROOT / "findings.toml").read_text())["finding"]
    version_box(v)
    if (e := load("e2e.json")):
        e2e_tables(e)
    if DEPLOY:
        deploy_tables(DEPLOY)
    workarounds(findings)
    differences(findings)
    pr = load("probes.json")
    if pr:
        probes(pr, findings)
    changes(pr, load("e2e.json"), DEPLOY, v)
    figs = ROOT / "report" / "figures"
    shutil.rmtree(figs, ignore_errors=True)
    shutil.copytree(ROOT / "figures", figs)
    print("wrote", sorted(p.name for p in GEN.iterdir()))


COMMIT = ""
DEPLOY = None

if __name__ == "__main__":
    main()
