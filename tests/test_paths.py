"""Tests for non-mutating Academy overlay path containment."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from academy_engine.paths import PathBoundaryError, ensure_within


class EnsureWithinTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name) / "repository"
        self.root.mkdir()

    def test_returns_a_normalized_path_inside_the_repository(self) -> None:
        actual = ensure_within(self.root, self.root / "overlays" / "lesson.md")

        self.assertEqual(actual, (self.root / "overlays" / "lesson.md").resolve())

    def test_overlay_destination_cannot_escape_repository(self) -> None:
        with self.assertRaises(PathBoundaryError):
            ensure_within(self.root, self.root / ".." / "outside.txt")

    def test_absolute_path_outside_the_repository_is_rejected(self) -> None:
        with self.assertRaises(PathBoundaryError):
            ensure_within(self.root, self.root.parent / "outside.txt")

    def test_existing_symlink_escape_is_rejected(self) -> None:
        outside = self.root.parent / "outside"
        outside.mkdir()
        escape = self.root / "escape"
        try:
            escape.symlink_to(outside, target_is_directory=True)
        except OSError as error:
            self.skipTest(f"symlinks are unavailable in this environment: {error}")

        with self.assertRaises(PathBoundaryError):
            ensure_within(self.root, escape / "lesson.md")

    @unittest.skipUnless(os.name == "nt", "Windows drive and case semantics")
    def test_windows_case_normalized_inside_path_is_accepted(self) -> None:
        alternate_case = Path(str(self.root).swapcase()) / "inside.txt"

        self.assertEqual(ensure_within(self.root, alternate_case), (self.root / "inside.txt").resolve())
