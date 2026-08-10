# Baseline report - 2026-07-20

All historical content in this report is a fictional Academy fixture. It summarizes
the pre-staged Workshop Queue state that later labs inspect and mutate. Recorded:
2026-07-30 (fictional Academy fixture); the dated report path is a reset-scenario label.

## Contract status

The repository is initialized at stage 2 with `arbiter: enabled`. Workshop Queue is
local-first, standard-library-only, and AGPL-3.0-only. Claiming follows
[ADR-0002](../../decisions/0002-explicit-ticket-state-machine.md) over the local
storage boundary in [ADR-0001](../../decisions/0001-json-storage-boundary.md).

## Evidence chain

1. [Ticket-assignment specification](../../specs/ticket-assignment.md) defines behavior.
2. [Ticket-assignment plan](../../plans/ticket-assignment.md) maps it to verification.
3. [Baseline checkpoint](../../checkpoints/2026-07-20-baseline.md) records architecture,
   domain, security, dependency, and hygiene posture.
4. [Open tasks](../../open-tasks.md) holds queued, in-progress, blocked, and done examples.

## Concerns retained for labs

- The stale `academy.fixture.0002` task is deliberate training data, not a live failure.
- The dependency task is blocked pending fictional review evidence; it does not block
  the current staged fixture.
- Prompts in [open questions](../../open-questions.md) are not unresolved product or
  security decisions.
