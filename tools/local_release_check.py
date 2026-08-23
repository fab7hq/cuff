"""Verify the editable Cuff CLI and host plugins in isolated homes."""

from __future__ import annotations

import argparse
import filecmp
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

PRODUCT = "cuff"
DISTRIBUTION = "cuff-cli"
VERSION = "0.1.0"


def run(argv: list[str], *, env: dict[str, str], cwd: Path | None = None) -> str:
    completed = subprocess.run(
        argv,
        cwd=cwd,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=900,
    )
    if completed.returncode:
        detail = (completed.stderr or completed.stdout).strip()
        raise RuntimeError(f"{' '.join(argv[:4])} failed: {detail}")
    return completed.stdout


def copy_payload(source: Path, target: Path) -> None:
    shutil.copytree(source, target)


def assert_cached_payload(source: Path, host_home: Path, manifest: str) -> None:
    candidates = []
    for found in host_home.rglob(manifest):
        root = found.parent.parent
        try:
            data = json.loads(found.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if data.get("name") == PRODUCT:
            candidates.append(root)
    for candidate in candidates:
        files = [path for path in source.rglob("*") if path.is_file()]
        if all(
            (candidate / path.relative_to(source)).is_file()
            and filecmp.cmp(path, candidate / path.relative_to(source), shallow=False)
            for path in files
        ):
            return
    raise RuntimeError(f"{PRODUCT} installed payload does not match its source")


def install_editable(root: Path, temp: Path, env: dict[str, str]) -> None:
    bin_dir = temp / "bin"
    env["UV_TOOL_DIR"] = str(temp / "uv-tools")
    env["UV_TOOL_BIN_DIR"] = str(bin_dir)
    run(["uv", "tool", "install", "--force", "--editable", str(root)], env=env)
    output = run([str(bin_dir / PRODUCT), "--version"], env=env)
    if VERSION not in output:
        raise RuntimeError(f"unexpected {PRODUCT} version: {output.strip()}")


def codex_check(root: Path, temp: Path, env: dict[str, str], live: bool) -> None:
    source = root / "plugins" / "codex" / PRODUCT
    marketplace = temp / "codex-marketplace"
    payload = marketplace / "plugins" / PRODUCT
    copy_payload(source, payload)
    catalog = marketplace / ".agents" / "plugins" / "marketplace.json"
    catalog.parent.mkdir(parents=True)
    catalog.write_text(
        json.dumps(
            {
                "name": "fab7-local",
                "interface": {"displayName": "Fab7 local"},
                "plugins": [
                    {
                        "name": PRODUCT,
                        "source": {"source": "local", "path": f"./plugins/{PRODUCT}"},
                        "policy": {
                            "installation": "AVAILABLE",
                            "authentication": "ON_INSTALL",
                        },
                        "category": "Productivity",
                    }
                ],
            },
            indent=2,
        )
        + "\n"
    )
    host_home = temp / "codex-home"
    host_home.mkdir()
    env["CODEX_HOME"] = str(host_home)
    run(["codex", "plugin", "marketplace", "add", str(marketplace)], env=env)
    run(["codex", "plugin", "add", f"{PRODUCT}@fab7-local"], env=env)
    run(["codex", "plugin", "list"], env=env)
    assert_cached_payload(source, host_home, ".codex-plugin/plugin.json")
    if live:
        workspace = temp / "workspace-codex"
        workspace.mkdir()
        run(
            [
                "codex",
                "exec",
                "--ephemeral",
                "--json",
                "--skip-git-repo-check",
                "-C",
                str(workspace),
                f"Use the {PRODUCT} plugin to run `{PRODUCT} --version`; do not modify files.",
            ],
            env=env,
        )


def claude_check(root: Path, temp: Path, env: dict[str, str], live: bool) -> None:
    source = root / "plugins" / "claude" / PRODUCT
    marketplace = temp / "claude-marketplace"
    payload = marketplace / "plugins" / PRODUCT
    copy_payload(source, payload)
    catalog = marketplace / ".claude-plugin" / "marketplace.json"
    catalog.parent.mkdir(parents=True)
    catalog.write_text(
        json.dumps(
            {
                "$schema": "https://json.schemastore.org/claude-code-marketplace.json",
                "name": "fab7-local",
                "description": "Isolated Fab7 development marketplace.",
                "owner": {"name": "Fab7"},
                "plugins": [
                    {
                        "name": PRODUCT,
                        "description": "Local development payload.",
                        "version": VERSION,
                        "source": f"./plugins/{PRODUCT}",
                        "category": "productivity",
                    }
                ],
            },
            indent=2,
        )
        + "\n"
    )
    host_home = temp / "claude-home"
    host_home.mkdir()
    env["CLAUDE_CONFIG_DIR"] = str(host_home)
    run(["claude", "plugin", "validate", str(source)], env=env)
    run(["claude", "plugin", "marketplace", "add", str(marketplace)], env=env)
    run(
        ["claude", "plugin", "install", f"{PRODUCT}@fab7-local", "--scope", "user", "--yes"],
        env=env,
    )
    run(["claude", "plugin", "list"], env=env)
    assert_cached_payload(source, host_home, ".claude-plugin/plugin.json")
    if live:
        workspace = temp / "workspace-claude"
        workspace.mkdir()
        run(
            [
                "claude",
                "-p",
                f"Use the {PRODUCT} plugin to run `{PRODUCT} --version`; do not modify files.",
                "--plugin-dir",
                str(source),
                "--output-format",
                "stream-json",
                "--verbose",
            ],
            env=env,
            cwd=workspace,
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", choices=("codex", "claude", "all"), default="all")
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix=f"{PRODUCT}-release-") as directory:
        temp = Path(directory)
        env = os.environ.copy()
        install_editable(root, temp, env)
        if args.host in ("codex", "all"):
            codex_check(root, temp, env.copy(), args.live)
        if args.host in ("claude", "all"):
            claude_check(root, temp, env.copy(), args.live)
    print(f"{DISTRIBUTION} {VERSION}: local CLI and {args.host} plugin check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
