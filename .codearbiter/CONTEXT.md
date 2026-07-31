---
arbiter: enabled
stage: 2
---
<!--INITIALIZED-->

# Project: Workshop Queue

Workshop Queue is a local-first Python application used in Arbiter Academy labs.
It records, assigns, and moves teaching tickets through a small explicit lifecycle.
This directory is a pre-staged Academy fixture: learners inspect, reset, mutate,
review, and audit it during later labs.

## Fixture identity

- Product steward: Academy Facilitator (fictional Academy role).
- Historical records: all dates, events, findings, and names in this state are
  fictional Academy fixtures, not evidence about a live service or person.
- Runtime: Python 3 with the standard library only; the root license is AGPL-3.0-only.

## Scope and boundaries

- Durable ticket data is local JSON under an operator-selected application-data root.
- Assignment behavior is defined by the [ticket-assignment specification](specs/ticket-assignment.md)
  and [implementation plan](plans/ticket-assignment.md).
- The JSON boundary is recorded by [ADR-0001](decisions/0001-json-storage-boundary.md);
  lifecycle rules are recorded by [ADR-0002](decisions/0002-explicit-ticket-state-machine.md).

## Not this project

Workshop Queue is not a hosted ticketing service, identity system, payment system,
or team chat. Academy exercises use only fabricated ticket content and need no
network connection or credential.

## Governing artifacts

- [Coding standards](coding-standards.md)
- [Technology and verification commands](tech-stack.md)
- [Security controls](security-controls.md)
- [Open task board](open-tasks.md)
- [Academy training questions](open-questions.md)
