"""MCP server pass-through: translate duo's [mcp] config into a JSON file
understood by `claude --mcp-config <path>`.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path


def write_mcp_config(mcp: dict, sessions_dir: Path | None = None) -> Path | None:
    """Write duo's MCP config to a JSON file. Returns the path or None if empty.

    Input shape (from duo config.toml):
        [mcp.servers.<name>]
        command = "npx"
        args    = ["-y", "@upstash/context7-mcp"]
        env     = { KEY = "val" }

    Output shape (Claude Code --mcp-config):
        {"mcpServers": {"<name>": {"command": "...", "args": [...], "env": {...}}}}
    """
    servers = (mcp or {}).get("servers") or {}
    if not servers:
        return None
    payload = {"mcpServers": {}}
    for name, spec in servers.items():
        entry: dict = {"command": spec.get("command", "")}
        if spec.get("args"):
            entry["args"] = list(spec["args"])
        if spec.get("env"):
            entry["env"] = dict(spec["env"])
        payload["mcpServers"][name] = entry

    base = sessions_dir or Path(tempfile.gettempdir())
    base.mkdir(parents=True, exist_ok=True)
    path = base / "mcp_config.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path
