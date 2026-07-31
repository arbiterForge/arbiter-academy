---
status: accepted
date: 2026-07-30
title: Keep ticket persistence at a validated local JSON boundary
decided-by: SUaDtL
supersedes: none
governs: workshop_queue/store.py, workshop_queue/app_data.py, data/*, workshop_queue/seed/*
---

# ADR-0001 — Keep ticket persistence at a validated local JSON boundary

## Status
Accepted

## Context
Workshop Queue is an offline teaching application. Learners need durable state that is easy to
inspect, reset, diff, and reproduce without an account, server, secret, or paid service. The same
storage layer must be safe in a cloned Academy checkout and when the console package is installed.
This record and its date are an Arbiter Academy fixture approved with the Academy specification.

## Decision
Persist tickets as validated JSON through `JsonTicketStore`. Every mutable path must remain beneath
an explicit trusted data root. Saves use a sibling temporary file, flush and synchronize it, then
replace the destination atomically. A source checkout uses its repository-local `data/` directory;
an installed package initializes an immutable bundled seed into an application-specific writable
user-data directory without overwriting an existing learner store.

## Alternatives considered
- **SQLite from the Python standard library** — transactional, but a binary store is less transparent
  for beginner inspection, Git-oriented exercises, and deterministic fixture resets.
- **A hosted database or API** — adds accounts, network access, secrets, expense, and failure modes
  that do not teach repository governance.
- **Direct JSON reads and writes in the CLI** — keeps the file format but mixes persistence,
  validation, presentation, and domain transitions into one untestable boundary.

## Consequences
Learners can inspect and reset the complete state with ordinary files, tests can use isolated
temporary roots, and no runtime package or service is required. The application must retain strict
schema validation, path containment, and atomic-write tests. JSON is suitable for this
repository-sized fixture, not a claim that it scales to a concurrent hosted service.

## Risks
Concurrent writers can still race after reading different snapshots, and filesystem durability
semantics vary after `os.replace`. A future requirement for multi-user writes, large datasets, or
cross-process transactions would reopen this decision.
