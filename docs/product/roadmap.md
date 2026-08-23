---
title: Cuff Product Roadmap
type: product
status: accepted
owner: product
authority_for:
  - 0.1.0 lean-core outcome
  - 0.1.0 store-root location
  - local release gate
  - external publication obligations
---

# Cuff product roadmap

## 0.1.0 lean-core cut

One product, five commands: `init`, `claim`, `verify`, `seal`, and `check`.

The cut is generation-1 claim/evidence ledgers, exact subjects, bounded literal
argv observation, atomic sealing, and one readiness gate. Git is the mandatory
workspace, observation, and readiness boundary. Work-item identity is explicit,
and the workspace marker is `{"schema":1}`.

The workspace store root is `.fab7/cuff/{project.json,records}`, so Cuff shares
the single `.fab7` namespace with the rest of the ecosystem rather than claiming
a second top-level dot directory. There is no compatibility reader, no legacy
detection, and no migration of any kind: a store at any other location is not a
Cuff store.

Deliberately absent: an extension lifecycle, a catalog, a host installer, a
custom bootstrap, a native executable builder, a managed toolchain, a
selected-release project pin, alternate provenance, `audit`, and `doctor`.

## Standard distribution

Cuff is a dependency-free Python package for Python 3.11 or newer. `uv build`
produces the standard wheel and source distribution; `uv tool install` owns
the executable environment. uv `0.11.32` remains the tested recommendation.

Claude Code and Codex guidance is stored as separate static native assets.
Each host owns plugin installation and removal. Cuff does not package those
assets into the Python wheel or mutate a live host.

## Release gate

A 0.1.0 publication requires fresh evidence for the exact release bytes:

- locked sync, Python 3.11 and current-version tests, and compile checks;
- standard wheel and source distribution build;
- wheel-content inspection and isolated installed-tool init/seal/check smoke;
- five-command help and removed-command rejection;
- static host manifest validation plus separately authorized live-host checks;
- known consumer cutovers reviewed in Denim, Tapestry, WNW, the Action, and
  registry-facing documentation; and
- clean whitespace and exact changed-path review.

Consumer changes, live host installation, release, publication, and deployment
remain separate operations requiring separate authority. Local Cuff tests do
not prove any of them.

## Still excluded

No proof envelope, public Python extension SDK, plugin runtime, verifier
registry, configurable provenance, database, service, remote ledger,
signature system, background updater, policy engine, compatibility layer, or
adjacent consumer refactor is planned as part of this cut.
