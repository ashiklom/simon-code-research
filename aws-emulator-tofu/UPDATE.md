# Re-checking the findings against a newer aws-emulator (agent instructions)

This experiment's findings (`findings.toml`, `results/*.json`, the report site, `EMULATOR-GUIDE.md`)
were produced against one specific aws-emulator build. The build is recorded in
`results/emulator-version.json`: `.deb` version, release date, aws-emulator git commit, .deb SHA-256, and source
(`deb-latest`, `deb@<version>` or `source-build@<commit>`), plus `last_checked`.
aws-emulator ships often, sometimes several times a day, so follow this procedure to keep
the findings current. Run all commands from `aws-emulator-tofu/`.

## 0. Prerequisites

```bash
mise install && pixi install          # tools + Python env (pinned)
mise run fetch                        # COGs + vectors into data/ (only needed for steps 3+)
```

## 1. Did aws-emulator change at all?

```bash
mise run update-check                 # = pixi run python scripts/update_check.py
```

The script reads the newest version from `downloads.aws.com/.../LTS/versions.json` and resolves its
commit from the `v<version>` git tag on github.com/aws/aws-emulator. It compares that commit with the
recorded one and writes `results/update-check.json`. The `status` field is one of three values:

| status | meaning | what you do |
|---|---|---|
| `UNCHANGED` | same commit as recorded | `last_checked` has been bumped already. Commit `results/emulator-version.json` + `results/update-check.json` with subject `aws-emulator-tofu: emulator update check (unchanged)`, then **stop**. |
| `NO_RELEVANT_CHANGES` | new release, but none of the crate paths or issue files referenced by any finding changed | Run `pixi run python scripts/update_check.py --record-no-change`, commit as above (subject `... (no relevant changes in <version>)`), then **stop**. Don't re-run the stack. The results stay attributed to the version that produced them. |
| `AFFECTED` (exit code 10) | some findings reference changed code, or issue files that moved to `things-that-now-work/` | Continue with step 2. |

How "relevant" is decided: each `[[finding]]` in `findings.toml` lists `crates` (path prefixes in the
aws-emulator repo, e.g. `services/service-com-amazonaws-lambda-awsgirapiservice/src/state/execution`)
and `issues` (file names under `issues/`). The diff is restricted to those paths. It is deliberately
generous: a hit means "re-test this finding", not "this finding is fixed".

## 2. Install the new emulator and look at what changed

```bash
OLD=$(python3 -c "import json;print(json.load(open('results/emulator-version.json'))['version'])")
mkdir -p results/history/$OLD && cp results/{emulator-version,deploy,e2e,probes}.json results/history/$OLD/
scripts/emulator.sh install                      # latest .deb (default), or: --version 1.0.336
mise run emulator:restart                        # fresh state, records results/emulator-version.json
```

The snapshot in `results/history/<old version>/` is what the site's "changes since the previous
version" table (`report/_generated/changes.md`) compares against.

For each affected finding, skim the diff summary printed by `update-check`. The full diff is in
`.emulator/src-check` (`git -C .emulator/src-check diff <old> <new> -- <crate path>`). Also read any
issue files that moved to `things-that-now-work/`, because they say what was fixed.

## 3. Re-test only what can be affected

Use the `evidence` field of each affected finding to pick what to re-run:

| evidence prefix | re-run |
|---|---|
| `probe:<name>` | `eval "$(scripts/emulator.sh env)" && pixi run python probes/run.py <name> ...` (results merge into `results/probes.json`) |
| `e2e:*` | `mise run measure && mise run load && mise run e2e` (deploy cycle + role matrix) |
| `deploy:*` | `mise run measure` |
| `unit:*` | `mise run unit` (no emulator needed) |

If in doubt, run everything: `mise run all` takes about 30 min.

Some workarounds may have become unnecessary. Each workaround in `infra/` is tagged with a comment
naming its finding id. Examples:

- `rds-describeglobalclusters-filter`: try `via_script = false` in `infra/main.tf`, which means
  native `aws_rds_cluster`.
- `ec2-sg-default-egress`: `create_security_group = true`.
- `lambda-guest-http`: drop `JWKS_JSON`.
- `cloudfront-authorization-dropped`: the e2e route `cf-authz` turns green.

Only remove a workaround after the corresponding probe or e2e check passes.

## 4. Update the findings and the report

1. Edit `findings.toml` for every re-tested finding:
   - set `status` (`gap` / `partial` / `works`);
   - set `last_verified_version` to the new version;
   - adjust `emulator_behavior`/`workaround`;
   - add `fixed_in = "<version>"` when a gap closed.
2. Add new findings for any new gap you hit, with `crates`, `issues` and `evidence` filled in so the
   next update check can see them.
3. Update `EMULATOR-GUIDE.md` (tables are hand-written; keep them consistent with `findings.toml`)
   and any report prose in `report/*.qmd` that states a now-changed behaviour.
4. Rebuild and check the site: `mise run site`, then from the repo root
   `uv run _helpers/build_site.py --only aws-emulator-tofu --skip-assets`.
5. Commit with a subject like `aws-emulator-tofu: re-verify findings against aws-emulator <version>`.
   Keep the version, commit and timestamp in `results/emulator-version.json`; the site shows them.

## Optional: check an unreleased build from source

Only do this when the user asks. A full build needs a Rust toolchain and about 100 GB of free disk.

```bash
pixi run python scripts/update_check.py --ref main         # what changed on main vs the tested commit
scripts/emulator.sh install --from-source --ref main       # cargo build --release + local .deb
mise run emulator:restart                                  # records source = source-build@<commit>
```

Then continue with steps 3–4. Record such results as `source-build@<commit>` in the commit message
and in `findings.toml` (`last_verified_version = "source@<short-commit>"`).
