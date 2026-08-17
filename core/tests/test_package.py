from __future__ import annotations

import json
import subprocess
import sys
import tomllib
import zipfile
from pathlib import Path

from cuff import __version__


ROOT = Path(__file__).resolve().parents[2]


def test_standard_package_metadata_is_lean_and_aligned() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())
    lock = tomllib.loads((ROOT / "uv.lock").read_text())
    locked_project = next(row for row in lock["package"] if row["name"] == "cuff-cli")

    assert __version__ == project["project"]["version"] == locked_project["version"] == "0.1.0"
    assert project["project"]["requires-python"] == ">=3.11"
    assert project["project"]["dependencies"] == []
    assert project["project"]["scripts"] == {"cuff": "cuff.cli:main"}
    assert project["tool"]["cuff"]["recommended-uv-version"] == "0.11.32"
    assert "build" not in project.get("dependency-groups", {})
    assert "package-data" not in project.get("tool", {}).get("setuptools", {})


def test_wheel_contains_only_the_proof_runtime(tmp_path: Path) -> None:
    process = subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(tmp_path)],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert process.returncode == 0, process.stderr
    wheel = next(tmp_path.glob("cuff_cli-0.1.0-*.whl"))
    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())

    assert {f"cuff/{name}" for name in (
        "__init__.py", "__main__.py", "cli.py", "errors.py", "gate.py", "git.py",
        "ledger.py", "subject.py", "workspace.py",
    )}.issubset(names)
    assert not any(
        token in name.lower()
        for name in names
        for token in ("extension", "template", "host", "plugin", "pyinstaller", "native")
    )


def test_import_boundary_loads_only_proof_core_modules() -> None:
    process = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys, cuff.cli; "
            "print('\\n'.join(sorted(name for name in sys.modules if name.startswith('cuff.'))))",
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert process.returncode == 0, process.stderr
    assert process.stdout.splitlines() == [
        "cuff.cli",
        "cuff.errors",
        "cuff.gate",
        "cuff.git",
        "cuff.ledger",
        "cuff.subject",
        "cuff.workspace",
    ]
    legacy = subprocess.run(
        [sys.executable, "-c", "import fab7"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert legacy.returncode != 0
    assert "No module named 'fab7'" in legacy.stderr


def test_static_host_plugins_are_short_and_runtime_free() -> None:
    codex = ROOT / "plugins/codex/cuff"
    claude = ROOT / "plugins/claude/cuff"
    codex_manifest = json.loads((codex / ".codex-plugin/plugin.json").read_text())
    claude_manifest = json.loads((claude / ".claude-plugin/plugin.json").read_text())

    assert codex_manifest["name"] == claude_manifest["name"] == "cuff"
    assert codex_manifest["version"] == claude_manifest["version"] == "0.1.0"
    assert codex_manifest["skills"] == "./skills/"
    assert sorted(path.parent.name for path in codex.glob("skills/*/SKILL.md")) == [
        "check", "init", "seal"
    ]
    assert sorted(path.stem for path in claude.glob("commands/*.md")) == ["check", "init", "seal"]
    for path in [*codex.rglob("*"), *claude.rglob("*")]:
        if path.is_file():
            text = path.read_text()
            assert len(text.splitlines()) <= 40
            for retired in ("pyinstaller", "cuff home", "native executable", "extension catalog"):
                assert retired not in text.lower()
