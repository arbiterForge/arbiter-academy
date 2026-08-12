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

## SD-ACA-005 - Verify the immutable release from its tagged source - confidence: high

- Date: 2026-08-11
- Point: Whether post-release Academy lesson work should rebuild Preview 0.5 installer assets from the mutable candidate, or whether Pages should verify the already-published tagged source while rendering the reviewed candidate site.
- Options: regenerate Preview 0.5 installer checksums from every candidate; keep the candidate-versus-tag release-bound path block; verify the immutable tagged source and public release assets exactly, while allowing later reviewed candidates whose public manifest still exposes only accepted lessons.
- SMARTS: Safety and Security favor retaining tag ancestry, immutable-release state, authenticated and public asset downloads, checksum validation, and byte-for-byte reproduction from the detached tag source. Maintainability favors one authority for a published release rather than a mutable checkout. Reviewability favors tests that materialize the tag and prove candidate-source rebuilding cannot return. Simplicity and Speed favor removing the overbroad post-tag path denylist so accepted non-routable lesson work can land without claiming a new release.
- Chosen: Pages verifies Preview 0.5 from its immutable tag source and assets. The candidate must descend from that tag, but later Academy source changes do not retarget released installers or alter their byte identity.

## SD-ACA-007 - Keep private candidate work separate from immutable release assets - confidence: high

- Date: 2026-08-12
- Point: Whether a non-routable Academy lesson change must rebuild the current preview installer bytes, after PR #19 correctly showed that a candidate wheel has a different bundle digest while Preview 0.6 remains immutable.
- Options: require a new preview for every packaged source change; weaken the builder digest check; reproduce the already published preview from its immutable tag while separately proving that a private candidate has not entered the public manifest.
- SMARTS: Safety and Security retain immutable tag ancestry, byte-for-byte asset reproduction, and the builder's exact installer digest check. Maintainability and Speed let reviewed private guided content merge without release churn. Reviewability and Testability require one tagged-source fixture, a private-candidate mutation regression, and a fresh preview whenever public routes or installable bytes change.
- Chosen: published-release asset and installer-behavior tests materialize the current immutable tag. Candidate builder tests remain fail-closed. A new preview is required for any public manifest route, installer, or installable-payload change; non-routable guided content may merge only while the candidate manifest still keeps it unavailable.

## SD-ACA-008 - Clarify candidate drift versus published release payload - confidence: high

- Date: 2026-08-12
- Point: Whether SD-ACA-007's payload boundary could be read to require a new preview for a private lesson edit that changes only a hypothetical future candidate wheel.
- Options: treat every candidate bundle-digest change as published-payload drift; allow an ambiguous exception; distinguish the immutable published release payload from mutable candidate source payload.
- SMARTS: Safety and Security keep installer digest checks fail-closed for the published tag and require a new preview for any released installer, release bundle, or public route change. Maintainability and Speed permit private non-routable source development without pretending its future wheel is already public. Reviewability and Testability bind Preview 0.6 to its reviewed tag commit, reject missing or retargeted tags, and prove a private candidate mutation remains outside the public manifest.
- Chosen: a private source edit may change a candidate-only future wheel without release churn while it remains non-routable. A new preview is required before any change becomes part of the published release payload, installer bytes, or public lesson catalog.
