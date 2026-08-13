# U06 Private Guided Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a private, action-backed U06 source lesson that teaches a real read-only `ca-preview` workflow without executing unsafe or unavailable advanced CodeArbiter surfaces.

**Architecture:** Seed one deterministic Markdown candidate through the existing scenario overlay. A U06-specific checkpoint profile accepts exactly two linear evidence commits: the frozen candidate change followed by a canonical binding report. The existing Markdown/action renderer supplies all lesson cards; Preview 0.12 continues to refuse U06.

**Tech Stack:** Python standard library, Academy scenario/checkpoint JSON, shared LessonAction renderer, unittest, Git fixtures.

## Global Constraints

- Keep U06 source-only and private: do not alter Preview 0.12, route inventory, release assets, or public README claims. The narrow installer package-data declaration required to preserve U06's nested scenario seed is allowed; unrelated installer changes are not.
- Use exactly the shared eight guided headings and standalone action references; no raw runnable command fences or bespoke UI.
- Teach `$ca-preview` as a read-only predicted review. Do not conflate it with the Academy Preview release identity.
- Never direct learners to run `ca-sandbox`, `ca-new-skill`, `ca-watch`, or `ca-tribunal`; classify their real prerequisites and risks instead.
- Native-terminal commands never begin with `!`; harness shell commands have exactly one `!`; host-native CodeArbiter commands have none.
- Check proves repository bytes, commit topology, and clean state only. It cannot prove host invocation or learner understanding.
- Every behavioral change starts red and receives an independent scoped review before a governed commit.

---

### Task 1: Freeze the candidate and replace the permissive U06 semantic profile

**Files:**
- Modify: `academy/scenarios/U06-preview-and-advanced-surfaces/manifest.json`
- Create: `academy/scenarios/U06-preview-and-advanced-surfaces/files/docs/U06-preview-candidate.md`
- Modify: `academy/checkpoints/U06-preview-and-advanced-surfaces.json`
- Modify: `academy/checkpoint.schema.json`
- Modify: `academy_engine/checkpoints.py`
- Test: `tests/test_power_user_u06.py`
- Test: `tests/test_scenario.py`
- Test: `tests/test_checkpoints.py`

**Interfaces:**
- Produces the `u06_preview_evidence` profile and one seeded `docs/U06-preview-candidate.md` source file.
- Consumes `_SemanticContext`, prepared attempt topology, committed blobs, and the existing scenario overlay.

- [ ] **Step 1: Write a positive two-commit U06 test**

Create a real-Git fixture that prepares U06, changes only the seeded candidate from its exact frozen bytes to the expected safe Markdown policy text in commit one, then adds only `.codearbiter/reports/academy/U06-preview.json` in commit two. The report must bind the prepared SHA, candidate SHA/tree, exact changed path, `read_only: true`, no preview telemetry, and four explicit advanced-surface decisions.

- [ ] **Step 2: Run the test red**

Run: `C:\Python314\python.exe -m unittest tests.test_power_user_u06.PrivateU06CheckpointTests.test_accepts_exact_two_commit_preview_evidence -v`

Expected: fail because the generic `preview_evidence` profile permits an unfrozen report shape and does not bind the two-commit topology.

- [ ] **Step 3: Implement the smallest strict predicate**

Add the U06 profile that requires a clean, linear prepared -> candidate -> report history, the fixed candidate file and exact final bytes, one report-only `HEAD` commit, canonical UTF-8 JSON, candidate SHA/tree/path bindings, and all four non-executed classifications. Reject extra commits, dirt including untracked paths, malformed or forged report fields, secret-bearing content, invented preview telemetry, and altered seed/final bytes.

- [ ] **Step 4: Add adversarial mutations**

Add independent failures for wrong candidate parent/tree, extra changed path, extra later commit, dirty/untracked worktree, malformed JSON, changed seed/final content, secret content, invented preview telemetry, and missing advanced-surface decision. Add scenario overlay and failed-Prepare rollback tests for the seed file.

- [ ] **Step 5: Run focused verification**

Run: `C:\Python314\python.exe -m unittest tests.test_power_user_u06 tests.test_scenario tests.test_checkpoints -q`

### Task 2: Add the private shared-manifest U06 lesson

