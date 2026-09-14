# Changelog

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
