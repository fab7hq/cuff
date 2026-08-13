from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

import fab7.ledger as ledger_module
from fab7.errors import Fab7Error
from fab7.ledger import (
    append,
    append_many,
    baseline,
    create_claim,
    init,
    normalize_work_item,
    read,
    read_all,
    resolve_actor,
    seal,
    validate_record,
    verify,
)

from conftest import git


DIGEST = "sha256:" + "a" * 64
SUBJECT = {"kind": "denim-fabric", "ref": "fabric_123", "digest": DIGEST}


def _claim(root: Path, summary: str = "Done") -> dict[str, object]:
    return create_claim(root, "work-1", summary, SUBJECT, "agent:test")


def test_claim_and_git_evidence_use_the_exact_closed_schema(repo: Path) -> None:
    init(repo)
    claim = _claim(repo)
    append(repo, claim)
    observed = verify(
        repo,
        "work-1",
        str(claim["id"]),
        [sys.executable, "-c", "print('proved')"],
        actor="agent:test",
    )

    assert set(claim) == {
        "v", "id", "type", "work_item", "created_at", "actor", "summary", "subject"
    }
    assert set(observed.record) == {
        "v", "id", "type", "work_item", "created_at", "actor", "claim",
        "subject_digest", "command_digest", "exit_code", "output_digest", "provenance",
    }
    assert observed.record["subject_digest"] == claim["subject"]["digest"]  # type: ignore[index]
    assert observed.record["provenance"] == {
        "kind": "git",
        "commit": git(repo, "rev-parse", "HEAD"),
    }
    assert observed.stdout == b"proved\n"


def test_digest_only_evidence_is_rejected_by_the_closed_parser() -> None:
    evidence = {
        "v": 1,
        "id": "rec_" + "1" * 32,
        "type": "evidence",
        "work_item": "work-1",
        "created_at": "2026-08-13T00:00:00Z",
        "actor": "agent:test",
        "claim": "rec_" + "2" * 32,
        "subject_digest": DIGEST,
        "command_digest": DIGEST,
        "exit_code": 0,
        "output_digest": DIGEST,
        "provenance": {"kind": "digest"},
    }

    with pytest.raises(Fab7Error, match="FAB7_LEDGER_INVALID"):
        validate_record(evidence)


def test_append_many_is_ordered_atomic_and_rejects_changed_baseline(repo: Path) -> None:
    init(repo)
    original = baseline(repo, "work-1")
    first = _claim(repo, "First")
    second = _claim(repo, "Second")

    path, lines = append_many(repo, [first, second], expected=original)

    assert lines == [1, 2]
    assert [record["id"] for record in read(repo, "work-1")] == [first["id"], second["id"]]
    with pytest.raises(Fab7Error, match="FAB7_CONCURRENT_UPDATE"):
        append_many(repo, [_claim(repo, "Third")], expected=original)
    assert path.read_text().count("\n") == 2


def test_closed_parser_rejects_legacy_unknown_fields_and_bad_links(repo: Path) -> None:
    directory = init(repo)
    claim = _claim(repo)
    path = directory / "work-1.jsonl"
    path.write_text(json.dumps({**claim, "git_ref": "a" * 40}) + "\n")
    with pytest.raises(Fab7Error, match="archive or remove"):
        read(repo, "work-1")

    path.write_text(json.dumps({**claim, "unexpected": True}) + "\n")
    with pytest.raises(Fab7Error, match="FAB7_LEDGER_INVALID"):
        read(repo, "work-1")

    path.unlink()
    sealed = seal(
        repo,
        "work-1",
        "Done",
        SUBJECT,
        [sys.executable, "-c", "pass"],
        actor="agent:test",
    )
    path.write_text("\n".join(json.dumps(record) for record in (sealed.evidence, sealed.claim)) + "\n")
    with pytest.raises(Fab7Error, match="unknown claim"):
        read(repo, "work-1")


def test_invalid_json_duplicate_ids_and_foreign_work_items_fail_closed(repo: Path) -> None:
    directory = init(repo)
    broken = directory / "broken.jsonl"
    broken.write_text("{not json}\n")
    with pytest.raises(Fab7Error, match="FAB7_LEDGER_INVALID"):
        read_all(repo)
    broken.unlink()

    claim = _claim(repo)
    path = directory / "work-1.jsonl"
    path.write_text("\n".join(json.dumps(claim) for _ in range(2)) + "\n")
    with pytest.raises(Fab7Error, match="duplicate"):
        read(repo, "work-1")

    foreign = create_claim(repo, "work-2", "Done", SUBJECT, "agent:test")
    path.write_text(json.dumps(foreign) + "\n")
    with pytest.raises(Fab7Error, match="work item does not match its ledger"):
        read(repo, "work-1")


