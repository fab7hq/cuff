---
title: Fab7 0.1.0 Lean Core Refactoring Plan
type: plan
status: proposed
owner: architecture
last_updated: 2026-08-13
implementation_authorized: false
publication_authorized: false
authority_for:
  - Fab7 simplification target
  - retained and removed CLI commands
  - proof-core ownership boundaries
  - implementation sequence and acceptance criteria
---

# Fab7 0.1.0 lean core refactoring plan

## 1. Purpose

Refactor Fab7 back to one product:

> Fab7 records a claim for one exact subject, executes one caller-selected
> verifier, records the observation, and later determines whether the latest
> claim still has fresh passing evidence.

Fab7 is a hard proof requirement that other products compose. An extension may
perform richer domain verification first, but Fab7 does not discover, register,
route to, or understand extension verification subsystems.

Denim is the reference composition:

1. Denim performs its own coverage and goal-drift verification.
2. Denim creates or confirms one immutable batch.
3. Denim invokes public `fab7 verify` or `fab7 seal` for that exact batch.
4. Denim accepts the Fab7 receipt only when it matches the requested batch.

This document plans the refactor. It does not authorize implementation,
sibling-repository changes, migration, release, publication, or deployment.

## 2. Decision summary

The target has five public commands plus `--version`:

```text
fab7 init
fab7 claim
fab7 verify
fab7 seal
fab7 check
```

The following commands are removed, not deprecated:

```text
fab7 install
fab7 ext ...
fab7 audit
fab7 doctor
```

The target architecture makes these additional decisions:

- keep the two closed record types: `claim` and `evidence`;
- keep exact subject identity as `{kind, ref, digest}`;
- keep literal verifier argv execution without a shell;
- make Git the single hard provenance and readiness boundary;
- keep `seal` because its atomic claim-and-evidence append is a real safety
  invariant, not a command alias;
- make `--work-item` explicit on every work-item command;
- require one explicit Git repository boundary while removing branch,
  pull-request, release, toolchain, and host inference from proof identity;
- replace the release-pinned project manifest with a minimal workspace marker;
- use standard `uv` package and tool workflows for Fab7 and extensions;
- let each host and extension own its native plugin installation and assets;
- retain the CLI JSON contract as the extension boundary; do not add a public
  Python SDK, plugin SDK, verifier registry, callback interface, or provider
  framework.

Git being the hard boundary has one narrow meaning:

- the Fab7 workspace is the exact root of one existing Git worktree;
- every evidence record carries the observed `HEAD` commit;
- `verify` and `seal` require the non-ledger worktree to be clean before and
  after execution;
- `check` always enforces commit ancestry, changed-path, cleanliness, and
  append-only ledger rules;
- subject, command, and output digests remain exact identity fields, not an
  alternative provenance mode;
- Fab7 never initializes a repository or stages, commits, fetches, pushes, or
  otherwise mutates Git.

## 3. Important verification boundary

“Fab7 does not call a verification subsystem” means Fab7 has no knowledge of
Denim, Tapestry, or another verifier implementation. The only process Fab7 may
start is the literal argv explicitly supplied after `--` to `verify` or `seal`.
Fab7 treats that argv as opaque data and records its command digest, exit code,
and output digest.

This generic process observation is retained because it gives Fab7 direct
evidence instead of caller self-report. Removing it would require a new generic
proof-envelope protocol and would no longer establish that Fab7 observed a
passing verifier. That redesign is outside this simplification plan.

An extension therefore owns two distinct layers:

- **domain verification:** coverage, goal drift, business rules, review, or any
  other extension-specific judgment performed before Fab7 is invoked;
- **final verifier argv:** a bounded deterministic assertion selected by the
  caller and observed by Fab7 for the exact subject.

Fab7 never selects that command, imports the extension, reads extension-owned
state by convention, or interprets the command's domain output. A final Denim
integrity command may confirm that the immutable batch still matches the
already accepted review; it must not make Fab7 a Denim workflow engine or rerun
an agentic semantic review.

## 4. Current implementation findings

