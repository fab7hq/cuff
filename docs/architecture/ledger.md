---
title: Cuff Ledger Contract
type: architecture
status: accepted
owner: architecture
authority_for:
  - claim and evidence record shapes
  - command observation semantics
  - atomic append invariants
  - latest-claim readiness
---

# Cuff ledger contract

Cuff persists one canonical JSONL ledger per normalized work item under
`.fab7/cuff/records/<work-item>.jsonl`. Record generation remains `1` and the only
record types are `claim` and `evidence`.

## Claim

```json
{
  "v": 1,
  "id": "rec_...",
  "type": "claim",
  "work_item": "task-1",
  "created_at": "2026-08-13T00:00:00Z",
  "actor": "human:unknown",
  "summary": "Implementation complete",
  "subject": {
    "kind": "file",
    "ref": "src/app.py",
    "digest": "sha256:..."
  }
}
```

Subject identity is exactly `{kind, ref, digest}`. `file` and `tree` are
reserved for bounded Cuff-computed manifests. Other lowercase kinds describe
caller-declared immutable subjects. Actor precedence is explicit argument,
`CUFF_ACTOR`, then `human:unknown`; it is attribution, not authentication.

## Evidence

```json
{
  "v": 1,
  "id": "rec_...",
  "type": "evidence",
  "work_item": "task-1",
  "created_at": "2026-08-13T00:00:01Z",
  "actor": "human:unknown",
  "claim": "rec_...",
  "subject_digest": "sha256:...",
  "command_digest": "sha256:...",
  "exit_code": 0,
  "output_digest": "sha256:...",
  "provenance": {
    "kind": "git",
    "commit": "0123456789abcdef0123456789abcdef01234567"
  }
}
```

Evidence must link to an earlier claim in the same ledger and repeat that
claim's subject digest. Provenance has only the Git shape. Older digest-only
evidence is incompatible and cannot establish readiness; it is never upgraded,
rewritten, or silently accepted.

## Opaque command observation

`verify` and `seal` execute only the literal argv after `--`, with no shell.
Cuff bounds argument count and bytes, timeout, and retained output. It digests
the complete stdout and stderr streams even when retained output is truncated.
The command digest binds canonical argv, not a verifier type or registry name.

Cuff does not understand the command's domain. An extension may perform
semantic review first and supply a deterministic final integrity assertion;
Cuff observes that caller-selected process and its exit status only.

A stable exit or timeout is representable evidence. Exit zero is passing;
nonzero and timeout code `124` are failed evidence. Launch failure and
interruption append no evidence.

## Atomicity and concurrency

Each append validates the complete resulting ledger and replaces the file
atomically under a per-ledger lock. A baseline length and digest reject a stale
writer after command execution.

`seal` builds one claim and one linked evidence record in memory and appends
both in one replacement. Stable success, failure, and timeout append exactly
one pair. Subject drift, Git drift, invalid observation, launch failure,
interruption, and concurrent mutation append neither record. There is no third
seal record.

Ledgers reject unknown fields, unknown record types, duplicate JSON keys,
duplicate record IDs, bad links, ownership mismatch, symlinks, incomplete
lines, and noncanonical work items.

## Readiness

`check` is the only readiness implementation. Its closed JSON result is:

```json
{
  "ok": true,
  "errors": [],
  "work_item": "task-1",
  "latest_claim": {},
  "selected_evidence": {},
  "record_count": 2
}
```

It validates every ledger before selecting the latest claim in the requested
ledger. The failure classification is closed and ordered:

| Code | Meaning |
|---|---|
| `CUFF_CLAIM_MISSING` | No claim exists. |
| `CUFF_EVIDENCE_MISSING` | No evidence links to the latest claim. |
| `CUFF_EVIDENCE_FAILED` | Linked evidence exists, but none passed. |
| `CUFF_SUBJECT_STALE` | Passing evidence exists, but the subject changed or cannot be recomputed. |
| `CUFF_EVIDENCE_STALE` | Passing evidence exists, but none applies to the selected Git state. |

File and tree subjects are recomputed. Every check also enforces:

- exact Git worktree-root ownership and non-ledger cleanliness;
- evidence-commit ancestry of the selected head;
- no non-record change after the evidence commit;
- optional explicit base/head comparison or the local default; and
- append-only record changes.

`selected_evidence` is set only to the exact passing record that satisfies
subject and Git freshness. `ok` is true only when `errors` is empty and that
record is present. `latest_claim` and `selected_evidence` are validated records,
never raw JSONL lines. The JSONL ledger remains the complete bounded history.
