"""Behavioral checks for the Academy Git command boundary."""

from __future__ import annotations

import subprocess
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import academy_engine.command as command_module
from academy_engine.checkpoints import evaluate_checkpoint
from academy_engine.command import GitCommandError, _run
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

    def test_streaming_capture_stops_at_the_stdout_byte_cap(self) -> None:
        with patch("academy_engine.command._MAX_STREAM_BYTES", 64):
            with self.assertRaisesRegex(GitCommandError, "stdout.*64-byte"):
                _run(
                    [sys.executable, "-c", "import sys; sys.stdout.buffer.write(b'x' * 65)"],
                    cwd=self.root,
                    check=False,
                )

    def test_streaming_capture_stops_at_the_stderr_byte_cap(self) -> None:
        with patch("academy_engine.command._MAX_STREAM_BYTES", 64):
            with self.assertRaisesRegex(GitCommandError, "stderr.*64-byte"):
                _run(
                    [sys.executable, "-c", "import sys; sys.stderr.buffer.write(b'x' * 65)"],
                    cwd=self.root,
                    check=False,
                )

    def test_timeout_terminates_the_process_without_waiting_for_normal_exit(self) -> None:
        started = time.monotonic()
        with patch("academy_engine.command._COMMAND_TIMEOUT_SECONDS", 0.1):
            with self.assertRaisesRegex(GitCommandError, "bounded timeout"):
                _run(
                    [sys.executable, "-c", "import time; time.sleep(30)"],
                    cwd=self.root,
                    check=False,
                )
        self.assertLess(time.monotonic() - started, 5)

    def test_timeout_terminates_delayed_child_before_its_side_effect(self) -> None:
        sentinel = self.root / "delayed-child.txt"
        child = (
            "import pathlib,sys,time; time.sleep(0.8); "
            "pathlib.Path(sys.argv[1]).write_text('invoked', encoding='utf-8')"
        )
        parent = (
            "import subprocess,sys,time; "
            f"subprocess.Popen([sys.executable, '-c', {child!r}, sys.argv[1]]); "
            "time.sleep(30)"
        )
        with patch("academy_engine.command._COMMAND_TIMEOUT_SECONDS", 0.1):
            with self.assertRaisesRegex(GitCommandError, "bounded timeout"):
                _run(
                    [sys.executable, "-c", parent, str(sentinel)],
                    cwd=self.root,
                    check=False,
                )
        time.sleep(1.0)
        self.assertFalse(sentinel.exists())

    def test_cleanup_terminates_descendants_after_the_leader_exits_first(self) -> None:
        sentinel = self.root / "orphaned-child.txt"
        child = (
            "import pathlib,sys,time; time.sleep(0.8); "
            "pathlib.Path(sys.argv[1]).write_text('invoked', encoding='utf-8')"
        )
        parent = (
            "import subprocess,sys; "
            f"subprocess.Popen([sys.executable, '-c', {child!r}, sys.argv[1]])"
        )

        _run(
            [sys.executable, "-c", parent, str(sentinel)],
            cwd=self.root,
            check=False,
        )
        time.sleep(1.0)

        self.assertFalse(sentinel.exists())

    @unittest.skipUnless(os.name == "nt", "Windows Job Object startup regression")
    def test_windows_child_cannot_spawn_before_job_assignment(self) -> None:
        sentinel = self.root / "pre-assignment-child.txt"
        child = (
            "import pathlib,sys; "
            "pathlib.Path(sys.argv[1]).write_text('invoked', encoding='utf-8')"
        )
        parent = (
            "import subprocess,sys,time; "
            f"subprocess.Popen([sys.executable, '-c', {child!r}, sys.argv[1]]); "
            "time.sleep(0.1)"
        )
        observed_before_assignment: list[bool] = []
        assign = command_module._assign_windows_job

        def delayed_assignment(process):
            time.sleep(0.4)
            observed_before_assignment.append(sentinel.exists())
            return assign(process)

        with patch(
            "academy_engine.command._assign_windows_job",
            side_effect=delayed_assignment,
        ):
            _run(
                [sys.executable, "-c", parent, str(sentinel)],
                cwd=self.root,
                check=False,
            )

        self.assertEqual(observed_before_assignment, [False])

    def test_repository_discovery_does_not_trust_core_worktree_redirection(self) -> None:
        sibling = self.root.parent / "redirected-worktree"
        sibling.mkdir()
        git(self.root, "config", "core.worktree", sibling.as_posix())

        self.assertEqual(
            command_module.repository_root(self.root / "nested"),
            self.root.resolve(),
        )
        with self.assertRaisesRegex(GitCommandError, "unsafe local Git configuration"):
            command_module.validate_repository_git_config(self.root / "nested")

    def test_repository_fsmonitor_helper_is_not_executed(self) -> None:
        sentinel = self.root / "fsmonitor-invoked.txt"
        helper = self.root / "malicious-fsmonitor.cmd"
        helper.write_text(
            f"@echo off\r\ntype nul > \"{sentinel}\"\r\n",
            encoding="utf-8",
        )
        git(self.root, "config", "core.fsmonitor", helper.as_posix())
        git(self.root, "config", "academy.safe", "visible")

        with self.assertRaisesRegex(GitCommandError, "unsafe local Git configuration"):
            run_git(self.root, ["status", "--porcelain", "--untracked-files=all"])
        self.assertFalse(sentinel.exists())
        self.assertEqual(
            run_git(self.root, ["config", "--get", "academy.safe"]).stdout.strip(),
            "visible",
        )

    def test_authoritative_config_rejects_clean_filter_without_launching_it(self) -> None:
        sentinel = self.root / "clean-filter-invoked.txt"
        helper = self.root / "malicious-clean-filter.cmd"
        helper.write_text(
            f"@echo off\r\ntype nul > \"{sentinel}\"\r\nmore\r\n",
            encoding="utf-8",
        )
        (self.root / ".gitattributes").write_text("*.txt filter=attack\n", encoding="utf-8")
        git(self.root, "config", "filter.attack.clean", helper.as_posix())

        with self.assertRaisesRegex(GitCommandError, "unsafe local Git configuration"):
            command_module.validate_repository_git_config(self.root)
        self.assertFalse(
            evaluate_checkpoint(self.root, "F01-fork-clone-doctor").passed
        )

        self.assertFalse(sentinel.exists())

    def test_authoritative_config_rejects_unknown_keys_but_allows_core_remote_branch(self) -> None:
        git(self.root, "remote", "add", "origin", "https://github.com/learner/arbiter-academy.git")
        git(self.root, "config", "branch.main.remote", "origin")
        command_module.validate_repository_git_config(self.root)
        git(self.root, "config", "academy.unknown", "value")

        with self.assertRaisesRegex(GitCommandError, "unsafe local Git configuration"):
            command_module.validate_repository_git_config(self.root)

    def test_authoritative_config_rejects_worktree_config_scope(self) -> None:
        sentinel = self.root / "worktree-filter-invoked.txt"
        helper = self.root / "worktree-filter.cmd"
        helper.write_text(
            f"@echo off\r\ntype nul > \"{sentinel}\"\r\nmore\r\n",
            encoding="utf-8",
        )
        git(self.root, "config", "extensions.worktreeConfig", "true")
        git(self.root, "config", "--worktree", "filter.attack.clean", helper.as_posix())

        with self.assertRaisesRegex(GitCommandError, "unsafe local Git configuration"):
            command_module.validate_repository_git_config(self.root)
        self.assertFalse(sentinel.exists())