### 4.1 The proof kernel is already direct

The useful core is concentrated in:

- `cli.py` for arguments, structured output, and exit status;
- `workspace.py` for bounded workspace selection;
- `subject.py` for declared and filesystem subject identity;
- `ledger.py` for claims, evidence, command observation, and atomic append;
- `gate.py` for latest-claim readiness;
- `git.py` for the mandatory repository provenance and readiness boundary;
- `errors.py` for stable failures.

The ledger already has the important properties to preserve: closed records,
duplicate rejection, bounded inputs and output retention, execution without a
shell, subject capture before and after verification, atomic replacement,
concurrent-update rejection, and append-only Git checks.

### 4.2 The CLI currently exposes two products

The current top-level CLI has nine commands and `ext` has seven subcommands.
Proof commands share one dispatcher with host registration, catalog refresh,
extension scaffolding, native builds, installation, diagnosis, migration,
rollback, and uninstall behavior.

This coupling is visible at import time: `cli.py` imports `extension/`,
`hosts.py`, installation code, package builders, and proof functions together.
A user invoking `fab7 check` therefore ships and imports responsibilities that
have nothing to do with checking proof.

### 4.3 Distribution dominates the implementation

The host, extension, native-build, release-build, toolchain, and plugin modules
are substantially larger than the proof kernel. Their tests likewise dominate
the suite. This is the main source of build pain and architectural surface, not
the claim/evidence ledger.

### 4.4 Project initialization is tied to a global native release

The current `.fab7/project.json` stores Fab7 version and executable digest, and
every project command compares them with a globally selected release. This
conflicts with normal `uv tool install`, upgrade, and isolated execution.
Workspace identity does not require executable pinning.

### 4.5 `audit` and `doctor` do not own independent product behavior

`audit` is a small projection of `check` plus records. `doctor` combines Git
availability, native release selection, PyInstaller toolchain identity,
workspace existence, and ledger parsing. Once custom distribution is removed,
ordinary command failures and `check --json` cover the useful diagnostics.

### 4.6 Hidden defaults add behavior without adding proof

Current behavior may infer a work item from a pull request or Git branch, infer
an actor from Git configuration, and choose Git provenance automatically during
initialization. These choices make the same command mean different things in
different environments. The target removes those identity inferences and the
provenance choice: Git is fixed, while work item and actor remain explicit.

## 5. Target product boundary

Fab7 owns only:

- initialization of one local proof workspace;
- exact subject validation and optional filesystem manifesting;
- completion claims;
- direct observation of one caller-selected verifier command;
- evidence linked to a claim and subject digest;
- atomic append and concurrent-write rejection;
- subject-digest freshness;
- mandatory Git commit provenance and readiness;
- stable human and JSON CLI output.

Fab7 does not own:

- extension discovery, catalogs, registries, source schemas, or packages;
- extension creation, builds, installation, activation, rollback, or removal;
- Claude Code or Codex plugin installation;
- Python or uv installation;
- managed CPython, PyInstaller, native executable assembly, or toolchain
  attestation;
- workflow-specific verification such as Denim coverage or goal drift;
- a verifier registry, verifier type hierarchy, callback protocol, or
  subsystem lifecycle;
- extension state, extension migrations, or cross-extension imports;
- plans, approvals, decisions, waivers, arbitrary events, or methodology;
- a service, daemon, database, dashboard, background updater, or remote ledger;
- merge, release, deployment, spend, or other material authority.

## 6. Target CLI contract

### 6.1 `fab7 init`

```text
fab7 init [--workspace PATH] [--json]
```

Behavior:

- select only the explicit existing directory or the current directory;
- require the `git` executable;
- require that selection to be the root of one existing Git worktree;
- create `.fab7/project.json` as the exact marker `{"schema": 1}`;
- create `.fab7/records/`;
- validate path and symlink safety;
- preserve already valid records;
- be idempotent for the exact marker;
- perform no network, host, release, uv, Python, or toolchain operation beyond
  resolving and validating the local Git worktree boundary.

