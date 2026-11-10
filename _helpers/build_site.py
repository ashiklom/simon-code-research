#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "markdown-it-py[linkify]>=3",
#     "mdit-py-plugins>=0.4",
# ]
# ///
"""Build the GitHub Pages site from committed outputs. Never re-runs experiments.

For each top-level experiment folder (not starting with `.` or `_`) with a README.md:
  1. Download release assets listed in <folder>/publish.toml from the release tagged <folder>.
  2. Run the manifest's `build` command (if any) and copy its `output` to <out>/<folder>/;
     otherwise render <folder>/README.md to <out>/<folder>/index.html.
  3. Inject a colophon into every HTML page of the experiment.
Then render the root README.md as the homepage.

Usage:
    uv run _helpers/build_site.py                       # everything -> _site/
    uv run _helpers/build_site.py --only my-experiment  # one experiment (plus homepage)
    uv run _helpers/build_site.py --skip-assets         # don't contact GitHub releases
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tomllib
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlsplit

from markdown_it import MarkdownIt
from mdit_py_plugins.footnote import footnote_plugin
from mdit_py_plugins.tasklists import tasklists_plugin

ROOT = Path(__file__).resolve().parent.parent
SITE_BASE = "https://{owner}.github.io/{name}/"
STYLE = Path(__file__).with_name("site.css")


class BuildError(Exception):
    pass


def run(cmd: list[str] | str, cwd: Path = ROOT, env: dict | None = None, **kw) -> str:
    res = subprocess.run(
        cmd, cwd=cwd, env=env, shell=isinstance(cmd, str),
        capture_output=kw.get("capture", True), text=True,
    )
    if res.returncode != 0:
        raise BuildError(f"command failed ({res.returncode}): {cmd}\n{res.stderr or ''}")
    return (res.stdout or "").strip()


# --- git / repo metadata -------------------------------------------------------------


def repo_slug() -> str:
    if os.environ.get("GITHUB_REPOSITORY"):
        return os.environ["GITHUB_REPOSITORY"]
    url = run(["git", "remote", "get-url", "origin"])
    m = re.search(r"github\.com[:/](.+?)(?:\.git)?$", url)
    if not m:
        raise BuildError(f"can't parse GitHub repo from origin URL: {url}")
    return m.group(1)


def head_sha() -> str:
    return os.environ.get("GITHUB_SHA") or run(["git", "rev-parse", "HEAD"])


def last_updated(folder: str) -> str:
    return run(["git", "log", "-1", "--format=%cs", "--", folder]) or "uncommitted"


# --- markdown rendering --------------------------------------------------------------

MD = (
    MarkdownIt("gfm-like", {"linkify": True, "typographer": False, "html": True})
    .use(footnote_plugin)
    .use(tasklists_plugin)
)
LINK_RE = re.compile(r'(\s(?:href|src))="([^"]*)"')


def is_external(url: str) -> bool:
    return bool(urlsplit(url).scheme) or url.startswith(("#", "//", "mailto:"))


def rewrite_links(body: str, src_dir: Path, site_dir: Path, ctx: "Context") -> str:
    """Make relative links in rendered Markdown work on the site.

    - Target already published under site_dir: keep.
    - Embedded file (src=, e.g. a figure) inside the source folder: copy into site_dir, keep.
    - Anything else in the repo (Markdown, code, folders): point to GitHub.
    """

    def fix(m: re.Match) -> str:
        attr, url = m.groups()
        url = html.unescape(url)
        if not url or is_external(url):
            return m.group(0)
        parts = urlsplit(url)
        target_rel = unquote(parts.path)
        target = (src_dir / target_rel).resolve()
        published = (site_dir / target_rel).resolve()
        if published.exists() and published.is_relative_to(ctx.out):
            return m.group(0)
        if attr.strip() == "src" and target.is_file() and target.is_relative_to(src_dir):
            published.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, published)
            return m.group(0)
        if target.exists() and target.is_relative_to(ROOT):
            kind = "tree" if target.is_dir() else "blob"
            path = target.relative_to(ROOT).as_posix()
            frag = f"#{parts.fragment}" if parts.fragment else ""
            return f'{attr}="{html.escape(ctx.github_url(kind, path) + frag)}"'
        print(f"  warning: broken link {url!r} in {src_dir.relative_to(ROOT) or '.'}", file=sys.stderr)
        return m.group(0)

    return LINK_RE.sub(fix, body)


def page(title: str, body: str, css_href: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<link rel="stylesheet" href="{css_href}">
</head>
<body>
<main class="markdown-body">
{body}
</main>
</body>
</html>
"""


