"""Closed claim/evidence ledgers and atomic command observations."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import subprocess
import tempfile
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator

from .errors import CuffError
from .subject import SHA256_RE, current_subject, validate_subject


RECORDS_DIR = ".cuff/records"
WORK_ITEM_RE = re.compile(r"^[a-z0-9_.-]{1,120}$")
RECORD_ID_RE = re.compile(r"^rec_[0-9a-f]{32}$")
GIT_OID_RE = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
CLAIM_FIELDS = {"v", "id", "type", "work_item", "created_at", "actor", "summary", "subject"}
EVIDENCE_FIELDS = {
    "v", "id", "type", "work_item", "created_at", "actor", "claim",
    "subject_digest", "command_digest", "exit_code", "output_digest", "provenance",
}
MAX_ACTOR_BYTES = 256
MAX_SUMMARY_BYTES = 4096
MAX_COMMAND_ARGUMENTS = 256
MAX_COMMAND_BYTES = 64 * 1024
MAX_RETAINED_OUTPUT = 1024 * 1024


@dataclass(frozen=True)
class LedgerBaseline:
    length: int
    digest: str


@dataclass(frozen=True)
class Observation:
    stdout: bytes
    stderr: bytes
    output_digest: str
    exit_code: int
    timed_out: bool = False


@dataclass(frozen=True)
class Verification:
    record: dict[str, Any]
    stdout: bytes
    stderr: bytes
    path: Path
    line: int
    timed_out: bool = False


@dataclass(frozen=True)
class Sealing:
    claim: dict[str, Any]
    evidence: dict[str, Any]
    stdout: bytes
    stderr: bytes
    path: Path
    lines: list[int]
    timed_out: bool = False


def normalize_work_item(value: str | None) -> str:
    if value is None:
        raise CuffError("CUFF_WORK_ITEM_REQUIRED", "A work item is required")
    if not isinstance(value, str):
        raise CuffError("CUFF_WORK_ITEM_INVALID", "Work item must be a short workspace-safe name")
    normalized = re.sub(r"[^a-z0-9_.-]+", "-", value.strip().lower()).strip("-")
    if not normalized or normalized in {".", ".."} or WORK_ITEM_RE.fullmatch(normalized) is None:
        raise CuffError("CUFF_WORK_ITEM_INVALID", "Work item must be a short workspace-safe name")
    return normalized


def resolve_actor(explicit: str | None) -> str:
    actor = explicit if explicit is not None else os.environ.get("CUFF_ACTOR")
    return _bounded_text(actor if actor is not None else "human:unknown", "actor", MAX_ACTOR_BYTES)


def init(root: Path) -> Path:
    path = root / RECORDS_DIR
    if (root / ".cuff").is_symlink() or path.is_symlink():
        raise CuffError("CUFF_PATH_INVALID", "Cuff workspace directories must not be symlinks")
    path.mkdir(parents=True, exist_ok=True)
    read_all(root)
    return path


def record_path(root: Path, work_item: str) -> Path:
    return root / RECORDS_DIR / f"{normalize_work_item(work_item)}.jsonl"


def baseline(root: Path, work_item: str) -> LedgerBaseline:
    path = record_path(root, work_item)
    content = path.read_bytes() if path.exists() else b""
    return _content_baseline(content)


def create_claim(
    root: Path,
    work_item: str,
    summary: str,
    subject: dict[str, str],
    actor: str | None = None,
) -> dict[str, Any]:
    selected_actor = resolve_actor(actor)
    record = {
        **_base_record("claim", work_item, selected_actor),
        "summary": _bounded_text(summary.strip(), "summary", MAX_SUMMARY_BYTES),
        "subject": validate_subject(subject),
    }
    validate_record(record)
    return record


def verify(
    root: Path,
    work_item: str,
    claim_id: str,
    command: list[str],
    *,
    timeout: float = 300,
    actor: str | None = None,
) -> Verification:
    normalized = normalize_work_item(work_item)
    records = read(root, normalized)
    claim = next(
        (record for record in records if record["type"] == "claim" and record["id"] == claim_id),
        None,
    )
    if claim is None:
        raise CuffError("CUFF_CLAIM_UNKNOWN", "Evidence must link to a claim in the same work item")
    expected = baseline(root, normalized)
    subject = _capture_subject(root, claim["subject"])
    git_state = _capture_git(root)
    observation = observe_command(root, command, timeout=timeout)
    _require_unchanged_subject(root, subject)
    evidence_provenance = _finish_provenance(root, git_state)
    evidence = _create_evidence(
        normalized,
        claim,
        command,
        observation,
        evidence_provenance,
        resolve_actor(actor),
    )
    path, lines = append_many(root, [evidence], expected=expected)
    return Verification(
        evidence,
        observation.stdout,
        observation.stderr,
        path,
        lines[0],
        observation.timed_out,
    )


def seal(
    root: Path,
    work_item: str,
    summary: str,
    subject: dict[str, str],
    command: list[str],
    *,
    timeout: float = 300,
    actor: str | None = None,
) -> Sealing:
    normalized = normalize_work_item(work_item)
    read(root, normalized)
    expected = baseline(root, normalized)
    captured_subject = _capture_subject(root, subject)
    selected_actor = resolve_actor(actor)
    claim = create_claim(root, normalized, summary, captured_subject, selected_actor)
    git_state = _capture_git(root)
    observation = observe_command(root, command, timeout=timeout)
    _require_unchanged_subject(root, captured_subject)
    evidence_provenance = _finish_provenance(root, git_state)
    evidence = _create_evidence(
        normalized,
        claim,
        command,
        observation,
        evidence_provenance,
        selected_actor,
    )
    path, lines = append_many(root, [claim, evidence], expected=expected)
    return Sealing(
        claim,
        evidence,
        observation.stdout,
        observation.stderr,
        path,
        lines,
        observation.timed_out,
    )


def observe_command(root: Path, command: list[str], *, timeout: float = 300) -> Observation:
    _validate_command(command, timeout)
    timed_out = False
    with tempfile.TemporaryFile() as stdout_file, tempfile.TemporaryFile() as stderr_file:
        try:
            process = subprocess.Popen(
                command,
                cwd=root,
                stdout=stdout_file,
                stderr=stderr_file,
            )
        except OSError as exc:
            raise CuffError("CUFF_COMMAND_FAILED", f"Verification command could not start: {exc}") from exc
        try:
            exit_code = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            process.kill()
            process.wait()
            exit_code = 124
        except KeyboardInterrupt:
            process.kill()
            process.wait()
            raise
        digest = _output_digest(stdout_file, stderr_file)
        stdout, stderr = _retained_output(stdout_file, stderr_file)
    return Observation(stdout, stderr, digest, exit_code, timed_out)


def append(root: Path, record: dict[str, Any]) -> tuple[Path, int]:
    path, lines = append_many(root, [record])
    return path, lines[0]


def append_many(
    root: Path,
    records: list[dict[str, Any]],
    *,
    expected: LedgerBaseline | None = None,
) -> tuple[Path, list[int]]:
    if not records:
        raise CuffError("CUFF_LEDGER_INVALID", "At least one record is required")
    for record in records:
        validate_record(record)
    work_items = {record["work_item"] for record in records}
    if len(work_items) != 1:
        raise CuffError("CUFF_LEDGER_INVALID", "Atomic records must share one work item")
    work_item = next(iter(work_items))
    path = record_path(root, work_item)
    directory = root / RECORDS_DIR
    if not directory.is_dir():
        raise CuffError("CUFF_NOT_INITIALIZED", "Run cuff init first")
    if directory.is_symlink() or path.is_symlink():
        raise CuffError("CUFF_PATH_INVALID", "Cuff ledgers must not be symlinks")
    with _lock(path):
        existing = path.read_bytes() if path.exists() else b""
        if expected is not None and _content_baseline(existing) != expected:
            raise CuffError(
                "CUFF_CONCURRENT_UPDATE",
                "The ledger changed while verification was running",
            )
        prior = _parse(existing, path)
        _require_ledger_work_item(prior, work_item, path)
        content = existing + b"".join((_canonical(record) + "\n").encode() for record in records)
        _require_ledger_work_item(_parse(content, path), work_item, path)
        first_line = len(prior) + 1
        _replace(path, content)
    return path, list(range(first_line, first_line + len(records)))


def read(root: Path, work_item: str) -> list[dict[str, Any]]:
    normalized = normalize_work_item(work_item)
    directory = root / RECORDS_DIR
    if directory.is_symlink():
        raise CuffError("CUFF_PATH_INVALID", "Cuff records directory must not be a symlink")
    path = record_path(root, normalized)
    if not path.exists():
        return []
    if path.is_symlink():
        raise CuffError("CUFF_PATH_INVALID", "Cuff ledgers must not be symlinks")
    records = _parse(path.read_bytes(), path)
    _require_ledger_work_item(records, normalized, path)
    return records


def read_all(root: Path) -> dict[str, list[dict[str, Any]]]:
    directory = root / RECORDS_DIR
    if not directory.is_dir():
        raise CuffError("CUFF_NOT_INITIALIZED", "Run cuff init first")
    if directory.is_symlink():
        raise CuffError("CUFF_PATH_INVALID", "Cuff records directory must not be a symlink")
    ledgers: dict[str, list[dict[str, Any]]] = {}
    for path in sorted(directory.glob("*.jsonl")):
        if path.is_symlink():
            raise CuffError("CUFF_PATH_INVALID", "Cuff ledgers must not be symlinks", {"path": str(path)})
        work_item = normalize_work_item(path.stem)
        records = _parse(path.read_bytes(), path)
        _require_ledger_work_item(records, work_item, path)
        ledgers[work_item] = records
    return ledgers


def validate_record(record: Any) -> None:
    if not isinstance(record, dict):
        raise CuffError("CUFF_LEDGER_INVALID", "Each JSONL line must be an object")
    if "git_ref" in record:
        raise CuffError(
            "CUFF_LEDGER_INVALID",
            "Ledger schema is incompatible; archive or remove .cuff and run cuff init",
        )
    record_type = record.get("type")
    allowed = (
        CLAIM_FIELDS
        if record_type == "claim"
        else EVIDENCE_FIELDS
        if record_type == "evidence"
        else set()
    )
    if not allowed or set(record) != allowed:
        raise CuffError(
            "CUFF_LEDGER_INVALID",
            "Record fields or type are invalid",
            {"record_id": record.get("id")},
        )
    if (
        record.get("v") != 1
        or not isinstance(record.get("id"), str)
        or RECORD_ID_RE.fullmatch(record["id"]) is None
    ):
        raise CuffError("CUFF_LEDGER_INVALID", "Record version or id is invalid")
    if normalize_work_item(record.get("work_item")) != record["work_item"]:
        raise CuffError("CUFF_LEDGER_INVALID", "Work item is not canonical")
    _validate_timestamp(record.get("created_at"))
    _bounded_text(record.get("actor"), "actor", MAX_ACTOR_BYTES)
    if record_type == "claim":
        _bounded_text(record.get("summary"), "summary", MAX_SUMMARY_BYTES)
        validate_subject(record.get("subject"))
        return
    if not isinstance(record["claim"], str) or RECORD_ID_RE.fullmatch(record["claim"]) is None:
        raise CuffError("CUFF_LEDGER_INVALID", "Evidence claim link is invalid")
    if type(record["exit_code"]) is not int:
        raise CuffError("CUFF_LEDGER_INVALID", "Evidence exit_code must be an integer")
    for field in ("subject_digest", "command_digest", "output_digest"):
        if not isinstance(record[field], str) or SHA256_RE.fullmatch(record[field]) is None:
            raise CuffError("CUFF_LEDGER_INVALID", f"Evidence {field} is invalid")
    _validate_provenance(record["provenance"])


def _create_evidence(
    work_item: str,
    claim: dict[str, Any],
    command: list[str],
    observation: Observation,
    provenance: dict[str, str],
    actor: str,
) -> dict[str, Any]:
    record = {
        **_base_record("evidence", work_item, actor),
        "claim": claim["id"],
        "subject_digest": claim["subject"]["digest"],
        "command_digest": "sha256:" + hashlib.sha256(_canonical(command).encode()).hexdigest(),
        "exit_code": observation.exit_code,
        "output_digest": observation.output_digest,
        "provenance": provenance,
    }
    validate_record(record)
    return record


def _base_record(record_type: str, work_item: str, actor: str) -> dict[str, Any]:
    return {
        "v": 1,
        "id": "rec_" + uuid.uuid4().hex,
        "type": record_type,
        "work_item": normalize_work_item(work_item),
        "created_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "actor": _bounded_text(actor, "actor", MAX_ACTOR_BYTES),
    }


def _parse(content: bytes, path: Path) -> list[dict[str, Any]]:
    if not content:
        return []
    if not content.endswith(b"\n"):
        raise CuffError("CUFF_LEDGER_INVALID", "JSONL ledger must end with a newline", {"path": str(path)})
    records: list[dict[str, Any]] = []
    for line_number, raw in enumerate(content.splitlines(), 1):
        try:
            record = json.loads(raw, object_pairs_hook=_no_duplicate_keys)
            validate_record(record)
        except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
            raise CuffError(
                "CUFF_LEDGER_INVALID", "Ledger contains invalid JSON", {"path": str(path), "line": line_number}
            ) from exc
        except CuffError as exc:
            raise CuffError(
                exc.code,
                exc.message,
                {**exc.context, "path": str(path), "line": line_number},
            ) from exc
        records.append(record)
    ids = [record["id"] for record in records]
    if len(ids) != len(set(ids)):
        raise CuffError("CUFF_LEDGER_INVALID", "Ledger contains duplicate record ids", {"path": str(path)})
    claims: dict[str, dict[str, Any]] = {}
    for record in records:
        if record["type"] == "claim":
            claims[record["id"]] = record
            continue
        claim = claims.get(record["claim"])
        if claim is None:
            raise CuffError(
                "CUFF_LEDGER_INVALID",
                "Evidence links to an unknown claim",
                {"record_id": record["id"]},
            )
        if record["work_item"] != claim["work_item"]:
            raise CuffError(
                "CUFF_LEDGER_INVALID",
                "Evidence work item differs from its claim",
                {"record_id": record["id"]},
            )
        if record["subject_digest"] != claim["subject"]["digest"]:
            raise CuffError(
                "CUFF_LEDGER_INVALID",
                "Evidence subject digest differs from its claim",
                {"record_id": record["id"]},
            )
    return records


def _require_ledger_work_item(
    records: list[dict[str, Any]],
    work_item: str,
    path: Path,
) -> None:
    if any(record["work_item"] != work_item for record in records):
        raise CuffError(
            "CUFF_LEDGER_INVALID",
            "Record work item does not match its ledger",
            {"path": str(path)},
        )


def _capture_subject(root: Path, subject: dict[str, str]) -> dict[str, str]:
    declared = validate_subject(subject)
    observed = current_subject(root, declared)
    if observed["digest"] != declared["digest"]:
        raise CuffError("CUFF_SUBJECT_CHANGED", "Filesystem subject does not match its declared digest")
    return declared


def _require_unchanged_subject(root: Path, subject: dict[str, str]) -> None:
    try:
        observed = current_subject(root, subject)
    except CuffError as exc:
        raise CuffError(
            "CUFF_SUBJECT_CHANGED",
            "Subject changed during verification; no evidence was recorded",
        ) from exc
    if observed != subject:
        raise CuffError(
            "CUFF_SUBJECT_CHANGED",
            "Subject changed during verification; no evidence was recorded",
        )


def _capture_git(root: Path) -> tuple[Path, str]:
    from . import git

    workspace = root.resolve()
    repository = git.repo_root(workspace)
    if repository != workspace:
        raise CuffError(
            "CUFF_WORKSPACE_NOT_ROOT",
            "Cuff workspace must be the Git worktree root",
            {"workspace": str(workspace), "repository": str(repository)},
        )
    dirty = [path for path in git.dirty_paths(repository) if not _is_record_path(repository, root, path)]
    if dirty:
        raise CuffError(
            "CUFF_REPOSITORY_DIRTY",
            "Commit or remove non-ledger changes before Git-provenance verification",
            {"paths": dirty},
        )
    return repository, git.head(repository)


def _finish_provenance(root: Path, state: tuple[Path, str]) -> dict[str, str]:
    repository, commit = state
    from . import git

    current_repository = git.repo_root(root)
    current_commit = git.head(current_repository)
    if current_repository != repository or current_commit != commit:
        raise CuffError(
            "CUFF_REPOSITORY_CHANGED",
            "Verification command changed Git HEAD; no evidence was recorded",
        )
    dirty = [path for path in git.dirty_paths(repository) if not _is_record_path(repository, root, path)]
    if dirty:
        raise CuffError(
            "CUFF_REPOSITORY_DIRTY",
            "Verification command left non-ledger Git changes; no evidence was recorded",
            {"paths": dirty},
        )
    return {"kind": "git", "commit": commit}


def _is_record_path(repository: Path, root: Path, path: str) -> bool:
    try:
        prefix = (root / RECORDS_DIR).resolve().relative_to(repository.resolve()).as_posix()
    except ValueError:
        return False
    normalized = path.replace("\\", "/")
    return normalized == prefix or normalized.startswith(prefix + "/")


def _validate_provenance(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        raise CuffError("CUFF_LEDGER_INVALID", "Evidence provenance must be an object")
    if set(value) == {"kind", "commit"} and value.get("kind") == "git":
        commit = value.get("commit")
        if isinstance(commit, str) and GIT_OID_RE.fullmatch(commit) is not None:
            return value
    raise CuffError("CUFF_LEDGER_INVALID", "Evidence provenance is invalid")


def _validate_command(command: list[str], timeout: float) -> None:
    if not command:
        raise CuffError("CUFF_COMMAND_REQUIRED", "Pass a verification command after --")
    if (
        len(command) > MAX_COMMAND_ARGUMENTS
        or any(not isinstance(argument, str) or not argument or "\0" in argument for argument in command)
        or sum(len(argument.encode()) for argument in command) > MAX_COMMAND_BYTES
    ):
        raise CuffError("CUFF_COMMAND_INVALID", "Verification command exceeds its argument bounds")
    if not math.isfinite(timeout) or timeout <= 0:
        raise CuffError("CUFF_TIMEOUT_INVALID", "Verification timeout must be a positive number")


def _validate_timestamp(value: Any) -> None:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise CuffError("CUFF_LEDGER_INVALID", "created_at must be a UTC timestamp ending in Z")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CuffError("CUFF_LEDGER_INVALID", "created_at must be an ISO timestamp") from exc
    if parsed.utcoffset() != UTC.utcoffset(parsed):
        raise CuffError("CUFF_LEDGER_INVALID", "created_at must be UTC")


def _bounded_text(value: Any, field: str, maximum: int) -> str:
    if not isinstance(value, str) or not value or len(value.encode("utf-8")) > maximum:
        raise CuffError("CUFF_LEDGER_INVALID", f"Record {field} must be bounded nonempty text")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise CuffError("CUFF_LEDGER_INVALID", f"Record {field} must not contain controls")
    return value


def _output_digest(stdout: Any, stderr: Any) -> str:
    digest = hashlib.sha256(b"cuff-output-1\0")
    for handle in (stdout, stderr):
        length = handle.seek(0, os.SEEK_END)
        digest.update(length.to_bytes(8, "big"))
        handle.seek(0)
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _retained_output(stdout: Any, stderr: Any) -> tuple[bytes, bytes]:
    stdout.seek(0)
    retained_stdout = stdout.read(MAX_RETAINED_OUTPUT)
    stderr.seek(0)
    retained_stderr = stderr.read(MAX_RETAINED_OUTPUT - len(retained_stdout))
    return retained_stdout, retained_stderr


def _content_baseline(content: bytes) -> LedgerBaseline:
    return LedgerBaseline(len(content), "sha256:" + hashlib.sha256(content).hexdigest())


def _replace(path: Path, content: bytes) -> None:
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile("wb", dir=path.parent, prefix=f".{path.stem}.", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
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


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


@contextmanager
def _lock(path: Path) -> Iterator[None]:
    lock = path.with_suffix(".lock")
    deadline = time.monotonic() + 5
    while True:
        try:
            lock.mkdir()
            break
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise CuffError("CUFF_LEDGER_BUSY", "Another writer holds the ledger lock")
            time.sleep(0.05)
    try:
        yield
    finally:
        lock.rmdir()
