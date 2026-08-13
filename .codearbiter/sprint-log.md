# Sprint log - Workshop Queue Academy fixture

Append-only. Historical records below are fictional Academy fixtures. Entries show
the SMARTS rationale learners inspect; they do not describe a live sprint.

## SD-01 - Keep assignment evidence local and linked - confidence: high
- Date: 2026-07-18 (fixture)
- Point: Whether assignment should simulate a remote queue or remain a local JSON workflow.
- Options: local JSON fixture; simulated remote service; defer the exercise.
- SMARTS: Reliable, Available, and Securable favor local JSON because it is
  inspectable offline and introduces no credentials or network boundary.
- Chosen: local JSON fixture, recorded in [ADR-0001](decisions/0001-json-storage-boundary.md).

## SD-02 - Use an explicit lifecycle - confidence: high
- Date: 2026-07-19 (fixture)
- Point: Whether assignment implies ticket state or state remains a visible field.
- SMARTS: Testable and Maintainable favor a visible state machine.
- Chosen: explicit states, recorded in [ADR-0002](decisions/0002-explicit-ticket-state-machine.md).
## SD-03 - Reconcile fixture chronology - confidence: high
- Date: 2026-07-30 (fixture record)
- Point: SD-01 and SD-02 retain their reset-scenario dates while their governing ADRs
  were formally recorded on 2026-07-30.
- SMARTS: Reliable and Reviewable favor preserving the original scenario records and
  appending their recorded-date relationship instead of rewriting append-only history.
- Chosen: The scenario dates remain teaching metadata; all formal decision, spec,
  plan, checkpoint, report, and done-task records use 2026-07-30.

## SD-ACA-007 - Bound U01 to an autonomous documentation sprint - confidence: high
- Date: 2026-08-12
- Point: Whether U01 should remain a private guide with no completion proof or gain a deterministic
  first verifier while the broader Power User route remains private.
- Options: keep the false-returning profile; accept arbitrary sprint artifacts; require one bounded
  documentation packet with a prepared brief, exact path boundary, append-only log, and clean history.
- SMARTS: Reliable and Testable favor the bounded packet because it proves durable repository facts
  without inventing approval or host telemetry. Maintainable favors the existing shared scenario,
  action-manifest, and Check layers. Available and Securable favor a local documentation change with
  no network, dependency, credential, or push requirement.
- Chosen: implement the bounded U01 source contract now and keep it private until packaging, routing,
  browser, and hosted-release acceptance establish a public lesson boundary.


## SD-ACA-008 - Promote U06 with repository-fact evidence only - confidence: high
- Date: 2026-08-13
- Point: Whether the public U06 lesson should preserve hand-authored preview telemetry or bind only durable repository facts after the real read-only ca-preview advisory step.
- Options: retain invented reviewer/scan fields; keep U06 private; publish the accepted two-commit candidate and Academy binding record while explicitly excluding invocation and telemetry claims.
- SMARTS: Reliable, Testable, and Securable favor the bounded repository record because it can be reproduced from committed state without claiming a host result. Available and Maintainable favor the existing installed Prepare/Check/Reset lifecycle and explicit public package inventory.
- Chosen: publish U06 in Preview 0.19 with real host-native ca-preview guidance, a public route, deterministic package assets, and U07 as the sole non-linking coming-next lesson.
