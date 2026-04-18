"""Command-line entry point for the `duox` tool."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from . import __version__
from .commands import CmdCtx, HANDLERS as SLASH_HANDLERS, dispatch
from .config import DuoConfig, EXAMPLE_CONFIG, duo_home
from .lineedit import LineEditor, slash_completions
from .mcp import write_mcp_config
from .orchestrator import State, run_goal, summary
from .peers import RUNNERS
from .session import SessionManager
from .skills import load_skills
from .ui import banner, color, welcome


def _parse_peers(raw: str) -> list[str]:
    out = [x.strip() for x in raw.split(",") if x.strip()]
    for n in out:
        if n not in RUNNERS:
            raise argparse.ArgumentTypeError(
                f"unknown peer {n!r}; choose from {list(RUNNERS)}")
    if not out:
        raise argparse.ArgumentTypeError("--peers cannot be empty")
    return out


def _build_argparser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="duox",
        description="DuoX — Claude + Codex + Ollama + OpenClaw peers in one terminal.",
    )
    ap.add_argument("--version", action="version", version=f"DuoX {__version__}")
    ap.add_argument("--cwd", default=os.getcwd(),
                    help="working directory for peers (default: cwd)")
    ap.add_argument("--max-steps", type=int, default=None,
                    help="hard cap on supervisor turns (default: from config)")
    ap.add_argument("--peers", type=_parse_peers, default=None,
                    metavar="A,B,C",
                    help="comma-separated peers: claude,codex,ollama,openclaw")
    ap.add_argument("--supervisor", default=None,
                    help="which peer supervises (must be in --peers)")
    ap.add_argument("--ollama-model", default=None, metavar="MODEL",
                    help="ollama model tag (default: llama3.1)")
    ap.add_argument("--tui", dest="tui", action="store_true", default=None,
                    help="force multi-pane live TUI on")
    ap.add_argument("--no-tui", dest="tui", action="store_false",
                    help="force TUI off (plain scrolling output)")
    ap.add_argument("--once", action="store_true",
                    help="run one goal then exit (no chat loop)")
    ap.add_argument("--parallel", action="store_true",
                    help="delegate same task to all executors in parallel")
    ap.add_argument("--resume", metavar="SESSION_ID",
                    help="resume an existing session by id (prefix ok)")

    ap.add_argument("-p", "--print", dest="print_prompt", metavar="PROMPT",
                    nargs="?", const="-", default=None,
                    help="headless: run one prompt, print final answer, exit "
                         "(use '-' or no value to read from stdin)")
    ap.add_argument("--output-format", choices=["text", "json"], default="text",
                    help="with -p: plain text (default) or JSON envelope")

    sub = ap.add_subparsers(dest="cmd")
    p_serve = sub.add_parser("serve", help="run HTTP API daemon")
    p_serve.add_argument("--port", type=int, default=None)
    p_serve.add_argument("--host", default="127.0.0.1")
    sub.add_parser("sessions", help="list saved sessions")
    sub.add_parser("init", help="write default config to ~/.duo/config.toml")
    sub.add_parser("doctor", help="verify peers, MCP, readline, openclaw")
    p_run = sub.add_parser("run", help="run the interactive orchestrator (default)")
    p_run.add_argument("prompt", nargs="?")

    ap.add_argument("prompt", nargs="?", help="initial goal (omit to be asked)")
    return ap


def _cmd_sessions(cfg: DuoConfig) -> int:
    sm = SessionManager(cfg)
    rows = sm.list()
    if not rows:
        print("(no sessions yet)")
        return 0
    for s in rows:
        meta = s.meta.get("goal") or ""
        print(f"{s.id}  {s.created_at}  {meta[:60]}")
    return 0


SAMPLE_SKILL = """\
---
name: style
always: true
---
## Coding style

