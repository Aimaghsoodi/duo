"""Line editor: readline history + tab completion for slash commands.

Falls back to plain input() when readline isn't available (e.g. on Windows
without pyreadline3 installed).
"""

from __future__ import annotations

import atexit
import os
from pathlib import Path
from typing import Callable, Optional


_rl = None  # the active readline module

def _try_import_readline():
    global _rl
    if _rl is not None:
        return _rl
    try:
        import readline  # type: ignore
        _rl = readline
        return _rl
    except ImportError:
        pass
    try:
        import pyreadline3  # type: ignore  # noqa: F401
        import readline  # pyreadline3 installs this  # type: ignore
        _rl = readline
        return _rl
    except ImportError:
        return None


class LineEditor:
    def __init__(self, history_path: Path,
                 completer_fn: Optional[Callable[[], list[str]]] = None) -> None:
        self.history_path = history_path
        self.completer_fn = completer_fn or (lambda: [])
        self._ready = False

    def setup(self) -> None:
        rl = _try_import_readline()
        if rl is None:
            self._ready = False
            return

        # history
        try:
            self.history_path.parent.mkdir(parents=True, exist_ok=True)
            if self.history_path.exists():
                rl.read_history_file(str(self.history_path))
            rl.set_history_length(2000)
            atexit.register(self._save_history, rl)
        except Exception:
            pass

        # completer
        try:
            rl.set_completer(self._completer)
            # Handle GNU readline ("tab: complete") vs libedit macOS default
            doc = getattr(rl, "__doc__", "") or ""
            if "libedit" in doc:
                rl.parse_and_bind("bind ^I rl_complete")
            else:
                rl.parse_and_bind("tab: complete")
            # Don't split on /, so "/pee<TAB>" completes to "/peers"
            rl.set_completer_delims(" \t\n")
        except Exception:
            pass

        self._ready = True

    def _save_history(self, rl) -> None:
        try:
            rl.write_history_file(str(self.history_path))
        except Exception:
            pass

    def _completer(self, text: str, state: int):
        options = [c for c in self.completer_fn() if c.startswith(text)]
        options.sort()
        try:
            return options[state]
        except IndexError:
            return None

    def prompt(self, s: str) -> str:
        # readline is picked up automatically by input() once set_completer is called
        return input(s)


def slash_completions(state, commands: list[str]) -> list[str]:
    """Build the current set of tab-completable tokens."""
    out = ["/" + c for c in commands]
    for n in getattr(state, "peers", {}):
        out.append(n)
    return out
