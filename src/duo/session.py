"""Persistent sessions + JSONL event log."""

from __future__ import annotations

import datetime as _dt
import json
import os
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from .config import DuoConfig


def _now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


@dataclass
class Session:
    id: str
    root: Path
    created_at: str = field(default_factory=_now_iso)
    meta: dict = field(default_factory=dict)

    @property
    def events_path(self) -> Path:
        return self.root / "events.jsonl"

    @property
    def transcript_path(self) -> Path:
        return self.root / "transcript.json"

    @property
    def meta_path(self) -> Path:
        return self.root / "session.json"

    def write_meta(self) -> None:
        self.meta_path.write_text(
            json.dumps({
                "id": self.id,
                "created_at": self.created_at,
                "meta": self.meta,
            }, indent=2),
            encoding="utf-8",
        )

    def append_event(self, kind: str, **fields: Any) -> None:
        rec = {"ts": _now_iso(), "kind": kind, **fields}
        with self.events_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def save_transcript(self, transcript: list[dict]) -> None:
        self.transcript_path.write_text(
            json.dumps(transcript, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def load_transcript(self) -> list[dict]:
        if not self.transcript_path.exists():
            return []
        return json.loads(self.transcript_path.read_text(encoding="utf-8"))


class SessionManager:
    def __init__(self, cfg: DuoConfig) -> None:
        self.cfg = cfg
        self.root = cfg.sessions_dir
        self.root.mkdir(parents=True, exist_ok=True)

    def new(self, meta: dict | None = None) -> Session:
        sid = _dt.datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
        p = self.root / sid
        p.mkdir(parents=True, exist_ok=True)
        s = Session(id=sid, root=p, meta=meta or {})
        s.write_meta()
        s.append_event("session_start", meta=s.meta)
        return s

    def list(self) -> list[Session]:
        out: list[Session] = []
        for d in sorted(self.root.iterdir(), reverse=True):
            if not d.is_dir():
                continue
            meta_path = d / "session.json"
            if not meta_path.exists():
                continue
            try:
                data = json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception:
                continue
            out.append(Session(id=data["id"], root=d,
                               created_at=data.get("created_at", ""),
                               meta=data.get("meta", {})))
        return out

    def resume(self, sid: str) -> Session:
        # allow prefix match
        candidates = [s for s in self.list() if s.id.startswith(sid)]
        if not candidates:
            raise FileNotFoundError(f"no session matching {sid!r}")
        if len(candidates) > 1:
            raise ValueError(f"ambiguous session prefix {sid!r}: "
                             + ", ".join(c.id for c in candidates[:5]))
        s = candidates[0]
        s.append_event("session_resume")
        return s
