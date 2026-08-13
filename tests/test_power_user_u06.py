from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

import academy_engine.checkpoints as checkpoints_module
from academy_engine.checkpoints import (
    _Attempt,
    _SemanticContext,
    _commit_paths,
    _exact_two_commit_range,
    _semantic,
    load_checkpoint,
)
from academy_engine.scenario import PreparationError, prepare_lab
from tests._temporary import RetryingTemporaryDirectory


SOURCE = Path(__file__).parents[1]
U06 = "U06-preview-and-advanced-surfaces"
CANDIDATE_PATH = "docs/U06-preview-candidate.md"
REPORT_PATH = ".codearbiter/reports/academy/U06-preview.json"
SEED_CANDIDATE = b"# U06 preview candidate\n\nThis draft is intentionally incomplete.\n"
SAFE_CANDIDATE = (
    b"# U06 preview candidate\n\n"
    b"## Read-only documentation policy\n\n"
    b"Preview may inspect the prepared attempt and report predicted reviewers. "
    b"It does not run a sandbox, create a skill, start watch, or convene a tribunal.\n\n"
    b"## Evidence\n\n"
    b"Record the reviewed commit, candidate tree, exact changed path, and a "
    b"repository bindings in the U06 Academy record.\n"
)


def git(root: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", *arguments],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


class PrivateU06CheckpointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = RetryingTemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "repository"
        self.root.mkdir()
        shutil.copytree(SOURCE / "academy", self.root / "academy")
        (self.root / ".gitignore").write_text(".academy/\n", encoding="utf-8")
        (self.root / "README.md").write_text("U06 fixture\n", encoding="utf-8")
        git(self.root, "init", "-b", "main")
        git(self.root, "config", "user.name", "U06 Fixture")
        git(self.root, "config", "user.email", "u06-fixture@example.invalid")
        git(self.root, "add", ".")
        git(self.root, "commit", "-m", "root base")
        git(self.root, "remote", "add", "origin", "https://github.com/learner/arbiter-academy.git")
        git(self.root, "remote", "add", "upstream", "https://github.com/arbiterForge/arbiter-academy.git")
        git(self.root, "remote", "set-url", "--push", "upstream", "DISABLED")

    def _complete_attempt(
        self,
        *,
        candidate_bytes: bytes = SAFE_CANDIDATE,
        candidate_extra_path: str | None = None,
        report_mutation=None,
        report_bytes: bytes | None = None,
        intermediate_path: str | None = None,
        expected_seed: bytes = SEED_CANDIDATE,
    ) -> _SemanticContext:
        prepared = prepare_lab(self.root, U06)
        self.assertEqual((self.root / CANDIDATE_PATH).read_bytes(), expected_seed)
        if intermediate_path is not None:
            intermediate = self.root / intermediate_path
            intermediate.parent.mkdir(parents=True, exist_ok=True)
            intermediate.write_text("intermediate\n", encoding="utf-8")
            git(self.root, "add", "--", intermediate_path)
            git(self.root, "commit", "-m", "write unrelated intermediate")
        candidate = self.root / CANDIDATE_PATH
        candidate.write_bytes(candidate_bytes)
        paths = [CANDIDATE_PATH]
        if candidate_extra_path is not None:
            extra = self.root / candidate_extra_path
            extra.parent.mkdir(parents=True, exist_ok=True)
            extra.write_text("unexpected\n", encoding="utf-8")
            paths.append(candidate_extra_path)
        git(self.root, "add", "--", *paths)
        git(self.root, "commit", "-m", "write U06 preview policy")
        candidate_commit = git(self.root, "rev-parse", "HEAD")
        candidate_tree = git(self.root, "rev-parse", "HEAD^{tree}")
        report = {
            "schema_version": 1,
            "prepared_commit": prepared.commit_sha,
            "candidate_commit": candidate_commit,
            "candidate_tree": candidate_tree,
            "candidate_path": CANDIDATE_PATH,
            "candidate_sha256": hashlib.sha256(candidate_bytes).hexdigest(),
            "changed_paths": [CANDIDATE_PATH],
            "read_only": True,
            "advanced_surfaces": {
                "ca-sandbox": "not-executed",
                "ca-new-skill": "not-executed",
                "ca-watch": "not-executed",
                "ca-tribunal": "not-executed",
            },
        }
        if report_mutation is not None:
            report_mutation(report)
        target = self.root / REPORT_PATH
        target.parent.mkdir(parents=True)
        target.write_bytes(
            report_bytes
            if report_bytes is not None
            else json.dumps(report, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
        )
        git(self.root, "add", "--", REPORT_PATH)
        git(self.root, "commit", "-m", "record U06 preview evidence")
        head = git(self.root, "rev-parse", "HEAD")
        predicate = load_checkpoint(SOURCE / "academy/checkpoints/U06-preview-and-advanced-surfaces.json").predicates[0]
        return _SemanticContext(
            self.root,
            _Attempt(prepared.branch, prepared.attempt, prepared.commit_sha, prepared.base_sha, head),
            predicate,
        )

    def test_accepts_exact_two_commit_preview_evidence(self) -> None:
        """Catches a preview record detached from the exact seeded candidate and two commits."""
        context = self._complete_attempt()
        self.assertEqual(
            git(self.root, "diff-tree", "--no-commit-id", "--name-only", "-r", context.attempt.prepared).splitlines(),
            [CANDIDATE_PATH, "training_scenarios/U06-preview-and-advanced-surfaces.json"],
        )
        self.assertTrue(_semantic(context))

    def test_rejects_candidate_with_wrong_parent_or_extra_changed_path(self) -> None:
        """Catches candidate evidence that is not the sole commit immediately after preparation."""
        context = self._complete_attempt(intermediate_path="docs/intermediate.md")
        self.assertFalse(_semantic(context))

    def test_rejects_candidate_commit_with_an_extra_path(self) -> None:
        """Catches unrelated content smuggled into the reviewed candidate commit."""
        context = self._complete_attempt(candidate_extra_path="docs/unrelated.md")
        self.assertFalse(_semantic(context))

    def test_rejects_wrong_candidate_tree_malformed_report_and_invented_preview_telemetry(self) -> None:
        """Catches forged bindings and telemetry a read-only ca-preview cannot persist."""
        cases = (
            ("wrong-tree", lambda report: report.update(candidate_tree="0" * 40), None),
            ("malformed", None, b"{"),
            ("invented-preview-telemetry", lambda report: report.update(predicted_reviewers=[]), None),
            ("missing-surface", lambda report: report["advanced_surfaces"].pop("ca-watch"), None),
        )
        for name, mutate, raw in cases:
            with self.subTest(name=name):
                self.temporary.cleanup()
                self.setUp()
                context = self._complete_attempt(report_mutation=mutate, report_bytes=raw)
                self.assertFalse(_semantic(context))

    def test_rejects_altered_seed_final_secret_dirty_and_later_history(self) -> None:
        """Catches changed fixture bytes, secret material, uncommitted state, and later history."""
        cases = (
            ("altered-final", SAFE_CANDIDATE + b"Unexpected policy.\n", None),
            ("secret", SAFE_CANDIDATE + b"to" + b"ken = " + b"gh" + b"p_abcdefghijklmnopqrstuvwx\n", None),
            ("dirty", SAFE_CANDIDATE, "dirty.txt"),
        )
        for name, candidate, dirty in cases:
            with self.subTest(name=name):
                self.temporary.cleanup()
                self.setUp()
                context = self._complete_attempt(candidate_bytes=candidate)
                if dirty is not None:
                    (self.root / dirty).write_text("untracked\n", encoding="utf-8")
                self.assertFalse(_semantic(context))
        self.temporary.cleanup()
        self.setUp()
        context = self._complete_attempt()
        (self.root / "docs" / "later.md").write_text("later\n", encoding="utf-8")
        git(self.root, "add", "--", "docs/later.md")
        git(self.root, "commit", "-m", "later change")
        self.assertFalse(
            _semantic(
                _SemanticContext(
                    self.root,
                    _Attempt(
                        context.attempt.branch,
                        context.attempt.number,
                        context.attempt.prepared,
                        context.attempt.base,
                        git(self.root, "rev-parse", "HEAD"),
                    ),
                    context.predicate,
                )
            )
        )

    def test_rejects_an_altered_scenario_seed(self) -> None:
        """Catches Prepare accepting a substituted U06 candidate seed."""
        seed = self.root / "academy/scenarios/U06-preview-and-advanced-surfaces/files/docs/U06-preview-candidate.md"
        seed.write_bytes(b"# U06 preview candidate\n\nSubstituted fixture.\n")
        git(self.root, "add", "--", "academy/scenarios/U06-preview-and-advanced-surfaces/files/docs/U06-preview-candidate.md")
        git(self.root, "commit", "-m", "replace U06 seed")
        before = git(self.root, "rev-parse", "HEAD")

        with self.assertRaisesRegex(PreparationError, "trusted protected overlay"):
            prepare_lab(self.root, U06)

        self.assertEqual(git(self.root, "rev-parse", "HEAD"), before)
        self.assertFalse(git(self.root, "branch", "--list", f"academy/{U06}/1"))
        self.assertFalse((self.root / CANDIDATE_PATH).exists())

    def test_fails_closed_when_git_status_cannot_determine_cleanliness(self) -> None:
        """Catches a failed cleanliness check being mistaken for an empty worktree."""
        context = self._complete_attempt()
        real_run_git = checkpoints_module.run_git

        def fail_status(repository: Path, arguments, **options):
            if arguments == ["status", "--porcelain", "--untracked-files=all"]:
                return subprocess.CompletedProcess(["git", *arguments], 1, "", "status unavailable")
            return real_run_git(repository, arguments, **options)

        with patch.object(checkpoints_module, "run_git", side_effect=fail_status):
            self.assertFalse(_semantic(context))

    def test_fails_closed_when_candidate_tree_resolution_fails(self) -> None:
        """Catches a failed tree query matching a forged empty report binding."""
        context = self._complete_attempt(
            report_mutation=lambda report: report.update(candidate_tree="")
        )
        real_run_git = checkpoints_module.run_git

        def fail_candidate_tree(repository: Path, arguments, **options):
            if arguments[0] == "rev-parse" and arguments[1].endswith("^{tree}"):
                return subprocess.CompletedProcess(["git", *arguments], 1, "", "tree unavailable")
            return real_run_git(repository, arguments, **options)

        with patch.object(checkpoints_module, "run_git", side_effect=fail_candidate_tree):
            self.assertFalse(_semantic(context))

    def test_rejects_assume_unchanged_candidate_worktree_drift(self) -> None:
        """Catches index flags hiding a candidate edit from porcelain status."""
        context = self._complete_attempt()
        try:
            git(self.root, "update-index", "--assume-unchanged", "--", CANDIDATE_PATH)
            (self.root / CANDIDATE_PATH).write_bytes(SAFE_CANDIDATE + b"Hidden worktree drift.\n")
            self.assertEqual(git(self.root, "status", "--porcelain"), "")
            self.assertFalse(_semantic(context))
        finally:
            git(self.root, "update-index", "--no-assume-unchanged", "--", CANDIDATE_PATH)

    def test_rejects_assume_unchanged_report_worktree_drift(self) -> None:
        """Catches index flags hiding an evidence-report edit from porcelain status."""
        context = self._complete_attempt()
        try:
            git(self.root, "update-index", "--assume-unchanged", "--", REPORT_PATH)
            (self.root / REPORT_PATH).write_bytes(b'{"forged":"report drift"}\n')
            self.assertEqual(git(self.root, "status", "--porcelain"), "")
            self.assertFalse(_semantic(context))
        finally:
            git(self.root, "update-index", "--no-assume-unchanged", "--", REPORT_PATH)

    def test_rejects_assume_unchanged_unrelated_tracked_worktree_drift(self) -> None:
        """Catches index flags hiding an unrelated tracked edit from porcelain status."""
        context = self._complete_attempt()
        try:
            git(self.root, "update-index", "--assume-unchanged", "--", "README.md")
            (self.root / "README.md").write_text("Hidden unrelated drift.\n", encoding="utf-8")
            self.assertEqual(git(self.root, "status", "--porcelain"), "")
            self.assertFalse(_semantic(context))
        finally:
            git(self.root, "update-index", "--no-assume-unchanged", "--", "README.md")


class ExactHistoryQueryTests(unittest.TestCase):
    def test_exact_two_commit_range_accepts_sha256_object_ids(self) -> None:
        """Catches a SHA-1-only history parser rejecting a SHA-256 repository."""
        prepared, candidate, head = "a" * 64, "b" * 64, "c" * 64

        def sha256_history(_root: Path, arguments, **_options):
            if arguments == ["rev-list", "--reverse", f"{prepared}..{head}"]:
                return subprocess.CompletedProcess(["git", *arguments], 0, f"{candidate}\n{head}\n", "")
            if arguments == ["rev-list", "--parents", "-n", "1", candidate]:
                return subprocess.CompletedProcess(["git", *arguments], 0, f"{candidate} {prepared}\n", "")
            if arguments == ["rev-list", "--parents", "-n", "1", head]:
                return subprocess.CompletedProcess(["git", *arguments], 0, f"{head} {candidate}\n", "")
            self.fail(f"unexpected Git query: {arguments}")

        with patch.object(checkpoints_module, "_repository_oid_pattern", return_value=checkpoints_module._SHA256), patch.object(
            checkpoints_module, "run_git", side_effect=sha256_history
        ):
            self.assertEqual(_exact_two_commit_range(Path("fixture"), prepared, head), (candidate, head))

    def test_exact_two_commit_range_rejects_parseable_parent_output_with_failure_status(self) -> None:
        """Catches a failed parent query being trusted solely because stdout looks valid."""
        prepared, candidate, head = "a" * 40, "b" * 40, "c" * 40

        def failed_parent(_root: Path, arguments, **_options):
            if arguments == ["rev-list", "--reverse", f"{prepared}..{head}"]:
                return subprocess.CompletedProcess(["git", *arguments], 0, f"{candidate}\n{head}\n", "")
            if arguments == ["rev-list", "--parents", "-n", "1", candidate]:
                return subprocess.CompletedProcess(["git", *arguments], 1, f"{candidate} {prepared}\n", "unavailable")
            self.fail(f"unexpected Git query: {arguments}")

        with patch.object(checkpoints_module, "_repository_oid_pattern", return_value=checkpoints_module._SHA40), patch.object(
            checkpoints_module, "run_git", side_effect=failed_parent
        ):
            self.assertIsNone(_exact_two_commit_range(Path("fixture"), prepared, head))

    def test_commit_paths_rejects_parseable_output_with_failure_status(self) -> None:
        """Catches an unsuccessful diff-tree result being treated as a verified path set."""
        with patch.object(
            checkpoints_module,
            "run_git",
            return_value=subprocess.CompletedProcess(
                ["git", "diff-tree"], 1, "docs/U06-preview-candidate.md\n", "unavailable"
            ),
        ):
            self.assertEqual(_commit_paths(Path("fixture"), "a" * 40), ())


if __name__ == "__main__":
    unittest.main()
