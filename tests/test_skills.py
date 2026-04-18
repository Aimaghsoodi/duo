from pathlib import Path

from duo.skills import load_skills, select_skills, render_skills


def test_load_and_select(tmp_path: Path):
    (tmp_path / "a.md").write_text(
        '---\nname: testing\nmatch: ["test", "pytest"]\n---\nuse pytest -q\n',
        encoding="utf-8",
    )
    (tmp_path / "b.md").write_text(
        '---\nname: global\nalways: true\n---\nremember the style guide\n',
        encoding="utf-8",
    )
    skills = load_skills(tmp_path)
    names = sorted(s.name for s in skills)
    assert names == ["global", "testing"]

    chosen = select_skills(skills, "please run the tests")
    chosen_names = sorted(s.name for s in chosen)
    assert chosen_names == ["global", "testing"]

    rendered = render_skills(chosen)
    assert "testing" in rendered and "global" in rendered


def test_select_ignores_non_matching(tmp_path: Path):
    (tmp_path / "a.md").write_text(
        '---\nname: frontend\nmatch: ["react", "css"]\n---\nhints\n',
        encoding="utf-8",
    )
    skills = load_skills(tmp_path)
    assert select_skills(skills, "fix the backend") == []
