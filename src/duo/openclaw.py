"""OpenClaw integration helpers (beyond the peer runner).

The peer runner (`run_openclaw` in peers.py) handles the conversational
`openclaw agent --message ...` call.

This module wraps the other sub-commands you'd want from inside duo:

  - `openclaw doctor`                      → health of gateway + channels
  - `openclaw message send --to X -m ...`  → send via any paired channel
  - `openclaw pairing list <channel>`      → list pending pairings

All calls are synchronous and return (stdout, rc).
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from typing import Optional


def openclaw_available() -> bool:
    return shutil.which("openclaw") is not None


def _run(args: list[str], *, cwd: Optional[str] = None, timeout: float = 60.0
         ) -> tuple[str, int]:
    try:
        p = subprocess.run(
            [shutil.which("openclaw") or "openclaw", *args],
            cwd=cwd, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout,
        )
        return ((p.stdout or "") + (p.stderr or ""), p.returncode)
    except FileNotFoundError:
        return ("openclaw not installed (try: npm i -g openclaw@latest)", 127)
    except subprocess.TimeoutExpired:
        return (f"openclaw timed out after {timeout}s", 124)
    except Exception as e:
        return (f"openclaw error: {e}", 1)


@dataclass
class OcResult:
    ok: bool
    text: str
    rc: int


def doctor() -> OcResult:
    text, rc = _run(["doctor"])
    return OcResult(ok=(rc == 0), text=text, rc=rc)


def send_message(to: str, message: str, *, channel: Optional[str] = None) -> OcResult:
    args = ["message", "send", "--to", to, "--message", message]
    if channel:
        args += ["--channel", channel]
    text, rc = _run(args)
    return OcResult(ok=(rc == 0), text=text, rc=rc)


def list_pairings(channel: str) -> OcResult:
    text, rc = _run(["pairing", "list", channel])
    return OcResult(ok=(rc == 0), text=text, rc=rc)


def approve_pairing(channel: str, code: str) -> OcResult:
    text, rc = _run(["pairing", "approve", channel, code])
    return OcResult(ok=(rc == 0), text=text, rc=rc)
