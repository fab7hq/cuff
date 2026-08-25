"""Cuff's intentionally small command line surface."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .errors import CuffError
from .gate import check
from .ledger import append, create_claim, normalize_work_item, seal, verify
from .subject import declared_subject, filesystem_subject
from .workspace import find_workspace, initialize_workspace


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cuff")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)

    initialize = commands.add_parser("init", help="initialize a Cuff workspace")
    initialize.add_argument("--workspace", type=Path)
    initialize.add_argument("--json", action="store_true")

    claim = commands.add_parser("claim", help="record a completion claim")
    claim.add_argument("--workspace", type=Path)
    claim.add_argument("--work-item", required=True)
    claim.add_argument("--summary", required=True)
    _add_subject_arguments(claim)
    claim.add_argument("--actor")
    claim.add_argument("--json", action="store_true")

    verification = commands.add_parser("verify", help="run a command and record its result")
    verification.add_argument("--workspace", type=Path)
    verification.add_argument("--work-item", required=True)
    verification.add_argument("--claim", required=True)
    verification.add_argument("--timeout", type=float, default=300)
    verification.add_argument("--actor")
    verification.add_argument("--json", action="store_true")
    verification.add_argument("verification_command", nargs=argparse.REMAINDER)

    sealing = commands.add_parser("seal", help="atomically record a claim and executed evidence")
    sealing.add_argument("--workspace", type=Path)
    sealing.add_argument("--work-item", required=True)
    sealing.add_argument("--summary", required=True)
    _add_subject_arguments(sealing)
    sealing.add_argument("--timeout", type=float, default=300)
    sealing.add_argument("--actor")
    sealing.add_argument("--json", action="store_true")
    sealing.add_argument("verification_command", nargs=argparse.REMAINDER)

    readiness = commands.add_parser("check", help="require fresh evidence for the latest claim")
    readiness.add_argument("--workspace", type=Path)
    readiness.add_argument("--work-item", required=True)
    readiness.add_argument("--base")
    readiness.add_argument("--head")
    readiness.add_argument("--include-latest-record", action="store_true")
    readiness.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        if args.command == "init":
            data = initialize_workspace(args.workspace)
            return _finish(args, data, f"Cuff project: {data['status']}")

        root = find_workspace(args.workspace)
        if args.command == "claim":
            subject = _subject(root, args)
            record = create_claim(root, args.work_item, args.summary, subject, args.actor)
            path, line = append(root, record)
            return _finish(
                args,
                {"ok": True, "record": record, "path": str(path), "line": line},
                f"Claim {record['id']} recorded for {record['work_item']}",
            )
        if args.command == "verify":
            observed = verify(
                root,
                args.work_item,
                args.claim,
                _verification_command(args.verification_command),
                timeout=args.timeout,
                actor=args.actor,
            )
            data = {
                "ok": observed.record["exit_code"] == 0,
                "record": observed.record,
                "path": str(observed.path),
                "line": observed.line,
                "timed_out": observed.timed_out,
            }
            return _finish_observation(
                args,
                data,
                observed.stdout,
                observed.stderr,
                f"Evidence {observed.record['id']} recorded: exit {observed.record['exit_code']}",
            )
        if args.command == "seal":
            sealed = seal(
                root,
                args.work_item,
                args.summary,
                _subject(root, args),
                _verification_command(args.verification_command),
                timeout=args.timeout,
                actor=args.actor,
            )
            data = {
                "ok": sealed.evidence["exit_code"] == 0,
                "claim": sealed.claim,
                "evidence": sealed.evidence,
                "path": str(sealed.path),
                "lines": sealed.lines,
                "timed_out": sealed.timed_out,
            }
            return _finish_observation(
                args,
                data,
                sealed.stdout,
                sealed.stderr,
                f"Claim {sealed.claim['id']} and evidence {sealed.evidence['id']} recorded: "
                f"exit {sealed.evidence['exit_code']}",
            )
        if args.command == "check":
            data = check(
                root,
                args.work_item,
                base=args.base,
                head=args.head,
                include_latest_record=args.include_latest_record,
            )
            return _finish_result(args, data, "Cuff readiness")
        parser.error("unknown command")
    except CuffError as exc:
        return _finish_error(args, exc)
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        error = {"code": "CUFF_UNEXPECTED", "message": f"{type(exc).__name__}: {exc}"}
        if getattr(args, "command", None) == "check":
            data = _check_error(args, error)
        else:
            data = {"ok": False, "errors": [error]}
        if getattr(args, "json", False):
            print(json.dumps(data, sort_keys=True, indent=2))
        else:
            print(f"{error['code']}: {error['message']}", file=sys.stderr)
        return 3
    return 2


def _add_subject_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--subject-kind")
    parser.add_argument("--subject-ref")
    parser.add_argument("--subject-digest")
    parser.add_argument("--subject-path", type=Path)


def _subject(root: Path, args: argparse.Namespace) -> dict[str, str]:
    declared = (args.subject_kind, args.subject_ref, args.subject_digest)
    if args.subject_path is not None:
        if any(value is not None for value in declared):
            raise CuffError(
                "CUFF_SUBJECT_INVALID",
                "Choose either --subject-path or all declared subject arguments",
            )
        return filesystem_subject(root, args.subject_path)
    if any(value is None for value in declared):
        raise CuffError(
            "CUFF_SUBJECT_REQUIRED",
            "Pass --subject-path or --subject-kind, --subject-ref, and --subject-digest",
        )
    return declared_subject(*declared)


def _verification_command(command: list[str]) -> list[str]:
    return command[1:] if command[:1] == ["--"] else command


def _finish(args: argparse.Namespace, data: dict[str, Any], message: str) -> int:
    if args.json:
        print(json.dumps(data, sort_keys=True, indent=2))
    else:
        print(message)
    return 0


def _finish_observation(
    args: argparse.Namespace,
    data: dict[str, Any],
    stdout: bytes,
    stderr: bytes,
    message: str,
) -> int:
    if args.json:
        print(json.dumps(data, sort_keys=True, indent=2))
    else:
        _replay(stdout, sys.stdout)
        _replay(stderr, sys.stderr)
        print(message)
    return 0 if data["ok"] else 1


def _finish_result(args: argparse.Namespace, data: dict[str, Any], label: str) -> int:
    if args.json:
        print(json.dumps(data, sort_keys=True, indent=2))
    else:
        print(f"{label}: {'PASS' if data['ok'] else 'FAIL'}")
        for error in data["errors"]:
            print(f"ERROR {error['code']}: {error['message']}")
    return 0 if data["ok"] else 1


def _finish_error(args: argparse.Namespace, error: CuffError) -> int:
    data = (
        _check_error(args, error.to_dict())
        if getattr(args, "command", None) == "check"
        else {"ok": False, "errors": [error.to_dict()]}
    )
    if getattr(args, "json", False):
        print(json.dumps(data, sort_keys=True, indent=2))
    else:
        print(str(error), file=sys.stderr)
    return 1


def _check_error(args: argparse.Namespace, error: dict[str, Any]) -> dict[str, Any]:
    work_item = getattr(args, "work_item", None)
    try:
        work_item = normalize_work_item(work_item)
    except CuffError:
        pass
    result = {
        "ok": False,
        "errors": [error],
        "work_item": work_item,
        "latest_claim": None,
        "selected_evidence": None,
        "record_count": 0,
    }
    if getattr(args, "include_latest_record", False):
        result["latest_record"] = None
    return result


def _replay(content: bytes, stream: Any) -> None:
    if content:
        stream.write(content.decode(errors="replace"))
        if not content.endswith(b"\n"):
            stream.write("\n")


if __name__ == "__main__":
    raise SystemExit(main())
