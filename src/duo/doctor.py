"""Health check: verify peers, config, readline, MCP, openclaw."""

from __future__ import annotations

import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from .config import DuoConfig, duo_home
from .peers import RUNNERS


@dataclass
class Check:
    name: str
    ok: bool
    detail: str = ""
    fix: str = ""


def _check_peer(name: str) -> Check:
    _, probe = RUNNERS[name]
    path = shutil.which(probe)
    if path:
        return Check(f"peer:{name}", True, path)
    fixes = {
        "claude":   "npm i -g @anthropic-ai/claude-code",
        "codex":    "npm i -g @openai/codex  (or pip install openai-codex)",
        "ollama":   "download from https://ollama.com/download",
        "openclaw": "npm i -g openclaw@latest  &&  openclaw onboard --install-daemon",
    }
    return Check(f"peer:{name}", False, "not on PATH", fixes.get(name, ""))


def _check_readline() -> Check:
    try:
        import readline  # noqa: F401
        return Check("readline", True, "available")
    except ImportError:
        if sys.platform == "win32":
            try:
                import pyreadline3  # noqa: F401
                return Check("readline", True, "pyreadline3")
            except ImportError:
                return Check("readline", False, "missing on win32",
                             "pip install pyreadline3")
        return Check("readline", False, "missing", "pip install readline")


def _check_config(cfg: DuoConfig) -> Check:
    path = duo_home() / "config.toml"
    if path.exists():
        return Check("config", True, str(path))
    return Check("config", True, "(defaults — run `duox init` to write one)")


def _check_context(cwd: Path) -> Check:
    from .context import discover
    files = discover(cwd, duo_home())
    if not files:
        return Check("context files", True,
                     "(none — add CLAUDE.md, AGENTS.md, or DUO.md)")
    return Check("context files", True,
                 ", ".join(f.label for f in files[:4]))


def _check_mcp(cfg: DuoConfig) -> Check:
    servers = (cfg.mcp or {}).get("servers") or {}
    if not servers:
        return Check("mcp", True, "(none configured)")
    return Check("mcp", True, f"{len(servers)} server(s): {', '.join(servers)}")


def _check_openclaw(cfg: DuoConfig) -> Check:
    from .openclaw import openclaw_available
    if "openclaw" not in cfg.peers:
        return Check("openclaw", True, "(not in peers — skipped)")
    if openclaw_available():
        return Check("openclaw", True, "installed")
    return Check("openclaw", False, "in peers but not installed",
                 "npm i -g openclaw@latest")


def run_checks(cfg: DuoConfig, cwd: Path) -> list[Check]:
    out: list[Check] = [_check_readline(), _check_config(cfg),
                        _check_context(cwd), _check_mcp(cfg),
                        _check_openclaw(cfg)]
    for n in cfg.peers:
        if n in RUNNERS:
            out.append(_check_peer(n))
    return out


def format_checks(checks: list[Check]) -> str:
    width = max(len(c.name) for c in checks)
    lines = []
    for c in checks:
        mark = "✓" if c.ok else "✗"
        lines.append(f"  {mark} {c.name.ljust(width)}  {c.detail}")
        if not c.ok and c.fix:
            lines.append(f"    → fix: {c.fix}")
    summary = sum(1 for c in checks if c.ok)
    lines.append(f"\n{summary}/{len(checks)} checks passing.")
    return "\n".join(lines)
