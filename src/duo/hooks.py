"""Pre/post-step shell hooks."""

from __future__ import annotations

import shlex
import subprocess
import time
from dataclasses import dataclass


@dataclass
class HookResult:
    cmd: str
    rc: int
    duration: float
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.rc == 0


def run_hook(cmd: str, cwd: str, *, timeout: float = 120.0) -> HookResult:
    t0 = time.time()
    try:
        # Use shell=True on Windows for compatibility with user-supplied strings
        # that may rely on shell syntax (pipes, etc.). Trust user's own config.
        p = subprocess.run(
            cmd, shell=True, cwd=cwd, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout,
        )
        return HookResult(cmd=cmd, rc=p.returncode,
                          duration=time.time() - t0,
                          stdout=p.stdout or "", stderr=p.stderr or "")
    except subprocess.TimeoutExpired as e:
        return HookResult(cmd=cmd, rc=124, duration=time.time() - t0,
                          stdout=e.stdout or "", stderr=f"timeout after {timeout}s")
    except Exception as e:
        return HookResult(cmd=cmd, rc=1, duration=time.time() - t0,
                          stdout="", stderr=str(e))


def run_hooks(cmds: list[str], cwd: str) -> list[HookResult]:
    return [run_hook(c, cwd) for c in (cmds or [])]
