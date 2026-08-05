# Open tasks - Workshop Queue Academy fixture

All dates, statuses, and roles below are fictional Academy fixtures. The task board
uses `queued -> in-progress -> done`; a blocked item remains queued with its blocker
stated explicitly.

## Queued

- [ ] academy.feature.0001 - Show a claimant in ticket list output
  - Desc: Render the existing `claimed_by` value promised by the [claim specification](specs/ticket-assignment.md).
  - Done when: A locally seeded claimed ticket displays its claimant without exposing storage internals.
  - Boundaries: CLI, local JSON
  - Curriculum lane: feature
  - Evidence: [ticket-assignment plan](plans/ticket-assignment.md)

- [ ] academy.feature.0002 - Show unresolved tickets in the summary
  - Desc: Add the caller-visible unresolved count to the Workshop Queue JSON report.
  - Done when: The JSON report returns unresolved as the exact total of open and claimed tickets.
  - Boundaries: workshop_queue/cli.py, tests/test_cli.py
  - Curriculum lane: feature
  - Evidence: [Academy feature plan](plans/academy-feature.md)

- [ ] academy.security.0004 - Reject control characters in a claimant label
  - Desc: Extend local claim validation while retaining [ADR-0002](decisions/0002-explicit-ticket-state-machine.md).
  - Done when: A control-character claimant is rejected and ordinary Academy names remain accepted.
  - Boundaries: model, validation
  - Curriculum lane: security
  - Evidence: [baseline checkpoint](checkpoints/2026-07-20-baseline.md)

- [ ] academy.release.0006 - Prepare Academy fixture release notes
  - Desc: Draft local-only release notes after open training lanes have evidence.
  - Done when: Notes distinguish fixture evidence from a published release and no publish command is run.
  - Boundaries: documentation, release
  - Curriculum lane: release
  - Evidence: [baseline summary](reports/2026-07-20-baseline/summary.md)

## In progress

- [~] academy.fixture.0002 - Reconcile the deliberately stale claim spike (started 2026-07-12)
  - Desc: A controlled stale item for the hygiene lab; learners decide whether its evidence supports completion or re-scoping.
  - Done when: The learner records a dated outcome through the task-board exercise.
  - Boundaries: task board, hygiene
  - Curriculum lane: fix
  - Scenario: deliberate Academy hygiene fixture; stale by design for the hygiene lab.
  - Evidence: [baseline checkpoint](checkpoints/2026-07-20-baseline.md)

## Blocked

- [ ] academy.dependency.0003 - Evaluate a fictional CSV export helper
  - Desc: Intentionally blocked until the dependency-review lab supplies fabricated provenance and license evidence.
  - Done when: The lab records an approved stdlib alternative or reviewed fictional dependency decision.
  - Boundaries: dependency, supply chain
  - Curriculum lane: dependency
  - Status: BLOCKED - training evidence has not yet been supplied.
  - Evidence: [security controls](security-controls.md)

## Done

- [x] academy.decision.0005 - Record explicit assignment lifecycle (done 2026-07-30)
  - Desc: The baseline chose a visible state machine over inferred ticket state.
  - Done when: The decision and learner-facing implications are linked from this board.
  - Boundaries: decision, model
  - Curriculum lane: decision
  - Evidence: [ADR-0002](decisions/0002-explicit-ticket-state-machine.md)
