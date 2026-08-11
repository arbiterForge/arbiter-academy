# Arbiter Academy Operations TUI Implementation Plan

> Deferred planning record. The website remains the course. Before implementation resumes, reconcile
> this draft with the approved four-operation boundary: setup, Check, reset/retry, and lesson change.
> No console command or TUI-specific action surface described below is public today.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build one typed `AcademyOperations` boundary for the repository setup/check/reset lifecycle and a focused full-screen console for readiness Doctor, F01 evidence Doctor, published-lab selection, prepare, check, reset/retry, return-to-base, progress, update, and opening the matching website lesson.

**Architecture:** Trusted Academy operations remain in the installed verifier and delegate to the existing doctor, publication, scenario, checkpoint, progress, and update modules. A pure immutable console reducer drives a prompt-toolkit view; the view never calls Git or verifier modules directly, and the existing CLI becomes a second renderer over the same operation results. Mutations use an exact-state preflight token, a process-local operation lock, and low-level revalidation immediately before writes.

**Tech Stack:** Python 3.11/3.12, `prompt_toolkit==3.0.53`, `wcwidth==0.8.2`, stdlib `dataclasses`/`enum`/`threading`/`webbrowser`, `unittest`, GitHub Actions on Windows and Ubuntu, committed offline wheels.

## Global Constraints

- The website remains the teaching surface; the console contains operational status and bounded results, never lesson prose or Markdown rendering.
- `$ca-add-dep` MUST accept `prompt_toolkit==3.0.53` and `wcwidth==0.8.2` before either wheel is added or either package is imported.
- `$ca-adr` MUST record the user-attributed standard-library-runtime exception, and the accepted ADR MUST be reconciled into `.codearbiter/tech-stack.md` and `.codearbiter/security-controls.md` before console implementation.
- If either governance gate fails, stop console work after the shared operations and CLI-parity tasks; do not substitute curses, raw VT handling, Textual, or another dependency.
- All authoritative operations require an Academy verifier installed outside the learner checkout; publication, titles, eligibility, and lesson paths come only from installed package data.
- `prepare`, evidence-recording Doctor, `check`, `reset`, `return-to-base`, and `update` revalidate their complete preflight immediately before mutation and permit only one mutating operation per `AcademyOperations` instance. Readiness Doctor never writes; evidence Doctor is a distinct operation.
- Reset never discards dirty work. Return-to-base preserves the attempt branch and creates no archive ref. Whole-tool uninstall is not a console operation.
- The TUI is full-screen only on an interactive TTY at least 72 columns by 20 rows; otherwise render a readable text snapshot and exit `2` without entering the alternate screen.
- Supported hosted cells are `windows-latest` and `ubuntu-latest`, each on Python `3.11` and `3.12`.
- Runtime installation resolves no package from an index: build and installer tests use `--no-index --find-links .github/wheelhouse` with the reviewed wheel hashes in this plan.
- Preserve every existing CLI command, exit code, stdout line, stderr line, trust check, and publication check unless this plan explicitly adds `console` or `return-to-base`. `graduate`, `export-catalog`, and `verify-track` remain on their existing direct CLI paths because they are outside the console's operational lifecycle; byte-exact characterization proves that intentional boundary.
- Initial install and whole-tool teardown remain installer lifecycle responsibilities. Version 1 of the console MUST NOT expose `install`, `uninstall`, `remove-tools`, or arbitrary command execution.
- This component plan starts after Task 1 of `2026-08-10-guided-f01-release.md` establishes the Preview 0.3 truth model. Its reviewed head is integrated with the guided-site head; it MUST NOT merge, publish, or advertise Preview 0.3 independently.

---

## File map

- Create `academy_engine/operations.py`: typed application boundary, read models, mutation plans, exact-state tokens, operation lock, and fixed lesson URL resolution.
- Create `academy_engine/return_to_base.py`: the single bounded Git transition from a clean canonical attempt to `main`.
- Create `academy_engine/tui/__init__.py`: exports `run_console` without importing prompt-toolkit during ordinary CLI operations.
- Create `academy_engine/tui/state.py`: immutable console state, events, action availability, and pure reducer.
- Create `academy_engine/tui/app.py`: prompt-toolkit application, key bindings, async operation dispatch, confirmation dialog, and non-TTY fallback.
- Create `academy_engine/tui/view.py`: full/wide and narrow layout composition plus plain-text fallback rendering.
- Create `academy_engine/tui/style.py`: restrained semantic style classes; no ANSI literals outside prompt-toolkit.
- Modify `academy_engine/cli.py`: parse `console` and `return-to-base`; route Doctor, prepare, reset, update, progress, and check through `AcademyOperations`; preserve graduate, export-catalog, and verify-track on their characterized direct paths.
- Modify `academy_engine/scenario.py`: expose `next_attempt(root: Path, lab_id: str) -> int` for preflight; keep prepare/reset mutation authority here and revalidate independently during execution.
- Modify `academy_engine/preview.py`: expose installed runnable labs and fixed, validated lesson paths.
- Modify `pyproject.toml`: exact runtime pins and TUI package inclusion.
- Add `.github/wheelhouse/prompt_toolkit-3.0.53-py3-none-any.whl` and `.github/wheelhouse/wcwidth-0.8.2-py3-none-any.whl` only after governance acceptance.
- Add `.github/wheelhouse/prompt_toolkit-3.0.53.LICENSE` and `.github/wheelhouse/wcwidth-0.8.2.LICENSE` from the reviewed distributions.
- Modify `.github/wheelhouse/README.md`: provenance, size, SHA-256, license, and runtime purpose for both wheels.
- Modify `.github/workflows/academy-verify.yml`: platform/Python matrix and offline runtime install proof.
- Leave `.github/workflows/academy-pages.yml` to the sibling guided-F01 release plan, which integrates the offline runtime and release-asset gate on the combined head.
- Create `tests/test_operations.py`, `tests/test_return_to_base.py`, `tests/test_tui_state.py`, `tests/test_tui_app.py`, and `tests/test_runtime_wheelhouse.py`.
- Modify `tests/test_academy_cli.py`, `tests/test_installation.py`, `tests/test_project_state.py`, and `scripts/run_test_shards.py`.
- Modify `README.md`: console launch/recovery commands and the explicit installer-versus-lesson lifecycle boundary.

## Public installer and console interface

The F01 website plan may consume these commands verbatim. Preview 0.3 exposes no PATH-dependent shorthand.

**Windows PowerShell 7 fast install:**

```powershell
irm https://github.com/arbiterForge/arbiter-academy/releases/download/preview-0.3/install.ps1 | iex
```

**Windows PowerShell 7 console launch from the learner clone:**

```powershell
$academy = "$env:LOCALAPPDATA\ArbiterAcademy\preview-0.3\Scripts\arbiter-academy.exe"
& $academy --repository (Get-Location).Path console
```

**macOS/Linux POSIX fast install:**

```sh
curl -fsSL https://github.com/arbiterForge/arbiter-academy/releases/download/preview-0.3/install.sh | sh
```

**macOS/Linux console launch from the learner clone:**

```sh
academy="${XDG_DATA_HOME:-$HOME/.local/share}/arbiter-academy/preview-0.3/bin/arbiter-academy"
"$academy" --repository "$PWD" console
```

Both installers download `arbiter-academy-preview-0.3.zip` from the same release, validate the archive against the lowercase SHA-256 literal embedded in the reviewed installer, extract only its three pinned wheels and `installation-manifest.json`, create an isolated environment at the exact versioned path above, and install with `--no-index --find-links`. They fail if the versioned install root already exists, reject archive path escape and unexpected members, remove only the newly created versioned root after partial failure, and finish by running `arbiter-academy doctor` against the current directory when it is a Git worktree. The fast pipe validates the downloaded bundle but does not claim to validate the installer bytes that are already executing.