**Files:**
- Create: `academy/actions/U06-preview-and-advanced-surfaces.json`
- Create: `academy/tracks/power-user/U06-preview-and-advanced-surfaces.md`
- Test: `tests/test_lesson_actions.py`

**Interfaces:**
- Produces exactly these ordered action IDs: `U06-confirm-private-boundary`, `U06-prepare-attempt`, `U06-inspect-scenario`, `U06-inspect-seeded-candidate`, `U06-create-contained-diff`, `U06-inspect-preview-input`, `U06-run-read-only-preview`, `U06-assess-preview-output`, `U06-stage-candidate`, `U06-commit-candidate`, `U06-classify-advanced-surfaces`, `U06-write-binding-report`, `U06-inspect-binding-report`, `U06-stage-report`, `U06-commit-report`, `U06-confirm-clean`, `U06-check-status`, `U06-reset-retry`.

- [ ] **Step 1: Write the failing lesson-action contract test**

Assert the exact ordered IDs, the eight headings, one-to-one guide references, actor/surface ownership, three OS copies for Academy lifecycle actions, and Claude/Codex/Pi direct-plus-fallback variants for the `ca-preview` card.

- [ ] **Step 2: Run it red**

Run: `C:\Python314\python.exe -m unittest tests.test_lesson_actions.LessonActionTests.test_private_u06_manifest_teaches_preview_without_executing_advanced_surfaces -v`

- [ ] **Step 3: Create guide and manifest**

Make the active agent create exactly the frozen Markdown diff and stop before staging; the learner inspects it, invokes host-native `ca-preview`, stages/commits the candidate, writes/reviews the binding report, and commits the report through `ca-commit`. State that sandbox needs Docker/untrusted target, new-skill needs demonstrated gap plus approved scope, watch needs real hosted PR/CI, and tribunal is a persistent expensive audit—not routine training.

- [ ] **Step 4: Add literal truth/safety assertions**

Lock the guide’s distinction between Academy preview and `ca-preview`; forbid executing the four advanced commands; lock the report’s four “not run here” classifications; forbid `!` on native and CodeArbiter variants; require Check-limit wording.

- [ ] **Step 5: Run focused verification**

Run: `C:\Python314\python.exe -m json.tool academy/actions/U06-preview-and-advanced-surfaces.json && C:\Python314\python.exe -m unittest tests.test_lesson_actions -q`

### Task 3: Prove private rendering and current-release refusal

**Files:**
- Modify: `tests/test_preview_site.py`
- Modify: `tests/test_academy_cli.py`

**Interfaces:**
- Uses `_read_markdown_document`, `_render_action`, and current published-lab dispatch.
- Produces source rendering proof while Preview 0.12 creates no U06 route or attempt state.

- [ ] **Step 1: Add failing boundary tests**

Render the U06 source directly and assert every action has shared actor/surface/copy rendering with no raw fences. Assert U06 is absent from public guided/runnable inventories. Assert installed Preview 0.12 `prepare`, `check`, and `reset U06-preview-and-advanced-surfaces` all refuse without mutation.

- [ ] **Step 2: Run red then make only necessary support changes**

Run: `C:\Python314\python.exe -m unittest tests.test_preview_site.PreviewSiteTests.test_u06_private_document_uses_shared_actions_without_a_public_route tests.test_academy_cli -q`

Do not add any route, package, TUI card, or publication entry; use existing renderer/refusal behavior unless the test establishes a gap.

- [ ] **Step 3: Run integration verification**

Run: `C:\Python314\python.exe -m unittest tests.test_power_user_u06 tests.test_scenario tests.test_checkpoints tests.test_lesson_actions tests.test_preview_site tests.test_academy_cli -q && C:\Python314\python.exe -m compileall -q academy_engine tests && git diff --check`

- [ ] **Step 4: Review and governed commit**

Obtain independent semantic and lesson/renderer review. Append the required new UTF-8 SMARTS delivery entry only after a user-authorized H-05 override; stage only this U06 source slice and commit through the governed gate.

## Self-review

- The frozen candidate and strict two-commit proof make `ca-preview` teachable without claiming host telemetry.
- The renderer remains shared; future card/system changes occur once.
- Current Preview 0.12 is unmodified and U06 remains non-routable.
- U06 source has no cross-repo implementation dependency, but promotion remains blocked by U05’s durable CodeArbiter lifecycle and the U01-U05 prerequisite chain.
