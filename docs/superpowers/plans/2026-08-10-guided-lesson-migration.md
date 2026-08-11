# Guided Lesson Migration Implementation Plan

> Historical migration plan. Use the checked-in action schema, lesson manifests, and current Preview
> publication record for executable behavior. Earlier draft inventories and command examples here
> are not release authority.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate F02-F04 and P01-P05 from runnable reference pages to complete guided lessons, then promote P06 and P07 only after their verifiers and guided lessons independently clear release gates.

**Architecture:** Reuse the versioned `LessonActionManifest` contract, renderer, local interaction module, publication truth model, and `AcademyOperations` console boundary established by the Preview 0.3 plans. Each lesson remains explanatory Markdown plus one authoritative JSON action manifest; each release slice changes `guided_labs` only after exact lesson, verifier, cold-read, visual, and generated-artifact evidence passes. The website remains the course, the console owns setup/check/reset/return operations, agents own sanctioned CodeArbiter routes, and learners own browser choices, terminal commands, review, and approval decisions.

**Tech Stack:** Python 3.11/3.12 standard library, JSON Schema 2020-12, Markdown, semantic HTML, local vanilla JavaScript/CSS/assets, `unittest`, Node built-in test runner, Git, GitHub Actions/Pages.

## Global Constraints

- Begin only from the merged Preview 0.3 head defined by `docs/superpowers/plans/2026-08-10-guided-f01-release.md` and the merged operations-console head defined by `docs/superpowers/plans/2026-08-10-academy-operations-tui.md`.
- The website is authoritative teaching content. The console may prepare, check, reset/retry, return to base, show progress, and open the matching website lesson; it must not render lesson prose.
- Use `lesson_contract_version: 1` and `schema_version: 1`; do not fork the shared `CommandVariant`, `LessonAction`, `LessonActionManifest`, `PreviewManifest`, or `AcademyOperations` interfaces.
- Every runnable sequence uses the headings `Know before you begin`, `What you will prove`, `Prepare safely`, `Practice`, `Recognize success`, `Check`, `Recover or continue`, and `Understand the mechanism`, in that order.
- Every action has one explicit actor (`learner`, `academy`, or `agent`), one explicit surface when applicable (`browser`, `native-terminal`, `harness`, or `academy-console`), an observable expected result, and a bounded recovery or stop condition.
- A learner shell command entered into a host harness TUI contains exactly one leading `!`. The same command shown for a native terminal contains no `!`. CodeArbiter host commands, Academy-console menu actions, browser actions, and expected output never contain `!`.
- Commands are present only in action manifests and referenced from Markdown with standalone `{{action:ACTION_ID}}` lines. Visible and copied bytes are identical. Expected output is never copyable.
- Learner-facing lessons contain no raw `git commit` command. A required commit is an `agent` action whose `language: codearbiter` variants invoke the selected host's `$ca-commit` equivalent; the learner reviews the proposed boundary and supplies any real approval the gate requests.
- A learner is assumed to know only material taught by the current or prerequisite lessons. Define every new Git, CodeArbiter, Academy, security, dependency, and evidence term before first use.
- Do not describe an agent or Academy action as a learner action. Do not claim a host command was executed when the verifier proves only committed state.
- Repository file authoring, source edits, test edits, report generation, sanctioned task transitions, reviews, and commit gates are `agent` actions unless a verifier contract explicitly requires manual learner authorship. Learner actions are decisions, approvals, reading, comparisons, and the shell commands the lesson deliberately teaches the learner to run. Academy actions remain limited to the operations-console lifecycle.
- A verifier's existence or merge is not guided readiness. `guided_labs` changes only in the release task for the relevant slice.
- Training media is an enhancement, not an instruction source. Only real captures from the exact Academy/CodeArbiter workflow are permitted; each committed capture requires version/commit provenance, captions or transcript, and a complete text path beneath it. Fake terminals, animated mockups, and simulated success output are prohibited.
- Runtime assets are local. No remote fonts/scripts, runtime requests, inline event handlers, generic dashboard grids, ornamental gradients, fake metrics, or decorative status content.
- Every slice receives desktop, tablet, narrow-mobile, 320px, 200% zoom, keyboard-only, reduced-motion, and no-JavaScript checks. Clipping, overlap, hidden required content, inaccessible focus, or ambiguous roles blocks publication.
- Use TDD, `apply_patch`, LF for identity-bound Markdown/JSON, and the governed branch/commit/PR path. Do not write to `main`.

## Shared interfaces consumed unchanged

```python
@dataclass(frozen=True)
class CommandVariant:
    id: str
    surface: str
    operating_system: str
    host: str
    language: str
    command: str
    copy: bool

@dataclass(frozen=True)
class LessonAction:
    id: str
    sequence: int
    title: str
    actor: str
    surface: str | None
    instruction: str
    rationale: str | None
    variants: tuple[CommandVariant, ...]
    expected_result: str
    recovery: str
    evidence: str | None

@dataclass(frozen=True)
class LessonActionManifest:
    schema_version: int
    lesson_contract_version: int
    document_id: str
    actions: tuple[LessonAction, ...]

def load_action_manifest(root: Path, document_id: str) -> LessonActionManifest: ...
def validate_action_manifest(data: Mapping[str, object], *, expected_document_id: str) -> LessonActionManifest: ...
```

`PreviewManifest.guided_labs` is an ordered subset of `runnable_labs`. Console mutations use only `AcademyOperations.preflight(kind: OperationKind, lab_id: str | None = None) -> OperationResult[MutationPlan]` followed by `AcademyOperations.execute(plan: MutationPlan) -> OperationResult[object]`; the exact kinds are `PREPARE`, `CHECK`, `RESET`, and `RETURN_TO_BASE`. `AcademyOperations.open_lesson(lab_id: str) -> OperationResult[str]` remains read-only. Lesson manifests describe those selections as `actor: academy`, `surface: academy-console`; they do not reproduce nonexistent convenience methods or low-level Git/CLI commands for console-owned state changes.

Every JSON action uses the shared schema exactly:

- A non-command action sets `actor` and one action-level `surface`, uses `variants: []`, and supplies nonempty `expected_result` and `recovery`.
- A command action sets action-level `surface: null`; every variant supplies all seven exact keys: `id`, `surface`, `operating_system`, `host`, `language`, `command`, and `copy`.
- Learner shell variants use `actor: learner`, `copy: true`, `host: none`, and either `surface: native-terminal, operating_system: windows, language: powershell` or `surface: native-terminal, operating_system: macos|linux, language: sh`. Their matching harness-TUI variants use the selected `host: claude-code|codex|pi`, `surface: harness`, the same OS/language, and exactly one leading `!`.
- Agent CodeArbiter actions use `actor: agent`, `surface: null`, `operating_system: all`, `language: codearbiter`, and host-native `claude-code`, `codex`, and `pi` variants. They never receive shell-passthrough variants and never begin with `!`.
- Academy-console and browser actions are non-command actions with `actor: academy` or `actor: learner` respectively. Selecting a console control is described as an operation, not rendered as a shell command or a duplicate CLI fallback.
- `copy: false` is reserved for a displayed command that is intentionally unsafe to copy and whose instruction explains why; normal executable variants use `copy: true`. Expected output remains in `expected_result`, never in a command variant.
- Every action declares bounded recovery in its own `recovery` field. References to the site-wide Recovery guide supplement but never replace that field.

## Serial integration and release ownership

This plan starts only after the combined Preview 0.3 PR from both sibling plans is merged and deployed. It does not execute in parallel with either sibling and does not modify their component branches. Within this plan, Preview 0.4, 0.5, and 0.6 are serial release branches rooted at the exact preceding merged release, so `academy_engine/preview.py`, the publication schema/manifest, builder/checker, templates, assets, packaging, installers, workflow, README, and shared migration tests have one writer at a time. Parallel agents may perform read-only lesson research or cold reads; they do not edit shared files or concurrently implement lesson tasks from this plan.

