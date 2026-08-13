"""The single latest-claim readiness decision."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .errors import Fab7Error
from .ledger import RECORDS_DIR, normalize_work_item, read, read_all
from .subject import current_subject


def check(
    root: Path,
    work_item: str,
    *,
    base: str | None = None,
    head: str | None = None,
) -> dict[str, Any]:
    normalized = normalize_work_item(work_item)
    result: dict[str, Any] = {
        "ok": False,
        "errors": [],
        "work_item": normalized,
        "latest_claim": None,
        "selected_evidence": None,
        "record_count": 0,
    }
    try:
        read_all(root)
        records = read(root, normalized)
    except Fab7Error as exc:
        result["errors"].append(exc.to_dict())
        return result

    result["record_count"] = len(records)
    claims = [record for record in records if record["type"] == "claim"]
    claim = claims[-1] if claims else None
    result["latest_claim"] = claim

    git_context = _check_git_workspace(root, base, head, result["errors"])
    if claim is None:
        _fail(result["errors"], "FAB7_CLAIM_MISSING", "No completion claim exists", work_item=normalized)
        return result

    passing = [
        record
        for record in records
        if record["type"] == "evidence"
        and record["claim"] == claim["id"]
        and record["exit_code"] == 0
    ]
    for evidence in reversed(passing):
        if not _subject_fresh(root, claim):
            break
        if git_context is None or not _evidence_fresh(root, evidence, head, git_context):
            continue
        result["selected_evidence"] = evidence
        result["ok"] = not result["errors"]
        return result

    _fail(
        result["errors"],
        "FAB7_EVIDENCE_MISSING",
        "Latest claim has no fresh passing evidence",
        work_item=normalized,
        record_id=claim["id"],
    )
    return result


def _subject_fresh(root: Path, claim: dict[str, Any]) -> bool:
    try:
        return current_subject(root, claim["subject"]) == claim["subject"]
    except Fab7Error:
        return False


def _check_git_workspace(
    root: Path,
    base: str | None,
    head: str | None,
    errors: list[dict[str, Any]],
) -> tuple[Path, str] | None:
    from . import git

    try:
        workspace = root.resolve()
        repository = git.repo_root(workspace)
        if repository != workspace:
            raise Fab7Error(
                "FAB7_WORKSPACE_NOT_ROOT",
                "Fab7 workspace must be the Git worktree root",
                {"workspace": str(workspace), "repository": str(repository)},
            )
        dirty = [
            path for path in git.dirty_paths(repository)
            if not _is_record_path(repository, workspace, path)
        ]
        if dirty:
            _fail(
                errors,
                "FAB7_REPOSITORY_DIRTY",
                "Git readiness cannot evaluate uncommitted non-ledger changes",
                paths=dirty,
            )

        proposed_ref = head or "HEAD"
        proposed = git.head(repository, proposed_ref)
        comparison_base = _comparison_base(repository, base, proposed_ref)
        if comparison_base is not None:
            if not git.is_ancestor(comparison_base, proposed, repository):
                _fail(
                    errors,
                    "FAB7_GIT_ANCESTRY",
                    "The comparison base is not an ancestor of the selected head",
                    base=comparison_base,
                    head=proposed,
                )
            _check_append_only(repository, workspace, comparison_base, head, errors)
        return repository, proposed
    except Fab7Error as exc:
        errors.append(exc.to_dict())
        return None


def _comparison_base(repository: Path, base: str | None, proposed_ref: str) -> str | None:
    from . import git

    if base is not None:
        return git.head(repository, base)
    return git.default_base(repository, proposed_ref)


def _check_append_only(
    repository: Path,
    root: Path,
    base: str,
    head: str | None,
    errors: list[dict[str, Any]],
) -> None:
    from . import git

    pathspec = _record_prefix(repository, root)
    for status, path in git.diff_status(repository, base, head, pathspec):
        target = (
            git.show_file(repository, head, path)
            if head is not None
            else (repository / path).read_bytes()
            if (repository / path).exists()
            else None
        )
        if status == "A" and target is not None and target.endswith(b"\n"):
            continue
        if status == "M":
            original = git.show_file(repository, base, path)
            if (
                original is not None
                and target is not None
                and target.startswith(original)
                and target.endswith(b"\n")
            ):
                continue
        _fail(
            errors,
            "FAB7_LEDGER_REWRITE",
            "Ledger changes must only append complete lines",
            path=path,
            status=status,
        )


def _evidence_fresh(
    root: Path,
    evidence: dict[str, Any],
    head: str | None,
    git_context: tuple[Path, str],
) -> bool:
    from . import git

    repository, proposed = git_context
    try:
        evidence_commit = git.head(repository, evidence["provenance"]["commit"])
        if not git.is_ancestor(evidence_commit, proposed, repository):
            return False
        changed = git.changed_files(repository, evidence_commit, proposed if head is not None else None)
        return not any(not _is_record_path(repository, root, path) for path in changed)
    except Fab7Error:
        return False


def _record_prefix(repository: Path, root: Path) -> str:
    try:
        return (root / RECORDS_DIR).resolve().relative_to(repository.resolve()).as_posix()
    except ValueError as exc:
        raise Fab7Error("FAB7_NOT_A_REPOSITORY", "Fab7 workspace is outside the selected repository") from exc


def _is_record_path(repository: Path, root: Path, path: str) -> bool:
    prefix = _record_prefix(repository, root)
    normalized = path.replace("\\", "/")
    return normalized == prefix or normalized.startswith(prefix + "/")


def _fail(errors: list[dict[str, Any]], code: str, message: str, **context: Any) -> None:
    errors.append({"code": code, "message": message, **context})