def test_actor_resolution_has_only_explicit_environment_unknown_precedence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FAB7_ACTOR", "agent:environment")
    monkeypatch.setenv("FAB7_PR_NUMBER", "41")

    assert resolve_actor("agent:explicit") == "agent:explicit"
    assert resolve_actor(None) == "agent:environment"
    monkeypatch.delenv("FAB7_ACTOR")
    assert resolve_actor(None) == "human:unknown"
    with pytest.raises(Fab7Error, match="bounded nonempty text"):
        resolve_actor("")
    with pytest.raises(Fab7Error, match="FAB7_WORK_ITEM_REQUIRED"):
        normalize_work_item(None)


def test_verify_records_passing_failure_and_timeout_observations(repo: Path) -> None:
    init(repo)
    claim = _claim(repo)
    append(repo, claim)

    passed = verify(repo, "work-1", str(claim["id"]), [sys.executable, "-c", "pass"])
    failed = verify(
        repo,
        "work-1",
        str(claim["id"]),
        [sys.executable, "-c", "raise SystemExit(7)"],
    )
    timed_out = verify(
        repo,
        "work-1",
        str(claim["id"]),
        [sys.executable, "-c", "import time; time.sleep(1)"],
        timeout=0.01,
    )

    assert [passed.record["exit_code"], failed.record["exit_code"], timed_out.record["exit_code"]] == [0, 7, 124]
    assert timed_out.timed_out
    assert [record["type"] for record in read(repo, "work-1")] == [
        "claim", "evidence", "evidence", "evidence"
    ]