Each preview is a real installable release, not a Pages-only label. Preview 0.4 packages Academy `0.2.0`, Preview 0.5 packages `0.3.0`, and Preview 0.6 packages `0.4.0`; each rebuilds the deterministic offline bundle, regenerates pinned PowerShell/POSIX installers and checksums, creates a new immutable tag/GitHub Release after explicit release confirmation, and deploys Pages only when that release tag resolves to the exact merge SHA. The console therefore reads the same installed manifest the website advertises.

## File Map

- Create `academy/actions/F02-orient-to-state.json`, `F03-work-the-board.json`, `F04-fix-with-evidence.json`, `P01-feature-through-plan.json`, `P02-commit-review-pr.json`, `P03-record-an-adr.json`, `P04-review-a-dependency.json`, `P05-checkpoint-remediation.json`, `P06-context-drift-recovery.json`, and `P07-threat-model.json`: authoritative actions for ten guided migrations.
- Modify `academy/tracks/foundations/F02-orient-to-state.md`, `F03-work-the-board.md`, and `F04-fix-with-evidence.md`: novice-complete Foundations lessons.
- Modify `academy/tracks/practitioner/P01-feature-through-plan.md`, `P02-commit-review-pr.md`, `P03-record-an-adr.md`, `P04-review-a-dependency.md`, `P05-checkpoint-remediation.md`, `P06-context-drift-recovery.md`, and `P07-threat-model.md`: guided Practitioner lessons.
- Modify `academy/publication/preview-0.3.json` by successive reviewed renames to `preview-0.4.json`, `preview-0.5.json`, and `preview-0.6.json`: slice-level publication truth.
- Modify `academy/publication/preview-manifest.schema.json` and `academy_engine/preview.py`: exact release arrays for each release head.
- Create `academy/media.schema.json` and `academy_engine/training_media.py`: real-capture provenance contract and loader.
- Create `academy/media/README.md`: capture, caption, transcript, and version-disclosure policy.
- Modify `scripts/build_preview_site.py` and `scripts/check_preview_site.py`: lesson/media rendering and fail-closed artifact validation.
- Modify `site/templates/lab.html` and `site/assets/academy.css`: optional real-media figure and transcript treatment within the established editorial lesson hierarchy.
- Modify `pyproject.toml` and `tests/test_package_resource.py`: package the new action manifests and media contract.
- Modify serially at each publication slice: `install/install.ps1`, `install/install.ps1.sha256`, `install/install.sh`, `install/install.sh.sha256`, `scripts/build_release_bundle.py`, `tests/test_installers.py`, `tests/test_runtime_wheelhouse.py`, and `tests/test_release_bundle.py`: versioned offline installation and immutable release assets.
- Create `tests/test_guided_lesson_migration.py`: cross-lesson anatomy, actor/surface, prerequisite, expected-result, recovery, and action-ID contract tests.
- Create `tests/test_training_media.py`: provenance and no-simulation tests.
- Modify `tests/test_lesson_actions.py`, `tests/test_preview_manifest.py`, `tests/test_preview_site.py`, `tests/test_pages_workflow.py`, `tests/test_foundations_labs.py`, and `tests/test_practitioner_labs.py`: lesson-specific and release-level coverage.
- Modify `.github/workflows/academy-pages.yml` and `README.md`: exact release build/deploy truth without duplicating course instructions.

---

### Task 1: Cross-Lesson Guided Contract and Real-Media Authority

**Files:**
- Create: `tests/test_guided_lesson_migration.py`
- Create: `academy/media.schema.json`
- Create: `academy_engine/training_media.py`
- Create: `academy/media/README.md`
- Create: `tests/test_training_media.py`
- Modify: `academy_engine/lesson_actions.py`
- Modify: `scripts/build_preview_site.py`
- Modify: `scripts/check_preview_site.py`
- Modify: `site/templates/lab.html`
- Modify: `site/assets/academy.css`
- Modify: `pyproject.toml`
- Modify: `tests/test_package_resource.py`
- Modify: `tests/test_preview_site.py`

**Interfaces:**
- Consumes: `load_action_manifest`, `LessonActionManifest`, and the existing action renderer from Preview 0.3.
- Produces: `GUIDED_MIGRATION_ORDER: tuple[str, ...]` equal to F02, F03, F04, P01, P02, P03, P04, P05, P06, P07 in catalog order.
- Produces test authority `MIGRATED_GUIDED: tuple[str, ...]`, `LESSON_PREREQUISITE_TERMS: Mapping[str, tuple[str, ...]]`, and `EXPECTED_ACTION_CONTRACT: Mapping[str, tuple[tuple[str, str, str | None, str], ...]]` in `tests/test_guided_lesson_migration.py`; each action tuple is `(id, actor, action_surface, command_kind)` where `command_kind` is `none`, `shell`, or `codearbiter`. Lesson tasks extend all three tables in the same commit as their manifest/prose.
- Produces: `TrainingMedia(id: str, lesson_id: str, kind: str, source_path: str, transcript_path: str, captured_release: str, captured_commit: str, sha256: str, duration_seconds: int, description: str)`.
- Produces: `load_training_media(root: Path, lesson_id: str, *, release_head: str) -> tuple[TrainingMedia, ...]` and `validate_training_media(data: Mapping[str, object], *, root: Path, expected_lesson_id: str, release_head: str) -> TrainingMedia`; `release_head` is the exact 40-character commit passed to the site builder.

- [ ] **Step 1: Write cross-lesson RED tests**

Create a table-driven test requiring each ID in `MIGRATED_GUIDED` to use the eight ordered anatomy headings, contain each declared action reference exactly once, define every term listed in its `prerequisite_terms`, and expose no unstructured fenced command. Initialize `MIGRATED_GUIDED = ()`; each lesson task appends only its completed lesson IDs, and Task 12 asserts it equals `GUIDED_MIGRATION_ORDER`. This keeps every intermediate commit green without weakening the final completeness gate.

For every migrated lesson, assert the manifest's ordered `(id, actor, surface, command kind)` projection equals `EXPECTED_ACTION_CONTRACT[lesson_id]`. For `shell`, require the complete applicable OS/host variant matrix, `copy: true`, native bytes without `!`, and harness-TUI bytes with exactly one `!`. For `codearbiter`, require exact `claude-code`, `codex`, and `pi` host variants, `operating_system: all`, `copy: true`, and no `!`. For `none`, require zero variants and a non-null action surface. Independently require every action's nonempty instruction, expected result, and bounded recovery.

```python
GUIDED_MIGRATION_ORDER = (
    "F02-orient-to-state", "F03-work-the-board", "F04-fix-with-evidence",
    "P01-feature-through-plan", "P02-commit-review-pr", "P03-record-an-adr",
    "P04-review-a-dependency", "P05-checkpoint-remediation",
    "P06-context-drift-recovery", "P07-threat-model",
)
MIGRATED_GUIDED: tuple[str, ...] = ()

def test_every_migrated_lesson_has_one_ordered_reference_per_action(self) -> None:
    for lesson_id in MIGRATED_GUIDED:
        manifest = load_action_manifest(SOURCE, lesson_id)
        text = lesson_path(lesson_id).read_text(encoding="utf-8")
        positions = [text.index(f"{{{{action:{action.id}}}}}") for action in manifest.actions]
        self.assertEqual(positions, sorted(positions), lesson_id)
        self.assertNotRegex(text, r"(?m)^\s*git commit(?:\s|$)")
        for action in manifest.actions:
            self.assertEqual(text.count(f"{{{{action:{action.id}}}}}"), 1, lesson_id)
```

- [ ] **Step 2: Run the contract harness and fixture mutation**

Run: `python -m unittest tests.test_guided_lesson_migration -v`

Expected: PASS for the empty migration set, while a fixture that adds `F02-orient-to-state` without its manifest fails. Each subsequent lesson task first adds its ID and observes RED before adding content.

- [ ] **Step 3: Write media-schema RED tests**

Require exact keys, safe repository-relative paths below `site/assets/training/`, kind in `webm|gif`, lowercase 64-character hexadecimal SHA-256 digest, 40-character captured commit, positive duration at most 180 seconds, nonempty description, and a committed `.vtt` or `.md` transcript. Reject `simulated`, `mock`, `fake`, `generated terminal`, missing transcript, remote URLs, mutable release names, path traversal, incorrect digest, and a capture whose disclosed commit is not an ancestor of the release head.

