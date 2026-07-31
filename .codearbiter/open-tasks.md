# Open tasks - Workshop Queue Academy fixture

All dates, statuses, and roles below are fictional Academy fixtures. The task board
uses `queued -> in-progress -> done`; a blocked item remains queued with its blocker
stated explicitly.

## Queued

- [ ] academy.feature.0001 - Show an assignee in ticket list output
  - Desc: Add the learner-visible read model promised by the [assignment specification](specs/ticket-assignment.md).
  - Done when: A locally seeded assigned ticket displays its assignee without exposing storage internals.
  - Boundaries: CLI, local JSON
  - Curriculum lane: feature
  - Evidence: [ticket-assignment plan](plans/ticket-assignment.md)

- [ ] academy.security.0004 - Reject control characters in an assignee label
  - Desc: Extend local input validation while retaining [ADR-0002](decisions/0002-explicit-ticket-state-machine.md).
  - Done when: A control-character label is rejected and ordinary Academy names remain accepted.
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

- [~] academy.hygiene.0002 - Reconcile the deliberately stale assignment spike (started 2026-07-12)
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
