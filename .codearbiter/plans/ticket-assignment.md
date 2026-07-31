# Plan - Ticket assignment

- Spec: [ticket assignment](../specs/ticket-assignment.md)
- Status: approved fixture baseline
- Recorded: 2026-07-30 (fictional Academy fixture)

## Execution ledger

| ID | Task | Verification | Status |
| --- | --- | --- | --- |
| A-01 | Add assignment to the local ticket model. | Unit test proves assignment preserves state. | done fixture |
| A-02 | Validate assignment labels at the command boundary. | Unit test rejects control characters. | queued fixture |
| A-03 | Render an assignee in list output. | CLI test checks the visible local result. | queued fixture |
| A-04 | Inspect the deliberately stale hygiene task. | Learner classifies it through the board exercise. | in-progress fixture |

## Constraints and evidence

Keep work standard-library-only, local-first, and free of real personal or credential
material. Do not add a dependency while [the blocked dependency task](../open-tasks.md)
remains unresolved. Preserve [ADR-0002](../decisions/0002-explicit-ticket-state-machine.md).

This plan begins from [the baseline checkpoint](../checkpoints/2026-07-20-baseline.md)
and reports its initial outcome in [the baseline summary](../reports/2026-07-20-baseline/summary.md).
