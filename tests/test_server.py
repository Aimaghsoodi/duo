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


# Build a urllib opener that bypasses any HTTP(S)_PROXY env vars — GitHub
# macOS runners occasionally set them and loopback requests get sent to a
# proxy that can't reach 127.0.0.1, causing the test to hang.
_NO_PROXY_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def test_health_endpoint(duo_home, tmp_path):
    cfg = DuoConfig.load()
    port = _free_port()
    t = threading.Thread(target=serve, args=(cfg,),
                         kwargs={"host": "127.0.0.1", "port": port,
                                 "cwd": str(tmp_path)},
                         daemon=True)
    t.start()
    deadline = time.monotonic() + 20.0
    last_err: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with _NO_PROXY_OPENER.open(
                f"http://127.0.0.1:{port}/health", timeout=2.0
            ) as r:
                data = json.loads(r.read().decode("utf-8"))
                assert data["ok"] is True
                assert "version" in data
                return
        except Exception as e:
            last_err = e
            time.sleep(0.2)
    raise AssertionError(f"server never started: {last_err!r}")
