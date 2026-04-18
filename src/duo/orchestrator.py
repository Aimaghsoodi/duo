"""Core loop: supervisor decides → peer acts → supervisor validates."""

from __future__ import annotations

import concurrent.futures as _fut
import json
import re
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


class DuoError(RuntimeError):
    """Recoverable DuoX runtime error — caller returns to the prompt."""

from .peers import Peer, RUNNERS, make_peer
from . import peers as _peers_mod
from .ui import BOLD, DIM, RESET, color, footer, header


def _emit(role: str, text: str) -> None:
    sink = _peers_mod._sink
    if sink is _peers_mod._default_sink:
        print(color(role if role in ("claude", "codex", "ollama", "user", "system", "err") else "system", text))
    else:
        sink(role, text + "\n")


@dataclass
class Turn:
    role: str
    text: str


@dataclass
class State:
    cwd: Path
    peers: dict[str, Peer] = field(default_factory=dict)
    supervisor: str = "claude"
    transcript: list[Turn] = field(default_factory=list)
    step: int = 0
    parallel: bool = False
    session: Optional[object] = None         # session.Session
    skills: list = field(default_factory=list)  # [Skill]
    cfg: Optional[object] = None                # DuoConfig
    mcp_config_path: Optional[Path] = None
    context_files: list = field(default_factory=list)   # [ContextFile]

    @classmethod
    def build(cls, cwd: Path, peer_names: list[str], supervisor: str,
              ollama_model: str | None = None,
              openclaw_cfg: dict | None = None) -> "State":
        peers: dict[str, Peer] = {}
        for n in peer_names:
            if n not in RUNNERS:
                raise ValueError(f"unknown peer: {n!r}. choices: {list(RUNNERS)}")
            extra = {}
            if n == "ollama" and ollama_model:
                extra["model"] = ollama_model
            if n == "openclaw" and openclaw_cfg:
                extra.update(openclaw_cfg)
            peers[n] = make_peer(n, **extra)
        if supervisor not in peers:
            raise ValueError(f"supervisor {supervisor!r} must be in --peers")
        return cls(cwd=cwd, peers=peers, supervisor=supervisor)

    def log(self, role: str, text: str) -> None:
        self.transcript.append(Turn(role, text.strip()))
        if self.session:
            self.session.append_event("turn", role=role, text=text.strip())

    def render(self, limit: int = 16000) -> str:
        joined = "\n\n".join(f"[{t.role}]\n{t.text}" for t in self.transcript)
        if len(joined) > limit:
            joined = "…[earlier context truncated]…\n\n" + joined[-limit:]
        return joined

    def live_peers(self) -> list[Peer]:
        return [p for p in self.peers.values() if p.alive and p.cmd_ok]

    def executors(self) -> list[str]:
        return [n for n, p in self.peers.items()
                if n != self.supervisor and p.alive and p.cmd_ok]


def _build_prompt(state: State, task: str) -> str:
    from .context import render as render_ctx
    from .skills import select_skills, render_skills
    skill_block = ""
    if state.skills:
        chosen = select_skills(state.skills, task)
        skill_block = render_skills(chosen)
    ctx_block = render_ctx(state.context_files) if state.context_files else ""
    return f"{task}{ctx_block}{skill_block}\n\n---\nShared transcript:\n{state.render()}"