There is no initialization provenance option. Git is the fixed product
boundary for initialization, verification, sealing, and readiness. Fab7 does
not initialize a Git repository, choose another worktree, or infer proof
identity from a branch or pull request.

### 6.2 `fab7 claim`

```text
fab7 claim --work-item ID --summary TEXT
           (--subject-kind KIND --subject-ref REF --subject-digest DIGEST
            | --subject-path PATH)
           [--workspace PATH] [--actor ACTOR] [--json]
```

Behavior:

- require the work item explicitly;
- accept either one Fab7-computed file/tree subject or one complete declared
  subject;
- append one validated claim;
- never execute a verifier;
- never infer work-item identity or actor attribution from Git;
- use `--actor`, then `FAB7_ACTOR`, then `human:unknown` for attribution;
- treat actor as attribution, not authentication.

### 6.3 `fab7 verify`

```text
fab7 verify --work-item ID --claim RECORD_ID
            [--workspace PATH]
            [--timeout SECONDS] [--actor ACTOR] [--json]
            -- COMMAND [ARGS...]
```

Behavior:

- require an existing claim in the same explicit work item;
- require the workspace to be the root of one clean Git worktree;
- allow only append-only Fab7 record paths to differ from `HEAD`;
- capture and validate the claimed subject before execution;
- execute the literal argv without a shell and with bounded arguments, time,
  retained output, and digested full output;
- reject subject drift, Git drift, or concurrent ledger mutation;
- append exactly one evidence record for a stable exit or timeout;
- return success only for exit code zero;
- never identify or interpret the verifier as an extension subsystem.

### 6.4 `fab7 seal`

```text
fab7 seal --work-item ID --summary TEXT
          (--subject-kind KIND --subject-ref REF --subject-digest DIGEST
           | --subject-path PATH)
          [--workspace PATH]
          [--timeout SECONDS] [--actor ACTOR] [--json]
          -- COMMAND [ARGS...]
```

Behavior:

- use the same subject, verifier, Git, and actor rules as `claim` and
  `verify`;
- construct one claim and one linked evidence record in memory;
- append both records in one locked atomic replacement;
- append a claim and failed evidence pair for a stable nonzero exit or timeout;
- append neither record after launch failure, interruption, subject drift, Git
  drift, invalid observation, or concurrent ledger mutation.

`seal` remains the preferred extension path because it prevents a partially
written latest claim when the final observation cannot be represented.

### 6.5 `fab7 check`

```text
fab7 check --work-item ID [--workspace PATH]
           [--base REF] [--head REF] [--json]
```

Behavior:

- require the work item explicitly;
- validate every ledger through the same closed parser;
- select the latest claim in the requested ledger;
- require linked exit-zero evidence for that claim;
- recompute file/tree subjects for digest freshness;
- always apply Git cleanliness, ancestry, changed-path, and append-only rules;
- accept optional explicit `--base` and `--head` refs for the mandatory Git
  comparison, otherwise use the defined local defaults;
- remain the only readiness implementation.

Human output remains one PASS/FAIL result plus errors. JSON output replaces the
removed `audit` command and has one stable closed shape:

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

On failure, `latest_claim` and `selected_evidence` may be `null`. The response
reports the evidence selected by the gate, not an unbounded history dump. The
JSONL ledger remains the complete inspectable history.

### 6.6 Common CLI rules

- Every stateful command accepts `--workspace PATH`.
- Without `--workspace`, non-init commands discover the nearest parent with the
  exact Fab7 project marker in a bounded walk.
- Every discovered or explicit workspace must equal its containing Git
  worktree root; a nested marker or workspace outside Git fails closed.
- All mutation and check failures return exit code `1` with stable Fab7 errors.
- Argument usage errors return `2`, unexpected internal failures return `3`,
  and interruption returns `130`.
- `--json` writes one JSON document to stdout; diagnostics do not corrupt that
  document.
- Removed commands fail argument parsing. They do not print compatibility or
  forwarding advice from runtime code.

## 7. Persistence and compatibility decisions

### 7.1 Retain the proof ledger contract

Do not redesign claims or the evidence payload during this refactor. Retain:

