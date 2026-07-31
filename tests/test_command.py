"""Behavioral checks for the Academy Git command boundary."""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from academy_engine.command import GitCommandError
from academy_engine.git import run_git


def git(directory: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=directory, check=True, text=True, capture_output=True)


class RunGitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name) / "training-repository"
        self.root.mkdir()
        git(self.root, "init")
        (self.root / "nested").mkdir()

    def test_runs_an_argument_sequence_from_the_repository_root(self) -> None:
        result = run_git(self.root / "nested", ["rev-parse", "--show-toplevel"])

        self.assertEqual(Path(result.stdout.strip()).resolve(), self.root.resolve())

    def test_treats_each_argument_literally(self) -> None:
        result = run_git(self.root, ["config", "academy.literal", "value with spaces; not-a-command"])

        self.assertEqual(result.returncode, 0)
        self.assertEqual(
            run_git(self.root, ["config", "--get", "academy.literal"]).stdout.strip(),
            "value with spaces; not-a-command",
        )

    def test_surfaces_git_stderr_for_a_failed_command(self) -> None:
        with self.assertRaisesRegex(GitCommandError, "does-not-exist"):
            run_git(self.root, ["show-ref", "--verify", "refs/heads/does-not-exist"])

    def test_decodes_non_ascii_git_output_as_utf8(self) -> None:
        configured_value = "fullwidth slash: \uFF0F"
        git(self.root, "config", "academy.unicode", configured_value)

        try:
            result = run_git(self.root, ["config", "--get", "academy.unicode"])
        except UnicodeDecodeError as error:
            self.fail(f"Git output used locale decoding instead of UTF-8: {error}")
        if result.stdout is None:
            self.fail("Git output became unusable after locale decoding failed")
        self.assertEqual(result.stdout.strip(), configured_value)

    def test_surrogateescapes_invalid_utf8_git_output(self) -> None:
        config_path = self.root / ".git" / "config"
        config_path.write_bytes(
            config_path.read_bytes() + b"\n[academy]\n\tinvalid = invalid-\x81-byte\n"
        )

        try:
            result = run_git(self.root, ["config", "--get", "academy.invalid"])
        except UnicodeDecodeError as error:
            self.fail(f"invalid Git bytes crashed text decoding: {error}")
        if result.stdout is None:
            self.fail("invalid Git bytes made captured text unusable")
        self.assertEqual(result.stdout.strip(), "invalid-\udc81-byte")