The verify-first alternatives download `install.ps1` plus `install.ps1.sha256`, or `install.sh` plus `install.sh.sha256`, from the same `preview-0.3` release, verify the script digest locally, then execute the verified file. F01 must link the rendered release asset and checksum source beside each fast command.

### Task 1: Clear dependency and architecture gates

**Files:**
- Create through `$ca-adr`: `.codearbiter/decisions/0004-prompt-toolkit-runtime.md`
- Modify through `$ca-adr`: `.codearbiter/decisions/decision-log.md`
- Modify: `.codearbiter/tech-stack.md`
- Modify: `.codearbiter/security-controls.md`

**Interfaces:**
- Consumes: approved design `docs/plans/2026-08-10-guided-course-and-operations-tui-design.md`.
- Produces: accepted dependency records for the exact two wheels and ADR-0004 authorizing the runtime-policy exception.

- [ ] **Step 1: Run the direct-dependency review before downloading or installing**

Invoke:

```text
$ca-add-dep "Add prompt_toolkit==3.0.53 as the operations-only full-screen console runtime and wcwidth==0.8.2 as its explicitly pinned direct runtime companion; require Python 3.11/3.12, Windows/Ubuntu support, offline wheels, license payloads, SHA-256 verification, no runtime package-index access, and no lesson-content rendering."
```

Expected: an accepted review for both exact versions. A rejection ends Tasks 6-10; Tasks 2-5 may still ship as shared operations plus CLI parity, with no `console` parser choice or TUI import.

- [ ] **Step 2: Record the runtime-policy decision**

Invoke:

```text
$ca-adr "Accept prompt_toolkit==3.0.53 plus wcwidth==0.8.2 for the operations-only Academy console, replacing the standard-library-only runtime rule solely for terminal input, resize, layout, and deterministic terminal testing; the website remains the course and raw terminal handling is rejected."
```

Expected: accepted `.codearbiter/decisions/0004-prompt-toolkit-runtime.md` attributed to the user and a matching decision-log entry.

- [ ] **Step 3: Reconcile the accepted controls**

Add these exact controls to the governed documents:

```markdown
- Runtime terminal UI: `prompt_toolkit==3.0.53`; display-width runtime: `wcwidth==0.8.2`.
- Runtime wheels are committed, SHA-256 pinned, license-retained, installed with `--no-index`, and exercised on Windows and Ubuntu with Python 3.11 and 3.12.
- The console cannot execute arbitrary learner commands, load lesson prose, derive authority from the learner checkout, or remove its own installation.
```

- [ ] **Step 4: Review the gate artifacts**

Run:

```powershell
rg -n "prompt_toolkit==3.0.53|wcwidth==0.8.2|no-index|Windows|Ubuntu|lesson prose|remove its own" .codearbiter
```

Expected: every exact pin and boundary appears in ADR-0004, tech stack, and security controls; no unresolved confirmation remains for this decision.

- [ ] **Step 5: Commit the governance slice**

Invoke `$ca-commit` with title:

```text
docs: record Academy console runtime decision
```

### Task 2: Characterize CLI behavior before extraction

**Files:**
- Modify: `tests/test_academy_cli.py`
- Create: `tests/test_operations.py`

**Interfaces:**
- Consumes: current `academy_engine.cli.main(argv: list[str] | None = None) -> int` behavior.
- Produces: `CliCase(argv: tuple[str, ...], exit_code: int, stdout: str, stderr: str)` characterization fixtures and operation-boundary RED tests.

- [ ] **Step 1: Add exact CLI characterization cases**

Add to `tests/test_academy_cli.py`:

```python
@dataclass(frozen=True)
class CliCase:
    argv: tuple[str, ...]
    exit_code: int
    stdout: str
    stderr: str


ARGPARSE_USAGE = (
    "usage: arbiter-academy [-h] [--repository REPOSITORY] [--matrix]\n"
    "                       {doctor,prepare,reset,update,progress,check,graduate,export-catalog,verify-track}\n"
    "                       [lab_id]\n"
)
CLI_ERROR_CASES = tuple(
    CliCase((command,), 2, "", ARGPARSE_USAGE + f"arbiter-academy: error: {command} requires LAB_ID\n")
    for command in ("prepare", "reset", "check")
)
```

For each error case, patch `sys.argv[0]` to the literal `arbiter-academy`, capture the full `SystemExit(2)` stderr, and store/assert the complete argparse frame rather than only the final message. For `prepare`, the exact fixture is:

```text
usage: arbiter-academy [-h] [--repository REPOSITORY] [--matrix]
                       {doctor,prepare,reset,update,progress,check,graduate,export-catalog,verify-track}
                       [lab_id]
arbiter-academy: error: prepare requires LAB_ID
```

Derive the reset/check fixtures only by replacing the final command word. Test success rendering with patched trusted modules for readiness Doctor, evidence Doctor, prepare, reset, update, progress, check pass/fail, graduate, export-catalog, and verify-track. Normalize nothing else; assert byte-exact stdout, stderr, and exit code.

- [ ] **Step 2: Add the operation routing RED test**

```python
def test_cli_constructs_one_operations_boundary_for_target(self) -> None:
    with patch("academy_engine.cli.AcademyOperations") as operations:
        operations.return_value.progress.return_value = OperationResult.success(
            OperationKind.PROGRESS,
            ProgressReport(()),
            stdout=("Academy progress: no prepared attempts.",),
        )
        exit_code = main(["--repository", str(REPOSITORY), "progress"])

    self.assertEqual(exit_code, 0)
    operations.assert_called_once_with(REPOSITORY)
    operations.return_value.progress.assert_called_once_with()
```

- [ ] **Step 3: Run the focused tests and prove RED**

Run:

```powershell
python -m unittest tests.test_academy_cli -v
```

Expected: existing characterizations pass and the routing test fails because `AcademyOperations` does not exist.

- [ ] **Step 4: Commit the characterization tests**

Invoke `$ca-commit` with title:

```text
test: characterize Academy CLI boundary
```

### Task 3: Build the typed read-only operations boundary

**Files:**
- Create: `academy_engine/operations.py`
- Modify: `academy_engine/preview.py`
- Modify: `tests/test_operations.py`

**Interfaces:**
- Consumes: `inspect_doctor(Path) -> DoctorReport`, `inspect_progress(Path) -> ProgressReport`, `load_preview_manifest(Path) -> PreviewManifest`, `Catalog.load(Path) -> Catalog`, and installed `load_contracts(Path) -> tuple[LabContract, ...]`.
- Produces:
  - `OperationKind(str, Enum)` values `DOCTOR_READINESS`, `DOCTOR_EVIDENCE`, `PREPARE`, `CHECK`, `RESET`, `RETURN_TO_BASE`, `UPDATE`, `OPEN_LESSON`, `PROGRESS`.
  - `OperationResult[T](kind, ok, value, stdout, stderr, error_code)` with `success(...)` and `failure(...)` constructors.
  - `LabOption(id, title, track, order, guided, prepared_attempts, lesson_url)`.
  - `AcademySnapshot(repository, branch, clean, detached, safe_for_push_labs, labs, progress)`.
  - `AcademyOperations(repository: Path, *, publication_root: Path | None = None, opener: Callable[[str], bool] = webbrowser.open_new_tab)`.
  - Read-only methods `snapshot()`, `doctor_readiness()`, `progress()`, and `open_lesson(lab_id: str)` returning `OperationResult`.
  - Evidence/mutation methods introduced in Task 4: `doctor_evidence(lab_id: str)` and `check(lab_id: str)` write durable learner evidence and therefore use the same preflight, lock, and exact-state revalidation path as Git mutations.
  - Evidence/mutation methods are introduced in Task 4: `preflight()` and `execute()` own evidence Doctor and Check writes.

- [ ] **Step 1: Write RED tests for installed-authority reads and fixed URLs**