- record generation `1`;
- claim fields and exact subject shape;
- evidence claim link, subject digest, command digest, exit code, output digest,
  and Git commit provenance;
- canonical JSONL serialization;
- one ledger per normalized work item;
- no third seal record;
- no compatibility reader, migration framework, dual write, or database.

Generation remains `1`, but the closed evidence parser deliberately narrows the
existing provenance union to the Git shape. A digest-only evidence record is
incompatible and cannot establish readiness. This is a direct contract cut,
not a new record generation or proof-envelope abstraction.

### 7.2 Replace only the project marker

The project marker becomes `{"schema": 1}` because package identity and a
configurable provenance default do not belong to workspace identity. The Git
worktree root is the mandatory external workspace boundary.

The implementation must not silently reinterpret or rewrite an incompatible
marker. A user cutting over an older initialized workspace must explicitly
archive or remove only the old marker and rerun `fab7 init`. Existing ledgers
may remain only when every record passes the Git-only closed ledger parser. No
automatic migration command is added.

## 8. Extension and host composition

### 8.1 One-way product ownership

```text
extension
    -> performs extension-specific verification
    -> creates one exact immutable subject
    -> invokes public fab7 claim/verify or fab7 seal
    -> validates the returned JSON receipt

fab7
    -> validates the subject and workspace
    -> executes only the literal caller-supplied verifier argv
    -> records the observation
    -> knows nothing about the extension
```

Fab7 must contain no extension names, extension paths, extension manifests,
extension record schemas, extension lifecycle hooks, or extension-specific
error mapping.

### 8.2 Denim reference behavior

Denim retains ownership of:

- pending asks and batch construction;
- semantic review;
- obligation coverage;
- goal-drift judgment;
- review freshness and confirmation;
- its immutable batch and local state;
- validation of the Fab7 response against the requested batch.

After those checks pass, Denim calls `fab7 seal` once for its batch. Any final
Denim argv supplied to Fab7 is a deterministic integrity assertion for the
already reviewed batch, not a Fab7-discovered subsystem and not another
semantic model review. Failed or mismatched Fab7 sealing leaves Denim state
pending.

Fab7 does not import Denim and Denim does not import Fab7 Python modules. The
public executable plus JSON output is the only runtime boundary.

### 8.3 Installation ownership

`uv` owns Python executable installation and dependency isolation:

- Fab7 is installed as the `fab7-cli` tool;
- Denim and every other extension are installed as their own uv tools;
- each project owns its own version, dependencies, wheel, and release;
- development uses an editable uv tool installation or an isolated project
  environment;
- Fab7 never builds or vendors an extension executable.

Claude Code and Codex own plugin discovery and installation:

- each repository contains its own small static host-native plugin assets;
- host assets invoke the corresponding uv-managed executable on `PATH`;
- the host plugin does not contain a copied Python runtime or native binary;
- the host's native plugin manager installs, updates, and removes those assets;
- Fab7 does not wrap host plugin commands or maintain a second marketplace.

The Fab7 repository may retain a minimal static host integration for
initialization and proof guidance, but it must not generate Claude assets from
Codex assets or vice versa. Small host-native files are cheaper and clearer
than a cross-host adapter/build framework.

## 9. Target repository structure

```text
fab7/
├── core/
│   ├── fab7/
│   │   ├── __init__.py
│   │   ├── __main__.py
│   │   ├── cli.py
│   │   ├── errors.py
│   │   ├── gate.py
│   │   ├── git.py
│   │   ├── ledger.py
│   │   ├── subject.py
│   │   └── workspace.py
│   └── tests/
│       ├── test_action.py
│       ├── test_cli.py
│       ├── test_gate.py
│       ├── test_git.py
│       ├── test_ledger.py
│       ├── test_package.py
│       ├── test_subject.py
│       └── test_workspace.py
├── plugins/
│   ├── claude/                 # minimal static native assets
│   └── codex/                  # minimal static native assets
├── action/                     # thin check wrapper
├── docs/
│   ├── architecture/
│   ├── plans/
│   └── product/
├── pyproject.toml
├── uv.lock
├── README.md
├── RUNBOOK.md
├── CONTRIBUTING.md
├── LICENSE
└── SECURITY.md
```

