# Cuff operations runbook

This runbook covers the smallest complete local path: install the Python tool,
initialize one existing Git worktree, record proof for an exact subject, and
check readiness.

## 1. Prerequisites

Confirm Git, Python, and uv are available:

```bash
git --version
python3 --version
uv self version
```

Cuff requires Python 3.11 or newer. uv `0.11.32` is the tested recommendation,
not a runtime equality gate. The selected workspace must already be the exact
root of one Git worktree.

## 2. Install Cuff

Install a released package with uv:

```bash
uv tool install cuff-cli==0.2.1
command -v cuff
cuff --version
```

For a reviewed checkout, use an editable tool installation while developing:

```bash
uv tool install --editable .
```

uv owns the environment, executable selection, and upgrades. Cuff does not
maintain a separate home, Python runtime, native builder, or installer.

## 3. Initialize the Git root

```bash
cd /path/to/git-worktree-root
cuff init --json
git status --short
git add .fab7/cuff/project.json
git commit -m "Initialize Cuff"
```

Initialization creates only:

```text
.fab7/cuff/
├── project.json    # {"schema":1}
└── records/        # one canonical JSONL ledger per work item
```

It is idempotent for the exact marker and preserves valid ledgers. It fails
outside Git, in a nested directory, for unsafe symlinks, and for malformed or
older markers. To cut over an old marker, archive or remove only that marker
explicitly and rerun `cuff init`; Cuff performs no migration.

## 4. Seal the first proof

Keep the non-ledger worktree clean, then run one caller-selected deterministic
verifier:

```bash
cuff seal \
  --work-item onboarding \
  --summary "Onboarding complete" \
  --subject-path README.md \
  --json \
  -- python -m pytest
```

`seal` captures the subject and `HEAD`, executes the literal argv without a
shell, checks subject and Git stability, then atomically appends one claim and
one linked evidence record. Exit zero returns success. A stable nonzero exit or
timeout appends a failed pair. Launch failure, interruption, drift, or a
concurrent ledger update appends neither record.

For an immutable external subject, pass all three declared fields instead:

```bash
cuff seal \
  --work-item release-artifact \
  --summary "Release artifact verified" \
  --subject-kind release-artifact \
  --subject-ref widget-1.2.3.tar.gz \
  --subject-digest sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef \
  --json \
  -- python tools/verify_release.py widget-1.2.3.tar.gz
```

Replace the illustrative digest with the artifact's actual lowercase SHA-256.
The subject identity and verifier are caller-owned and opaque to Cuff.
`tools/verify_release.py` is illustrative caller code, not part of Cuff.

## 5. Split claim and verify when necessary

```bash
cuff claim \
  --work-item onboarding \
  --summary "Onboarding complete" \
  --subject-path README.md \
  --json

cuff verify \
  --work-item onboarding \
  --claim rec_REPLACE_ME \
  --json \
  -- python -m pytest
```

Prefer `seal` when possible: a standalone claim becomes the latest claim
immediately and readiness fails until linked passing evidence exists.

Actor precedence is `--actor`, then `CUFF_ACTOR`, then `human:unknown`. Actor
is attribution, not authentication. Cuff never infers actor or work item from
Git configuration, a branch, or a pull request.

## 6. Check readiness

```bash
cuff check --work-item onboarding --json
```

For an explicit comparison range:

```bash
cuff check \
  --work-item onboarding \
  --base origin/main \
  --head HEAD \
  --json
```

The result contains `ok`, `errors`, `work_item`, `latest_claim`,
`selected_evidence`, and `record_count`. The JSONL file remains the full
history. The latest-claim evidence classification is exact:

- `CUFF_CLAIM_MISSING`: no claim exists;
- `CUFF_EVIDENCE_MISSING`: the latest claim has no linked evidence;
- `CUFF_EVIDENCE_FAILED`: linked evidence exists but none passed;
- `CUFF_SUBJECT_STALE`: passing evidence exists but the subject changed or
  cannot be recomputed; and
- `CUFF_EVIDENCE_STALE`: passing evidence no longer applies to the selected
  Git state.