```python
PREVIEW_0_3_RUNNABLE = (
    "F01-fork-clone-doctor",
    "F02-orient-to-state",
    "F03-work-the-board",
    "F04-fix-with-evidence",
    "P01-feature-through-plan",
    "P02-commit-review-pr",
    "P03-record-an-adr",
    "P04-review-a-dependency",
    "P05-checkpoint-remediation",
)


def test_snapshot_uses_installed_publication_and_repository_progress(self) -> None:
    operations = AcademyOperations(self.learner, publication_root=self.installed)
    snapshot = operations.snapshot().value
    self.assertIsNotNone(snapshot)
    self.assertEqual(tuple(lab.id for lab in snapshot.labs), PREVIEW_0_3_RUNNABLE)
    self.assertTrue(all(lab.lesson_url.startswith(ACADEMY_SITE_ORIGIN) for lab in snapshot.labs))


def test_open_lesson_rejects_checkout_controlled_title_or_path(self) -> None:
    (self.learner / "academy/publication/preview-0.3.json").write_text(
        '{"lesson_path":"https://attacker.invalid/"}', encoding="utf-8"
    )
    opened: list[str] = []
    result = AcademyOperations(
        self.learner,
        publication_root=self.installed,
        opener=lambda url: not opened.append(url),
    ).open_lesson("F01-fork-clone-doctor")
    self.assertTrue(result.ok)
    self.assertEqual(opened, [
        "https://arbiterforge.github.io/arbiter-academy/labs/F01-fork-clone-doctor/"
    ])
```

- [ ] **Step 2: Run the new tests and prove RED**

Run:

```powershell
python -m unittest tests.test_operations -v
```

Expected: import failure for `academy_engine.operations`.

- [ ] **Step 3: Add exact result and snapshot types**

Implement this public surface in `academy_engine/operations.py`:

```python
from __future__ import annotations

import webbrowser
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Generic, TypeVar

T = TypeVar("T")
ACADEMY_SITE_ORIGIN = "https://arbiterforge.github.io/arbiter-academy"


class OperationKind(str, Enum):
    DOCTOR_READINESS = "doctor-readiness"
    DOCTOR_EVIDENCE = "doctor-evidence"
    PREPARE = "prepare"
    CHECK = "check"
    RESET = "reset"
    RETURN_TO_BASE = "return-to-base"
    UPDATE = "update"
    OPEN_LESSON = "open-lesson"
    PROGRESS = "progress"


@dataclass(frozen=True)
class OperationResult(Generic[T]):
    kind: OperationKind
    ok: bool
    value: T | None
    stdout: tuple[str, ...] = ()
    stderr: tuple[str, ...] = ()
    error_code: str | None = None

    @classmethod
    def success(cls, kind: OperationKind, value: T, *, stdout: tuple[str, ...] = ()) -> "OperationResult[T]":
        return cls(kind, True, value, stdout)

    @classmethod
    def failure(
        cls,
        kind: OperationKind,
        code: str,
        message: str,
        *,
        stderr: tuple[str, ...] | None = None,
    ) -> "OperationResult[T]":
        return cls(kind, False, None, (), stderr or (f"error: {message}",), code)


@dataclass(frozen=True)
class LabOption:
    id: str
    title: str
    track: str
    order: int
    guided: bool
    prepared_attempts: tuple[int, ...]
    lesson_url: str


@dataclass(frozen=True)
class AcademySnapshot:
    repository: Path
    branch: str | None
    clean: bool
    detached: bool
    safe_for_push_labs: bool
    labs: tuple[LabOption, ...]
    progress: ProgressReport
```

Implement the read-only methods in the Interfaces block. The constructor canonicalizes the repository and publication root once. Each call catches only the listed domain exceptions already caught by `cli.main`, maps them to a path-free `OperationResult.failure`, and returns its domain object in `value` on success. `open_lesson` accepts only a lab in the installed manifest and constructs the URL from `ACADEMY_SITE_ORIGIN`, the literal `/labs/` segment, and the catalog-validated lab ID; a false or raised opener becomes `browser-open-failed`.

Build `LabOption.title` from the installed `academy/contracts.json` loaded through `load_contracts(publication_root)`, keyed one-to-one with the installed catalog; reject missing/duplicate/extra contract IDs. Build `prepared_attempts` by grouping the repository-derived `inspect_progress(repository).entries` by lab ID. Neither field may come from learner Markdown, learner catalog bytes, or a hard-coded display table.

- [ ] **Step 4: Characterize verifier trust and evidence writes without moving them yet**

Add characterization tests proving the current evidence Doctor writes `.codearbiter/reports/academy/F01-doctor.json` and successful Check writes `.academy/progress.json`. Move `ensure_authoritative_verifier` and `_verifier_publication_root` from `cli.py` into `operations.py` without weakening `_inside()` canonicalization, but keep both write paths behind RED tests until Task 4 adds mutation preflight/locking.

- [ ] **Step 5: Run read-operation and regression tests**

Run:

```powershell
python -m unittest tests.test_operations tests.test_academy_cli tests.test_preview_manifest tests.test_progress -v
```

Expected: PASS.

- [ ] **Step 6: Commit the read boundary**

Invoke `$ca-commit` with title:

```text
feat: add typed Academy operations boundary
```

### Task 4: Add exact mutation plans, return-to-base, and operation locking

**Files:**
- Create: `academy_engine/return_to_base.py`
- Modify: `academy_engine/operations.py`
- Modify: `academy_engine/scenario.py`
- Create: `tests/test_return_to_base.py`
- Modify: `tests/test_operations.py`

**Interfaces:**
- Consumes: `prepare_lab`, `reset_lab`, `update_academy`, canonical attempt syntax `academy/{lab_id}/{positive_integer}`, base branch `main`.
- Produces:
  - `RefExpectation(ref: str, target: str | None)`, where a 40-character `target` means that exact ref/OID pair MUST still exist and `target=None` means the named ref MUST still be absent.
  - `MutationPlan(kind, repository, lab_id, current_branch, resulting_branch, head_sha, status_sha256, remote_config_sha256, base_ref, current_attempt_ref, resulting_ref, archive_ref, upstream_ref, created_at, token, confirmation)`, where each ref field is `RefExpectation | None`, `None` means the operation cannot touch or depend on that ref, `created_at: datetime` is timezone-aware UTC, `confirmation: str | None`, and the timestamp fixes the reset archive name used by both preflight and execution.
  - `AcademyOperations.preflight(kind: OperationKind, lab_id: str | None = None, *, now: datetime | None = None) -> OperationResult[MutationPlan]`.
  - `AcademyOperations.execute(plan: MutationPlan) -> OperationResult[object]`; every successful domain result is wrapped in `OperationResult.success(...)` with the byte-exact legacy CLI stdout/stderr stored on the result.
  - `ReturnedToBase(lab_id, attempt_branch, base_branch, preserved_head)`.
  - `return_to_base(root: Path, lab_id: str, *, expected_head: str, expected_status_sha256: str, expected_base_target: str) -> ReturnedToBase`.
  - `next_attempt(root: Path, lab_id: str) -> int`, a public read-only wrapper over the existing contiguous-attempt validation.

- [ ] **Step 1: Write RED tests for return-to-base safety**