The exact test filenames may be consolidated when a separate file adds no
clarity. The architecture must not introduce interfaces solely to match this
tree.

## 10. Removal map

Remove these runtime areas after their retained responsibilities have moved:

- `core/fab7/extension/`;
- `core/fab7/plugin/`;
- `core/fab7/templates/`;
- `core/fab7/hosts.py`;
- `core/fab7/install.py`;
- `core/fab7/toolchain.py`;
- `core/fab7/native_build.py`;
- `core/fab7/release_build.py`;
- Fab7-managed build requirements and PyInstaller package data;
- `install.sh`;
- generated host adapter templates and extension action templates.

Remove or replace tests whose only contract is deleted behavior:

- `test_extensions.py`;
- `test_ext_create.py`;
- `test_extension_install.py`;
- `test_hosts.py`;
- `test_native_build.py`;
- `test_plugin_build.py`;
- native artifact and selected-release portions of `test_artifact.py` and
  `test_distribution.py`.

Do not leave empty packages, deprecated imports, forwarding functions, retired
error codes, compatibility parser branches, or skipped tests for removed
behavior.

## 11. File-level implementation plan

### 11.1 `core/fab7/cli.py`

- rebuild the parser around the five retained commands;
- remove all host and extension imports;
- make work item required where applicable;
- remove every provenance selector and digest-only execution branch;
- remove `audit` and `doctor` dispatch;
- remove extension-specific output helpers;
- preserve one common JSON error envelope;
- keep stdout/stderr replay for non-JSON verifier execution;
- add parser tests proving every removed command is absent.

### 11.2 `core/fab7/workspace.py`

- own project initialization and marker validation;
- select current directory for implicit init;
- require the selected directory and every discovered marker to equal the
  containing Git worktree root;
- retain bounded nearest-parent discovery for later commands;
- reject symlinked or malformed project paths;
- atomically create the minimal marker;
- call ledger directory initialization without release selection.

### 11.3 `core/fab7/ledger.py`

- retain claim, verify, seal, parser, bounds, locking, and atomic writes;
- remove pull-request and Git-branch work-item derivation;
- reduce actor resolution to explicit argument, `FAB7_ACTOR`, or
  `human:unknown`;
- preserve literal Git commit provenance;
- keep command execution generic and extension-unaware;
- preserve failed evidence and timeout semantics;
- avoid splitting the module unless a directly measured responsibility can be
  removed by doing so.

### 11.4 `core/fab7/gate.py`

- keep one `check` implementation;
- fold the minimal useful audit projection into the check result;
- remove `audit` and `doctor`;
- remove toolchain and release imports;
- return the selected latest claim and evidence in the JSON-ready result;
- keep subject-digest freshness and mandatory Git freshness in direct
  functions;
- remove the generic `Result` helper if a plain closed result object is simpler.

### 11.5 `core/fab7/errors.py`

- retain `Fab7Error` and stable error serialization;
- remove unused result machinery after `gate.py` is simplified;
- do not introduce an error class hierarchy.

### 11.6 `core/fab7/subject.py` and `core/fab7/git.py`

- preserve existing bounded subject and Git behavior;
- remove helpers made unreachable by the single mandatory Git policy;
- do not add pluggable subject or provenance providers.

### 11.7 Packaging

- keep a standard PEP 517 project and the `fab7` console script;
- keep runtime dependencies empty;
- remove the PyInstaller build dependency and Fab7 package templates;
- remove the exact managed-CPython coupling;
- set the minimum Python version to the lowest version proven by the retained
  core, initially expected to be Python 3.11 or later;
- use `uv build` to create the standard wheel and source distribution;
- use `uv tool install` for executable installation;
- keep uv `0.11.32` as the tested recommendation, not a runtime equality gate;
- regenerate `uv.lock` only after `pyproject.toml` reaches its target shape.

### 11.8 Static host assets

