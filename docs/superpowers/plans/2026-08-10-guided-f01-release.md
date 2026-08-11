# Guided F01 Release Implementation Plan

> Historical delivery plan. Preview 0.3 command examples and the proposed console launch surface
> never became the public contract. Current public availability and installer paths are defined by
> the checked-in Preview manifest, Home actions, and release-assets verification.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish Preview 0.3 with a first-class guided Home, Recovery guide, and F01 lesson whose commands, actors, execution surfaces, expected results, recovery paths, and publication state are explicit and testable.

**Architecture:** Keep the static website as the authoritative teaching surface. Home, Recovery, and F01 retain readable Markdown but reference versioned JSON actions that are loaded and validated by a new typed `academy_engine.lesson_actions` boundary; the existing static builder renders those actions and a committed local JavaScript asset progressively enhances host/OS selection and copying. Preview truth is split into runnable, guided, and coming-next states, while F02-P05 remain runnable reference lessons and the site never equates verifier availability with guided readiness.

**Tech Stack:** Python 3.11/3.12 standard library, frozen dataclasses, JSON Schema 2020-12 as a checked-in contract, `string.Template`, semantic HTML, local vanilla JavaScript, local CSS/fonts/assets, `unittest`, GitHub Actions/Pages.

## Global Constraints

