"""Expand `@path` and `@path:start-end` mentions in user input into file excerpts.

Rules:
  - `@file.py`                 → whole file (capped)
  - `@src/`                    → directory listing (one level)
  - `@file.py:12-40`           → lines 12..40 inclusive
  - `@"path with spaces.md"`   → quoted path supported
  - Escape with `\@` to keep a literal `@`.

Only resolves paths inside `cwd` (no `..` escape, no absolute paths to elsewhere).
Silently skips misses — the mention is left as plain text so the model still sees it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


MAX_FILE_BYTES = 64_000
MAX_DIR_ENTRIES = 200

_MENTION_RE = re.compile(
    r'(?<!\\)@(?:"([^"]+)"|([^\s:]+))(?::(\d+)(?:-(\d+))?)?'
)


@dataclass
class Mention:
    raw: str
    path: Path
    start: int | None = None
    end: int | None = None
    is_dir: bool = False


def _safe_resolve(cwd: Path, rel: str) -> Path | None:
    try:
        p = (cwd / rel).resolve()
    except Exception:
        return None
    try:
        p.relative_to(cwd.resolve())
    except ValueError:
        return None
    if not p.exists():
        return None
    return p


def parse(text: str, cwd: Path) -> list[Mention]:
    out: list[Mention] = []
    for m in _MENTION_RE.finditer(text):
        rel = m.group(1) or m.group(2)
        p = _safe_resolve(cwd, rel)
        if not p:
            continue
        start = int(m.group(3)) if m.group(3) else None
        end = int(m.group(4)) if m.group(4) else (start if start else None)
        out.append(Mention(raw=m.group(0), path=p, start=start, end=end,
                           is_dir=p.is_dir()))
    return out


def _render_file(m: Mention) -> str:
    try:
        if m.start is not None:
            lines = m.path.read_text(encoding="utf-8", errors="replace").splitlines()
            s = max(1, m.start) - 1
            e = min(len(lines), m.end or m.start)
            excerpt = "\n".join(lines[s:e])
            header = f"{m.path.name}:{m.start}-{e}"
            return f"\n### @{header}\n```\n{excerpt}\n```\n"
        data = m.path.read_bytes()
        if len(data) > MAX_FILE_BYTES:
            body = data[:MAX_FILE_BYTES].decode("utf-8", errors="replace")
            body += f"\n… (truncated, {len(data) - MAX_FILE_BYTES} more bytes)"
        else:
            body = data.decode("utf-8", errors="replace")
        return f"\n### @{m.path.name}\n```\n{body}\n```\n"
    except Exception as e:
        return f"\n### @{m.path.name}\n(could not read: {e})\n"


def _render_dir(m: Mention) -> str:
    try:
        entries = sorted(m.path.iterdir(), key=lambda p: (p.is_file(), p.name))
    except Exception as e:
        return f"\n### @{m.path.name}/\n(could not list: {e})\n"
    rows = []
    for p in entries[:MAX_DIR_ENTRIES]:
        rows.append(f"  {'d' if p.is_dir() else 'f'} {p.name}")
    extra = "" if len(entries) <= MAX_DIR_ENTRIES else f"\n  … (+{len(entries) - MAX_DIR_ENTRIES} more)"
    return f"\n### @{m.path.name}/\n" + "\n".join(rows) + extra + "\n"


def expand(text: str, cwd: Path) -> tuple[str, list[Mention]]:
    """Return (augmented_text, mentions). The original line is preserved; file
    bodies are appended as a '## Mentions' block so the user's prose is untouched."""
    mentions = parse(text, cwd)
    # unescape \@ → @
    clean = re.sub(r"\\@", "@", text)
    if not mentions:
        return clean, []
    parts = ["\n\n## Mentions"]
    seen: set[Path] = set()
    for m in mentions:
        if m.path in seen and m.start is None:
            continue
        seen.add(m.path)
        parts.append(_render_dir(m) if m.is_dir else _render_file(m))
    return clean + "".join(parts), mentions
