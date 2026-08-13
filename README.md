<p align="center">
  <img src="docs/assets/banner.svg" alt="Fab7 Knitting Machine & Loom Schematic Banner" width="100%" />
</p>

# Fab7

Fab7 records a completion claim for one exact subject, executes one
caller-selected verifier, records the observation, and later decides whether
the latest claim still has fresh passing evidence.

Fab7 is deliberately one proof product. It does not discover, build, install,
or run extension subsystems. Products such as Denim perform their own domain
verification, create an immutable subject, and compose Fab7 through the public
CLI and JSON response.

## Requirements

- Python 3.11 or newer;
- `uv` on `PATH` (`0.11.32` is the tested recommendation); and
- an existing Git worktree. Its root is the only valid Fab7 workspace.

Git is mandatory. Fab7 never initializes a repository, selects another
worktree, or stages, commits, fetches, pushes, releases, or deploys anything.

## Install

Install a released version as a standard uv-managed tool:

```bash
uv tool install fab7-cli==0.1.0
fab7 --version
```

For local development, install the checkout explicitly:

```bash
uv tool install --editable .
```

Fab7 has no runtime dependencies. It is distributed as a standard wheel and
source distribution; it contains no bundled Python or native executable.

## Five-command quickstart

Run initialization at the exact Git worktree root:

```bash
fab7 init --json
git add .fab7/project.json
git commit -m "Initialize Fab7"
```

The marker is exactly `{"schema":1}` and records live under
`.fab7/records/`. An incompatible marker is never rewritten or migrated.

The preferred path atomically appends a claim and its observed evidence:

```bash
fab7 seal \
  --work-item task-1 \
  --summary "Implementation complete" \
  --subject-path src \
  --json \
  -- python -m pytest

fab7 check --work-item task-1 --json
```

The split path is available when the claim must exist before verification:

```bash
fab7 claim \
  --work-item task-1 \
  --summary "Implementation complete" \
  --subject-path src \
  --json

fab7 verify \
  --work-item task-1 \
  --claim rec_REPLACE_ME \
  --json \
  -- python -m pytest
```

The public surface is exactly:

```text
fab7 init
fab7 claim
fab7 verify
fab7 seal
fab7 check
```

Every claim, verification, seal, and check names its work item explicitly.
Declared subjects use the complete `{kind, ref, digest}` identity; file and
tree subjects use `--subject-path` and a Fab7-computed manifest digest.

## Proof boundary

- Claims and evidence are closed generation-1 JSONL records.
- Every evidence record contains the `HEAD` commit observed before execution.
- Verifier argv is executed literally without a shell.
- Non-ledger dirtiness before or after verification records no evidence.
- `seal` appends its linked pair in one locked atomic replacement.
- `check` enforces subject freshness, commit ancestry, changed paths,
  non-ledger cleanliness, and append-only ledger changes.

Fab7 treats verifier argv as opaque. It does not select the command, import an
extension, interpret domain output, or grant merge, release, deployment,
spend, or residual-risk authority.

## Static host integrations

Small native assets live in [`plugins/claude/fab7`](plugins/claude/fab7) and
[`plugins/codex/fab7`](plugins/codex/fab7). The corresponding host plugin
manager owns their installation and removal. These assets require only the
uv-managed `fab7` executable on `PATH`; Fab7 itself does not install plugins.

```bash
# Codex
codex plugin marketplace add fab7hq/fab7 --ref v0.1.0
codex plugin add fab7@fab7hq

# Claude Code
claude plugin marketplace add fab7hq/fab7@v0.1.0
claude plugin install fab7@fab7hq --scope user
```

See [RUNBOOK.md](RUNBOOK.md) for operations, [the architecture overview](docs/architecture/overview.md)
for ownership, and [the ledger contract](docs/architecture/ledger.md) for the
record and gate invariants.

## Development

```bash
uv sync --locked
uv run --locked python -m pytest
uv run --locked python -m compileall -q core/fab7
uv build
git diff --check
```

## Community and support

- Use [Fab7 Discussions](https://github.com/fab7hq/fab7/discussions) for usage questions and design proposals.
- Report reproducible defects through [GitHub Issues](https://github.com/fab7hq/fab7/issues/new/choose).
- Read [CONTRIBUTING.md](CONTRIBUTING.md) before proposing a change.
- Report vulnerabilities privately as described in [SECURITY.md](SECURITY.md).

Fab7 is licensed under the [Apache License 2.0](LICENSE).
