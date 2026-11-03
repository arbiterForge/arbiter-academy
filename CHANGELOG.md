# Changelog

## [0.33] — 2026-11-03

### Added

- Publish Academy Preview releases through a protected hosted workflow.

### Fixed

- Flag F04, P05, P01, U01 and U04 for review when the task board library or the Markdown references change.
- Accept only lane work items the commit gate keeps, and ask the P01 feature lane not to record a separate item.
- Keep the P01 task-board check as it was in Preview 0.32.
- Accept the sprint's work item in U01 when it names the committed specification and plan.
- Accept the fix lane's queued work item in the F04 and P05 repair commits.
- Rebind the lesson source map to codeArbiter 27e6cb12 and drop the deleted sources.
- Stop teaching the retired preview, question and metrics commands in U06, P04 and U02.
- Bind Preview 0.33 to the codeArbiter 3.8.3, ca-codex 0.26.3 and ca-pi 0.27.3 release cohort.
- Teach current Arbiter workflows with clear practical lessons and source drift checks.
- Use codeArbiter in current Academy copy and require future Previews to retain it.

## [0.32] — 2026-09-14

### Added

- Publish and enforce the Preview adapter compatibility matrix.

### Fixed

- Prepare Academy Preview 0.32 release assets and Pages identity for rolling adapter compatibility.
- Keep local Preview pre-tag validation focused while exact-head GitHub CI runs the exhaustive matrix.

## [0.31] — 2026-09-14

### Added

- Add a governed Academy Preview release target with exact six-asset publication policy.

### Fixed

- Keep Preview 0.30 installers bound to their exact bundle.
- Make the F03 handoff safely confirm main before F04.
- Standardize mutable Academy product copy on codeArbiter without changing command bytes.
- Prepare Academy Preview 0.31 release assets and Pages identity for the current guided curriculum.
- Align Preview 0.31 command and visual verification baselines with the immutable release candidate.
- Academy bootstrap commands now verify the reviewed installer digest before execution.
- Academy setup now verifies tagged installers against exact digests embedded in the reviewed public page.
- Make the Windows Preview installer verify release hashes reliably across environment-key casing variants.
- Make Academy Preview release checks reusable across versions.
- Reconcile the malformed Academy Preview release footer through the exact-SHA release ledger.
- Make Academy release validation portable across Git Bash and WSL on Windows.
