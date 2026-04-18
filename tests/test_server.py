import json
import socket
import threading
import time
import urllib.request

from duo.config import DuoConfig
from duo.server import serve


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_health_endpoint(duo_home, tmp_path):
    cfg = DuoConfig.load()
    port = _free_port()
    t = threading.Thread(target=serve, args=(cfg,),
                         kwargs={"host": "127.0.0.1", "port": port,
                                 "cwd": str(tmp_path)},
                         daemon=True)
    t.start()
    deadline = time.monotonic() + 15.0
    last_err: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1.0) as r:
                data = json.loads(r.read().decode("utf-8"))
                assert data["ok"] is True
                assert "version" in data
                return
        except Exception as e:
            last_err = e
            time.sleep(0.2)
    raise AssertionError(f"server never started: {last_err!r}")