- [ ] **Step 4: Implement the media authority without inventing media**

Implement frozen `TrainingMedia`, exact semantic validation, digest verification, and zero-or-more media loading from the path returned by `root / "academy" / "media" / f"{lesson_id}.json"`. `validate_training_media` hashes the media bytes under `root`, validates the transcript path, and runs `git merge-base --is-ancestor captured_commit release_head`; `load_training_media` passes both trusted values and rejects a non-commit or non-ancestor. Absence is valid. Presence is valid only when the capture and transcript both exist and pass provenance checks. The builder passes its exact `--release-sha` as `release_head` and renders a `<figure class="training-media">` after `What you will prove`, including native controls, description, a disclosure formatted from `captured_release` and the first 12 characters of `captured_commit`, and an always-visible transcript link. The checker rejects autoplay, muted instructional video, remote sources, missing captions/transcript, and unregistered media files.

- [ ] **Step 5: Document the real-capture procedure**

Specify: start from a clean tagged Academy release; use the real console and real selected CodeArbiter host; record only the bounded lesson interaction; redact by re-recording rather than editing terminal pixels; keep commands/results truthful; transcribe all spoken and terminal-critical information; record release, exact commit, duration, file hash, host, OS, and capture date; never synthesize terminal frames. Require a new capture when commands, output, or layout materially changes.

- [ ] **Step 6: Run contract, media, package, and site tests**

Run: `python -m unittest tests.test_guided_lesson_migration tests.test_training_media tests.test_package_resource tests.test_preview_site -v`

Expected: all tests PASS; the fixture proves incomplete entries fail while `MIGRATED_GUIDED` truthfully remains empty.

- [ ] **Step 7: Commit the shared migration authority**

```powershell
git add academy/media.schema.json academy/media/README.md academy_engine/training_media.py tests/test_training_media.py tests/test_guided_lesson_migration.py academy_engine/lesson_actions.py scripts/build_preview_site.py scripts/check_preview_site.py site/templates/lab.html site/assets/academy.css pyproject.toml tests/test_package_resource.py tests/test_preview_site.py
```

Invoke `$ca-commit`; use commit title `feat: define guided lesson migration authority` when the gate requests it.

### Task 2: Guided F02 — Orient to Live State

**Files:**
- Create: `academy/actions/F02-orient-to-state.json`
- Modify: `academy/tracks/foundations/F02-orient-to-state.md`
- Modify: `tests/test_lesson_actions.py`
- Modify: `tests/test_foundations_labs.py`
- Modify: `tests/test_guided_lesson_migration.py`

**Interfaces:**
- Produces ordered action IDs: `F02-prepare`, `F02-run-status`, `F02-read-context`, `F02-follow-context-links`, `F02-hash-context`, `F02-write-orientation`, `F02-inspect-orientation`, `F02-review-commit-boundary`, `F02-run-commit-gate`, `F02-confirm-clean`, `F02-check`, `F02-return-base`, `F02-reset-retry`.

- [ ] **Step 1: Write F02 lifecycle RED tests**

Assert all 13 IDs occur once and in order; `prepare`, `check`, `return-base`, and `reset/retry` are Academy-console actions; status is an agent/harness action with exact Claude, Codex, Pi, and Pi fallback variants; Git/hash/file commands have native PowerShell, POSIX, and exactly-one-`!` harness forms. Assert prerequisites define tracked bytes, SHA-256, repository-relative path, JSON object, stage, and clean worktree before use.

- [ ] **Step 2: Run F02 tests and verify RED**

Run: `python -m unittest tests.test_lesson_actions tests.test_foundations_labs tests.test_guided_lesson_migration -v`

Expected: FAIL because F02 is prose-only and does not identify action ownership or execution surface.

- [ ] **Step 3: Author the exact guided path**

Teach that Academy prepares the numbered branch, the agent returns status, and the learner reads `.codearbiter/CONTEXT.md` plus its linked board/standards/decisions/plans. Provide byte-preserving SHA-256 variants for PowerShell and POSIX Python, then an exact four-key JSON-writing action for `schema_version`, `context_path`, `context_sha256`, and integer `stage`. Never ask the agent to guess the digest or stage.

- [ ] **Step 4: Encode observable success and recovery**

Before Check require the learner to review a one-file boundary, then use the selected host's CodeArbiter commit gate; require empty `git status --short` afterward. State that external Check reloads the committed context blob and rejects extra keys, stale hashes, changed context, and uncommitted files. For every failure route to inspect the named file; reset/retry preserves the failed attempt; return-to-base is available only after clean state.

- [ ] **Step 5: Run F02 tests and commit**

Run: `python -m unittest tests.test_lesson_actions tests.test_foundations_labs tests.test_guided_lesson_migration -v`

Expected: all F02-specific tests PASS; later lessons remain excluded from focused assertions.

```powershell
git add academy/actions/F02-orient-to-state.json academy/tracks/foundations/F02-orient-to-state.md tests/test_lesson_actions.py tests/test_foundations_labs.py tests/test_guided_lesson_migration.py
```

Invoke `$ca-commit`; use commit title `docs: guide live-state orientation`.

### Task 3: Guided F03 — Sanctioned Task Lifecycle

**Files:**
- Create: `academy/actions/F03-work-the-board.json`
- Modify: `academy/tracks/foundations/F03-work-the-board.md`
- Modify: `tests/test_lesson_actions.py`
- Modify: `tests/test_foundations_labs.py`
- Modify: `tests/test_guided_lesson_migration.py`

**Interfaces:**
- Produces ordered action IDs: `F03-prepare`, `F03-read-board`, `F03-start-task`, `F03-inspect-started`, `F03-complete-task`, `F03-inspect-done`, `F03-review-diff`, `F03-review-commit-boundary`, `F03-run-commit-gate`, `F03-confirm-clean`, `F03-check`, `F03-return-base`, `F03-reset-retry`.

- [ ] **Step 1: Write F03 RED tests**

Require the lesson to define task ID, queued `[ ]`, active `[~]`, complete `[x]`, sanctioned transition, and started/done dates before first use. Assert only the agent executes `$ca-task`/host equivalents and the CodeArbiter commit gate; the learner reads, diffs, and approves the proposed one-file boundary; Academy prepares/checks/recovers. Require exact target `academy.feature.0001` and reject wording that asks the learner to implement its described feature, run raw `git commit`, or fabricate `gate-events.log`.

- [ ] **Step 2: Run F03 tests and verify RED**

Run: `python -m unittest tests.test_foundations_labs tests.test_guided_lesson_migration -v`

Expected: FAIL on missing structured ownership and observable intermediate states.

- [ ] **Step 3: Implement the guided transition sequence**

Show the learner the unchanged task scope before start, the exact `[~]` result after start, and the same line in canonical `[x] ... (done YYYY-MM-DD)` form after done. Require `git diff -- .codearbiter/open-tasks.md`, learner confirmation of the one-path boundary, one commit through the selected host's CodeArbiter commit gate, and a clean worktree. Explain that the verifier proves the byte transition and commit date relationship, not which executable wrote it.

- [ ] **Step 4: Add bounded recovery and verify GREEN**

Wrong task, unrelated board edit, malformed date, or dirty worktree must stop before Check and offer preserved retry. Run: `python -m unittest tests.test_lesson_actions tests.test_foundations_labs tests.test_guided_lesson_migration -v`.

Expected: all F02/F03 guided and Foundations verifier-contract tests PASS.

- [ ] **Step 5: Commit F03**

```powershell
git add academy/actions/F03-work-the-board.json academy/tracks/foundations/F03-work-the-board.md tests/test_lesson_actions.py tests/test_foundations_labs.py tests/test_guided_lesson_migration.py
```

Invoke `$ca-commit`; use commit title `docs: guide the sanctioned task lifecycle`.

### Task 4: Guided F04 and Foundations Publication Slice

