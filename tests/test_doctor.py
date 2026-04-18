from pathlib import Path

from duo.config import DuoConfig
from duo.doctor import run_checks, format_checks, Check


def test_run_checks_returns_list(duo_home, tmp_path):
    cfg = DuoConfig()
    checks = run_checks(cfg, tmp_path)
    names = {c.name for c in checks}
    assert "readline" in names
    assert "config" in names
    assert "context files" in names
    # each configured peer is checked
    for p in cfg.peers:
        assert f"peer:{p}" in names


def test_format_checks_has_marks():
    checks = [Check("x", True, "ok"), Check("y", False, "bad", "run foo")]
    out = format_checks(checks)
    assert "✓ x" in out
    assert "✗ y" in out
    assert "fix: run foo" in out
    assert "1/2 checks passing" in out


def test_cli_doctor_subcommand(duo_home, tmp_path, capsys):
    from duo.cli import _build_argparser, _cmd_doctor
    cfg = DuoConfig()
    rc = _cmd_doctor(cfg, str(tmp_path))
    assert rc in (0, 1)  # ok if peers missing in test env
    out = capsys.readouterr().out
    assert "checks passing" in out


def test_print_flag_parses_with_value():
    from duo.cli import _build_argparser
    ap = _build_argparser()
    args = ap.parse_args(["-p", "hello world", "--output-format", "json"])
    assert args.print_prompt == "hello world"
    assert args.output_format == "json"


def test_print_flag_bare_means_stdin():
    from duo.cli import _build_argparser
    ap = _build_argparser()
    args = ap.parse_args(["-p"])
    assert args.print_prompt == "-"
