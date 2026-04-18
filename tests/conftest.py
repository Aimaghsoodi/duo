import os
import pytest


@pytest.fixture
def duo_home(tmp_path, monkeypatch):
    """Isolate ~/.duo to a tmpdir for each test."""
    home = tmp_path / "duohome"
    home.mkdir()
    monkeypatch.setenv("DUO_HOME", str(home))
    return home
