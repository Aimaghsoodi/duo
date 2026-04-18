from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

from duo.commands import CmdCtx, dispatch
from duo.config import DuoConfig
from duo.orchestrator import State, Turn
from duo.peers import make_peer


def _make_ctx(tmp_path):
    state = State(cwd=tmp_path, peers={
        "claude": make_peer("claude"),
        "codex":  make_peer("codex"),
    }, supervisor="claude")
    cfg = DuoConfig()
    outputs = []
    ctx = CmdCtx(state=state, session=None, cfg=cfg,
                 emit=lambda role, text: outputs.append((role, text)))
    return ctx, outputs


def test_non_slash_is_goal(tmp_path):
    ctx, _ = _make_ctx(tmp_path)
    r = dispatch("build a todo app", ctx)
    assert r.kind == "goal"
    assert r.text == "build a todo app"


def test_help(tmp_path):
    ctx, outs = _make_ctx(tmp_path)
    r = dispatch("/help", ctx)
    assert r.kind == "handled"
    assert any("DuoX commands" in text for _, text in outs)


def test_quit(tmp_path):
    ctx, _ = _make_ctx(tmp_path)
    assert dispatch("/quit", ctx).kind == "quit"
    assert dispatch("/exit", ctx).kind == "quit"


def test_clear(tmp_path):
    ctx, _ = _make_ctx(tmp_path)
    ctx.state.transcript.append(Turn("user", "x"))
    r = dispatch("/clear", ctx)
    assert r.kind == "handled"
    assert ctx.state.transcript == []


def test_peers_list_and_set(tmp_path):
    ctx, outs = _make_ctx(tmp_path)
    dispatch("/peers", ctx)
    assert any("peers:" in text for _, text in outs)

    dispatch("/peers claude,ollama", ctx)
    assert set(ctx.state.peers) == {"claude", "ollama"}


def test_supervisor_switch(tmp_path):
    ctx, _ = _make_ctx(tmp_path)
    dispatch("/supervisor codex", ctx)
    assert ctx.state.supervisor == "codex"


def test_parallel_toggle(tmp_path):
    ctx, _ = _make_ctx(tmp_path)
    dispatch("/parallel on", ctx)
    assert ctx.state.parallel is True
    dispatch("/parallel off", ctx)
    assert ctx.state.parallel is False


def test_plan_and_review_become_goals(tmp_path):
    ctx, _ = _make_ctx(tmp_path)
    r = dispatch("/plan add logging", ctx)
    assert r.kind == "goal" and "PLAN ONLY" in r.text
    r = dispatch("/review last diff", ctx)
    assert r.kind == "goal" and "REVIEW ONLY" in r.text


def test_tips_and_examples(tmp_path):
    ctx, outs = _make_ctx(tmp_path)
    dispatch("/tips", ctx)
    assert any("tips" in text.lower() for _, text in outs)
    outs.clear()
    dispatch("/examples", ctx)
    assert any("examples" in text.lower() for _, text in outs)


def test_remember_appends_to_notes(tmp_path, monkeypatch):
    monkeypatch.setenv("DUO_HOME", str(tmp_path / "duohome"))
    ctx, _ = _make_ctx(tmp_path)
    r = dispatch("/remember use pnpm not npm in this repo", ctx)
    assert r.kind == "handled"
    notes = tmp_path / "duohome" / "notes.md"
    assert notes.exists()
    assert "use pnpm not npm" in notes.read_text(encoding="utf-8")


def test_remember_requires_arg(tmp_path):
    ctx, outs = _make_ctx(tmp_path)
    dispatch("/remember", ctx)
    assert any("usage" in t for _, t in outs)


def test_cd_changes_cwd(tmp_path):
    sub = tmp_path / "proj"
    sub.mkdir()
    ctx, outs = _make_ctx(tmp_path)
    dispatch(f"/cd {sub}", ctx)
    assert ctx.state.cwd == sub.resolve()


def test_cd_rejects_non_dir(tmp_path):
    ctx, outs = _make_ctx(tmp_path)
    (tmp_path / "file.txt").write_text("x", encoding="utf-8")
    dispatch(f"/cd {tmp_path / 'file.txt'}", ctx)
    assert any("not a directory" in t for _, t in outs)


def test_mention_in_goal_expands(tmp_path):
    ctx, outs = _make_ctx(tmp_path)
    (tmp_path / "note.md").write_text("hello world", encoding="utf-8")
    r = dispatch("please read @note.md", ctx)
    assert r.kind == "goal"
    assert "hello world" in r.text
    assert any("expanded 1 mention" in t for _, t in outs)


def test_unknown_command(tmp_path):
    ctx, outs = _make_ctx(tmp_path)
    r = dispatch("/nosuch", ctx)
    assert r.kind == "handled"
    assert any("unknown command" in text for _, text in outs)
