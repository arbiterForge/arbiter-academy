# Specification - Ticket assignment

- Status: approved fixture baseline
- Recorded: 2026-07-30 (fictional Academy fixture)
- Domain: Workshop Queue
- Governing decision: [ADR-0002](../decisions/0002-explicit-ticket-state-machine.md)

## Problem

A facilitator needs to assign a locally stored workshop ticket to an Academy role
without confusing assignment with lifecycle completion.

## Acceptance criteria

1. Assigning a valid local role records that role on the selected ticket.
2. Assignment preserves the ticket's explicit lifecycle state.
3. Invalid or control-character-bearing assignment labels are rejected locally.
4. List output can show an assignee without exposing JSON storage details.
5. The behavior needs no network access or added runtime package.

## Boundaries

This is local-only: no accounts, notifications, remote sync, payment, or credential
handling. Persistence remains governed by [ADR-0001](../decisions/0001-json-storage-boundary.md)
and controls remain in [security controls](../security-controls.md).

## Evidence

The [implementation plan](../plans/ticket-assignment.md) maps each criterion to
verification. Starting review posture is in [the baseline checkpoint](../checkpoints/2026-07-20-baseline.md).
