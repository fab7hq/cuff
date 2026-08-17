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
uv tool install cuff-cli==0.1.0
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
git add .cuff/project.json
git commit -m "Initialize Cuff"
```

Initialization creates only:

```text
.cuff/
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
  --work-item onboarding \
  --summary "Batch reviewed" \
  --subject-kind denim-fabric \
  --subject-ref fabric_123 \
  --subject-digest sha256:REPLACE_WITH_64_LOWERCASE_HEX \
  --json \
  -- denim assert-batch fabric_123
```

The verifier is caller-owned and opaque to Cuff.

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
history. `check` fails for a missing/latest unproved claim, failed or stale
evidence, subject mutation, non-ledger dirtiness, changed implementation,
ancestry failure, or ledger rewrite.

## 7. Static host plugins

Cuff ships no plugin installer. This repository keeps host-native source at:

```text
plugins/claude/cuff/   # Claude Code manifest and commands
plugins/codex/cuff/    # Codex manifest and skills
```

Install through the selected host's native plugin manager:

```bash
# Codex
codex plugin marketplace add fab7hq/cuff --ref v0.1.0
codex plugin add cuff@fab7hq

# Claude Code
claude plugin marketplace add fab7hq/cuff@v0.1.0
claude plugin install cuff@fab7hq --scope user
```

Ensure the uv-managed `cuff` executable is on the host process's `PATH`. The
static assets delegate proof operations to `cuff --json` and contain no
runtime, generated payload, or copied executable. Live installation must be
validated separately for the exact host version; repository tests only
establish static structure.

## 8. Release

After the release commit passes `CI`, create and push the matching version tag
(for example, `v0.1.0`). `release.yaml` verifies that the tag matches
`pyproject.toml`, reruns the source checks and tests, builds once, publishes to
PyPI with Trusted Publishing, then creates the GitHub Release from that tag.

Configure the PyPI publisher as `fab7hq/cuff`, workflow `release.yaml`,
environment `pypi`, and project `cuff-cli`. No PyPI token is used, and ordinary
pushes to `main` never publish a package.

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
| `CUFF_EVIDENCE_MISSING` | Produce passing fresh evidence for the latest claim. |

Use `--json` for automation. It writes one JSON document to stdout and keeps
diagnostics from corrupting that result.

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