- Prefer clear, minimal changes over clever rewrites.
- Don't add features the user didn't ask for.
- Don't write comments that just restate the code.
- Match existing conventions (naming, imports, error handling).
"""


def _cmd_init(cfg_path: Path) -> int:
    wrote_any = False
    if not cfg_path.exists():
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        cfg_path.write_text(EXAMPLE_CONFIG, encoding="utf-8")
        print(f"wrote {cfg_path}")
        wrote_any = True
    else:
        print(f"{cfg_path} already exists — leaving alone.")

    skills_dir = cfg_path.parent / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)
    sample = skills_dir / "style.md"
    if not sample.exists():
        sample.write_text(SAMPLE_SKILL, encoding="utf-8")
        print(f"wrote {sample}")
        wrote_any = True

    if not wrote_any:
        print("(nothing to do — everything already initialised)")
    return 0


def _cmd_serve(cfg: DuoConfig, host: str, port: int | None, cwd: str) -> int:
    from .server import serve
    return serve(cfg, host=host, port=port or cfg.api_port, cwd=cwd)


def _cmd_doctor(cfg: DuoConfig, cwd: str) -> int:
    from .doctor import run_checks, format_checks
    checks = run_checks(cfg, Path(cwd).resolve())
    print(format_checks(checks))
    return 0 if all(c.ok for c in checks) else 1


def _run_print(state: State, cfg: DuoConfig, session, prompt: str,
               output_format: str) -> int:
    """Headless: run one goal, emit final answer, exit. Used by `-p/--print`."""
    import io, json as _json
    from . import peers as _peers_mod

    buf: list[tuple[str, str]] = []

    def _sink(role: str, line: str) -> None:
        buf.append((role, line))

    _peers_mod.set_sink(_sink)
    try:
        run_goal(state, prompt, cfg.max_steps)
    except Exception as e:
        if output_format == "json":
            print(_json.dumps({"ok": False, "error": str(e)}))
        else:
            print(f"error: {e}", file=sys.stderr)
        return 1
    finally:
        _peers_mod.set_sink(None)

    # Extract last supervisor turn as the final answer.
    final = ""
    for t in reversed(state.transcript):
        if t.role == state.supervisor and "decision:" not in t.text[:40]:
            final = t.text
            break
    if not final and state.transcript:
        final = state.transcript[-1].text

    if session:
        session.save_transcript(
            [{"role": t.role, "text": t.text} for t in state.transcript]
        )

    if output_format == "json":
        stats = {p.name: {"calls": p.calls, "seconds": round(p.seconds, 2),
                          "tokens_in": p.extra.get("tokens_in", 0),
                          "tokens_out": p.extra.get("tokens_out", 0)}
                 for p in state.peers.values()}
        print(_json.dumps({
            "ok": True,
            "final": final,
            "session_id": session.id if session else None,
            "turns": len(state.transcript),
            "peers": stats,
        }, indent=2))
    else:
        print(final)
    return 0


def _interactive_loop(state: State, cfg: DuoConfig, session, args, skills) -> int:
    from .ui import color

    use_tui = args.tui
    if use_tui is None:
        use_tui = (cfg.tui == "on") or (cfg.tui == "auto" and len(state.live_peers()) >= 2)
    tui_ctx = None
    if use_tui:
        try:
            from .tui import live_tui
            tui_ctx = live_tui(state)
        except Exception as e:
            print(color("err", f"TUI unavailable ({e}); plain output"))
            tui_ctx = None

    from .orchestrator import _emit as _emit_fn
    ctx = CmdCtx(state=state, session=session, cfg=cfg,
                 emit=_emit_fn)
    setattr(ctx, "_skills", skills)

    editor = LineEditor(
        history_path=duo_home() / "history",
        completer_fn=lambda: slash_completions(state, list(SLASH_HANDLERS)),
    )
    editor.setup()

    try:
        if tui_ctx: tui_ctx.__enter__()
        pending = (args.prompt or "").strip()
        if not pending:
            print(color("system", "  ask anything, or type /help · /tips · /examples"))
            pending = editor.prompt(color("user", "you ▸ ")).strip()
        while pending:
            result = dispatch(pending, ctx)
            if result.kind == "quit":
                break
            if result.kind == "goal":
                try:
                    run_goal(state, result.text, cfg.max_steps)
                except KeyboardInterrupt:
                    print(color("err", "\n⏹  interrupted — back to prompt"))
                except Exception as e:
                    from .orchestrator import DuoError
                    if isinstance(e, DuoError):
                        print(color("err", f"error: {e} — back to prompt"))
                    else:
                        print(color("err", f"unexpected: {e!r}"))
                summary(state)
                if session:
                    session.save_transcript(
                        [{"role": t.role, "text": t.text} for t in state.transcript]
                    )
            if args.once:
                break
            if tui_ctx:
                tui_ctx.__exit__(None, None, None)
                tui_ctx = None
            try:
                pending = editor.prompt(color("user", "\nyou ▸ ")).strip()
            except (KeyboardInterrupt, EOFError):
                print()
                break
            if pending and use_tui:
                from .tui import live_tui
                tui_ctx = live_tui(state)
                tui_ctx.__enter__()
        print(color("system", "bye."))
    except (KeyboardInterrupt, EOFError):
        print(color("err", "\n⏹  interrupted"))
        summary(state)
    finally:
        if tui_ctx:
            try: tui_ctx.__exit__(None, None, None)
            except Exception: pass
    return 0


def main() -> int:
    ap = _build_argparser()
    args = ap.parse_args()
    cfg = DuoConfig.load(project_dir=Path(args.cwd).resolve())
    cfg_path = duo_home() / "config.toml"

    if getattr(args, "cmd", None) == "sessions":
        return _cmd_sessions(cfg)
    if getattr(args, "cmd", None) == "init":
        return _cmd_init(cfg_path)
    if getattr(args, "cmd", None) == "serve":
        return _cmd_serve(cfg, args.host, args.port, args.cwd)
    if getattr(args, "cmd", None) == "doctor":
        return _cmd_doctor(cfg, args.cwd)

    peers = args.peers or cfg.peers
    supervisor = args.supervisor or cfg.supervisor
    ollama_model = args.ollama_model or cfg.ollama_model
    max_steps = args.max_steps or cfg.max_steps

    try:
        state = State.build(
            cwd=Path(args.cwd).resolve(),
            peer_names=peers,
            supervisor=supervisor,
            ollama_model=ollama_model,
            openclaw_cfg=getattr(cfg, "openclaw", {}) or None,
        )
    except ValueError as e:
        print(color("err", f"config error: {e}"))
        return 2

    state.cfg = cfg
    state.parallel = args.parallel or cfg.parallel_default
    state.skills = load_skills(cfg.skills_dir)
    state.mcp_config_path = write_mcp_config(cfg.mcp, cfg.sessions_dir)
    from .context import discover as _discover_ctx
    state.context_files = _discover_ctx(state.cwd, duo_home())

    sm = SessionManager(cfg)
    if args.resume:
        try:
            session = sm.resume(args.resume)
            loaded = session.load_transcript()
            from .orchestrator import Turn
            state.transcript = [Turn(t["role"], t["text"]) for t in loaded]
            print(color("system", f"resumed session {session.id} "
                                  f"({len(state.transcript)} turns)"))
        except Exception as e:
            print(color("err", f"resume failed: {e}"))
            return 2
    else:
        session = sm.new(meta={"goal": (args.prompt or ""), "peers": peers,
                               "supervisor": supervisor, "cwd": str(state.cwd)})
    state.session = session

    cfg.max_steps = max_steps

    if args.print_prompt is not None:
        prompt = args.print_prompt
        if prompt in ("", "-"):
            prompt = sys.stdin.read().strip()
        else:
            prompt = prompt.strip()
        if not prompt:
            print("error: -p/--print requires a prompt (arg or stdin)", file=sys.stderr)
            return 2
        return _run_print(state, cfg, session, prompt, args.output_format)

    banner(str(state.cwd))
    for p in state.peers.values():
        if not p.cmd_ok:
            print(color("err", f"⚠  peer '{p.name}' not on PATH — skipped"))
    active = [p.name for p in state.live_peers()]
    use_tui_hint = (args.tui if args.tui is not None else
                    cfg.tui == "on" or (cfg.tui == "auto" and len(active) >= 2))
    welcome(
        active_peers=active,
        supervisor=state.supervisor,
        session_id=session.id,
        skills=len(state.skills),
        mcp=bool(state.mcp_config_path),
        tui=bool(use_tui_hint),
    )

    return _interactive_loop(state, cfg, session, args, state.skills)


if __name__ == "__main__":
    raise SystemExit(main())
