---
title: Cuff Architecture Overview
type: architecture
status: accepted
owner: architecture
last_updated: 2026-08-13
authority_for:
  - proof-core module ownership
  - public CLI flow
  - Git workspace boundary
  - extension composition boundary
---

# Cuff architecture overview

Cuff records a claim for one exact subject, observes one literal verifier argv,
and decides whether the latest claim retains fresh passing evidence.

## Product boundary

Cuff owns:

- one minimal marker and append-only record directory at a Git worktree root;
- declared or Cuff-computed exact subject identity;
- closed claim and evidence records;
- bounded command observation without a shell;
- Git commit provenance, cleanliness, ancestry, changed-path, and ledger rules;
- stable human and JSON CLI output.

Cuff does not own extension discovery, packages, catalogs, host installation,
Python installation, native builds, verifier selection, domain semantics,
plans, approvals, releases, deployments, or remote state.

## Modules

| Module | Responsibility |
|---|---|
| `cli.py` | five-command parser, output contracts, and exit status |
| `workspace.py` | root-only initialization, exact marker validation, and bounded discovery |
| `subject.py` | closed subject validation and bounded file/tree manifests |
| `ledger.py` | records, parsing, command observation, locks, and atomic append |
| `gate.py` | the single latest-claim readiness decision and JSON projection |
| `git.py` | minimal worktree, commit, ancestry, diff, and history operations |
| `errors.py` | one stable `CuffError` envelope |

Importing `cuff.cli` imports only these proof-core modules.

## Public flow

```text
caller
  -> cuff init at exact existing Git root
  -> cuff claim + cuff verify, or one atomic cuff seal
       -> capture exact subject and HEAD
       -> execute only caller-supplied argv
       -> reject subject, Git, or ledger drift
       -> append closed evidence
  -> cuff check
       -> parse every ledger
       -> choose latest claim and linked passing evidence
       -> enforce subject and Git freshness
       -> return one PASS/FAIL projection
```

The public parser exposes exactly:

```text
cuff init [--workspace PATH] [--json]
cuff claim --work-item ID --summary TEXT SUBJECT [--workspace PATH] [--actor ACTOR] [--json]
cuff verify --work-item ID --claim RECORD_ID [--workspace PATH] [--timeout SECONDS] [--actor ACTOR] [--json] -- COMMAND [ARGS...]
cuff seal --work-item ID --summary TEXT SUBJECT [--workspace PATH] [--timeout SECONDS] [--actor ACTOR] [--json] -- COMMAND [ARGS...]
cuff check --work-item ID [--workspace PATH] [--base REF] [--head REF] [--json]
```

`SUBJECT` is either `--subject-path PATH` or all of `--subject-kind KIND`,
`--subject-ref REF`, and `--subject-digest DIGEST`.

## Workspace and Git boundary

The workspace is exactly the containing Git worktree root. `init` selects only
the explicit directory or current directory; it never searches for or switches
to another repository. Later commands perform a bounded nearest-marker walk,
then require that marker to be at the worktree root.

The marker value is `{"schema":1}`. Package version and executable identity do
not belong to workspace identity. Older markers fail without rewrite or
migration. Git is never mutated by Cuff.

Every observation is anchored to the stable pre-execution `HEAD`. Verification
and sealing allow only record paths to differ from `HEAD`; `check` always
enforces non-ledger cleanliness, evidence ancestry, changed implementation,
and append-only ledger history.

## Extension composition

An extension owns domain verification and immutable subject construction. It
then invokes `cuff seal --json` or the split claim/verify path and validates the
returned identifiers and digest. Cuff never imports the extension, discovers
its state, selects its verifier, or interprets its output.

```text
extension domain checks -> exact subject -> public cuff executable -> JSON receipt
```

The repository's Claude Code and Codex directories are small static guidance
assets. Host-native plugin managers own their lifecycle; the Python package
does not contain or install them.
