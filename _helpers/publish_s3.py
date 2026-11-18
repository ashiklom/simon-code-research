#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Publish an experiment's site data to the public S3 bucket (served through CloudFront).

Layout (see /CLAUDE.md, "S3 / CloudFront"):

    s3://<bucket>/simon-code-research/<folder>/site-data/<version>/...   immutable, pinned by the site
    s3://<bucket>/simon-code-research/<folder>/stores/...                Icechunk repos (written by the experiment)

The version is ``vYYYYMMDD-<hash8>``, where the hash covers every file's relative path and
content, so re-publishing identical data is a no-op and the pin changes only when the data do.
Objects are uploaded as INTELLIGENT_TIERING with ``Cache-Control: immutable``.

Usage:
    uv run _helpers/publish_s3.py site <folder> <local-dir> [--dry-run] [--env-file site/.env.production]
    uv run _helpers/publish_s3.py prune <folder> --keep <version> [--dry-run]
    uv run _helpers/publish_s3.py summary [<folder>]

Requires the aws CLI. Writes use the profile in $PUBLISH_AWS_PROFILE (default
``ycgs-all-buckets-writer``); listing uses the same profile.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BUCKET = os.environ.get("PUBLISH_S3_BUCKET", "ycgs-use1-public")
ROOT = "simon-code-research"
PROFILE = os.environ.get("PUBLISH_AWS_PROFILE", "ycgs-all-buckets-writer")
PUBLIC_URL = os.environ.get("YCGS_PUBLIC_BUCKET_URL", "https://d3v5kb9d29awwb.cloudfront.net").rstrip("/")
IMMUTABLE = "public, max-age=31536000, immutable"
# us-east-1 list prices (USD per GB-month). IT objects < 128 KB stay in the frequent tier.
PRICE_STD, PRICE_IT_IDLE = 0.023, 0.004
SMALL = 128 * 1024


def aws(*args: str, capture: bool = False) -> str:
    cmd = ["aws", "--profile", PROFILE, *args]
    if capture:
        return subprocess.check_output(cmd, text=True)
    subprocess.check_call(cmd)
    return ""


def files_of(d: Path) -> list[Path]:
    return sorted(p for p in d.rglob("*") if p.is_file() and not p.name.startswith("."))


def content_hash(d: Path, files: list[Path]) -> str:
    h = hashlib.sha256()
    for p in files:
        h.update(p.relative_to(d).as_posix().encode() + b"\0")
        with p.open("rb") as f:
            for block in iter(lambda: f.read(1 << 20), b""):
                h.update(block)
        h.update(b"\0")
    return h.hexdigest()[:8]


def cost_line(sizes: list[int]) -> str:
    total = sum(sizes)
    small = sum(s for s in sizes if s < SMALL)
    gb, small_gb = total / 1e9, small / 1e9
    hot = gb * PRICE_STD
    idle = small_gb * PRICE_STD + (gb - small_gb) * PRICE_IT_IDLE
    return (
        f"{len(sizes):,} objects, {gb:.3f} GB ({small_gb:.3f} GB in objects < 128 KB); "
        f"~${hot:.3f}/month hot, ~${idle:.3f}/month once idle (Intelligent-Tiering)"
    )


def prefix(folder: str, *parts: str) -> str:
    return "/".join([ROOT, folder, *parts]).rstrip("/") + "/"