**Files:**
- Create: `academy/actions/F04-fix-with-evidence.json`
- Modify: `academy/tracks/foundations/F04-fix-with-evidence.md`
- Modify: `tests/test_lesson_actions.py`
- Modify: `tests/test_foundations_labs.py`
- Modify: `tests/test_guided_lesson_migration.py`
- Rename: `academy/publication/preview-0.3.json` -> `academy/publication/preview-0.4.json`
- Modify: `academy/publication/preview-manifest.schema.json`
- Modify: `academy_engine/preview.py`
- Modify: `tests/test_preview_manifest.py`
- Modify: `tests/test_preview_site.py`
- Modify: `README.md`
- Modify: `academy/actions/home.json`
- Modify: `academy/guides/home.md`
- Modify: `pyproject.toml`
- Modify: `install/install.ps1`
- Modify: `install/install.ps1.sha256`
- Modify: `install/install.sh`
- Modify: `install/install.sh.sha256`
- Modify: `scripts/build_release_bundle.py`
- Modify: `tests/test_installers.py`
- Modify: `tests/test_runtime_wheelhouse.py`
- Modify: `tests/test_release_bundle.py`
- Modify: `tests/test_pages_workflow.py`
- Modify: `.github/workflows/academy-pages.yml`
- Create: `docs/reviews/preview-0.4-cold-read-1.md`
- Create: `docs/reviews/preview-0.4-cold-read-2.md`

**Interfaces:**
- Produces ordered action IDs: `F04-prepare`, `F04-enter-fix-lane`, `F04-read-defect`, `F04-write-regression`, `F04-run-red`, `F04-review-regression-boundary`, `F04-run-regression-commit-gate`, `F04-repair-boundary`, `F04-run-focused-green`, `F04-run-suite-green`, `F04-review-repair-boundary`, `F04-run-repair-commit-gate`, `F04-confirm-clean`, `F04-check`, `F04-return-base`, `F04-reset-retry`.
- Produces Preview 0.4 `guided_labs`: F01, F02, F03, F04. `runnable_labs` remains F01-F04 and P01-P05; `coming_next` remains P06/P07.

- [ ] **Step 1: Write F04 and Preview 0.4 RED tests**

Require learner/agent/Academy separation, a meaningful failing `unittest` before production edits, a test-only commit, later code-only commit, retained ordinary-label coverage, and explicit difference between test failure and import/syntax error. Require Preview 0.4 exact ordered arrays and reject P01 as guided.

- [ ] **Step 2: Run focused tests and verify RED**

Run: `python -m unittest tests.test_foundations_labs tests.test_preview_manifest tests.test_preview_site tests.test_guided_lesson_migration -v`

Expected: FAIL because F04 is unstructured and Preview 0.3 guides only F01.

- [ ] **Step 3: Author F04's two-commit proof**

Teach U+0000-U+001F and U+007F control characters, the real `claim_ticket` boundary, exact focused test path, RED interpretation, and smallest validation repair. Label `$ca-fix` and both `$ca-commit` equivalents as agent actions. Label test execution, diff review, and source inspection as learner terminal actions. Show expected changed-path sets after each governed commit and require external Check only from clean state.

- [ ] **Step 4: Run the Foundations cold-read review**

Give two independent reviewers only: “You completed guided F01 and know how to open the site and console.” They must complete F02-F04 in order, identify every actor and surface, explain each introduced term, predict every expected state, preserve RED-before-GREEN history, and recover from one wrong-task and one same-commit mutation. Convert every miss into a failing content/contract test before correction. Store reports at `docs/reviews/preview-0.4-cold-read-1.md` and `docs/reviews/preview-0.4-cold-read-2.md` in the execution branch.

- [ ] **Step 5: Advance publication truth and verify the artifact**

Set release to `preview-0.4`, preserve nine runnable labs, set the exact four-item guided list, and retain P06/P07 as nonlinked status. Build/check the site and verify Home/course ledger labels F01-F04 Guided and P01-P05 Reference lesson.

Set the package version to `0.2.0`; update the deterministic bundle name, install roots, immutable release URLs, and workflow release-asset gate from `preview-0.3` to `preview-0.4`; rebuild the Academy wheel plus offline bundle; and replace every committed checksum with the digest of the final reviewed bytes. Tests must reject a Preview 0.4 page whose installer, installed publication manifest, package version, tag, or release asset still names Preview 0.3.

Run: `python -m unittest tests.test_lesson_actions tests.test_foundations_labs tests.test_preview_manifest tests.test_preview_site -v`

Run: `node --test tests/site/academy.test.mjs`

Run: `python scripts/build_preview_site.py --output site/generated --release-sha 4444444444444444444444444444444444444444; python scripts/check_preview_site.py site/generated`

Run: `python -m unittest tests.test_installers tests.test_runtime_wheelhouse tests.test_release_bundle tests.test_pages_workflow -v`

Expected: all commands PASS and no P06/P07 runnable link exists.

- [ ] **Step 6: Complete visual acceptance and commit**

Capture Home and F02-F04 at 1440x900, 1024x768, 390x844, and 320x568; repeat F04 at 200% zoom, keyboard-only, no-JS, and reduced motion. Add a regression before any clipping/overlap/focus correction. Commit only after both cold reads and the visual matrix pass.

```powershell
git add academy/actions/F04-fix-with-evidence.json academy/tracks/foundations/F04-fix-with-evidence.md academy/actions/home.json academy/guides/home.md academy/publication/preview-0.4.json academy/publication/preview-manifest.schema.json academy_engine/preview.py tests/test_lesson_actions.py tests/test_foundations_labs.py tests/test_guided_lesson_migration.py tests/test_preview_manifest.py tests/test_preview_site.py README.md pyproject.toml install/install.ps1 install/install.ps1.sha256 install/install.sh install/install.sh.sha256 scripts/build_release_bundle.py tests/test_installers.py tests/test_runtime_wheelhouse.py tests/test_release_bundle.py tests/test_pages_workflow.py .github/workflows/academy-pages.yml docs/reviews/preview-0.4-cold-read-1.md docs/reviews/preview-0.4-cold-read-2.md
```

Invoke `$ca-commit`; use commit title `feat: publish guided foundations lessons`.

- [ ] **Step 7: Publish the immutable Preview 0.4 release**

Open and clear the governed ready PR, merge only the exact green head, and resolve the merge SHA. Present that SHA plus byte lengths/SHA-256 values for exactly `install.ps1`, `install.ps1.sha256`, `install.sh`, `install.sh.sha256`, `arbiter-academy-preview-0.4.zip`, and `arbiter-academy-preview-0.4.zip.sha256`; obtain explicit release confirmation. Create annotated tag `preview-0.4` at the merge SHA and a GitHub Release with exactly those six assets. Verify remote tag target, asset bytes/hashes, and the Pages gate that requires the exact tag and all matching assets before deployment. Fetch production Home, F02-F04, and `release.json`; require HTTP 200, `release == "preview-0.4"`, and `commit` equal to the merge SHA.

### Task 5: Guided P01 — Feature, Approval, Plan, and TDD

**Files:**
- Create: `academy/actions/P01-feature-through-plan.json`
- Modify: `academy/tracks/practitioner/P01-feature-through-plan.md`
- Modify: `tests/test_lesson_actions.py`
- Modify: `tests/test_practitioner_labs.py`
- Modify: `tests/test_guided_lesson_migration.py`

**Interfaces:**
- Produces ordered action IDs: `P01-prepare`, `P01-read-context-task-boundary`, `P01-enter-feature-lane`, `P01-author-spec`, `P01-request-user-approval`, `P01-record-supported-approval`, `P01-derive-plan`, `P01-start-task`, `P01-write-regression`, `P01-run-red`, `P01-implement-summary`, `P01-run-focused-green`, `P01-run-full-green`, `P01-run-commit-gate`, `P01-confirm-clean`, `P01-check`, `P01-return-base`, `P01-reset-retry`.

- [ ] **Step 1: Write P01 RED tests**

Require definitions of observable behavior, acceptance criterion, approval boundary, derived plan, coverage mapping, RED/GREEN, and commit gate. Assert the agent routes the feature lane, drafts the spec/plan/test/code, transitions the task, and runs the commit gate; the learner reviews the artifacts and communicates the real user's approval decision; Academy manages attempt state. Reject invented plan approval, invented invocation evidence, RED commits, amend/rebase instructions, raw `git commit`, or a claim that the verifier proves temporal TDD execution.

