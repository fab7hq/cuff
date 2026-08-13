from __future__ import annotations

import json
import sys
from pathlib import Path

from fab7.gate import check
from fab7.ledger import append, create_claim, init, record_path, seal, verify
from fab7.subject import declared_subject, filesystem_subject

from conftest import git


DIGEST = "sha256:" + "a" * 64
OPAQUE = declared_subject("denim-fabric", "fabric_123", DIGEST)


def _claim(root: Path, subject: dict[str, str] = OPAQUE) -> dict[str, object]:
    init(root)
    claim = create_claim(root, "work-1", "Implementation complete", subject, "agent:test")
    append(root, claim)
    return claim


def _verify(root: Path, claim: dict[str, object]) -> None:
    verify(
        root,
        "work-1",
        str(claim["id"]),
        [sys.executable, "-c", "print('ok')"],
        actor="agent:test",
    )


def _codes(result: dict[str, object]) -> list[str]:
    return [error["code"] for error in result["errors"]]  # type: ignore[index]


def test_gate_has_one_closed_projection_and_requires_latest_claim(repo: Path) -> None:
    init(repo)
    empty = check(repo, "work-1")
    assert set(empty) == {
        "ok", "errors", "work_item", "latest_claim", "selected_evidence", "record_count"
    }
    assert _codes(empty) == ["FAB7_CLAIM_MISSING"]
    assert empty["latest_claim"] is None
    assert empty["selected_evidence"] is None

    claim = _claim(repo)
    assert _codes(check(repo, "work-1")) == ["FAB7_EVIDENCE_MISSING"]
    _verify(repo, claim)
    passed = check(repo, "work-1")
    assert passed["ok"]
    assert passed["latest_claim"] == claim
    assert passed["selected_evidence"]["claim"] == claim["id"]  # type: ignore[index]
    assert passed["record_count"] == 2

    latest = _claim(repo)
    assert latest["id"] != claim["id"]
    assert _codes(check(repo, "work-1")) == ["FAB7_EVIDENCE_MISSING"]


def test_failed_evidence_does_not_back_a_claim(repo: Path) -> None:
    claim = _claim(repo)
    verify(
        repo,
        "work-1",
        str(claim["id"]),
        [sys.executable, "-c", "raise SystemExit(1)"],
        actor="agent:test",
    )
    assert _codes(check(repo, "work-1")) == ["FAB7_EVIDENCE_MISSING"]


def test_every_nonledger_mutation_invalidates_git_readiness_for_opaque_subject(repo: Path) -> None:
    claim = _claim(repo)
    _verify(repo, claim)
    (repo / "unrelated.txt").write_text("later")

    result = check(repo, "work-1")

    assert "FAB7_REPOSITORY_DIRTY" in _codes(result)
    assert not result["ok"]


def test_filesystem_subject_mutation_makes_evidence_stale(repo: Path) -> None:
    claim = _claim(repo, filesystem_subject(repo, repo / "app.py"))
    _verify(repo, claim)
    assert check(repo, "work-1")["ok"]

    (repo / "app.py").write_text("VALUE = 2\n")
    result = check(repo, "work-1")
    assert "FAB7_REPOSITORY_DIRTY" in _codes(result)
    assert "FAB7_EVIDENCE_MISSING" in _codes(result)


def test_committed_implementation_change_stales_git_evidence(repo: Path) -> None:
    claim = _claim(repo, filesystem_subject(repo, repo / "app.py"))
    _verify(repo, claim)
    git(repo, "add", ".fab7")
    git(repo, "commit", "-qm", "record proof")
    assert check(repo, "work-1")["ok"]

    (repo / "app.py").write_text("VALUE = 2\n")
    git(repo, "add", "app.py")
    git(repo, "commit", "-qm", "change implementation")
    assert "FAB7_EVIDENCE_MISSING" in _codes(check(repo, "work-1"))


def test_git_ledger_rewrite_is_rejected(repo: Path) -> None:
    claim = _claim(repo, filesystem_subject(repo, repo / "app.py"))
    _verify(repo, claim)
    git(repo, "add", ".fab7")
    git(repo, "commit", "-qm", "record proof")
    baseline_ref = git(repo, "rev-parse", "HEAD")

    path = record_path(repo, "work-1")
    rows = path.read_text().splitlines()
    record = json.loads(rows[0])
    record["summary"] = "rewritten"
    rows[0] = json.dumps(record, sort_keys=True, separators=(",", ":"))
    path.write_text("\n".join(rows) + "\n")
    git(repo, "add", ".fab7/records")
    git(repo, "commit", "-qm", "rewrite proof")

    result = check(repo, "work-1", base=baseline_ref, head="HEAD")
    assert "FAB7_LEDGER_REWRITE" in _codes(result)


def test_explicit_base_and_head_apply_ancestry_and_changed_path_checks(repo: Path) -> None:
    base = git(repo, "rev-parse", "HEAD")
    init(repo)
    sealed = seal(
        repo,
        "work-1",
        "Done",
        OPAQUE,
        [sys.executable, "-c", "pass"],
        actor="agent:test",
    )
    git(repo, "add", ".fab7")
    git(repo, "commit", "-qm", "proof")
    proof_head = git(repo, "rev-parse", "HEAD")

    result = check(repo, "work-1", base=base, head=proof_head)

    assert result["ok"]
    assert result["selected_evidence"] == sealed.evidence


def test_explicit_nonancestor_base_fails_readiness(repo: Path) -> None:
    init(repo)
    seal(
        repo,
        "work-1",
        "Done",
        OPAQUE,
        [sys.executable, "-c", "pass"],
        actor="agent:test",
    )
    git(repo, "add", ".fab7")
    git(repo, "commit", "-qm", "proof")
    unrelated = git(repo, "commit-tree", "HEAD^{tree}", "-m", "unrelated root")

    result = check(repo, "work-1", base=unrelated, head="HEAD")

    assert "FAB7_GIT_ANCESTRY" in _codes(result)
    assert not result["ok"]
