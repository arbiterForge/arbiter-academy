# Academy Preview release contract plan

**Spec:** `.codearbiter/specs/academy-preview-release-contract.md`
**Approval:** user-approved campaign checkpoint; SMARTS sprint approval recorded in `.codearbiter/sprint-log.md`

## Acceptance ledger

- AC-01: Exactly one generic Academy Preview target parses with the declared numeric policy and stable manifest.
- AC-02: No candidate tag is hard-coded in the declaration and exactly six safe asset names render.
- AC-03: The stable manifest begins at the immutable predecessor version 0.30.
- AC-04: Every current candidate surface agrees and is equal to or exactly one step ahead of the stable manifest.
- AC-05: The declared builder uses the release variables and Pages reproduction epoch.
- AC-06: Pre-tag commands are portable and check-only, cover the focused release and compatibility consumers plus indentation, exclude exhaustive local unittest discovery, and preserve the exact-head hosted shards as the exhaustive gate. While GitHub branch protection is absent, the governed merge operator must verify the successful `verify-candidate` aggregate at the exact PR head.
- AC-07: Focused, affected, helper, and governed validation pass with protected history preserved.
- AC-08: Manual three-job permissions and environment boundary.
- AC-09: Inert compatibility-data parsing and trusted helper-source binding.
- AC-10: Candidate, changelog, manifest, predecessor, tag, release, and exact-head CI preflight refusal.
- AC-11: Credential-free bounded asset build and transfer.
- AC-12: Write-token job runs no Academy code and verifies, tags, publishes, and reads back exact bytes and identities.
- AC-13: Resume is same-candidate and unpublished only; published history is never rewritten.
- AC-14: Mutation, affected-suite, shell, review, and hosted evidence are reported separately.
- AC-15: Maintainer guidance preserves implementation/settings/CI/merge/publication/deployment boundaries.

## Ordered tasks

| ID | Paths | Verification | Maps to | Covers | Depends on | Status |
|---|---|---|---|---|---|---|
| T-01 | `tests/test_release_declaration.py` | `python -m unittest tests.test_release_declaration -v` fails for the absent or policy-inconsistent declaration and manifest with assertions covering all seven criteria. | TDD Phase 1 red proof | AC-01, AC-02, AC-03, AC-04, AC-05, AC-06 | none | ACCEPTED |
| T-02 | `academy/release.json`, `.codearbiter/release-targets.md` | The T-01 focused suite passes; installed `_releaselib.py list-targets`, `show-row academy-preview`, and `render-release-assets 0.31 preview-0.31 ...` agree with the test oracle. The pre-tag row runs the bounded release and compatibility consumers plus tabnanny, while exact-head hosted shards own exhaustive discovery and the governed merge operator verifies their `verify-candidate` aggregate before merge. | TDD Phase 3 minimal green | AC-01, AC-02, AC-03, AC-04, AC-05, AC-06 | T-01 | ACCEPTED |
| T-03 | `tests/test_release_declaration.py`, `tests/test_release_assets.py`, `install/install.ps1`, `install/install.ps1.sha256`, existing affected release surfaces read-only | `python -m unittest tests.test_preview_manifest tests.test_codearbiter_compatibility tests.test_preview_site tests.test_pages_workflow tests.test_release_declaration tests.test_release_assets tests.test_foundations_labs.PreviewCompatibilitySourceTests -v` passes with the release, compatibility, workflow, and Windows module-path regressions; `python -m tabnanny academy_engine workshop_queue scripts tests` and `git diff --check` are clean. | TDD Phase 4 obligation verification plus regression-first `$ca-fix` for release-gate locality and the ambient `Get-FileHash` dependency exposed by the gate | AC-02, AC-04, AC-05, AC-06, AC-07 | T-02 | ACCEPTED |
| T-04 | `tests/test_release_workflow.py` | The workflow contract test fails against a preflight that imports `academy_engine` to choose the helper source, then rejects that regression and the existing security-relevant mutants independently. | TDD regression for the takeover security finding | AC-08, AC-09, AC-10, AC-11, AC-12, AC-13, AC-14 | T-03 | DONE |
| T-05 | `.github/workflows/academy-release.yml` | `python -m unittest tests.test_release_workflow -v` passes after preflight validates the version and parses the exact candidate manifest as inert JSON; every embedded Bash block passes `bash -n`. | Minimal hosted publisher implementation and security repair | AC-08, AC-09, AC-10, AC-11, AC-12, AC-13 | T-04 | DONE |
| T-06 | `docs/academy-maintenance.md`, affected release/workflow tests | The focused release/workflow suites, tabnanny, compileall, project-state check, diff check, and a bounded replay against the published Preview 0.32 assets pass; tampered installer, archive, and digest inputs fail for the intended reason. | Maintainer handoff and local obligation verification | AC-11, AC-12, AC-13, AC-14, AC-15 | T-05 | DONE |
| T-07 | GitHub repository settings, exact branch head, pull request and hosted checks | Owner-configured `academy-release` protection and `preview-*` tag rules are observed; the pushed exact head passes hosted CI and independent review before merge. Publication and Pages deployment remain a later explicit operation. | Delivery boundary | AC-08, AC-13, AC-14, AC-15 | T-06 | PENDING |

## MVP slice

T-01 through T-03 are the accepted declaration slice. T-04 through T-06 form the hosted-publisher implementation slice authorized on 2026-11-03. T-07 owns the separate settings and delivery boundary. A later dispatch, tag, GitHub Release, and Pages deployment are operational release actions, not evidence produced by this implementation branch.

## Bijection proof

Every AC is covered by at least one task and every task advances the declared release or publisher outcome. If every AC passed and nothing else changed, maintainers would have a declared Academy target and a fail-closed hosted publisher whose local implementation, repository settings, hosted qualification, and actual publication remain distinguishable. No task authorizes a tag, release, merge, or repository-setting mutation by implication.
