---
title: Cuff Documentation
type: index
status: accepted
owner: docs
---

# Cuff documentation

Cuff is a Git-anchored claim and evidence gate with five public commands.

| Document | Authority |
|---|---|
| [`architecture/overview.md`](architecture/overview.md) | module ownership, CLI flow, Git boundary, and composition |
| [`architecture/ledger.md`](architecture/ledger.md) | closed records, verifier observation, atomic append, and readiness |
| [`product/vision.md`](product/vision.md) | product boundary and non-goals |
| [`product/roadmap.md`](product/roadmap.md) | 0.1.0 lean-core cut and release gate |

Implementation planning is unified at the ecosystem root, `fab7/plan.md`; this
repository carries no plan of its own.

Installation and operations live in the root [README](../README.md) and
[runbook](../RUNBOOK.md). Agent-facing working rules live in
[`AGENTS.md`](../AGENTS.md). Static host assets live under `plugins/`; their host
managers own installation.
