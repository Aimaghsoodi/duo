"""Terminal UI primitives: colors, headers, live prefixing."""

from __future__ import annotations

import os
import sys
import time

if os.name == "nt":
    try:
        import ctypes
        _k = ctypes.windll.kernel32
        _k.SetConsoleMode(_k.GetStdHandle(-11), 7)          # enable VT / ANSI
        _k.SetConsoleOutputCP(65001)                        # set console to UTF-8
    except Exception:
        pass

# Force UTF-8 on stdout/stderr so box chars + emoji render on Windows.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

RESET = "\x1b[0m"
BOLD = "\x1b[1m"
DIM = "\x1b[2m"

C = {
    "claude":   "\x1b[38;5;213m",
    "codex":    "\x1b[38;5;118m",
    "ollama":   "\x1b[38;5;51m",
    "openclaw": "\x1b[38;5;203m",
    "user":     "\x1b[38;5;221m",
    "system":   "\x1b[38;5;244m",
    "hdr":      "\x1b[38;5;81m",
    "err":      "\x1b[38;5;203m",
}

def color(role: str, text: str) -> str:
    return f"{C.get(role, '')}{text}{RESET}"

def banner(cwd: str) -> None:
    print(color("hdr", "━" * 72))
    print(color("hdr", BOLD + "  DuoX  ")
          + DIM + "claude × codex × ollama × openclaw orchestrator  "
          + RESET + color("claude", "·")
          + DIM + " AbteeX AI Labs" + RESET)
    print(color("hdr", "━" * 72))
    print(f"{DIM}cwd: {cwd}{RESET}")


TIPS = [
    ("type a goal in plain English",     "e.g.  build a todo cli in ./scratch with tests"),
    ("slash commands start with /",      "/help  /peers  /supervisor  /parallel on  /quit"),
    ("switch peers mid-chat",            "/peers claude,codex,openclaw"),
    ("talk to one peer directly",        "/codex open main.py and add logging"),
    ("parallel race the same task",      "/parallel on   (then next goal fans out to all executors)"),
    ("plan-only / review-only modes",    "/plan add retries    /review last diff"),
    ("resume a prior session",           "duox --resume <id>    (list with: duox sessions)"),
    ("run as HTTP API",                  "duox serve --port 8787"),
    ("headless one-shot",                "duox -p \"your prompt\"   [--output-format json]"),
    ("health check",                     "duox doctor   (or /doctor inside the chat)"),
    ("inline file excerpts",             "type @file.py or @src/main.py:12-40 in any prompt"),
    ("compact & remember",               "/compact  (shrink context)   /remember <note>  (persist)"),
    ("skills auto-load from",            "~/.duo/skills/*.md   (frontmatter: name/match/always)"),
    ("hooks run pre/post each step",     "configure in ~/.duo/config.toml   [hooks]"),
    ("MCP servers work inside DuoX",     "configure in ~/.duo/config.toml   [mcp.servers.<name>]"),
    ("openclaw channels",                "/oc-health   /oc-send <to> <msg>   /oc-pair <channel>"),
    ("interrupt a running step",         "Ctrl-C returns to the prompt (doesn't quit)"),
    ("exit",                             "/quit   or  Ctrl-D"),
]


def welcome(active_peers: list[str], supervisor: str, session_id: str,
            skills: int = 0, mcp: bool = False, tui: bool = False) -> None:
    """Claude-Code-style welcome banner with tips."""
    from . import __version__
    hdr = color("hdr", "╭" + "─" * 70 + "╮")
    ftr = color("hdr", "╰" + "─" * 70 + "╯")
    bar = color("hdr", "│")

    def row(text: str) -> str:
        import re as _re
        raw = _re.sub(r"\x1b\[[0-9;]*m", "", text)
        pad = max(0, 68 - len(raw))
        return f"{bar} {text}{' ' * pad} {bar}"

    print(hdr)
    print(row(f"{BOLD}DuoX{RESET} {DIM}v{__version__}{RESET}  "
              f"{DIM}— claude × codex peers in one terminal{RESET}"))
    print(row(""))
    peers_s = "  ".join(color(p, p) for p in active_peers) or color("err", "(none)")
    print(row(f"peers:       {peers_s}"))
    print(row(f"supervisor:  {color(supervisor, supervisor)}"))
    print(row(f"session:     {DIM}{session_id}{RESET}"))
    flags = []
    if skills: flags.append(f"skills={skills}")
    if mcp:    flags.append("mcp")
    if tui:    flags.append("tui")
    if flags:
        print(row(f"extras:      {DIM}{'  '.join(flags)}{RESET}"))
    print(row(""))
    print(row(f"{BOLD}getting started{RESET}"))
    print(row(f"  {color('hdr', '1.')} type any goal and press enter"))
    print(row(f"     {DIM}e.g. 'add a /health endpoint to server.py'{RESET}"))
    print(row(f"  {color('hdr', '2.')} claude plans, codex executes — both stream live"))
    print(row(f"     {DIM}tool calls show as ● Read(file) / ● Write(path){RESET}"))
    print(row(f"  {color('hdr', '3.')} slash-commands for power moves"))
    print(row(f"     {DIM}/help  /tips  /doctor  /parallel on  /model  /quit{RESET}"))
    print(row(""))
    print(row(f"{DIM}type {RESET}/help{DIM} for the full command list, "
              f"{RESET}/quit{DIM} to exit{RESET}"))
    print(ftr)


def tips_panel() -> None:
    """Print the full tip list (for the /tips slash command)."""
    print(color("hdr", "DuoX tips:"))
    for title, ex in TIPS:
        print(f"  {color('hdr', '›')} {BOLD}{title}{RESET}")
        print(f"      {DIM}{ex}{RESET}")

def header(step: int, who: str, kind: str) -> None:
    stamp = time.strftime("%H:%M:%S")
    print()
    print(color(who, f"┌─ step {step:>2} · {who.upper()} · {kind} ")
          + color("hdr", "·") + f" {DIM}{stamp}{RESET}")

def footer(note: str = "") -> None:
    tail = f"{DIM}└─{RESET}"
    if note:
        tail += f" {DIM}{note}{RESET}"
    print(tail)

def line_prefix(role: str) -> str:
    return color(role, "│ ")
