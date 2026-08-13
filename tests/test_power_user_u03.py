from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from academy_engine.checkpoints import Predicate, _Attempt, _SemanticContext, _remote_safe, _semantic
from academy_engine.scenario import prepare_lab


SOURCE = Path(__file__).resolve().parents[1]


def git(root: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments],
        cwd=root,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=True,
    )
    return result.stdout.strip()


class PrivateU03CheckpointTests(unittest.TestCase):
    """Private, Git-backed evidence boundaries for the U03 release exercise."""

    _SCENARIO_PATH = "training_scenarios/U03-refactor-chore-release.json"
    _CODE = "workshop_queue/store.py"
    _TEST = "tests/test_store.py"
    _CHORE = "README.md"
    _CHANGELOG = "CHANGELOG.md"
    _TARGETS = ".codearbiter/release-targets.md"
    _TARGET = "academy-private-training"
    _VERSION = "0.0.1"
    _TAG = "academy-v0.0.1"
    _DATE = "2026-08-13"

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "learner"
        self.root.mkdir()
        (self.root / ".codearbiter").mkdir()
        (self.root / ".codearbiter/CONTEXT.md").write_text("stage: 2\n", encoding="utf-8")
        (self.root / "workshop_queue").mkdir()
        (self.root / "tests").mkdir()
        (self.root / self._CODE).write_text("def read_ticket():\n    return 'open'\n", encoding="utf-8")
        (self.root / self._TEST).write_text("def test_read_ticket_parity():\n    assert True\n", encoding="utf-8")
        (self.root / self._CHORE).write_text("# Workshop Queue\n", encoding="utf-8")
        git(self.root, "init", "-b", "main")
        git(self.root, "config", "user.name", "Academy Learner")
        git(self.root, "config", "user.email", "learner@example.test")
        git(self.root, "add", ".")
        git(self.root, "commit", "-m", "base")
        self.base = git(self.root, "rev-parse", "HEAD")
        git(self.root, "remote", "add", "origin", "https://github.com/learner/arbiter-academy.git")
        git(self.root, "remote", "add", "upstream", "https://github.com/arbiterForge/arbiter-academy.git")
        git(self.root, "remote", "set-url", "--push", "upstream", "DISABLED")
        self.branch = "academy/U03-refactor-chore-release/1"
        git(self.root, "switch", "-c", self.branch)
        self._write_brief()
        self.prepared = self._commit("prepare private U03 brief", self._SCENARIO_PATH, self._TARGETS)

    def _write_brief(self) -> None:
        payload = {
            "schema_version": 2,
            "lab_id": "U03-refactor-chore-release",
            "operation": "refactor_chore_release",
            "starting_condition": "first-release",
            "refactor": {"code_path": self._CODE, "test_path": self._TEST},
            "chore": {"path": self._CHORE},
            "release": {
                "target": self._TARGET,
                "version": self._VERSION,
                "tag": self._TAG,
                "changelog": self._CHANGELOG,
            },
        }
        path = self.root / self._SCENARIO_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
        (self.root / self._TARGETS).write_text(
            "<!-- release-targets -->\n[academy-private-training]\nprefix: academy-v\n"
            "changelog: CHANGELOG.md\npayload: .\n<!-- /release-targets -->\n",
            encoding="utf-8",
        )

    def _section(self) -> str:
        return (
            f"## [{self._VERSION}] — {self._DATE}\n\n### Changed\n\n"
            "- Preserve ticket-read behavior while clarifying its boundary.\n"
        )

    def _tag_message(self) -> str:
        return f"{self._section()}\nReleased-at: {self._DATE}\n"

    def _commit(self, message: str, *paths: str) -> str:
        git(self.root, "add", "--", *paths)
        git(self.root, "commit", "-m", message)
        return git(self.root, "rev-parse", "HEAD")

    def _complete_three_commit_attempt(self, *, mutate_test: bool = False, extra_path: bool = False) -> str:
        (self.root / self._CODE).write_text("def read_ticket():\n    return 'open'  # refactored\n", encoding="utf-8")
        paths = [self._CODE]
        if mutate_test:
            (self.root / self._TEST).write_text("def test_read_ticket_parity():\n    assert 'open' == 'open'\n", encoding="utf-8")
            paths.append(self._TEST)
        if extra_path:
            (self.root / "unapproved.txt").write_text("outside the brief\n", encoding="utf-8")
            paths.append("unapproved.txt")
        self._commit(
            "refactor: clarify store boundary\n\n"
            "CHANGELOG: Preserve ticket-read behavior while clarifying its boundary.",
            *paths,
        )
        (self.root / self._CHORE).write_text("# Workshop Queue\n\nPrivate Academy release note.\n", encoding="utf-8")
        self._commit("docs: document approved release note", self._CHORE)
        (self.root / self._CHANGELOG).write_text("# Changelog\n\n" + self._section(), encoding="utf-8")
        return self._commit("chore: prepare academy release", self._CHANGELOG)

    def _context(self, head: str) -> _SemanticContext:
        return _SemanticContext(
            self.root,
            _Attempt(self.branch, 1, self.prepared, self.base, head),
            Predicate(
                "refactor_chore_release",
                "lab_semantics",
                {
                    "profile": "refactor_chore_release",
                    "scenario": self._SCENARIO_PATH,
                    "code": self._CODE,
                    "test": self._TEST,
                    "chore": self._CHORE,
                    "release_target": self._TARGET,
                    "release_version": self._VERSION,
                    "release_tag": self._TAG,
                    "release_changelog": self._CHANGELOG,
                    "release_targets": self._TARGETS,
                },
            ),
        )

    def test_rejects_a_lightweight_tag_even_when_legacy_path_checks_pass(self) -> None:
        """Catches accepting `git tag academy-v*` as release evidence."""
        head = self._complete_three_commit_attempt()
        git(self.root, "tag", self._TAG, head)

        self.assertTrue(_remote_safe(self.root))
        self.assertFalse(_semantic(self._context(head)))

    def test_accepts_only_the_declared_annotated_tag_on_a_bounded_clean_attempt(self) -> None:
        """Catches a verifier that cannot accept the intended private evidence boundary."""
        head = self._complete_three_commit_attempt()
        message = Path(self.temporary.name) / "tag-message.txt"
        message.write_text(self._tag_message(), encoding="utf-8")
        git(self.root, "tag", "-a", self._TAG, "-F", str(message), "--cleanup=verbatim", head)

        self.assertTrue(_semantic(self._context(head)))

    def test_rejects_an_annotated_tag_with_extra_blank_content_after_the_message(self) -> None:
        """Catches stripping extra blank tag-body content from an otherwise exact message."""
        head = self._complete_three_commit_attempt()
        message = Path(self.temporary.name) / "tag-message.txt"
        message.write_text(self._tag_message(), encoding="utf-8")
        git(self.root, "tag", "-a", self._TAG, "-F", str(message), "--cleanup=verbatim", head)
        tag_object = subprocess.run(
            ["git", "cat-file", "tag", self._TAG],
            cwd=self.root,
            capture_output=True,
            check=True,
        ).stdout + b"\n"
        object_id = subprocess.run(
            ["git", "mktag"],
            cwd=self.root,
            input=tag_object,
            capture_output=True,
            check=True,
        ).stdout.decode("ascii").strip()
        git(self.root, "update-ref", f"refs/tags/{self._TAG}", object_id)

        self.assertFalse(_semantic(self._context(head)))

    def test_rejects_an_annotated_tag_for_a_different_declared_release(self) -> None:
        """Catches accepting a well-formed tag that does not name the prepared release."""
        head = self._complete_three_commit_attempt()
        git(self.root, "tag", "-a", "academy-v9.9.9", "-m", "wrong", head)

        self.assertFalse(_semantic(self._context(head)))

    def test_rejects_chore_before_refactor(self) -> None:
        """Catches accepting the right paths when the governed order is reversed."""
        (self.root / self._CHORE).write_text("# Workshop Queue\n\nPrivate Academy release note.\n", encoding="utf-8")
        self._commit("document approved release note", self._CHORE)
        (self.root / self._CODE).write_text("def read_ticket():\n    return 'open'  # refactored\n", encoding="utf-8")
        self._commit(
            "refactor: clarify store boundary\n\n"
            "CHANGELOG: Preserve ticket-read behavior while clarifying its boundary.",
            self._CODE,
        )
        (self.root / self._CHANGELOG).write_text("# Changelog\n\n" + self._section(), encoding="utf-8")
        head = self._commit("chore: prepare academy release", self._CHANGELOG)
        message = Path(self.temporary.name) / "reversed-tag-message.txt"
        message.write_text(self._tag_message(), encoding="utf-8")
        git(self.root, "tag", "-a", self._TAG, "-F", str(message), "--cleanup=verbatim", head)

        self.assertFalse(_semantic(self._context(head)))

    def test_rejects_unapproved_path_inside_the_refactor_commit(self) -> None:
        """Catches accepting a lesson commit that changes files outside the prepared scope."""
        head = self._complete_three_commit_attempt(extra_path=True)
        git(self.root, "tag", "-a", self._TAG, "-m", self._tag_message(), head)

        self.assertFalse(_semantic(self._context(head)))

    def test_rejects_a_dirty_worktree_after_other_evidence_is_complete(self) -> None:
        """Catches treating committed evidence as sufficient when the learner state is dirty."""
        head = self._complete_three_commit_attempt()
        git(self.root, "tag", "-a", self._TAG, "-m", self._tag_message(), head)
        (self.root / "uncommitted.txt").write_text("not part of the attempt\n", encoding="utf-8")

        self.assertFalse(_semantic(self._context(head)))

    def test_rejects_a_changed_preexisting_parity_test(self) -> None:
        """Catches a refactor exercise that rewrites the baseline regression instead of preserving it."""
        head = self._complete_three_commit_attempt(mutate_test=True)
        git(self.root, "tag", "-a", self._TAG, "-m", self._tag_message(), head)

        self.assertFalse(_semantic(self._context(head)))

    def test_rejects_an_attempt_without_the_preexisting_parity_test(self) -> None:
        """Catches treating a missing test before and after the attempt as preserved evidence."""
        (self.root / self._TEST).unlink()
        self.prepared = self._commit("prepare U03 without parity fixture", self._TEST)
        head = self._complete_three_commit_attempt()
        git(self.root, "tag", "-a", self._TAG, "-m", self._tag_message(), head)

        self.assertFalse(_semantic(self._context(head)))

    def test_prepare_copies_the_declared_private_brief_before_work_starts(self) -> None:
        """Catches a U03 scenario that cannot drive the real release lane."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "learner"
            root.mkdir()
            shutil.copytree(SOURCE / "academy", root / "academy")
            shutil.copytree(SOURCE / ".codearbiter", root / ".codearbiter")
            (root / "workshop_queue").mkdir()
            (root / "tests").mkdir()
            (root / self._CODE).write_text("def read_ticket():\n    return 'open'\n", encoding="utf-8")
            (root / self._TEST).write_text("def test_read_ticket_parity():\n    assert True\n", encoding="utf-8")
            (root / self._CHORE).write_text("# Workshop Queue\n", encoding="utf-8")
            git(root, "init", "-b", "main")
            git(root, "config", "user.name", "Academy Learner")
            git(root, "config", "user.email", "learner@example.test")
            git(root, "add", ".")
            git(root, "commit", "-m", "base")
            git(root, "remote", "add", "origin", "https://github.com/learner/arbiter-academy.git")
            git(root, "remote", "add", "upstream", "https://github.com/arbiterForge/arbiter-academy.git")
            git(root, "remote", "set-url", "--push", "upstream", "DISABLED")

            prepared = prepare_lab(root, "U03-refactor-chore-release")
            brief = json.loads((root / self._SCENARIO_PATH).read_text(encoding="utf-8"))

            self.assertEqual(prepared.branch, self.branch)
            self.assertEqual(brief["refactor"], {"code_path": self._CODE, "test_path": self._TEST})
            self.assertEqual(brief["chore"], {"path": self._CHORE})
            targets = (root / ".codearbiter/release-targets.md").read_text(encoding="utf-8")
            self.assertIn("<!-- release-targets -->", targets)
            self.assertIn("[academy-private-training]", targets)
            self.assertIn("prefix: academy-v", targets)
            self.assertIn("changelog: CHANGELOG.md", targets)
            self.assertIn("payload: .", targets)
            self.assertEqual(
                brief["release"],
                {
                    "target": self._TARGET,
                    "version": "0.0.1",
                    "tag": "academy-v0.0.1",
                    "changelog": "CHANGELOG.md",
                },
            )


if __name__ == "__main__":
    unittest.main()