```python
def clean_status_digest() -> str:
    return hashlib.sha256(b"").hexdigest()


def test_return_to_base_preserves_clean_attempt_ref_and_switches_to_main(self) -> None:
    attempt = prepare_lab(self.root, "F01-fork-clone-doctor")
    result = return_to_base(
        self.root,
        attempt.lab_id,
        expected_head=attempt.commit_sha,
        expected_status_sha256=clean_status_digest(),
        expected_base_target=git(self.root, "rev-parse", "refs/heads/main"),
    )
    self.assertEqual(git(self.root, "branch", "--show-current"), "main")
    self.assertEqual(git(self.root, "rev-parse", attempt.branch), attempt.commit_sha)
    self.assertEqual(result.attempt_branch, attempt.branch)
    self.assertEqual(git(self.root, "for-each-ref", "--format=%(refname:short)", "refs/heads/academy/archive/"), "")


def test_return_to_base_refuses_dirty_wrong_or_changed_attempt_without_writes(self) -> None:
    before = git(self.root, "show-ref")
    with self.assertRaisesRegex(ReturnToBaseError, "clean matching Academy attempt"):
        return_to_base(
            self.root,
            "F01-fork-clone-doctor",
            expected_head="0" * 40,
            expected_status_sha256=clean_status_digest(),
            expected_base_target=git(self.root, "rev-parse", "refs/heads/main"),
        )
    self.assertEqual(git(self.root, "show-ref"), before)
```

- [ ] **Step 2: Write RED tests for token binding and the process-local lock**

```python
def test_execute_refuses_stale_plan_before_mutation(self) -> None:
    plan = self.operations.preflight(
        OperationKind.RETURN_TO_BASE, "F01-fork-clone-doctor"
    ).value
    self.assertIsNotNone(plan)
    (self.learner / "unexpected.txt").write_text("dirty\n", encoding="utf-8")
    result = self.operations.execute(plan)
    self.assertFalse(result.ok)
    self.assertEqual(result.error_code, "stale-preflight")
    self.assertEqual(current_branch(self.learner), plan.current_branch)


def test_execute_rejects_changed_present_or_expected_absent_refs(self) -> None:
    cases = (
        (self.return_plan, self.move_main_ref),
        (self.return_plan, self.move_current_attempt_ref),
        (self.prepare_plan, self.create_expected_absent_resulting_ref),
        (self.reset_plan, self.create_expected_absent_archive_ref),
        (self.update_plan, self.move_upstream_tracking_ref),
    )
    for plan, mutate_ref in cases:
        with self.subTest(ref=mutate_ref.__name__):
            mutate_ref()
            refs_before_execute = git(self.learner, "show-ref")
            result = self.operations.execute(plan)
            self.assertEqual(result.error_code, "stale-preflight")
            self.assertEqual(git(self.learner, "show-ref"), refs_before_execute)
            self.restore_fixture()


def test_second_mutation_is_rejected_while_first_holds_lock(self) -> None:
    entered = Event()
    release = Event()
    operations = AcademyOperations(self.learner)
    operations._before_mutation = lambda: (entered.set(), release.wait(5))
    first = Thread(target=lambda: operations.execute(self.prepare_plan))
    first.start()
    self.assertTrue(entered.wait(2))
    second = operations.execute(self.update_plan)
    self.assertEqual(second.error_code, "operation-active")
    release.set()
    first.join(5)
```

- [ ] **Step 3: Run focused tests and prove RED**

Run:

```powershell
python -m unittest tests.test_return_to_base tests.test_operations -v
```

Expected: missing `MutationPlan` and `return_to_base` failures.

- [ ] **Step 4: Implement state-bound preflight tokens**

Build `status_sha256` from `run_git(...).stdout.encode("utf-8", "surrogateescape")` for `git status --porcelain=v1 -z --untracked-files=all`. Build `remote_config_sha256` from the same reversible byte encoding of `git config --local --null --get-regexp "^(remote\\.|branch\\.|push\\.)"`; a return code other than `0` or `1` is a preflight failure. Build `base_ref` for `refs/heads/main`; build `current_attempt_ref` when the current branch is a canonical attempt; build `resulting_ref` for the branch prepare/reset/return/update can create or move; build `archive_ref` for reset's exact timestamped archive; build `upstream_ref` for `refs/remotes/upstream/main` on update. For a ref that must not yet exist, store its exact name with `target=None`; use a missing `RefExpectation` only when dispatch cannot touch or depend on that ref. Build `token` as SHA-256 over canonical UTF-8 JSON containing exactly `kind`, canonical repository path, lab ID or `null`, current branch, resulting branch, HEAD SHA, status digest, remote-config digest, each ref expectation as either `null` or `{ref, target}`, and the UTC timestamp. `execute()` MUST acquire `threading.Lock(blocking=False)`, recompute every repository-derived field, reuse the immutable plan's `created_at`, rebuild the token, compare the full plan, and return `stale-preflight` before dispatch if any expected-present ref moves, any expected-absent ref appears, or any other field differs.

Confirmation text is generated by `preflight()` and names exact paths/refs:

```text
Reset F01-fork-clone-doctor in C:\Academy\arbiter-academy: archive academy/F01-fork-clone-doctor/1 as academy/archive/F01-fork-clone-doctor/20260810T120000Z, then prepare academy/F01-fork-clone-doctor/2.
Return C:\Academy\arbiter-academy from academy/F01-fork-clone-doctor/1 to main; preserve academy/F01-fork-clone-doctor/1 at aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa and create no archive.
Update C:\Academy\arbiter-academy on main by fast-forward only; preserve every academy/* attempt and archive ref.
```

- [ ] **Step 5: Implement the low-level return operation**

`return_to_base()` validates repository root, zero status bytes, exact current attempt syntax, exact lab ID, expected HEAD, expected status digest, the current attempt ref target, and `refs/heads/main == expected_base_target`, then runs only `git switch main`. If switch fails, it verifies the attempt and base refs still resolve to their expected targets and raises `ReturnToBaseError`; it never deletes or rewrites any ref.

- [ ] **Step 6: Route existing mutations through `execute()`**

Add these exact pure render helpers; each tuple item is one legacy output line, except `report.render()` which may contain its existing internal newlines:

```python
def render_prepared(value: PreparedLab, *, action: str = "prepared") -> tuple[str, ...]:
    lines = [f"Academy {action}: {value.branch} at {value.commit_sha}"]
    if value.origin_repository_id is not None:
        lines.extend((
            f"Origin repository ID: {value.origin_repository_id}",
            f"Upstream repository ID: {value.upstream_repository_id}",
        ))
    return tuple(lines)

def render_returned(value: ReturnedToBase) -> tuple[str, ...]:
    return (f"Academy returned to main; preserved {value.attempt_branch} at {value.preserved_head}",)

def render_doctor_evidence(
    report: DoctorReport, destination: Path, repository: Path
) -> tuple[str, ...]:
    return (
        report.render(),
        f"Recorded {destination.relative_to(repository).as_posix()}",
    )

def render_checkpoint_result(value: CheckpointResult) -> OperationResult[CheckpointResult]:
    if value.passed:
        return OperationResult.success(
            OperationKind.CHECK,
            value,
            stdout=(f"checkpoint {value.lab_id}: passed; progress: .academy/progress.json",),
        )
    line = f"checkpoint {value.lab_id}: failed ({', '.join(value.failed_predicates)})"
    return OperationResult.failure(
        OperationKind.CHECK,
        "checkpoint-failed",
        line,
        stderr=(line,),
    )
```

Dispatch exactly:

