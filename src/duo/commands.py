"""Slash-command dispatcher for duo's interactive loop.

Commands start with `/`. Anything else is treated as a goal and passed to the
supervisor loop unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from .peers import RUNNERS


@dataclass
class CommandResult:
    # One of: "goal" (run as supervisor goal), "handled" (printed output),
    # "quit" (exit session), "reset" (clear transcript).
    kind: str
    text: str = ""


# Handlers take (ctx, args:str) -> CommandResult
Handler = Callable[["CmdCtx", str], CommandResult]


@dataclass
class CmdCtx:
    state: object                 # orchestrator.State
    session: Optional[object]     # session.Session | None
    cfg: object                   # DuoConfig
    emit: Callable[[str, str], None]   # role, text


def _h_tips(ctx: CmdCtx, args: str) -> CommandResult:
    from .ui import TIPS
    lines = ["DuoX tips:"]
    for title, ex in TIPS:
        lines.append(f"  › {title}")
        lines.append(f"      {ex}")
    ctx.emit("system", "\n".join(lines))
    return CommandResult("handled")


def _h_examples(ctx: CmdCtx, args: str) -> CommandResult:
    examples = [
        "DuoX examples — paste or adapt:",
        "",
        "  build a todo cli in ./scratch with tests",
        "  read src/ and summarise the module graph in under 200 words",
        "  find every TODO/FIXME in this repo and group by file",
        "  refactor duo/cli.py to extract the interactive loop",
        "  /plan wire ollama as a fallback when claude is rate-limited",
        "  /parallel on   then:   write a pytest for duo/hooks.py",
        "  /codex open pyproject.toml and bump version to 0.2.0",
        "  /oc-send +15551234 \"ship status: green\"",
    ]
    ctx.emit("system", "\n".join(examples))
    return CommandResult("handled")


def _h_help(ctx: CmdCtx, args: str) -> CommandResult:
    rows = [
        ("/help",               "show this help"),
        ("/tips",               "show usage tips"),
        ("/examples",           "show example prompts you can paste"),
        ("/quit, /exit",        "leave the session"),
        ("/clear, /reset",      "clear transcript (keeps session + peers)"),
        ("/peers [a,b,c]",      "list or set active peers"),
        ("/model <peer> <m>",   "set model (ollama only today)"),
        ("/supervisor <peer>",  "change supervisor"),
        ("/skills",             "list loaded skills"),
        ("/history [n]",        "show last n transcript turns"),
        ("/save",               "write transcript to session folder"),
        ("/cost",               "show per-peer call/time stats"),
        ("/hooks",              "list configured hooks"),
        ("/mcp",                "list configured MCP servers"),
        ("/parallel on|off",    "toggle parallel delegation"),
        ("/plan <task>",        "ask supervisor for a plan only"),
        ("/review <task>",      "ask supervisor for a review only"),
        ("/test",               "run configured test hook"),
        ("/swarm <task>",       "explicit parallel sub-agents prompt"),
        ("/claude <msg>",       "send raw message to claude peer (no supervisor)"),
        ("/codex <msg>",        "send raw message to codex peer"),
        ("/ollama <msg>",       "send raw message to ollama peer"),
        ("/openclaw <msg>, /oc","send raw message to openclaw agent"),
        ("/oc-health",          "run `openclaw doctor`"),
        ("/oc-send <to> <msg>", "send via any paired openclaw channel"),
        ("/oc-pair <chan> [approve <code>]", "list or approve openclaw pairings"),
        ("/compact",            "summarise transcript into one turn"),
        ("/remember <note>",    "append note to ~/.duo/notes.md (auto-loaded)"),
        ("/cd <dir>",           "change working dir (reloads context files)"),
        ("/doctor",             "verify peers, MCP, readline, openclaw"),
        ("@file[:a-b]",         "inline file/dir excerpt (no slash; use in any prompt)"),
    ]
    width = max(len(r[0]) for r in rows)
    lines = ["DuoX commands:"]
    for cmd, desc in rows:
        lines.append(f"  {cmd.ljust(width)}  {desc}")
    ctx.emit("system", "\n".join(lines))
    return CommandResult("handled")


def _h_quit(ctx: CmdCtx, args: str) -> CommandResult:
    return CommandResult("quit")


def _h_clear(ctx: CmdCtx, args: str) -> CommandResult:
    ctx.state.transcript.clear()
    ctx.emit("system", "transcript cleared.")
    return CommandResult("handled")


def _h_peers(ctx: CmdCtx, args: str) -> CommandResult:
    from .peers import make_peer
    if not args.strip():
        rows = []
        for p in ctx.state.peers.values():
            flag = "alive" if (p.alive and p.cmd_ok) else ("missing" if not p.cmd_ok else "exhausted")
            rows.append(f"  {p.name:<10} {flag}")
        ctx.emit("system", "peers:\n" + "\n".join(rows))
        return CommandResult("handled")
    names = [x.strip() for x in args.replace(" ", ",").split(",") if x.strip()]
    for n in names:
        if n not in RUNNERS:
            ctx.emit("err", f"unknown peer: {n}")
            return CommandResult("handled")
    new_peers = {}
    for n in names:
        if n in ctx.state.peers:
            new_peers[n] = ctx.state.peers[n]
        else:
            extra = {}
            if n == "ollama":
                extra["model"] = getattr(ctx.cfg, "ollama_model", "llama3.1")
            elif n == "openclaw":
                extra.update(getattr(ctx.cfg, "openclaw", {}) or {})
            new_peers[n] = make_peer(n, **extra)
    ctx.state.peers = new_peers
    if ctx.state.supervisor not in new_peers:
        ctx.state.supervisor = next(iter(new_peers))
    ctx.emit("system", f"active peers: {', '.join(new_peers)} · supervisor: {ctx.state.supervisor}")
    return CommandResult("handled")


def _h_supervisor(ctx: CmdCtx, args: str) -> CommandResult:
    name = args.strip()
    if name not in ctx.state.peers:
        ctx.emit("err", f"{name!r} not in active peers: {list(ctx.state.peers)}")
        return CommandResult("handled")
    ctx.state.supervisor = name
    ctx.emit("system", f"supervisor → {name}")
    return CommandResult("handled")


def _h_model(ctx: CmdCtx, args: str) -> CommandResult:
    parts = args.split(None, 1)
    if len(parts) != 2:
        ctx.emit("err", "usage: /model <peer> <model-id>")
        return CommandResult("handled")
    peer, model = parts
    if peer not in ctx.state.peers:
        ctx.emit("err", f"peer {peer!r} not active")
        return CommandResult("handled")
    if peer != "ollama":
        ctx.emit("system", f"(note: only ollama model is configurable today; ignored for {peer})")
        return CommandResult("handled")
    ctx.state.peers[peer].extra["model"] = model
    ctx.emit("system", f"{peer} model → {model}")
    return CommandResult("handled")


def _h_skills(ctx: CmdCtx, args: str) -> CommandResult:
    skills = getattr(ctx, "_skills", None)
    if not skills:
        ctx.emit("system", "no skills loaded.")
        return CommandResult("handled")
    rows = [f"  {s.name:<20} always={s.always} match={s.match}" for s in skills]
    ctx.emit("system", "skills:\n" + "\n".join(rows))
    return CommandResult("handled")


def _h_history(ctx: CmdCtx, args: str) -> CommandResult:
    try:
        n = int(args.strip()) if args.strip() else 10
    except ValueError:
        n = 10
    turns = ctx.state.transcript[-n:]
    if not turns:
        ctx.emit("system", "(empty transcript)")
        return CommandResult("handled")
    out = []
    for t in turns:
        head = t.text.splitlines()[0][:160] if t.text else ""
        out.append(f"  [{t.role}] {head}")
    ctx.emit("system", "\n".join(out))
    return CommandResult("handled")


def _h_save(ctx: CmdCtx, args: str) -> CommandResult:
    if not ctx.session:
        ctx.emit("err", "no active session")
        return CommandResult("handled")
    ctx.session.save_transcript(
        [{"role": t.role, "text": t.text} for t in ctx.state.transcript]
    )
    ctx.emit("system", f"transcript saved → {ctx.session.transcript_path}")
    return CommandResult("handled")


def _h_cost(ctx: CmdCtx, args: str) -> CommandResult:
    rows = []
    for p in ctx.state.peers.values():
        rows.append(f"  {p.name:<10} calls={p.calls:<3} "
                    f"time={p.seconds:6.1f}s  "
                    f"tok_in={p.extra.get('tokens_in', 0)} "
                    f"tok_out={p.extra.get('tokens_out', 0)}")
    ctx.emit("system", "cost/usage:\n" + "\n".join(rows))
    return CommandResult("handled")


def _h_hooks(ctx: CmdCtx, args: str) -> CommandResult:
    h = getattr(ctx.cfg, "hooks", {}) or {}
    if not h:
        ctx.emit("system", "no hooks configured.")
        return CommandResult("handled")
    out = []
    for k, v in h.items():
        out.append(f"  {k}:")
        for c in v or []:
            out.append(f"    - {c}")
    ctx.emit("system", "hooks:\n" + "\n".join(out))
    return CommandResult("handled")


def _h_mcp(ctx: CmdCtx, args: str) -> CommandResult:
    mcp = getattr(ctx.cfg, "mcp", {}) or {}
    servers = (mcp.get("servers") or {})
    if not servers:
        ctx.emit("system", "no MCP servers configured.")
        return CommandResult("handled")
    out = [f"  {n}: {v.get('command')} {' '.join(v.get('args') or [])}"
           for n, v in servers.items()]
    ctx.emit("system", "mcp servers:\n" + "\n".join(out))
    return CommandResult("handled")


def _h_parallel(ctx: CmdCtx, args: str) -> CommandResult:
    a = args.strip().lower()
    if a not in ("on", "off"):
        ctx.emit("err", "usage: /parallel on|off")
        return CommandResult("handled")
    ctx.state.parallel = (a == "on")  # type: ignore[attr-defined]
    ctx.emit("system", f"parallel mode: {a}")
    return CommandResult("handled")


def _h_plan(ctx: CmdCtx, args: str) -> CommandResult:
    if not args.strip():
        ctx.emit("err", "usage: /plan <task>")
        return CommandResult("handled")
    return CommandResult("goal", f"PLAN ONLY (no execution): {args.strip()}")


def _h_review(ctx: CmdCtx, args: str) -> CommandResult:
    if not args.strip():
        ctx.emit("err", "usage: /review <task>")
        return CommandResult("handled")
    return CommandResult("goal", f"REVIEW ONLY (no edits): {args.strip()}")


def _h_test(ctx: CmdCtx, args: str) -> CommandResult:
    from .hooks import run_hooks
    cmds = (getattr(ctx.cfg, "hooks", {}) or {}).get("test") or []
    if not cmds:
        ctx.emit("system", "no [hooks].test configured; defaulting to: pytest -q")
        cmds = ["pytest -q"]
    results = run_hooks(cmds, str(ctx.state.cwd))
    for r in results:
        tag = "ok" if r.ok else f"FAIL rc={r.rc}"
        ctx.emit("system" if r.ok else "err",
                 f"$ {r.cmd}  [{tag}, {r.duration:.1f}s]\n{r.stdout}{r.stderr}")
    return CommandResult("handled")


def _h_swarm(ctx: CmdCtx, args: str) -> CommandResult:
    if not args.strip():
        ctx.emit("err", "usage: /swarm <task>")
        return CommandResult("handled")
    return CommandResult("goal",
        "SWARM MODE: decompose into independent sub-tasks and fan out across "
        "parallel sub-agents. Join results at the end.\n\nTask: " + args.strip())


def _raw_peer(ctx: CmdCtx, peer: str, msg: str) -> CommandResult:
    if not msg.strip():
        ctx.emit("err", f"usage: /{peer} <message>")
        return CommandResult("handled")
    if peer not in ctx.state.peers or not ctx.state.peers[peer].cmd_ok:
        ctx.emit("err", f"peer {peer!r} not active/installed")
        return CommandResult("handled")
    from .orchestrator import _call
    out = _call(ctx.state, peer, msg)
    ctx.state.log(peer, out)
    return CommandResult("handled")


def _h_claude(ctx: CmdCtx, args: str) -> CommandResult:
    return _raw_peer(ctx, "claude", args)


def _h_codex(ctx: CmdCtx, args: str) -> CommandResult:
    return _raw_peer(ctx, "codex", args)


def _h_ollama(ctx: CmdCtx, args: str) -> CommandResult:
    return _raw_peer(ctx, "ollama", args)


def _h_openclaw(ctx: CmdCtx, args: str) -> CommandResult:
    return _raw_peer(ctx, "openclaw", args)


def _h_oc_health(ctx: CmdCtx, args: str) -> CommandResult:
    from .openclaw import doctor, openclaw_available
    if not openclaw_available():
        ctx.emit("err", "openclaw not installed (npm i -g openclaw@latest)")
        return CommandResult("handled")
    r = doctor()
    ctx.emit("system" if r.ok else "err", r.text or f"doctor rc={r.rc}")
    return CommandResult("handled")


def _h_oc_send(ctx: CmdCtx, args: str) -> CommandResult:
    from .openclaw import send_message, openclaw_available
    if not openclaw_available():
        ctx.emit("err", "openclaw not installed")
        return CommandResult("handled")
    parts = args.split(None, 1)
    if len(parts) != 2:
        ctx.emit("err", 'usage: /oc-send "<target>" <message>')
        return CommandResult("handled")
    to, msg = parts[0].strip('"').strip("'"), parts[1]
    r = send_message(to, msg)
    ctx.emit("system" if r.ok else "err",
             r.text or f"send rc={r.rc}")
    return CommandResult("handled")


def _h_oc_pair(ctx: CmdCtx, args: str) -> CommandResult:
    from .openclaw import list_pairings, approve_pairing, openclaw_available
    if not openclaw_available():
        ctx.emit("err", "openclaw not installed")
        return CommandResult("handled")
    parts = args.split()
    if not parts:
        ctx.emit("err", "usage: /oc-pair <channel> [approve <code>]")
        return CommandResult("handled")
    channel = parts[0]
    if len(parts) >= 3 and parts[1] == "approve":
        r = approve_pairing(channel, parts[2])
    else:
        r = list_pairings(channel)
    ctx.emit("system" if r.ok else "err", r.text or f"rc={r.rc}")
    return CommandResult("handled")


def _h_version(ctx: CmdCtx, args: str) -> CommandResult:
    from . import __version__
    ctx.emit("system", f"DuoX {__version__}")
    return CommandResult("handled")


def _h_config(ctx: CmdCtx, args: str) -> CommandResult:
    cfg = ctx.cfg
    lines = [
        f"  peers           = {getattr(cfg, 'peers', [])}",
        f"  supervisor      = {getattr(cfg, 'supervisor', '')}",
        f"  ollama_model    = {getattr(cfg, 'ollama_model', '')}",
        f"  tui             = {getattr(cfg, 'tui', 'auto')}",
        f"  max_steps       = {getattr(cfg, 'max_steps', 30)}",
        f"  parallel_default= {getattr(cfg, 'parallel_default', False)}",
        f"  skills_dir      = {getattr(cfg, 'skills_dir', '')}",
        f"  sessions_dir    = {getattr(cfg, 'sessions_dir', '')}",
        f"  api_port        = {getattr(cfg, 'api_port', 8787)}",
    ]
    ctx.emit("system", "config:\n" + "\n".join(lines))
    return CommandResult("handled")


def _h_session(ctx: CmdCtx, args: str) -> CommandResult:
    s = ctx.session
    if not s:
        ctx.emit("system", "no active session")
        return CommandResult("handled")
    ctx.emit("system",
             f"session {s.id}\n  created={s.created_at}\n"
             f"  events={s.events_path}\n  transcript={s.transcript_path}")
    return CommandResult("handled")


def _h_doctor(ctx: CmdCtx, args: str) -> CommandResult:
    from .doctor import run_checks, format_checks
    checks = run_checks(ctx.cfg, ctx.state.cwd)
    ctx.emit("system", "DuoX doctor:\n" + format_checks(checks))
    return CommandResult("handled")


def _h_cd(ctx: CmdCtx, args: str) -> CommandResult:
    from pathlib import Path
    target = args.strip().strip('"').strip("'")
    if not target:
        ctx.emit("system", f"cwd: {ctx.state.cwd}")
        return CommandResult("handled")
    new = (ctx.state.cwd / target).resolve() if not Path(target).is_absolute() else Path(target).resolve()
    if not new.exists() or not new.is_dir():
        ctx.emit("err", f"not a directory: {new}")
        return CommandResult("handled")
    ctx.state.cwd = new
    from .context import discover as _discover
    from .config import duo_home
    ctx.state.context_files = _discover(new, duo_home())
    ctx.emit("system", f"cwd → {new}  ({len(ctx.state.context_files)} context file(s))")
    return CommandResult("handled")


def _h_compact(ctx: CmdCtx, args: str) -> CommandResult:
    """Summarise transcript into one turn to free context."""
    from .orchestrator import _call, Turn
    from . import peers as _peers_mod
    if not ctx.state.transcript:
        ctx.emit("system", "(empty transcript — nothing to compact)")
        return CommandResult("handled")
    n_before = len(ctx.state.transcript)
    task = ("Summarise the shared transcript into a concise briefing (<= 400 words). "
            "Preserve: user goals, decisions, file paths touched, unresolved "
            "questions, and any state the next turn needs. Plain text, no JSON.")
    ctx.emit("system", f"· compacting {n_before} turns via {ctx.state.supervisor}…")
    with _peers_mod.quiet_stream():
        summary = _call(ctx.state, ctx.state.supervisor, task)
    ctx.state.transcript = [Turn("system", "[compacted]\n" + summary.strip())]
    if ctx.session:
        ctx.session.append_event("compact", turns_before=n_before)
    ctx.emit("system", f"transcript compacted ({n_before} → 1 turn)")
    return CommandResult("handled")


def _h_remember(ctx: CmdCtx, args: str) -> CommandResult:
    """Append a note to ~/.duo/notes.md (auto-loaded as context next time)."""
    note = args.strip()
    if not note:
        ctx.emit("err", "usage: /remember <note>")
        return CommandResult("handled")
    from .config import duo_home
    import datetime as _dt
    path = duo_home() / "notes.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    stamp = _dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    header = "" if path.exists() else "# DuoX notes\n\nAuto-loaded as context on every run.\n"
    with path.open("a", encoding="utf-8") as f:
        if header:
            f.write(header)
        f.write(f"\n- ({stamp}) {note}\n")
    ctx.emit("system", f"remembered → {path}")
    return CommandResult("handled")


def _h_resume(ctx: CmdCtx, args: str) -> CommandResult:
    ctx.emit("err", "use `duox --resume <id>` at launch (cannot hot-swap sessions)")
    return CommandResult("handled")


HANDLERS: dict[str, Handler] = {
    "help":       _h_help,
    "?":          _h_help,
    "tips":       _h_tips,
    "examples":   _h_examples,
    "quit":       _h_quit,
    "exit":       _h_quit,
    "clear":      _h_clear,
    "reset":      _h_clear,
    "peers":      _h_peers,
    "supervisor": _h_supervisor,
    "model":      _h_model,
    "skills":     _h_skills,
    "history":    _h_history,
    "save":       _h_save,
    "cost":       _h_cost,
    "hooks":      _h_hooks,
    "mcp":        _h_mcp,
    "parallel":   _h_parallel,
    "plan":       _h_plan,
    "review":     _h_review,
    "test":       _h_test,
    "swarm":      _h_swarm,
    "claude":     _h_claude,
    "codex":      _h_codex,
    "ollama":     _h_ollama,
    "openclaw":   _h_openclaw,
    "oc":         _h_openclaw,
    "oc-health":  _h_oc_health,
    "oc-send":    _h_oc_send,
    "oc-pair":    _h_oc_pair,
    "version":    _h_version,
    "config":     _h_config,
    "session":    _h_session,
    "resume":     _h_resume,
    "compact":    _h_compact,
    "remember":   _h_remember,
    "cd":         _h_cd,
    "doctor":     _h_doctor,
}


def dispatch(line: str, ctx: CmdCtx) -> CommandResult:
    """Parse a single user input line. Non-slash → goal. `/x y z` → handler."""
    s = line.strip()
    if not s:
        return CommandResult("handled")
    if not s.startswith("/"):
        from .mentions import expand as _expand_mentions
        expanded, used = _expand_mentions(s, ctx.state.cwd)
        if used:
            names = ", ".join(f"@{m.path.name}" for m in used)
            ctx.emit("system", f"· expanded {len(used)} mention(s): {names}")
        return CommandResult("goal", expanded)
    cmd, _, rest = s[1:].partition(" ")
    cmd = cmd.lower()
    h = HANDLERS.get(cmd)
    if not h:
        ctx.emit("err", f"unknown command: /{cmd}  (try /help)")
        return CommandResult("handled")
    return h(ctx, rest)
