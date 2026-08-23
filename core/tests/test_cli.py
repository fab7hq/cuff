from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import pytest

import cuff.cli as cli
from cuff import __version__
from cuff.cli import main

from conftest import git


DIGEST = "sha256:" + "a" * 64


def _subject_args() -> list[str]:
    return [
        "--subject-kind", "denim-fabric", "--subject-ref", "fabric_123",
        "--subject-digest", DIGEST,
    ]


def _initialize_and_commit(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["init", "--workspace", str(repo), "--json"]) == 0
    capsys.readouterr()
    git(repo, "add", ".fab7/cuff/project.json")
    git(repo, "commit", "-qm", "initialize cuff")


def test_command_surface_is_exactly_the_five_proof_commands() -> None:
    parser = cli.build_parser()
    subparsers = next(
        action for action in parser._actions if isinstance(action, argparse._SubParsersAction)
    )

    assert set(subparsers.choices) == {"init", "claim", "verify", "seal", "check"}


@pytest.mark.parametrize("command", ["install", "ext", "audit", "doctor", "ci-check"])
def test_removed_top_level_commands_are_rejected(command: str) -> None:
    with pytest.raises(SystemExit) as raised:
        cli.build_parser().parse_args([command])
    assert raised.value.code == 2


@pytest.mark.parametrize(
    "argv",
    [
        ["claim", "--summary", "Done", *_subject_args()],
        ["verify", "--claim", "rec_" + "1" * 32, "--", "true"],
        ["seal", "--summary", "Done", *_subject_args(), "--", "true"],
        ["check"],
    ],
)
def test_every_work_item_command_requires_explicit_identity(argv: list[str]) -> None:
    with pytest.raises(SystemExit) as raised:
        cli.build_parser().parse_args(argv)
    assert raised.value.code == 2


@pytest.mark.parametrize(
    "argv",
    [
        ["init", "--provenance", "git"],
        ["verify", "--work-item", "work-1", "--claim", "rec_" + "1" * 32,
         "--provenance", "git", "--", "true"],
        ["seal", "--work-item", "work-1", "--summary", "Done", *_subject_args(),
         "--provenance", "git", "--", "true"],
        ["check", "--work-item", "work-1", "--require-git"],
    ],
)
def test_provenance_selectors_are_absent(argv: list[str]) -> None:
    with pytest.raises(SystemExit) as raised:
        cli.build_parser().parse_args(argv)
    assert raised.value.code == 2


def test_denim_style_json_subprocess_contract_is_git_anchored(
    repo: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["init", "--json"]) == 0
    initialized = json.loads(capsys.readouterr().out)
    assert initialized == {
        "ok": True,
        "marker": {"schema": 1},
        "status": "initialized",
        "workspace": str(repo),
    }
    git(repo, "add", ".fab7/cuff/project.json")
    git(repo, "commit", "-qm", "initialize cuff")

    assert main([
        "claim", "--work-item", "work-1", "--summary", "Done", *_subject_args(), "--json"
    ]) == 0
    claim = json.loads(capsys.readouterr().out)["record"]
    assert claim["subject"] == {
        "kind": "denim-fabric",
        "ref": "fabric_123",
        "digest": DIGEST,
    }

    assert main([
        "verify", "--work-item", "work-1", "--claim", claim["id"], "--json", "--",
        sys.executable, "-c", "print('verified')",
    ]) == 0
    evidence = json.loads(capsys.readouterr().out)["record"]
    assert evidence["exit_code"] == 0
    assert evidence["claim"] == claim["id"]
    assert evidence["subject_digest"] == DIGEST
    assert evidence["provenance"] == {
        "kind": "git",
        "commit": git(repo, "rev-parse", "HEAD"),
    }

    assert main(["check", "--work-item", "work-1", "--json"]) == 0
    checked = json.loads(capsys.readouterr().out)
    assert checked["ok"]
    assert checked["latest_claim"] == claim
    assert checked["selected_evidence"] == evidence


