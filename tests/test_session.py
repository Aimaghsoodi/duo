import json

from duo.config import DuoConfig
from duo.session import SessionManager


def test_new_and_list(duo_home):
    cfg = DuoConfig.load()
    sm = SessionManager(cfg)
    s = sm.new(meta={"goal": "hi"})
    assert s.events_path.exists()
    s.append_event("turn", role="user", text="hi")
    assert s.events_path.read_text(encoding="utf-8").strip().count("\n") == 1
    rows = sm.list()
    assert any(r.id == s.id for r in rows)


def test_resume_by_prefix(duo_home):
    cfg = DuoConfig.load()
    sm = SessionManager(cfg)
    s = sm.new()
    got = sm.resume(s.id[:8])
    assert got.id == s.id


def test_transcript_roundtrip(duo_home):
    cfg = DuoConfig.load()
    sm = SessionManager(cfg)
    s = sm.new()
    s.save_transcript([{"role": "user", "text": "hi"}])
    assert s.load_transcript() == [{"role": "user", "text": "hi"}]
