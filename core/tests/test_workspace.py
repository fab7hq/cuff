from __future__ import annotations

from pathlib import Path

import pytest

from cuff.errors import CuffError
from cuff.ledger import append, create_claim
from cuff.workspace import find_workspace, initialize_workspace

from conftest import git


DIGEST = "sha256:" + "a" * 64
SUBJECT = {"kind": "artifact", "ref": "artifact_123", "digest": DIGEST}


def test_init_writes_the_minimal_marker_at_the_exact_git_root(repo: Path) -> None:
    before = git(repo, "rev-parse", "HEAD")

    with pytest.raises(CuffError, match="CUFF_PROJECT_NOT_INITIALIZED"):
        find_workspace(repo)

    result = initialize_workspace(repo)

    assert result == {
        "ok": True,
        "status": "initialized",
        "workspace": str(repo),
        "marker": {"schema": 1},
    }
    assert (repo / ".fab7/cuff/project.json").read_bytes() == b'{"schema":1}\n'
    assert (repo / ".fab7/cuff/records").is_dir()
    assert git(repo, "rev-parse", "HEAD") == before
    assert git(repo, "status", "--short").splitlines() == ["?? .fab7/"]


def test_init_is_idempotent_and_preserves_valid_existing_ledgers(repo: Path) -> None:
    initialize_workspace(repo)
    claim = create_claim(repo, "work-1", "Done", SUBJECT, "agent:test")
    path, _line = append(repo, claim)
    before = path.read_bytes()

    result = initialize_workspace(repo)

    assert result["status"] == "already_initialized"
    assert path.read_bytes() == before


def test_init_selects_only_current_or_explicit_directory(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    child = repo / "nested" / "child"
    child.mkdir(parents=True)
    monkeypatch.chdir(child)

    with pytest.raises(CuffError, match="CUFF_WORKSPACE_NOT_ROOT"):
        initialize_workspace()
    assert not (child / ".fab7").exists()

    result = initialize_workspace(repo)
    assert result["workspace"] == str(repo)


def test_init_rejects_non_git_nested_missing_and_non_directory_workspaces(
    repo: Path,
) -> None:
    workspace = repo.parent / f"{repo.name}-non-git"
    workspace.mkdir()
    nested = repo / "nested"
    nested.mkdir()
    missing = repo / "missing"
    file = repo / "file"
    file.write_text("x")

    with pytest.raises(CuffError, match="CUFF_NOT_A_REPOSITORY"):
        initialize_workspace(workspace)
    with pytest.raises(CuffError, match="CUFF_WORKSPACE_NOT_ROOT"):
        initialize_workspace(nested)
    for selected in (missing, file):
        with pytest.raises(CuffError, match="CUFF_WORKSPACE_INVALID"):
            initialize_workspace(selected)


def test_init_rejects_missing_git_with_one_stable_error(
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PATH", "")

    with pytest.raises(CuffError, match="CUFF_GIT_FAILED"):
        initialize_workspace(repo)


def test_nearest_project_discovery_is_bounded_and_requires_git_root(
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    initialize_workspace(repo)
    child = repo / "a" / "b"
    child.mkdir(parents=True)
    assert find_workspace(cwd=child) == repo
    assert find_workspace(repo, cwd=child) == repo

    monkeypatch.setattr("cuff.workspace.MAX_PARENT_WALK", 1)
    with pytest.raises(CuffError, match="CUFF_PROJECT_NOT_INITIALIZED"):
        find_workspace(cwd=child)


def test_nested_marker_fails_closed_instead_of_switching_to_outer_project(repo: Path) -> None:
    initialize_workspace(repo)
    nested = repo / "nested"
    (nested / ".fab7/cuff/records").mkdir(parents=True)
    (nested / ".fab7/cuff/project.json").write_bytes(b'{"schema":1}\n')

    with pytest.raises(CuffError, match="CUFF_WORKSPACE_NOT_ROOT"):
        find_workspace(cwd=nested)
    with pytest.raises(CuffError, match="CUFF_WORKSPACE_NOT_ROOT"):
        find_workspace(nested)


def test_unsafe_nested_state_fails_closed_during_discovery(repo: Path, tmp_path: Path) -> None:
    initialize_workspace(repo)
    nested = repo / "nested"
    nested.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (nested / ".fab7").mkdir()
    (nested / ".fab7/cuff").symlink_to(outside, target_is_directory=True)

    with pytest.raises(CuffError, match="CUFF_PATH_INVALID"):
        find_workspace(cwd=nested)


@pytest.mark.parametrize(
    "content",
    [
        b'{"schema":1,"version":"0.1.0"}\n',
        b'{"schema":2}\n',
        b'{ "schema": 1 }\n',
        b'{"schema":1}',
        b'{"schema":1,"schema":1}\n',
        b'not-json\n',
    ],
)
def test_incompatible_marker_is_preserved_without_hidden_rewrite(repo: Path, content: bytes) -> None:
    marker = repo / ".fab7/cuff/project.json"
    marker.parent.mkdir(parents=True)
    marker.write_bytes(content)

    with pytest.raises(CuffError, match="CUFF_PROJECT_INCOMPATIBLE"):
        initialize_workspace(repo)

    assert marker.read_bytes() == content
    assert not (repo / ".fab7/cuff/records").exists()


def test_symlinked_state_marker_and_records_fail_closed(repo: Path, tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (repo / ".fab7").symlink_to(outside, target_is_directory=True)
    with pytest.raises(CuffError, match="CUFF_PATH_INVALID"):
        initialize_workspace(repo)
    (repo / ".fab7").unlink()

    (repo / ".fab7").mkdir()
    (repo / ".fab7/cuff").symlink_to(outside, target_is_directory=True)
    with pytest.raises(CuffError, match="CUFF_PATH_INVALID"):
        initialize_workspace(repo)
    (repo / ".fab7/cuff").unlink()

    state = repo / ".fab7/cuff"
    state.mkdir()
    outside_marker = outside / "project.json"
    outside_marker.write_bytes(b'{"schema":1}\n')
    (state / "project.json").symlink_to(outside_marker)
    with pytest.raises(CuffError, match="CUFF_PATH_INVALID"):
        initialize_workspace(repo)
    (state / "project.json").unlink()

    (state / "project.json").write_bytes(b'{"schema":1}\n')
    (state / "records").symlink_to(outside, target_is_directory=True)
    with pytest.raises(CuffError, match="CUFF_PATH_INVALID"):
        initialize_workspace(repo)

    (state / "records").unlink()
    (state / "records").write_text("unsafe")
    with pytest.raises(CuffError, match="CUFF_PATH_INVALID"):
        initialize_workspace(repo)
