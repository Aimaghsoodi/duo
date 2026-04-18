"""Inline streaming UI — Claude-Code / Codex-CLI style.

No full-screen layout, no boxes, no flicker. Every streamed line prints
directly into the terminal scrollback with a colored role glyph, exactly
like `claude` and `codex`. A single spinner line shows "thinking" state
and is cleared the moment real output arrives. Works identically for one
peer or many running in parallel — peers just interleave by role.
"""

from __future__ import annotations

import itertools
import sys
import threading
import time

from rich.console import Console
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
    "sup":      "bold cyan",
}

ROLE_GLYPHS = {
    "claude":   "◆",
    "codex":    "◇",
    "ollama":   "○",
    "openclaw": "◈",
    "system":   "·",
    "err":      "✖",
    "user":     "▸",
    "sup":      "▸",
}

SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]


class TUI:
    """Inline stream printer. Same public API as before (sink / enter / exit)."""

    def __init__(self, state) -> None:
        self.state = state
        self.console = Console(soft_wrap=True, highlight=False)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thr: threading.Thread | None = None
        self._prev_sink = None
        self._current_role: str | None = None
        self._at_line_start = True
        self._spinner_on = False
        self._spinner_text = ""
        self._spinner_thread: threading.Thread | None = None

    # --- sink: every streamed chunk flows through here ---
    def sink(self, role: str, line: str) -> None:
        with self._lock:
            self._clear_spinner_locked()
            for part in (line.rstrip("\n").splitlines() or [""]):
                self._print_line_locked(role, part)

    def _print_line_locked(self, role: str, text: str) -> None:
        color = ROLE_COLORS.get(role, "white")
        glyph = ROLE_GLYPHS.get(role, "·")
        if role == self._current_role and not self._at_line_start:
            self.console.print(Text("   " + text))
            return
        t = Text()
        t.append(f" {glyph} ", style=color)
        t.append(f"{role:<7}", style=f"dim {color}")
        t.append("  ")
        t.append(text)
        self.console.print(t)
        self._current_role = role
        self._at_line_start = True

    # --- spinner (single-line, in-place) ---
    def _spinner_loop(self) -> None:
        frames = itertools.cycle(SPINNER_FRAMES)
        while self._spinner_on and not self._stop.is_set():
            with self._lock:
                if not self._spinner_on:
                    return
                frame = next(frames)
                sys.stdout.write(f"\r\033[2K \033[36m{frame}\033[0m  "
                                 f"\033[2m{self._spinner_text}\033[0m")
                sys.stdout.flush()
            time.sleep(0.08)

    def _clear_spinner_locked(self) -> None:
        if self._spinner_on:
            sys.stdout.write("\r\033[2K")
            sys.stdout.flush()
            self._spinner_on = False

    def status(self, text: str) -> None:
        """Show a live spinner line — cleared as soon as output arrives."""
        with self._lock:
            self._clear_spinner_locked()
            self._spinner_text = text
            self._spinner_on = True
        if not self._spinner_thread or not self._spinner_thread.is_alive():
            self._spinner_thread = threading.Thread(
                target=self._spinner_loop, daemon=True)
            self._spinner_thread.start()

    def clear_status(self) -> None:
        with self._lock:
            self._clear_spinner_locked()

    # --- lifecycle ---
    def __enter__(self) -> "TUI":
        self._prev_sink = peers_mod._sink
        peers_mod.set_sink(self.sink)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self._stop.set()
        with self._lock:
            self._clear_spinner_locked()
        peers_mod.set_sink(self._prev_sink)


def live_tui(state) -> TUI:
    return TUI(state)
