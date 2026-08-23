"""Safe selection and initialization of one Git-root Cuff workspace."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from . import git
from .errors import CuffError
from .ledger import RECORDS_DIR, STATE_DIR, init as init_records


MAX_PARENT_WALK = 64
PROJECT_PATH = Path(".fab7/cuff/project.json")
PROJECT_MARKER = {"schema": 1}
PROJECT_MARKER_BYTES = b'{"schema":1}\n'


def initialize_workspace(
    explicit: Path | None = None,
    *,
    cwd: Path | None = None,
) -> dict[str, Any]:
    """Initialize only the caller-selected directory or current directory."""
    start = (cwd or Path.cwd()).resolve()
    root = _existing_directory(explicit or start, start)
    _require_git_root(root)
    state = root / STATE_DIR
    marker = root / PROJECT_PATH
    _require_safe_state_paths(state, marker)
    _require_safe_records_path(root / RECORDS_DIR)

    existed = marker.exists()
    if existed:
        _read_marker(marker)
    else:
        state.mkdir(mode=0o755, parents=True, exist_ok=True)
    init_records(root)
    if not existed:
        _create_marker(marker)
    return {
        "ok": True,
        "status": "already_initialized" if existed else "initialized",
        "workspace": str(root),
        "marker": dict(PROJECT_MARKER),
    }


def find_workspace(
    explicit: Path | None = None,
    *,
    cwd: Path | None = None,
) -> Path:
    """Find and validate the explicit or nearest parent Cuff workspace."""
    start = (cwd or Path.cwd()).resolve()
    if explicit is not None:
        root = _existing_directory(explicit, start)
        _validate_project(root)
        return root

    current = start
    for _ in range(MAX_PARENT_WALK):
        state = current / STATE_DIR
        marker = current / PROJECT_PATH
        if state.parent.is_symlink() or state.is_symlink() or (state.exists() and not state.is_dir()):
            raise CuffError(
                "CUFF_PATH_INVALID",
                "Cuff state path in workspace discovery is unsafe",
                {"path": str(state)},
            )
        if marker.exists() or marker.is_symlink():
            _validate_project(current)
            return current
        parent = current.parent
        if parent == current:
            break
        current = parent
    raise _not_initialized(start)


def _validate_project(root: Path) -> None:
    state = root / STATE_DIR
    marker = root / PROJECT_PATH
    if not marker.exists() and not marker.is_symlink():
        raise _not_initialized(root)
    _require_safe_state_paths(state, marker)
    _read_marker(marker)
    _require_git_root(root)
    records = root / RECORDS_DIR
    _require_safe_records_path(records)
    if not records.is_dir():
        raise CuffError(
            "CUFF_PROJECT_INVALID",
            "Cuff records directory is missing or unsafe; rerun cuff init",
            {"path": str(records)},
        )


def _require_git_root(root: Path) -> None:
    repository = git.repo_root(root)
    if repository != root.resolve():
        raise CuffError(
            "CUFF_WORKSPACE_NOT_ROOT",
            "Cuff workspace must be the Git worktree root",
            {"workspace": str(root.resolve()), "repository": str(repository)},
        )


def _existing_directory(path: Path, start: Path) -> Path:
    candidate = path.expanduser()
    if not candidate.is_absolute():
        candidate = start / candidate
    if candidate.is_symlink() or not candidate.is_dir():
        raise CuffError(
            "CUFF_WORKSPACE_INVALID",
            "Workspace must be one existing non-symlink directory",
            {"path": str(candidate)},
        )
    return candidate.resolve()


def _require_safe_state_paths(state: Path, marker: Path) -> None:
    if state.parent.is_symlink() or (state.parent.exists() and not state.parent.is_dir()):
        raise CuffError(
            "CUFF_PATH_INVALID",
            "Cuff state directory must be a non-symlink directory",
            {"path": str(state.parent)},
        )
    if state.is_symlink() or (state.exists() and not state.is_dir()):
        raise CuffError(
            "CUFF_PATH_INVALID",
            "Cuff state directory must be a non-symlink directory",
            {"path": str(state)},
        )
    if marker.is_symlink() or (marker.exists() and not marker.is_file()):
        raise CuffError(
            "CUFF_PATH_INVALID",
            "Cuff project marker must be a regular non-symlink file",
            {"path": str(marker)},
        )


def _require_safe_records_path(records: Path) -> None:
    if records.is_symlink() or (records.exists() and not records.is_dir()):
        raise CuffError(
            "CUFF_PATH_INVALID",
            "Cuff records path must be a non-symlink directory",
            {"path": str(records)},
        )


def _read_marker(path: Path) -> dict[str, int]:
    try:
        content = path.read_bytes()
        data = json.loads(content, object_pairs_hook=_no_duplicate_keys)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise CuffError(
            "CUFF_PROJECT_INCOMPATIBLE",
            "Cuff project marker is incompatible; archive or remove only the marker and rerun cuff init",
            {"path": str(path)},
        ) from exc
    if data != PROJECT_MARKER or content != PROJECT_MARKER_BYTES:
        raise CuffError(
            "CUFF_PROJECT_INCOMPATIBLE",
            "Cuff project marker is incompatible; archive or remove only the marker and rerun cuff init",
            {"path": str(path)},
        )
    return data


def _create_marker(path: Path) -> None:
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile("wb", dir=path.parent, prefix=".project.", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(PROJECT_MARKER_BYTES)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            _read_marker(path)
        descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def _no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for key, value in pairs:
        if key in data:
            raise ValueError(f"duplicate JSON key: {key}")
        data[key] = value
    return data


def _not_initialized(path: Path) -> CuffError:
    return CuffError(
        "CUFF_PROJECT_NOT_INITIALIZED",
        "No Cuff project was found; run cuff init or pass --workspace",
        {"path": str(path)},
    )
