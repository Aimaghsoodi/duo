from pathlib import Path

from duo.config import DuoConfig, EXAMPLE_CONFIG, duo_home


def test_defaults(duo_home):
    cfg = DuoConfig.load()
    assert cfg.peers == ["claude", "codex"]
    assert cfg.supervisor == "claude"
    assert cfg.max_steps == 30
    assert cfg.skills_dir == Path(duo_home) / "skills"
    assert cfg.sessions_dir == Path(duo_home) / "sessions"


def test_loads_toml(duo_home, tmp_path):
    (duo_home / "config.toml").write_text(
        '''
peers = ["claude", "ollama"]
supervisor = "ollama"
max_steps = 7
ollama_model = "qwen2.5"
parallel_default = true
[hooks]
pre_step = ["echo pre"]
post_step = ["echo post"]
[mcp.servers.x]
command = "npx"
args = ["-y", "foo"]
''',
        encoding="utf-8",
    )
    cfg = DuoConfig.load()
    assert cfg.peers == ["claude", "ollama"]
    assert cfg.supervisor == "ollama"
    assert cfg.max_steps == 7
    assert cfg.ollama_model == "qwen2.5"
    assert cfg.parallel_default is True
    assert cfg.hooks["pre_step"] == ["echo pre"]
    assert cfg.mcp["servers"]["x"]["command"] == "npx"


def test_project_config_overrides_global(duo_home, tmp_path):
    (duo_home / "config.toml").write_text(
        'peers = ["claude", "codex"]\nsupervisor = "claude"\nmax_steps = 30\n'
        '[hooks]\npre_step = ["echo global"]\n',
        encoding="utf-8",
    )
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / ".duo.toml").write_text(
        'supervisor = "codex"\nmax_steps = 5\n'
        '[hooks]\npost_step = ["echo project"]\n',
        encoding="utf-8",
    )
    cfg = DuoConfig.load(project_dir=proj)
    assert cfg.supervisor == "codex"
    assert cfg.max_steps == 5
    assert cfg.peers == ["claude", "codex"]  # inherited
    assert cfg.hooks["pre_step"] == ["echo global"]
    assert cfg.hooks["post_step"] == ["echo project"]


def test_deep_merge():
    from duo.config import _deep_merge
    a = {"x": 1, "nested": {"a": 1, "b": 2}}
    b = {"y": 2, "nested": {"b": 20, "c": 3}}
    out = _deep_merge(a, b)
    assert out == {"x": 1, "y": 2, "nested": {"a": 1, "b": 20, "c": 3}}


def test_example_contains_keys():
    # sanity — example is valid TOML-ish and has the keys we document
    assert "peers" in EXAMPLE_CONFIG
    assert "[hooks]" in EXAMPLE_CONFIG
    assert "[mcp." in EXAMPLE_CONFIG