- retain only actions that directly help initialize or use the proof CLI;
- remove `ext-create`, `ext-list`, and `ext-install` assets;
- store final Claude Code and Codex files in their native layouts;
- keep each file short and delegate all proof mutation to `fab7 --json`;
- validate static structure, but do not rebuild or package it through Python;
- require separately authorized live-host installation evidence before claiming
  current host compatibility.

### 11.9 GitHub Action

- keep the action only as a thin invocation of released Fab7;
- install or run the selected standard package through uv;
- invoke `fab7 check` with explicit work item and refs;
- contain no second readiness implementation;
- do not build a native executable inside the action.

## 12. Implementation phases

### Phase 0 — Baseline and contract freeze

1. Capture `git status --short`, including all untracked paths.
2. Preserve every unrelated user-owned edit in the dirty worktree.
3. Run the current focused proof tests and full suite before deletion.
4. Save current `fab7 --help` and retained command help as comparison evidence.
5. Add target parser and workspace tests before removing implementation.

Exit criteria:

- baseline failures, if any, are recorded and distinguished from new failures;
- the five-command target, unchanged claim shape, and Git-only evidence shape
  are explicit in tests;
- no implementation or publication authority is inferred from this plan.

### Phase 1 — Isolate the proof CLI

1. Remove `install` and `ext` parser/dispatcher branches and imports.
2. Remove `audit` and `doctor` commands.
3. Make work item explicit.
4. Remove every provenance selector and require Git commit provenance.
5. Enrich `check --json` with the selected claim/evidence projection.
6. Confirm `claim`, `verify`, `seal`, and `check` behavior before deleting
   supporting distribution modules.

Exit criteria:

- help exposes exactly five commands;
- removed commands fail parser tests;
- proof-focused tests pass without importing extension or host modules.

### Phase 2 — Simplify workspace initialization

1. Move initialization into `workspace.py`.
2. Replace release-pinned metadata with the exact schema marker.
3. Require explicit or current workspace selection to resolve to the exact Git
   worktree root, without initializing or switching repositories.
4. Remove selected-release validation from every project command.
5. Prove idempotence, nearest-project discovery, path safety, and preservation
   of valid existing ledgers.

Exit criteria:

- `fab7 init` fails closed outside a Git worktree and for a selection that is
  not the worktree root;
- no ordinary proof command needs `FAB7_HOME`, uv, PyInstaller, or a globally
  selected release;
- an incompatible marker fails clearly without hidden rewriting.

### Phase 3 — Delete distribution and extension machinery

1. Delete the removal-map modules and templates.
2. Delete their exclusive tests and error codes.
3. Remove package data and imports made unreachable.
4. Search the repository for retired module, command, and schema names.
5. Keep no compatibility facade.

Exit criteria:

- importing `fab7.cli` loads only proof-core modules;
- no runtime code references catalog, extension package, host registration,
  PyInstaller, managed CPython, or native release selection;
- the retained full test suite passes.

### Phase 4 — Standard uv packaging and static host integration

1. Simplify `pyproject.toml` and regenerate the lock.
2. Build a wheel and source distribution with `uv build`.
3. Install the wheel into an isolated temporary uv tool directory.
4. In a disposable Git worktree, smoke `fab7 --version`, `init`, commit the
   marker and test subject, then run `seal` and `check` from that installation.
5. Replace generated host assets with minimal static native files.
6. Validate host files structurally; keep live host mutation as a separately
   authorized acceptance step.

Exit criteria:

- standard artifacts install without the source checkout;
- no native executable or bundled Python is produced;
- the host assets depend only on the `fab7` executable being on `PATH`.

### Phase 5 — Documentation synchronization

Update every active document in the same change:

- `README.md`: one proof product, Git prerequisite and hard workspace boundary,
  uv installation, and five-command quickstart;
- `RUNBOOK.md`: standard uv tool setup, explicit work item, mandatory Git
  boundary, and separate native host-plugin setup;
