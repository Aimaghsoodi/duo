"""Project / user context files, auto-injected into the supervisor prompt.

Looks for (in order):
    ./DUO.md
    ./CLAUDE.md
    ./AGENTS.md
    ~/.duo/DUO.md
    ~/.duo/notes.md          (written by /remember)

Each found file becomes a block in the injected context.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


CONTEXT_FILENAMES = ("DUO.md", "CLAUDE.md", "AGENTS.md")


@dataclass
class ContextFile:
    label: str
    path: Path
    body: str


def discover(cwd: Path, duo_home: Path) -> list[ContextFile]:
    out: list[ContextFile] = []
    seen: set[Path] = set()
    # walk up from cwd to the drive/fs root, picking up any context file we find
    for d in [cwd] + list(cwd.parents):
        for name in CONTEXT_FILENAMES:
            p = d / name
            if p.exists() and p.resolve() not in seen:
                try:
                    out.append(ContextFile(label=f"{name} @ {d}",
                                           path=p,
                                           body=p.read_text(encoding="utf-8").strip()))
                    seen.add(p.resolve())
                except Exception:
                    pass
    # user-global
    for name in ("DUO.md", "notes.md"):
        p = duo_home / name
        if p.exists() and p.resolve() not in seen:
            try:
                out.append(ContextFile(label=f"~/.duo/{name}",
                                       path=p,
                                       body=p.read_text(encoding="utf-8").strip()))
                seen.add(p.resolve())
            except Exception:
                pass
    return out


def render(files: list[ContextFile], *, max_chars: int = 12000) -> str:
    if not files:
        return ""
    parts = ["\n\n## Project context\n"]
    total = 0
    for f in files:
        if not f.body:
            continue
        chunk = f"\n### {f.label}\n{f.body}\n"
        if total + len(chunk) > max_chars:
            parts.append(f"\n### {f.label}\n(truncated — {len(f.body)} chars)\n")
            break
        parts.append(chunk)
        total += len(chunk)
    return "".join(parts)
