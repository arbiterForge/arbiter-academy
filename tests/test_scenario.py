from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from academy_engine import command as command_module
from academy_engine import scenario as scenario_module
from academy_engine.catalog import CatalogError
from academy_engine.attribution import AttributionError
from academy_engine.command import GitCommandError, run_git as bounded_run_git
from academy_engine.exercise_state import ExerciseStateError
from academy_engine.scenario import PreparedLab, PreparationError, prepare_lab, reset_lab
from academy_engine.external_state import ExternalStateStore
from academy_engine.progress import inspect_progress
from tests._temporary import RetryingTemporaryDirectory
from tests.test_p06_context_recovery import (
    P06_CLI_OBJECT,
    P06_CONTEXT_BYTES,
    P06_CONTEXT_SHA256,
    P06_NOTE_BYTES,
    P06_PRIOR_CLI_OBJECT,
    P06_PROVENANCE_BYTES,
    P06_SCENARIO_BYTES,
    assert_p06_report_source_contract,
)


def git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=root, text=True, encoding="utf-8", capture_output=True, check=True)
    return result.stdout.strip()


def academy_git_fixture() -> tuple[RetryingTemporaryDirectory, Path]:
    temporary = RetryingTemporaryDirectory()
    root = Path(temporary.name) / "repository"
    root.mkdir()
    git(root, "init", "-b", "main")
    git(root, "config", "user.name", "Academy Learner")
    git(root, "config", "user.email", "learner@example.test")
    (root / "README.md").write_text("base\n", encoding="utf-8")
    manifest = root / "academy" / "scenarios" / "F01-fork-clone-doctor"
    (manifest / "files").mkdir(parents=True)
    (manifest / "files" / "seed.txt").write_text("starting state\n", encoding="utf-8")
    shutil.copyfile(Path(__file__).parents[1] / "academy" / "catalog.json", root / "academy" / "catalog.json")
    (manifest / "manifest.json").write_text(json.dumps({"schema_version": 1, "id": "F01-fork-clone-doctor",
        "files": [{"source": "seed.txt", "destination": "exercise/seed.txt"}], "removals": [],
        "starting_task": "F01", "checkpoint": "academy/checkpoints/F01-fork-clone-doctor.json",
        "requires_push_safe_setup": True}), encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-m", "base")
    git(root, "remote", "add", "origin", "https://github.com/learner/arbiter-academy.git")
    git(root, "remote", "add", "upstream", "https://github.com/arbiterForge/arbiter-academy.git")
    git(root, "remote", "set-url", "--push", "upstream", "DISABLED")
    return temporary, root


def add_scenario(root: Path, lab_id: str) -> None:
    scenario = root / "academy" / "scenarios" / lab_id
    (scenario / "files").mkdir(parents=True)
    (scenario / "files" / "seed.txt").write_text("starting state\n", encoding="utf-8")
    (scenario / "manifest.json").write_text(json.dumps({
        "schema_version": 1, "id": lab_id, "files": [{"source": "seed.txt", "destination": "exercise/seed.txt"}],
        "removals": [], "starting_task": lab_id[:3], "checkpoint": f"academy/checkpoints/{lab_id}.json",
        "requires_push_safe_setup": False,
    }), encoding="utf-8")


def p01_academy_git_fixture() -> tuple[RetryingTemporaryDirectory, Path]:
    """Create the smallest real repository that can prepare the P01 control-state seed."""
    temporary = RetryingTemporaryDirectory()
    root = Path(temporary.name) / "repository"
    root.mkdir()
    source = Path(__file__).parents[1]
    shutil.copytree(source / "academy", root / "academy")
    shutil.copytree(source / ".codearbiter", root / ".codearbiter")
    git(root, "init", "-b", "main")
    git(root, "config", "user.name", "Academy Learner")
    git(root, "config", "user.email", "learner@example.test")
    git(root, "add", ".")
    git(root, "commit", "-m", "base")
    git(root, "remote", "add", "origin", "https://github.com/learner/arbiter-academy.git")
    git(root, "remote", "add", "upstream", "https://github.com/arbiterForge/arbiter-academy.git")
    git(root, "remote", "set-url", "--push", "upstream", "DISABLED")
    return temporary, root

def p05_academy_git_fixture() -> tuple[RetryingTemporaryDirectory, Path]:
    """Create a P04-shaped learner repository for the real P05 preparation path."""
    temporary = RetryingTemporaryDirectory()
    root = Path(temporary.name) / "repository"
    root.mkdir()
    (root / "data").mkdir()
    source = Path(__file__).parents[1]
    for relative in ("academy", ".codearbiter", "workshop_queue", "tests"):
        shutil.copytree(source / relative, root / relative, ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copyfile(source / ".gitignore", root / ".gitignore")
    shutil.copyfile(source / "pyproject.toml", root / "pyproject.toml")
    for relative in (
        "workshop_queue/model.py",
        "workshop_queue/service.py",
        "workshop_queue/cli.py",
        "tests/test_cli.py",
    ):
        (root / relative).write_bytes(
            subprocess.run(
                ["git", "show", f"b0dc9e5:{relative}"],
                cwd=source,
                check=True,
                capture_output=True,
            ).stdout
        )
    p03_adr = root / ".codearbiter/decisions/0004-academy-lab.md"
    p03_adr.write_text(
        "---\nstatus: accepted\ndate: 2026-08-01\n"
        "title: Choose the Workshop Queue summary-format boundary\n"
        "decided-by: Academy Learner\nsupersedes: none\n---\n\n"
        "# ADR-0004 — Choose the Workshop Queue summary-format boundary\n",
        encoding="utf-8",
        newline="\n",
    )
    p03_log = root / ".codearbiter/decisions/decision-log.md"
    p03_log.write_text(
        p03_log.read_text(encoding="utf-8")
        + "\n## DECISION-0004 — ADR-0004 — Choose the Workshop Queue summary-format boundary\n\n"
        "**Date:** 2026-08-01\n**Status:** accepted\n**Supersedes:** none\n"
        "**Decided by:** Academy Learner\n**Decision category:** architecture\n"
        "**Artifact-section-hash:** n/a\n\n---\n",
        encoding="utf-8",
        newline="\n",
    )
    git(root, "init", "-b", "main")
    git(root, "config", "user.name", "Academy Learner")
    git(root, "config", "user.email", "learner@example.test")
    git(root, "add", ".")
    git(root, "commit", "-m", "base")
    git(root, "remote", "add", "origin", "https://github.com/learner/arbiter-academy.git")
    git(root, "remote", "add", "upstream", "https://github.com/arbiterForge/arbiter-academy.git")
    git(root, "remote", "set-url", "--push", "upstream", "DISABLED")
    return temporary, root


def p07_academy_git_fixture() -> tuple[tempfile.TemporaryDirectory[str], Path]:
    """Create a real later-lab repository with the frozen P07 target committed."""
    temporary, root = p01_academy_git_fixture()
    source = Path(__file__).parents[1]
    target = root / "academy_engine" / "paths.py"
    target.parent.mkdir(parents=True)
    shutil.copyfile(source / "academy_engine" / "paths.py", target)
    git(root, "add", "academy_engine/paths.py")
    git(root, "commit", "-m", "add frozen P07 target")
    return temporary, root

def p06_academy_git_fixture() -> tuple[RetryingTemporaryDirectory, Path]:
    """Create the real shared-source base used by generic P06 preparation."""
    temporary = RetryingTemporaryDirectory()
    root = Path(temporary.name) / "repository"
    root.mkdir()
    source = Path(__file__).parents[1]
    for relative in ("academy", ".codearbiter", "workshop_queue"):
        shutil.copytree(source / relative, root / relative, ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copyfile(source / ".gitignore", root / ".gitignore")
    shutil.copyfile(source / "pyproject.toml", root / "pyproject.toml")
    git(root, "init", "-b", "main")
    git(root, "config", "user.name", "Academy Learner")
    git(root, "config", "user.email", "learner@example.test")
    git(root, "add", ".")
    git(root, "commit", "-m", "base")
    git(root, "remote", "add", "origin", "https://github.com/learner/arbiter-academy.git")
    git(root, "remote", "add", "upstream", "https://github.com/arbiterForge/arbiter-academy.git")
    git(root, "remote", "set-url", "--push", "upstream", "DISABLED")
    return temporary, root


def git_bytes(root: Path, *args: str) -> bytes:
    return subprocess.run(
        ["git", *args], cwd=root, capture_output=True, check=True
    ).stdout


class ScenarioTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary, self.root = academy_git_fixture()
        self.addCleanup(self.temporary.cleanup)

    def test_prepare_creates_numbered_branch_overlay_and_exact_commit(self) -> None:
        base = git(self.root, "rev-parse", "HEAD")
        prepared = prepare_lab(self.root, "F01-fork-clone-doctor")
        self.assertEqual(prepared.branch, "academy/F01-fork-clone-doctor/1")
        self.assertEqual(prepared.base_sha, base)
        self.assertEqual((self.root / "exercise" / "seed.txt").read_text(encoding="utf-8"), "starting state\n")
        self.assertEqual(git(self.root, "log", "-1", "--format=%s"), "academy: prepare F01-fork-clone-doctor attempt 1")

    def test_p05_prepare_and_reset_stage_the_real_blocked_summary_defect(self) -> None:
        temporary, root = p05_academy_git_fixture()
        self.addCleanup(temporary.cleanup)

        prepared = prepare_lab(root, "P05-checkpoint-remediation")
        paths = tuple(
            git(root, "diff-tree", "--no-commit-id", "--name-only", "-r", prepared.commit_sha).splitlines()
        )
        self.assertEqual(
            paths,
            (
                ".codearbiter/decisions/0005-terminal-blocked-ticket-lifecycle.md",
                ".codearbiter/decisions/decision-log.md",
                "tests/test_cli.py",
                "training_scenarios/P05-checkpoint-remediation.json",
                "workshop_queue/cli.py",
                "workshop_queue/model.py",
                "workshop_queue/service.py",
            ),
        )
        observed = subprocess.run(
            [
                sys.executable,
                "-m",
                "unittest",
                "tests.test_cli.WorkshopQueueCliTests.test_p05_prepared_blocked_ticket_persists_before_summary_defect",
                "-v",
            ],
            cwd=root,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )
        self.assertEqual(observed.returncode, 0, observed.stderr)
        shutil.rmtree(root / "data")
        self.assertEqual(git(root, "status", "--porcelain", "--untracked-files=all"), "")

        retry = reset_lab(
            root,
            "P05-checkpoint-remediation",
            now=lambda: datetime(2026, 8, 7, tzinfo=timezone.utc),
        )
        archive = "academy/archive/P05-checkpoint-remediation/20260807T000000Z"
        self.assertEqual(retry.attempt, 2)
        self.assertEqual(
            git(root, "show", f"{archive}:workshop_queue/cli.py"),
            git(root, "show", f"{prepared.commit_sha}:workshop_queue/cli.py"),
        )
        self.assertEqual(
            git(root, "show", f"{archive}:.codearbiter/decisions/0005-terminal-blocked-ticket-lifecycle.md"),
            git(root, "show", f"{prepared.commit_sha}:.codearbiter/decisions/0005-terminal-blocked-ticket-lifecycle.md"),
        )

    def test_prepare_p07_preserves_the_frozen_target_blob_before_learner_work(self) -> None:
        """Catches preparation that rebinds or mutates the frozen containment target."""
        temporary, root = p07_academy_git_fixture()
        self.addCleanup(temporary.cleanup)
        expected_descriptor = (
            b'{"lab_id":"P07-threat-model","operation":"stride_model",'
            b'"request":"academy_engine/paths.py archive-import containment boundary",'
            b'"schema_version":1,"starting_condition":"model-absent",'
            b'"target":"academy_engine/paths.py",'
            b'"target_blob":"b36801add4eb375f796d1107ee63dd604d08a034",'
            b'"target_sha256":"e40a7655ce6ba6cde58a91ae10a714f10046c055ac90dcbc58f0696c39133a5d"}\n'
        )

        prepared = prepare_lab(root, "P07-threat-model", installed_authority=True)

        self.assertEqual(
            git(root, "rev-parse", f"{prepared.base_sha}:academy_engine/paths.py"),
            "b36801add4eb375f796d1107ee63dd604d08a034",
        )
        self.assertEqual(
            git(root, "rev-parse", f"{prepared.commit_sha}:academy_engine/paths.py"),
            "b36801add4eb375f796d1107ee63dd604d08a034",
        )
        self.assertEqual(
            subprocess.run(
                ["git", "show", f"{prepared.commit_sha}:training_scenarios/P07-threat-model.json"],
                cwd=root,
                capture_output=True,
                check=True,
            ).stdout,
            expected_descriptor,
        )
        self.assertEqual(git(root, "status", "--porcelain", "--untracked-files=all"), "")

    def test_reset_p07_archives_a_failed_attempt_without_mutating_the_target(self) -> None:
        """Catches reset discarding the failed branch or rebinding the target on retry."""
        temporary, root = p07_academy_git_fixture()
        self.addCleanup(temporary.cleanup)
        prepared = prepare_lab(root, "P07-threat-model", installed_authority=True)
        report = root / ".codearbiter" / "reports" / "academy" / "P07-threat-model.md"
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text("failed learner attempt\n", encoding="utf-8", newline="\n")
        git(root, "add", ".codearbiter/reports/academy/P07-threat-model.md")
        git(root, "commit", "-m", "learner: incomplete P07 report")
        failed_head = git(root, "rev-parse", "HEAD")

        retry = reset_lab(
            root,
            "P07-threat-model",
            now=lambda: datetime(2026, 8, 8, 12, 34, 56, tzinfo=timezone.utc),
            installed_authority=True,
        )

        archive = "academy/archive/P07-threat-model/20260808T123456Z"
        self.assertEqual(git(root, "rev-parse", archive), failed_head)
        self.assertEqual(retry.attempt, 2)
        for revision in (archive, retry.base_sha, retry.commit_sha):
            with self.subTest(revision=revision):
                self.assertEqual(
                    git(root, "rev-parse", f"{revision}:academy_engine/paths.py"),
                    "b36801add4eb375f796d1107ee63dd604d08a034",
                )
        self.assertEqual(
            subprocess.run(
                ["git", "show", f"{archive}:.codearbiter/reports/academy/P07-threat-model.md"],
                cwd=root,
                capture_output=True,
                check=True,
            ).stdout,
            b"failed learner attempt\n",
        )
        self.assertEqual(
            git(root, "status", "--porcelain", "--untracked-files=all"),
            "",
        )

    def test_prepare_p06_commits_frozen_stale_context_provenance_and_preserved_note_before_learner_work(self) -> None:
        """Catches P06 omitting safe provenance/note fixtures or reading a substituted CLI source."""
        temporary, root = p06_academy_git_fixture()
        self.addCleanup(temporary.cleanup)

        prepared = prepare_lab(
            root,
            "P06-context-drift-recovery",
            installed_authority=True,
        )
        paths = tuple(
            git(root, "diff-tree", "--no-commit-id", "--name-only", "-r", prepared.commit_sha).splitlines()
        )
        self.assertEqual(
            paths,
            (
                ".codearbiter/.provenance/CONTEXT.json",
                ".codearbiter/CONTEXT.md",
                "docs/preserved-note.md",
                "training_scenarios/P06-context-drift-recovery.json",
            ),
        )
        self.assertEqual(
            git_bytes(root, "show", f"{prepared.commit_sha}:.codearbiter/.provenance/CONTEXT.json"),
            P06_PROVENANCE_BYTES,
        )
        self.assertEqual(
            git_bytes(root, "show", f"{prepared.commit_sha}:docs/preserved-note.md"),
            P06_NOTE_BYTES,
        )
        self.assertEqual(
            git_bytes(root, "show", f"{prepared.commit_sha}:training_scenarios/P06-context-drift-recovery.json"),
            P06_SCENARIO_BYTES,
        )
        git(root, "cat-file", "-e", f"{prepared.commit_sha}:.codearbiter/CONTEXT.md")
        context = git_bytes(root, "show", f"{prepared.commit_sha}:.codearbiter/CONTEXT.md")
        self.assertEqual(context, P06_CONTEXT_BYTES)
        self.assertEqual(hashlib.sha256(context).hexdigest(), P06_CONTEXT_SHA256)
        cli_object = git(root, "rev-parse", f"{prepared.commit_sha}:workshop_queue/cli.py")
        self.assertEqual(cli_object, P06_CLI_OBJECT)
        self.assertNotEqual(cli_object, P06_PRIOR_CLI_OBJECT)
        assert_p06_report_source_contract(
            self,
            git_bytes(root, "show", f"{prepared.commit_sha}:workshop_queue/cli.py"),
        )
        provenance = json.loads(P06_PROVENANCE_BYTES)
        self.assertEqual(provenance["entries"][0]["hash"], P06_PRIOR_CLI_OBJECT)
        self.assertEqual(git(root, "status", "--porcelain", "--untracked-files=all"), "")

    def test_prepare_p06_rejects_altered_protected_overlay_bytes_before_branch_creation(self) -> None:
        """Catches a learner checkout replacing trusted P06 control-state fixture content."""
        temporary, root = p06_academy_git_fixture()
        self.addCleanup(temporary.cleanup)
        context_path = root / ".codearbiter/CONTEXT.md"
        context_before = context_path.read_bytes()
        source = root / "academy/scenarios/P06-context-drift-recovery/files/CONTEXT.md"
        source.write_bytes(source.read_bytes() + b"\nattacker-controlled context\n")
        git(root, "add", source.relative_to(root).as_posix())
        git(root, "commit", "-m", "replace P06 protected overlay")
        before = git(root, "rev-parse", "HEAD")

        with self.assertRaisesRegex(PreparationError, "trusted protected overlay"):
            prepare_lab(
                root,
                "P06-context-drift-recovery",
                installed_authority=True,
            )

        self.assertEqual(git(root, "rev-parse", "HEAD"), before)
        self.assertFalse(git(root, "branch", "--list", "academy/P06-context-drift-recovery/1"))
        self.assertEqual(context_path.read_bytes(), context_before)

    def test_prepare_p06_rejects_protected_source_swap_after_validation(self) -> None:
        """Catches a hash-to-use race replacing trusted P06 bytes after preflight."""
        temporary, root = p06_academy_git_fixture()
        self.addCleanup(temporary.cleanup)
        source = root / "academy/scenarios/P06-context-drift-recovery/files/CONTEXT.md"
        destination = root / ".codearbiter/CONTEXT.md"
        destination_before = destination.read_bytes()
        attacker_bytes = b"attacker-controlled context\n"
        original_head = git(root, "rev-parse", "HEAD")
        real_run_git = scenario_module.run_git
        swapped = False

        def swap_after_branch(repository: Path, args, *, check: bool = True):
            nonlocal swapped
            result = real_run_git(repository, args, check=check)
            if tuple(args[:2]) == ("switch", "-c") and not swapped:
                source.write_bytes(attacker_bytes)
                swapped = True
            return result

        with patch.object(scenario_module, "run_git", side_effect=swap_after_branch):
            with self.assertRaisesRegex(PreparationError, "changed after validation"):
                prepare_lab(
                    root,
                    "P06-context-drift-recovery",
                    installed_authority=True,
                )

        self.assertTrue(swapped)
        self.assertEqual(git(root, "branch", "--show-current"), "main")
        self.assertEqual(git(root, "rev-parse", "HEAD"), original_head)
        self.assertFalse(git(root, "branch", "--list", "academy/P06-context-drift-recovery/1"))
        self.assertEqual(destination.read_bytes(), destination_before)
        self.assertEqual(source.read_bytes(), attacker_bytes)

    def test_reset_p06_archives_failed_attempt_and_preserves_its_head(self) -> None:
        """Catches reset deleting learner history or escaping the bounded Git-only command route."""
        temporary, root = p06_academy_git_fixture()
        self.addCleanup(temporary.cleanup)
        prepared = prepare_lab(
            root,
            "P06-context-drift-recovery",
            installed_authority=True,
        )
        failed = root / "failed-attempt.txt"
        failed.write_text("retain this failed P06 attempt\n", encoding="utf-8")
        git(root, "add", "failed-attempt.txt")
        git(root, "commit", "-m", "learner: incomplete P06 recovery")
        old_head = git(root, "rev-parse", "HEAD")
        old_branch = prepared.branch
        calls: list[tuple[str, ...]] = []
        launches: list[tuple[str, ...]] = []
        real_popen = subprocess.Popen

        def observed_popen(*args, **kwargs):
            invocation = tuple(args[0])
            self.assertTrue(invocation)
            self.assertIs(kwargs.get("shell"), False)
            git_invocation = invocation
            if Path(invocation[0]).resolve() == Path(sys.executable).resolve():
                self.assertGreaterEqual(len(invocation), 4)
                self.assertEqual(invocation[1], "-c")
                git_invocation = invocation[3:]
            self.assertEqual(git_invocation[0], "git")
            self.assertFalse(
                any(
                    argument in {"clone", "fetch", "pull", "push", "ls-remote", "submodule"}
                    for argument in git_invocation
                ),
                git_invocation,
            )
            for argument in git_invocation[1:]:
                path_text = argument
                for prefix in ("--git-dir=", "--work-tree="):
                    if path_text.startswith(prefix):
                        path_text = path_text.removeprefix(prefix)
                candidate = Path(path_text)
                if candidate.is_absolute():
                    try:
                        candidate.resolve().relative_to(root.resolve())
                    except ValueError:
                        self.fail(f"Git argument escaped the P06 repository: {argument}")
            launches.append(git_invocation)
            return real_popen(*args, **kwargs)

        def guarded_git(
            actual_root: Path,
            args,
            *,
            check: bool = True,
            trust_local_config: bool = False,
            **kwargs,
        ):
            self.assertNotIsInstance(args, str)
            vector = tuple(args)
            self.assertTrue(vector)
            self.assertNotIn(vector[0], {"cmd", "powershell", "pwsh", "python", "curl", "wget"})
            self.assertNotIn(vector[0], {"clone", "fetch", "pull", "push", "ls-remote", "submodule"})
            for argument in vector:
                self.assertFalse(Path(argument).is_absolute(), vector)
                self.assertNotIn("://", argument)
            calls.append(vector)
            return bounded_run_git(
                actual_root,
                vector,
                check=check,
                trust_local_config=trust_local_config,
                **kwargs,
            )

        with patch("academy_engine.scenario._run_git", side_effect=guarded_git), patch.object(
            command_module.subprocess,
            "Popen",
            side_effect=observed_popen,
        ):
            retry = reset_lab(
                root,
                "P06-context-drift-recovery",
                now=lambda: datetime(2026, 8, 8, 12, 34, 56, tzinfo=timezone.utc),
                installed_authority=True,
            )

        archive = "academy/archive/P06-context-drift-recovery/20260808T123456Z"
        self.assertTrue(calls)
        self.assertTrue(launches)
        self.assertEqual(retry.attempt, 2)
        self.assertEqual(retry.branch, "academy/P06-context-drift-recovery/2")
        self.assertEqual(git(root, "branch", "--show-current"), retry.branch)
        self.assertEqual(git(root, "rev-parse", old_branch), old_head)
        self.assertEqual(git(root, "rev-parse", archive), old_head)
        self.assertEqual(git(root, "show", f"{old_branch}:failed-attempt.txt"), "retain this failed P06 attempt")
        self.assertFalse(any(vector[:2] == ("reset", "--hard") for vector in calls))
        self.assertFalse(any(vector and vector[0] == "rebase" for vector in calls))
        self.assertFalse(any(vector[:2] == ("commit", "--amend") for vector in calls))
        self.assertFalse(any(vector[:2] == ("update-ref", "-d") for vector in calls))

    def test_p02_patch_remains_applicable_before_p05_stages_its_fixture(self) -> None:
        """P05 may generate blocked behavior, but must not alter the shared P02 source."""
        temporary, root = p05_academy_git_fixture()
        self.addCleanup(temporary.cleanup)
        source = Path(__file__).parents[1]
        for relative in (
            "workshop_queue/model.py",
            "workshop_queue/service.py",
            "workshop_queue/cli.py",
            "tests/test_cli.py",
            "tests/test_model.py",
            "tests/test_service.py",
        ):
            (root / relative).write_bytes((source / relative).read_bytes())
        git(root, "add", "workshop_queue", "tests")
        if git(root, "status", "--porcelain"):
            git(root, "commit", "-m", "shared source under test")

        patch = root / "academy/scenarios/P02-commit-review-pr/files/P02-worktree.patch"
        checked = subprocess.run(
            ["git", "apply", "--check", "--", str(patch)],
            cwd=root,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )
        self.assertEqual(checked.returncode, 0, checked.stderr)
        applied = subprocess.run(
            ["git", "apply", "--", str(patch)],
            cwd=root,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )
        self.assertEqual(applied.returncode, 0, applied.stderr)
        self.assertNotEqual(git(root, "status", "--porcelain"), "")
        git(root, "add", ".codearbiter/tech-stack.md", "workshop_queue/cli.py", "tests/test_cli.py")
        git(root, "commit", "-m", "learner: add unresolved report coverage")
        self.assertEqual(git(root, "log", "-1", "--format=%s"), "learner: add unresolved report coverage")

        prepared = prepare_lab(root, "P05-checkpoint-remediation")
        observed = subprocess.run(
            [
                sys.executable,
                "-m",
                "unittest",
                "tests.test_cli.WorkshopQueueCliTests.test_p05_prepared_blocked_ticket_persists_before_summary_defect",
                "-v",
            ],
            cwd=root,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )
        self.assertEqual(prepared.lab_id, "P05-checkpoint-remediation")
        self.assertEqual(observed.returncode, 0, observed.stderr)

    def test_p05_prepare_commit_failure_restores_all_seven_fixture_targets(self) -> None:
        temporary, root = p05_academy_git_fixture()
        self.addCleanup(temporary.cleanup)
        original = {
            path: (root / path).read_bytes()
            for path in (
                "tests/test_cli.py",
                "workshop_queue/cli.py",
                "workshop_queue/model.py",
                "workshop_queue/service.py",
                ".codearbiter/decisions/decision-log.md",
            )
        }
        overlay = root / "training_scenarios/P05-checkpoint-remediation.json"
        adr = root / ".codearbiter/decisions/0005-terminal-blocked-ticket-lifecycle.md"
        self.assertFalse(overlay.exists())
        self.assertFalse(adr.exists())
        hooks = Path(temporary.name) / "hooks"
        hooks.mkdir()
        hook = hooks / "pre-commit"
        hook.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
        hook.chmod(0o755)
        git(root, "config", "core.hooksPath", str(hooks))

        with self.assertRaises(PreparationError):
            prepare_lab(root, "P05-checkpoint-remediation")

        self.assertEqual(git(root, "branch", "--show-current"), "main")
        self.assertFalse(git(root, "branch", "--list", "academy/P05-checkpoint-remediation/1"))
        self.assertFalse(overlay.exists())
        self.assertFalse(adr.exists())
        for path, contents in original.items():
            self.assertEqual((root / path).read_bytes(), contents)


    def test_p01_control_state_seed_survives_prepare_and_reset_archive(self) -> None:
        """Catches a seed omitted from the generic prepare/reset snapshot boundary."""
        temporary, root = p01_academy_git_fixture()
        self.addCleanup(temporary.cleanup)
        before = (root / ".codearbiter/open-tasks.md").read_bytes()
        prepared = prepare_lab(root, "P01-feature-through-plan")
        seeded = (root / ".codearbiter/open-tasks.md").read_bytes()
        self.assertNotEqual(seeded, before)
        self.assertIn(b"academy.feature.0002", seeded)

        retry = reset_lab(
            root,
            "P01-feature-through-plan",
            now=lambda: datetime(2026, 8, 4, tzinfo=timezone.utc),
        )
        archive = "academy/archive/P01-feature-through-plan/20260804T000000Z"
        self.assertEqual(retry.attempt, prepared.attempt + 1)
        self.assertEqual(
            git(root, "show", f"{archive}:.codearbiter/open-tasks.md").encode(),
            seeded.rstrip(b"\n"),
        )
        self.assertEqual((root / ".codearbiter/open-tasks.md").read_bytes(), seeded)

    def test_p01_seed_symlink_is_rejected_before_branch_creation(self) -> None:
        """Catches a control-state seed that traverses a symlink/reparse point."""
        temporary, root = p01_academy_git_fixture()
        self.addCleanup(temporary.cleanup)
        source = root / "academy/scenarios/P01-feature-through-plan/files/open-tasks.md"
        outside = root / "outside-seed.md"
        outside.write_bytes(source.read_bytes())
        source.unlink()
        try:
            os.symlink(outside, source)
        except OSError as error:
            self.skipTest(f"symlink/reparse creation unavailable: {error}")
        git(root, "add", "-A")
        git(root, "commit", "-m", "unsafe P01 seed")
        before = git(root, "rev-parse", "HEAD")
        with self.assertRaisesRegex(PreparationError, "symlink or reparse"):
            prepare_lab(root, "P01-feature-through-plan")
        self.assertEqual(git(root, "rev-parse", "HEAD"), before)
        self.assertFalse(git(root, "branch", "--list", "academy/P01-feature-through-plan/1"))

    def test_p01_seed_prepare_rollback_restores_the_default_board(self) -> None:
        """Catches a failed prepare that leaves the protected seed destination modified."""
        temporary, root = p01_academy_git_fixture()
        self.addCleanup(temporary.cleanup)
        before = (root / ".codearbiter/open-tasks.md").read_bytes()
        hooks = Path(temporary.name) / "hooks"
        hooks.mkdir()
        hook = hooks / "pre-commit"
        hook.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
        hook.chmod(0o755)
        git(root, "config", "core.hooksPath", str(hooks))
        with self.assertRaises(PreparationError):
            prepare_lab(root, "P01-feature-through-plan")
        self.assertEqual((root / ".codearbiter/open-tasks.md").read_bytes(), before)
        self.assertEqual(git(root, "branch", "--show-current"), "main")
        self.assertFalse(git(root, "branch", "--list", "academy/P01-feature-through-plan/1"))

    def test_p03_rejects_unsafe_attribution_before_attempt_branch_mutation(self) -> None:
        """Catches P03 inheriting generic preparation before its identity preflight."""
        temporary, root = p01_academy_git_fixture()
        self.addCleanup(temporary.cleanup)
        before = git(root, "rev-parse", "HEAD")
        with patch(
            "academy_engine.scenario.prospective_author_name",
            side_effect=AttributionError("P03 preparation requires a display-safe Git author name."),
        ) as prospective:
            with self.assertRaisesRegex(PreparationError, "display-safe Git author") as caught:
                prepare_lab(root, "P03-record-an-adr")
        prospective.assert_called_once_with(root.resolve(), trust_local_config=True)
        self.assertEqual(git(root, "rev-parse", "HEAD"), before)
        self.assertFalse(git(root, "branch", "--list", "academy/P03-record-an-adr/1"))
        self.assertNotIn("p03-private-canary", str(caught.exception))

    def test_p03_prepared_commit_must_match_prospective_author_and_rolls_back(self) -> None:
        """Catches a safe initial identity being replaced by a mismatched prepare commit."""
        temporary, root = p01_academy_git_fixture()
        self.addCleanup(temporary.cleanup)
        before = git(root, "rev-parse", "HEAD")
        with patch("academy_engine.scenario.prospective_author_name", return_value="Ada Learner"), patch(
            "academy_engine.scenario.commit_author_name", return_value="Other Learner"
        ):
            with self.assertRaisesRegex(PreparationError, "committed attribution"):
                prepare_lab(root, "P03-record-an-adr")
        self.assertEqual(git(root, "rev-parse", "HEAD"), before)
        self.assertEqual(git(root, "branch", "--show-current"), "main")
        self.assertFalse(git(root, "branch", "--list", "academy/P03-record-an-adr/1"))

    def test_p02_prepare_and_reset_refuse_without_installed_authority_before_state_access(self) -> None:
        for operation in (prepare_lab, reset_lab):
            caught: Exception | None = None
            with self.subTest(operation=operation.__name__), patch(
                "academy_engine.scenario.ExternalStateStore.has_records"
            ) as probed, patch(
                "academy_engine.scenario.open_existing_p02_store"
            ) as opened_existing, patch(
                "academy_engine.scenario.open_p02_store"
            ) as opened_new, patch(
                "academy_engine.scenario.restore_p02"
            ) as restored, patch(
                "academy_engine.scenario.prepare_p02"
            ) as prepared:
                try:
                    operation(
                        self.root,
                        "P02-commit-review-pr",
                        installed_authority=False,
                    )
                except Exception as error:
                    caught = error
                else:
                    self.fail("P02 state was reachable without installed authority")

            self.assertIsInstance(caught, PreparationError)
            self.assertEqual(
                str(caught),
                "P02 exercise records require installed Academy authority.",
            )
            probed.assert_not_called()
            opened_existing.assert_not_called()
            opened_new.assert_not_called()
            restored.assert_not_called()
            prepared.assert_not_called()

    def test_p02_prepare_dispatches_to_external_state_before_generic_overlay(self) -> None:
        scenario = self.root / "academy/scenarios/P02-commit-review-pr"
        shutil.copytree(Path(__file__).parents[1] / "academy/scenarios/P02-commit-review-pr", scenario)
        git(self.root, "add", "academy/scenarios/P02-commit-review-pr")
        git(self.root, "commit", "-m", "add P02 fixture")
        base = git(self.root, "rev-parse", "main")
        expected = PreparedLab("P02-commit-review-pr", 1, "academy/P02-commit-review-pr/1", "a" * 40, "b" * 40)
        store = Mock()

        with patch("academy_engine.scenario.preflight_p02", return_value=base) as preflight, patch(
            "academy_engine.scenario.open_p02_store", return_value=store
        ) as opened, patch(
            "academy_engine.scenario.prepare_p02", return_value=expected
        ) as prepared:
            result = prepare_lab(
                self.root,
                "P02-commit-review-pr",
                installed_authority=True,
            )

        self.assertEqual(result, expected)
        preflight.assert_called_once_with(self.root.resolve(), unittest.mock.ANY)
        opened.assert_called_once_with(self.root.resolve(), base=base)
        prepared.assert_called_once()

    def test_p08_proves_installed_authority_before_p02_restore_and_state_open(self) -> None:
        scenario = self.root / "academy/scenarios/P08-repository-hygiene"
        shutil.copytree(
            Path(__file__).parents[1] / "academy/scenarios/P08-repository-hygiene",
            scenario,
        )
        git(self.root, "add", "academy/scenarios/P08-repository-hygiene")
        git(self.root, "commit", "-m", "add P08 fixture")
        base = git(self.root, "rev-parse", "main")
        expected = PreparedLab(
            "P08-repository-hygiene", 1,
            "academy/P08-repository-hygiene/1", base, "b" * 40,
        )
        authority = Mock()
        lab = Mock()
        events: list[str] = []

        def preflight(repository: Path):
            self.assertEqual(repository, self.root.resolve())
            events.append("p08-authority")
            return base, lab, authority

        def restore(*_args, **_kwargs):
            events.append("p02-restore")

        def opened(*_args, **_kwargs):
            events.append("p08-store")
            return Mock()

        with patch("academy_engine.scenario.preflight_p08", side_effect=preflight), patch(
            "academy_engine.scenario._restore_p02_before_later_lab", side_effect=restore
        ), patch("academy_engine.scenario.open_p08_store", side_effect=opened), patch(
            "academy_engine.scenario.prepare_p08", return_value=expected
        ) as prepared:
            result = prepare_lab(
                self.root, "P08-repository-hygiene", installed_authority=True
            )

        self.assertEqual(result, expected)
        self.assertEqual(events, ["p08-authority", "p02-restore", "p08-store"])
        prepared.assert_called_once_with(self.root.resolve(), unittest.mock.ANY, lab)

    def test_p08_authority_failure_blocks_p02_restore_and_p08_state_access(self) -> None:
        failure = ExerciseStateError("installed-authority-required")
        with patch("academy_engine.scenario.preflight_p08", side_effect=failure), patch(
            "academy_engine.scenario._restore_p02_before_later_lab"
        ) as restored, patch("academy_engine.scenario.open_p08_store") as opened, patch(
            "academy_engine.scenario.prepare_p08"
        ) as prepared:
            with self.assertRaises(PreparationError) as raised:
                prepare_lab(
                    self.root, "P08-repository-hygiene", installed_authority=True
                )
        self.assertIn("P02 requires installed Academy authority", str(raised.exception))
        restored.assert_not_called()
        opened.assert_not_called()
        prepared.assert_not_called()

    def test_p08_reset_dispatches_after_authority_and_p02_restoration(self) -> None:
        scenario = self.root / "academy/scenarios/P08-repository-hygiene"
        shutil.copytree(
            Path(__file__).parents[1] / "academy/scenarios/P08-repository-hygiene",
            scenario,
        )
        git(self.root, "add", "academy/scenarios/P08-repository-hygiene")
        git(self.root, "commit", "-m", "add P08 fixture")
        base = git(self.root, "rev-parse", "main")
        expected = PreparedLab(
            "P08-repository-hygiene", 2,
            "academy/P08-repository-hygiene/2", base, "b" * 40,
        )
        events: list[str] = []
        lab, authority, store = Mock(), Mock(), Mock()

        def preflight(repository: Path):
            self.assertEqual(repository, self.root.resolve())
            events.append("p08-authority")
            return base, lab, authority

        def restore(*_args, **_kwargs):
            events.append("p02-restore")

        def opened(*_args, **_kwargs):
            events.append("p08-store")
            return store

        with patch("academy_engine.scenario.preflight_p08", side_effect=preflight), patch(
            "academy_engine.scenario._restore_p02_before_later_lab", side_effect=restore
        ), patch("academy_engine.scenario.open_p08_store", side_effect=opened), patch(
            "academy_engine.scenario.reset_p08", return_value=expected, create=True
        ) as reset:
            result = reset_lab(
                self.root, "P08-repository-hygiene", installed_authority=True
            )

        self.assertEqual(result, expected)
        self.assertEqual(events, ["p08-authority", "p02-restore", "p08-store"])
        reset.assert_called_once_with(self.root.resolve(), store)

    def test_fresh_p02_dispatch_opens_state_at_the_base_verified_by_preflight(self) -> None:
        """Mutation caught: discarding preflight_p02's verified base before state open."""
        scenario = self.root / "academy/scenarios/P02-commit-review-pr"
        shutil.copytree(Path(__file__).parents[1] / "academy/scenarios/P02-commit-review-pr", scenario)
        git(self.root, "add", "academy/scenarios/P02-commit-review-pr")
        git(self.root, "commit", "-m", "add P02 fixture")
        verified_base = "f" * 40
        expected = PreparedLab("P02-commit-review-pr", 1, "academy/P02-commit-review-pr/1", "a" * 40, "b" * 40)
        store = Mock()

        with patch(
            "academy_engine.scenario.preflight_p02", return_value=verified_base
        ) as preflight, patch(
            "academy_engine.scenario.open_p02_store", return_value=store
        ) as opened, patch(
            "academy_engine.scenario.prepare_p02", return_value=expected
        ):
            result = prepare_lab(
                self.root,
                "P02-commit-review-pr",
                installed_authority=True,
            )

        self.assertEqual(result, expected)
        preflight.assert_called_once_with(self.root.resolve(), unittest.mock.ANY)
        opened.assert_called_once_with(self.root.resolve(), base=verified_base)

    def test_fresh_p02_preflight_rejects_before_external_state_open(self) -> None:
        scenario = self.root / "academy/scenarios/P02-commit-review-pr"
        shutil.copytree(Path(__file__).parents[1] / "academy/scenarios/P02-commit-review-pr", scenario)
        git(self.root, "add", "academy/scenarios/P02-commit-review-pr")
        git(self.root, "commit", "-m", "add P02 fixture")

        with patch(
            "academy_engine.scenario.ExternalStateStore.has_records", return_value=False
        ), patch(
            "academy_engine.scenario.preflight_p02",
            side_effect=PreparationError("preflight rejected"),
            create=True,
        ) as preflight, patch(
            "academy_engine.scenario.open_p02_store"
        ) as opened, patch(
            "academy_engine.scenario.prepare_p02",
            return_value=PreparedLab(
                "P02-commit-review-pr", 1, "academy/P02-commit-review-pr/1", "a" * 40, "b" * 40
            ),
        ):
            with self.assertRaisesRegex(PreparationError, "preflight rejected"):
                prepare_lab(
                    self.root,
                    "P02-commit-review-pr",
                    installed_authority=True,
                )

        preflight.assert_called_once()
        opened.assert_not_called()

    def test_p02_reset_restores_then_prepares_the_next_attempt(self) -> None:
        scenario = self.root / "academy/scenarios/P02-commit-review-pr"
        shutil.copytree(Path(__file__).parents[1] / "academy/scenarios/P02-commit-review-pr", scenario)
        git(self.root, "add", "academy/scenarios/P02-commit-review-pr")
        git(self.root, "commit", "-m", "add P02 fixture")
        expected = PreparedLab("P02-commit-review-pr", 2, "academy/P02-commit-review-pr/2", "a" * 40, "b" * 40)
        store = Mock()

        with patch(
            "academy_engine.scenario._p02_preparation_base", return_value="a" * 40
        ), patch(
            "academy_engine.scenario.open_existing_p02_store", return_value=store
        ), patch(
            "academy_engine.scenario.restore_p02"
        ) as restored, patch("academy_engine.scenario.prepare_p02", return_value=expected):
            result = reset_lab(
                self.root,
                "P02-commit-review-pr",
                installed_authority=True,
            )

        restored.assert_called_once()
        self.assertEqual(result, expected)

    def test_p02_catalog_manifest_and_os_failures_use_stable_path_free_code(self) -> None:
        scenario = self.root / "academy/scenarios/P02-commit-review-pr"
        shutil.copytree(Path(__file__).parents[1] / "academy/scenarios/P02-commit-review-pr", scenario)
        git(self.root, "add", "academy/scenarios/P02-commit-review-pr")
        git(self.root, "commit", "-m", "add P02 fixture")
        private_path = r"C:\external\learner-secret\manifest.json"
        cases = (
            (
                "catalog",
                "academy_engine.scenario.Catalog.load",
                CatalogError(f"could not read catalog: {private_path}"),
            ),
            (
                "manifest",
                "academy_engine.scenario.load_manifest_file",
                CatalogError(f"could not read manifest: {private_path}"),
            ),
            (
                "os",
                "academy_engine.scenario.Catalog.load",
                OSError(f"access denied: {private_path}"),
            ),
        )

        for label, target, failure in cases:
            with self.subTest(label=label), patch(target, side_effect=failure):
                with self.assertRaises(PreparationError) as caught:
                    prepare_lab(
                        self.root,
                        "P02-commit-review-pr",
                        installed_authority=True,
                    )

            self.assertEqual(str(caught.exception), "P02 exercise state is invalid.")
            self.assertNotIn(private_path, str(caught.exception))
            self.assertIsInstance(caught.exception.__cause__, ExerciseStateError)
            self.assertEqual(caught.exception.__cause__.code, "invalid-exercise-state")

    def test_p02_prepare_and_reset_git_discovery_is_unchecked_and_path_free(self) -> None:
        scenario = self.root / "academy/scenarios/P02-commit-review-pr"
        shutil.copytree(Path(__file__).parents[1] / "academy/scenarios/P02-commit-review-pr", scenario)
        git(self.root, "add", "academy/scenarios/P02-commit-review-pr")
        git(self.root, "commit", "-m", "add P02 fixture")
        private_path = r"C:\external\learner-secret\.git"
        raw_git = f"fatal: unsafe repository at {private_path} for learner@example.test"

        for operation in (prepare_lab, reset_lab):
            calls: list[bool] = []

            def checked_git_failure(_root, _args, *, check=True, **_kwargs):
                calls.append(check)
                if check:
                    raise GitCommandError(raw_git)
                return subprocess.CompletedProcess(["git"], 128, "", raw_git)

            with self.subTest(operation=operation.__name__), patch(
                "academy_engine.scenario._run_git", side_effect=checked_git_failure
            ):
                caught_error: Exception | None = None
                try:
                    operation(
                        self.root,
                        "P02-commit-review-pr",
                        installed_authority=True,
                    )
                except Exception as error:
                    caught_error = error
                else:
                    self.fail("P02 Git discovery unexpectedly succeeded")

            self.assertEqual(calls, [False])
            self.assertIsNotNone(caught_error)
            self.assertEqual(str(caught_error), "P02 exercise state is invalid.")
            self.assertNotIn(private_path, str(caught_error))
            self.assertNotIn(raw_git, str(caught_error))
            self.assertIsInstance(caught_error.__cause__, ExerciseStateError)
            self.assertEqual(caught_error.__cause__.code, "invalid-exercise-state")

    def test_later_lab_resumes_p02_restoration_even_after_checkout_reached_main(self) -> None:
        add_scenario(self.root, "P03-record-an-adr")
        git(self.root, "add", "academy/scenarios/P03-record-an-adr")
        git(self.root, "commit", "-m", "add P03 fixture")
        store = Mock()

        with patch(
            "academy_engine.scenario.ExternalStateStore.has_records", return_value=True
        ), patch("academy_engine.scenario.open_existing_p02_store", return_value=store), patch(
            "academy_engine.scenario.has_active_p02", return_value=True
        ), patch("academy_engine.scenario.restore_p02") as restored:
            try:
                result = prepare_lab(
                    self.root,
                    "P03-record-an-adr",
                    installed_authority=True,
                )
            except TypeError as error:
                self.fail(f"installed authority was not accepted: {error}")

        restored.assert_called_once_with(
            self.root.resolve(), store, transition_to="P03-record-an-adr"
        )
        self.assertEqual(result.lab_id, "P03-record-an-adr")

    def test_later_lab_without_installed_authority_refuses_new_records_before_restore(self) -> None:
        add_scenario(self.root, "P03-record-an-adr")
        git(self.root, "add", "academy/scenarios/P03-record-an-adr")
        git(self.root, "commit", "-m", "add P03 fixture")
        before_head = git(self.root, "rev-parse", "HEAD")
        before_branch = git(self.root, "branch", "--show-current")

        with patch(
            "academy_engine.scenario.ExternalStateStore.has_records", return_value=True
        ) as probed, patch(
            "academy_engine.scenario.open_existing_p02_store"
        ) as opened, patch(
            "academy_engine.scenario.restore_p02"
        ) as restored:
            try:
                prepare_lab(
                    self.root,
                    "P03-record-an-adr",
                    installed_authority=False,
                )
            except TypeError as error:
                self.fail(f"installed authority was not accepted: {error}")
            except PreparationError as error:
                caught = error
            else:
                self.fail("later-lab preparation restored P02 without installed authority")

        self.assertEqual(
            str(caught),
            "P02 exercise records require installed Academy authority.",
        )
        probed.assert_called_once_with(self.root.resolve(), lab="p02")
        opened.assert_not_called()
        restored.assert_not_called()
        self.assertEqual(git(self.root, "rev-parse", "HEAD"), before_head)
        self.assertEqual(git(self.root, "branch", "--show-current"), before_branch)

    def test_later_lab_reset_without_installed_authority_refuses_records_before_mutation(self) -> None:
        add_scenario(self.root, "P03-record-an-adr")
        git(self.root, "add", "academy/scenarios/P03-record-an-adr")
        git(self.root, "commit", "-m", "add P03 fixture")
        with patch(
            "academy_engine.scenario.ExternalStateStore.has_records", return_value=False
        ):
            prepare_lab(self.root, "P03-record-an-adr")
        before_head = git(self.root, "rev-parse", "HEAD")
        before_branch = git(self.root, "branch", "--show-current")
        before_refs = git(
            self.root,
            "for-each-ref",
            "--format=%(refname)",
            "refs/heads/academy/",
        )

        with patch(
            "academy_engine.scenario.ExternalStateStore.has_records", return_value=True
        ) as probed, patch(
            "academy_engine.scenario.open_existing_p02_store"
        ) as opened, patch(
            "academy_engine.scenario.restore_p02"
        ) as restored:
            try:
                reset_lab(
                    self.root,
                    "P03-record-an-adr",
                    installed_authority=False,
                )
            except TypeError as error:
                self.fail(f"installed authority was not accepted: {error}")
            except PreparationError as error:
                caught = error
            else:
                self.fail("later-lab reset mutated state without installed authority")

        self.assertEqual(
            str(caught),
            "P02 exercise records require installed Academy authority.",
        )
        probed.assert_called_once_with(self.root.resolve(), lab="p02")
        opened.assert_not_called()
        restored.assert_not_called()
        self.assertEqual(git(self.root, "rev-parse", "HEAD"), before_head)
        self.assertEqual(git(self.root, "branch", "--show-current"), before_branch)
        self.assertEqual(
            git(
                self.root,
                "for-each-ref",
                "--format=%(refname)",
                "refs/heads/academy/",
            ),
            before_refs,
        )

    def test_later_lab_with_no_p02_records_never_opens_or_mutates_external_state(self) -> None:
        add_scenario(self.root, "P03-record-an-adr")
        git(self.root, "add", "academy/scenarios/P03-record-an-adr")
        git(self.root, "commit", "-m", "add P03 fixture")

        with patch(
            "academy_engine.scenario.ExternalStateStore.has_records", return_value=False
        ) as probed, patch(
            "academy_engine.scenario.open_existing_p02_store"
        ) as opened, patch(
            "academy_engine.scenario.restore_p02"
        ) as restored:
            result = prepare_lab(self.root, "P03-record-an-adr")

        probed.assert_called_once_with(self.root.resolve(), lab="p02")
        opened.assert_not_called()
        restored.assert_not_called()
        self.assertEqual(result.lab_id, "P03-record-an-adr")

    def test_later_lab_with_harmless_local_config_and_no_p02_state_prepares_without_creating_state(self) -> None:
        """Catches a read-only P02 locator that applies mutation-policy config validation."""
        add_scenario(self.root, "P04-review-a-dependency")
        git(self.root, "add", "academy/scenarios/P04-review-a-dependency")
        git(self.root, "commit", "-m", "add P04 fixture")
        git(self.root, "config", "pull.rebase", "false")
        state_root = Path(self.temporary.name) / "absent-installed-state"

        try:
            with patch(
                "academy_engine.external_state.resolve_state_root",
                return_value=state_root,
            ):
                result = prepare_lab(self.root, "P04-review-a-dependency")
        finally:
            self.assertFalse(state_root.exists())

        self.assertEqual(result.lab_id, "P04-review-a-dependency")
        self.assertEqual(result.branch, "academy/P04-review-a-dependency/1")

    def test_later_lab_blocks_when_only_stale_p02_epochs_exist(self) -> None:
        add_scenario(self.root, "P03-record-an-adr")
        git(self.root, "add", "academy/scenarios/P03-record-an-adr")
        git(self.root, "commit", "-m", "add P03 fixture")
        before = git(self.root, "rev-parse", "HEAD")

        with patch(
            "academy_engine.scenario.ExternalStateStore.has_records", return_value=True
        ), patch(
            "academy_engine.scenario.open_existing_p02_store", return_value=None
        ), patch("academy_engine.scenario.restore_p02") as restored:
            with self.assertRaisesRegex(PreparationError, "identity"):
                prepare_lab(
                    self.root,
                    "P03-record-an-adr",
                    installed_authority=True,
                )

        restored.assert_not_called()
        self.assertEqual(git(self.root, "rev-parse", "HEAD"), before)

    def test_later_lab_rejects_partial_current_locator_state_without_sidecar_mutation(self) -> None:
        for kind in (
            "missing-lock",
            "directory-lock",
            "empty-epochs",
            "missing-identity",
            "corrupt-identity",
        ):
            with self.subTest(kind=kind):
                temporary, root = academy_git_fixture()
                try:
                    add_scenario(root, "P03-record-an-adr")
                    git(root, "add", "academy/scenarios/P03-record-an-adr")
                    git(root, "commit", "-m", "add P03 fixture")
                    base = git(root, "rev-parse", "HEAD")
                    catalog = root / "academy/catalog.json"
                    state_root = Path(temporary.name) / "partial-state"
                    store = ExternalStateStore.open(
                        root,
                        academy_base_commit=base,
                        catalog_sha256=hashlib.sha256(catalog.read_bytes()).hexdigest(),
                        test_root=state_root,
                    )
                    if kind == "missing-lock":
                        store._lock_path.unlink()
                    elif kind == "directory-lock":
                        store._lock_path.unlink()
                        store._lock_path.mkdir()
                    elif kind == "empty-epochs":
                        shutil.rmtree(store._epoch_dir)
                    elif kind == "missing-identity":
                        store._identity_path.unlink()
                    else:
                        store._identity_path.write_bytes(b'{"corrupt":true}\n')
                    before = {
                        path.relative_to(state_root).as_posix(): (
                            "directory" if path.is_dir() else path.read_bytes()
                        )
                        for path in state_root.rglob("*")
                    }
                    head = git(root, "rev-parse", "HEAD")

                    with patch(
                        "academy_engine.external_state.resolve_state_root",
                        return_value=state_root,
                    ):
                        with self.assertRaisesRegex(PreparationError, "state|identity"):
                            prepare_lab(root, "P03-record-an-adr")

                    after = {
                        path.relative_to(state_root).as_posix(): (
                            "directory" if path.is_dir() else path.read_bytes()
                        )
                        for path in state_root.rglob("*")
                    }
                    self.assertEqual(after, before)
                    self.assertEqual(git(root, "rev-parse", "HEAD"), head)
                finally:
                    temporary.cleanup()

    def test_prepare_refuses_dirty_default_detached_and_unknown_lab_without_moving_head(self) -> None:
        before = git(self.root, "rev-parse", "HEAD")
        (self.root / "notes.txt").write_text("uncommitted", encoding="utf-8")
        with self.assertRaisesRegex(PreparationError, "clean"):
            prepare_lab(self.root, "F01-fork-clone-doctor")
        self.assertEqual(git(self.root, "rev-parse", "HEAD"), before)
        (self.root / "notes.txt").unlink()
        with self.assertRaisesRegex(PreparationError, "catalog"):
            prepare_lab(self.root, "not-in-catalog")
        self.assertEqual(git(self.root, "rev-parse", "HEAD"), before)
        git(self.root, "checkout", "--detach")
        with self.assertRaisesRegex(PreparationError, "detached"):
            prepare_lab(self.root, "F01-fork-clone-doctor")

    def test_prepare_numbers_monotonically_and_prevalidates_missing_sources(self) -> None:
        git(self.root, "branch", "academy/F01-fork-clone-doctor/2")
        prepared = prepare_lab(self.root, "F01-fork-clone-doctor")
        self.assertEqual(prepared.attempt, 3)
        git(self.root, "checkout", "main")
        git(self.root, "rm", "academy/scenarios/F01-fork-clone-doctor/files/seed.txt")
        git(self.root, "commit", "-m", "remove scenario source")
        before = git(self.root, "rev-parse", "HEAD")
        with self.assertRaisesRegex(PreparationError, "source"):
            prepare_lab(self.root, "F01-fork-clone-doctor")
        self.assertEqual(git(self.root, "rev-parse", "HEAD"), before)
        self.assertFalse(git(self.root, "branch", "--list", "academy/F01-fork-clone-doctor/4"))

    def test_prepare_applies_declared_removal_and_requires_safe_remotes_when_requested(self) -> None:
        manifest_path = self.root / "academy/scenarios/F01-fork-clone-doctor/manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["removals"] = ["obsolete.txt"]
        manifest["requires_push_safe_setup"] = True
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        catalog_path = self.root / "academy/catalog.json"
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
        catalog["labs"][0]["requires_push_safe_setup"] = True
        catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
        (self.root / "obsolete.txt").write_text("remove me\n", encoding="utf-8")
        git(self.root, "add", ".")
        git(self.root, "commit", "-m", "scenario removal")
        before = git(self.root, "rev-parse", "HEAD")
        git(self.root, "remote", "set-url", "origin", "https://github.com/arbiterForge/arbiter-academy.git")
        with self.assertRaisesRegex(PreparationError, "origin"):
            prepare_lab(self.root, "F01-fork-clone-doctor")
        self.assertEqual(git(self.root, "rev-parse", "HEAD"), before)

    def test_progress_derives_only_lab_attempt_and_status_from_refs(self) -> None:
        prepare_lab(self.root, "F01-fork-clone-doctor")
        report = inspect_progress(self.root)
        self.assertEqual(report.entries[0].lab_id, "F01-fork-clone-doctor")
        self.assertEqual(report.entries[0].attempt, 1)
        self.assertNotIn(str(self.root), report.render())

    def test_cli_progress_has_a_stable_error_outside_a_repository(self) -> None:
        script = Path(__file__).parents[1] / "scripts" / "academy.py"
        with tempfile.TemporaryDirectory() as plain:
            result = subprocess.run([sys.executable, str(script), "progress"], cwd=plain, text=True, encoding="utf-8", capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("error:", result.stderr)
        self.assertNotIn("Traceback", result.stderr + result.stdout)

    def test_prepare_rejects_protected_git_removal_before_branch_creation(self) -> None:
        manifest_path = self.root / "academy/scenarios/F01-fork-clone-doctor/manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["removals"] = [".git/config"]
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        git(self.root, "add", "academy/scenarios/F01-fork-clone-doctor/manifest.json")
        git(self.root, "commit", "-m", "unsafe manifest")
        before = git(self.root, "rev-parse", "HEAD")
        with self.assertRaisesRegex(PreparationError, "protected"):
            prepare_lab(self.root, "F01-fork-clone-doctor")
        self.assertTrue((self.root / ".git" / "config").is_file())
        self.assertEqual(git(self.root, "rev-parse", "HEAD"), before)
        self.assertFalse(git(self.root, "branch", "--list", "academy/F01-fork-clone-doctor/1"))

    def test_prepare_rejects_an_in_repository_ancestor_symlink(self) -> None:
        outside = self.root / "safe-target"
        outside.mkdir()
        link = self.root / "academy/scenarios/F01-fork-clone-doctor/files/link"
        try:
            os.symlink(outside, link, target_is_directory=True)
        except OSError as error:
            self.skipTest(f"symlink/reparse creation unavailable: {error}")
        manifest_path = self.root / "academy/scenarios/F01-fork-clone-doctor/manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["files"] = [{"source": "link/seed.txt", "destination": "exercise/seed.txt"}]
        (outside / "seed.txt").write_text("escape\n", encoding="utf-8")
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        git(
            self.root,
            "add",
            "academy/scenarios/F01-fork-clone-doctor/manifest.json",
            "academy/scenarios/F01-fork-clone-doctor/files/link",
            "safe-target/seed.txt",
        )
        git(self.root, "commit", "-m", "reparse manifest")
        with self.assertRaisesRegex(PreparationError, "reparse"):
            prepare_lab(self.root, "F01-fork-clone-doctor")
        self.assertFalse((self.root / "exercise" / "seed.txt").exists())

    def test_prepare_rejects_official_origin_for_non_push_lab_f02(self) -> None:
        add_scenario(self.root, "F02-orient-to-state")
        git(self.root, "add", "academy/scenarios/F02-orient-to-state")
        git(self.root, "commit", "-m", "add F02 fixture")
        git(self.root, "remote", "set-url", "origin", "https://github.com/arbiterForge/arbiter-academy.git")
        with self.assertRaisesRegex(PreparationError, "origin"):
            prepare_lab(self.root, "F02-orient-to-state")
        self.assertFalse(git(self.root, "branch", "--list", "academy/F02-orient-to-state/1"))

    def test_prepare_rolls_back_branch_index_and_overlay_after_commit_hook_failure(self) -> None:
        hooks = Path(self.temporary.name) / "hooks"
        hooks.mkdir()
        hook = hooks / "pre-commit"
        hook.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
        hook.chmod(0o755)
        git(self.root, "config", "core.hooksPath", str(hooks))
        before = git(self.root, "rev-parse", "HEAD")
        with self.assertRaises(PreparationError):
            prepare_lab(self.root, "F01-fork-clone-doctor")
        self.assertEqual(git(self.root, "branch", "--show-current"), "main")
        self.assertEqual(git(self.root, "rev-parse", "HEAD"), before)
        self.assertEqual(git(self.root, "status", "--porcelain", "--untracked-files=all"), "")
        self.assertFalse(git(self.root, "branch", "--list", "academy/F01-fork-clone-doctor/1"))
        self.assertFalse((self.root / "exercise" / "seed.txt").exists())
