---
title: Cuff Product Vision
type: product
status: accepted
owner: product
authority_for:
  - product purpose
  - ownership boundary
  - explicit non-goals
---

# Cuff product vision

Cuff makes one narrow promise:

> Record a claim for one exact subject, execute one caller-selected verifier,
> record the observation, and later determine whether the latest claim still
> has fresh passing evidence.

The product is a hard proof requirement that richer workflows compose. A
completion statement is not evidence. A caller receives a useful receipt only
when Cuff directly observed a stable verifier result for the same subject and
Git commit.

## Principles

- Exact subject, work-item, command, output, and commit identities are explicit.
- Git is one mandatory readiness boundary, not a configurable provider.
- `seal` preserves the atomic claim-and-evidence invariant.
- JSON is the executable composition boundary.
- Failure is closed, bounded, and inspectable.
- Attribution is not authentication, and proof is not material authority.

## One-way composition

A caller owns semantic review, coverage, goal drift, and its immutable domain
state. After those checks, it calls the public Cuff executable for the exact
subject and validates the returned JSON receipt. Cuff does not know the
caller's name, schema, state, or verifier semantics.

## Explicit non-goals

Cuff is not an extension hub, plugin installer, native builder, managed Python
distribution, verifier registry, callback framework, provenance provider
system, database, service, dashboard, planner, approval engine, release tool,
or deployment operator. It adds no compatibility aliases, automatic
migration, remote state, signatures, or new runtime dependencies.

Host integrations are small static native assets maintained outside the proof
runtime. Their host managers own installation and compatibility.