def _call(state: State, peer_name: str, task: str, *, as_json: bool = False) -> str:
    if peer_name not in state.peers:
        peer_name = state.supervisor
    peer = state.peers[peer_name]
    prompt = _build_prompt(state, task)
    cwd = str(state.cwd)
    runner, _ = RUNNERS[peer_name]

    mcp_path = str(state.mcp_config_path) if state.mcp_config_path else None

    def _go(p: Peer) -> tuple[str, bool]:
        r, _ = RUNNERS[p.name]
        if p.name == "claude":
            return r(p, prompt, cwd, as_json=as_json, mcp_config=mcp_path)
        return r(p, prompt, cwd)

    if state.session:
        state.session.append_event("peer_call_start", peer=peer_name, task_len=len(task))

    if peer.alive and peer.cmd_ok:
        out, exhausted = _go(peer)
        if not exhausted:
            if state.session:
                state.session.append_event("peer_call_end", peer=peer_name,
                                           ok=True, bytes=len(out))
            return out
        peer.alive = False
        _emit("system", f"⚠  {peer.name} exhausted — trying fallback")

    fallbacks = [state.peers[state.supervisor]] if state.supervisor != peer_name else []
    fallbacks += [p for n, p in state.peers.items()
                  if n != peer_name and n != state.supervisor]
    for fb in fallbacks:
        if not fb.alive or not fb.cmd_ok:
            continue
        out, exhausted = _go(fb)
        if not exhausted:
            if state.session:
                state.session.append_event("peer_call_end", peer=fb.name,
                                           ok=True, fallback_from=peer_name)
            return out
        fb.alive = False

    _emit("err", "✖  All peers exhausted.")
    if state.session:
        state.session.append_event("peer_call_end", peer=peer_name, ok=False)
    raise DuoError("all peers exhausted")


def _call_parallel(state: State, peer_names: list[str], task: str) -> dict[str, str]:
    """Run the same task on multiple peers concurrently; return {peer: output}."""
    out: dict[str, str] = {}
    with _fut.ThreadPoolExecutor(max_workers=len(peer_names)) as ex:
        futs = {ex.submit(_call, state, n, task): n for n in peer_names}
        for f in _fut.as_completed(futs):
            n = futs[f]
            try:
                out[n] = f.result()
            except Exception as e:
                out[n] = f"<error from {n}: {e}>"
    return out


SUPERVISOR_SYSTEM = textwrap.dedent("""\
    You are the SUPERVISOR in the DuoX multi-peer swarm. You have one or more peer
    executors available. You share a transcript and a filesystem.

    Each turn, output ONE JSON object only (no prose outside it):

        {"action": "delegate" | "execute_self" | "validate" | "done",
         "to": "<peer name>" | null,
         "instructions": "<concrete, scoped>",
         "reason": "<one sentence>",
         "final_answer": "<only if action=done>"}

    Rules:
      • Delegate heavy implementation/edits to an executor peer.
      • Use execute_self for planning, reading, small reviews.
      • After any delegate, your next turn should usually be "validate".
      • Stop with action=done when the user's goal is met.
""")

SWARM_HINT = (
    "\n\nSwarm mode is ON: if any part of this is independent, spawn parallel "
    "sub-agents and join their results."
)


def _decide(state: State, goal: str) -> dict:
    available = ", ".join(state.executors()) or "(none — execute_self only)"
    task = (SUPERVISOR_SYSTEM
            + f"\nAvailable executor peers: {available}"
            + f"\nUser goal:\n{goal}\n\nRespond with the JSON decision now.")
    _emit("system", f"· {state.supervisor} deciding…")
    with _peers_mod.quiet_stream():
        raw = _call(state, state.supervisor, task)
    m = re.search(r"\{[\s\S]*\}", raw)
    if not m:
        return {"action": "done", "final_answer": raw, "reason": "no-json"}
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return {"action": "done", "final_answer": raw, "reason": "bad-json"}


def _print_decision(state: State, d: dict) -> None:
    action = d.get("action", "?")
    to = d.get("to")
    reason = d.get("reason", "")
    instr = (d.get("instructions") or "").strip()
    arrow = f" → {to}" if to else ""
    _emit(state.supervisor, f"▸ decision: {action}{arrow}  — {reason}")
    for ln in instr.splitlines():
        _emit(state.supervisor, f"  {ln}")


