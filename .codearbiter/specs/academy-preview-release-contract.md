# Academy Preview release contract

**Status:** approved
**Approved by:** user, through the active campaign checkpoint and the recorded 2026-09-13 Academy release authorization
**Governs:** `.codearbiter/release-targets.md`, `academy/release.json`, `tests/test_release_declaration.py`

## Problem

Arbiter Academy has a prepared Preview 0.31 candidate and a deterministic six-asset build, but the installed release lane cannot act because the repository has no unambiguous declared release target. Maintainers need one repository-owned declaration that lets the generic release mechanism derive future Preview identities without confusing the browser tooling package or Workshop Queue fixture version for the Academy release.

## Approach

Declare one `academy-preview` target with the existing `preview-` namespace, the generic two-component `numeric-sequence` policy, a dedicated release-state JSON manifest, exact asset templates, and the existing deterministic builder. A focused repository test binds the declaration to the current candidate workflow while permitting exactly the two valid lifecycle states: the manifest equals the prepared candidate during publication, or trails it by one final component before the release bump.

This adds a small explicit release-state file instead of overloading `package.json`, `pyproject.toml`, or a version-named publication manifest. The extra file costs one maintained datum but preserves the established meanings of those existing files and gives the release lane a stable, version-agnostic manifest path.

The user extended this contract on 2026-11-03 with the instruction "Yes build the publisher." The hosted phase is a manually dispatched, three-job GitHub Actions workflow. A read-only `preflight` binds the exact main commit, release declaration, changelog section, immutable predecessor, and exact-head Pages evidence; a read-only `build` job runs the declared builder without a credential; and an environment-gated `publish` job receives the write token, verifies the transferred assets against committed installer bytes, creates the immutable tag and release, and reads both back. The helper source is selected by parsing the candidate's committed compatibility JSON as inert data and proving that commit is on codeArbiter `main`; Academy code never runs while selecting that trust source or beside the write token.

## Scope

- Add the marker-gated `.codearbiter/release-targets.md` declaration for the Academy Preview series.
- Add `academy/release.json` as the stable release manifest, initially recording the immutable predecessor version `0.30`.
- Add focused tests for policy shape, exact six-asset templates, current-candidate synchronization, and the absence of a `preview-0.31` literal from shared declaration structure.
- Validate the row through the installed 0.10.0 release helper and preserve all existing Academy verification.
- Add a manually dispatched hosted publisher for the declared `academy-preview` target, with read-only preflight/build jobs and one environment-gated write job.
- Add mutation-based contract tests and maintainer documentation for safe dispatch, exact-head evidence, resume behavior, and immutable publication.

Out of scope: changing learner behavior, modifying Preview 0.30, editing deferred PR #56, publishing or tagging from this implementation commit, introducing a second release series, changing the Workshop Queue package version, replacing the existing asset builder, or weakening Pages identity checks.

The hosted implementation also excludes automatically dispatching publication, publishing from a pull request or fork, changing repository settings without owner authority, moving or deleting a published tag/release, storing a long-lived release credential, and treating local checks as hosted workflow proof.

## Decided parameters

- Target name: `academy-preview`; display name: `Arbiter Academy Preview`.
- Tag prefix: `preview-`; version policy: `numeric-sequence`; initial version: `0.1`.
- Stable manifest: `academy/release.json`; predecessor value before the release bump: `0.30`.
- Payload: the repository root, because the Preview bundle and course surface span the repository.
- Changelog: `CHANGELOG.md`, created by the release lane when Preview 0.31 is cut.
- The exact asset inventory is the two installers, their two checksum files, the version-templated Academy ZIP, and its checksum.
- The release build invokes the existing deterministic builder with the reviewed Preview 0.31 epoch; changing that operator-authored command invalidates the release-command confirmation hash.
- Pre-tag checks run the focused release and compatibility consumers plus the Python indentation check through the resolved interpreter. The pull request's exact-head hosted shards own the exhaustive test inventory; until repository settings enforce that check, the governed merge operator must verify the `verify-candidate` aggregate at the exact PR head before merge.
- This sole declared series is eligible for the repository's Latest release badge.
- Hosted publication is maintainer-dispatched from `main`, queues concurrent requests, and fails closed if `main` moves after dispatch.
- Only the `publish` job receives `contents: write`; the asset build receives no GitHub token, and the write-token job runs no Academy repository code.
- The helper commit is read directly from `academy/publication/preview-<version>.json`, must be one shared 40-hex source across all compatibility components, and must be proven reachable from codeArbiter `main` before its release helper is used.
- The publisher can resume only when the annotated tag already resolves to the same candidate and no GitHub Release exists. Published tags and releases remain immutable.