def md_title(text: str, fallback: str) -> str:
    m = re.search(r"^#\s+(.+)$", text, re.M)
    return m.group(1).strip() if m else fallback


# --- colophon ------------------------------------------------------------------------


def colophon(ctx: "Context", folder: str | None, manifest: dict) -> str:
    sha = ctx.sha
    items = [f"Built {ctx.built}"]
    if folder:
        items.append(f"last updated {last_updated(folder)}")
        items.append(
            f'source <a href="{ctx.github_url("tree", folder)}">{folder}/</a> '
            f'@ <a href="https://github.com/{ctx.slug}/commit/{sha}"><code>{sha[:7]}</code></a>'
        )
        if manifest.get("models"):
            items.append("models: " + ", ".join(html.escape(m) for m in manifest["models"]))
        if manifest.get("tools"):
            items.append("tools: " + ", ".join(html.escape(t) for t in manifest["tools"]))
        docs = [
            f'<a href="{ctx.github_url("blob", f"{folder}/{name}")}">{name}</a>'
            for name in ("PROMPT.md", "PLAN.md", "TRANSCRIPT.md")
            if (ROOT / folder / name).exists()
        ]
        if docs:
            items.append(" · ".join(docs))
        items.append(f'<a href="{ctx.site_url}">all experiments</a>')
    else:
        items.append(
            f'<a href="https://github.com/{ctx.slug}">source</a> '
            f'@ <a href="https://github.com/{ctx.slug}/commit/{sha}"><code>{sha[:7]}</code></a>'
        )
    style = (
        "margin:3rem auto 1rem;max-width:60rem;padding:.75rem 1rem;border-top:1px solid #8884;"
        "font:13px/1.5 system-ui,sans-serif;color:#666;text-align:center"
    )
    return f'<footer class="colophon" style="{style}">{" — ".join(items)}</footer>'


def inject_colophon(f: Path, footer: str) -> None:
    text = f.read_text(errors="surrogateescape")
    idx = text.lower().rfind("</body>")
    text = text[:idx] + footer + "\n" + text[idx:] if idx >= 0 else text + footer
    f.write_text(text, errors="surrogateescape")


# --- experiments ---------------------------------------------------------------------


class Context:
    def __init__(self, out: Path, skip_assets: bool):
        self.out = out.resolve()
        self.skip_assets = skip_assets
        self.slug = repo_slug()
        self.sha = head_sha()
        self.built = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        owner, name = self.slug.split("/")
        self.site_url = SITE_BASE.format(owner=owner, name=name)

    def github_url(self, kind: str, path: str) -> str:
        return f"https://github.com/{self.slug}/{kind}/{self.sha}/{path}"


def load_manifest(folder: Path) -> dict:
    path = folder / "publish.toml"
    if not path.exists():
        print(f"  note: {folder.name}/publish.toml missing; rendering README.md", file=sys.stderr)
        return {}
    manifest = tomllib.loads(path.read_text())
    unknown = set(manifest) - {"build", "output", "models", "tools", "assets"}
    if unknown:
        raise BuildError(f"{path}: unknown keys {sorted(unknown)}")
    return manifest


