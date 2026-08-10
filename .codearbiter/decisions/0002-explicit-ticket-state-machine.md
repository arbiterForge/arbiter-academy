---
status: accepted
date: 2026-07-30
title: Enforce an explicit immutable ticket state machine
decided-by: SUaDtL
supersedes: none
governs: workshop_queue/model.py, workshop_queue/service.py, tests/test_model.py, tests/test_service.py
---

# ADR-0002 — Enforce an explicit immutable ticket state machine

## Status
Accepted

## Context
Workshop Queue must give learners credible feature, fix, TDD, review, and audit exercises without
hiding domain behavior inside CLI formatting or mutable dictionaries. Invalid transitions need to
fail consistently, and accepted transitions need durable attribution and timestamps. This record
and its date are an Arbiter Academy fixture approved with the Academy implementation plan.

## Decision
Represent ticket status with the explicit values `open`, `claimed`, and `completed`. Permit only
`open` to `claimed` and `claimed` to `completed`. Transition functions validate the current state,
require the relevant volunteer or resolution, record a UTC timestamp, and return a new ticket list
containing immutable replacement values. Missing tickets and invalid transitions raise stable
domain errors before persistence.

## Alternatives considered
- **Mutable dictionaries with ad hoc status strings** — shorter initially, but permit misspelled
  states, partial updates, and domain behavior that is hard to test or audit.
- **Allow direct `open` to `completed` transitions** — convenient for demos, but removes assignment
  attribution and weakens the lifecycle learners are meant to govern.
- **Put transition rules in CLI command handlers** — couples the domain to presentation and makes
  other callers responsible for reproducing the same validation.

## Consequences
Every valid state change is deterministic, attributable, and independently testable. Callers must
handle domain errors and persist the returned collection explicitly. New lifecycle states require
an intentional update to the model, transitions, fixtures, tests, and this decision's assumptions.

## Risks
The three-state lifecycle may become too small if Workshop Queue later models reassignment,
cancellation, or reopened work. Adding a state without defining every inbound and outbound
transition would make this decision incomplete and should reopen it.