def cmd_site(a: argparse.Namespace) -> None:
    folder_dir = REPO / a.folder
    if not folder_dir.is_dir():
        sys.exit(f"no experiment folder {folder_dir}")
    src = Path(a.local_dir).resolve()
    files = files_of(src)
    if not files:
        sys.exit(f"no files under {src}")
    version = f"v{dt.date.today():%Y%m%d}-{content_hash(src, files)}"
    key = prefix(a.folder, "site-data", version)
    url = f"{PUBLIC_URL}/{key.rstrip('/')}"
    sizes = [p.stat().st_size for p in files]
    print(f"version   {version}")
    print(f"target    s3://{BUCKET}/{key}")
    print(f"url       {url}")
    print(f"contents  {cost_line(sizes)}")
    big = sorted(((s, p) for s, p in zip(sizes, files) if s > 4e6), reverse=True)[:5]
    for s, p in big:
        print(f"  large: {p.relative_to(src)} {s / 1e6:.1f} MB")
    if a.dry_run:
        return
    if _exists(key):
        print("version already uploaded; syncing any missing objects")
    aws(
        "s3", "sync", str(src), f"s3://{BUCKET}/{key}",
        "--storage-class", "INTELLIGENT_TIERING",
        "--cache-control", IMMUTABLE,
        "--no-progress", "--only-show-errors",
        "--exclude", ".*", "--exclude", "*/.*",
    )
    if a.env_file:
        env = folder_dir / a.env_file
        env.write_text(
            "# Site data lives in the public S3 bucket and is served through CloudFront (see README,\n"
            "# \"Publishing the site data\"). The path is versioned by content hash, so the site and its\n"
            "# data match. Update with `mise run publish-site-data`.\n"
            f"VITE_DATA_BASE={url}\n"
        )
        print(f"wrote     {env.relative_to(REPO)}")
    print(json.dumps({"version": version, "url": url}))


def _exists(key: str) -> bool:
    out = aws("s3api", "list-objects-v2", "--bucket", BUCKET, "--prefix", key, "--max-items", "1",
              "--query", "KeyCount", "--output", "text", capture=True)
    return out.strip() not in ("", "0", "None")


def cmd_prune(a: argparse.Namespace) -> None:
    base = prefix(a.folder, "site-data")
    out = aws("s3api", "list-objects-v2", "--bucket", BUCKET, "--prefix", base, "--delimiter", "/",
              "--query", "CommonPrefixes[].Prefix", "--output", "json", capture=True)
    versions = [p.removeprefix(base).strip("/") for p in (json.loads(out) or [])]
    if a.keep not in versions:
        sys.exit(f"refusing to prune: {a.keep} is not among the uploaded versions {versions}")
    for v in versions:
        if v == a.keep:
            continue
        print(f"{'would delete' if a.dry_run else 'deleting'} s3://{BUCKET}/{base}{v}/")
        if not a.dry_run:
            aws("s3", "rm", "--recursive", "--only-show-errors", f"s3://{BUCKET}/{base}{v}/")


def cmd_summary(a: argparse.Namespace) -> None:
    base = prefix(a.folder) if a.folder else f"{ROOT}/"
    out = aws("s3api", "list-objects-v2", "--bucket", BUCKET, "--prefix", base,
              "--query", "Contents[].[Key,Size]", "--output", "json", capture=True)
    rows = json.loads(out) or []
    groups: dict[str, list[int]] = {}
    for k, s in rows:
        parts = k.removeprefix(f"{ROOT}/").split("/")
        g = "/".join(parts[:3]) if len(parts) > 3 else "/".join(parts[:-1])
        groups.setdefault(g, []).append(s)
    for g, sizes in sorted(groups.items()):
        print(f"{g:70s} {cost_line(sizes)}")
    print(f"{'TOTAL':70s} {cost_line([s for v in groups.values() for s in v])}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("site", help="upload a site-data directory as a new immutable version")
    s.add_argument("folder")
    s.add_argument("local_dir")
    s.add_argument("--env-file", default="site/.env.production",
                   help="file (relative to the folder) to write VITE_DATA_BASE into; '' to skip")
    s.add_argument("--dry-run", action="store_true")
    s.set_defaults(func=cmd_site)
    p = sub.add_parser("prune", help="delete every site-data version except --keep")
    p.add_argument("folder")
    p.add_argument("--keep", required=True)
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_prune)
    m = sub.add_parser("summary", help="sizes and estimated monthly cost per prefix")
    m.add_argument("folder", nargs="?")
    m.set_defaults(func=cmd_summary)
    a = ap.parse_args()
    a.func(a)


if __name__ == "__main__":
    main()