```python
lab_id = plan.lab_id
if plan.kind in {OperationKind.PREPARE, OperationKind.RESET, OperationKind.RETURN_TO_BASE,
                 OperationKind.DOCTOR_EVIDENCE, OperationKind.CHECK} and lab_id is None:
    return OperationResult.failure(plan.kind, "lab-required", "operation requires a lab ID.")
installed_authority = self._installed_authority(plan.kind, lab_id)
if plan.kind is OperationKind.PREPARE:
    assert lab_id is not None
    value = prepare_lab(repository, lab_id, installed_authority=installed_authority)
    return OperationResult.success(plan.kind, value, stdout=render_prepared(value))
if plan.kind is OperationKind.RESET:
    assert lab_id is not None
    value = reset_lab(repository, lab_id, now=lambda: plan.created_at, installed_authority=installed_authority)
    return OperationResult.success(plan.kind, value, stdout=render_prepared(value, action="reset"))
if plan.kind is OperationKind.RETURN_TO_BASE:
    assert lab_id is not None
    assert plan.base_ref is not None and plan.base_ref.target is not None
    value = return_to_base(repository, lab_id, expected_head=plan.head_sha,
                           expected_status_sha256=plan.status_sha256,
                           expected_base_target=plan.base_ref.target)
    return OperationResult.success(plan.kind, value, stdout=render_returned(value))
if plan.kind is OperationKind.UPDATE:
    value = update_academy(repository)
    return OperationResult.success(plan.kind, value, stdout=(value.render(),))
if plan.kind is OperationKind.DOCTOR_EVIDENCE:
    assert lab_id is not None
    report = inspect_doctor(repository)
    value = record_foundations_doctor(repository, report)
    return OperationResult.success(
        plan.kind, value, stdout=render_doctor_evidence(report, value, repository)
    )
if plan.kind is OperationKind.CHECK:
    assert lab_id is not None
    value = evaluate_checkpoint(repository, lab_id)
    if value.passed:
        record_checkpoint(repository / ".academy" / "progress.json", value)
    return render_checkpoint_result(value)
```

`preflight()` supports exactly `DOCTOR_EVIDENCE`, `PREPARE`, `CHECK`, `RESET`, `RETURN_TO_BASE`, and `UPDATE`; all six acquire the process lock and revalidate immediately before writing. Only prepare/reset/return/update produce confirmation text; evidence Doctor and Check carry `confirmation=None` and execute after successful preflight without a confirmation dialog. `_installed_authority(kind, lab_id)` preserves the current CLI policy exactly: validate config and verifier authority for P02/P08 prepare/reset and all checks; for a later lab with P02 records, require installed authority before state access; otherwise return `False`. Reject all other kinds with `unsupported-mutation`. Do not expose a public mutation callback; tests patch a private `_before_mutation` callable initialized to `lambda: None`.

- [ ] **Step 7: Run mutation, scenario, and update suites**

Run:

```powershell
python -m unittest tests.test_return_to_base tests.test_operations tests.test_scenario tests.test_update -v
```

Expected: PASS, including dirty work, wrong branch, stale token, same-timestamp archive, unsafe remote, rollback, and lock contention cases.

- [ ] **Step 8: Commit the mutation boundary**

Invoke `$ca-commit` with title:

```text
feat: add safe Academy lesson transitions
```

### Task 5: Refactor the CLI to exact operations parity

**Files:**
- Modify: `academy_engine/cli.py`
- Modify: `tests/test_academy_cli.py`

**Interfaces:**
- Consumes: `AcademyOperations`, `OperationResult`, `OperationKind`, `MutationPlan` from Tasks 3-4.
- Produces: `_emit(result: OperationResult[object]) -> int`; new commands `console` and `return-to-base`.

- [ ] **Step 1: Add RED command parsing and parity tests**

```python
def test_return_to_base_cli_preflights_and_executes_without_interactive_prompt(self) -> None:
    lab_id = "F01-fork-clone-doctor"
    attempt_branch = "academy/F01-fork-clone-doctor/1"
    head = "a" * 40
    plan = MutationPlan(
        kind=OperationKind.RETURN_TO_BASE,
        repository=REPOSITORY,
        lab_id=lab_id,
        current_branch=attempt_branch,
        resulting_branch="main",
        head_sha=head,
        status_sha256=hashlib.sha256(b"").hexdigest(),
        remote_config_sha256="c" * 64,
        base_ref=RefExpectation("refs/heads/main", "d" * 40),
        current_attempt_ref=RefExpectation(f"refs/heads/{attempt_branch}", head),
        resulting_ref=RefExpectation("refs/heads/main", "d" * 40),
        archive_ref=None,
        upstream_ref=None,
        created_at=datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc),
        token="b" * 64,
        confirmation="Return the Academy fixture to main and preserve its attempt branch.",
    )
    result = OperationResult.success(
        OperationKind.RETURN_TO_BASE,
        ReturnedToBase(lab_id, attempt_branch, "main", head),
        stdout=(f"Academy returned to main; preserved {attempt_branch} at {head}",),
    )
    with patch("academy_engine.cli.AcademyOperations") as boundary:
        boundary.return_value.preflight.return_value = OperationResult.success(OperationKind.RETURN_TO_BASE, plan)
        boundary.return_value.execute.return_value = result
        exit_code = main(["--repository", str(REPOSITORY), "return-to-base", lab_id])
    self.assertEqual(exit_code, 0)
    boundary.return_value.execute.assert_called_once_with(plan)
```

Also replay every `CliCase` from Task 2 after patching `AcademyOperations`; compare exact exit code and output streams to the pre-extraction behavior.

- [ ] **Step 2: Run parity tests and prove RED**

Run:

```powershell
python -m unittest tests.test_academy_cli -v
```

Expected: failures show direct legacy dispatch and missing new choices.

- [ ] **Step 3: Replace direct dispatch with operation methods**

`main()` canonicalizes the requested repository once, constructs `AcademyOperations(requested_repository)`, and routes readiness/evidence Doctor, prepare, reset, update, progress, check, and `return-to-base`. Read-only commands call their operation method directly. Evidence-writing and Git-writing commands call `preflight()` and then `execute()`; the CLI remains non-interactive, so it executes a valid plan immediately. `graduate`, `export-catalog`, and `verify-track` retain their characterized direct dispatch. `_emit()` writes each operations result's `stdout` entry plus `\n`, each `stderr` entry plus `\n`, and returns `0 if result.ok else 1`. Preserve Task 2 byte-for-byte for every command-specific line and exit code; the only permitted argparse-frame delta is the deterministic addition of `console` and `return-to-base` to the displayed choice set, which receives its own exact fixture.

`console` performs a lazy import only inside its branch:

```python
if arguments.command == "console":
    from academy_engine.tui import run_console
    return run_console(operations)
```

- [ ] **Step 4: Prove exact CLI parity**

Run:

```powershell
python -m unittest tests.test_academy_cli tests.test_cli tests.test_doctor tests.test_progress tests.test_update -v
```

Expected: PASS with byte-exact legacy output plus the two new command contracts.

- [ ] **Step 5: Commit CLI extraction**

Invoke `$ca-commit` with title:

```text
refactor: route Academy CLI through operations
```

### Task 6: Vendor and prove the pinned offline runtime

**Files:**
- Modify: `pyproject.toml`
- Add: `.github/wheelhouse/prompt_toolkit-3.0.53-py3-none-any.whl`
- Add: `.github/wheelhouse/wcwidth-0.8.2-py3-none-any.whl`
- Add: `.github/wheelhouse/prompt_toolkit-3.0.53.LICENSE`
- Add: `.github/wheelhouse/wcwidth-0.8.2.LICENSE`
- Modify: `.github/wheelhouse/README.md`
- Create: `tests/test_runtime_wheelhouse.py`
- Modify: `tests/test_installation.py`
- Modify: `tests/test_project_state.py`

**Interfaces:**
- Consumes: accepted Task 1 dependency review and ADR-0004.
- Produces: offline-installable runtime locked to wheel SHA-256 values below.

- [ ] **Step 1: Add RED wheel identity tests**

```python
EXPECTED_RUNTIME_WHEELS = {
    "prompt_toolkit-3.0.53-py3-none-any.whl": "01c0891d7f9237d5e339f7d3e42cdae80b7534abb1c7c0e3352efba6231492f2",
    "wcwidth-0.8.2-py3-none-any.whl": "d63947694a0539a1d51e01eda7caf800c291020e6cdd7e28ad7b14dd33ad4f85",
}


def test_runtime_wheels_match_reviewed_hashes_and_contain_licenses(self) -> None:
    for name, digest in EXPECTED_RUNTIME_WHEELS.items():
        wheel = REPOSITORY / ".github/wheelhouse" / name
        self.assertEqual(hashlib.sha256(wheel.read_bytes()).hexdigest(), digest)
        with ZipFile(wheel) as archive:
            self.assertTrue(any(path.endswith(("LICENSE", "LICENSE.txt")) for path in archive.namelist()))
```

