from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from academy_engine.update import UpdateError, update_academy
from tests.test_scenario import git


class UpdateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.official = self.root / "official.git"
        self.fork = self.root / "fork.git"
        self.seed = self.root / "seed"
        self.learner = self.root / "learner"
        self.seed.mkdir()
        git(self.seed, "init", "-b", "main")
        git(self.seed, "config", "user.name", "Academy")
        git(self.seed, "config", "user.email", "academy@example.test")
        (self.seed / "README.md").write_text("one\n", encoding="utf-8")
        git(self.seed, "add", ".")
        git(self.seed, "commit", "-m", "one")
        git(self.root, "clone", "--bare", str(self.seed), str(self.official))
        git(self.root, "clone", "--bare", str(self.seed), str(self.fork))
        git(self.root, "clone", str(self.fork), str(self.learner))
        git(self.learner, "remote", "set-url", "origin", "https://github.com/learner/arbiter-academy.git")
        git(self.learner, "remote", "add", "upstream", "git@github.com:arbiterForge/arbiter-academy.git")
        git(self.learner, "remote", "set-url", "--push", "upstream", "DISABLED")
        helper = self.root / "academy_ssh.py"
        helper.write_text(
            "import subprocess, sys\n"
            "repository = sys.argv[1]\n"
            "command = sys.argv[-1]\n"
            "if not command.startswith('git-upload-pack '): raise SystemExit(2)\n"
            "raise SystemExit(subprocess.run(['git', 'upload-pack', repository]).returncode)\n",
            encoding="utf-8",
        )
        git(self.learner, "config", "core.sshCommand", f'\"{sys.executable}\" \"{helper}\" \"{self.official}\"')

    def test_update_fast_forwards_only_base_and_preserves_attempt_refs(self) -> None:
        git(self.seed, "remote", "add", "origin", str(self.official))
        (self.seed / "README.md").write_text("two\n", encoding="utf-8")
        git(self.seed, "commit", "-am", "two")
        git(self.seed, "push", "origin", "main")
        baseline = git(self.learner, "rev-parse", "HEAD")
        git(self.learner, "branch", "academy/F01-fork-clone-doctor/1", baseline)
        report = update_academy(self.learner)
        self.assertTrue(report.advanced)
        self.assertEqual(git(self.learner, "rev-parse", "academy/F01-fork-clone-doctor/1"), baseline)
        self.assertEqual(report.after_sha, git(self.learner, "rev-parse", "HEAD"))

    def test_update_reports_noop_and_refuses_divergence_or_non_base_state(self) -> None:
        report = update_academy(self.learner)
        self.assertFalse(report.advanced)
        git(self.learner, "config", "user.name", "Learner")
        git(self.learner, "config", "user.email", "learner@example.test")
        (self.learner / "local.txt").write_text("local\n", encoding="utf-8")
        git(self.learner, "add", ".")
        git(self.learner, "commit", "-m", "local")
        before = git(self.learner, "rev-parse", "HEAD")
        with self.assertRaisesRegex(UpdateError, "fast-forward"):
            update_academy(self.learner)
        self.assertEqual(git(self.learner, "rev-parse", "HEAD"), before)
