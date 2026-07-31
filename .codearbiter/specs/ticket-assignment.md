# Specification - Ticket claim

- Status: approved fixture baseline
- Recorded: 2026-07-30 (fictional Academy fixture)
- Domain: Workshop Queue
- Governing decision: [ADR-0002](../decisions/0002-explicit-ticket-state-machine.md)

## Problem

A facilitator needs to claim a locally stored workshop ticket for an Academy role
without confusing the claim transition with lifecycle completion.

## Acceptance criteria

1. `claim_ticket` moves an open ticket to claimed and records `claimed_by` with a UTC claim time.
2. Claiming does not complete the ticket; completion remains a separate claimed-to-completed transition.
3. Control-character validation for claimant labels is queued work, not baseline-complete behavior.
4. Learner-visible rendering of `claimed_by` is queued work and must not expose JSON storage details.
5. The behavior needs no network access or added runtime package.

## Boundaries

This is local-only: no accounts, notifications, remote sync, payment, or credential
handling. Persistence remains governed by [ADR-0001](../decisions/0001-json-storage-boundary.md)
and controls remain in [security controls](../security-controls.md).

## Evidence

The [implementation plan](../plans/ticket-assignment.md) maps each criterion to
verification. Starting review posture is in [the baseline checkpoint](../checkpoints/2026-07-20-baseline.md).