- [ ] **Step 2: Run wheel tests and prove RED**

Run:

```powershell
python -m unittest tests.test_runtime_wheelhouse -v
```

Expected: missing-wheel failures.

- [ ] **Step 3: Download only the accepted artifacts and verify before moving them into the repo**

Use a fresh task-specific directory and exact hashes:

```powershell
$academyDependencyReview = New-Item -ItemType Directory -Path (Join-Path $env:TEMP ("academy-runtime-" + [guid]::NewGuid()))
python -m pip download --only-binary=:all: --no-deps --dest $academyDependencyReview.FullName prompt_toolkit==3.0.53 wcwidth==0.8.2
Get-FileHash -Algorithm SHA256 (Join-Path $academyDependencyReview.FullName 'prompt_toolkit-3.0.53-py3-none-any.whl')
Get-FileHash -Algorithm SHA256 (Join-Path $academyDependencyReview.FullName 'wcwidth-0.8.2-py3-none-any.whl')
```

Expected digests are exactly the two values in `EXPECTED_RUNTIME_WHEELS`. Copy the verified wheels with `Copy-Item -LiteralPath` and extract the upstream license payloads verbatim into the named `.LICENSE` files.

- [ ] **Step 4: Pin runtime metadata and offline install behavior**

Set:

```toml
dependencies = [
  "prompt_toolkit==3.0.53",
  "wcwidth==0.8.2",
]
```

Update installation tests to build the Academy wheel with the existing pinned setuptools wheel, then install into an empty venv using:

```text
python -m pip install --no-index --find-links .github/wheelhouse dist/workshop_queue-0.1.0-py3-none-any.whl
```

Assert imported versions are `3.0.53` and `0.8.2`; repeat with network-denial shims so any index request fails the test.

- [ ] **Step 5: Run packaging tests**

Run:

```powershell
python -m unittest tests.test_runtime_wheelhouse tests.test_installation tests.test_project_state -v
```

Expected: PASS.

- [ ] **Step 6: Commit the reviewed runtime**

Invoke `$ca-commit` with title:

```text
build: package pinned Academy console runtime
```

### Task 7: Implement the pure console state reducer

**Files:**
- Create: `academy_engine/tui/__init__.py`
- Create: `academy_engine/tui/state.py`
- Create: `tests/test_tui_state.py`
- Modify: `pyproject.toml`

**Interfaces:**
- Consumes: `AcademySnapshot`, `LabOption`, `MutationPlan`, `OperationKind`, `OperationResult`.
- Produces:
  - `Pane(str, Enum)` values `LABS`, `ACTIONS`, `RESULT`.
  - `Dialog(plan: MutationPlan)`.
  - `ACTION_LABELS`, an immutable mapping from operation kinds to `Readiness Doctor`, `Record F01 Doctor evidence`, `Prepare`, `Check`, `Reset / retry`, `Return to main`, `Update checkout`, and `Open lesson`.
  - `ConsoleState(snapshot, selected_lab_id, pane, width, height, busy, dialog, last_result, exit_requested)`.
  - Events `MoveSelection(delta)`, `FocusNext`, `Resize(width, height)`, `Begin(kind)`, `PreflightReady(result)`, `Confirm`, `Cancel`, `OperationFinished(result, snapshot)`, `RequestExit`.
  - `available_actions(state: ConsoleState) -> tuple[OperationKind, ...]`.
  - `reduce(state: ConsoleState, event: ConsoleEvent) -> ConsoleState`.

- [ ] **Step 1: Write reducer RED tests**

```python
def test_busy_state_disables_every_mutation_but_keeps_navigation(self) -> None:
    busy = reduce(self.state, Begin(OperationKind.PREPARE))
    self.assertTrue(busy.busy)
    self.assertNotIn(OperationKind.PREPARE, available_actions(busy))
    self.assertNotIn(OperationKind.RESET, available_actions(busy))
    self.assertEqual(
        reduce(busy, MoveSelection(1)).selected_lab_id,
        "F02-orient-to-state",
    )


def test_cancelled_confirmation_clears_dialog_without_operation(self) -> None:
    waiting = reduce(self.state, PreflightReady(OperationResult.success(OperationKind.RESET, self.plan)))
    cancelled = reduce(waiting, Cancel())
    self.assertIsNone(cancelled.dialog)
    self.assertFalse(cancelled.busy)
    self.assertIsNone(cancelled.last_result)
```

Cover selection wrap, grouped lab order, guided/runnable labels, pane focus, wide/narrow transition at 96 columns, minimum-size state, invalid events, check result, operation error, and exit while busy.

- [ ] **Step 2: Run reducer tests and prove RED**

Run:

```powershell
python -m unittest tests.test_tui_state -v
```

Expected: import failure for `academy_engine.tui.state`.

- [ ] **Step 3: Implement immutable reducer transitions**

Use frozen dataclasses and `dataclasses.replace`; `reduce()` performs no I/O. `Begin` sets `busy=True`; preflight completion opens `Dialog` and clears `busy` only when `plan.confirmation` is not `None`. Evidence Doctor and Check plans have no confirmation, so the app dispatches them directly after preflight while remaining busy. `Confirm` closes a real dialog and sets `busy=True`; `Cancel` closes it without a result; `OperationFinished(result, snapshot)` sets `busy=False`, stores the result, and replaces the stale snapshot. `RequestExit` is ignored while busy and otherwise sets `exit_requested=True`.

- [ ] **Step 4: Add package discovery**

Change setuptools package selection to include both packages explicitly:

```toml
[tool.setuptools]
packages = ["workshop_queue", "academy_engine", "academy_engine.tui"]
```

- [ ] **Step 5: Run reducer and package tests**

Run:

```powershell
python -m unittest tests.test_tui_state tests.test_package_resource tests.test_project_state -v
```

Expected: PASS.

- [ ] **Step 6: Commit the reducer**

Invoke `$ca-commit` with title:

```text
feat: add deterministic Academy console state
```

### Task 8: Build the full-screen prompt-toolkit console

**Files:**
- Create: `academy_engine/tui/style.py`
- Create: `academy_engine/tui/view.py`
- Create: `academy_engine/tui/app.py`
- Modify: `academy_engine/tui/__init__.py`
- Create: `tests/test_tui_app.py`

**Interfaces:**
- Consumes: Task 7 reducer and `AcademyOperations` methods.
- Produces:
  - `render_plain(snapshot: AcademySnapshot, *, reason: str) -> str`.
  - `build_layout(get_state: Callable[[], ConsoleState]) -> Container`.
  - `AcademyConsole(operations: AcademyOperations, *, input: Input | None = None, output: Output | None = None)`.
  - `AcademyConsole.run() -> int`.
  - `run_console(operations: AcademyOperations) -> int`.

- [ ] **Step 1: Write non-TTY and minimum-size RED tests**

```python
def test_non_tty_prints_snapshot_without_importing_alternate_screen(self) -> None:
    output = StringIO()
    with patch("academy_engine.tui.app.sys.stdin.isatty", return_value=False), redirect_stdout(output):
        exit_code = run_console(self.operations)
    self.assertEqual(exit_code, 2)
    self.assertIn("Arbiter Academy console requires an interactive terminal.", output.getvalue())
    self.assertIn("F01-fork-clone-doctor", output.getvalue())


def test_below_minimum_size_uses_plain_fallback(self) -> None:
    console = AcademyConsole(self.operations, input=create_pipe_input(), output=DummyOutput())
    with patch.object(console, "terminal_size", return_value=os.terminal_size((71, 19))):
        self.assertEqual(console.run(), 2)
```

- [ ] **Step 2: Write prompt-toolkit interaction RED tests**