- [ ] **Step 2: Implement the exact guided flow**

Teach the prepared `academy.feature.0002` task, required spec path, criterion-to-plan mapping, explicit user pause, supported approval representation, focused summary test, bounded `open + claimed` implementation, and one final green commit. Every action states the visible file/state result and its failure stop.

- [ ] **Step 3: Run and commit**

Run: `python -m unittest tests.test_practitioner_labs tests.test_lesson_actions tests.test_guided_lesson_migration -v`

Expected: P01 guided and verifier-semantics tests PASS.

```powershell
git add academy/actions/P01-feature-through-plan.json academy/tracks/practitioner/P01-feature-through-plan.md tests/test_lesson_actions.py tests/test_practitioner_labs.py tests/test_guided_lesson_migration.py
```

Invoke `$ca-commit`; use commit title `docs: guide the approved feature lifecycle`.

### Task 6: Guided P02 — Review, Commit, Safe Push, and Offline Receipt

**Files:**
- Create: `academy/actions/P02-commit-review-pr.json`
- Modify: `academy/tracks/practitioner/P02-commit-review-pr.md`
- Modify: `tests/test_lesson_actions.py`
- Modify: `tests/test_practitioner_labs.py`
- Modify: `tests/test_guided_lesson_migration.py`

**Interfaces:**
- Produces ordered action IDs: `P02-locate-repository`, `P02-prepare-outside-checkout`, `P02-capture-identity`, `P02-enter-checkout`, `P02-prove-start`, `P02-inspect-staged-work`, `P02-run-review`, `P02-resolve-review`, `P02-run-work-commit-gate`, `P02-capture-work-head`, `P02-prove-range`, `P02-push-origin`, `P02-prove-origin`, `P02-prove-upstream-absent`, `P02-write-receipt`, `P02-stage-receipt`, `P02-run-receipt-commit-gate`, `P02-confirm-clean`, `P02-check`, `P02-return-base`, `P02-reset-retry`.

- [ ] **Step 1: Write P02 RED tests**

Require the page to define local bare repository, logical repository identity, remote, branch, prepared commit, work head, receipt commit, and offline receipt before use. Assert preparation is explicitly outside the learner checkout, subsequent host/Git work is inside it, only `origin` receives the branch, `upstream` remains absent, and the page never claims a hosted PR exists.

- [ ] **Step 2: Replace the monolithic shell blocks with bounded actions**

Split identity capture, guard checks, review, first sanctioned commit, range proof, origin-only push, exact receipt writing, receipt-only sanctioned commit, and external Check. Preserve every existing fail-closed comparison, but give each block one purpose, a copy button, expected output, and recovery. Harness variants of every PowerShell/POSIX block begin with exactly one `!`; `$ca-review` and `$ca-commit` variants do not.

- [ ] **Step 3: Add mutation and route tests**

Assert the rendered lesson stops on three-line prepare-output drift, wrong current branch, changed prepared commit, empty work range, origin mismatch, unexpected upstream ref, dirty receipt stage, or in-checkout verifier. Require reset to preserve the old attempt and restore the learner's original remotes.

- [ ] **Step 4: Run and commit**

Run: `python -m unittest tests.test_practitioner_labs tests.test_academy_cli tests.test_lesson_actions tests.test_guided_lesson_migration -v`

Expected: all P02 route, receipt, and guided tests PASS.

```powershell
git add academy/actions/P02-commit-review-pr.json academy/tracks/practitioner/P02-commit-review-pr.md tests/test_lesson_actions.py tests/test_practitioner_labs.py tests/test_guided_lesson_migration.py
```

Invoke `$ca-commit`; use commit title `docs: guide the offline review and receipt lifecycle`.

### Task 7: Guided P03 — Record an Accepted Decision

**Files:**
- Create: `academy/actions/P03-record-an-adr.json`
- Modify: `academy/tracks/practitioner/P03-record-an-adr.md`
- Modify: `tests/test_lesson_actions.py`
- Modify: `tests/test_practitioner_labs.py`
- Modify: `tests/test_guided_lesson_migration.py`

**Interfaces:**
- Produces P03 ordered IDs: `P03-prepare`, `P03-read-decision-context`, `P03-enter-adr-lane`, `P03-author-adr`, `P03-request-acceptance`, `P03-record-acceptance`, `P03-inspect-log-append`, `P03-stage-decision`, `P03-run-commit-gate`, `P03-confirm-clean`, `P03-check`, `P03-return-base`, `P03-reset-retry`.

- [ ] **Step 1: Write P03 RED tests**

Require ADR definition, decision owner, accepted status, immutable number/date/title, alternatives/consequences, and append-only decision log. Separate learner authorship, user acceptance, agent `$ca-adr`, and Academy operations.

- [ ] **Step 2: Author P03's accepted-decision lifecycle**

Teach the exact `0004-academy-lab.md` and decision-log outcomes, the user acceptance stop, sanctioned authoring route, one bounded evidence commit, and verifier limits. Recovery preserves rejected/incomplete attempts rather than renumbering accepted history by hand.

- [ ] **Step 3: Run and commit**

Run: `python -m unittest tests.test_practitioner_labs tests.test_lesson_actions tests.test_guided_lesson_migration -v`

Expected: P03 guided and verifier-contract tests PASS.

```powershell
git add academy/actions/P03-record-an-adr.json academy/tracks/practitioner/P03-record-an-adr.md tests/test_lesson_actions.py tests/test_practitioner_labs.py tests/test_guided_lesson_migration.py
```

Invoke `$ca-commit`; use commit title `docs: guide accepted architecture decisions`.

### Task 8: Guided P04 — Review a Dependency Without Installing It

**Files:**
- Create: `academy/actions/P04-review-a-dependency.json`
- Modify: `academy/tracks/practitioner/P04-review-a-dependency.md`
- Modify: `tests/test_lesson_actions.py`
- Modify: `tests/test_practitioner_labs.py`
- Modify: `tests/test_candidate_data.py`
- Modify: `tests/test_guided_lesson_migration.py`

**Interfaces:**
- Produces ordered action IDs: `P04-prepare`, `P04-read-candidate-set`, `P04-enter-dependency-lane`, `P04-inspect-wheel-metadata`, `P04-verify-wheel-hashes`, `P04-read-licenses`, `P04-assess-provenance`, `P04-assess-supply-chain`, `P04-write-review`, `P04-confirm-no-install`, `P04-stage-review`, `P04-run-commit-gate`, `P04-confirm-clean`, `P04-check`, `P04-return-base`, `P04-reset-retry`.

- [ ] **Step 1: Write P04 RED tests**

Define dependency, wheel, license, provenance, hash, transitive dependency, supply-chain risk, and “review is not installation” before first use. Require exact candidate-set identities, committed hashes, bundled licenses, and report fields. Reject every `pip install`, dependency declaration edit, runtime import, or claim that review approved installation.

- [ ] **Step 2: Author P04's no-install review lifecycle**

Teach inspection of the committed `python_dateutil` and `six` wheels, candidate-set digests, bundled license evidence, project runtime policy, provenance, supply-chain disposition, and strict review report. The learner reviews the cited evidence and disposition; the agent owns `$ca-add-dep`, authors the bounded report, and runs the commit gate; Academy owns attempt operations. The expected result explicitly says `pyproject.toml` is unchanged and no package is installed.

- [ ] **Step 3: Run and commit**

Run: `python -m unittest tests.test_practitioner_labs tests.test_candidate_data tests.test_lesson_actions tests.test_guided_lesson_migration -v`

Expected: P04 guided, frozen-candidate, and verifier-contract tests PASS.

```powershell
git add academy/actions/P04-review-a-dependency.json academy/tracks/practitioner/P04-review-a-dependency.md tests/test_lesson_actions.py tests/test_practitioner_labs.py tests/test_candidate_data.py tests/test_guided_lesson_migration.py
```