- `CONTRIBUTING.md`: uv sync/test/build workflow without PyInstaller;
- `docs/product/vision.md`: remove the extension-hub product promise;
- `docs/product/roadmap.md`: describe the 0.1.0 lean-core cut and release gate;
- `docs/architecture/overview.md`: target modules, flow, and ownership;
- `docs/architecture/ledger.md`: retain record semantics and clarify opaque
  caller-selected argv;
- `docs/README.md`: remove distribution architecture from the active index;
- `action/README.md` and action metadata: thin package-based check behavior.

Delete `docs/architecture/distribution.md` once all still-valid installation
guidance has moved to the README or runbook. Do not retain it as historical
architecture in the active documentation tree.

Exit criteria:

- no active document advertises `fab7 install`, `fab7 ext`, `audit`, or
  `doctor`;
- no active document claims Fab7 builds or installs extensions or host plugins;
- all command examples match parser help;
- version `0.1.0` and advisory uv `0.11.32` remain aligned where relevant.

### Phase 6 — Consumer and release review

Perform read-only consumer checks first:

- Denim `fab7 seal` invocation and response validation;
- Tapestry initialization and strict result parsing;
- WNW or other repositories that call Fab7;
- GitHub Action inputs and examples;
- registry documentation that still presents Fab7 as an extension manager.

Sibling changes require their own authority and validation. Do not modify them
as an implicit part of the Fab7 refactor.

Exit criteria for the Fab7 repository:

- every retained local acceptance criterion passes;
- known consumer incompatibilities are listed with exact paths and contracts;
- publication remains blocked until authorized consumer cutovers and live-host
  evidence are complete.

## 13. Test plan

### CLI and workspace

- help contains only the retained commands;
- every removed command is rejected;
- missing explicit work item fails;
- init is idempotent and invokes Git only to resolve and validate the worktree
  root;
- explicit and nearest-parent workspace selection is bounded and safe;
- malformed, symlinked, or incompatible markers fail closed;
- non-Git directories, nested workspace markers, and explicit non-root
  workspaces fail closed;
- a missing or unusable Git executable fails with one stable Fab7 error;
- human and JSON output remain separate and parseable.

### Claim and subject

- declared and filesystem subjects retain exact closed shapes;
- path escape, symlink, special-file, depth, file-count, and byte bounds remain;
- claim append is atomic;
- actor precedence is explicit argument, environment, then unknown;
- no Git branch, Git actor, or pull-request identity is inferred.

### Verify and seal

- passing, failing, and timed-out commands produce exact observations;
- every produced evidence record contains the stable pre-execution `HEAD`;
- non-ledger dirtiness before or after execution appends no evidence;
- the full output is digested while retained output stays bounded;
- launch failure and interruption append no evidence;
- subject drift appends no evidence;
- concurrent append preserves the competing writer and rejects the stale
  writer;
- seal success and stable failure append exactly one linked pair;
- seal launch failure, drift, interruption, and concurrency append neither
  record;
- literal argv is executed without a shell.

### Check and Git

- no claim, no evidence, failed evidence, and stale evidence fail;
- the latest claim controls readiness;
- file/tree mutation invalidates subject freshness;
- every non-ledger mutation invalidates Git readiness, including for an opaque
  declared subject;
- digest-only evidence is rejected by the closed parser and never selected;
- Git dirty state, changed implementation, ancestry failure, and ledger rewrite
  fail;
- optional `--base` and `--head` override the mandatory Git comparison refs;
- JSON selects the exact claim and evidence used by the gate.

### Packaging and static integrations

- `uv sync --locked` succeeds;
- the full retained pytest suite passes;
- `uv build` creates an installable wheel and source distribution;
- an isolated tool installation can execute the minimal end-to-end path;
- wheel inspection contains only runtime package files;
- static host manifests and skills contain no generated native payload;
- the action delegates to `fab7 check`.

## 14. Verification commands

The implementation should finish with direct evidence equivalent to:

```sh
uv sync --locked
uv run --locked python -m pytest
uv run --locked python -m compileall -q core/fab7
uv build
fab7 --help
fab7 init --help
fab7 claim --help
fab7 verify --help
fab7 seal --help
fab7 check --help
git diff --check
git status --short
```

