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
_tui = None  # live TUI instance, if any — orchestrator uses its spinner


def set_sink(sink: Optional[Sink]) -> None:
    global _sink
    _sink = sink or _default_sink


def set_tui(tui) -> None:
    global _tui
    _tui = tui


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
            cwd: Optional[str] = None,
            line_emit: Optional[Callable[[str], Optional[str]]] = None
            ) -> tuple[str, str, int]:
    """Run `cmd`, forwarding stdout lines to the sink live.

    `line_emit`, if given, receives each raw stdout line and returns the text
    to show to the user (or None to suppress). Use this to convert JSONL
    stream events into human-readable chunks while still capturing raw output.
    """
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
    # If a TUI is attached, show a spinner so the user knows this peer is
    # running (codex exec can be silent for a while before emitting output).
    if not _quiet and _tui is not None and hasattr(_tui, "status"):
        try: _tui.status(f"{role} running…")
        except Exception: pass
    try:
        for line in p.stdout:
            buf.append(line)
            shown = line_emit(line) if line_emit else line
            if _quiet or not shown:
                continue
            hb.pause()
            _sink(role, shown if shown.endswith("\n") else shown + "\n")
            hb.resume()
    finally:
        hb.stop()
        if not _quiet and _tui is not None and hasattr(_tui, "clear_status"):
            try: _tui.clear_status()
            except Exception: pass
    rc = p.wait()
    err = p.stderr.read() if p.stderr else ""
    if err.strip():
        for ln in err.splitlines():
            _sink("err", f"! {ln}\n")
    return ("".join(buf), err, rc)


def run_claude(peer: Peer, prompt: str, cwd: str, *, as_json: bool = False,
               mcp_config: Optional[str] = None) -> tuple[str, bool]:
    # stream-json: Claude emits one JSON event per line — we parse deltas live
    # so the user sees tokens as they're generated instead of waiting for the
    # full result blob.
    cmd = [_which("claude"), "-p", "--dangerously-skip-permissions",
           "--verbose", "--output-format", "stream-json"]
    if mcp_config:
        cmd += ["--mcp-config", mcp_config]

    state = {"result": "", "in_tok": 0, "out_tok": 0, "tool_ids": {}}

    def _tool_arg(name: str, inp: dict) -> str:
        """Extract the most informative argument for a tool call (Claude-Code style)."""
        if not isinstance(inp, dict):
            return ""
        for key in ("file_path", "path", "notebook_path", "pattern",
                    "command", "url", "query", "prompt"):
            v = inp.get(key)
            if v:
                s = str(v)
                return s if len(s) < 80 else s[:77] + "…"
        return ""

    def emit(raw: str) -> Optional[str]:
        s = raw.strip()
        if not s:
            return None
        try:
            ev = json.loads(s)
        except Exception:
            return None
        et = ev.get("type")
        if et == "assistant":
            msg = ev.get("message") or {}
            lines: list[str] = []
            for block in (msg.get("content") or []):
                btype = block.get("type")
                if btype == "text":
                    txt = (block.get("text") or "").rstrip()
                    if txt:
                        lines.append(txt)
                elif btype == "tool_use":
                    tname = block.get("name", "tool")
                    arg = _tool_arg(tname, block.get("input") or {})
                    state["tool_ids"][block.get("id", "")] = tname
                    lines.append(f"● {tname}({arg})" if arg else f"● {tname}")
            return "\n".join(lines) or None
        if et == "user":
            # tool_result events come back as user role with content
            msg = ev.get("message") or {}
            lines: list[str] = []
            for block in (msg.get("content") or []):
                if block.get("type") == "tool_result":
                    tname = state["tool_ids"].get(block.get("tool_use_id", ""), "")
                    content = block.get("content")
                    if isinstance(content, list):
                        content = "".join(c.get("text", "") for c in content
                                          if isinstance(c, dict))
                    summary = (content or "").strip().splitlines()
                    first = summary[0][:80] if summary else ""
                    more = f" (+{len(summary)-1} lines)" if len(summary) > 1 else ""
                    if first:
                        lines.append(f"  ⎿  {first}{more}")
            return "\n".join(lines) or None
        if et == "result":
            state["result"] = (ev.get("result") or "").strip()
            usage = ev.get("usage") or {}
            state["in_tok"] = int(usage.get("input_tokens", 0) or 0)
            state["out_tok"] = int(usage.get("output_tokens", 0) or 0)
            return None
        return None

    t0 = time.time()
    peer.calls += 1
    stdout, stderr, rc = _stream(cmd, peer.name, stdin_text=prompt, cwd=cwd,
                                 line_emit=emit)
    peer.seconds += time.time() - t0
    blob = stdout + "\n" + stderr
    if rc != 0 and is_exhausted(blob):
        return (blob, True)
    peer.extra["tokens_in"] = peer.extra.get("tokens_in", 0) + state["in_tok"]
    peer.extra["tokens_out"] = peer.extra.get("tokens_out", 0) + state["out_tok"]
    return (state["result"] or stdout.strip(), False)


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
