"""Live TUI.

Default mode: single scrolling transcript pane + status bar — feels like
the Claude Code / Codex CLI. Per-peer side-by-side panes kick in when
parallel mode is on or 3+ peers are active.
"""

from __future__ import annotations

import threading
import time
from collections import deque

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.text import Text

from . import peers as peers_mod


ROLE_COLORS = {
    "claude":   "magenta",
    "codex":    "green",
    "ollama":   "cyan",
    "openclaw": "bright_red",
    "system":   "white",
    "err":      "red",
    "user":     "yellow",
}

ROLE_GLYPHS = {
    "claude":   "◆",
    "codex":    "◇",
    "ollama":   "○",
    "openclaw": "🦞",
    "system":   "·",
    "err":      "✖",
    "user":     "▸",
}


class _PaneState:
    def __init__(self, name: str, max_lines: int = 400) -> None:
        self.name = name
        self.lines: deque[tuple[str, str]] = deque(maxlen=max_lines)  # (role, text)
        self.last_activity = 0.0

    def add(self, role: str, line: str) -> None:
        for part in line.rstrip("\n").splitlines() or [""]:
            self.lines.append((role, part))
        self.last_activity = time.time()


class TUI:
    def __init__(self, state) -> None:
        self.state = state
        self.console = Console()
        self.chat = _PaneState("chat", max_lines=800)
        self.peer_panes: dict[str, _PaneState] = {
            n: _PaneState(n) for n in state.peers.keys()
        }
        self._lock = threading.Lock()
        self._live: Live | None = None
        self._stop = threading.Event()
        self._thr: threading.Thread | None = None
        self._t0 = time.time()
        self._prev_sink = None

    # --- mode detection ---
    def _split_mode(self) -> bool:
        if getattr(self.state, "parallel", False):
            return True
        return len([p for p in self.state.peers.values() if p.cmd_ok]) >= 3

    # --- sink: every streamed line goes through here ---
    def sink(self, role: str, line: str) -> None:
        with self._lock:
            self.chat.add(role, line)
            if role in self.peer_panes:
                self.peer_panes[role].add(role, line)
            elif role == "err" and self.peer_panes:
                target = max(self.peer_panes.values(),
                             key=lambda p: p.last_activity, default=None)
                if target:
                    target.add(role, line)

    # --- rendering ---
    def _format_line(self, role: str, text: str) -> Text:
        color = ROLE_COLORS.get(role, "white")
        glyph = ROLE_GLYPHS.get(role, "·")
        t = Text()
        t.append(f" {glyph} ", style=f"bold {color}")
        t.append(f"{role:<6} ", style=f"dim {color}")
        t.append("│ ", style="dim")
        t.append(text)
        return t

    def _chat_panel(self) -> Panel:
        if not self.chat.lines:
            body: Text | str = Text("(waiting for peers)", style="dim")
        else:
            # render as a single Text with per-line styling, keeping only what fits
            height = max(8, (self.console.size.height or 24) - 6)
            recent = list(self.chat.lines)[-height:]
            body = Text()
            for i, (role, text) in enumerate(recent):
                if i > 0:
                    body.append("\n")
                body.append_text(self._format_line(role, text))
        title = f"[bold cyan]duo[/] · session transcript"
        return Panel(body, title=title, border_style="cyan", padding=(0, 1))

    def _peer_panel(self, name: str) -> Panel:
        pane = self.peer_panes[name]
        peer = self.state.peers[name]
        color = ROLE_COLORS.get(name, "white")
        idle = time.time() - pane.last_activity if pane.last_activity else None
        bits = [f"calls={peer.calls}", f"time={peer.seconds:.1f}s"]
        if not peer.alive:
            bits.append("[red]EXHAUSTED[/]")
        elif idle is not None and idle < 2.0:
            bits.append(f"[{color}]● streaming[/]")
        elif peer.calls == 0:
            bits.append("[dim]idle[/]")
        else:
            bits.append("[dim]waiting[/]")
        title = f"[bold {color}]{name}[/] · " + " · ".join(bits)
        if not pane.lines:
            body: Text | str = Text("(no output yet)", style="dim")
        else:
            body = Text("\n".join(t for _, t in pane.lines))
        return Panel(body, title=title, border_style=color, padding=(0, 1))

    def _status_line(self) -> Text:
        parts = []
        for n, p in self.state.peers.items():
            if not p.cmd_ok:
                parts.append(f"[dim]{n}:missing[/]")
                continue
            c = ROLE_COLORS.get(n, "white")
            tok = ""
            ti, to = p.extra.get("tokens_in", 0), p.extra.get("tokens_out", 0)
            if ti or to:
                tok = f" {ti}/{to}t"
            parts.append(f"[{c}]{n}[/] {p.calls}c/{p.seconds:.0f}s{tok}")
        flags = []
        if getattr(self.state, "parallel", False):
            flags.append("[cyan]parallel[/]")
        if self.state.skills:
            flags.append(f"skills={len(self.state.skills)}")
        if self.state.mcp_config_path:
            flags.append("mcp")
        flag_s = "  " + "  ".join(flags) if flags else ""
        status = (
            f"[bold cyan]duo[/] step {self.state.step}  "
            f"sup=[{ROLE_COLORS.get(self.state.supervisor,'white')}]"
            f"{self.state.supervisor}[/]  "
            f"elapsed={time.time() - self._t0:.0f}s   "
            + "  ".join(parts) + flag_s
            + "   [dim]/help · /quit[/]"
        )
        return Text.from_markup(status)

    def _render(self) -> Layout:
        layout = Layout()
        if self._split_mode():
            panels = [self._peer_panel(n) for n, p in self.state.peers.items() if p.cmd_ok]
            inner = Layout()
            inner.split_row(*[Layout(p, name=f"p{i}") for i, p in enumerate(panels)])
            main = inner
        else:
            main = Layout(self._chat_panel())

        layout.split_column(
            Layout(main, ratio=1),
            Layout(self._status_line(), size=1, name="status"),
        )
        return layout

    def _run(self) -> None:
        # auto_refresh=False: we drive repaints ourselves to avoid fighting
        # Rich's internal refresh thread (which can cause flicker).
        with Live(self._render(), console=self.console,
                  auto_refresh=False, screen=False, transient=True) as live:
            self._live = live
            while not self._stop.is_set():
                with self._lock:
                    try:
                        live.update(self._render(), refresh=True)
                    except Exception:
                        pass
                time.sleep(0.1)

    def __enter__(self) -> "TUI":
        self._prev_sink = peers_mod._sink
        peers_mod.set_sink(self.sink)
        self._thr = threading.Thread(target=self._run, daemon=True)
        self._thr.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self._stop.set()
        if self._thr:
            self._thr.join(timeout=1.0)
        peers_mod.set_sink(self._prev_sink)


def live_tui(state) -> TUI:
    return TUI(state)
