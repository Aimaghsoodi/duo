from unittest.mock import patch

from duo import openclaw as oc
from duo.peers import RUNNERS, make_peer
from duo.commands import CmdCtx, dispatch
from duo.orchestrator import State
from duo.config import DuoConfig


def test_registered_in_runners():
    assert "openclaw" in RUNNERS
    runner, probe = RUNNERS["openclaw"]
    assert probe == "openclaw"


def test_doctor_when_missing(monkeypatch):
    monkeypatch.setattr(oc.shutil, "which", lambda _: None)
    r = oc.doctor()
    # fallback uses 'openclaw' path which then FileNotFoundError → rc=127
    assert isinstance(r, oc.OcResult)
    assert r.rc in (127, 1)


def test_send_message_returns_result(monkeypatch):
    class FakeCP:
        returncode = 0
        stdout = "sent ok\n"
        stderr = ""
    def fake_run(*a, **kw):
        return FakeCP()
    monkeypatch.setattr(oc.subprocess, "run", fake_run)
    monkeypatch.setattr(oc.shutil, "which", lambda _: "/usr/bin/openclaw")
    r = oc.send_message("+1234", "hi")
    assert r.ok
    assert "sent ok" in r.text


def test_slash_commands_registered(tmp_path):
    state = State(cwd=tmp_path, peers={"claude": make_peer("claude")},
                  supervisor="claude")
    cfg = DuoConfig()
    outs = []
    ctx = CmdCtx(state=state, session=None, cfg=cfg,
                 emit=lambda role, text: outs.append((role, text)))
    # /oc-health when openclaw missing should emit err, not crash
    dispatch("/oc-health", ctx)
    assert outs, "expected at least one emitted message"
    # /oc-send bad args
    outs.clear()
    dispatch("/oc-send", ctx)
    assert any("oc-send" in t.lower() or "not installed" in t.lower() for _, t in outs)
