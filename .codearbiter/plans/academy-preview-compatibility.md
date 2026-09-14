# Academy Preview integration compatibility plan

**Spec:** `.codearbiter/specs/academy-preview-compatibility.md`
**Approval:** SMARTS-approved for autonomous sprint execution under SD-ACA-017, SD-ACA-019, SD-ACA-020, and active campaign checkpoint 043

## Acceptance ledger

- AC-01: Loading Preview 0.32 returns exactly three reviewed compatibility records and rejects missing, unknown, duplicate, malformed, floating, cross-release, cross-source, tag/version-mismatched, or invalid-digest data.
- AC-02: The local-checkout checker accepts only when every tag peels to the declared source and its component manifest version and raw-byte SHA-256 match.
- AC-03: Complete-ref freshness checking uses semantic numeric ordering for all three tag families and rejects stale declarations, including 0.9.9 versus 0.9.10.
- AC-04: Academy Verify and the existing Pages verifier derive the credential-free, full-history codeArbiter checkout from the declaration; Verify runs on pull request, schedule, and manual dispatch without a second source-SHA pin, and Pages preserves the same source contract on main.
- AC-05: The built site and generated release JSON expose all three exact records and state the release-and-command-contract evidence limitation accessibly.
- AC-06: Focused, affected, governance, and hosted validation pass while Preview 0.31 history and deferred PR #56 remain untouched.

## Ordered tasks

| ID | Paths | Verification | Maps to | Covers | Depends on | Status |
|---|---|---|---|---|---|---|
| T-01 | `tests/test_preview_manifest.py`, `academy/publication/preview-0.32.json`, `academy/publication/preview-manifest.schema.json` | `python -m unittest tests.test_preview_manifest -v` first fails for the absent compatibility contract and later passes all strict-schema cases. | TDD Phase 1 failing obligations and Phase 4 behavior proof | AC-01 | none | ACCEPTED |
| T-02 | `academy_engine/preview.py`, `academy/publication/preview-0.32.json` | `python -m unittest tests.test_preview_manifest -v` returns zero failures and exposes three immutable compatibility values through `PreviewManifest`. | TDD Phase 3 minimal implementation | AC-01 | T-01 | ACCEPTED |
| T-03 | `tests/test_codearbiter_compatibility.py` | `python -m unittest tests.test_codearbiter_compatibility -v` first fails because the checker is absent and covers tag peeling, manifest bytes, bounded diagnostics, semantic ordering, malformed refs, and stale declarations. | TDD Phase 1 failing obligations | AC-02, AC-03 | T-02 | ACCEPTED |
| T-04 | `scripts/check_codearbiter_compatibility.py`, `.github/workflows/academy-verify.yml`, `.github/workflows/academy-pages.yml`, `tests/test_pages_workflow.py`, `tests/test_foundations_labs.py` | `python -m unittest tests.test_codearbiter_compatibility tests.test_pages_workflow tests.test_foundations_labs.PreviewCompatibilitySourceTests tests.test_foundations_labs.PinnedTaskWriterTests -v` proves exact source verification, the pull-request/schedule/manual and main workflow contracts, and F03 source reuse with no duplicate source pin. | TDD Phase 3 implementation and Phase 4 integration proof | AC-02, AC-03, AC-04 | T-03 | ACCEPTED |
| T-05 | `tests/test_preview_site.py` | `python -m unittest tests.test_preview_site -v` first fails for absent generated JSON and accessible homepage compatibility output, then covers the evidence-limitation copy. | TDD Phase 1 failing obligations | AC-05 | T-02 | ACCEPTED |
| T-06 | `scripts/build_preview_site.py`, `scripts/check_preview_site.py`, `tests/test_preview_site.py` | `python -m unittest tests.test_preview_site tests.test_preview_manifest tests.test_codearbiter_compatibility tests.test_pages_workflow tests.test_release_declaration tests.test_release_assets -v` passes the complete affected local surface; exact-head hosted evidence remains the downstream PR gate. | TDD Phase 3 implementation and Phase 4 affected regression proof | AC-05, AC-06 | T-04, T-05 | ACCEPTED |

## MVP slice

T-01 through T-06 are one minimal shippable slice. The declaration without exact-source freshness enforcement would not satisfy the user’s rolling requirement; the checker without public rendering would not resolve the user-facing compatibility gap. No post-MVP embellishment is included.

## Delivery gate

All implementation tasks are accepted on fresh local proof. AC-06 remains open at the delivery boundary until the PR's exact-head hosted checks pass. The user explicitly authorized immutable Preview 0.32 publication on 2026-09-14; the release preparation must advance every current release-bound surface while preserving Preview 0.31, then use the ordinary PR, exact-head CI, merge, tag, asset, and Pages gates.

## Bijection proof

Every AC is covered by at least one task: AC-01 by T-01/T-02, AC-02 and AC-03 by T-03/T-04, AC-04 by T-04, AC-05 by T-05/T-06, and AC-06 by T-06. Every task advances at least one AC. Dependencies are acyclic. If every AC passed and nothing else changed, Academy would possess the exact rolling compatibility contract requested; the remaining codeArbiter-site gitlink update is an explicit separately bound campaign residual, not a missing Academy criterion.
