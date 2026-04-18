import sys

import pytest

from duo.hooks import run_hook, run_hooks


def test_run_hook_ok(tmp_path):
    r = run_hook(f'{sys.executable} -c "print(42)"', cwd=str(tmp_path))
    assert r.ok
    assert "42" in r.stdout


def test_run_hook_fail(tmp_path):
    r = run_hook(f'{sys.executable} -c "import sys; sys.exit(3)"', cwd=str(tmp_path))
    assert not r.ok
    assert r.rc == 3


def test_run_hooks_batch(tmp_path):
    results = run_hooks([
        f'{sys.executable} -c "print(1)"',
        f'{sys.executable} -c "print(2)"',
    ], cwd=str(tmp_path))
    assert len(results) == 2
    assert results[0].ok and results[1].ok
