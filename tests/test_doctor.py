"""Doctor command behavior for Academy learner setup diagnostics."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from academy_engine.doctor import inspect_doctor


PUSH_DISABLED = "DISABLED"


def git(directory: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=directory, check=True, text=True, capture_output=True)


class DoctorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name) / "repository"
        self.root.mkdir()
        git(self.root, "init")
        git(self.root, "config", "user.name", "Academy Learner")
        git(self.root, "config", "user.email", "learner@example.test")
        (self.root / "README.md").write_text("academy\n", encoding="utf-8")
        git(self.root, "add", "README.md")
        git(self.root, "commit", "-m", "initial")
        git(self.root, "remote", "add", "origin", "https://github.com/learner/arbiter-academy.git")
        git(self.root, "remote", "add", "upstream", "https://github.com/arbiterForge/arbiter-academy.git")
        git(self.root, "remote", "set-url", "--push", "upstream", PUSH_DISABLED)
        codearbiter = self.root / ".codearbiter"
        codearbiter.mkdir()
        (codearbiter / "CONTEXT.md").write_text("initialized\n", encoding="utf-8")
        git(self.root, "add", ".codearbiter/CONTEXT.md")
        git(self.root, "commit", "-m", "initialize codeArbiter")

    def test_reports_structured_safe_learner_setup(self) -> None:
        report = inspect_doctor(self.root)

        self.assertTrue(report.safe_for_push_labs)
        self.assertTrue(report.git.available)
        self.assertTrue(report.worktree.clean)
        self.assertFalse(report.worktree.detached)
        self.assertEqual(report.remotes.origin.owner, "learner")
        self.assertTrue(report.remotes.upstream.is_official)
        self.assertTrue(getattr(report.remotes, "upstream_push_disabled", False))
        self.assertTrue(report.codearbiter_active)
        self.assertIn("python scripts/academy.py doctor", report.host_guidance)
        self.assertIn("git remote set-url --push upstream DISABLED", report.host_guidance)
        self.assertIn(
            "Origin identity is fork-compatible; GitHub lineage is not verified offline.",
            report.render(),
        )

    def test_reports_unsafe_configuration_without_a_traceback(self) -> None:
        git(self.root, "remote", "set-url", "origin", "https://github.com/arbiterForge/arbiter-academy.git")

        report = inspect_doctor(self.root)

        self.assertFalse(report.safe_for_push_labs)
        self.assertTrue(report.issues)
        self.assertIn(
            "Origin identity is not fork-compatible; GitHub lineage is not verified offline.",
            report.render(),
        )
        self.assertNotIn("Origin identity is fork-compatible;", report.render())

    def test_reports_a_dirty_worktree_as_unsafe(self) -> None:
        (self.root / "README.md").write_text("changed\n", encoding="utf-8")

        report = inspect_doctor(self.root)

        self.assertFalse(report.worktree.clean)
        self.assertIn("worktree has uncommitted changes.", report.issues)

    def test_forces_all_untracked_files_visible_despite_status_config(self) -> None:
        git(self.root, "config", "status.showUntrackedFiles", "no")
        (self.root / "hidden-untracked.txt").write_text("hidden\n", encoding="utf-8")

        report = inspect_doctor(self.root)

        self.assertFalse(report.worktree.clean)
        self.assertIn("worktree has uncommitted changes.", report.issues)

    def test_reports_a_detached_head_as_unsafe(self) -> None:
        git(self.root, "checkout", "--detach")

        report = inspect_doctor(self.root)

        self.assertTrue(report.worktree.detached)
        self.assertIn("HEAD is detached; check out a learner branch before a push lab.", report.issues)

    def test_reports_missing_codearbiter_activation_as_unsafe(self) -> None:
        (self.root / ".codearbiter").rename(self.root / ".academy-hidden-codearbiter")

        report = inspect_doctor(self.root)

        self.assertFalse(report.codearbiter_active)
        self.assertIn("codeArbiter is not activated in this repository.", report.issues)

    def test_reports_uninitialized_codearbiter_as_unsafe(self) -> None:
        (self.root / ".codearbiter" / "CONTEXT.md").rename(self.root / ".codearbiter" / "CONTEXT.hidden")

        report = inspect_doctor(self.root)

        self.assertTrue(report.codearbiter_active)
        self.assertFalse(report.codearbiter_initialized)
        self.assertIn("codeArbiter is not initialized in this repository.", report.issues)

    def test_reports_available_git_when_current_directory_is_not_a_repository(self) -> None:
        plain_directory = Path(self.temporary_directory.name) / "plain-directory"
        plain_directory.mkdir()

        report = inspect_doctor(plain_directory)

        self.assertTrue(report.git.available)
        self.assertIsNotNone(report.git.version)
        self.assertFalse(report.safe_for_push_labs)

    def test_cli_returns_nonzero_and_readable_report_for_unsafe_repository(self) -> None:
        git(self.root, "remote", "set-url", "origin", "https://github.com/arbiterForge/arbiter-academy.git")
        script = Path(__file__).parents[1] / "scripts" / "academy.py"

        result = subprocess.run(
            [sys.executable, str(script), "doctor"],
            cwd=self.root,
            text=True,
            capture_output=True,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("UNSAFE", result.stdout)
        self.assertNotIn("Traceback", result.stdout + result.stderr)

    def test_cli_normalizes_malformed_remote_parser_errors_without_traceback(self) -> None:
        git(self.root, "remote", "set-url", "origin", "https://[github.com/learner/arbiter-academy.git")
        script = Path(__file__).parents[1] / "scripts" / "academy.py"

        result = subprocess.run(
            [sys.executable, str(script), "doctor"],
            cwd=self.root,
            text=True,
            capture_output=True,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("origin remote is invalid", result.stdout)
        self.assertNotIn("Traceback", result.stdout + result.stderr)