def fetch_assets(folder: Path, assets: list[dict], ctx: Context) -> None:
    if not assets:
        return
    if ctx.skip_assets:
        print(f"  skipping {len(assets)} release asset(s)")
        return
    tag = folder.name
    info = json.loads(run(["gh", "release", "view", tag, "--repo", ctx.slug, "--json", "assets"]))
    available = {a["name"] for a in info["assets"]}
    listed = {a["name"] for a in assets}
    if missing := listed - available:
        raise BuildError(f"release {tag!r} is missing assets listed in publish.toml: {sorted(missing)}")
    if extra := available - listed:
        print(f"  warning: release {tag!r} has assets not in publish.toml: {sorted(extra)}", file=sys.stderr)
    for a in assets:
        dest = (folder / a["dest"]).resolve()
        if not dest.is_relative_to(folder.resolve()):
            raise BuildError(f"asset dest escapes {tag}/: {a['dest']}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        run(["gh", "release", "download", tag, "--repo", ctx.slug,
             "--pattern", a["name"], "--output", str(dest), "--clobber"])
        print(f"  asset {a['name']} -> {dest.relative_to(ROOT)}")


def build_experiment(folder: Path, ctx: Context) -> None:
    print(f"[{folder.name}]")
    manifest = load_manifest(folder)
    fetch_assets(folder, manifest.get("assets", []), ctx)
    site_dir = ctx.out / folder.name
    if site_dir.exists():
        shutil.rmtree(site_dir)

    if build := manifest.get("build"):
        env = os.environ | {
            "MISE_YES": "1",
            "MISE_TRUSTED_CONFIG_PATHS": str(ROOT),
            "SITE_BASE_URL": f"{ctx.site_url}{folder.name}/",
        }
        print(f"  build: {build}")
        run(build, cwd=folder, env=env, capture=False)
        output = (folder / manifest.get("output", "_site")).resolve()
        if not output.is_dir() or not output.is_relative_to(folder.resolve()):
            raise BuildError(f"build output {output} is not a directory inside {folder.name}/")
        shutil.copytree(output, site_dir)
    else:
        readme = (folder / "README.md").read_text()
        site_dir.mkdir(parents=True)
        body = rewrite_links(MD.render(readme), folder, site_dir, ctx)
        (site_dir / "index.html").write_text(page(md_title(readme, folder.name), body, "../style.css"))

    footer = colophon(ctx, folder.name, manifest)
    for f in site_dir.rglob("*.html"):
        inject_colophon(f, footer)


def build_home(ctx: Context) -> None:
    print("[homepage]")
    readme = (ROOT / "README.md").read_text()
    body = rewrite_links(MD.render(readme), ROOT, ctx.out, ctx)
    index = ctx.out / "index.html"
    index.write_text(page(md_title(readme, ctx.slug), body, "style.css"))
    inject_colophon(index, colophon(ctx, None, {}))


def experiments() -> list[Path]:
    return sorted(
        d for d in ROOT.iterdir()
        if d.is_dir() and not d.name.startswith((".", "_")) and (d / "README.md").exists()
    )


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out", type=Path, default=ROOT / "_site")
    p.add_argument("--only", action="append", help="build only this experiment folder; repeatable")
    p.add_argument("--skip-assets", action="store_true", help="don't download release assets")
    args = p.parse_args()
    sys.stdout.reconfigure(line_buffering=True)  # keep stdout/stderr interleaved in CI logs

    ctx = Context(args.out, args.skip_assets)
    folders = experiments()
    if args.only:
        unknown = set(args.only) - {f.name for f in folders}
        if unknown:
            sys.exit(f"unknown experiment(s): {sorted(unknown)}")
        folders = [f for f in folders if f.name in args.only]
    else:
        shutil.rmtree(ctx.out, ignore_errors=True)
    ctx.out.mkdir(parents=True, exist_ok=True)
    shutil.copy2(STYLE, ctx.out / "style.css")
    (ctx.out / ".nojekyll").touch()

    failed = []
    for folder in folders:
        try:
            build_experiment(folder, ctx)
        except (BuildError, OSError, tomllib.TOMLDecodeError, KeyError) as e:
            print(f"  ERROR: {e}", file=sys.stderr)
            failed.append(folder.name)
    build_home(ctx)

    if failed:
        sys.exit(f"Failed to build: {', '.join(failed)}")
    print(f"Site written to {ctx.out}")


if __name__ == "__main__":
    main()
