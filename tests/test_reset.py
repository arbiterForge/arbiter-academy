from __future__ import annotations

import unittest
from datetime import datetime, timezone

from academy_engine.scenario import PreparationError, prepare_lab, reset_lab
from tests.test_scenario import academy_git_fixture, git


class ResetTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary, self.root = academy_git_fixture()
        self.addCleanup(self.temporary.cleanup)

    def test_reset_archives_current_attempt_then_creates_independent_retry(self) -> None:
        first = prepare_lab(self.root, "F01-fork-clone-doctor")
        (self.root / "learner.txt").write_text("work\n", encoding="utf-8")
        git(self.root, "add", "learner.txt")
        git(self.root, "commit", "-m", "learner work")
        first_head = git(self.root, "rev-parse", "HEAD")
        retry = reset_lab(self.root, "F01-fork-clone-doctor", now=lambda: datetime(2026, 7, 30, 12, 0, 0, tzinfo=timezone.utc))
        self.assertEqual(retry.attempt, 2)
        self.assertEqual(git(self.root, "rev-parse", "academy/archive/F01-fork-clone-doctor/20260730T120000Z"), first_head)
        self.assertEqual(git(self.root, "merge-base", "academy/F01-fork-clone-doctor/2", "main"), git(self.root, "rev-parse", "main"))
        self.assertNotEqual(git(self.root, "rev-parse", "academy/F01-fork-clone-doctor/2^"), first_head)

    def test_reset_refuses_dirty_wrong_attempt_and_archive_collision(self) -> None:
        prepare_lab(self.root, "F01-fork-clone-doctor")
        (self.root / "dirty.txt").write_text("dirty\n", encoding="utf-8")
        with self.assertRaisesRegex(PreparationError, "clean"):
            reset_lab(self.root, "F01-fork-clone-doctor")
        (self.root / "dirty.txt").unlink()
        git(self.root, "checkout", "main")
        with self.assertRaisesRegex(PreparationError, "matching attempt"):
            reset_lab(self.root, "F01-fork-clone-doctor")

    def test_reset_refuses_a_deterministic_archive_collision_without_deleting_attempt(self) -> None:
        prepared = prepare_lab(self.root, "F01-fork-clone-doctor")
        timestamp = datetime(2026, 7, 30, 12, 0, 0, tzinfo=timezone.utc)
        archive = "academy/archive/F01-fork-clone-doctor/20260730T120000Z"
        git(self.root, "branch", archive)
        with self.assertRaisesRegex(PreparationError, "archive branch already exists"):
            reset_lab(self.root, "F01-fork-clone-doctor", now=lambda: timestamp)
        self.assertEqual(git(self.root, "rev-parse", prepared.branch), prepared.commit_sha)
