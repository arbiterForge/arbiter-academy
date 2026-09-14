# Academy Preview release contract plan

**Spec:** `.codearbiter/specs/academy-preview-release-contract.md`
**Approval:** user-approved campaign checkpoint; SMARTS sprint approval recorded in `.codearbiter/sprint-log.md`

## Acceptance ledger

- AC-01: Exactly one generic Academy Preview target parses with the declared numeric policy and stable manifest.
- AC-02: No candidate tag is hard-coded in the declaration and exactly six safe asset names render.
- AC-03: The stable manifest begins at the immutable predecessor version 0.30.
- AC-04: Every current candidate surface agrees and is equal to or exactly one step ahead of the stable manifest.
- AC-05: The declared builder uses the release variables and Pages reproduction epoch.
- AC-06: Pre-tag commands are portable, check-only, and cover unittest plus indentation.
- AC-07: Focused, affected, helper, and governed validation pass with protected history preserved.

## Ordered tasks

| ID | Paths | Verification | Maps to | Covers | Depends on | Status |
|---|---|---|---|---|---|---|
| T-01 | `tests/test_release_declaration.py` | `python -m unittest tests.test_release_declaration -v` fails for the absent declaration and manifest with assertions covering all seven criteria. | TDD Phase 1 red proof | AC-01, AC-02, AC-03, AC-04, AC-05, AC-06 | none | ACCEPTED |
| T-02 | `academy/release.json`, `.codearbiter/release-targets.md` | The T-01 focused suite passes; installed `_releaselib.py list-targets`, `show-row academy-preview`, and `render-release-assets 0.31 preview-0.31 ...` agree with the test oracle. | TDD Phase 3 minimal green | AC-01, AC-02, AC-03, AC-04, AC-05, AC-06 | T-01 | ACCEPTED |
| T-03 | `tests/test_release_declaration.py`, `tests/test_release_assets.py`, `install/install.ps1`, `install/install.ps1.sha256`, existing affected release surfaces read-only | `python -m unittest tests.test_release_declaration tests.test_release_assets tests.test_pages_workflow tests.test_preview_manifest -v` passes with the Windows module-path regression, and `git diff --check` is clean. | TDD Phase 4 obligation verification plus regression-first `$ca-fix` for the ambient `Get-FileHash` dependency exposed by the gate | AC-02, AC-04, AC-05, AC-06, AC-07 | T-02 | ACCEPTED |

## MVP slice

T-01 through T-03 form the minimal implementation slice. The sprint's required commit-gate, review, PR, exact-head CI, and merge phases complete AC-07 after the task ledger is accepted. The later tag, GitHub Release, Pages deployment, and live proof are the subsequent release phase authorized by the campaign, not implementation tasks in this plan.

## Bijection proof

Every AC is covered by at least one task and every task advances AC-01 through AC-07. There are no plan-only tasks and no uncovered criteria. If every AC passed and nothing else changed, the repository would have the missing generic target declaration and the release lane could proceed; the remaining publication work is explicitly the next phase, not a hidden implementation defect.