The built wheel must also be installed and smoked in a disposable uv tool root;
running from the source checkout is not packaging evidence. Live Claude Code or
Codex installation is separate external-state evidence and must not be inferred
from static tests.

## 15. Acceptance matrix

| Requirement | Required evidence |
|---|---|
| Five-command CLI | parser tests and actual help output |
| No extension subsystem in Fab7 | source search plus import-boundary test |
| Denim-style composition remains possible | exact subprocess contract test and consumer review |
| Git is the hard boundary | missing-Git, non-Git, and non-root rejection plus Git-only CLI tests |
| Every observation is commit-anchored | record parser, verify, seal, and Git gate tests |
| Seal remains atomic | success, failure, drift, interruption, and concurrency tests |
| Audit and doctor are gone | parser rejection and source/doc search |
| No custom extension lifecycle | deleted modules/tests and source/doc search |
| No native build stack | simplified metadata, wheel inspection, and source search |
| Standard uv installation works | disposable installed-wheel smoke |
| Documentation matches runtime | command-example scan and manual authority review |
| Dirty user work is preserved | before/after changed-path comparison |
| No publication occurred | local/remote release state unchanged unless separately authorized |

## 16. Risks and controls

### Existing project markers become incompatible

Control: fail clearly, preserve valid ledgers, document the explicit marker
cutover, and add no automatic migration.

### Existing digest-only evidence becomes incompatible

Control: fail clearly and require a new Git-anchored observation. Do not accept,
rewrite, upgrade, or silently reinterpret digest-only evidence.

### Consumers may parse removed command output or init fields

Control: inventory exact callers before publication. Update each sibling only
under separate authority. Do not add compatibility fields to Fab7.

### Removing custom installation may temporarily reduce convenience

Control: complete and test the standard uv tool instructions and static native
host assets before release. Do not restore a second installer.

### Generic verifier argv may be mistaken for subsystem orchestration

Control: document that Fab7 executes opaque caller-supplied argv only. Keep all
extension discovery, routing, semantics, and state outside Fab7.

### Large deletion can conceal regressions

Control: land the refactor in phases, run proof tests after each phase, inspect
all changed and untracked paths, and compare retained behavior against the
acceptance matrix rather than relying on line-count reduction.

## 17. Explicit non-goals

This refactor must not add:

- a proof-envelope or attestation protocol;
- a public Python API solely for extensions;
- a verifier interface, registry, callback bus, or plugin runtime;
- an extension registry client or marketplace abstraction;
- host adapter classes or a host-neutral generated package;
- compatibility aliases for removed commands;
- automatic workspace or record migration;
- signatures, remote storage, SQLite, a service, or a dashboard;
- additional or configurable provenance modes;
- new runtime dependencies;
- an adjacent Denim, Tapestry, WNW, or registry refactor;
- release, publication, or deployment work.

## 18. Definition of done

The refactor is complete only when all of the following are true:

1. Fab7 exposes exactly `init`, `claim`, `verify`, `seal`, and `check`.
2. The claim/evidence ledger and atomic seal invariants remain directly tested.
3. Every evidence record is anchored to Git and readiness always enforces the
   Git worktree, commit ancestry, changed-path, cleanliness, and append-only
   ledger boundary.
4. Work-item identity is explicit and environment-independent.
5. Fab7 has no extension, host-installation, native-build, managed-toolchain, or
   selected-release runtime code.
6. Fab7 builds as a standard dependency-free Python package and installs as a
   uv-managed tool.
7. Host integrations are small static native assets owned outside the proof
   runtime.
8. Extensions compose Fab7 through its executable and JSON result without Fab7
   understanding their domain verification.
9. Every active document describes the implemented five-command architecture.
10. Focused, full-suite, packaging, installed-tool, whitespace, and changed-path
    evidence pass for the exact final tree.
11. Known sibling cutovers and live-host obligations are reported separately;
    none are claimed from local Fab7 tests.
12. No release or publication occurs without separate explicit authorization.
