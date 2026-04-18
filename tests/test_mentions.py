from duo.mentions import expand, parse


def test_expand_whole_file(tmp_path):
    (tmp_path / "hello.py").write_text("print('hi')\n", encoding="utf-8")
    out, used = expand("look at @hello.py and explain", tmp_path)
    assert len(used) == 1
    assert "## Mentions" in out
    assert "print('hi')" in out


def test_expand_line_range(tmp_path):
    (tmp_path / "x.py").write_text("a\nb\nc\nd\ne\n", encoding="utf-8")
    out, used = expand("see @x.py:2-4", tmp_path)
    assert used[0].start == 2 and used[0].end == 4
    assert "b\nc\nd" in out
    assert "e" not in out.split("## Mentions")[1]


def test_expand_directory(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("", encoding="utf-8")
    (tmp_path / "src" / "b.py").write_text("", encoding="utf-8")
    out, used = expand("check @src", tmp_path)
    assert used and used[0].is_dir
    assert "a.py" in out and "b.py" in out


def test_missing_file_silent(tmp_path):
    out, used = expand("read @nope.md", tmp_path)
    assert used == []
    assert out == "read @nope.md"


def test_escape(tmp_path):
    (tmp_path / "real.md").write_text("x", encoding="utf-8")
    out, used = expand(r"email \@user and see @real.md", tmp_path)
    assert len(used) == 1
    assert "@user" in out  # escaped one preserved as literal


def test_path_escape_blocked(tmp_path):
    sub = tmp_path / "sub"
    sub.mkdir()
    (tmp_path / "secret.txt").write_text("nope", encoding="utf-8")
    found = parse("read @../secret.txt", sub)
    assert found == []


def test_quoted_path(tmp_path):
    (tmp_path / "a b.md").write_text("spaced", encoding="utf-8")
    out, used = expand('open @"a b.md"', tmp_path)
    assert used and "spaced" in out
