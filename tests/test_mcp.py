import json

from duo.mcp import write_mcp_config


def test_empty_returns_none(tmp_path):
    assert write_mcp_config({}, tmp_path) is None
    assert write_mcp_config({"servers": {}}, tmp_path) is None


def test_translates_duo_to_claude(tmp_path):
    mcp = {
        "servers": {
            "context7": {"command": "npx", "args": ["-y", "@upstash/context7-mcp"]},
            "gh":       {"command": "gh-mcp", "env": {"TOKEN": "abc"}},
        }
    }
    path = write_mcp_config(mcp, tmp_path)
    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert set(data["mcpServers"]) == {"context7", "gh"}
    assert data["mcpServers"]["context7"]["args"] == ["-y", "@upstash/context7-mcp"]
    assert data["mcpServers"]["gh"]["env"] == {"TOKEN": "abc"}
