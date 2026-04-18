"""Peer subprocess runners for Claude Code, Codex CLI, and Ollama."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from .ui import DIM, RESET, color, line_prefix


def _which(name: str) -> str:
    resolved = shutil.which(name)
    return resolved or name


EXHAUSTED_RE = re.compile(
    r"rate[- ]?limit|quota|usage limit|out of credits?|"
    r"insufficient (credits?|balance|funds)|credit[- ]?balance|"
    r"\b429\b|payment required|subscription.*(expired|required)",
    re.IGNORECASE,
)


def is_exhausted(text: str) -> bool:
    return bool(EXHAUSTED_RE.search(text or ""))


# A sink receives one line (already newline-terminated) of streamed output.
Sink = Callable[[str, str], None]  # (role, line)


def _default_sink(role: str, line: str) -> None:
    sys.stdout.write(line_prefix(role) + line)
    sys.stdout.flush()


# Current sink — swapped by the TUI when active.
_sink: Sink = _default_sink
_quiet: bool = False


def set_sink(sink: Optional[Sink]) -> None:
    global _sink
    _sink = sink or _default_sink


class quiet_stream:
    """Context manager: swallow streamed output (used for internal supervisor calls)."""
    def __enter__(self):
        global _quiet
        self._prev = _quiet
        _quiet = True
        return self
    def __exit__(self, *exc):
        global _quiet
        _quiet = self._prev


@dataclass
class Peer:
    name: str
    alive: bool = True
    calls: int = 0
    seconds: float = 0.0
    cmd_ok: bool = True          # whether the underlying CLI is installed
    extra: dict = field(default_factory=dict)


class _Heartbeat:
    """Non-TUI heartbeat: prints '⋯ <role> thinking Ns' on a CR line."""
    def __init__(self, role: str, interval: float = 1.0) -> None:
        self.role = role
        self.interval = interval
        self._stop = threading.Event()
        self._active = threading.Event()
        self._t0 = time.time()
        self._thr: Optional[threading.Thread] = None

    def start(self) -> None:
        if _sink is not _default_sink:
            return  # TUI handles status itself
        self._active.set()
        self._thr = threading.Thread(target=self._loop, daemon=True)
        self._thr.start()

    def pause(self) -> None:
        self._active.clear()
        self._clear()

    def resume(self) -> None:
        self._t0 = time.time()
        self._active.set()

    def stop(self) -> None:
        self._stop.set()
        if self._thr:
            self._thr.join(timeout=0.5)
        self._clear()

    def _clear(self) -> None:
        try:
            sys.stdout.write("\r\x1b[2K")
            sys.stdout.flush()
        except Exception:
            pass

    def _loop(self) -> None:
        dots = ["⋯  ", "·⋯ ", " ·⋯", "⋯ ·"]
        i = 0
        while not self._stop.is_set():
            if self._active.is_set():
                elapsed = time.time() - self._t0
                msg = f"\r{color(self.role, dots[i % len(dots)])} {DIM}{self.role} thinking {elapsed:4.0f}s{RESET}"
                try:
                    sys.stdout.write(msg)
                    sys.stdout.flush()
                except Exception:
                    pass
                i += 1
            time.sleep(self.interval)


def _stream(cmd: list[str], role: str, *, stdin_text: Optional[str] = None,
            cwd: Optional[str] = None) -> tuple[str, str, int]:
    try:
        p = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE if stdin_text is not None else None,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace",
            cwd=cwd, bufsize=1,
        )
    except FileNotFoundError as e:
        return ("", f"{e}", 127)

    if stdin_text is not None:
        try:
            p.stdin.write(stdin_text)
            p.stdin.close()
        except Exception:
            pass

    buf: list[str] = []
    assert p.stdout is not None
    hb = _Heartbeat(role)
    hb.start()
    try:
        for line in p.stdout:
            buf.append(line)
            if not _quiet:
                hb.pause()
                _sink(role, line)
                hb.resume()
    finally:
        hb.stop()
    rc = p.wait()
    err = p.stderr.read() if p.stderr else ""
    if err.strip():
        for ln in err.splitlines():
            _sink("err", f"! {ln}\n")
    return ("".join(buf), err, rc)


def run_claude(peer: Peer, prompt: str, cwd: str, *, as_json: bool = False,
               mcp_config: Optional[str] = None) -> tuple[str, bool]:
    # Request JSON always so we can parse usage/tokens; surface text via `.result`.
    cmd = [_which("claude"), "-p", "--dangerously-skip-permissions",
           "--output-format", "json"]
    if mcp_config:
        cmd += ["--mcp-config", mcp_config]
    t0 = time.time()
    peer.calls += 1
    stdout, stderr, rc = _stream(cmd, peer.name, stdin_text=prompt, cwd=cwd)
    peer.seconds += time.time() - t0
    blob = stdout + "\n" + stderr
    if rc != 0 and is_exhausted(blob):
        return (blob, True)
    result_text = stdout.strip()
    try:
        data = json.loads(stdout)
        result_text = data.get("result") or data.get("text") or stdout
        usage = (data.get("usage") or {})
        peer.extra["tokens_in"] = peer.extra.get("tokens_in", 0) + int(
            usage.get("input_tokens", 0) or 0)
        peer.extra["tokens_out"] = peer.extra.get("tokens_out", 0) + int(
            usage.get("output_tokens", 0) or 0)
    except Exception:
        pass
    return (result_text if isinstance(result_text, str) else str(result_text), False)


def run_codex(peer: Peer, prompt: str, cwd: str) -> tuple[str, bool]:
    last_msg = Path(tempfile.gettempdir()) / f"codex-last-{uuid.uuid4().hex}.txt"
    cmd = [_which("codex"), "exec",
           "--dangerously-bypass-approvals-and-sandbox",
           "--skip-git-repo-check",
           "--cd", cwd,
           "--output-last-message", str(last_msg),
           "-"]
    t0 = time.time()
    peer.calls += 1
    stdout, stderr, rc = _stream(cmd, peer.name, stdin_text=prompt)
    peer.seconds += time.time() - t0
    blob = stdout + "\n" + stderr
    if rc != 0 and is_exhausted(blob):
        return (blob, True)
    if last_msg.exists():
        out = last_msg.read_text(encoding="utf-8", errors="replace").strip()
        try: last_msg.unlink()
        except OSError: pass
        if out:
            return (out, False)
    return (stdout.strip(), False)


def run_ollama(peer: Peer, prompt: str, cwd: str) -> tuple[str, bool]:
    model = peer.extra.get("model") or os.environ.get("DUO_OLLAMA_MODEL", "llama3.1")
    cmd = [_which("ollama"), "run", model]
    t0 = time.time()
    peer.calls += 1
    stdout, stderr, rc = _stream(cmd, peer.name, stdin_text=prompt, cwd=cwd)
    peer.seconds += time.time() - t0
    blob = stdout + "\n" + stderr
    if rc != 0 and is_exhausted(blob):
        return (blob, True)
    return (stdout.strip(), False)


def run_openclaw(peer: Peer, prompt: str, cwd: str) -> tuple[str, bool]:
    """Run openclaw's local agent as a peer.

    Requires `openclaw` on PATH. The Gateway daemon should already be running
    (the user runs `openclaw onboard --install-daemon` once).
    """
    thinking = peer.extra.get("thinking", "high")
    extra = peer.extra.get("args") or []
    cmd = [_which("openclaw"), "agent",
           "--message", prompt,
           "--thinking", str(thinking),
           *extra]
    t0 = time.time()
    peer.calls += 1
    # openclaw takes message via flag, not stdin
    stdout, stderr, rc = _stream(cmd, peer.name, stdin_text=None, cwd=cwd)
    peer.seconds += time.time() - t0
    blob = stdout + "\n" + stderr
    if rc != 0 and is_exhausted(blob):
        return (blob, True)
    return (stdout.strip(), False)


# Registry: peer name -> (runner, default-cmd-to-check)
RUNNERS: dict[str, tuple[Callable[..., tuple[str, bool]], str]] = {
    "claude":   (run_claude,   "claude"),
    "codex":    (run_codex,    "codex"),
    "ollama":   (run_ollama,   "ollama"),
    "openclaw": (run_openclaw, "openclaw"),
}


def make_peer(name: str, **extra) -> Peer:
    _, probe = RUNNERS[name]
    installed = shutil.which(probe) is not None
    return Peer(name=name, cmd_ok=installed, extra=extra)