Use `prompt_toolkit.input.create_pipe_input()` and `prompt_toolkit.output.DummyOutput()` to prove: arrow/j-k navigation, Tab pane movement, `d` readiness Doctor, `e` record F01 Doctor evidence, `p` prepare, `c` check, `r` reset, `b` return-to-base, `u` update, `o` open lesson, `q` exit, Enter confirmation, Escape cancellation, resize to one pane, and disabled mutation while busy. Assert operation calls and reducer state, not terminal escape bytes. Prove evidence Doctor and Check each call `preflight()` then `execute()` without a dialog, while prepare/reset/return/update require their plan's confirmation when present.

- [ ] **Step 3: Run console tests and prove RED**

Run:

```powershell
python -m unittest tests.test_tui_app -v
```

Expected: missing `AcademyConsole` and view functions.

- [ ] **Step 4: Implement restrained semantic styles and layouts**

Define only these style classes in `style.py`: `header`, `track`, `lab`, `lab.selected`, `lab.prepared`, `status.good`, `status.warn`, `status.bad`, `action`, `action.disabled`, `result`, `dialog`, `footer`, and `focus`. Use the Academy charcoal/ivory/amber palette, preserve terminal defaults where possible, and never rely on color alone: every status includes `READY`, `CAUTION`, `BLOCKED`, or `ACTIVE` text.

At width `>=96`, render labs left and repository/actions/result right. At `72..95`, render one pane selected by `state.pane`. Never truncate the selected lab ID, branch, confirmation, or error; wrap them in scrollable windows.

- [ ] **Step 5: Implement asynchronous operation dispatch**

Use `Application(full_screen=True, mouse_support=False)` and one `ThreadPoolExecutor(max_workers=1, thread_name_prefix="academy-operation")`. Read operations may execute in the worker. Mutations first call `preflight`; confirmation dispatches only the returned immutable plan to `execute`. Completion uses `application.loop.call_soon_threadsafe` to reduce `OperationFinished`, refresh `snapshot()`, invalidate, and restore focus. Executor shutdown waits for the active operation; `q` cannot terminate while `busy`.

- [ ] **Step 6: Implement safe confirmation content**

The dialog displays `plan.confirmation` verbatim, then `Enter: confirm` and `Esc: cancel`. No single-letter key confirms. Cancel calls no operation and writes no progress. The action list displays a disabled reason for dirty state, wrong branch, unavailable lab, active operation, or failed Doctor precondition.

- [ ] **Step 7: Run console and boundary tests**

Run:

```powershell
python -m unittest tests.test_tui_app tests.test_tui_state tests.test_operations tests.test_return_to_base -v
```

Expected: PASS with no real browser launch, Git mutation, or alternate-screen output in unit tests.

- [ ] **Step 8: Commit the full-screen console**

Invoke `$ca-commit` with title:

```text
feat: add Academy operations console
```

### Task 9: Enforce the installer lifecycle boundary

**Files:**
- Create: `install/install.ps1`
- Create: `install/install.ps1.sha256`
- Create: `install/install.sh`
- Create: `install/install.sh.sha256`
- Create: `scripts/build_release_bundle.py`
- Create: `tests/test_installers.py`
- Modify: `tests/test_installation.py`
- Modify: `tests/test_tui_app.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: existing externally installed verifier bootstrap and the new `arbiter-academy console` command.
- Produces: the exact Preview 0.3 public installer/launch interface above, canonical tracked installer checksum files, a deterministic offline release bundle, and proof that uninstall remains outside the running console while lesson setup/teardown remain inside it.

- [ ] **Step 1: Add RED installer contract tests**

In `tests/test_installers.py`, parse both committed scripts without executing them and assert the exact release, asset name, install roots, SHA-256 literal shape, `--no-index`, and absence of package-index URLs. Require `install.ps1.sha256` and `install.sh.sha256` to equal the lowercase digest of the corresponding committed script in canonical `<sha256><two spaces><basename><LF>` form, with no BOM or CR. Build the release archive twice under different temporary directories and assert byte identity. The only accepted archive members are:

```python
EXPECTED_BUNDLE_MEMBERS = (
    "installation-manifest.json",
    "wheels/prompt_toolkit-3.0.53-py3-none-any.whl",
    "wheels/wcwidth-0.8.2-py3-none-any.whl",
    "wheels/workshop_queue-0.1.0-py3-none-any.whl",
)
```

The manifest contains `schema_version: 1`, `release: "preview-0.3"`, each relative member path, byte length, SHA-256, and `ownership: "installer"`; reject unknown keys, duplicate paths, absolute paths, `..`, backslashes, links, and case-fold collisions.

- [ ] **Step 2: Run installer contract tests and prove RED**

Run:

```powershell
python -m unittest tests.test_installers -v
```

Expected: missing installer and bundle-builder failures.

- [ ] **Step 3: Implement deterministic offline bundle construction**

`scripts/build_release_bundle.py` accepts exactly `--academy-wheel PATH --wheelhouse PATH --output PATH`. It verifies the two third-party hashes from Task 6, verifies the Academy wheel filename and metadata version `0.1.0`, writes canonical compact UTF-8 JSON plus newline, sorts archive members lexically, stores every member with ZIP timestamp `1980-01-01T00:00:00`, Unix mode `0o644`, and DEFLATE level `9`, and writes `arbiter-academy-preview-0.3.zip`. A second output line prints `sha256  filename`; no network call occurs.

- [ ] **Step 4: Implement the reviewed installers**

Both scripts use release `preview-0.3`, bundle `arbiter-academy-preview-0.3.zip`, and an exact 64-character lowercase bundle digest copied from a clean deterministic build. PowerShell requires PowerShell 7 and Python 3.11/3.12, installs at `$env:LOCALAPPDATA\ArbiterAcademy\preview-0.3`, and invokes the created venv's `Scripts\python.exe -m pip install --no-index --find-links`, followed by the extracted `workshop_queue-0.1.0-py3-none-any.whl`. POSIX requires `python3` 3.11/3.12, installs at `${XDG_DATA_HOME:-$HOME/.local/share}/arbiter-academy/preview-0.3`, and invokes the created venv's `bin/python -m pip install` with the same offline flags and wheel.

After installer bytes are final, write and commit `install/install.ps1.sha256` and `install/install.sh.sha256` in the canonical form asserted in Step 1. Any later installer edit MUST update its tracked checksum in the same commit; a mismatch blocks the component review.

Each script creates the versioned root with an ownership sentinel before any download, refuses a pre-existing root, downloads to a child temporary directory, checks the bundle digest before extraction, validates the manifest and ZIP member set with the selected Python interpreter, creates the venv, installs, checks `prompt_toolkit.__version__ == "3.0.53"` and `wcwidth.__version__ == "0.8.2"`, then removes the downloaded bundle. On failure it removes only the root whose sentinel matches the current invocation nonce. It never edits PATH, a shell profile, the learner checkout, or another Academy version.

- [ ] **Step 5: Execute the documented fast and verify-first paths in isolated tests**

Serve release assets from a loopback HTTP fixture and execute a temporary copy of each installer whose single fixed GitHub release-origin literal is replaced with that fixture origin; assert the committed installer itself contains no alternate-origin hook. Run PowerShell on Windows and `sh` on POSIX. Assert clean install, exact console executable, Doctor invocation, pre-existing-root refusal, wrong bundle hash, wrong installer checksum, interrupted download, unexpected ZIP member, path escape, partial pip failure, nonce mismatch, and rollback scope. Network denial during pip installation MUST still pass.

- [ ] **Step 6: Add RED command-surface tests**

```python
def test_console_exposes_lesson_lifecycle_but_not_tool_lifecycle(self) -> None:
    labels = tuple(ACTION_LABELS[action] for action in available_actions(self.console.state))
    self.assertEqual(
        labels,
        (
            "Readiness Doctor",
            "Record F01 Doctor evidence",
            "Prepare",
            "Check",
            "Reset / retry",
            "Return to main",
            "Update checkout",
            "Open lesson",
        ),
    )
    for forbidden in ("Install", "Uninstall", "Delete tools", "Shell", "Command prompt"):
        self.assertNotIn(forbidden, labels)