Invoke `$ca-commit`; use commit title `docs: guide dependency review without installation`.

### Task 9: Guided P05 and Current-Practitioner Publication Slice

**Files:**
- Create: `academy/actions/P05-checkpoint-remediation.json`
- Modify: `academy/tracks/practitioner/P05-checkpoint-remediation.md`
- Modify: `tests/test_lesson_actions.py`
- Modify: `tests/test_practitioner_labs.py`
- Modify: `tests/test_task6a_strictness.py`
- Modify: `tests/test_guided_lesson_migration.py`
- Rename: `academy/publication/preview-0.4.json` -> `academy/publication/preview-0.5.json`
- Modify: `academy/publication/preview-manifest.schema.json`
- Modify: `academy_engine/preview.py`
- Modify: `tests/test_preview_manifest.py`
- Modify: `tests/test_preview_site.py`
- Modify: `README.md`
- Modify: `academy/actions/home.json`
- Modify: `academy/guides/home.md`
- Modify: `pyproject.toml`
- Modify: `install/install.ps1`
- Modify: `install/install.ps1.sha256`
- Modify: `install/install.sh`
- Modify: `install/install.sh.sha256`
- Modify: `scripts/build_release_bundle.py`
- Modify: `tests/test_installers.py`
- Modify: `tests/test_runtime_wheelhouse.py`
- Modify: `tests/test_release_bundle.py`
- Modify: `tests/test_pages_workflow.py`
- Modify: `.github/workflows/academy-pages.yml`
- Create: `docs/reviews/preview-0.5-cold-read-1.md`
- Create: `docs/reviews/preview-0.5-cold-read-2.md`

**Interfaces:**
- Produces ordered action IDs: `P05-prepare`, `P05-read-prepared-decision`, `P05-run-checkpoint`, `P05-inspect-finding`, `P05-write-finding`, `P05-run-finding-commit-gate`, `P05-write-regression`, `P05-run-red`, `P05-run-red-commit-gate`, `P05-repair-summary`, `P05-run-green`, `P05-run-green-commit-gate`, `P05-inspect-commit-paths`, `P05-write-receipt`, `P05-run-receipt-commit-gate`, `P05-confirm-clean`, `P05-check`, `P05-return-base`, `P05-reset-retry`.
- Produces Preview 0.5 `guided_labs`: F01-F04 and P01-P05. `runnable_labs` remains those same nine labs; `coming_next` remains P06/P07.

- [ ] **Step 1: Write P05 and Preview 0.5 RED tests**

Require exact finding, later test-only RED, later code-only GREEN, later receipt-only commit, ordered commit IDs, and exact `affected_paths` roles. Explain checkpoint finding versus remediation evidence, and reject same-commit, reversed, synthetic, transcript-only, or path-swapped proof. Require exact nine-item guided/runnable equality for Preview 0.5.

- [ ] **Step 2: Author the four-commit evidence path**

Use the exact compact finding grammar already enforced by the verifier. Label host-specific checkpoint invocation, finding/test/repair/receipt authoring, and all commit-gate invocations as agent work; label learner review, deliberately taught shell test execution, and approval of each exact commit boundary as learner work. Show `git diff-tree --name-only` expected sets before receipt creation. Explain that Academy Check recomputes ADR bytes, append-only decision state, domain behavior, commit order, and path roles.

- [ ] **Step 3: Run the Practitioner cold-read review**

Give two independent reviewers only: “You completed F01-F04 and may use their definitions.” They must complete P01-P05 without hidden commands; correctly pause for the two real user decisions; distinguish agent, learner, and Academy work; never push upstream; never install P04 candidates; and recover from an unsafe P02 remote plus a same-commit P05 history. Convert every miss into a failing regression. Store reports as `docs/reviews/preview-0.5-cold-read-1.md` and `docs/reviews/preview-0.5-cold-read-2.md`.

- [ ] **Step 4: Advance Preview 0.5 and run release tests**

Update exact schema/runtime arrays and site ledger. Remove “guided rewrite pending” from P01-P05, retain nonlinked P06/P07 status, and state all nine runnable labs are guided.

Set package version `0.3.0` and advance every deterministic bundle, install root, release URL, checksum, and workflow asset/tag assertion to `preview-0.5`. Rebuild from the exact release head; fail if any Preview 0.4 installer or installed-manifest identity remains.

Run: `python -m unittest tests.test_lesson_actions tests.test_foundations_labs tests.test_practitioner_labs tests.test_task6a_strictness tests.test_preview_manifest tests.test_preview_site -v`

Run: `node --test tests/site/academy.test.mjs`

Run: `python scripts/build_preview_site.py --output site/generated --release-sha 5555555555555555555555555555555555555555; python scripts/check_preview_site.py site/generated`

Run: `python -m unittest tests.test_installers tests.test_runtime_wheelhouse tests.test_release_bundle tests.test_pages_workflow -v`

Expected: all commands PASS; P06/P07 have no generated lab page or link.

- [ ] **Step 5: Complete visual acceptance and commit**

Capture P01-P05 at 1440x900, 1024x768, 390x844, 320x568, and P02/P05 at 200% zoom. Exercise every copy control keyboard-only, no-JS fallback, reduced motion, and longest command variant. Add failing regressions before correcting any defect.

```powershell
git add academy/actions/P05-checkpoint-remediation.json academy/tracks/practitioner/P05-checkpoint-remediation.md academy/actions/home.json academy/guides/home.md academy/publication/preview-0.5.json academy/publication/preview-manifest.schema.json academy_engine/preview.py tests/test_lesson_actions.py tests/test_practitioner_labs.py tests/test_task6a_strictness.py tests/test_guided_lesson_migration.py tests/test_preview_manifest.py tests/test_preview_site.py README.md pyproject.toml install/install.ps1 install/install.ps1.sha256 install/install.sh install/install.sh.sha256 scripts/build_release_bundle.py tests/test_installers.py tests/test_runtime_wheelhouse.py tests/test_release_bundle.py tests/test_pages_workflow.py .github/workflows/academy-pages.yml docs/reviews/preview-0.5-cold-read-1.md docs/reviews/preview-0.5-cold-read-2.md
```

Invoke `$ca-commit`; use commit title `feat: publish nine guided academy lessons`.

- [ ] **Step 6: Publish the immutable Preview 0.5 release**

Open and clear the governed ready PR, merge only its exact green head, and resolve the merge SHA. Present that SHA plus byte lengths/SHA-256 values for exactly `install.ps1`, `install.ps1.sha256`, `install.sh`, `install.sh.sha256`, `arbiter-academy-preview-0.5.zip`, and `arbiter-academy-preview-0.5.zip.sha256`; obtain explicit release confirmation. Create annotated tag `preview-0.5` and its GitHub Release at the merge SHA without modifying Preview 0.4. Verify the remote tag/assets and Pages exact-tag/asset gate, then fetch Home, P01-P05, and `release.json`; require HTTP 200, `release == "preview-0.5"`, exact merge commit, nine Guided lessons, and no P06/P07 link.

### Task 10: P06 Verifier Readiness and Guided Context Recovery

**Files:**
- Verify/modify only if a failing regression requires it: `academy_engine/scenario.py`, `academy_engine/checkpoints.py`, `academy_engine/curriculum.py`, `academy/checkpoints/P06-context-drift-recovery.json`, `academy/scenarios/P06-context-drift-recovery/manifest.json`, `academy/scenarios/P06-context-drift-recovery/files/CONTEXT.md`, `academy/scenarios/P06-context-drift-recovery/files/CONTEXT.provenance.json`, `academy/scenarios/P06-context-drift-recovery/files/preserved-note.md`, and `academy/scenarios/P06-context-drift-recovery/files/scenario.json`
- Create: `academy/actions/P06-context-drift-recovery.json`
- Modify: `academy/tracks/practitioner/P06-context-drift-recovery.md`
- Modify: `tests/test_p06_context_recovery.py`
- Modify: `tests/test_scenario.py`
- Modify: `tests/test_practitioner_labs.py`
- Modify: `tests/test_task6a_strictness.py`
- Modify: `tests/test_lesson_actions.py`
- Modify: `tests/test_guided_lesson_migration.py`

