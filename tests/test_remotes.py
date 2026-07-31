"""Real-Git remote validation checks for fork-first Academy labs."""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from academy_engine.remotes import (
    GitHubRemote,
    RemoteSafetyError,
    normalize_github_remote,
    validate_training_remotes,
)


OFFICIAL = "https://github.com/arbiterForge/arbiter-academy.git"


def git(directory: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=directory, check=True, text=True, capture_output=True)


class NormalizeGitHubRemoteTests(unittest.TestCase):
    def test_recognizes_canonical_github_forms(self) -> None:
        expected = GitHubRemote(owner="arbiterForge", repository="arbiter-academy")
        for url in (
            "https://github.com/arbiterForge/arbiter-academy.git",
            "ssh://git@github.com/arbiterForge/arbiter-academy.git",
            "git@github.com:arbiterForge/arbiter-academy.git",
        ):
            with self.subTest(url=url):
                self.assertEqual(normalize_github_remote(url), expected)

    def test_compares_identity_case_insensitively_and_trims_one_git_suffix(self) -> None:
        remote = normalize_github_remote("https://github.com/ARBITERforge/ARBITER-academy.GIT")

        self.assertTrue(remote.matches("arbiterForge", "arbiter-academy"))

    def test_rejects_ambiguous_or_noncanonical_remote_urls(self) -> None:
        for url in (
            "https://user:token@github.com/learner/arbiter-academy.git",
            "https://github.com/learner/arbiter-academy.git?view=1",
            "https://github.com/learner/arbiter-academy.git#readme",
            "https://github.com/learner/../arbiter-academy.git",
            "https://github.com/learner%2Fother/arbiter-academy.git",
            "https://github.com/learner/arbiter-academy/extra.git",
            "https://example.com/learner/arbiter-academy.git",
            "git@github.com:learner/arbiter-academy.git.git",
        ):
            with self.subTest(url=url):
                with self.assertRaisesRegex(RemoteSafetyError, "GitHub remote"):
                    normalize_github_remote(url)


class ValidateTrainingRemotesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name) / "repository"
        self.root.mkdir()
        git(self.root, "init")

    def set_remotes(self, origin: str | None, upstream: str | None) -> None:
        if origin is not None:
            git(self.root, "remote", "add", "origin", origin)
        if upstream is not None:
            git(self.root, "remote", "add", "upstream", upstream)

    def test_push_training_rejects_official_origin(self) -> None:
        self.set_remotes("git@github.com:arbiterForge/arbiter-academy.git", OFFICIAL)

        with self.assertRaisesRegex(RemoteSafetyError, "fork"):
            validate_training_remotes(self.root, require_push_safe=True)

    def test_push_training_accepts_a_learner_fork_and_official_upstream(self) -> None:
        self.set_remotes("git@github.com:learner/arbiter-academy.git", "ssh://git@github.com/arbiterForge/arbiter-academy.git")

        report = validate_training_remotes(self.root, require_push_safe=True)

        self.assertTrue(report.push_safe)
        self.assertEqual(report.origin, GitHubRemote("learner", "arbiter-academy"))
        self.assertTrue(report.upstream.is_official)

    def test_real_git_remotes_accept_each_canonical_github_form(self) -> None:
        forms = (
            ("https://github.com/learner/arbiter-academy.git", "https://github.com/arbiterForge/arbiter-academy.git"),
            ("ssh://git@github.com/learner/arbiter-academy.git", "ssh://git@github.com/arbiterForge/arbiter-academy.git"),
            ("git@github.com:learner/arbiter-academy.git", "git@github.com:arbiterForge/arbiter-academy.git"),
        )
        for origin, upstream in forms:
            with self.subTest(origin=origin):
                with tempfile.TemporaryDirectory() as temporary_directory:
                    root = Path(temporary_directory)
                    git(root, "init")
                    git(root, "remote", "add", "origin", origin)
                    git(root, "remote", "add", "upstream", upstream)
                    self.assertTrue(validate_training_remotes(root, require_push_safe=True).push_safe)

    def test_real_git_remotes_reject_noncanonical_urls(self) -> None:
        malformed = (
            "https://user:token@github.com/learner/arbiter-academy.git",
            "https://github.com/learner/arbiter-academy.git?view=1",
            "https://github.com/learner/arbiter-academy.git#readme",
            "https://github.com/learner/../arbiter-academy.git",
            "https://github.com/learner%2Fother/arbiter-academy.git",
            "https://github.com/learner/arbiter-academy/extra.git",
            "https://example.com/learner/arbiter-academy.git",
            "git@github.com:learner/arbiter-academy.git.git",
        )
        for origin in malformed:
            with self.subTest(origin=origin):
                with tempfile.TemporaryDirectory() as temporary_directory:
                    root = Path(temporary_directory)
                    git(root, "init")
                    git(root, "remote", "add", "origin", origin)
                    git(root, "remote", "add", "upstream", OFFICIAL)
                    with self.assertRaisesRegex(RemoteSafetyError, "GitHub remote"):
                        validate_training_remotes(root, require_push_safe=True)

    def test_read_only_orientation_reports_an_unsafe_configuration_without_raising(self) -> None:
        self.set_remotes(OFFICIAL, None)

        report = validate_training_remotes(self.root, require_push_safe=False)

        self.assertFalse(report.push_safe)
        self.assertIn("fork", " ".join(report.issues).lower())

    def test_push_training_rejects_missing_or_malformed_remotes(self) -> None:
        self.set_remotes("https://github.com/learner/arbiter-academy.git?bad=1", None)

        with self.assertRaisesRegex(RemoteSafetyError, "upstream|GitHub remote"):
            validate_training_remotes(self.root, require_push_safe=True)

    def test_push_training_rejects_an_origin_for_another_repository(self) -> None:
        self.set_remotes("https://github.com/learner/not-arbiter-academy.git", OFFICIAL)

        with self.assertRaisesRegex(RemoteSafetyError, "fork"):
            validate_training_remotes(self.root, require_push_safe=True)

    def test_push_training_rejects_a_nonofficial_upstream(self) -> None:
        self.set_remotes("https://github.com/learner/arbiter-academy.git", "https://github.com/learner/arbiter-academy.git")

        with self.assertRaisesRegex(RemoteSafetyError, "upstream"):
            validate_training_remotes(self.root, require_push_safe=True)

    def test_push_training_rejects_a_missing_origin(self) -> None:
        self.set_remotes(None, OFFICIAL)

        with self.assertRaisesRegex(RemoteSafetyError, "origin remote is missing"):
            validate_training_remotes(self.root, require_push_safe=True)

    def test_push_training_rejects_a_missing_upstream(self) -> None:
        self.set_remotes("https://github.com/learner/arbiter-academy.git", None)

        with self.assertRaisesRegex(RemoteSafetyError, "upstream remote is missing"):
            validate_training_remotes(self.root, require_push_safe=True)
