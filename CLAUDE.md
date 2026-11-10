# simon-code-research

A collection of independent code experiments, published to GitHub Pages at
https://ashiklom.github.io/simon-code-research/.

## Experiment layout

Each experiment lives in its own top-level folder. If I don't give a name, pick a short,
informative, lowercase-kebab-case name with no date (e.g. `raster-zonal-stats`). The name
is permanent once published: it is the Pages URL path and the release tag.

```
<folder>/
  README.md        # see "Experiment README" below
  PROMPT.md        # my prompts + Q&A, verbatim (see "Recording the conversation")
  PLAN.md          # latest accepted plan, only if plan mode was used
  TRANSCRIPT.md    # cleaned conversation transcript
  publish.toml     # site build + release-asset manifest (see "Publishing")
  <lockfiles>      # see "Dependencies"
```

- Experiments are standalone: never import code from another experiment. Copy (vendor) code
  from another experiment instead, and note where it came from.
- Shared publishing and execution tooling (CI scripts, transcript conversion, etc.) lives in
  `/_helpers/`. Experiments may call `_helpers/` for running or publishing, but their own
  analysis code must not depend on it.

### Experiment README

GitHub-flavored Markdown containing:
- What the question was and what was done (a few sentences)
- Key results: the headline numbers, figure, or conclusion
- How to reproduce: the exact command(s), e.g. `mise run all`
- Link to the experiment's page: `https://ashiklom.github.io/simon-code-research/<folder>/`

### Root README

`/README.md` is the source for the Pages homepage. Add one line per experiment, newest
first:

```
- [<folder>](<folder>/): one-sentence summary. ([site](https://ashiklom.github.io/simon-code-research/<folder>/))
```

## Recording the conversation

### PROMPT.md
- Copy my messages **verbatim**: the original prompt plus every later message, clarification,
  and answer.
- Also include your questions to me (including AskUserQuestion questions and their options)
  so my answers make sense.
- Separate entries with headings in order, e.g. `## Prompt`, `## Claude: question`,
  `## Answer`, `## Follow-up 2`.
- Record slash commands exactly as I typed them (e.g. `/simplify`); don't expand them.
- Include pasted text in fenced blocks. Save pasted images and files to `<folder>/prompt-assets/`
  and link or embed them.

### PLAN.md
- Write it when I approve a plan in plan mode, word for word as approved.
- If the plan changes later, overwrite it with the latest version. Earlier versions live in
  git history.

### TRANSCRIPT.md
- When the experiment is done, run `uv run _helpers/transcript.py -o <folder>/TRANSCRIPT.md`.
  It defaults to the current session; pass `-s <session-id>` (repeatable) when the work spanned
  several sessions.
- The helper keeps user/assistant text and one-line tool-call summaries, drops tool output,
  thinking, and system context, and redacts the home directory and email addresses. Skim the
  output for anything else sensitive before committing; use `--redact <string>` if needed.

## Dependencies

Each experiment pins its own dependencies with committed lockfiles. Default order:

1. **mise** (`mise.toml`): pins tool versions (Python, R, Node, uv, pixi, quarto, …) and
   defines the experiment's tasks (`mise run <task>`).
2. **uv** (`pyproject.toml` + `uv.lock`): Python packages.
3. **rig + renv** (`renv.lock`): R. rig selects the R version; renv pins packages.
4. **pixi** (`pixi.toml` + `pixi.lock`): when you need conda-forge packages (GDAL/geospatial
   stack, compiled libraries, mixed R+Python).
5. **Nix** (`flake.nix` + `flake.lock`): last resort, for system dependencies the others can't
   provide.

For JS/TS, use a Node pinned in mise plus a package-manager lockfile. If something can't
reasonably be pinned (e.g. CUDA drivers, credentials), list it in the README under
"Requirements".

## Data and large files

- Don't commit data that can be downloaded. Commit a download script or task that fetches it to
  a git-ignored path.
- Release assets are only for things the site needs: figures, small processed outputs. Upload
  raw results only when an interactive visualization reads them.
- Rule of thumb: files over ~4 MB don't go in git. Put them in the release if the site needs
  them; otherwise leave them unpublished. Exceptions are fine; mention them when you make one.

## Publishing (GitHub Pages)

`.github/workflows/pages.yml` runs `_helpers/build_site.py` on every push to `main` and every
release publish/edit. CI **never re-runs experiments**: it only renders and publishes outputs
already committed or uploaded to releases.

- Preview one experiment locally: `uv run _helpers/build_site.py --only <folder>`, then open
  `_site/<folder>/index.html`. Add `--skip-assets` if the release doesn't exist yet.
- A failing experiment build fails the whole deploy, so the build must pass locally first.

### publish.toml (per-experiment manifest)

```toml
# Optional. Command that renders the site from committed outputs into `output`.
# Must be fast and must not re-run analysis. Omit it to render README.md as the page.
build = "mise run site"
output = "_site"            # copied to /<folder>/ on Pages (git-ignored)

# Shown in the page colophon
models = ["claude-opus-5-5"]
tools = ["quarto", "python"]

# Files downloaded from the GitHub release tagged <folder> before `build` runs
[[assets]]
name = "fig-results.png"    # asset name in the release
dest = "figures/fig-results.png"  # path relative to <folder>/
```

- Each experiment chooses its own site generator (Quarto, MkDocs, plain HTML, Vite, …).
  Install it through the experiment's own mise/pixi/uv config so CI can reproduce the build.
  CI only provides `mise`, `uv`, and `gh`. `build` runs from `<folder>/` with
  `SITE_BASE_URL` set to the experiment's Pages URL.
- Without `build`, `README.md` becomes the page: embedded images (`![](figures/x.png)`) are
  copied over, and links to other repo files point to GitHub.
- CI renders the homepage from `/README.md` and adds a colophon footer to every experiment page
  with: build timestamp, last-updated date (last commit touching `<folder>/`), short commit SHA
  linked to `<folder>/` on GitHub, models and tools from `publish.toml`, and links to
  `PROMPT.md`, `PLAN.md` (if present), and `TRANSCRIPT.md`.

### Releases

- Each experiment has exactly one release, tagged `<folder>`, which you update in place.
- Create it with `gh release create <folder>`. Upload with `gh release upload <folder> <files> --clobber`.
- **Ask me before creating a release or uploading to one.** List the files and their sizes.
- Every uploaded asset must appear in `publish.toml`'s `[[assets]]`, and every listed asset
  must exist in the release.

## Git workflow

- Work on a branch named `exp/<folder>` (or a short descriptive name for non-experiment
  changes). Push it to `origin` regularly as you go.
- Make one logical commit per change. Keep `PROMPT.md` and `PLAN.md` updates in their own
  commits, separate from code (e.g. `<folder>: update PLAN.md`). Prefix commit subjects with
  `<folder>: `.
- When done: `git fetch`, rebase the branch onto `origin/main`, fast-forward `main` to it, and
  push `main`. Then delete the branch locally and on `origin`.
