"""Skills loader: markdown files in ~/.duo/skills/*.md.

Each skill is a markdown file with optional YAML frontmatter:

    ---
    name: testing
    match: ["test", "pytest", "unit test"]
    always: false
    ---
    # Skill body (gets injected into supervisor prompt)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


_FRONT_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


@dataclass
class Skill:
    name: str
    path: Path
    body: str
    match: list[str] = field(default_factory=list)
    always: bool = False

    def applies_to(self, text: str) -> bool:
        if self.always:
            return True
        if not self.match:
            return False
        t = text.lower()
        return any(m.lower() in t for m in self.match)


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    m = _FRONT_RE.match(text)
    if not m:
        return {}, text
    fm_raw = m.group(1)
    body = text[m.end():]
    # minimal YAML-ish parser: key: value, lists as [a, b, c] or value, value
    meta: dict = {}
    for line in fm_raw.splitlines():
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        k = k.strip()
        v = v.strip()
        if v.startswith("[") and v.endswith("]"):
            items = [x.strip().strip('"').strip("'") for x in v[1:-1].split(",") if x.strip()]
            meta[k] = items
        elif v.lower() in ("true", "false"):
            meta[k] = v.lower() == "true"
        else:
            meta[k] = v.strip('"').strip("'")
    return meta, body


def load_skills(skills_dir: Path) -> list[Skill]:
    if not skills_dir.exists():
        return []
    out: list[Skill] = []
    for p in sorted(skills_dir.glob("*.md")):
        try:
            text = p.read_text(encoding="utf-8")
        except Exception:
            continue
        meta, body = _parse_frontmatter(text)
        out.append(Skill(
            name=str(meta.get("name") or p.stem),
            path=p,
            body=body.strip(),
            match=list(meta.get("match") or []),
            always=bool(meta.get("always", False)),
        ))
    return out


def select_skills(skills: list[Skill], text: str, *, max_chars: int = 4000) -> list[Skill]:
    chosen: list[Skill] = []
    total = 0
    for s in skills:
        if not s.applies_to(text):
            continue
        if total + len(s.body) > max_chars:
            break
        chosen.append(s)
        total += len(s.body)
    return chosen


def render_skills(skills: list[Skill]) -> str:
    if not skills:
        return ""
    parts = ["\n\n## Loaded skills\n"]
    for s in skills:
        parts.append(f"\n### {s.name}\n{s.body}\n")
    return "".join(parts)
