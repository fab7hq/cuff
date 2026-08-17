from __future__ import annotations

import os
from pathlib import Path

import pytest

from cuff.errors import CuffError
from cuff.subject import declared_subject, filesystem_subject, validate_subject


DIGEST = "sha256:" + "a" * 64


def test_declared_subject_is_closed_and_bounded() -> None:
    assert declared_subject("denim-fabric", "fabric_123", DIGEST) == {
        "kind": "denim-fabric",
        "ref": "fabric_123",
        "digest": DIGEST,
    }

    invalid = [
        ("Denim", "fabric_123", DIGEST),
        ("denim", "", DIGEST),
        ("denim", "fabric\n123", DIGEST),
        ("denim", "fabric_123", "sha256:" + "A" * 64),
    ]
    for kind, ref, digest in invalid:
        with pytest.raises(CuffError, match="CUFF_SUBJECT_INVALID"):
            declared_subject(kind, ref, digest)

    for kind in ("file", "tree"):
        with pytest.raises(CuffError, match="reserved"):
            declared_subject(kind, "artifact", DIGEST)

    with pytest.raises(CuffError, match="Subject fields are invalid"):
        validate_subject({"kind": "artifact", "ref": "a", "digest": DIGEST, "extra": "x"})
    with pytest.raises(CuffError, match="bounded lowercase token"):
        declared_subject("a" * 121, "artifact", DIGEST)
    with pytest.raises(CuffError, match="bounded text"):
        declared_subject("artifact", "a" * 2049, DIGEST)


def test_filesystem_manifest_is_deterministic_and_content_bound(workspace: Path) -> None:
    tree = workspace / "subject"
    tree.mkdir()
    (tree / "b.txt").write_text("b\n")
    (tree / "a.txt").write_text("a\n")

    first = filesystem_subject(workspace, tree)
    second = filesystem_subject(workspace, Path("subject"))
    assert first == second
    assert first["kind"] == "tree"
    assert first["ref"] == "subject"

    (tree / "a.txt").write_text("changed\n")
    assert filesystem_subject(workspace, tree)["digest"] != first["digest"]


def test_filesystem_manifest_binds_mode_and_file_identity(workspace: Path) -> None:
    path = workspace / "tool"
    path.write_text("#!/bin/sh\n")
    path.chmod(0o644)
    first = filesystem_subject(workspace, path)
    path.chmod(0o755)
    second = filesystem_subject(workspace, path)

    assert first["kind"] == "file"
    assert first["ref"] == "tool"
    assert second["digest"] != first["digest"]


def test_filesystem_manifest_rejects_escape_controller_state_and_symlink(
    workspace: Path,
    tmp_path: Path,
) -> None:
    outside = tmp_path.parent / "outside-subject"
    outside.write_text("outside")
    (workspace / ".cuff").mkdir()
    (workspace / ".cuff/state").write_text("state")
    (workspace / "link").symlink_to(outside)

    for path in (outside, workspace / ".cuff", workspace / "link"):
        with pytest.raises(CuffError, match="CUFF_SUBJECT_PATH_INVALID"):
            filesystem_subject(workspace, path)


def test_filesystem_manifest_rejects_special_files_and_bounds(
    workspace: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fifo = workspace / "pipe"
    os.mkfifo(fifo)
    with pytest.raises(CuffError, match="CUFF_SUBJECT_PATH_INVALID"):
        filesystem_subject(workspace, fifo)

    tree = workspace / "bounded"
    tree.mkdir()
    (tree / "one").write_text("1")
    (tree / "two").write_text("2")
    monkeypatch.setattr("cuff.subject.MAX_FILES", 1)
    with pytest.raises(CuffError, match="CUFF_SUBJECT_BOUNDS"):
        filesystem_subject(workspace, tree)


def test_filesystem_manifest_enforces_byte_depth_and_name_bounds(
    workspace: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    byte_tree = workspace / "bytes"
    byte_tree.mkdir()
    (byte_tree / "a").write_text("12")
    with monkeypatch.context() as bounded:
        bounded.setattr("cuff.subject.MAX_BYTES", 1)
        with pytest.raises(CuffError, match="CUFF_SUBJECT_BOUNDS"):
            filesystem_subject(workspace, byte_tree)

    depth_tree = workspace / "depth"
    (depth_tree / "child").mkdir(parents=True)
    (depth_tree / "child" / "a").write_text("1")
    with monkeypatch.context() as bounded:
        bounded.setattr("cuff.subject.MAX_DEPTH", 0)
        with pytest.raises(CuffError, match="CUFF_SUBJECT_BOUNDS"):
            filesystem_subject(workspace, depth_tree)

    name_tree = workspace / "names"
    name_tree.mkdir()
    (name_tree / "long").write_text("1")
    with monkeypatch.context() as bounded:
        bounded.setattr("cuff.subject.MAX_NAME_BYTES", 3)
        with pytest.raises(CuffError, match="CUFF_SUBJECT_BOUNDS"):
            filesystem_subject(workspace, name_tree)