def _run_hooks(state: State, kind: str) -> None:
    from .hooks import run_hooks
    cfg = state.cfg
    cmds = ((getattr(cfg, "hooks", {}) or {}).get(kind)) or []
    if not cmds:
        return
    results = run_hooks(cmds, str(state.cwd))
    for r in results:
        tag = "ok" if r.ok else f"FAIL rc={r.rc}"
        _emit("system" if r.ok else "err",
              f"[{kind}] $ {r.cmd}  [{tag}, {r.duration:.1f}s]")
        if state.session:
            state.session.append_event("hook", kind=kind, cmd=r.cmd,
                                       rc=r.rc, duration=r.duration)


def run_goal(state: State, goal: str, max_steps: int = 30) -> None:
    state.log("user", goal)
    _emit("user", "▸ user goal: " + goal)

    for step in range(1, max_steps + 1):
        state.step = step
        _run_hooks(state, "pre_step")

        if state.session:
            state.session.append_event("step_start", step=step)

        decision = _decide(state, goal)
        state.log(state.supervisor, "decision: " + json.dumps(decision))
        _print_decision(state, decision)

        action = decision.get("action")
        instr = decision.get("instructions", "")

        if action == "done":
            final = decision.get("final_answer") or "(no final answer)"
            _emit("system", "━━━ DONE ━━━")
            for ln in final.splitlines():
                _emit("system", "  " + ln)
            _run_hooks(state, "post_step")
            return

        if action == "delegate":
            target = decision.get("to")
            if state.parallel and len(state.executors()) >= 2:
                results = _call_parallel(state, state.executors(), instr + SWARM_HINT)
                combined = "\n\n".join(f"=== {n} ===\n{t}" for n, t in results.items())
                state.log("system", combined)
                _emit("system", f"· {state.supervisor} merging parallel results…")
                with _peers_mod.quiet_stream():
                    check = _call(state, state.supervisor,
                        "You ran the same instruction on multiple peers in parallel. "
                        "Compare their outputs, pick the best (or merge), and state "
                        "which and why.\n\n" + combined)
                state.log(state.supervisor, "merge: " + check)
                _emit(state.supervisor, check)
            else:
                if not target or target not in state.peers or target == state.supervisor:
                    execs = state.executors()
                    target = execs[0] if execs else state.supervisor
                out = _call(state, target, instr + SWARM_HINT)
                state.log(target, out)

                _emit("system", f"· {state.supervisor} validating…")
                with _peers_mod.quiet_stream():
                    check = _call(state, state.supervisor,
                        "Validate the latest peer output against the user goal. "
                        "3-8 bullet lines. Plain text, no JSON.")
                state.log(state.supervisor, "validation: " + check)
                _emit(state.supervisor, check)
            _run_hooks(state, "post_step")
            continue

        if action == "execute_self":
            out = _call(state, state.supervisor, instr + SWARM_HINT)
            state.log(state.supervisor, out)
            _run_hooks(state, "post_step")
            continue

        if action == "validate":
            out = _call(state, state.supervisor,
                instr or "Review the latest result, state pass/fail with reasons.")
            state.log(state.supervisor, "validation: " + out)
            _run_hooks(state, "post_step")
            continue

        _emit("err", f"unknown action {action!r}; stopping.")
        return

    _emit("system", f"hit max-steps={max_steps}; stopping.")


def summary(state: State) -> None:
    _emit("system", "━━━ summary ━━━")
    for p in state.peers.values():
        if not p.cmd_ok:
            status = "NOT INSTALLED"
        elif not p.alive:
            status = "EXHAUSTED"
        else:
            status = "alive"
        toks = ""
        ti, to = p.extra.get("tokens_in", 0), p.extra.get("tokens_out", 0)
        if ti or to:
            toks = f"  tok_in={ti} tok_out={to}"
        _emit("system",
              f"  {p.name:<10} calls={p.calls}  time={p.seconds:.1f}s  "
              f"{status}{toks}")
