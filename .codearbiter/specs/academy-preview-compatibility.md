# Academy Preview integration compatibility

**Status:** approved for autonomous sprint execution
**Approved by:** SMARTS under the active campaign authority, the user's rolling-enforcement direction, and SD-ACA-017
**Governs:** `academy/publication/preview-*.json`, `academy/publication/preview-manifest.schema.json`, `academy_engine/preview.py`, `scripts/check_codearbiter_compatibility.py`, `.github/workflows/academy-verify.yml`, `.github/workflows/academy-pages.yml`, `scripts/build_preview_site.py`, `scripts/check_preview_site.py`, `tests/test_preview_manifest.py`, `tests/test_codearbiter_compatibility.py`, `tests/test_preview_site.py`, `tests/test_pages_workflow.py`, `tests/test_foundations_labs.py`

## Problem

Academy maintainers and learners cannot determine which exact published codeArbiter, ca-codex, and ca-pi artifacts a Preview was checked against, while hosted verification still pins an older unlabelled codeArbiter source commit. Done means every current Preview carries a strict, public, release-scoped compatibility declaration and maintainer CI fails when that declaration no longer names the newest published component releases or cannot reproduce their shared source identity.

## Approach

Extend the existing versioned Academy publication manifest with one closed-schema `integration_compatibility` object, then validate it both offline and against an exact full-history codeArbiter checkout in maintainer CI. This is preferable to a prose table or a second free-floating manifest because the declaration travels with the immutable Preview, feeds the generated site, and makes future Preview and adapter updates cross-check the same source of truth; it costs a small workflow and validator surface.

The declaration proves exact release and command-contract alignment, not unexecuted end-to-end behavior inside every host. The generated site must state that boundary instead of presenting the matrix as runtime certification.

## Scope

- Add an exact three-host compatibility declaration to `academy/publication/preview-0.32.json`, binding the Academy release, component names, release tags, semantic versions, shared source commit, component manifest paths, and component manifest SHA-256 values.
- Extend the Academy Preview loader with strict local schema, identifier, tag/version, digest, evidence-level, and shared-source validation for the declaration.
- Add a standard-library checker that validates the declared tags, tag commits, component manifests, versions, and digests against an exact codeArbiter Git checkout and rejects a declaration whose component tag is not the highest published release-tag version visible in that checkout.
- Make pull-request, scheduled, manual, and main Pages verification derive the codeArbiter checkout from the declaration, fetch full tag history, and run the compatibility checker instead of relying on the older hard-coded source SHA.
- Render the exact compatibility rows and their evidence limitation on the Academy homepage and generated `release.json`.

Out of scope: moving or rewriting the immutable Preview 0.31 tag; editing deferred PR #56; asserting end-to-end runtime compatibility that was not executed; changing codeArbiter release tags or manifests; adding learner runtime networking, dependencies, authentication, secrets, telemetry, or a hosted service; changing the verifier trust boundary; updating the codeArbiter site's Academy gitlink in this separately bound checkpoint. The user explicitly extended this checkpoint on 2026-09-14 to publish the resulting compatibility contract as immutable Preview 0.32 through the existing release lane.

## Decided parameters

- The declaration lives inside each versioned `academy/publication/preview-*.json`; `academy/release.json` remains the generic release lane's stable version pointer.
- The three component IDs are `codearbiter`, `ca-codex`, and `ca-pi`; display names preserve `codeArbiter`, `Codex`, and `Pi` where user-facing.
- Preview 0.32 records `v2.17.11`, `ca-codex-v0.9.11`, and `ca-pi-v0.10.13`, all peeled to `d6900d96f0b61f66d420b6a424fddfd89ac0f71e`; Preview 0.31 remains unchanged at its published tag.
- The component manifest paths are `plugins/ca/.claude-plugin/plugin.json`, `plugins/ca-codex/.codex-plugin/plugin.json`, and `plugins/ca-pi/package.json`.
- The exact manifest SHA-256 values are `6834bcd5628e3e2183ed4643ea129fd0f2e0fb3e942abdd48bd885162f5de964`, `9df49b76696cd7e008ebc2f976292825012d001f8d8e89f580104e34e3bb23c5`, and `5f6596c90d4341a0a6a8a1f71a5f4126abc6aa8b2ed6aefe69c03df44ab68fb4` respectively.
- The evidence level is `release-and-command-contract`; public copy explicitly says this is not end-to-end host certification.
- Highest-version comparison is semantic numeric ordering within each approved tag prefix, never lexicographic ordering and never a floating `latest` reference.
- Maintainer verification may fetch the public codeArbiter Git repository with credentials disabled; learner execution remains offline.
- The existing SHA-256 release-integrity control and installed-verifier trust boundary are conformed to, not superseded.

## Acceptance criteria

1. Loading Preview 0.32 returns exactly three ordered compatibility records whose Academy release, component IDs, tags, versions, shared source commit, manifest paths, manifest digests, and `release-and-command-contract` evidence level equal the reviewed values in this spec; the local loader rejects missing, unknown, duplicate, malformed, floating, cross-release, cross-source, tag/version-mismatched, or invalid-digest data.
2. Given a local codeArbiter Git checkout with the declared tags, the checker peels every tag to the one declared source commit, reads each declared component manifest from that tag, and accepts only when its version and raw-byte SHA-256 match the declaration; a wrong tag target, path, version, or digest fails with a bounded diagnostic.
3. Given complete tag refs, the checker compares semantic numeric versions within `v`, `ca-codex-v`, and `ca-pi-v` families and fails when any declared component is behind the highest visible release tag, including the `0.9.9` versus `0.9.10` ordering case.
4. Academy Verify runs on pull requests, a bounded schedule, and manual dispatch, while the existing Pages verifier covers main publication; both read the source commit from the validated Preview declaration, check out that exact public codeArbiter commit with complete tag history and credentials disabled, and run the compatibility checker with no separately hard-coded source SHA.
5. Building the Academy site emits the complete compatibility object in generated `release.json` and renders one accessible homepage row per component with exact version and tag plus adjacent language that limits evidence to release and command contracts rather than end-to-end host execution.
6. Focused compatibility, Preview-manifest, generated-site, and workflow contract tests pass; indentation, compile, project-state, secret-scan, affected release/Page checks, and current required Academy CI remain green without touching Preview 0.31 history or PR #56.

## Open questions

None. The campaign record supplies the rolling-enforcement direction, exact-version requirement, proof boundary, repository boundary, and standing execution authority. Accepted ADR-0003 remains unchanged because this feature describes release compatibility evidence and does not turn Academy receipts into cryptographic attestation.

## Adversarial review

The strongest failure case is calling newest-tag alignment “compatibility” without exercising every host. The design survives only by naming its evidence `release-and-command-contract`, showing that limitation publicly, and leaving end-to-end cells unclaimed. The most fragile criterion is highest-tag detection: it must use numeric version parsing over complete refs and reject malformed or ambiguous family members without treating lexicographic order as release order. The assumption most likely to invalidate the approach is that the three public release tags continue to share one source commit; the checker deliberately fails if that stops being true so maintainers must record an explicit multi-source model rather than silently weakening the proof.