**Interfaces:**
- Produces ordered action IDs: `P06-prepare`, `P06-read-context-source-provenance-note`, `P06-capture-prepared-identities`, `P06-run-context-check`, `P06-select-rescout`, `P06-correct-context`, `P06-correct-provenance`, `P06-inspect-recovery-diff`, `P06-run-recovery-commit-gate`, `P06-recompute-git-object-digests`, `P06-write-handoff`, `P06-run-handoff-commit-gate`, `P06-confirm-note-unchanged`, `P06-confirm-clean`, `P06-check`, `P06-return-base`, `P06-reset-retry`.

- [ ] **Step 1: Prove verifier readiness before lesson work**

Run the P06 security/history suite on the exact integration head. Require protected overlay source-to-destination allowlisting, installed-authority hash binding, immutable payload capture, immediate source re-read, TOCTOU rejection with rollback, note preservation, exactly two ordered commits, clean-worktree check, and external-verifier enforcement.

Run: `python -m unittest tests.test_p06_context_recovery tests.test_scenario tests.test_practitioner_labs tests.test_task6a_strictness -v`

Expected: all P06 tests PASS. If any fails, add the smallest adversarial regression and repair verifier behavior before authoring or publishing the lesson.

- [ ] **Step 2: Write guided P06 RED tests**

Require definitions of context drift, provenance, tracked Git object, re-scout, prepared/head digest, and preservation proof. Assert the learner explicitly chooses `re-scout`, edits the bounded context/provenance/handoff evidence, and reviews each proposed boundary; the agent owns `$ca-context-check` and executes both sanctioned CodeArbiter commit gates; Academy owns lifecycle operations. Reject claims that the report proves host invocation, and reject every raw `git commit` command.

- [ ] **Step 3: Author the exact two-commit recovery**

Teach the exact stale sentence, replacement sentence, ADR-0005 link, prepared CLI object, provenance source hash, and unchanged `docs/preserved-note.md`. The first CodeArbiter commit-gate action accepts only context and provenance; the second accepts only the canonical v2 handoff. Use `git show "${preparedCommit}:.codearbiter/CONTEXT.md"`, `git show "${preparedCommit}:.codearbiter/.provenance/CONTEXT.json"`, and `git show "${preparedCommit}:docs/preserved-note.md"` for before bytes and filesystem/head reads for after bytes. State exact expected path sets and digest equalities.

- [ ] **Step 4: Run P06 lesson and verifier tests**

Run: `python -m unittest tests.test_p06_context_recovery tests.test_scenario tests.test_practitioner_labs tests.test_task6a_strictness tests.test_lesson_actions tests.test_guided_lesson_migration -v`

Expected: all P06 tests PASS with no publication change.

- [ ] **Step 5: Commit P06 without making it public**

```powershell
git add academy/actions/P06-context-drift-recovery.json academy/tracks/practitioner/P06-context-drift-recovery.md tests/test_p06_context_recovery.py tests/test_scenario.py tests/test_practitioner_labs.py tests/test_task6a_strictness.py tests/test_lesson_actions.py tests/test_guided_lesson_migration.py academy_engine/scenario.py academy_engine/checkpoints.py academy_engine/curriculum.py academy/checkpoints/P06-context-drift-recovery.json academy/scenarios/P06-context-drift-recovery/manifest.json academy/scenarios/P06-context-drift-recovery/files/CONTEXT.md academy/scenarios/P06-context-drift-recovery/files/CONTEXT.provenance.json academy/scenarios/P06-context-drift-recovery/files/preserved-note.md academy/scenarios/P06-context-drift-recovery/files/scenario.json
```

Invoke `$ca-commit`; use commit title `docs: guide bounded context recovery`.

### Task 11: P07 Verifier Readiness and Guided Threat Modeling

**Files:**
- Verify/modify only if a failing regression requires it: `academy_engine/checkpoints.py`, `academy_engine/curriculum.py`, `academy/checkpoints/P07-threat-model.json`, `academy/scenarios/P07-threat-model/manifest.json`, and `academy/scenarios/P07-threat-model/files/scenario.json`
- Create: `academy/actions/P07-threat-model.json`
- Modify: `academy/tracks/practitioner/P07-threat-model.md`
- Modify: `tests/test_p07_threat_model.py`
- Modify: `tests/test_practitioner_labs.py`
- Modify: `tests/test_task6a_strictness.py`
- Modify: `tests/test_lesson_actions.py`
- Modify: `tests/test_guided_lesson_migration.py`

**Interfaces:**
- Produces ordered action IDs: `P07-prepare`, `P07-read-boundary`, `P07-capture-target-identity`, `P07-run-threat-model`, `P07-define-stride`, `P07-write-scope`, `P07-write-six-threats`, `P07-write-controls`, `P07-record-clearance`, `P07-add-academy-binding`, `P07-validate-report-shape`, `P07-review-report-boundary`, `P07-run-report-commit-gate`, `P07-confirm-target-unchanged`, `P07-confirm-clean`, `P07-check`, `P07-return-base`, `P07-reset-retry`.

- [ ] **Step 1: Prove P07 verifier readiness**

Require exact target blob/SHA binding, report-only history, UTF-8/LF/12KiB bounds, six unique ordered STRIDE rows, visible semantic relationships, native-section/Academy-section separation, non-ASCII and hidden-markup rejection, target immutability, and no false claim of tool invocation.

Run: `python -m unittest tests.test_p07_threat_model tests.test_practitioner_labs tests.test_task6a_strictness -v`

Expected: all P07 verifier tests PASS before lesson authoring.

- [ ] **Step 2: Write guided P07 RED tests**

Require definitions and one concrete Academy-specific example for Spoofing, Tampering, Repudiation, Information Disclosure, Denial of Service, and Elevation of Privilege before the report template. Separate advisory clearance from implementation authorization. Require the exact native heading order and separate target binding labels.

- [ ] **Step 3: Author the guided report sequence**

Teach boundary identification from learner-controlled archive member to contained destination, then one unique modal threat per STRIDE category, disposition prefixes, recommended controls, clearance, and immutable target identity. The agent facilitates threat modeling, authors the bounded report, and runs the CodeArbiter commit gate; the learner reviews the threat reasoning, selects the advisory clearance, and approves the report-only boundary; Academy independently checks bytes/history.

- [ ] **Step 4: Run and commit without publication**

Run: `python -m unittest tests.test_p07_threat_model tests.test_practitioner_labs tests.test_task6a_strictness tests.test_lesson_actions tests.test_guided_lesson_migration -v`

Expected: all P07 tests PASS; Preview 0.5 still has no P06/P07 link.

```powershell
git add academy/actions/P07-threat-model.json academy/tracks/practitioner/P07-threat-model.md tests/test_p07_threat_model.py tests/test_practitioner_labs.py tests/test_task6a_strictness.py tests/test_lesson_actions.py tests/test_guided_lesson_migration.py academy_engine/checkpoints.py academy_engine/curriculum.py academy/checkpoints/P07-threat-model.json academy/scenarios/P07-threat-model/manifest.json academy/scenarios/P07-threat-model/files/scenario.json
```

Invoke `$ca-commit`; use commit title `docs: guide repository threat modeling`.

### Task 12: P06/P07 Cold Read and Preview 0.6 Promotion

**Files:**
- Rename: `academy/publication/preview-0.5.json` -> `academy/publication/preview-0.6.json`
- Modify: `academy/publication/preview-manifest.schema.json`
- Modify: `academy_engine/preview.py`
- Modify: `tests/test_preview_manifest.py`
- Modify: `tests/test_preview_site.py`
- Modify: `tests/test_pages_workflow.py`
- Modify: `.github/workflows/academy-pages.yml`
- Modify: `README.md`
- Modify: `academy/actions/home.json`
- Modify: `academy/guides/home.md`
- Modify: `pyproject.toml`
- Modify: `install/install.ps1`
- Modify: `install/install.ps1.sha256`
- Modify: `install/install.sh`
- Modify: `install/install.sh.sha256`
- Modify: `scripts/build_release_bundle.py`
- Modify: `tests/test_installers.py`
- Modify: `tests/test_runtime_wheelhouse.py`
- Modify: `tests/test_release_bundle.py`
- Create during execution: `docs/reviews/preview-0.6-cold-read-1.md`
- Create during execution: `docs/reviews/preview-0.6-cold-read-2.md`