def test_plain_verify_replays_command_output(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _initialize_and_commit(repo, capsys)
    assert main([
        "claim", "--work-item", "work-1", "--summary", "Done", *_subject_args(), "--json"
    ]) == 0
    claim = json.loads(capsys.readouterr().out)["record"]

    assert main([
        "verify", "--work-item", "work-1", "--claim", claim["id"], "--",
        sys.executable, "-c", "import sys; print('visible'); print('warning', file=sys.stderr)",
    ]) == 0
    captured = capsys.readouterr()
    assert "visible" in captured.out
    assert "Evidence " in captured.out
    assert "warning" in captured.err


def test_atomic_seal_json_returns_both_records_and_failure_status(
    repo: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _initialize_and_commit(repo, capsys)

    assert main([
        "seal", "--work-item", "work-1", "--summary", "Done", *_subject_args(), "--json", "--",
        sys.executable, "-c", "raise SystemExit(7)",
    ]) == 1
    data = json.loads(capsys.readouterr().out)
    assert not data["ok"]
    assert data["claim"]["type"] == "claim"
    assert data["evidence"]["type"] == "evidence"
    assert data["evidence"]["claim"] == data["claim"]["id"]
    assert data["evidence"]["exit_code"] == 7


def test_subdirectory_discovers_the_root_project(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _initialize_and_commit(repo, capsys)
    child = repo / "nested" / "child"
    child.mkdir(parents=True)
    original = Path.cwd()
    try:
        os.chdir(child)
        assert main([
            "claim", "--work-item", "work-1", "--summary", "Done", *_subject_args(), "--json"
        ]) == 0
    finally:
        os.chdir(original)
    assert json.loads(capsys.readouterr().out)["record"]["work_item"] == "work-1"


def test_json_errors_are_one_parseable_stdout_document(
    repo: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _initialize_and_commit(repo, capsys)
    assert main([
        "claim", "--work-item", "work-1", "--summary", "Done", *_subject_args(), "--json"
    ]) == 0
    claim = json.loads(capsys.readouterr().out)["record"]

    assert main([
        "verify", "--work-item", "work-1", "--claim", claim["id"], "--json"
    ]) == 1
    captured = capsys.readouterr()
    assert captured.err == ""
    assert json.loads(captured.out)["errors"][0]["code"] == "CUFF_COMMAND_REQUIRED"


def test_missing_setup_and_non_git_init_return_stable_errors(
    repo: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main([
        "check", "--workspace", str(repo), "--work-item", "work-1", "--json"
    ]) == 1
    assert json.loads(capsys.readouterr().out)["errors"][0]["code"] == "CUFF_PROJECT_NOT_INITIALIZED"

    outside = repo.parent / f"{repo.name}-outside"
    outside.mkdir()
    assert main(["init", "--workspace", str(outside), "--json"]) == 1
    assert json.loads(capsys.readouterr().out)["errors"][0]["code"] == "CUFF_NOT_A_REPOSITORY"


def test_interruption_and_unexpected_failure_have_distinct_exit_codes(
    repo: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _initialize_and_commit(repo, capsys)
    monkeypatch.setattr(cli, "check", lambda *_args, **_kwargs: (_ for _ in ()).throw(KeyboardInterrupt()))
    assert main(["check", "--work-item", "work-1", "--json"]) == 130
    assert capsys.readouterr().out == ""

    monkeypatch.setattr(cli, "check", lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError("boom")))
    assert main(["check", "--work-item", "work-1", "--json"]) == 3
    data = json.loads(capsys.readouterr().out)
    assert data["errors"] == [{"code": "CUFF_UNEXPECTED", "message": "ValueError: boom"}]


def test_version_flag_reports_package_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as raised:
        cli.build_parser().parse_args(["--version"])
    assert raised.value.code == 0
    assert capsys.readouterr().out.strip() == __version__
