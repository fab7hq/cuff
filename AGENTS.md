# AGENTS.md

Cuff records a claim for one exact subject, observes one caller-selected
verifier, and decides whether the latest claim still has fresh passing evidence.
This file is what an agent needs to work in this repository.

## Setup

```sh
uv sync --locked          # Python >= 3.11, zero runtime dependencies
```

## Commands

```sh
uv run python -m pytest                     # whole suite, ~70 tests
uv run python -m pytest core/tests/test_gate.py -q
uv run python -m compileall -q core/cuff core/tests
uv lock --check --no-config
uv build                                    # wheel + sdist
uv run cuff --help                          # the five commands
```

Try it in a scratch worktree, never in this one:

```sh
cd $(mktemp -d) && git init -q && git commit -q --allow-empty -m init
uv run --project /path/to/cuff cuff init
uv run --project /path/to/cuff cuff claim --work-item demo --subject-path .
```

## Layout

```text
core/cuff/       the package: cli, workspace, subject, ledger, gate, git, errors
core/tests/      one test module per package module
action/          the GitHub Action wrapper — a thin package-based check
plugins/         static host assets for Claude Code and Codex
docs/            this project's own documentation
```

## Rules the code enforces

- **Git is the boundary, not a provider.** The workspace must be a Git worktree
  root; commit provenance, cleanliness, ancestry, and changed paths are all read
  from Git. There is no configurable alternative.
- **A completion statement is not evidence.** A receipt is written only when Cuff
  directly observed a stable verifier result for the same subject and commit.
- **`seal` is atomic.** The claim-and-evidence invariant holds or nothing is
  written.
- **Records are closed and append-only.** No compatibility reader, no legacy
  detection, no migration: a store at another location is not a Cuff store.
- **Observation is literal argv, without a shell.** Bounded, inspectable, no
  interpolation.
- **Failure is closed.** Every refusal is a stable error shape, not a guess.
- **Attribution is not authentication**, and proof is not material authority.
- **One-way composition.** An extension calls the public executable and validates
  the returned JSON. Cuff never learns an extension's name, schema, or
  semantics.

## Lean by default

The most common failure here is not a bug — it is a change bigger than the
problem. Read this before writing code.

**Always** — build the smallest complete change that satisfies the request, and
stop. Delete rather than deprecate: no compatibility reader, no legacy
detection, no "keep both paths for now". Fail closed with one stable error
shape.

**Ask first** — a new dependency, module, configuration surface, or public
option; any abstraction whose second caller does not exist yet; any widening of
a signature for a case nobody asked for.

**Never**

- Speculative generality: a plugin point, strategy interface, registry, or
  extension hook with exactly one implementation.
- A flag for a decision you can simply make. One correct behaviour beats a knob.
- Thin wrappers that each do one line of work. Splitting a function to hit a
  line-count rule produces lasagna, not clarity.
- Cleverness that needs a diagram to explain.
- A retry ladder or a fallback that guesses.

Why, in five lines:

- **YAGNI** — a hook for "later" is dead code now, and dead code gets trusted by
  mistake. Add it when the second caller arrives.
- **Duplicate twice before abstracting** — the wrong abstraction costs more than
  the duplication it replaced, because it must be unpicked before anything moves.
- **Deep modules, narrow interfaces** — a module absorbs complexity instead of
  distributing it. One unit doing real work behind a small surface beats five
  that pass the problem along.
- **Complexity is dependencies and obscurity, and it arrives one small addition
  at a time.** Every parameter, branch, file, and import is a permanent tax on
  the next reader. No knob is free.
- **Working is not finished, and clever is not finished** — the test is whether
  the next person can change it safely.

### In this codebase

Good — the workspace marker is `{"schema": 1}`. Nothing else. It answers "is
this a Cuff workspace" and refuses to answer anything a caller did not ask.

Bad — the marker as a settings file:

```json
{"schema": 1, "defaults": {...}, "providers": [...], "features": {...}}
```

Restraint already paid for, and not to be undone: zero runtime dependencies,
five commands, Git as the only boundary with no provider abstraction over it, no
migration framework, and no compatibility reader. A store at another location is
not a Cuff store — that sentence is the entire migration policy.

## Conventions

- Python 3.11+, standard library only.
- `--json` is the executable composition boundary: stable keys, stable order.
  Adding a key is a contract change; reordering is a break.
- Full type annotations, `from __future__ import annotations`.
- Comments explain *why* a rule exists. No task ids, no dates, no changelog
  entries in code or documentation.
- Tests build fixtures in `tmp_path` and create real throwaway Git worktrees.
  Do not write tests that assert on repository layout or packaging metadata.
- Never weaken, skip, or rewrite an existing test's expectation to make a change
  pass. A test that exists but did not run counts as missing.

## Gotchas

- This repository does not use its own gate: `/.fab7/` is ignored on purpose. A
  seal ledger here would mean Cuff had been sealing its own artifacts.
- `seal` re-checks worktree cleanliness *after* the verifier runs, so a verifier
  that writes into the worktree fails the seal.
- `cuff seal --json` sets `ok` from the verifier's exit code, not from whether a
  record was written. Refused and sealed-but-failing are different outcomes and
  must not be collapsed.
- Host plugin assets under `plugins/` are never packaged into the wheel, and Cuff
  never mutates a live host.