```

Add an installation test that creates `learner = fixture_root / "learner"`, builds a fresh external venv from the reviewed wheelhouse, and invokes `subprocess.run([academy_executable, "--repository", str(learner.resolve()), "console"], stdin=DEVNULL, capture_output=True)`. Assert exit `2`, the readable fallback, and no writes outside the venv manifest-owned paths and learner `.academy` progress namespace.

- [ ] **Step 7: Run lifecycle tests and prove RED**

Run:

```powershell
python -m unittest tests.test_installation tests.test_tui_app -v
```

Expected: README/label or console-installation contract failures until documented and wired.

- [ ] **Step 8: Replace README bootstrap usage with the public interface**

Document the exact fast, verify-first, and console-launch commands from **Public installer and console interface**. Retain these exact post-install transition commands:

```powershell
& $academy --repository (Get-Location).Path console
& $academy --repository (Get-Location).Path return-to-base F01-fork-clone-doctor
```

```sh
"$academy" --repository "$PWD" console
"$academy" --repository "$PWD" return-to-base F01-fork-clone-doctor
```

State explicitly: the external installer owns installation and eventual whole-tool removal; the console owns only Doctor, lesson prepare/check/reset, preserving attempts, return-to-base, checkout update, progress, and opening the public lesson. The running console never removes its executable or environment.

- [ ] **Step 9: Run lifecycle and README contract tests**

Run:

```powershell
python -m unittest tests.test_installers tests.test_installation tests.test_tui_app tests.test_preview_site -v
```

Expected: PASS.

- [ ] **Step 10: Commit the installer and lifecycle boundary**

Invoke `$ca-commit` with title:

```text
docs: define Academy console lifecycle boundary
```

### Task 10: Add adversarial and platform verification

**Files:**
- Modify: `.github/workflows/academy-verify.yml`
- Modify: `scripts/run_test_shards.py`
- Modify: `tests/test_operations.py`
- Modify: `tests/test_tui_app.py`
- Modify: `tests/test_runtime_wheelhouse.py`

**Interfaces:**
- Consumes: complete operations/console/runtime feature.
- Produces: exact-head Windows/Ubuntu Python 3.11/3.12 evidence and adversarial authority coverage.

- [ ] **Step 1: Add adversarial RED tests**

Add cases that prove:

```python
ADVERSARIAL_CASES = (
    "learner publication manifest adds an unpublished lab",
    "learner catalog changes a title or lesson path",
    "lesson URL contains encoded slash, backslash, query, fragment, or foreign origin",
    "repository path traverses a symlink or Windows junction after preflight",
    "HEAD, branch, status, remote config, main ref, attempt ref, resulting ref, archive ref, or upstream target changes after preflight",
    "two UI actions race the same mutation lock",
    "worker raises OSError or GitCommandError while the alternate screen is active",
    "terminal shrinks below 72x20 during an operation",
    "stdin or stdout is redirected",
    "browser opener returns false or raises",
)
```

Each test snapshots refs, HEAD, status, and external files before the operation and asserts no unauthorized difference after rejection.

- [ ] **Step 2: Run adversarial tests and prove RED where coverage is missing**

Run:

```powershell
python -m unittest tests.test_operations tests.test_return_to_base tests.test_tui_app tests.test_runtime_wheelhouse -v
```

Expected: at least the newly introduced adversarial cases fail before the corresponding guards are complete.

- [ ] **Step 3: Close each failing boundary minimally**

Keep URL validation in `preview.py`, filesystem/ref revalidation in `operations.py` and `return_to_base.py`, and UI cleanup in `tui/app.py`. On every exception, convert to a path-free `OperationResult.failure`; call `Application.exit` only after restoring terminal state. Do not catch `BaseException`.

- [ ] **Step 4: Expand hosted verification without multiplying long curriculum shards**

Keep the existing exhaustive Ubuntu shard matrix unchanged. Add one focused `console-platform` job:

```yaml
console-platform:
  runs-on: ${{ matrix.os }}
  timeout-minutes: 20
  strategy:
    fail-fast: false
    matrix:
      os: [ubuntu-latest, windows-latest]
      python-version: ["3.11", "3.12"]
  steps:
    - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
      with:
        ref: ${{ github.event.pull_request.head.sha || github.sha }}
        persist-credentials: false
    - uses: actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97 # v7.0.0
      with:
        python-version: ${{ matrix.python-version }}
    - run: python -m pip install --no-index --find-links .github/wheelhouse .
    - run: python -m unittest tests.test_runtime_wheelhouse tests.test_operations tests.test_return_to_base tests.test_tui_state tests.test_tui_app -v
```

Do not edit the Pages workflow in this component branch. The sibling guided-F01 release plan Task 8 adds the exact offline install command and release-asset gate on the combined integration head, after this component has merged into that head.

- [ ] **Step 5: Run the complete local gate**

Run:

```powershell
python -m tabnanny academy_engine scripts tests workshop_queue
python -m compileall -q academy_engine scripts tests workshop_queue
python -m unittest tests.test_runtime_wheelhouse tests.test_operations tests.test_return_to_base tests.test_tui_state tests.test_tui_app tests.test_academy_cli tests.test_installation tests.test_project_state -v
python scripts/run_test_shards.py --list
python scripts/scan_secrets.py --staged
git diff --check
```

Expected: every command exits `0`; scanner reports zero findings; diff check prints nothing.

- [ ] **Step 6: Perform manual terminal acceptance on both layout widths**

Run from an externally installed verifier:

```powershell
arbiter-academy --repository . console
```

Verify keyboard-only navigation at 120x35 and 80x24, resize during Doctor, cancel reset, confirm return-to-base on a disposable clean attempt, failure text wrapping, visible focus, and terminal restoration after `q` and Ctrl+C. Record the exact package version, OS, Python version, terminal, repository HEAD, and screenshots in the PR evidence.

- [ ] **Step 7: Request independent review**

Invoke `$ca-review` against the exact current diff. Treat any BLOCK finding about installed authority, dirty-work preservation, stale preflight, ref preservation, non-TTY behavior, dependency provenance, or platform coverage as release-blocking.

- [ ] **Step 8: Commit the verification slice**

Invoke `$ca-commit` with title:

```text
test: verify Academy console across platforms
```

- [ ] **Step 9: Hand the reviewed component head to Preview 0.3 integration**

Record the exact commit, tree, wheel hashes, local focused counts, and independent review verdict, then integrate this head into `codex/academy-preview-0.3` with the guided-site head. Do not merge this component to `main` or advertise the installer URLs before the combined Preview 0.3 PR has exact-head hosted evidence. The combined PR description includes this scope statement:

```text
The website remains the course. This console handles repository operations only. It does not publish or rewrite any lesson, add whole-tool teardown, execute arbitrary commands, or promote P06/P07.
```

## Self-review record

- Spec coverage: shared operations, CLI parity, return-to-base, state reducer, full-screen UI, safe confirmation, operation lock, non-TTY fallback, dependency/ADR gates, pinned offline wheels, installer lifecycle boundary, adversarial authority, and Windows/Ubuntu Python 3.11/3.12 all map to explicit tasks.
- Placeholder scan: no deferred implementation markers or undefined task references remain.
- Type consistency: `OperationKind`, `OperationResult`, `RefExpectation`, `MutationPlan`, `AcademySnapshot`, `ConsoleState`, `AcademyOperations.preflight()`, and `AcademyOperations.execute()` retain one spelling and signature throughout.
- Scope control: lesson schema, site rendering, Home/Recovery/F01 prose, copy controls, media, and public promotion belong to the separate guided-course/site plan and are intentionally absent here.
