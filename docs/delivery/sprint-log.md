# Arbiter Academy delivery sprint log

This is the append-only delivery record for the public `arbiterForge/arbiter-academy`
repository. It records real maintainership decisions. It is deliberately separate from
`.codearbiter/sprint-log.md`, which is a fictional Workshop Queue teaching fixture.

## SD-ACA-001 - Bind F02 orientation evidence to one preserved attempt - confidence: high

- Date: 2026-08-11
- Point: Whether F02 should describe the existing permissive orientation checkpoint or
  strengthen the checkpoint before the lesson becomes public.
- Options: preserve the permissive checkpoint and narrow the lesson; require only a
  valid orientation record; require one orientation-record commit, an unchanged prepared
  context blob, and a clean worktree.
- SMARTS: Security, Maintainability, Reviewability, Testability, and Safety favor the
  bounded attempt. A public lesson must prove the evidence boundary it teaches, preserve
  a failed attempt for recovery, and reject unrelated or post-orientation state.
- Chosen: strengthen F02 before publication. Check will require exactly the orientation
  record in the learner evidence commit, the prepared context bytes unchanged, and a
  clean worktree at verification time.

## SD-ACA-002 - Publish each guided slice as an immutable preview - confidence: high

- Date: 2026-08-11
- Point: Whether F02 may change the already published Preview 0.4 release identity or
  should receive a new immutable preview release.
- Options: mutate Preview 0.4; delay F02 until the complete course; publish F02 as
  Preview 0.5 with refreshed checked-in installers and release assets.
- SMARTS: Security and Safety reject mutable installer bytes under an existing release
  identity. Maintainability and Reviewability favor a small, named public slice that
  maps one publication manifest to one verified asset set. Testability remains bounded
  because F02 promotion can prove its own route and verifier without waiting for F03.
- Chosen: publish F02 only as a new immutable Preview 0.5 release after its guided
  page, verifier, assets, and hosted exact-head checks are accepted.

## SD-ACA-004 - Encode F04 as an executable evidence sequence - confidence: high

- Date: 2026-08-11
- Point: Whether the public F04 lesson should remain a prose walkthrough or use the
  Academy action contract to guide and verify a real red-to-green, two-commit fix.
- Options: retain raw prose; make the operations TUI the primary lesson surface; publish
  a website-first structured lesson with terminal, harness, and CodeArbiter actions
  explicitly separated.
- SMARTS: Safety and Security favor an isolated prepared attempt, a test-only commit
  before the repair, a service-only repair commit, and a Check that rejects broad or
  unreachable changes. Maintainability and Testability favor one manifest shared by the
  rendered guide and contract tests. Reviewability favors visible actor, surface,
  expected-result, evidence, and recovery fields for every learner action. Simplicity
  and Speed favor a small operations TUI only for prepare/check/reset/return rather
  than a second instructional interface.
- Chosen: author F04 as a website-first, structured nineteen-action lesson; native
  terminal commands, harness prompts, and agent CodeArbiter commands are unambiguous,
  while the TUI remains limited to attempt lifecycle operations.
