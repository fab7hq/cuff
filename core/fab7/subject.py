"""Closed subject identities and deterministic filesystem manifests."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from pathlib import Path
from typing import Any

from .errors import Fab7Error


SUBJECT_FIELDS = {"kind", "ref", "digest"}
SUBJECT_KIND_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,119}$")
SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
FILESYSTEM_KINDS = {"file", "tree"}
MAX_REF_BYTES = 2048
MAX_FILES = 10_000
MAX_BYTES = 256 * 1024 * 1024
MAX_DEPTH = 64
MAX_NAME_BYTES = 255


def declared_subject(kind: str, ref: str, digest: str) -> dict[str, str]:
    subject = {"kind": kind, "ref": ref, "digest": digest}
    validate_subject(subject)
    if kind in FILESYSTEM_KINDS:
        raise Fab7Error(
            "FAB7_SUBJECT_INVALID",
            "The file and tree subject kinds are reserved for --subject-path",
        )
    return subject


def validate_subject(value: Any) -> dict[str, str]:
    if not isinstance(value, dict) or set(value) != SUBJECT_FIELDS:
        raise Fab7Error("FAB7_SUBJECT_INVALID", "Subject fields are invalid")
    kind = value.get("kind")
    ref = value.get("ref")
    digest = value.get("digest")
    if not isinstance(kind, str) or SUBJECT_KIND_RE.fullmatch(kind) is None:
        raise Fab7Error("FAB7_SUBJECT_INVALID", "Subject kind must be a bounded lowercase token")
    if (
        not isinstance(ref, str)
        or not ref
        or len(ref.encode("utf-8")) > MAX_REF_BYTES
        or any(ord(character) < 32 or ord(character) == 127 for character in ref)
    ):
        raise Fab7Error("FAB7_SUBJECT_INVALID", "Subject ref must be bounded text without controls")
    if not isinstance(digest, str) or SHA256_RE.fullmatch(digest) is None:
        raise Fab7Error("FAB7_SUBJECT_INVALID", "Subject digest must be lowercase SHA-256")
    return {"kind": kind, "ref": ref, "digest": digest}


def filesystem_subject(root: Path, path: Path) -> dict[str, str]:
    workspace = root.resolve()
    target, reference = _bounded_target(workspace, path)
    target_stat = target.stat(follow_symlinks=False)
    if stat.S_ISREG(target_stat.st_mode):
        entries = [_file_entry(target, reference, target_stat)]
        kind = "file"
    elif stat.S_ISDIR(target_stat.st_mode):
        entries = _tree_entries(workspace, target)
        kind = "tree"
    else:
        raise Fab7Error(
            "FAB7_SUBJECT_PATH_INVALID",
            "Filesystem subjects must be regular files or directories",
            {"path": str(path)},
        )
    total_bytes = sum(entry["bytes"] for entry in entries)
    if len(entries) > MAX_FILES or total_bytes > MAX_BYTES:
        raise Fab7Error(
            "FAB7_SUBJECT_BOUNDS",
            "Filesystem subject exceeds the file or byte bound",
            {"files": len(entries), "bytes": total_bytes},
        )
    manifest = {"format": "fab7-manifest-1", "entries": entries}
    encoded = json.dumps(
        manifest,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode()
    return {"kind": kind, "ref": reference, "digest": "sha256:" + hashlib.sha256(encoded).hexdigest()}


def current_subject(root: Path, subject: dict[str, str]) -> dict[str, str]:
    validated = validate_subject(subject)
    if validated["kind"] not in FILESYSTEM_KINDS:
        return validated
    current = filesystem_subject(root, Path(validated["ref"]))
    if current["kind"] != validated["kind"]:
        raise Fab7Error("FAB7_SUBJECT_CHANGED", "Filesystem subject kind changed")
    return current


def _bounded_target(workspace: Path, path: Path) -> tuple[Path, str]:
    raw = path.expanduser()
    candidate = raw if raw.is_absolute() else workspace / raw
    lexical = Path(os.path.abspath(candidate))
    try:
        relative = lexical.relative_to(workspace)
    except ValueError as exc:
        raise Fab7Error("FAB7_SUBJECT_PATH_INVALID", "Subject path escapes the workspace") from exc
    if relative.parts[:1] == (".fab7",):
        raise Fab7Error("FAB7_SUBJECT_PATH_INVALID", "Fab7 controller state cannot be a subject")
    current = workspace
    for part in relative.parts:
        if len(os.fsencode(part)) > MAX_NAME_BYTES:
            raise Fab7Error("FAB7_SUBJECT_BOUNDS", "Filesystem subject name exceeds the bound")
        current /= part
        if current.is_symlink():
            raise Fab7Error("FAB7_SUBJECT_PATH_INVALID", "Filesystem subjects must not contain symlinks")
    if not lexical.exists():
        raise Fab7Error("FAB7_SUBJECT_PATH_INVALID", "Filesystem subject does not exist")
    resolved = lexical.resolve()
    try:
        resolved.relative_to(workspace)
    except ValueError as exc:
        raise Fab7Error("FAB7_SUBJECT_PATH_INVALID", "Subject path escapes the workspace") from exc
    reference = relative.as_posix() if relative.parts else "."
    return resolved, reference


def _tree_entries(workspace: Path, target: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    total_bytes = 0
    for directory, names, filenames in os.walk(target, topdown=True, followlinks=False):
        directory_path = Path(directory)
        relative_directory = directory_path.relative_to(target)
        if len(relative_directory.parts) > MAX_DEPTH:
            raise Fab7Error("FAB7_SUBJECT_BOUNDS", "Filesystem subject exceeds the depth bound")
        for name in [*names, *filenames]:
            if len(os.fsencode(name)) > MAX_NAME_BYTES:
                raise Fab7Error("FAB7_SUBJECT_BOUNDS", "Filesystem subject name exceeds the bound")

        kept_names: list[str] = []
        for name in names:
            candidate = directory_path / name
            workspace_relative = candidate.relative_to(workspace)
            if workspace_relative.parts[:1] == (".fab7",):
                continue
            directory_mode = candidate.stat(follow_symlinks=False).st_mode
            if stat.S_ISLNK(directory_mode):
                raise Fab7Error("FAB7_SUBJECT_PATH_INVALID", "Filesystem subjects must not contain symlinks")
            if not stat.S_ISDIR(directory_mode):
                raise Fab7Error("FAB7_SUBJECT_PATH_INVALID", "Filesystem subjects contain a special entry")
            kept_names.append(name)
        names[:] = sorted(kept_names, key=os.fsencode)

        for name in sorted(filenames, key=os.fsencode):
            candidate = directory_path / name
            metadata = candidate.stat(follow_symlinks=False)
            if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
                raise Fab7Error("FAB7_SUBJECT_PATH_INVALID", "Filesystem subjects contain a special entry")
            relative = candidate.relative_to(workspace).as_posix()
            entries.append(_file_entry(candidate, relative, metadata))
            total_bytes += metadata.st_size
            if len(entries) > MAX_FILES or total_bytes > MAX_BYTES:
                raise Fab7Error("FAB7_SUBJECT_BOUNDS", "Filesystem subject exceeds the file or byte bound")
    entries.sort(key=lambda entry: os.fsencode(entry["path"]))
    return entries


def _file_entry(path: Path, reference: str, metadata: os.stat_result) -> dict[str, Any]:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return {
        "path": reference,
        "mode": stat.S_IMODE(metadata.st_mode),
        "bytes": metadata.st_size,
        "digest": "sha256:" + digest.hexdigest(),
    }