def test_verify_bounds_retained_output_and_executes_literal_argv(
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    init(repo)
    claim = _claim(repo)
    append(repo, claim)
    monkeypatch.setattr(ledger_module, "MAX_RETAINED_OUTPUT", 16)

    first = verify(
        repo,
        "work-1",
        str(claim["id"]),
        [sys.executable, "-c", "print('a' * 16 + 'b', end='')"],
    )
    second = verify(
        repo,
        "work-1",
        str(claim["id"]),
        [sys.executable, "-c", "print('a' * 16 + 'c', end='')"],
    )
    literal = "$(touch injected)"
    observed = verify(
        repo,
        "work-1",
        str(claim["id"]),
        [sys.executable, "-c", "import sys; print(sys.argv[1])", literal],
    )

    assert first.stdout == second.stdout == b"a" * 16
    assert first.record["output_digest"] != second.record["output_digest"]
    monkeypatch.setattr(ledger_module, "MAX_RETAINED_OUTPUT", 1024 * 1024)
    observed = verify(
        repo,
        "work-1",
        str(claim["id"]),
        [sys.executable, "-c", "import sys; print(sys.argv[1])", literal],
    )
    assert observed.stdout == (literal + "\n").encode()
    assert not (repo / "injected").exists()


def test_git_verification_rejects_dirty_pre_and_post_state(repo: Path) -> None:
    init(repo)
    claim = _claim(repo)
    append(repo, claim)
    (repo / "app.py").write_text("VALUE = 2\n")
    with pytest.raises(Fab7Error, match="FAB7_REPOSITORY_DIRTY"):
        verify(repo, "work-1", str(claim["id"]), [sys.executable, "-c", "pass"])
    (repo / "app.py").write_text("VALUE = 1\n")

    with pytest.raises(Fab7Error, match="FAB7_REPOSITORY_DIRTY"):
        verify(
            repo,
            "work-1",
            str(claim["id"]),
            [sys.executable, "-c", "from pathlib import Path; Path('new').write_text('dirty')"],
        )
    assert [record["type"] for record in read(repo, "work-1")] == ["claim"]


def test_git_verification_rejects_changed_head(repo: Path) -> None:
    init(repo)
    claim = _claim(repo)
    append(repo, claim)

    with pytest.raises(Fab7Error, match="FAB7_REPOSITORY_CHANGED"):
        verify(
            repo,
            "work-1",
            str(claim["id"]),
            [
                sys.executable,
                "-c",
                "from pathlib import Path; import subprocess; "
                "Path('new.txt').write_text('new'); "
                "subprocess.run(['git','add','new.txt'],check=True); "
                "subprocess.run(['git','commit','-qm','changed head'],check=True)",
            ],
        )
    assert [record["type"] for record in read(repo, "work-1")] == ["claim"]


def test_verify_drift_launch_failure_interruption_and_concurrency_append_no_evidence(
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    init(repo)
    from fab7.subject import filesystem_subject

    real_observe = ledger_module.observe_command
    subject = filesystem_subject(repo, repo / "app.py")
    claim = create_claim(repo, "work-1", "Done", subject, "agent:test")
    append(repo, claim)
    with pytest.raises(Fab7Error, match="FAB7_SUBJECT_CHANGED"):
        verify(
            repo,
            "work-1",
            str(claim["id"]),
            [sys.executable, "-c", "from pathlib import Path; Path('app.py').unlink()"],
        )
    (repo / "app.py").write_text("VALUE = 1\n")
    assert [record["type"] for record in read(repo, "work-1")] == ["claim"]

    with pytest.raises(Fab7Error, match="FAB7_COMMAND_FAILED"):
        verify(repo, "work-1", str(claim["id"]), ["fab7-command-that-does-not-exist"])
    assert [record["type"] for record in read(repo, "work-1")] == ["claim"]

    monkeypatch.setattr(
        ledger_module,
        "observe_command",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(KeyboardInterrupt()),
    )
    with pytest.raises(KeyboardInterrupt):
        verify(repo, "work-1", str(claim["id"]), [sys.executable, "-c", "pass"])
    assert [record["type"] for record in read(repo, "work-1")] == ["claim"]

    monkeypatch.setattr(ledger_module, "observe_command", real_observe)

    def concurrent(*args: object, **kwargs: object):
        observation = real_observe(*args, **kwargs)
        append(repo, _claim(repo, "Concurrent"))
        return observation

    monkeypatch.setattr(ledger_module, "observe_command", concurrent)
    with pytest.raises(Fab7Error, match="FAB7_CONCURRENT_UPDATE"):
        verify(repo, "work-1", str(claim["id"]), [sys.executable, "-c", "pass"])
    assert [record["type"] for record in read(repo, "work-1")] == ["claim", "claim"]


def test_seal_appends_one_linked_pair_for_success_failure_and_timeout(repo: Path) -> None:
    init(repo)
    success = seal(
        repo, "work-1", "Done", SUBJECT, [sys.executable, "-c", "print('ok')"], actor="agent:test"
    )
    failure = seal(
        repo, "work-1", "Failed", SUBJECT, [sys.executable, "-c", "raise SystemExit(9)"]
    )
    timeout = seal(
        repo,
        "work-1",
        "Timed out",
        SUBJECT,
        [sys.executable, "-c", "import time; time.sleep(1)"],
        timeout=0.01,
    )

    assert [success.evidence["exit_code"], failure.evidence["exit_code"], timeout.evidence["exit_code"]] == [0, 9, 124]
    assert timeout.timed_out
    records = read(repo, "work-1")
    assert [record["type"] for record in records] == ["claim", "evidence"] * 3
    assert all(record["type"] != "seal" for record in records)


def test_seal_drift_launch_failure_and_interruption_append_nothing(
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    init(repo)
    from fab7.subject import filesystem_subject

    subject = filesystem_subject(repo, repo / "app.py")
    with pytest.raises(Fab7Error, match="FAB7_SUBJECT_CHANGED"):
        seal(
            repo,
            "work-1",
            "Done",
            subject,
            [sys.executable, "-c", "from pathlib import Path; Path('app.py').write_text('after')"],
        )
    (repo / "app.py").write_text("VALUE = 1\n")
    assert read(repo, "work-1") == []


def test_seal_git_dirty_and_head_drift_append_nothing(repo: Path) -> None:
    init(repo)
    with pytest.raises(Fab7Error, match="FAB7_REPOSITORY_DIRTY"):
        seal(
            repo,
            "work-1",
            "Done",
            SUBJECT,
            [sys.executable, "-c", "from pathlib import Path; Path('dirty').write_text('x')"],
        )
    (repo / "dirty").unlink()
    assert read(repo, "work-1") == []

    with pytest.raises(Fab7Error, match="FAB7_REPOSITORY_CHANGED"):
        seal(
            repo,
            "work-1",
            "Done",
            SUBJECT,
            [
                sys.executable,
                "-c",
                "from pathlib import Path; import subprocess; "
                "Path('new.txt').write_text('new'); "
                "subprocess.run(['git','add','new.txt'],check=True); "
                "subprocess.run(['git','commit','-qm','changed head'],check=True)",
            ],
        )
    assert read(repo, "work-1") == []


def test_seal_launch_failure_and_interruption_append_nothing(
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    init(repo)

    with pytest.raises(Fab7Error, match="FAB7_COMMAND_FAILED"):
        seal(repo, "work-1", "Done", SUBJECT, ["fab7-command-that-does-not-exist"])
    assert read(repo, "work-1") == []

    monkeypatch.setattr(
        ledger_module,
        "observe_command",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(KeyboardInterrupt()),
    )
    with pytest.raises(KeyboardInterrupt):
        seal(repo, "work-1", "Done", SUBJECT, [sys.executable, "-c", "pass"])
    assert read(repo, "work-1") == []


def test_seal_rejects_concurrent_append_and_preserves_other_writer(
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    init(repo)
    real_observe = ledger_module.observe_command

    def concurrent(*args: object, **kwargs: object):
        observation = real_observe(*args, **kwargs)
        append(repo, _claim(repo, "Concurrent"))
        return observation

    monkeypatch.setattr(ledger_module, "observe_command", concurrent)
    with pytest.raises(Fab7Error, match="FAB7_CONCURRENT_UPDATE"):
        seal(repo, "work-1", "Done", SUBJECT, [sys.executable, "-c", "pass"])

    records = read(repo, "work-1")
    assert len(records) == 1
    assert records[0]["summary"] == "Concurrent"


def test_ledger_symlinks_are_rejected(repo: Path, tmp_path: Path) -> None:
    directory = init(repo)
    outside = tmp_path / "outside.jsonl"
    outside.write_text("")
    (directory / "work-1.jsonl").symlink_to(outside)

    with pytest.raises(Fab7Error, match="FAB7_PATH_INVALID"):
        read(repo, "work-1")
