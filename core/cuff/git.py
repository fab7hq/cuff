"""The few Git operations required for provenance and freshness."""

from __future__ import annotations

import subprocess
from pathlib import Path

from .errors import CuffError


def _run(args: list[str], *, root: Path | str | None = None, check: bool = True) -> str:
    try:
        process = subprocess.run(
            ["git", *args],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CuffError("CUFF_GIT_FAILED", f"Git command could not complete: {exc}") from exc
    if check and process.returncode != 0:
        raise CuffError(
            "CUFF_GIT_FAILED",
            process.stderr.strip() or "Git command failed",
            {"command": ["git", *args]},
        )
    return process.stdout


def repo_root(cwd: Path | str | None = None) -> Path:
    value = _run(["rev-parse", "--show-toplevel"], root=cwd, check=False).strip()
    if not value:
        raise CuffError("CUFF_NOT_A_REPOSITORY", "Cuff must run inside a Git repository")
    return Path(value).resolve()


def head(root: Path, ref: str = "HEAD") -> str:
    value = _run(["rev-parse", "--verify", f"{ref}^{{commit}}"], root=root, check=False).strip()
    if not value:
        raise CuffError("CUFF_GIT_REF_INVALID", f"Git ref cannot be resolved: {ref}")
    return value


def is_ancestor(ancestor: str, descendant: str, root: Path) -> bool:
    try:
        process = subprocess.run(
            ["git", "merge-base", "--is-ancestor", ancestor, descendant],
            cwd=root,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CuffError("CUFF_GIT_FAILED", f"Git ancestry check could not complete: {exc}") from exc
    if process.returncode in (0, 1):
        return process.returncode == 0
    raise CuffError("CUFF_GIT_FAILED", process.stderr.decode().strip() or "Git ancestry check failed")


def default_base(root: Path, proposed_head: str = "HEAD") -> str | None:
    parent = _run(["rev-parse", "--verify", f"{proposed_head}^"], root=root, check=False).strip()
    return parent or None


def changed_files(root: Path, start: str, end: str | None = None) -> list[str]:
    args = ["-c", "core.quotePath=false", "diff", "--name-only", start]
    if end is not None:
        args.append(end)
    return [line for line in _run(args, root=root).splitlines() if line]


def dirty_paths(root: Path) -> list[str]:
    tracked = _run(
        ["-c", "core.quotePath=false", "diff", "--name-only", "HEAD"],
        root=root,
    ).splitlines()
    untracked = _run(
        ["-c", "core.quotePath=false", "ls-files", "--others", "--exclude-standard"],
        root=root,
    ).splitlines()
    return sorted({path for path in (*tracked, *untracked) if path})


def diff_status(root: Path, base: str, head_ref: str | None, pathspec: str) -> list[tuple[str, str]]:
    args = ["-c", "core.quotePath=false", "diff", "--name-status", "--no-renames", base]
    if head_ref is not None:
        args.append(head_ref)
    args.extend(["--", pathspec])
    rows: list[tuple[str, str]] = []
    for line in _run(args, root=root).splitlines():
        status, separator, path = line.partition("\t")
        if separator:
            rows.append((status, path))
    return rows


def show_file(root: Path, ref: str, path: str) -> bytes | None:
    try:
        process = subprocess.run(
            ["git", "show", f"{ref}:{path}"],
            cwd=root,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CuffError("CUFF_GIT_FAILED", f"Historical ledger could not be read: {exc}") from exc
    return process.stdout if process.returncode == 0 else None
