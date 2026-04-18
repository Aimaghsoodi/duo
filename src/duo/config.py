"""DuoX configuration: ~/.duo/config.toml + defaults + path layout."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

try:
    import tomllib  # py311+
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore


def duo_home() -> Path:
    override = os.environ.get("DUO_HOME")
    return Path(override) if override else Path.home() / ".duo"


def _deep_merge(a: dict, b: dict) -> dict:
    """Return a new dict: a merged with b, b taking precedence. Recurses into nested dicts."""
    out = dict(a)
    for k, v in b.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


@dataclass
class DuoConfig:
    peers: list[str] = field(default_factory=lambda: ["claude", "codex"])
    supervisor: str = "claude"
    ollama_model: str = "llama3.1"
    tui: str = "auto"                 # auto|on|off
    max_steps: int = 30
    skills_dir: Path = field(default_factory=lambda: duo_home() / "skills")
    sessions_dir: Path = field(default_factory=lambda: duo_home() / "sessions")
    log_level: str = "info"
    hooks: dict = field(default_factory=dict)         # {"pre_step": [...], "post_step": [...]}
    mcp: dict = field(default_factory=dict)           # raw table passed through to claude
    openclaw: dict = field(default_factory=dict)      # {"thinking": "high", "args": [...]}
    parallel_default: bool = True
    api_port: int = 8787
    raw: dict = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path | None = None, *,
             project_dir: Path | None = None) -> "DuoConfig":
        home = duo_home()
        home.mkdir(parents=True, exist_ok=True)
        path = path or home / "config.toml"
        raw: dict = {}
        if path.exists():
            with path.open("rb") as f:
                raw = tomllib.load(f)
        # project-level override: ./.duo.toml merged on top
        proj = project_dir or Path.cwd()
        proj_cfg = proj / ".duo.toml"
        if proj_cfg.exists():
            try:
                with proj_cfg.open("rb") as f:
                    proj_raw = tomllib.load(f)
                raw = _deep_merge(raw, proj_raw)
            except Exception:
                pass
        if not raw:
            return cls()

        cfg = cls(raw=raw)
        if "peers" in raw and isinstance(raw["peers"], list):
            cfg.peers = [str(x) for x in raw["peers"]]
        cfg.supervisor = raw.get("supervisor", cfg.supervisor)
        cfg.ollama_model = raw.get("ollama_model", cfg.ollama_model)
        cfg.tui = raw.get("tui", cfg.tui)
        cfg.max_steps = int(raw.get("max_steps", cfg.max_steps))
        cfg.log_level = raw.get("log_level", cfg.log_level)
        cfg.parallel_default = bool(raw.get("parallel_default", cfg.parallel_default))
        cfg.api_port = int(raw.get("api_port", cfg.api_port))

        if "skills_dir" in raw:
            cfg.skills_dir = Path(os.path.expanduser(raw["skills_dir"]))
        if "sessions_dir" in raw:
            cfg.sessions_dir = Path(os.path.expanduser(raw["sessions_dir"]))

        cfg.hooks = raw.get("hooks", {}) or {}
        cfg.mcp = raw.get("mcp", {}) or {}
        cfg.openclaw = raw.get("openclaw", {}) or {}

        cfg.skills_dir.mkdir(parents=True, exist_ok=True)
        cfg.sessions_dir.mkdir(parents=True, exist_ok=True)
        return cfg


EXAMPLE_CONFIG = """\
# ~/.duo/config.toml — DuoX configuration
peers      = ["claude", "codex"]      # also: "ollama", "openclaw"
supervisor = "claude"
ollama_model = "llama3.1"
tui        = "auto"                    # auto | on | off
max_steps  = 30
parallel_default = true   # fan every goal out to all executor peers simultaneously
api_port   = 8787

[hooks]
pre_step  = []    # e.g. ["echo step starting"]
post_step = []    # e.g. ["pytest -q", "ruff check ."]

[mcp.servers.context7]
# passed through to `claude --mcp-config`
command = "npx"
args    = ["-y", "@upstash/context7-mcp"]

[openclaw]
# Requires `npm i -g openclaw@latest` + `openclaw onboard --install-daemon`.
thinking = "high"
args     = []    # extra args appended to `openclaw agent ...`
"""
