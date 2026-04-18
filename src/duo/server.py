"""Minimal HTTP daemon for duo. stdlib-only.

Endpoints:
  GET  /health                → {"ok": true, "version": ..., "peers": [...]}
  GET  /sessions              → [{"id","created_at","meta"}]
  GET  /sessions/<id>         → full session meta + transcript
  GET  /sessions/<id>/events  → newline-delimited JSONL
  POST /goal                  → {"goal": "...", "resume": "<id>?"} → runs goal
                                 synchronously, returns {"session","final","transcript"}

This is a thin control-plane. It is not intended to be exposed to the public
internet. Bind to 127.0.0.1 and front with Tailscale/SSH tunnel if needed.
"""

from __future__ import annotations

import http.server
import json
import socketserver
import threading
import urllib.parse
from pathlib import Path
from typing import Any

from . import __version__
from .config import DuoConfig
from .mcp import write_mcp_config
from .orchestrator import State, run_goal
from .session import SessionManager
from .skills import load_skills


class _Handler(http.server.BaseHTTPRequestHandler):
    cfg: DuoConfig = None  # set by serve()
    cwd: str = "."

    def log_message(self, fmt, *args):  # quieter default access log
        pass

    # --- helpers ---
    def _send_json(self, obj: Any, status: int = 200) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_text(self, text: str, status: int = 200,
                   content_type: str = "text/plain; charset=utf-8") -> None:
        body = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # --- routing ---
    def do_GET(self) -> None:
        path = urllib.parse.urlparse(self.path).path.rstrip("/")

        if path == "" or path == "/health":
            return self._send_json({
                "ok": True,
                "version": __version__,
                "peers": self.cfg.peers,
                "supervisor": self.cfg.supervisor,
            })

        if path == "/sessions":
            sm = SessionManager(self.cfg)
            return self._send_json([
                {"id": s.id, "created_at": s.created_at, "meta": s.meta}
                for s in sm.list()
            ])

        parts = [p for p in path.split("/") if p]
        if len(parts) == 2 and parts[0] == "sessions":
            sm = SessionManager(self.cfg)
            try:
                s = sm.resume(parts[1])
            except Exception as e:
                return self._send_json({"error": str(e)}, 404)
            return self._send_json({
                "id": s.id, "created_at": s.created_at, "meta": s.meta,
                "transcript": s.load_transcript(),
            })

        if len(parts) == 3 and parts[0] == "sessions" and parts[2] == "events":
            sm = SessionManager(self.cfg)
            try:
                s = sm.resume(parts[1])
            except Exception as e:
                return self._send_json({"error": str(e)}, 404)
            if not s.events_path.exists():
                return self._send_text("")
            return self._send_text(s.events_path.read_text(encoding="utf-8"),
                                   content_type="application/x-ndjson; charset=utf-8")

        return self._send_json({"error": "not found"}, 404)

    def do_POST(self) -> None:
        path = urllib.parse.urlparse(self.path).path.rstrip("/")
        if path != "/goal":
            return self._send_json({"error": "not found"}, 404)
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(body.decode("utf-8") or "{}")
        except Exception as e:
            return self._send_json({"error": f"bad json: {e}"}, 400)

        goal = (data.get("goal") or "").strip()
        if not goal:
            return self._send_json({"error": "missing 'goal'"}, 400)

        cfg = self.cfg
        state = State.build(
            cwd=Path(self.cwd).resolve(),
            peer_names=cfg.peers,
            supervisor=cfg.supervisor,
            ollama_model=cfg.ollama_model,
            openclaw_cfg=getattr(cfg, "openclaw", {}) or None,
        )
        state.cfg = cfg
        state.skills = load_skills(cfg.skills_dir)
        state.mcp_config_path = write_mcp_config(cfg.mcp, cfg.sessions_dir)

        sm = SessionManager(cfg)
        if data.get("resume"):
            try:
                session = sm.resume(data["resume"])
                loaded = session.load_transcript()
                from .orchestrator import Turn
                state.transcript = [Turn(t["role"], t["text"]) for t in loaded]
            except Exception as e:
                return self._send_json({"error": f"resume failed: {e}"}, 400)
        else:
            session = sm.new(meta={"goal": goal, "peers": cfg.peers,
                                   "supervisor": cfg.supervisor, "cwd": self.cwd,
                                   "origin": "api"})
        state.session = session

        run_goal(state, goal, cfg.max_steps)
        session.save_transcript(
            [{"role": t.role, "text": t.text} for t in state.transcript]
        )

        final = ""
        for t in reversed(state.transcript):
            if t.role == state.supervisor and "DONE" in t.text.upper() or t.text.strip():
                final = t.text
                break

        return self._send_json({
            "session": session.id,
            "final": final,
            "turns": len(state.transcript),
            "transcript_path": str(session.transcript_path),
        })


class _ThreadedHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def serve(cfg: DuoConfig, *, host: str = "127.0.0.1", port: int = 8787,
          cwd: str = ".") -> int:
    _Handler.cfg = cfg
    _Handler.cwd = cwd
    httpd = _ThreadedHTTPServer((host, port), _Handler)
    print(f"duo api listening on http://{host}:{port}  (cwd={cwd})")
    print("  GET  /health")
    print("  GET  /sessions")
    print("  GET  /sessions/<id>[/events]")
    print("  POST /goal   {\"goal\":\"...\",\"resume\":\"<id>?\"}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nshutting down.")
    finally:
        httpd.server_close()
    return 0
