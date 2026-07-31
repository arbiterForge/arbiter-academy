from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from academy_engine.scenario import PreparationError, prepare_lab
from academy_engine.progress import inspect_progress


def git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=root, text=True, encoding="utf-8", capture_output=True, check=True)
    return result.stdout.strip()


def academy_git_fixture() -> tuple[tempfile.TemporaryDirectory[str], Path]:
    temporary = tempfile.TemporaryDirectory()
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
