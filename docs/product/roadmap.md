---
title: Cuff Product Roadmap
type: product
status: accepted
owner: product
last_updated: 2026-08-13
authority_for:
  - 0.1.0 lean-core outcome
  - local release gate
  - external publication obligations
---

# Cuff product roadmap

## 0.1.0 lean-core cut

The 0.1.0 source returns Cuff to one product with five commands: `init`,
`claim`, `verify`, `seal`, and `check`.

The cut retains generation-1 claim/evidence ledgers, exact subjects, bounded
literal argv observation, atomic sealing, and one readiness gate. Git becomes
the mandatory workspace, observation, and readiness boundary. Work-item
identity is explicit, and the workspace marker is reduced to `{"schema":1}`.

The cut removes the extension lifecycle, catalog, host installer, custom
bootstrap, native executable builder, managed toolchain, selected-release
project pin, alternate provenance, `audit`, and `doctor`. These are direct
contract removals with no compatibility reader or migration framework.

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