**Interfaces:**
- Produces Preview 0.6 `runnable_labs` and `guided_labs`: F01-F04 and P01-P07 in catalog order.
- Produces Preview 0.6 `coming_next`: `P08-repository-hygiene` only; it is status text with no runnable link.
- Produces `release.json` with `release: preview-0.6`, `lesson_contract_version: 1`, and exact merged commit.

- [ ] **Step 1: Run the advanced cold-read review before changing publication**

Give two independent reviewers only: “You completed Preview 0.5.” Require each to complete P06 and P07, identify every actor/surface, explain every new term, preserve unrelated note bytes, construct exact two-commit P06 history, construct report-only P07 history, distinguish advisory threat modeling from authorization, recognize every expected state, and recover from one P06 source-swap failure plus one malformed P07 row. Any miss blocks promotion and becomes a failing regression. Persist both reports.

- [ ] **Step 2: Write Preview 0.6 mutation RED tests**

Set `MIGRATED_GUIDED = GUIDED_MIGRATION_ORDER`, then require exact 11-lab runnable/guided arrays, P08-only coming-next state, generated P06/P07 pages, no P08 page/link, action-manifest completeness, and release JSON identity. Mutate P06 out of guided, P07 into coming-next, P08 into runnable, remove a P06 action, and change a P07 expected result; require checker rejection.

- [ ] **Step 3: Advance the publication manifest only after verifier and cold-read evidence**

Rename to Preview 0.6, update pinned schema/runtime arrays, enable P06/P07 console selection and site links from installed manifest truth, and show P08 as nonlinked coming next. Update README with counts and direct links only; do not duplicate lesson commands.

Set package version `0.4.0` and advance every deterministic bundle, install root, immutable release URL, checksum, and workflow asset/tag assertion to `preview-0.6`. The bundle must contain the P06/P07 verifier, scenarios, action manifests, and installed Preview 0.6 publication truth. Reject any release whose site is 0.6 while its installed console still reports 0.5.

- [ ] **Step 4: Run complete local gates**

```powershell
python -m tabnanny academy_engine scripts tests workshop_queue
python -m compileall -q academy_engine scripts tests workshop_queue
python -m unittest tests.test_lesson_actions tests.test_guided_lesson_migration tests.test_training_media tests.test_foundations_labs tests.test_practitioner_labs tests.test_p06_context_recovery tests.test_p07_threat_model tests.test_task6a_strictness tests.test_preview_manifest tests.test_preview_site tests.test_pages_workflow -v
node --test tests/site/academy.test.mjs
python -m unittest tests.test_operations tests.test_tui_state tests.test_tui_app tests.test_installers tests.test_runtime_wheelhouse tests.test_release_bundle -v
python scripts/build_preview_site.py --output site/generated --release-sha 6666666666666666666666666666666666666666
python scripts/check_preview_site.py site/generated
python scripts/scan_secrets.py --staged
```

Expected: every command PASS; generated Home links all 11 guided lessons and does not link P08.

- [ ] **Step 5: Complete visual/media acceptance**

Capture P06/P07 pages at 1440x900, 1024x768, 390x844, 320x568, and 200% zoom; traverse host/OS selection, copy, transcript, console launch, and recovery controls keyboard-only; repeat no-JS/reduced-motion. If real training media was recorded, verify exact file digest, commit/release disclosure, captions/transcript, native controls, and text-complete lesson. If no real capture exists, publish no media container or promise.

- [ ] **Step 6: Commit Preview 0.6 promotion**

```powershell
git add academy/actions/home.json academy/guides/home.md academy/publication/preview-0.6.json academy/publication/preview-manifest.schema.json academy_engine/preview.py tests/test_preview_manifest.py tests/test_preview_site.py tests/test_pages_workflow.py .github/workflows/academy-pages.yml README.md pyproject.toml install/install.ps1 install/install.ps1.sha256 install/install.sh install/install.sh.sha256 scripts/build_release_bundle.py tests/test_installers.py tests/test_runtime_wheelhouse.py tests/test_release_bundle.py docs/reviews/preview-0.6-cold-read-1.md docs/reviews/preview-0.6-cold-read-2.md
```

Invoke `$ca-commit`; use commit title `feat: publish guided context and threat-model labs`.

- [ ] **Step 7: Publish the immutable Preview 0.6 release**

Open and clear the governed ready PR, merge only its exact green head, and resolve the merge SHA. Present that SHA plus byte lengths/SHA-256 values for exactly `install.ps1`, `install.ps1.sha256`, `install.sh`, `install.sh.sha256`, `arbiter-academy-preview-0.6.zip`, and `arbiter-academy-preview-0.6.zip.sha256`; obtain explicit release confirmation. Create annotated tag `preview-0.6` and its GitHub Release at the merge SHA without changing older releases. Verify remote tag/assets, Pages exact-tag/asset gating, production Home/P06/P07/release JSON, and an install into a fresh user-owned directory whose console reports Preview 0.6 and offers exactly the 11 guided labs.

### Task 13: Cross-Release Independent Audit

**Files:**
- Verify only: all files changed by Tasks 1-12

**Interfaces:**
- Consumes the three independently published heads from Tasks 4, 9, and 12.
- Produces one audit proving exact-head CI, review, immutable releases, Pages, and production evidence remained internally consistent across all slices.

- [ ] **Step 1: Audit Preview 0.4 evidence**

Independently compare the Task 4 PR head, merge SHA, tag target, release assets, installed manifest, Pages run, production `release.json`, cold reads, and screenshots. Require one commit identity throughout, F01-F04 Guided, P01-P05 Reference, and no P06/P07 link.

- [ ] **Step 2: Audit Preview 0.5 evidence**

Independently prove the Preview 0.5 branch was rooted at the exact Preview 0.4 merge and compare its PR/merge/tag/assets/installed manifest/Pages/production evidence. Require all nine runnable labs Guided and P06/P07 nonlinked.

- [ ] **Step 3: Audit Preview 0.6 evidence**

Independently prove the Preview 0.6 branch was rooted at the exact Preview 0.5 merge, contains the reviewed P06/P07 verifier trees, and has matching PR/merge/tag/assets/installed manifest/Pages/production evidence. Require 11 Guided links, P08 status-only, installed-console selection parity, and exact Pages provenance.

- [ ] **Step 4: Use bounded CI monitoring**

For each PR, use one local terminal-state monitor and one long wait. Do not make repeated inference calls while hosted state is unchanged. On red, fetch the failing log once, write a regression, correct, rerun exact-head local review, push, and begin one new bounded wait.

- [ ] **Step 5: Persist slice evidence**

For each release record PR URL, reviewed commit/tree, test counts, cold-read reports, viewport inventory, optional real-media provenance, CI run URL, merge SHA, Pages run URL, and production URLs in the active governed handoff/audit location. Do not write live orchestration history into the Academy fixture `.codearbiter/sprint-log.md`.

## Plan Self-Review

- Spec coverage: all ten lessons have exact action IDs, actor/surface boundaries, prerequisites, expected results, recovery, verifier relationships, cold-read gates, visual gates, and per-slice publication ownership.
- Publication ordering: Preview 0.4 guides F01-F04, Preview 0.5 guides F01-P05, and Preview 0.6 guides F01-P07 only after P06/P07 verifier readiness; P08 remains nonlinked.
- Media safety: real capture is optional enhancement, provenance/captions/transcript are mandatory when present, and absent media creates no empty or simulated UI.
- Interface consistency: all tasks consume the Preview 0.3 action/publication/operations interfaces unchanged; action IDs are unique and lesson-prefixed.
- Placeholder scan: commands, paths, release names, arrays, action IDs, review inputs, expected results, and test invocations are concrete.
- Learner clarity: every lesson explicitly separates learner, agent, and Academy work and distinguishes native terminal commands from harness `!` passthrough.
