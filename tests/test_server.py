import json
import threading
import time
import urllib.request

from duo.config import DuoConfig
from duo.server import serve


def test_health_endpoint(duo_home, tmp_path):
    cfg = DuoConfig.load()
    # pick a non-default port to avoid collisions
    port = 18899
    t = threading.Thread(target=serve, args=(cfg,),
                         kwargs={"host": "127.0.0.1", "port": port,
                                 "cwd": str(tmp_path)},
                         daemon=True)
    t.start()
    # wait for bind
    for _ in range(30):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=0.2) as r:
                data = json.loads(r.read().decode("utf-8"))
                assert data["ok"] is True
                assert "version" in data
                return
        except Exception:
            time.sleep(0.1)
    raise AssertionError("server never started")
