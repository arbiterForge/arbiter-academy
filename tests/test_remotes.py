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
LEARNER = "https://github.com/learner/arbiter-academy.git"
PUSH_DISABLED = "DISABLED"


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

    def test_rejects_every_c0_control_and_del_before_parsing(self) -> None:
        canonical = "https://github.com/learner/arbiter-academy.git"
        for codepoint in (*range(0x20), 0x7F):
            with self.subTest(codepoint=codepoint):
                control = chr(codepoint)
                for url in (
                    control + canonical,
                    f"https://git{control}hub.com/learner/arbiter-academy.git",
                    f"https://github.com/learner/arbiter{control}-academy.git",
                ):
                    with self.assertRaisesRegex(RemoteSafetyError, "GitHub remote"):
                        normalize_github_remote(url)

    def test_normalizes_urlsplit_value_errors_to_remote_safety_errors(self) -> None:
        for url in (
            "https://[github.com/learner/arbiter-academy.git",
            "https://github.com:invalid/learner/arbiter-academy.git",
            "https://github.com\uFF0Flearner/arbiter-academy.git",
        ):
            with self.subTest(url=url):
                try:
                    normalize_github_remote(url)
                except RemoteSafetyError as error:
                    self.assertIn("GitHub remote", str(error))
                except ValueError as error:
                    self.fail(f"parser leaked ValueError instead of RemoteSafetyError: {error}")
                else:
                    self.fail("malformed URL was accepted")


class ValidateTrainingRemotesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name) / "repository"
        self.root.mkdir()
        git(self.root, "init")

    def set_remotes(
        self,
        origin: str | None,
        upstream: str | None,
        *,
        disable_upstream_push: bool = True,
    ) -> None:
        if origin is not None:
            git(self.root, "remote", "add", "origin", origin)
        if upstream is not None:
            git(self.root, "remote", "add", "upstream", upstream)
            if disable_upstream_push:
                git(self.root, "remote", "set-url", "--push", "upstream", PUSH_DISABLED)

    def test_push_training_rejects_official_origin(self) -> None:
        self.set_remotes("git@github.com:arbiterForge/arbiter-academy.git", OFFICIAL)

        with self.assertRaisesRegex(RemoteSafetyError, "non-official same-name"):
            validate_training_remotes(self.root, require_push_safe=True)

    def test_push_training_accepts_a_fork_compatible_origin_and_disabled_official_upstream(self) -> None:
        self.set_remotes("git@github.com:learner/arbiter-academy.git", "ssh://git@github.com/arbiterForge/arbiter-academy.git")

        report = validate_training_remotes(self.root, require_push_safe=True)

        self.assertTrue(report.push_safe)
        self.assertEqual(report.origin, GitHubRemote("learner", "arbiter-academy"))
        self.assertTrue(report.upstream.is_official)
        self.assertTrue(getattr(report, "upstream_push_disabled", False))
        self.assertEqual(getattr(report, "effective_push_remote", None), "origin")
        self.assertFalse(getattr(report, "lineage_verified_offline", True))

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
                    git(root, "remote", "set-url", "--push", "upstream", PUSH_DISABLED)
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
                    git(root, "remote", "set-url", "--push", "upstream", PUSH_DISABLED)
                    with self.assertRaisesRegex(RemoteSafetyError, "GitHub remote"):
                        validate_training_remotes(root, require_push_safe=True)

    def test_rejects_official_origin_pushurl_with_learner_fetch_url(self) -> None:
        self.set_remotes(LEARNER, OFFICIAL)
        git(self.root, "remote", "set-url", "--push", "origin", OFFICIAL)

        with self.assertRaisesRegex(RemoteSafetyError, "origin push"):
            validate_training_remotes(self.root, require_push_safe=True)

    def test_rejects_any_unsafe_origin_target_among_multiple_pushurls(self) -> None:
        self.set_remotes(LEARNER, OFFICIAL)
        git(self.root, "remote", "set-url", "--push", "origin", LEARNER)
        git(self.root, "remote", "set-url", "--add", "--push", "origin", OFFICIAL)

        with self.assertRaisesRegex(RemoteSafetyError, "origin push"):
            validate_training_remotes(self.root, require_push_safe=True)

    def test_rejects_origin_pushurl_for_a_different_nonofficial_owner(self) -> None:
        self.set_remotes(LEARNER, OFFICIAL)
        git(
            self.root,
            "remote",
            "set-url",
            "--push",
            "origin",
            "https://github.com/other-learner/arbiter-academy.git",
        )

        with self.assertRaisesRegex(RemoteSafetyError, "match origin"):
            validate_training_remotes(self.root, require_push_safe=True)

    def test_rejects_official_upstream_without_explicit_push_disable(self) -> None:
        self.set_remotes(LEARNER, OFFICIAL, disable_upstream_push=False)

        with self.assertRaisesRegex(RemoteSafetyError, "DISABLED"):
            validate_training_remotes(self.root, require_push_safe=True)

    def test_rejects_any_nondisabled_upstream_target(self) -> None:
        self.set_remotes(LEARNER, OFFICIAL)
        git(self.root, "remote", "set-url", "--add", "--push", "upstream", OFFICIAL)

        with self.assertRaisesRegex(RemoteSafetyError, "DISABLED"):
            validate_training_remotes(self.root, require_push_safe=True)

    def test_branch_push_remote_must_resolve_to_origin(self) -> None:
        self.set_remotes(LEARNER, OFFICIAL)
        branch = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=self.root,
            check=True,
            text=True,
            capture_output=True,
        ).stdout.strip()
        git(self.root, "config", f"branch.{branch}.pushRemote", "upstream")

        with self.assertRaisesRegex(RemoteSafetyError, "push routing"):
            validate_training_remotes(self.root, require_push_safe=True)

    def test_remote_push_default_must_resolve_to_origin(self) -> None:
        self.set_remotes(LEARNER, OFFICIAL)
        git(self.root, "config", "remote.pushDefault", "upstream")

        with self.assertRaisesRegex(RemoteSafetyError, "push routing"):
            validate_training_remotes(self.root, require_push_safe=True)

    def test_branch_push_remote_takes_precedence_over_safe_remote_default(self) -> None:
        self.set_remotes(LEARNER, OFFICIAL)
        branch = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=self.root,
            check=True,
            text=True,
            capture_output=True,
        ).stdout.strip()
        git(self.root, "config", f"branch.{branch}.pushRemote", "upstream")
        git(self.root, "config", "remote.pushDefault", "origin")
        git(self.root, "config", f"branch.{branch}.remote", "origin")

        with self.assertRaisesRegex(RemoteSafetyError, "push routing"):
            validate_training_remotes(self.root, require_push_safe=True)

    def test_safe_branch_push_remote_overrides_unsafe_lower_precedence_routes(self) -> None:
        self.set_remotes(LEARNER, OFFICIAL)
        branch = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=self.root,
            check=True,
            text=True,
            capture_output=True,
        ).stdout.strip()
        git(self.root, "config", f"branch.{branch}.pushRemote", "origin")
        git(self.root, "config", "remote.pushDefault", "upstream")
        git(self.root, "config", f"branch.{branch}.remote", "upstream")

        report = validate_training_remotes(self.root, require_push_safe=True)

        self.assertEqual(report.effective_push_remote, "origin")

    def test_remote_push_default_takes_precedence_over_branch_remote(self) -> None:
        self.set_remotes(LEARNER, OFFICIAL)
        branch = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=self.root,
            check=True,
            text=True,
            capture_output=True,
        ).stdout.strip()
        git(self.root, "config", "remote.pushDefault", "origin")
        git(self.root, "config", f"branch.{branch}.remote", "upstream")

        report = validate_training_remotes(self.root, require_push_safe=True)

        self.assertEqual(report.effective_push_remote, "origin")

    def test_branch_remote_fallback_must_resolve_to_origin(self) -> None:
        self.set_remotes(LEARNER, OFFICIAL)
        branch = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=self.root,
            check=True,
            text=True,
            capture_output=True,
        ).stdout.strip()
        git(self.root, "config", f"branch.{branch}.remote", "upstream")

        with self.assertRaisesRegex(RemoteSafetyError, "push routing"):
            validate_training_remotes(self.root, require_push_safe=True)

    def test_default_origin_routing_is_safe_without_branch_push_config(self) -> None:
        self.set_remotes(LEARNER, OFFICIAL)

        report = validate_training_remotes(self.root, require_push_safe=True)

        self.assertEqual(getattr(report, "effective_push_remote", None), "origin")

    def test_read_only_orientation_reports_an_unsafe_configuration_without_raising(self) -> None:
        self.set_remotes(OFFICIAL, None)

        report = validate_training_remotes(self.root, require_push_safe=False)

        self.assertFalse(report.push_safe)
        self.assertIn("non-official same-name", " ".join(report.issues).lower())

    def test_push_training_rejects_missing_or_malformed_remotes(self) -> None:
        self.set_remotes("https://github.com/learner/arbiter-academy.git?bad=1", None)

        with self.assertRaisesRegex(RemoteSafetyError, "upstream|GitHub remote"):
            validate_training_remotes(self.root, require_push_safe=True)

    def test_push_training_rejects_an_origin_for_another_repository(self) -> None:
        self.set_remotes("https://github.com/learner/not-arbiter-academy.git", OFFICIAL)

        with self.assertRaisesRegex(RemoteSafetyError, "same-name"):
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