- The website remains the course; the Academy console handles repository operations and must not duplicate lesson prose.
- This plan does not implement `prompt_toolkit`, `wcwidth`, `AcademyOperations`, or the full-screen console. Any public `console` launch command remains blocked until the separate dependency review, ADR, reconciliation, and console implementation are merged.
- Preview 0.3 MUST NOT publish until the sibling operations/TUI plan has produced the tested `console` command, deterministic release bundle, PowerShell/POSIX installers, and exact launch paths below on the same integration head.
- Publish exactly nine runnable labs: F01-F04 and P01-P05. Publish exactly one guided lab: F01. Keep P06 and P07 in `coming_next` and publish no runnable link for either.
- Keep transitional `available_labs == runnable_labs`; require `guided_labs` to be an ordered subset of `runnable_labs`; require runnable and coming-next sets to be disjoint.
- Use `lesson_contract_version: 1` in Preview 0.3 and `schema_version: 1` in every action manifest.
- Command-bearing content must come from action manifests. Markdown may contain only a standalone `{{action:ACTION_ID}}` reference at the point where an action renders.
- Every command variant declares actor, surface, host, operating system, language, visible bytes, and copy policy. Harness shell passthrough begins with exactly one `!`; CodeArbiter invocations never begin with `!`.
- Support Windows PowerShell 7+, macOS POSIX shell, Linux POSIX shell, Claude Code, Codex, and Pi (including Pi's `/skill:ca-*` fallback).
- Render all variants in usable HTML before JavaScript runs. JavaScript may collapse unselected variants but may not create required content.
- Copy from the rendered `<code>` element's `textContent`; do not maintain a second command payload in HTML or JavaScript.
- Expected output is never rendered with a copy control. Clipboard and local-storage failures must leave visible, keyboard-usable fallback behavior.
- Runtime assets are committed and local. No inline event handlers, inline scripts, runtime network calls, remote fonts, generic dashboard grids, fake terminal output, ornamental metrics, or decorative gradients.
- F01 evidence is accepted only after a numbered attempt branch, safe remotes, host Doctor, Academy Doctor report, learner evidence commit, clean worktree, and external Academy Check.
- The release is blocked by clipping, overlap, inaccessible focus, missing labels, hidden content without JavaScript, incorrect copied bytes, unexplained prerequisites, or an ambiguous actor/surface.
- Use `apply_patch` for edits, LF for identity-bound JSON/Markdown, and the governed commit/PR path. Do not write directly to `main`.

## Cross-plan integration order

1. Complete this plan's Task 1 publication model on the Preview 0.3 integration branch so `guided_labs` is available to operations code.
2. Run this plan's Tasks 2-7 and the sibling operations/TUI plan's Tasks 1-10 in parallel worktrees rooted at that reviewed integration base.
3. Integrate both exact reviewed heads without publishing either branch independently.
4. Complete this plan's Tasks 8-9 against the combined head; only that head may advertise or publish Preview 0.3.

The public commands consumed from the sibling plan are exact:

```powershell
irm https://github.com/arbiterForge/arbiter-academy/releases/download/preview-0.3/install.ps1 | iex
$academy = "$env:LOCALAPPDATA\ArbiterAcademy\preview-0.3\Scripts\arbiter-academy.exe"
& $academy --repository (Get-Location).Path console
```

```sh
curl -fsSL https://github.com/arbiterForge/arbiter-academy/releases/download/preview-0.3/install.sh | sh
academy="${XDG_DATA_HOME:-$HOME/.local/share}/arbiter-academy/preview-0.3/bin/arbiter-academy"
"$academy" --repository "$PWD" console
```

## File Map

- Create `academy/lesson-action.schema.json`: checked-in JSON Schema for action manifests.
- Create `academy/actions/home.json`, `academy/actions/recovery.json`, and `academy/actions/F01-fork-clone-doctor.json`: authoritative guided actions.
- Create `academy/guides/home.md` and `academy/guides/recovery.md`: explanatory content with stable action references.
- Create `academy_engine/lesson_actions.py`: typed loader and semantic validator.
- Modify `academy/publication/preview-0.2.json` by renaming it to `academy/publication/preview-0.3.json`: authoritative Preview 0.3 truth states.
- Modify `academy/publication/preview-manifest.schema.json`: pin the Preview 0.3 truth model.
- Modify `academy/tracks/foundations/F01-fork-clone-doctor.md`: rewrite the complete novice path and reference every action once.
- Modify `academy_engine/preview.py`: validate and expose runnable/guided/coming-next states.
- Modify `scripts/build_preview_site.py`: load guides/actions, render action references, and emit the expanded reviewed asset inventory.
- Modify `scripts/check_preview_site.py`: validate semantic controls, local scripts, links, IDs, action structure, and reviewed hashes.
- Modify `site/templates/base.html`, `site/templates/index.html`, `site/templates/lab.html`, and `site/templates/recovery.html`: semantic shells for the guided content.
- Create `site/assets/academy.js`: progressive host/OS selection and accessible copy behavior.
- Modify `site/assets/academy.css`: editorial guided-lesson layout and responsive/accessibility states.
- Modify `pyproject.toml`: package the action schema, action manifests, guides, and Preview 0.3 manifest.
- Modify `README.md`: point setup/course claims at Preview 0.3 without duplicating lesson instructions.
- Modify `.github/workflows/academy-pages.yml`: build/check Preview 0.3 and preserve exact-head deployment provenance.
- Modify `tests/test_preview_manifest.py`, `tests/test_package_resource.py`, `tests/test_preview_site.py`, `tests/test_pages_workflow.py`, and `tests/test_foundations_labs.py`: publication, packaging, renderer, site, deployment, and F01 lifecycle coverage.
- Create `tests/test_lesson_actions.py`: schema-independent semantic validation and action-reference tests.
- Create `tests/site/academy.test.mjs`: dependency-free JavaScript behavior tests using Node's built-in test runner and a purpose-built fake DOM.

---

### Task 1: Preview 0.3 Publication Truth

**Files:**
- Rename: `academy/publication/preview-0.2.json` -> `academy/publication/preview-0.3.json`
- Modify: `academy/publication/preview-manifest.schema.json`
- Modify: `academy_engine/preview.py`
- Modify: `pyproject.toml`
- Modify: `README.md`
- Modify: `academy/tracks/practitioner/P05-checkpoint-remediation.md`
- Modify: `scripts/build_preview_site.py`
- Modify: `scripts/check_preview_site.py`
- Modify: `site/assets/PROVENANCE.md`
- Modify: `site/templates/base.html`
- Modify: `site/templates/index.html`
- Modify: `tests/test_academy_cli.py`
- Modify: `tests/test_installation.py`
- Modify: `tests/test_practitioner_labs.py`
- Modify: `tests/test_preview_manifest.py`
- Modify: `tests/test_preview_site.py`

**Interfaces:**
- Produces: `PreviewManifest(release: str, lesson_contract_version: int, available_labs: tuple[str, ...], runnable_labs: tuple[str, ...], guided_labs: tuple[str, ...], coming_next: tuple[str, ...], discussion_url: str, catalog_sha256: str)`.
- Produces: `require_runnable_lab(root: Path, lab_id: str) -> None`, `require_guided_lab(root: Path, lab_id: str) -> None`; keep `require_published_lab` as a compatibility alias that calls `require_runnable_lab`.

- [x] **Step 1: Write failing truth-model tests**

Add tests that build a manifest with `lesson_contract_version=1`, `available_labs=PREVIEW_0_3`, `runnable_labs=PREVIEW_0_3`, `guided_labs=["F01-fork-clone-doctor"]`, and the existing two-item `coming_next`. Assert acceptance, then separately assert rejection when compatibility lists differ, guided order differs, F01 is omitted, guided contains P06, or runnable intersects coming-next.

```python
def test_preview_manifest_separates_runnable_guided_and_coming_next(self) -> None:
    manifest = validate_preview_manifest(self.root, self.make_manifest())
    self.assertEqual(manifest.release, "preview-0.3")
    self.assertEqual(manifest.lesson_contract_version, 1)
    self.assertEqual(manifest.available_labs, tuple(PREVIEW_0_3))
    self.assertEqual(manifest.runnable_labs, tuple(PREVIEW_0_3))
    self.assertEqual(manifest.guided_labs, ("F01-fork-clone-doctor",))

def test_preview_manifest_rejects_a_false_guided_claim(self) -> None:
    with self.assertRaisesRegex(ValueError, "guided_labs must be an ordered subset"):
        validate_preview_manifest(
            self.root,
            self.make_manifest(guided_labs=["P06-context-drift-recovery"]),
        )
```

- [x] **Step 2: Run the focused tests and verify RED**

Run: `python -m unittest tests.test_preview_manifest -v`

Expected: FAIL because Preview 0.2 has no `runnable_labs`, `guided_labs`, or `lesson_contract_version` fields.

- [x] **Step 3: Implement the exact Preview 0.3 model**

Set `_RELEASE = "preview-0.3"`, rename `_AVAILABLE_LABS` to `_RUNNABLE_LABS`, and validate exact keys:

```python
expected = {
    "release", "lesson_contract_version", "available_labs", "runnable_labs",
    "guided_labs", "coming_next", "discussion_url", "catalog_sha256",
}
```

Require integer `lesson_contract_version == 1`; require `available_labs == runnable_labs == _RUNNABLE_LABS`; require `guided_labs == ("F01-fork-clone-doctor",)` and preserve catalog order; reject `set(runnable_labs) & set(coming_next)`. Update the JSON Schema with the same exact keys and pinned ordered arrays.

- [x] **Step 4: Run the focused tests and verify GREEN**

Run: `python -m unittest tests.test_preview_manifest -v`

Expected: all Preview manifest tests PASS.

- [x] **Step 5: Commit the truth-model slice**

```powershell
git add academy/publication/preview-0.3.json academy/publication/preview-manifest.schema.json academy_engine/preview.py pyproject.toml README.md academy/tracks/practitioner/P05-checkpoint-remediation.md scripts/build_preview_site.py scripts/check_preview_site.py site/assets/PROVENANCE.md site/templates/base.html site/templates/index.html tests/test_academy_cli.py tests/test_installation.py tests/test_practitioner_labs.py tests/test_preview_manifest.py tests/test_preview_site.py
$ca-commit
```

Use commit title `feat: separate guided academy publication truth` when the gate asks for the message.

Review remediation required the complete mechanical Preview 0.2 to Preview 0.3 consumer migration
so this committed slice left existing site and practitioner suites green. Task 8 still owns the new
tag, release-asset, checksum, and deployment-gate semantics.

### Task 2: Versioned Lesson Action Contract

**Files:**
- Create: `academy/lesson-action.schema.json`
- Create: `academy_engine/lesson_actions.py`
- Create: `tests/test_lesson_actions.py`
- Modify: `pyproject.toml`
- Modify: `tests/test_package_resource.py`

**Interfaces:**
- Produces: `CommandVariant(id: str, surface: str, operating_system: str, host: str, language: str, command: str, copy: bool)`.
- Produces: `LessonAction(id: str, sequence: int, title: str, actor: str, surface: str | None, instruction: str, rationale: str | None, variants: tuple[CommandVariant, ...], expected_result: str, recovery: str, evidence: str | None)`.
- Produces: `LessonActionManifest(schema_version: int, lesson_contract_version: int, document_id: str, actions: tuple[LessonAction, ...])`.
- Produces: `load_action_manifest(root: Path, document_id: str) -> LessonActionManifest` and `validate_action_manifest(data: Mapping[str, object], *, expected_document_id: str) -> LessonActionManifest`.

- [x] **Step 1: Write semantic-validator RED tests**

Cover exact keys, integer-not-boolean versions, bounded safe IDs, contiguous sequence starting at 1, unique action/variant IDs, allowed actors/surfaces/hosts/OS/languages, non-empty expected/recovery text, one-to-one command/copy policy, shell passthrough, host-native syntax, and visible/copy identity.

```python
def test_harness_shell_requires_exactly_one_passthrough_prefix(self) -> None:
    for command in ("git status", "!!git status"):
        with self.subTest(command=command):
            data = self.manifest(command=command, surface="harness", language="sh", host="codex")
            with self.assertRaisesRegex(ValueError, "exactly one !"):
                validate_action_manifest(data, expected_document_id="F01-fork-clone-doctor")

def test_codearbiter_invocations_reject_shell_passthrough(self) -> None:
    data = self.manifest(command="!$ca-doctor", surface="harness", language="codearbiter", host="codex")
    with self.assertRaisesRegex(ValueError, "must not begin with !"):
        validate_action_manifest(data, expected_document_id="F01-fork-clone-doctor")
```

- [x] **Step 2: Run the contract tests and verify RED**

Run: `python -m unittest tests.test_lesson_actions tests.test_package_resource -v`

Expected: FAIL because the module and packaged schema do not exist.

- [x] **Step 3: Implement the frozen models and fail-closed loader**

Use exact enumerations:

```python
ACTORS = frozenset({"learner", "academy", "agent"})
SURFACES = frozenset({"browser", "native-terminal", "harness", "academy-console"})
OPERATING_SYSTEMS = frozenset({"all", "windows", "macos", "linux"})
HOSTS = frozenset({"none", "claude-code", "codex", "pi"})
LANGUAGES = frozenset({"none", "powershell", "sh", "text", "codearbiter"})
```

Non-command actions require one action-level `surface` and zero variants. They reject `harness`
because the action-level shape cannot name the required host; harness interactions use command
variants. Command actions require `surface: null` and at least one variant. Enforce a maximum of 64 actions, 12 variants per action, 8192 Unicode code points per command, 1024 Unicode code points for each prose field, no ASCII controls except LF inside commands, and no CR bytes. Load only `academy/actions/{document_id}.json` after rejecting separators, `.`/`..`, and IDs outside `[A-Za-z0-9][A-Za-z0-9-]{0,95}`. Contain the exact candidate with `ensure_within` before reading so symlink or reparse ancestors cannot escape `academy/actions`.

- [x] **Step 4: Add the JSON Schema and package-data contract**

Make the schema's `additionalProperties` false at every object, use `oneOf` for non-command versus command actions, and encode the exact enums and bounds above. Add these data-file entries:

```toml
"share/arbiter-academy/academy" = [
  "academy/lesson-action.schema.json",
  "academy/catalog.json",
  "academy/catalog.schema.json",
  "academy/checkpoint.schema.json",
  "academy/contracts.json",
  "academy/receipt.schema.json",
  "academy/scenario.schema.json",
]
"share/arbiter-academy/academy/actions" = ["academy/actions/*.json"]
"share/arbiter-academy/academy/guides" = ["academy/guides/*.md"]
```

- [x] **Step 5: Run focused tests and verify GREEN**

Run: `python -m unittest tests.test_lesson_actions tests.test_package_resource -v`

Expected: all action validation and packaging tests PASS.

- [x] **Step 6: Commit the action-contract slice**

```powershell
git add academy/lesson-action.schema.json academy_engine/lesson_actions.py tests/test_lesson_actions.py pyproject.toml tests/test_package_resource.py
$ca-commit
```

Use commit title `feat: define guided lesson action contract`.

Review remediation aligned JSON Schema and runtime on Unicode code-point limits and whitespace
semantics, then routed manifest reads through the existing symlink/reparse containment boundary.

### Task 3: Action-Aware Static Renderer

**Files:**
- Modify: `academy/lesson-action.schema.json`
- Modify: `academy_engine/lesson_actions.py`
- Modify: `scripts/build_preview_site.py`
- Modify: `site/templates/index.html`
- Modify: `site/templates/lab.html`
- Modify: `site/templates/recovery.html`
- Modify: `tests/test_lesson_actions.py`
- Modify: `tests/test_preview_site.py`

**Interfaces:**
- Consumes: `load_action_manifest(root: Path, document_id: str) -> LessonActionManifest`.
- Produces: `_read_markdown_document(root: Path, relative_path: Path, document_id: str, *, require_h1: bool) -> dict[str, object]`.
- Produces: `_render_action(action: LessonAction) -> str` and `_render_markdown(document_id: str, lines: list[str], actions: Mapping[str, LessonAction]) -> tuple[str, tuple[tuple[int, str, str], ...], tuple[str, ...]]`.

- [x] **Step 1: Write renderer RED tests with a complete temporary manifest**

Assert a standalone `{{action:F01-prepare}}` becomes one numbered `<section class="lesson-action" data-action-id="F01-prepare">`, includes a visible `You · Native terminal` label, associates heading/status IDs, renders the literal command once per variant, and returns the referenced ID. Assert rejection for inline references, duplicate references, unreferenced actions, unknown IDs, raw command fences in guided documents, and action markup injected through prose.

- [x] **Step 2: Run the focused renderer tests and verify RED**

Run: `python -m unittest tests.test_preview_site.PreviewSiteTests.test_guided_action_reference_renders_semantic_numbered_step tests.test_preview_site.PreviewSiteTests.test_guided_documents_require_one_to_one_action_references -v`

Expected: FAIL because `_render_markdown` does not accept or resolve action manifests.

- [x] **Step 3: Implement action-reference parsing before paragraph parsing**

Recognize only `re.fullmatch(r"\{\{action:([A-Za-z0-9][A-Za-z0-9-]{0,95})\}\}", line)`. Escape every prose value, generate IDs from validated action IDs, and render each variant as:

```html
<div class="command-variant" data-os="windows" data-host="codex" data-surface="harness">
  <p class="action-role">You · Codex harness · Windows</p>
  <div class="command-shell">
    <pre tabindex="0"><code id="command-F01-prepare-codex-windows" class="language-powershell">! &amp; $academy --repository (Get-Location).Path prepare F01-fork-clone-doctor</code></pre>
    <button type="button" class="command-copy" data-copy-target="command-F01-prepare-codex-windows" aria-describedby="copy-status-F01-prepare-codex-windows">Copy</button>
  </div>
  <p id="copy-status-F01-prepare-codex-windows" class="copy-status" role="status" aria-live="polite"></p>
</div>
```

Do not emit a copy button when `copy` is false. Render expected result and recovery in separate labeled blocks; render evidence only when declared.

- [x] **Step 4: Load actions only for guided documents**

Wire Home and Recovery through independent fail-closed guide/action pairs. Before Task 5, neither
member present preserves the honest legacy page. A complete pair activates the action-aware path;
exactly one member or malformed content fails before output. For labs, use the action-aware path only when `lab_id in manifest.guided_labs`; keep the existing renderer for runnable reference lessons and render a visible `Reference lesson · guided rewrite pending` status.

- [x] **Step 5: Run focused and legacy renderer tests**

Run: `python -m unittest tests.test_preview_site -v`

Expected: all site renderer tests PASS and F02-P05 remain renderable.

- [x] **Step 6: Commit the renderer slice**

```powershell
git add academy/lesson-action.schema.json academy_engine/lesson_actions.py scripts/build_preview_site.py site/templates/index.html site/templates/lab.html site/templates/recovery.html tests/test_lesson_actions.py tests/test_preview_site.py
$ca-commit
```

Use commit title `feat: render structured guided lesson actions`.

Review remediation prohibited hostless non-command harness actions and added the latent paired
Home/Recovery activation boundary consumed by Task 5 without publishing placeholder lessons.

### Task 4: Progressive Host, OS, and Copy Controls

**Files:**
- Create: `site/assets/academy.js`
- Create: `tests/site/academy.test.mjs`
- Modify: `scripts/build_preview_site.py`
- Modify: `scripts/check_preview_site.py`
- Modify: `site/assets/academy.css`
- Modify: `site/templates/base.html`
- Modify: `tests/test_preview_site.py`
- Modify: `tests/test_pages_workflow.py`
- Modify: `.github/workflows/academy-pages.yml`

**Interfaces:**
- Produces JS functions `selectVariant(root, os, host)`, `copyCommand(button, clipboard, selection)`, `restorePreferences(storage)`, and `bindAcademyPage(document, navigator, storage)`.
- Consumes only `data-os`, `data-host`, `data-surface`, and `data-copy-target`; command bytes always come from `document.getElementById(target).textContent`.

- [x] **Step 1: Write dependency-free JavaScript RED tests**

Use `node:test` and `node:assert/strict` with small fake elements implementing `querySelectorAll`, `getElementById`, `hidden`, `textContent`, `focus`, and `selectNodeContents`. Test exact copied bytes, Clipboard rejection fallback, missing target error status, invalid stored preferences, filtering without deleting variants, and independent OS/host selection.

Variant filtering uses exact wildcard semantics: a variant is visible when `variant.os` is `all` or equals the selected OS, and `variant.host` is `none` or equals the selected host. Browser and Academy-console actions use `os=all, host=none` unless their command genuinely differs by platform. Tests must prove selecting Codex + Windows retains native-terminal and OS-neutral variants, and no-JS HTML exposes every variant.

```javascript
test("copyCommand copies exactly the visible code bytes", async () => {
  const fixture = academyFixture("!git remote -v\n");
  await copyCommand(fixture.button, { writeText: async value => fixture.copied.push(value) }, fixture.selection);
  assert.deepEqual(fixture.copied, ["!git remote -v\n"]);
  assert.equal(fixture.status.textContent, "Copied command.");
});
```

- [x] **Step 2: Run JavaScript tests and verify RED**

Run: `node --test tests/site/academy.test.mjs`

Expected: FAIL because `site/assets/academy.js` does not exist.

- [x] **Step 3: Implement the local module and no-JS-first markup**

Export the four named functions, then call `bindAcademyPage(document, navigator, window.localStorage)` from a guarded `DOMContentLoaded` listener. Set `document.documentElement.dataset.enhanced = "true"` only after binding succeeds. A failed clipboard call must focus the code block, select its contents, and announce `Clipboard unavailable. The command is selected; press Ctrl+C or Command+C.`

- [x] **Step 4: Extend the artifact allowlist and HTML validator**

Add `assets/academy.js` to `_PUBLIC_ASSET_FILES`, `_ASSET_SHA256`, `_EXPECTED_FILES`, and the base template as `<script type="module" src="$script_url"></script>`. Permit only the exact required attributes (`type`, `src`, `data-*`, `aria-describedby`, `aria-live`, `hidden`, `tabindex`) and require every copy target/status reference to resolve uniquely.

- [x] **Step 5: Add the exact CI behavior gate**

Add `node --test tests/site/academy.test.mjs` to the Pages build job before the site build. Add a workflow test asserting this command occurs before `Build the Academy site` and that no `npm install`, `npx`, CDN, or remote JavaScript URL exists.

- [x] **Step 6: Run behavior and site tests**

Run: `node --test tests/site/academy.test.mjs`

Run: `python -m unittest tests.test_preview_site tests.test_pages_workflow -v`

Expected: all tests PASS.

- [x] **Step 7: Commit the interaction slice**

```powershell
git add site/assets/academy.js tests/site/academy.test.mjs scripts/build_preview_site.py scripts/check_preview_site.py site/assets/academy.css site/templates/base.html tests/test_preview_site.py tests/test_pages_workflow.py .github/workflows/academy-pages.yml
$ca-commit
```

Use commit title `feat: add accessible academy command controls`.

The approved SMARTS scope correction added one progressive, initially hidden host/OS control group
per structured guide with selectable variants. Security review then restricted `hidden` to that
exact container and made clipboard fallback report selection success truthfully.

### Task 5: Guided Home and Recovery Content

**Files:**
- Create: `academy/guides/home.md`
- Create: `academy/guides/recovery.md`
- Create: `academy/actions/home.json`
- Create: `academy/actions/recovery.json`
- Modify: `site/templates/index.html`
- Modify: `site/templates/recovery.html`
- Modify: `academy/lesson-action.schema.json`
- Modify: `academy_engine/lesson_actions.py`
- Modify: `scripts/build_preview_site.py`
- Modify: `scripts/check_preview_site.py`
- Modify: `tests/test_lesson_actions.py`
- Modify: `tests/test_preview_site.py`

**Interfaces:**
- Consumes: the action contract and renderer from Tasks 2-3.
- Produces stable Home action IDs `home-fork`, `home-clone`, `home-enter-clone`, `home-install`, `home-launch-console`, and `home-doctor`.
- Produces stable Recovery action IDs `recovery-inspect`, `recovery-return-attempt`, `recovery-repair-remotes`, `recovery-check`, `recovery-reset`, and `recovery-return-base`.
- Narrows action resources to one canonical Academy GitHub HTTPS boundary shared by schema, runtime, and artifact checker.

- [x] **Step 1: Write novice-path RED tests**

Assert Home defines fork before linking the GitHub fork page; defines clone, repository, `origin`, and `upstream` before first command use; identifies prerequisites; labels every command surface; and shows Guided, Reference lesson, and Coming next as three distinct states. Assert Recovery branches on dirty state, wrong branch, unsafe remotes, and existing attempts and never says only `make the repository clean`, `delete the branch`, `reset --hard`, or `force-push`.

- [x] **Step 2: Run Home/Recovery tests and verify RED**

Run: `python -m unittest tests.test_preview_site.PreviewSiteTests.test_home_teaches_every_prerequisite_before_first_use tests.test_preview_site.PreviewSiteTests.test_recovery_is_a_bounded_operational_decision_tree -v`

Expected: FAIL against the current hand-written pages.

- [x] **Step 3: Author Home's exact learning sequence**

Use these headings in order: `Start here`, `What the Academy changes`, `Create your practice fork`, `Clone it to your computer`, `Install the reviewed Academy tools`, `Open the operations console`, `Run readiness checks`, `Choose your first lesson`, `Course status`, `Get help`. Explain that a fork is the learner-owned GitHub copy, a clone is the local working copy, `origin` points to the fork, and `upstream` points to `arbiterForge/arbiter-academy`. Render the exact fast-install and console-launch commands from **Cross-plan integration order**. Beside each fast installer, link its immutable release asset source plus the verify-first script/checksum path and state that the piped script validates the downloaded bundle, not its own already-executing bytes. Delete the old inline 46-line bootstrap from the public page.

- [x] **Step 4: Author Recovery's exact decision order**

Use these decisions in order: repository not found/not Git; dirty worktree; wrong branch/detached HEAD; unsafe/missing remotes; no prepared attempt; failed Check with clean committed evidence; retry; return to `main`. Each branch states `Stop`, the observation command or console action, the safe next action, and what is preserved.

- [x] **Step 5: Run site tests and verify GREEN**

Run: `python -m unittest tests.test_preview_site -v`

Expected: all Home/Recovery and legacy site tests PASS. Installer-command and console-launch identity remain combined-head gates in Task 8.

- [x] **Step 6: Commit the guided entry/recovery slice**

```powershell
git add academy/guides/home.md academy/guides/recovery.md academy/actions/home.json academy/actions/recovery.json site/templates/index.html site/templates/recovery.html tests/test_preview_site.py
$ca-commit
```

The initial slice landed as `afc1bfd` (`feat(academy): guide entry and recovery paths`). Exact-diff
review then BLOCKed the fresh-clone bridge, Recovery executability, resource validation parity, and
resource landmark semantics. Test-first remediation landed as `f864264`
(`fix(academy): make entry and recovery executable`). Independent re-review returned PASS with no
findings. Fresh evidence covered 86 lesson/site tests, 49 remotes/Doctor/project-state tests, 11
browser-control tests, a staged-byte secret scan over all 10 committed files, fresh build and artifact
validation, and desktop/mobile browser inspection.

### Task 6: F01 Exact Evidence Lifecycle

**Files:**
- Create: `academy/actions/F01-fork-clone-doctor.json`
- Modify: `academy/tracks/foundations/F01-fork-clone-doctor.md`
- Modify: `academy_engine/checkpoints.py`
- Modify: `academy_engine/curriculum.py`
- Modify: `tests/test_lesson_actions.py`
- Modify: `tests/test_foundations_labs.py`
- Modify: `tests/test_preview_site.py`

**Interfaces:**
- Consumes existing verifier behavior: `prepare_lab`, `inspect_doctor`, `record_foundations_doctor`, `evaluate_checkpoint`, and `reset_lab`.
- Produces ordered action IDs `F01-prepare`, `F01-inspect-remotes`, `F01-repair-origin`, `F01-set-upstream`, `F01-disable-upstream-push`, `F01-select-push-default`, `F01-host-doctor`, `F01-academy-doctor`, `F01-inspect-report`, `F01-stage-report`, `F01-review-commit-boundary`, `F01-commit-report`, `F01-confirm-clean`, `F01-check`, `F01-return-base`, and `F01-reset-retry`.

- [x] **Step 1: Write F01 lifecycle RED tests**

Assert the 16 IDs above occur once and in order; every action has an expected result and recovery; the host Doctor variants are exactly `host: claude-code, command: /ca:doctor`, `host: codex, command: $ca-doctor`, and the two Pi alternatives `host: pi, command: /ca-doctor` plus `/skill:ca-doctor`; native shell variants omit `!`; harness shell variants prepend exactly one `!`; host-native Doctor and commit-gate commands omit `!`.

Assert rendered prose says Academy Doctor creates `.codearbiter/reports/academy/F01-doctor.json`; the learner inspects and stages only that path, reviews the proposed commit boundary, and supplies any genuine approval requested by the gate; an `agent` owns `F01-commit-report` through host-native CodeArbiter variants `host: claude-code, command: /ca:commit`, `host: codex, command: $ca-commit`, and `host: pi` commands `/ca-commit` plus `/skill:ca-commit`. Check uses the externally installed verifier, Doctor failure forbids the evidence commit, and Check failure preserves the clean committed attempt.

- [x] **Step 2: Run F01 tests and verify RED**

Run: `python -m unittest tests.test_lesson_actions tests.test_foundations_labs tests.test_preview_site -v`

Expected: FAIL because F01 is prose-only and collapses the lifecycle.

- [x] **Step 3: Rewrite F01 to the approved anatomy**

Use headings exactly: `Know before you begin`, `What you will prove`, `Prepare safely`, `Practice`, `Recognize success`, `Check`, `Recover or continue`, `Understand the mechanism`. Before preparation, require clean `main`. After `F01-prepare`, require `academy/F01-fork-clone-doctor/<attempt>` and explain that `<attempt>` is the number printed by Academy, not literal input.

- [x] **Step 4: Encode exact observable outcomes**

Require the report bytes to decode to:

```json
{
  "schema_version": 1,
  "safe_for_push_labs": true,
  "effective_push_remote": "origin"
}
```

Require `git status --short` to print nothing before external Check. Require Check success text to contain `checkpoint F01-fork-clone-doctor: passed; progress: .academy/progress.json`. Explain that the progress record is written only after the external verifier independently reads the committed report and live Git configuration.

`F01-stage-report` is explicitly `actor: learner` with native-terminal and harness shell variants for staging the one report path. `F01-review-commit-boundary` is a learner review/approval action with no command. `F01-commit-report` is explicitly `actor: agent`, `surface: null`, `language: codearbiter`, and the four host variants above; it contains no shell or learner-owned commit command.

- [x] **Step 5: Add end-to-end real-repository evidence coverage**

Extend the existing F01 fixture test to execute prepare, configure remotes, run `main(["doctor", "F01-fork-clone-doctor"])`, commit only the report, assert clean state, run external Check, and assert progress. Add mutations for uncommitted report, report committed with extra path, changed live remote after commit, missing upstream push-disable, wrong `remote.pushDefault`, and Check from an in-checkout verifier; each must fail without deleting the attempt commit.

- [x] **Step 6: Run F01 and scenario tests and verify GREEN**

Run: `python -m unittest tests.test_lesson_actions tests.test_foundations_labs tests.test_doctor tests.test_checkpoints tests.test_scenario -v`

Expected: all F01 lifecycle and existing verifier tests PASS.

- [x] **Step 7: Commit the F01 slice**

```powershell
git add academy/actions/F01-fork-clone-doctor.json academy/tracks/foundations/F01-fork-clone-doctor.md tests/test_lesson_actions.py tests/test_foundations_labs.py tests/test_preview_site.py
$ca-commit
```

Use commit title `docs: teach the complete F01 evidence lifecycle`.

The complete lifecycle landed as `39e52c1` (`feat(academy): teach the complete F01 evidence
lifecycle`). SMARTS approved the behavioral classification because the bounded lesson required a
narrow guided-heading compatibility seam and exact report-only commit enforcement. Review then
BLOCKed one approval step that labeled a harness interaction as Native terminal. Test-first
correction `e819b98` added the closed, non-command `active-harness` surface; generic hostless
`harness` remains rejected and command variants cannot use the new surface. Exact-diff re-review
returned PASS with no findings.

Fresh bounded evidence covered 93 action/site/contract tests, 11 curriculum tests, 10 project-state
tests, five focused approval-surface tests, eight behavioral lifecycle proofs, and four real-repository
lifecycle, mutation, reset, and authority cases. Lint, compile, package-resource, fresh build, artifact
validation, staged-byte secret scans, and diff checks passed. The 35-test Foundations module also
proved every F01 case, but six unrelated F03 source-pin cases remained red because
`CODEARBITER_TASKWRITE` and `CODEARBITER_SOURCE_SHA` were absent; they are not recorded as green and
the Task 6 diff does not touch their pin loader.

### Task 7: Editorial Visual System and Responsive Accessibility

**Files:**
- Modify: `site/assets/academy.css`
- Modify: `site/templates/base.html`
- Modify: `site/templates/lab.html`
- Modify: `tests/test_preview_site.py`

**Interfaces:**
- Consumes semantic classes from Tasks 3-6.
- Produces responsive layouts at 1440x900, 1024x768, 390x844, 320x568, and 200% zoom without clipped content or reordered lesson meaning.

- [x] **Step 1: Write CSS contract RED tests**

Assert `min-width: 0` on grid children, bounded horizontal scrolling on command `<pre>`, `overflow-wrap: anywhere` on prose/path output, 44px minimum pointer targets, visible `:focus-visible`, `[hidden] { display: none !important; }`, a no-motion media query, a high-contrast forced-colors rule, a 42rem single-column breakpoint, and no `.lab-grid` card layout, `radial-gradient`, or invented metric component.

- [x] **Step 2: Run visual-contract tests and verify RED**

Run: `python -m unittest tests.test_preview_site.PreviewSiteTests.test_guided_visual_contract_is_editorial_responsive_and_accessible -v`

Expected: FAIL because the current CSS uses card grids/gradients and lacks guided controls.

- [x] **Step 3: Implement the restrained lesson hierarchy**

Use a linear course ledger for publication states, numbered action rails for the main lesson, compact role labels that include text and icon shape, inset expected-result/recovery blocks, and a sticky desktop TOC that becomes a normal-flow disclosure-free list on narrow screens. Keep the existing local Manrope and JetBrains Mono assets.

- [x] **Step 4: Verify the generated artifact at all required viewports**

Build and serve:

```powershell
python scripts/build_preview_site.py --output site/generated --release-sha 1111111111111111111111111111111111111111
python -m http.server 4333 --directory site/generated
```

Capture Home, Recovery, and F01 at 1440x900, 1024x768, 390x844, and 320x568; repeat F01 at 200% zoom, keyboard-only, and reduced motion. Record no clipping, overlap, obscured focus, inaccessible command, semantic reordering, or decorative competition. If any occurs, add a failing CSS/markup regression before changing the styles.

- [x] **Step 5: Run site tests and artifact checker**

Run: `python -m unittest tests.test_preview_site -v`

Run: `python scripts/check_preview_site.py site/generated`

Expected: both commands PASS.

- [x] **Step 6: Commit the visual slice**

```powershell
git add site/assets/academy.css site/templates/base.html site/templates/lab.html tests/test_preview_site.py
$ca-commit
```

Use commit title `style: establish guided academy lesson hierarchy`.

The editorial visual system landed as `238a1be` (`feat(site): establish guided lesson
hierarchy`). Browser inspection covered Home, Recovery, and F01 at 1440x900, 1024x768,
390x844, and 320x568, plus a 720x450 reflow proxy for 200% zoom. Document width remained
contained, command regions remained bounded and horizontally scrollable, and the narrow lesson
TOC followed the article in normal flow. Live keyboard focus injection and media-feature emulation
were unavailable in the embedded browser and are not claimed; executable focus-visible,
reduced-motion, and forced-colors contracts cover that boundary.

Independent review BLOCKed sticky-header fragment navigation because TOC targets landed behind the
header. Test-first correction `30d2e15` (`fix(site): keep lesson anchors below sticky header`)
added 6rem desktop and 9rem <=42rem target offsets. Live reproduction proved the corrected
`Prepare safely` heading below the header at 1024x768 and 390x844, and exact-diff re-review returned
PASS with no findings. Fresh evidence covered 56 preview-site tests, 10 project-state tests,
tabnanny, compileall, a fresh build, artifact validation, staged secret scans, and diff checks.

### Task 8: Fail-Closed Publication and Deployment Validation

**Files:**
- Modify: `scripts/check_preview_site.py`
- Modify: `tests/test_preview_site.py`
- Modify: `tests/test_pages_workflow.py`
- Modify: `.github/workflows/academy-pages.yml`
- Modify: `README.md`
- Modify: `install/install.ps1`
- Modify: `install/install.ps1.sha256`
- Modify: `install/install.sh`
- Modify: `install/install.sh.sha256`
- Verify: `scripts/build_release_bundle.py`
- Modify: `tests/test_installers.py`
- Modify: `tests/test_release_bundle.py`

**Interfaces:**
- Produces: `check_preview_site(root: Path) -> None` acceptance of the exact Preview 0.3 artifact only.
- Produces: `release.json` with `{"release": "preview-0.3", "commit": <exact 40-char SHA>, "lesson_contract_version": 1}`.

- [ ] **Step 1: Write artifact mutation RED tests**

Build once, copy the artifact per mutation, and assert the checker rejects: removed JS; changed JS/CSS hash; P06/P07 link; F01 missing guided label; F02 falsely guided; `available_labs`/`runnable_labs` drift; missing action ID; duplicate DOM ID; dangling copy target/status; copied command text in an HTML attribute; inline handler/script; remote runtime asset; hidden-by-default variant without a no-JS path; and release SHA/version mismatch.

Add workflow tests proving deployment cannot begin until the GitHub Release tag resolves to the exact merge SHA and these assets exist with matching checksums: `install.ps1`, `install.ps1.sha256`, `install.sh`, `install.sh.sha256`, `arbiter-academy-preview-0.3.zip`, and `arbiter-academy-preview-0.3.zip.sha256`.

- [ ] **Step 2: Run checker tests and verify RED**

Run: `python -m unittest tests.test_preview_site tests.test_pages_workflow -v`

Expected: the new Preview 0.3 mutations FAIL their assertions against the existing checker/workflow.

- [ ] **Step 3: Implement exact artifact validation**

Update allowed elements/attributes and reviewed hashes only after final asset bytes settle. Require one H1, skip link, header/nav/main/footer, unique IDs, resolved ARIA/copy references, local script/style/font/image targets, no inline executable content, and the exact page inventory: Home, Recovery, F01-P05 lab pages, release JSON, and reviewed assets. Add a pre-deploy workflow job that uses the GitHub API to require tag `preview-0.3` at the workflow's exact merge SHA, downloads the six named release assets, verifies all three checksum files, and exposes a success output required by the Pages deploy job. A missing/mismatched tag, asset, or checksum blocks deployment rather than publishing dead installer links.

- [ ] **Step 4: Update README without duplicating the course**

State that Preview 0.3 has nine runnable labs, F01 is the first guided lesson, F02-P05 remain reference lessons awaiting guided rewrites, P06-P07 are coming next, and the website is the course. Link directly to the public Home, F01, and Recovery pages; keep commands in their action manifests rather than copying the lesson into README.

- [ ] **Step 5: Finalize combined-head release assets before review**

From the combined guided-site plus operations/TUI head, set `SOURCE_DATE_EPOCH=315532800` and `PYTHONHASHSEED=0`. In two separate fresh temporary directories, build `workshop_queue-0.1.0-py3-none-any.whl` with the pinned local `setuptools==83.0.0`, `pip wheel --no-index --no-deps --no-build-isolation`, and no source outside the combined checkout; require the two wheel byte streams to match. Feed each wheel to `scripts/build_release_bundle.py` with the reviewed wheelhouse and require identical `arbiter-academy-preview-0.3.zip` bytes/digests.

Replace the bundle-digest literal in both installers with that combined-head digest, regenerate `install/install.ps1.sha256` and `install/install.sh.sha256` as canonical lowercase `<sha256><two spaces><basename><LF>` UTF-8 without BOM, and run `tests.test_installers tests.test_release_bundle tests.test_runtime_wheelhouse`. Add a regression that changes one packaged guide/action byte and proves the wheel/bundle digest changes, while two builds of identical source remain byte-identical.

Stage exactly the four installer/checksum files plus their changed tests and invoke `$ca-commit` with title `build: finalize Preview 0.3 release assets`. This asset-finalization commit MUST precede full local gates, independent review, and exact-head CI; Task 9 may verify these bytes but MUST NOT discover or repair a stale digest after CI.

- [ ] **Step 6: Run complete local release gates**

```powershell
python -m tabnanny academy_engine scripts tests workshop_queue
python -m compileall -q academy_engine scripts tests workshop_queue
python -m unittest tests.test_preview_manifest tests.test_lesson_actions tests.test_preview_site tests.test_pages_workflow tests.test_foundations_labs -v
node --test tests/site/academy.test.mjs
python -m unittest tests.test_installers tests.test_runtime_wheelhouse tests.test_operations tests.test_return_to_base tests.test_tui_state tests.test_tui_app -v
python scripts/build_preview_site.py --output site/generated --release-sha 2222222222222222222222222222222222222222
python scripts/check_preview_site.py site/generated
python scripts/scan_secrets.py --staged
```

Expected: every command PASS; generated `release.json` names Preview 0.3, contract version 1, and the supplied SHA.

- [ ] **Step 7: Commit the release-validation slice**

```powershell
git add scripts/check_preview_site.py tests/test_preview_site.py tests/test_pages_workflow.py .github/workflows/academy-pages.yml README.md tests/test_installers.py tests/test_release_bundle.py
$ca-commit
```

Use commit title `chore: gate the guided F01 preview release`.

### Task 9: Independent Review, Exact-Head CI, and Pages Proof

**Files:**
- Verify: all files in Tasks 1-8
- Publish after explicit release confirmation: `install/install.ps1`, `install/install.sh`, their two SHA-256 files, `arbiter-academy-preview-0.3.zip`, and its SHA-256 file

**Interfaces:**
- Consumes: clean feature-branch HEAD and the repository's governed review/PR flow.
- Produces: a merged exact-head Preview 0.3, a `preview-0.3` tag/GitHub Release bound to that merge, and a Pages deployment whose public `release.json` matches the merged commit.

- [ ] **Step 1: Run the novice cold-read review**

Give two independent reviewers only the public prerequisite statement. Require each to identify every actor/surface, explain fork/clone/origin/upstream before use, select a correct host/OS command, complete the F01 evidence lifecycle without an unstated command, identify the expected result at every step, and recover from dirty state plus unsafe upstream. Treat every miss as a blocker and add a failing regression test before correction.

- [ ] **Step 2: Run independent code/content and visual review**

Require zero BLOCK findings for manifest authority, command-byte identity, injection safety, no-JS completeness, F01 verifier truth, responsive layout, keyboard flow, focus visibility, and anti-slop design-system compliance.

- [ ] **Step 3: Run the repository's full governed commit/PR gate**

Re-run exact-head tests after every correction on the combined site + operations/TUI + installer head. Push `codex/academy-preview-0.3`, open a ready Academy PR, and include exact commit/tree, wheel/install-bundle hashes, test counts, novice-review result, terminal acceptance, screenshot matrix, and the explicit statement that P06/P07 remain unavailable. Neither component branch may merge or publish independently.

- [ ] **Step 4: Wait once for terminal hosted checks**

Use one bounded local monitor for the PR head and one long wait. Do not make repeated inference calls while CI is unchanged. Merge under the user's Academy-only merge authority only when all required checks and review threads are green at the exact PR head.

- [ ] **Step 5: Prepare and verify the immutable release assets**

Build the Academy wheel and deterministic bundle from the exact green PR head twice in separate temporary directories and require identical bundle SHA-256 values. Recompute both installer digests and require the tracked `install/install.ps1.sha256` and `install/install.sh.sha256` bytes to match canonical `<sha256><two spaces><filename><LF>` form exactly; generate only the bundle checksum asset in that same form. Verify the installers embed the bundle digest, execute the documented verify-first paths against a loopback release fixture, and confirm the six upload files contain no path outside the reviewed set.

- [ ] **Step 6: Confirm, merge, and publish the tag/release at the exact merge**

Before creating the irreversible tag/GitHub Release, present the exact green PR head, prepared asset hashes, intended tag `preview-0.3`, and the requirement that the tag target will be the resulting merge SHA; obtain the explicit release confirmation required by CodeArbiter. Merge the authorized Academy PR, resolve the merge SHA, create the annotated tag at that SHA through the governed release route, push the tag, and create the GitHub Release with exactly the six reviewed assets. Immediately verify the remote tag target, release target, asset names, byte lengths, and SHA-256 values. Do not reuse or overwrite an existing tag/release.

- [ ] **Step 7: Let the gated Pages deployment complete**

The main Pages run waits for the release assets. Use one bounded monitor and one long wait; do not repeatedly poll with model calls. Require the release-asset pre-deploy job and Pages deploy job to succeed at the exact merge SHA.

- [ ] **Step 8: Verify the deployed exact merge**

Verify the Pages workflow for the merge SHA succeeds, then fetch the public Home, Recovery, F01, and `release.json`. Require HTTP 200; `release == "preview-0.3"`; `lesson_contract_version == 1`; `commit` equals the merged SHA; F01 has a guided link; F02-P05 have reference labels/links; and P06/P07 have status text but no runnable links.

- [ ] **Step 9: Record the release evidence and close the slice**

Persist PR URL, merged SHA, Pages run URL, production URLs, screenshot inventory, novice-review reports, and exact terminal check results in the governed handoff/audit location selected by the active CodeArbiter route. Do not write live sprint history into the Academy's fictional `.codearbiter/sprint-log.md` fixture.

## Plan Self-Review

- Spec coverage: publication truth, action schema/references, Home, Recovery, F01 lifecycle, renderer, local JS, host/OS variants, copy behavior, accessibility, responsive validation, exact-head CI, and Pages proof each map to a task.
- Scope boundary: the plan consumes a future console command only after its separate dependency/ADR/operations plan lands; it does not implement or silently substitute a TUI.
- Completeness scan: every code-producing step names its files, interfaces, test command, expected result, and concrete behavior.
- Type consistency: `PreviewManifest`, `CommandVariant`, `LessonAction`, `LessonActionManifest`, loader names, action IDs, contract versions, release name, and output fields are consistent across tasks.
- Publication safety: F01 is the only guided lab; F02-P05 remain runnable reference lessons; P06/P07 remain status-only.