Named workspace, ledger, dirtiness, ancestry, rewrite, and unexpected errors
remain separate. `selected_evidence` is non-null only when one passing record
satisfies subject and Git freshness. `ok` is true only when `errors` is empty
and that selected record is present.

## 7. Static host plugins

Cuff ships no plugin installer. This repository keeps one host-native source
payload at:

```text
plugins/cuff/
├── .claude-plugin/plugin.json
├── .codex-plugin/plugin.json
├── commands/
└── skills/
```

Install through the selected host's native plugin manager:

```bash
# Codex
codex plugin marketplace add fab7hq/fab7
codex plugin add cuff@fab7

# Claude Code
claude plugin marketplace add fab7hq/fab7
claude plugin install cuff@fab7 --scope user
```

Ensure the uv-managed `cuff` executable is on the host process's `PATH`. The
static assets delegate proof operations to `cuff --json` and contain no
runtime, generated payload, or copied executable. Live installation must be
validated separately for the exact host version; repository tests only
establish static structure.

## 8. Release

After the release commit passes `CI`, create and push the matching version tag
(`v0.2.1`). `release.yaml` verifies that the tag matches
`pyproject.toml`, reruns the source checks and tests, builds once, publishes to
PyPI with Trusted Publishing, then creates the GitHub Release from that tag.

Configure the PyPI publisher as `fab7hq/cuff`, workflow `release.yaml`,
environment `pypi`, and project `cuff-cli`. No PyPI token is used, and ordinary
pushes to `main` never publish a package.

Authenticated host qualification is a separate pre-tag gate. It uses fresh
`sandbox/cuff-02` lanes, a frozen qualification manifest, and a passing trusted
containment preflight under the root `LLM_VERIFICATION.md`. The live release
checker accepts only those matching controls and requires three fresh current
and three fresh stale-subject observations from each installed host.

## Troubleshooting

| Error | Meaning and action |
|---|---|
| `CUFF_GIT_FAILED` | Git is missing or could not complete. Restore a usable `git` executable. |
| `CUFF_NOT_A_REPOSITORY` | The selected directory is not in a Git worktree. Create/select the repository outside Cuff. |
| `CUFF_WORKSPACE_NOT_ROOT` | Run at the exact worktree root; nested markers are invalid. |
| `CUFF_PROJECT_NOT_INITIALIZED` | Run `cuff init --json` at the intended root. |
| `CUFF_PROJECT_INCOMPATIBLE` | Preserve ledgers, explicitly archive/remove only the old marker, then reinitialize. |
| `CUFF_REPOSITORY_DIRTY` | Commit or remove non-ledger changes before verify or seal. |
| `CUFF_SUBJECT_CHANGED` | Restore or recapture the exact filesystem subject. |
| `CUFF_CONCURRENT_UPDATE` | Another writer won; inspect the preserved ledger and retry deliberately. |
| `CUFF_LEDGER_REWRITE` | Restore append-only record history. |
| `CUFF_CLAIM_MISSING` | Record a claim for the requested work item. |
| `CUFF_EVIDENCE_MISSING` | Record evidence linked to the latest claim. |
| `CUFF_EVIDENCE_FAILED` | Run a verifier that exits successfully for the latest claim. |
| `CUFF_SUBJECT_STALE` | Restore the exact subject or create a new claim for its current identity. |
| `CUFF_EVIDENCE_STALE` | Re-observe passing evidence at the selected Git state. |

Use `--json` for automation. It writes one JSON document to stdout and keeps
diagnostics from corrupting that result.

Exit status `0` means success. Status `1` means a gate, refusal, or verifier
failure; `2` is argument parsing; `3` is an unexpected failure; and `130` is
interruption.

## Contributor verification

```bash
uv sync --locked
uv run --locked python -m pytest
uv run --locked python -m compileall -q core/cuff
uv build
git diff --check
git status --short
```

Packaging acceptance additionally requires installing the built wheel in an
isolated uv tool root and running the complete Git init/seal/check smoke outside
the source checkout.
