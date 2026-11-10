#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Convert Claude Code session logs (JSONL) into a cleaned, publishable TRANSCRIPT.md.

Keeps user and assistant text plus one-line summaries of tool calls. Drops tool output,
thinking, subagent (sidechain) traffic, and system/context messages. Redacts the home
directory and email addresses.

Usage:
    uv run _helpers/transcript.py -o <folder>/TRANSCRIPT.md            # current session
    uv run _helpers/transcript.py -o <folder>/TRANSCRIPT.md -s ID -s ID # several sessions
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import subprocess
import sys
from pathlib import Path

HOME = str(Path.home())
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
EMAIL_ALLOW = re.compile(r"(^noreply@anthropic\.com$|@users\.noreply\.github\.com$)")
SYSTEM_REMINDER_RE = re.compile(r"<system-reminder>.*?</system-reminder>\s*", re.S)
DROP_TAGS_RE = re.compile(
    r"<(local-command-stdout|local-command-stderr|bash-stdout|bash-stderr|command-message)>"
    r".*?</\1>\s*",
    re.S,
)
MAX_INLINE = 160


def repo_root() -> Path:
    out = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True
    )
    return Path(out.stdout.strip()) if out.returncode == 0 else Path.cwd()


def project_log_dir(root: Path) -> Path:
    # Claude Code stores logs under ~/.claude/projects/<cwd with / and . replaced by ->
    return Path(HOME) / ".claude" / "projects" / re.sub(r"[/.]", "-", str(root))


def resolve_session(arg: str | None, log_dir: Path) -> Path:
    if arg and Path(arg).is_file():
        return Path(arg)
    session_id = arg or os.environ.get("CLAUDE_CODE_SESSION_ID")
    if session_id:
        path = log_dir / f"{session_id}.jsonl"
        if not path.is_file():
            sys.exit(f"Session log not found: {path}")
        return path
    logs = sorted(log_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime)
    if not logs:
        sys.exit(f"No session logs in {log_dir}")
    return logs[-1]


def redact(text: str, extra: list[str]) -> str:
    text = text.replace(HOME, "~")
    text = text.replace(re.sub(r"[/.]", "-", HOME), "~")  # as encoded in log dir names
    text = EMAIL_RE.sub(
        lambda m: m.group(0) if EMAIL_ALLOW.search(m.group(0)) else "[email]", text
    )
    for s in extra:
        text = text.replace(s, "[redacted]")
    return text


def clean_user_text(text: str) -> str:
    """Strip injected context; render slash commands and ! commands as typed."""
    text = SYSTEM_REMINDER_RE.sub("", text)
    text = DROP_TAGS_RE.sub("", text)
    name = re.search(r"<command-name>(.*?)</command-name>", text, re.S)
    if name:
        args = re.search(r"<command-args>(.*?)</command-args>", text, re.S)
        cmd = name.group(1).strip()
        if not cmd.startswith("/"):
            cmd = "/" + cmd
        return f"`{cmd} {args.group(1).strip() if args else ''}`".replace(" `", "`")
    bash = re.search(r"<bash-input>(.*?)</bash-input>", text, re.S)
    if bash:
        return f"`! {bash.group(1).strip()}`"
    return text.strip()


def demote_headings(text: str, levels: int = 2) -> str:
    """Push Markdown headings down so they nest under the ## User / ## Claude headings."""
    out, fence = [], None
    for line in text.split("\n"):
        m = re.match(r"\s*(`{3,}|~{3,})", line)
        if m and (fence is None or m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence)):
            fence = None if fence else m.group(1)
        elif fence is None and re.match(r"#{1,6} ", line):
            hashes = len(line) - len(line.lstrip("#"))
            line = "#" * min(6, hashes + levels) + line[hashes:]
        out.append(line)
    return "\n".join(out)


def short(s: str, n: int = MAX_INLINE) -> str:
    s = " ".join(str(s).split())
    return s if len(s) <= n else s[: n - 1] + "…"


def rel(path: str, root: Path) -> str:
    try:
        return str(Path(path).relative_to(root))
    except ValueError:
        return path


def code(s: str) -> str:
    """Inline code span that survives backticks in s."""
    ticks = "``" if "`" in s else "`"
    pad = " " if s.startswith("`") or s.endswith("`") else ""
    return f"{ticks}{pad}{s}{pad}{ticks}"


def summarize_tool(name: str, inp: dict, root: Path) -> str:
    match name:
        case "Bash":
            desc = inp.get("description")
            cmd = code(short(inp.get("command", "")))
            return f"{desc}: {cmd}" if desc else cmd
        case "Read" | "Write" | "Edit" | "NotebookEdit":
            return code(rel(inp.get("file_path") or inp.get("notebook_path", ""), root))
        case "Grep" | "Glob":
            where = f" in {code(rel(inp['path'], root))}" if inp.get("path") else ""
            return f"{code(short(inp.get('pattern', '')))}{where}"
        case "WebFetch":
            return inp.get("url", "")
        case "WebSearch":
            return code(short(inp.get("query", "")))
        case "Agent" | "Task":
            kind = inp.get("subagent_type", "general-purpose")
            return f"{inp.get('description', '')} ({kind})"
        case "Skill":
            return code(inp.get("skill", ""))
        case "ToolSearch":
            return code(short(inp.get("query", "")))
        case _:
            return code(short(json.dumps(inp, ensure_ascii=False)))


def render_questions(inp: dict) -> list[str]:
    lines = []
    for q in inp.get("questions", []):
        lines.append(f"> **{q.get('header', 'Question')}:** {q.get('question', '')}")
        for opt in q.get("options", []):
            lines.append(f"> - *{opt.get('label', '')}*: {opt.get('description', '')}")
        lines.append(">")
    return lines[:-1] if lines else lines