## Acceptance criteria

1. The installed release helper parses exactly one `academy-preview` target whose prefix is `preview-`, policy is `numeric-sequence`, initial version is `0.1`, stable manifest is `academy/release.json`, payload is `.`, and latest eligibility is true.
2. The declaration contains no literal `preview-0.31` or other single candidate tag and renders exactly six safe asset names for version `0.31`, including the version-templated ZIP and checksum.
3. The stable manifest is valid JSON with canonical string version `0.30`, matching the latest immutable `preview-0.30` tag before the release lane advances it.
4. The current prepared candidate identity read from the Pages workflow, publication manifest, README heading, release-asset tests, and package-data path is identical and is either the manifest identity or exactly one final-component increment beyond it; malformed, regressing, skipped, or shape-changing identities fail.
5. The declared build command targets the existing deterministic builder, supplies the release lane's exact tag and empty asset directory variables, and uses the same reviewed epoch as the Pages reproduction gate.
6. The declared pre-tag commands are check-only and interpreter-portable, cover the focused release and compatibility consumers plus the repository indentation check, do not invoke exhaustive unittest discovery locally, and leave the exhaustive inventory to the pull request's exact-head hosted shards. The governed merge operator treats a successful `verify-candidate` aggregate at that exact head as a mandatory procedural gate while GitHub branch protection is absent.
7. Focused declaration tests, the installed helper's row parsing and asset rendering, the affected release and Pages tests, and the repository's required governed validation all pass without changing Preview 0.30 or PR #56.
8. The workflow has only manual dispatch and exactly three jobs: read-only `preflight`, credential-free read-only `build`, and environment-gated `publish` with the sole `contents: write` permission.
9. Preflight validates the version before reading `academy/publication/preview-<version>.json` from the exact candidate commit, treats it as JSON data without importing Academy code, requires exactly three compatibility components with one shared 40-hex source commit, and proves that source belongs to codeArbiter `main`.
10. Preflight refuses a moved `main`, a candidate that did not introduce the requested changelog section, mismatched manifests, a non-increasing version, a mutable predecessor, an existing release, a conflicting tag, or incomplete exact-head `Academy Pages` push evidence.
11. Build runs the declared release builder once with read-only repository permission and no token, verifies the six declared assets, and transfers only that bounded artifact set to publication.
12. Publish runs no Academy code, verifies the downloaded installers and checksums byte-for-byte against the candidate, binds the archive digest into both installers, composes and checks the annotated tag, pushes by full refspec without hooks or force, publishes with the committed changelog section, and reads back the immutable release, tag object, candidate commit, and every asset digest.
13. A retry may resume only from an unpublished tag at the same candidate; no workflow path moves, deletes, or replaces a published tag or release.
14. Static contract tests reject each security-relevant weakening independently, related release/workflow suites pass locally, every shell block parses, and exact-head hosted CI plus independent review remain pending until the branch is pushed.
15. Maintainer documentation distinguishes implementation, repository settings, exact-head CI, merge, dispatch, publication, and Pages deployment, and does not imply that this implementation itself publishes Preview 0.33.

## Open questions

No implementation choice is open. On 2026-11-03 the owner authorized the full release path, and live repository configuration established the two settings outside this diff: an `academy-release` environment with a required reviewer and `main`-only deployment branches, and an active `preview-*` tag ruleset that blocks deletion and non-fast-forward updates without bypass actors. Exact-head hosted CI, merge, dispatch, publication read-back, and Pages qualification remain separate observed gates.

## Adversarial review

The strongest failure case is a manifest that is technically parseable but drifts from the many prepared-candidate surfaces. AC-04 makes that state machine explicit and rejects any gap larger than one release step. The riskiest assumption is that the fixed build epoch belongs in operator-reviewed release data rather than derived from the release commit; the existing Pages byte-reproduction contract already fixes that exact epoch, so reusing it is required for Preview 0.31 and any later change will invalidate the release-command confirmation hash.
