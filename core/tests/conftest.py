from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


def git(root: Path, *args: str) -> str:
    process = subprocess.run(
        ["git", *args],
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert process.returncode == 0, process.stderr
    return process.stdout.strip()


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.name", "Cuff Test")
    git(tmp_path, "config", "user.email", "test@example.com")
    (tmp_path / "app.py").write_text("VALUE = 1\n")
    git(tmp_path, "add", "app.py")
    git(tmp_path, "commit", "-qm", "baseline")
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    return tmp_path