def answer_text(result_block: dict, tool_use_result) -> str:
    if isinstance(tool_use_result, dict) and isinstance(tool_use_result.get("answers"), dict):
        answers = tool_use_result["answers"]
        return "\n".join(f"- {q}\n  → **{a}**" for q, a in answers.items())
    content = result_block.get("content")
    if isinstance(content, list):
        content = "\n".join(b.get("text", "") for b in content if isinstance(b, dict))
    return str(content or "")


class Transcript:
    def __init__(self, root: Path, out: Path, redactions: list[str]):
        self.root = root
        self.out = out
        self.redactions = redactions
        self.lines: list[str] = []
        self.speaker: str | None = None
        self.pending_questions: dict[str, dict] = {}
        self.models: set[str] = set()
        self.n_images = 0

    def emit(self, *lines: str) -> None:
        self.lines.extend(lines)

    def start(self, speaker: str) -> None:
        if self.speaker != speaker:
            self.emit("", f"## {speaker}", "")
            self.speaker = speaker

    def save_image(self, block: dict, session_id: str) -> str | None:
        src = block.get("source", {})
        if src.get("type") != "base64":
            return None
        ext = src.get("media_type", "image/png").split("/")[-1].replace("jpeg", "jpg")
        self.n_images += 1
        assets = self.out.parent / "prompt-assets"
        assets.mkdir(parents=True, exist_ok=True)
        path = assets / f"transcript-{session_id[:8]}-{self.n_images}.{ext}"
        path.write_bytes(base64.b64decode(src["data"]))
        return str(path.relative_to(self.out.parent))

    def add_session(self, path: Path) -> None:
        session_id = path.stem
        rows = [json.loads(line) for line in path.open() if line.strip()]
        first = next((r.get("timestamp") for r in rows if r.get("timestamp")), "")
        self.emit("", f"<!-- session {session_id} -->", f"*Session started {first[:16].replace('T', ' ')} UTC*")
        self.speaker = None
        for r in rows:
            if r.get("isSidechain") or r.get("isMeta"):
                continue
            if r.get("isCompactSummary"):
                self.start("User")
                self.emit("*[Earlier context was compacted]*", "")
                continue
            msg = r.get("message") or {}
            if r.get("type") == "user":
                self.user(msg, r, session_id)
            elif r.get("type") == "assistant":
                if msg.get("model") and not msg["model"].startswith("<"):
                    self.models.add(msg["model"])
                self.assistant(msg)

    def user(self, msg: dict, row: dict, session_id: str) -> None:
        content = msg.get("content")
        blocks = [{"type": "text", "text": content}] if isinstance(content, str) else content or []
        for b in blocks:
            if b.get("type") == "tool_result":
                q = self.pending_questions.pop(b.get("tool_use_id"), None)
                if q is not None:
                    self.start("User")
                    self.emit("*Answered:*", "", answer_text(b, row.get("toolUseResult")), "")
                continue
            if b.get("type") == "text":
                text = clean_user_text(b.get("text", ""))
                if text:
                    self.start("User")
                    self.emit(demote_headings(text), "")
            elif b.get("type") == "image":
                rel_path = self.save_image(b, session_id)
                if rel_path:
                    self.start("User")
                    self.emit(f"![pasted image]({rel_path})", "")

    def assistant(self, msg: dict) -> None:
        for b in msg.get("content") or []:
            kind = b.get("type")
            if kind == "text" and b.get("text", "").strip():
                self.start("Claude")
                self.emit(demote_headings(b["text"].strip()), "")
            elif kind == "tool_use":
                self.start("Claude")
                name, inp = b.get("name", "?"), b.get("input") or {}
                if name == "AskUserQuestion":
                    self.pending_questions[b.get("id")] = inp
                    self.emit("*Asked:*", "", *render_questions(inp), "")
                elif name == "ExitPlanMode" and inp.get("plan"):
                    self.emit(
                        "<details><summary><b>Proposed plan</b></summary>", "",
                        inp["plan"].strip(), "", "</details>", "",
                    )
                else:
                    self.emit(f"- **{name}**: {summarize_tool(name, inp, self.root)}", "")

    def render(self, title: str) -> str:
        header = [f"# {title}", ""]
        if self.models:
            header.append(f"Model(s): {', '.join(sorted(self.models))}")
        header.append(
            "Tool output, thinking, and system context are omitted; tool calls are summarized."
        )
        body = "\n".join(header + self.lines)
        body = re.sub(r"\n{3,}", "\n\n", body)
        # Consecutive tool bullets read better as one list.
        body = re.sub(r"(?m)^(- \*\*.+)\n\n(?=- \*\*)", r"\1\n", body)
        return redact(body.strip() + "\n", self.redactions)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("-o", "--out", required=True, type=Path, help="output Markdown file")
    p.add_argument(
        "-s", "--session", action="append",
        help="session ID or path to .jsonl; repeatable, rendered in order "
             "(default: $CLAUDE_CODE_SESSION_ID, else the newest log for this repo)",
    )
    p.add_argument("--title", default="Transcript")
    p.add_argument("--redact", action="append", default=[], help="extra string to redact; repeatable")
    args = p.parse_args()

    root = repo_root()
    log_dir = project_log_dir(root)
    sessions = [resolve_session(s, log_dir) for s in (args.session or [None])]

    t = Transcript(root, args.out.resolve(), args.redact)
    for s in sessions:
        t.add_session(s)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(t.render(args.title))
    print(f"Wrote {args.out} from {len(sessions)} session(s)")


if __name__ == "__main__":
    main()
