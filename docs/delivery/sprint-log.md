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

## SD-ACA-003 - Promote F03 through an immutable Preview 0.6 - confidence: high

- Date: 2026-08-11
- Point: Whether to leave the completed F03 guided lesson private until the full Academy
  course is ready, mutate Preview 0.5, or publish the reviewed F01-F03 sequence as a
  successor release.
- Options: defer F03; mutate Preview 0.5; publish F03 as Preview 0.6 with a fresh
  manifest, installers, release assets, Pages contract, and exact-head hosted checks.
- SMARTS: Safety and Security reject changing a previously reviewed installer identity.
  Maintainability and Reviewability favor a small immutable addition whose one-commit
  verifier contract is independently testable. Testability and Scope favor releasing a
  finished third lesson now while F04 and later lessons remain explicitly unavailable.
- Chosen: publish F03 only as Preview 0.6 after its guide, action contract, strict
  checkpoint, release assets, and hosted exact-head checks are accepted. Preview 0.5
  remains an immutable historical release.
