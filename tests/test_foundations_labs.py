from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from academy_engine.checkpoints import _f04_has_uncommitted_learner_changes, evaluate_checkpoint, load_checkpoint
from academy_engine.curriculum import CurriculumError, _subsections, load_track, verify_track
from academy_engine.doctor import inspect_doctor, record_foundations_doctor
from academy_engine.paths import PathBoundaryError
from academy_engine.scenario import PreparationError, prepare_lab, reset_lab
from tests._temporary import cleanup_temporary_directory


SOURCE = Path(__file__).resolve().parents[1]
OFFICIAL_CODEARBITER_SHA = "debb49da71aa1b97bca0988f72e46bb5875a23e3"
OFFICIAL_TASKWRITE_BLOB = "287d49a24cd8aaf7e33ee3852c2092aca03c4b78"
OFFICIAL_TASKWRITE_SHA256 = "f834f3fcc9dafcdf31db16ad4f52cd232c17162dc1711bdba112c2cac8a30d29"
FOUNDATIONS = (
    "F01-fork-clone-doctor",
    "F02-orient-to-state",
    "F03-work-the-board",
    "F04-fix-with-evidence",
)


def git(root: Path, *arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *arguments],
        cwd=root,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=check,
    )


class AcademyRepository:
    def __init__(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "learner"
        self.root.mkdir()
        for name in (
            "academy",
            "academy_engine",
            "scripts",
            ".codearbiter",
            "workshop_queue",
            "tests",
        ):
            shutil.copytree(SOURCE / name, self.root / name)
        shutil.copyfile(SOURCE / ".gitignore", self.root / ".gitignore")
        shutil.copyfile(SOURCE / "pyproject.toml", self.root / "pyproject.toml")
        git(self.root, "init", "-b", "main")
        git(self.root, "config", "user.name", "Academy Learner")
        git(self.root, "config", "user.email", "learner@example.invalid")
        git(self.root, "add", "-f", ".")
        git(self.root, "commit", "-m", "Academy base")
        git(self.root, "remote", "add", "origin", "https://github.com/learner/arbiter-academy.git")

    def close(self) -> None:
        cleanup_temporary_directory(self.temporary)

    def add_safe_upstream(self, *, ssh: bool = False) -> None:
        url = (
            "git@github.com:arbiterForge/arbiter-academy.git"
            if ssh
            else "https://github.com/arbiterForge/arbiter-academy.git"
        )
        existing = git(self.root, "remote", check=False).stdout.splitlines()
        if "upstream" in existing:
            git(self.root, "remote", "set-url", "upstream", url)
        else:
            git(self.root, "remote", "add", "upstream", url)
        git(self.root, "remote", "set-url", "--push", "upstream", "DISABLED")

    def commit(
        self,
        message: str,
        *paths: str,
        allow_empty: bool = False,
        commit_date: str | None = None,
    ) -> str:
        if paths:
            git(self.root, "add", "--", *paths)
        args = ["commit", "-m", message]
        if allow_empty:
            args.insert(1, "--allow-empty")
        environment = os.environ.copy()
        if commit_date is not None:
            environment["GIT_AUTHOR_DATE"] = commit_date
            environment["GIT_COMMITTER_DATE"] = commit_date
        subprocess.run(
            ["git", *args],
            cwd=self.root,
            env=environment,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=True,
        )
        return git(self.root, "rev-parse", "HEAD").stdout.strip()


def pinned_task_writer() -> tuple[Path, str]:
    value = os.environ.get("CODEARBITER_TASKWRITE")
    asserted_sha = os.environ.get("CODEARBITER_SOURCE_SHA")
    if not value or not asserted_sha:
        raise AssertionError(
            "CODEARBITER_TASKWRITE and CODEARBITER_SOURCE_SHA are required for the live F03 integration"
        )
    if asserted_sha != OFFICIAL_CODEARBITER_SHA:
        raise AssertionError("CODEARBITER_SOURCE_SHA does not match the reviewed source pin")
    writer = Path(value).expanduser().resolve()
    source = writer.parents[2]
    canonical_writer = (source / "core/pysrc/taskwrite.py").resolve()
    if writer != canonical_writer or not writer.is_file():
        raise AssertionError("task writer must be the canonical official repository path")
    repository = Path(git(source, "rev-parse", "--show-toplevel").stdout.strip()).resolve()
    if repository != source:
        raise AssertionError("task writer repository root is not canonical")
    observed_sha = git(source, "rev-parse", "HEAD").stdout.strip()
    if observed_sha != OFFICIAL_CODEARBITER_SHA:
        raise AssertionError(
            "codeArbiter source HEAD does not match the reviewed source pin"
        )
    protected = (
        "core/pysrc/taskwrite.py",
        "core/pysrc/_taskboardlib.py",
        "core/pysrc/_hooklib.py",
        "core/pysrc/hostapi.py",
        "core/pysrc/_gitexec.py",
        "core/pysrc/_pathnorm.py",
        "core/pysrc/_activationlib.py",
        "core/pysrc/_scopelib.py",
        "core/pysrc/_protectedlib.py",
        "core/pysrc/_sensitivelib.py",
    )
    for relative in protected:
        head_line = git(source, "ls-tree", "HEAD", "--", relative).stdout.rstrip("\n")
        metadata, separator, head_path = head_line.partition("\t")
        fields = metadata.split()
        if (
            not separator
            or head_path != relative
            or len(fields) != 3
            or fields[1] != "blob"
        ):
            raise AssertionError("protected task-writer input is not a tracked HEAD blob")
        head_mode, _, head_blob = fields
        index_lines = git(source, "ls-files", "--stage", "--", relative).stdout.splitlines()
        if len(index_lines) != 1:
            raise AssertionError("protected task-writer input lacks one index entry")
        index_metadata, separator, index_path = index_lines[0].partition("\t")
        index_fields = index_metadata.split()
        if (
            not separator
            or index_path != relative
            or len(index_fields) != 3
            or index_fields != [head_mode, head_blob, "0"]
        ):
            raise AssertionError("protected task-writer index differs from reviewed HEAD")
        worktree_blob = git(
            source, "hash-object", "--no-filters", "--", relative
        ).stdout.strip()
        if worktree_blob != head_blob:
            raise AssertionError("protected task-writer worktree differs from reviewed HEAD")
        if relative == "core/pysrc/taskwrite.py" and head_blob != OFFICIAL_TASKWRITE_BLOB:
            raise AssertionError("task-writer Git blob does not match the reviewed pin")
    digest = hashlib.sha256(writer.read_bytes()).hexdigest()
    if digest != OFFICIAL_TASKWRITE_SHA256:
        raise AssertionError("task-writer file digest does not match the reviewed pin")
    return writer, digest


def run_task_writer(
    fixture: AcademyRepository,
    verb: str,
    day: str,
    *,
    task_id: str = "academy.docs.0001",
) -> None:
    writer, _ = pinned_task_writer()
    environment = os.environ.copy()
    environment["CLAUDE_PROJECT_DIR"] = str(fixture.root)
    environment["CLAUDE_PLUGIN_ROOT"] = str(writer.parents[2])
    result = subprocess.run(
        [sys.executable, str(writer), verb, task_id, "--date", day],
        cwd=fixture.root,
        env=environment,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise AssertionError(result.stdout + result.stderr)


class PinnedTaskWriterTests(unittest.TestCase):
    def setUp(self) -> None:
        value = os.environ.get("CODEARBITER_TASKWRITE")
        if not value:
            self.fail("CODEARBITER_TASKWRITE must select the official checkout for pin tests")
        self.official_writer = Path(value).resolve()
        self.official_source = self.official_writer.parents[2]
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(cleanup_temporary_directory, self.temporary)

    def clone_official(self, name: str) -> Path:
        target = Path(self.temporary.name) / name
        subprocess.run(
            [
                "git",
                "clone",
                "--shared",
                "--no-checkout",
                str(self.official_source),
                str(target),
            ],
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=True,
        )
        git(target, "checkout", "--detach", OFFICIAL_CODEARBITER_SHA)
        git(target, "config", "user.name", "Pin Fixture")
        git(target, "config", "user.email", "pin@example.invalid")
        return target

    def invoke_pin(self, writer: Path, asserted_sha: str) -> tuple[Path, str]:
        previous_writer = os.environ.get("CODEARBITER_TASKWRITE")
        previous_sha = os.environ.get("CODEARBITER_SOURCE_SHA")
        try:
            os.environ["CODEARBITER_TASKWRITE"] = str(writer)
            os.environ["CODEARBITER_SOURCE_SHA"] = asserted_sha
            return pinned_task_writer()
        finally:
            if previous_writer is None:
                os.environ.pop("CODEARBITER_TASKWRITE", None)
            else:
                os.environ["CODEARBITER_TASKWRITE"] = previous_writer
            if previous_sha is None:
                os.environ.pop("CODEARBITER_SOURCE_SHA", None)
            else:
                os.environ["CODEARBITER_SOURCE_SHA"] = previous_sha

    def test_pin_rejects_untracked_or_wrong_path_writer(self) -> None:
        clone = self.clone_official("wrong-path")
        shadow = clone / "alternate/pysrc/taskwrite.py"
        shadow.parent.mkdir(parents=True)
        shutil.copyfile(clone / "core/pysrc/taskwrite.py", shadow)

        with self.assertRaises(AssertionError):
            self.invoke_pin(shadow, OFFICIAL_CODEARBITER_SHA)

    def test_pin_rejects_wrong_repository_commit_or_blob(self) -> None:
        wrong_commit = self.clone_official("wrong-commit")
        git(wrong_commit, "commit", "--allow-empty", "-m", "unreviewed descendant")
        descendant = git(wrong_commit, "rev-parse", "HEAD").stdout.strip()

        arbitrary = Path(self.temporary.name) / "arbitrary"
        arbitrary.mkdir()
        git(arbitrary, "init", "-b", "main")
        git(arbitrary, "config", "user.name", "Pin Fixture")
        git(arbitrary, "config", "user.email", "pin@example.invalid")
        for relative in (
            "core/pysrc/taskwrite.py",
            "core/pysrc/_taskboardlib.py",
            "core/pysrc/_hooklib.py",
            "core/pysrc/hostapi.py",
        ):
            destination = arbitrary / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(self.official_source / relative, destination)
        git(arbitrary, "add", ".")
        git(arbitrary, "commit", "-m", "canonical-looking arbitrary source")
        arbitrary_sha = git(arbitrary, "rev-parse", "HEAD").stdout.strip()

        wrong_blob = Path(self.temporary.name) / "wrong-blob"
        shutil.copytree(arbitrary, wrong_blob)
        writer = wrong_blob / "core/pysrc/taskwrite.py"
        writer.write_bytes(writer.read_bytes() + b"\n# unreviewed executable delta\n")
        git(wrong_blob, "add", "core/pysrc/taskwrite.py")
        git(wrong_blob, "commit", "-m", "change executable bytes")
        wrong_blob_sha = git(wrong_blob, "rev-parse", "HEAD").stdout.strip()

        cases = (
            (wrong_commit / "core/pysrc/taskwrite.py", descendant),
            (arbitrary / "core/pysrc/taskwrite.py", arbitrary_sha),
            (wrong_blob / "core/pysrc/taskwrite.py", wrong_blob_sha),
        )
        for candidate, asserted_sha in cases:
            with self.subTest(candidate=candidate.parent.parent.parent.name):
                with self.assertRaises(AssertionError):
                    self.invoke_pin(candidate, asserted_sha)

    def test_pin_rejects_staged_or_transitive_protected_input_drift(self) -> None:
        staged = self.clone_official("staged-drift")
        staged_path = staged / "core/pysrc/_taskboardlib.py"
        original = staged_path.read_bytes()
        staged_path.write_bytes(original + b"\n# staged-only drift\n")
        git(staged, "add", "core/pysrc/_taskboardlib.py")
        staged_path.write_bytes(original)

        transitive = self.clone_official("transitive-drift")
        transitive_path = transitive / "core/pysrc/_gitexec.py"
        transitive_path.write_bytes(
            transitive_path.read_bytes() + b"\n# unreviewed runtime input\n"
        )

        for candidate in (staged, transitive):
            with self.subTest(candidate=candidate.name):
                with self.assertRaises(AssertionError):
                    self.invoke_pin(
                        candidate / "core/pysrc/taskwrite.py",
                        OFFICIAL_CODEARBITER_SHA,
                    )

    def test_pin_accepts_only_exact_official_identity(self) -> None:
        writer, digest = self.invoke_pin(
            self.official_writer, OFFICIAL_CODEARBITER_SHA
        )

        self.assertEqual(writer, self.official_source / "core/pysrc/taskwrite.py")
        self.assertEqual(digest, OFFICIAL_TASKWRITE_SHA256)
        self.assertEqual(
            git(self.official_source, "rev-parse", "HEAD:core/pysrc/taskwrite.py").stdout.strip(),
            OFFICIAL_TASKWRITE_BLOB,
        )


class FoundationsCurriculumTests(unittest.TestCase):
    def test_f03_seed_declares_the_bounded_docs_start_contract(self) -> None:
        """Catches F03 drifting back to a board-only or feature-task scenario."""
        scenario = SOURCE / "academy/scenarios/F03-work-the-board/files/scenario.json"
        self.assertEqual(
            json.loads(scenario.read_text(encoding="utf-8")),
            {
                "schema_version": 1,
                "lab_id": "F03-work-the-board",
                "operation": "task_start_co_commit",
                "target": "academy.docs.0001",
                "starting_condition": "queued",
            },
        )

    def test_f04_uses_the_guided_lesson_anatomy_and_all_actions_once(self) -> None:
        path = SOURCE / "academy/tracks/foundations/F04-fix-with-evidence.md"
        text = path.read_text(encoding="utf-8")
        self.assertIn("Complete F02 first", text)
        self.assertNotIn("Complete F03 first", text)
        self.assertEqual(
            tuple(line[3:] for line in text.splitlines() if line.startswith("## ")),
            ("Know before you begin", "What you will prove", "Prepare safely", "Practice", "Recognize success", "Check", "Recover or continue", "Understand the mechanism"),
        )
        for action_id in (
            "F04-prepare", "F04-inspect-defect", "F04-confirm-baseline", "F04-start-fix", "F04-request-regression", "F04-run-red-regression", "F04-inspect-test-boundary", "F04-stage-regression", "F04-review-regression-boundary", "F04-commit-regression", "F04-prove-red-commit", "F04-request-repair", "F04-prove-repair", "F04-inspect-repair-boundary", "F04-stage-repair", "F04-review-repair-boundary", "F04-commit-repair", "F04-inspect-history", "F04-check", "F04-reset-retry", "F04-return-base",
        ):
            self.assertEqual(text.count("{{action:" + action_id + "}}"), 1, action_id)
        self.assertNotIn("```", text)

    def test_f03_uses_the_public_guided_lesson_anatomy_and_all_actions_once(self) -> None:
        """F03 must expose its runnable docs co-commit workflow without private-source copy."""
        path = SOURCE / "academy/tracks/foundations/F03-work-the-board.md"
        text = path.read_text(encoding="utf-8")
        body = text.split("---", 2)[2]
        headings = tuple(line[3:] for line in text.splitlines() if line.startswith("## "))
        self.assertEqual(
            headings,
            (
                "Know before you begin",
                "What you will prove",
                "Prepare safely",
                "Practice",
                "Recognize success",
                "Check",
                "Recover or continue",
                "Understand the mechanism",
            ),
        )
        action_ids = (
            "F03-prepare", "F03-read-target-task",
            "F03-start-task", "F03-inspect-started-task", "F03-read-contract",
            "F03-run-docs-chore", "F03-review-co-commit-boundary",
            "F03-choose-keep-branch", "F03-confirm-clean", "F03-check",
            "F03-reset-retry",
        )
        for action_id in action_ids:
            self.assertEqual(body.count("{{action:" + action_id + "}}"), 1, action_id)
        lab = load_track(SOURCE, "foundations").labs[2]
        self.assertEqual(lab.id, FOUNDATIONS[2])
        self.assertEqual(lab.scenario_command, "{{action:F03-prepare}}")
        self.assertEqual(lab.checkpoint_command, "{{action:F03-check}}")
        self.assertEqual(
            lab.host_commands,
            {
                "claude-code": "/ca:task start academy.docs.0001",
                "codex": "$ca-task start academy.docs.0001",
                "pi": "/ca-task start academy.docs.0001\n/skill:ca-task start academy.docs.0001",
            },
        )
        self.assertIn("Preview 0.29", body)
        self.assertIn("$ca-chore docs", body)
        self.assertIn("academy.docs.0001", body)
        self.assertIn("clean retained F03 attempt branch", body)
        self.assertNotIn("Reset\nfrom clean main", body)
        self.assertIn("docs/ticket-list-contract.md", body)
        self.assertIn("[~]", body)
        self.assertIn("Keep the branch as-is", body)
        self.assertIn("no hosted pull request", body)
        self.assertIn("cannot prove that `$ca-task` ran", body)
        self.assertIn("cannot prove that `$ca-chore` ran", body)
        self.assertNotIn("F03-private-boundary", body)
        self.assertNotIn("Future private-source walkthrough", body)
        self.assertNotIn("refuse F03", body)
        self.assertNotIn("preview-0.25", body)
        self.assertNotIn("git commit", body)

    def test_f02_uses_the_guided_lesson_anatomy_and_all_actions_once(self) -> None:
        path = SOURCE / "academy/tracks/foundations/F02-orient-to-state.md"
        text = path.read_text(encoding="utf-8")
        headings = tuple(
            line[3:] for line in text.splitlines()
            if line.startswith("## ")
        )

        self.assertEqual(
            headings,
            (
                "Know before you begin",
                "What you will prove",
                "Prepare safely",
                "Practice",
                "Recognize success",
                "Check",
                "Recover or continue",
                "Understand the mechanism",
            ),
        )
        for action_id in (
            "F02-prepare", "F02-run-status", "F02-read-context",
            "F02-follow-context-links", "F02-hash-context",
            "F02-write-orientation", "F02-inspect-orientation",
            "F02-stage-orientation", "F02-review-commit-boundary",
            "F02-run-commit-gate", "F02-confirm-clean", "F02-check",
            "F02-return-base", "F02-reset-retry",
        ):
            self.assertEqual(text.count("{{action:" + action_id + "}}"), 1, action_id)
        lab = load_track(SOURCE, "foundations").labs[1]
        self.assertEqual(lab.id, FOUNDATIONS[1])
        self.assertEqual(
            lab.host_commands,
            {
                "claude-code": "/ca:status",
                "codex": "$ca-status",
                "pi": "/ca-status\n/skill:ca-status",
            },
        )

    def test_f01_uses_the_guided_lesson_anatomy_and_all_actions_once(self) -> None:
        path = SOURCE / "academy/tracks/foundations/F01-fork-clone-doctor.md"
        text = path.read_text(encoding="utf-8")
        headings = tuple(
            line[3:] for line in text.splitlines() if line.startswith("## ")
        )

        self.assertEqual(
            headings,
            (
                "Know before you begin",
                "What you will prove",
                "Prepare safely",
                "Practice",
                "Recognize success",
                "Check",
                "Recover or continue",
                "Understand the mechanism",
            ),
        )
        for action_id in (
            "F01-prepare", "F01-inspect-remotes", "F01-repair-origin",
            "F01-set-upstream", "F01-disable-upstream-push",
            "F01-select-push-default", "F01-host-doctor", "F01-academy-doctor",
            "F01-inspect-report", "F01-stage-report", "F01-review-commit-boundary",
            "F01-commit-report", "F01-confirm-clean", "F01-check",
            "F01-return-base", "F01-reset-retry",
        ):
            self.assertEqual(text.count("{{action:" + action_id + "}}"), 1, action_id)

    def test_track_loader_exposes_the_exact_progression_and_action_contract(self) -> None:
        track = load_track(SOURCE, "foundations")
        self.assertEqual(tuple(lab.id for lab in track.labs), FOUNDATIONS)
        self.assertEqual(
            tuple(lab.prerequisites for lab in track.labs),
            ((), (FOUNDATIONS[0],), (FOUNDATIONS[1],), (FOUNDATIONS[1],)),
        )
        for lab in track.labs:
            with self.subTest(lab=lab.id):
                self.assertTrue(lab.outcome)
                self.assertGreater(lab.estimated_minutes, 0)
                self.assertEqual(len(lab.hints), 3)
                self.assertEqual(
                    set(lab.host_commands), {"claude-code", "codex", "pi"}
                )
                self.assertIn("prepare", lab.scenario_command)
                if lab.id == "F03-work-the-board":
                    self.assertEqual(lab.checkpoint_command, "{{action:F03-check}}")
                else:
                    self.assertIn("arbiter-academy --repository", lab.checkpoint_command)
                self.assertTrue(lab.success_evidence)
                self.assertIn("reset", lab.recovery)

    def test_loader_rejects_a_missing_progressive_hint_as_a_contract_break(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copytree(SOURCE / "academy", root / "academy")
            path = root / "academy/tracks/foundations/F02-orient-to-state.md"
            text = path.read_text(encoding="utf-8")
            path.write_text(text.replace("### Hint 3", "### Reference"), encoding="utf-8")

            with self.assertRaisesRegex(CurriculumError, "three progressive hints"):
                load_track(root, "foundations")

    def test_loader_rejects_each_comment_only_progressive_hint(self) -> None:
        """Catches headings whose whitespace/comments falsely count as learner guidance."""
        for number in (1, 2, 3):
            with self.subTest(hint=number), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                shutil.copytree(SOURCE / "academy", root / "academy")
                path = root / "academy/tracks/foundations/F02-orient-to-state.md"
                text = path.read_text(encoding="utf-8")
                heading = f"### Hint {number}\n"
                start = text.index(heading) + len(heading)
                terminator = (
                    f"### Hint {number + 1}\n"
                    if number < 3
                    else "## Understand the mechanism\n"
                )
                end = text.index(terminator, start)
                comment_only = (
                    " \t\n<!-- no learner-visible guidance -->\n"
                    "<!--\nmultiline maintenance note\n-->\n\n"
                )
                path.write_text(
                    text[:start] + comment_only + text[end:], encoding="utf-8"
                )

                with self.assertRaisesRegex(CurriculumError, "learner-visible"):
                    load_track(root, "foundations")

    def test_loader_rejects_duplicate_host_sections_instead_of_overwriting_one(self) -> None:
        """Preserve duplicate legacy host-heading detection after all lessons went guided."""
        with self.assertRaisesRegex(CurriculumError, "repeats host subsection Codex"):
            _subsections(
                "### Codex\n\nFirst command.\n\n### Codex\n\nSecond command.\n",
                Path("legacy-guide.md"),
                "host",
            )

    def test_verify_track_matrix_binds_sources_scenarios_and_checkpoints(self) -> None:
        report = verify_track(SOURCE, "foundations", matrix=True)

        self.assertTrue(report.passed, report.issues)
        self.assertEqual(report.lab_count, 4)
        self.assertEqual(report.matrix_cells, 49)
        self.assertNotIn(str(SOURCE), report.render())

    def test_verify_track_fails_closed_on_a_non_object_scenario(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copytree(SOURCE / "academy", root / "academy")
            scenario = root / "academy/scenarios/F02-orient-to-state/files/scenario.json"
            scenario.write_text("[]\n", encoding="utf-8")

            report = verify_track(root, "foundations", matrix=True)

        self.assertFalse(report.passed)
        self.assertIn("scenario input must be an object", "\n".join(report.issues))

    def test_verify_track_rejects_noncanonical_foundations_scenario_semantics(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copytree(SOURCE / "academy", root / "academy")
            scenario = root / "academy/scenarios/F03-work-the-board/files/scenario.json"
            payload = json.loads(scenario.read_text(encoding="utf-8"))
            payload["operation"] = "looks_close_but_is_not_the_course"
            scenario.write_text(json.dumps(payload), encoding="utf-8")

            report = verify_track(root, "foundations", matrix=True)

        self.assertFalse(report.passed)
        self.assertIn("scenario semantics are noncanonical", "\n".join(report.issues))

    def test_loader_rejects_comment_only_required_content(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copytree(SOURCE / "academy", root / "academy")
            path = root / "academy/tracks/foundations/F02-orient-to-state.md"
            text = path.read_text(encoding="utf-8")
            start = text.index("## Know before you begin")
            end = text.index("## What you will prove")
            path.write_text(
                text[:start]
                + "## Know before you begin\n\n<!-- deliberately empty -->\n\n"
                + text[end:],
                encoding="utf-8",
            )

            with self.assertRaisesRegex(CurriculumError, "learner-visible content"):
                load_track(root, "foundations")

    def test_cli_verify_track_reports_a_structural_matrix_without_authoritative_claims(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(SOURCE / "scripts/academy.py"),
                "verify-track",
                "foundations",
                "--matrix",
            ],
            cwd=SOURCE,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Foundations: 4 labs", result.stdout)
        self.assertIn("49 matrix cells", result.stdout)
        self.assertIn("structural", result.stdout.casefold())
        self.assertNotIn("graduated", result.stdout.casefold())


class FoundationsScenarioTests(unittest.TestCase):
    def test_f01_complete_real_repository_lifecycle_records_progress_after_external_check(self) -> None:
        fixture = AcademyRepository()
        self.addCleanup(fixture.close)
        fixture.add_safe_upstream()
        git(fixture.root, "config", "remote.pushDefault", "origin")

        prepared = prepare_lab(fixture.root, FOUNDATIONS[0])
        report = record_foundations_doctor(fixture.root, inspect_doctor(fixture.root))
        self.assertEqual(
            json.loads(report.read_text(encoding="utf-8")),
            {
                "schema_version": 1,
                "safe_for_push_labs": True,
                "effective_push_remote": "origin",
            },
        )
        fixture.commit("record doctor result", ".codearbiter/reports/academy/F01-doctor.json")
        self.assertEqual(git(fixture.root, "status", "--short").stdout, "")

        command = subprocess.run(
            [
                sys.executable,
                str(SOURCE / "scripts/academy.py"),
                "--repository",
                str(fixture.root),
                "check",
                FOUNDATIONS[0],
            ],
            cwd=SOURCE,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )

        self.assertEqual(command.returncode, 0, command.stderr)
        self.assertEqual(
            command.stdout.strip(),
            "checkpoint F01-fork-clone-doctor: passed; progress: .academy/progress.json",
        )
        progress = json.loads((fixture.root / ".academy/progress.json").read_text(encoding="utf-8"))
        self.assertEqual(progress["checkpoints"][0]["attempt"], prepared.branch)

    def test_f01_failed_mutations_preserve_the_attempt_commit(self) -> None:
        for case in (
            "uncommitted-report",
            "extra-committed-path",
            "changed-live-origin",
            "missing-upstream-push-disable",
            "wrong-push-default",
        ):
            with self.subTest(case=case):
                fixture = AcademyRepository()
                self.addCleanup(fixture.close)
                fixture.add_safe_upstream()
                git(fixture.root, "config", "remote.pushDefault", "origin")
                prepare_lab(fixture.root, FOUNDATIONS[0])
                report = record_foundations_doctor(fixture.root, inspect_doctor(fixture.root))
                if case == "uncommitted-report":
                    attempt_commit = git(fixture.root, "rev-parse", "HEAD").stdout.strip()
                else:
                    paths = [str(report.relative_to(fixture.root))]
                    if case == "extra-committed-path":
                        extra = fixture.root / "learner-notes.txt"
                        extra.write_text("not F01 evidence\n", encoding="utf-8")
                        paths.append(str(extra.relative_to(fixture.root)))
                    attempt_commit = fixture.commit("record doctor result", *paths)
                if case == "changed-live-origin":
                    git(fixture.root, "remote", "set-url", "origin", "https://github.com/arbiterForge/arbiter-academy.git")
                elif case == "missing-upstream-push-disable":
                    git(fixture.root, "remote", "set-url", "--push", "upstream", "https://github.com/arbiterForge/arbiter-academy.git")
                elif case == "wrong-push-default":
                    git(fixture.root, "config", "remote.pushDefault", "upstream")

                result = evaluate_checkpoint(fixture.root, FOUNDATIONS[0])

                self.assertFalse(result.passed)
                self.assertEqual(git(fixture.root, "rev-parse", "HEAD").stdout.strip(), attempt_commit)

    def test_f01_reset_preserves_the_failed_attempt_and_prepares_a_retry(self) -> None:
        fixture = AcademyRepository()
        self.addCleanup(fixture.close)
        fixture.add_safe_upstream()
        git(fixture.root, "config", "remote.pushDefault", "origin")
        prepared = prepare_lab(fixture.root, FOUNDATIONS[0])
        report = record_foundations_doctor(fixture.root, inspect_doctor(fixture.root))
        attempt_commit = fixture.commit("record doctor result", str(report.relative_to(fixture.root)))

        retry = reset_lab(fixture.root, FOUNDATIONS[0])

        self.assertEqual(retry.branch, "academy/F01-fork-clone-doctor/2")
        archive_refs = git(
            fixture.root,
            "for-each-ref",
            "--format=%(refname)",
            "refs/heads/academy/archive/F01-fork-clone-doctor/",
        ).stdout.splitlines()
        self.assertEqual(len(archive_refs), 1)
        self.assertEqual(
            git(fixture.root, "rev-parse", archive_refs[0]).stdout.strip(),
            attempt_commit,
        )

    def test_f01_in_checkout_check_refuses_circular_authority_and_preserves_commit(self) -> None:
        fixture = AcademyRepository()
        self.addCleanup(fixture.close)
        fixture.add_safe_upstream()
        git(fixture.root, "config", "remote.pushDefault", "origin")
        prepare_lab(fixture.root, FOUNDATIONS[0])
        report = record_foundations_doctor(fixture.root, inspect_doctor(fixture.root))
        attempt_commit = fixture.commit("record doctor result", str(report.relative_to(fixture.root)))

        command = subprocess.run(
            [
                sys.executable,
                str(fixture.root / "scripts/academy.py"),
                "--repository",
                str(fixture.root),
                "check",
                FOUNDATIONS[0],
            ],
            cwd=fixture.root,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )

        self.assertEqual(command.returncode, 1, command.stdout + command.stderr)
        self.assertIn("installed outside the target repository", command.stderr)
        self.assertEqual(git(fixture.root, "rev-parse", "HEAD").stdout.strip(), attempt_commit)
        self.assertFalse((fixture.root / ".academy/progress.json").exists())

    def test_f01_prepare_accepts_a_fork_safe_origin_before_upstream_is_configured(self) -> None:
        fixture = AcademyRepository()
        self.addCleanup(fixture.close)

        prepared = prepare_lab(fixture.root, FOUNDATIONS[0])

        self.assertEqual(prepared.branch, "academy/F01-fork-clone-doctor/1")
        self.assertEqual(git(fixture.root, "remote").stdout.strip(), "origin")
        fixture.commit("inspect incomplete routing", allow_empty=True)
        self.assertFalse(evaluate_checkpoint(fixture.root, FOUNDATIONS[0]).passed)

    def test_f01_prepare_still_rejects_an_official_origin(self) -> None:
        fixture = AcademyRepository()
        self.addCleanup(fixture.close)
        git(
            fixture.root,
            "remote",
            "set-url",
            "origin",
            "https://github.com/arbiterForge/arbiter-academy.git",
        )

        with self.assertRaisesRegex(PreparationError, "fork-safe origin"):
            prepare_lab(fixture.root, FOUNDATIONS[0])

    def test_f01_academy_doctor_records_only_the_bounded_semantic_result(self) -> None:
        fixture = AcademyRepository()
        self.addCleanup(fixture.close)
        fixture.add_safe_upstream()
        prepare_lab(fixture.root, FOUNDATIONS[0])

        result = subprocess.run(
            [
                sys.executable,
                str(SOURCE / "scripts/academy.py"),
                "doctor",
                FOUNDATIONS[0],
            ],
            cwd=fixture.root,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        artifact = json.loads(
            (fixture.root / ".codearbiter/reports/academy/F01-doctor.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            artifact,
            {
                "schema_version": 1,
                "safe_for_push_labs": True,
                "effective_push_remote": "origin",
            },
        )
        serialized = json.dumps(artifact)
        self.assertNotIn(str(fixture.root), serialized)
        self.assertNotIn("learner", serialized)

    def test_f01_doctor_refuses_a_reparse_redirected_report_destination(self) -> None:
        fixture = AcademyRepository()
        self.addCleanup(fixture.close)
        fixture.add_safe_upstream()
        prepare_lab(fixture.root, FOUNDATIONS[0])
        report = inspect_doctor(fixture.root)
        temporary_root = Path(fixture.temporary.name).resolve()
        outside = temporary_root / "outside-reports"
        outside.mkdir()
        sentinel = outside / "sentinel.txt"
        sentinel_bytes = b"academy junction target"
        sentinel.write_bytes(sentinel_bytes)
        link = fixture.root / ".codearbiter/reports/academy"

        def is_reparse(path: Path) -> bool:
            details = os.lstat(path)
            attributes = getattr(details, "st_file_attributes", 0)
            return bool(
                stat.S_ISLNK(details.st_mode)
                or attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
            )

        if link.exists():
            self.assertFalse(is_reparse(link))
            shutil.rmtree(link)
        link.parent.mkdir(parents=True, exist_ok=True)
        if sys.platform == "win32":
            def safe_operand(path: Path) -> str:
                relative = path.relative_to(temporary_root)
                rendered = str(relative)
                self.assertFalse(relative.is_absolute())
                self.assertNotIn("..", relative.parts)
                self.assertNotRegex(rendered, r'[\x00-\x1f"&|<>^()%!*?]')
                return rendered

            system_root = Path(os.environ["SystemRoot"])
            command = system_root / "System32/cmd.exe"
            self.assertTrue(command.is_absolute())
            self.assertTrue(command.is_file())
            created = subprocess.run(
                [
                    str(command),
                    "/d",
                    "/v:off",
                    "/c",
                    "mklink",
                    "/J",
                    safe_operand(link),
                    safe_operand(outside),
                ],
                cwd=temporary_root,
                shell=False,
                capture_output=True,
                check=False,
                timeout=10,
            )
            diagnostic = (created.stdout + created.stderr)[:2048].decode("utf-8", "replace")
            self.assertEqual(created.returncode, 0, diagnostic)
        else:
            os.symlink(outside, link, target_is_directory=True)

        try:
            self.assertTrue(is_reparse(link))
            with self.assertRaisesRegex(PathBoundaryError, "symlink or reparse"):
                record_foundations_doctor(fixture.root, report)
        finally:
            if os.path.lexists(link):
                if not is_reparse(link):
                    raise AssertionError("refusing to remove an ordinary directory as a redirect")
                if sys.platform == "win32":
                    os.rmdir(link)
                else:
                    os.unlink(link)

        self.assertFalse(os.path.lexists(link))
        self.assertTrue(outside.is_dir())
        self.assertEqual(sentinel.read_bytes(), sentinel_bytes)
        self.assertFalse((outside / "F01-doctor.json").exists())

    def test_f04_prepare_stages_a_real_defect_and_removes_the_finished_regression(self) -> None:
        fixture = AcademyRepository()
        self.addCleanup(fixture.close)
        fixture.add_safe_upstream()

        prepare_lab(fixture.root, FOUNDATIONS[3])
        regression = "test_claim_rejects_control_characters_in_volunteer_label"
        test_text = (fixture.root / "tests/test_service.py").read_text(encoding="utf-8")
        service_text = (fixture.root / "workshop_queue/service.py").read_text(encoding="utf-8")

        self.assertNotIn(regression, test_text)
        self.assertNotIn("control characters", service_text)
        probe = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "from datetime import datetime, timezone; "
                    "from tests.test_service import open_ticket; "
                    "from workshop_queue.service import claim_ticket; "
                    "claim_ticket([open_ticket('RQ-104')], 'RQ-104', 'Sam\\nAdmin', "
                    "datetime.now(timezone.utc))"
                ),
            ],
            cwd=fixture.root,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(probe.returncode, 0, probe.stderr)


class FoundationsCheckpointMatrixTests(unittest.TestCase):
    def _prepared(self, lab_id: str) -> AcademyRepository:
        fixture = AcademyRepository()
        fixture.add_safe_upstream()
        prepare_lab(fixture.root, lab_id)
        return fixture

    def test_f03_prepare_seeds_only_the_queued_docs_task_and_contract_note(self) -> None:
        """Catches a board-only F03 prepare or an accidental broader task fixture."""
        fixture = self._prepared(FOUNDATIONS[2])
        self.addCleanup(fixture.close)

        self.assertEqual(
            (fixture.root / ".codearbiter/open-tasks.md").read_text(encoding="utf-8"),
            """# Open tasks - F03 Academy fixture

All dates, statuses, and roles below are fictional Academy fixtures.

## Queued

- [ ] academy.docs.0001 - Clarify claimant visibility in ticket list output
  - Desc: Correct the prepared contract so claimed tickets show their claimant while open tickets do not.
  - Done when: The local contract distinguishes claimant visibility for claimed and open tickets without exposing storage internals.
  - Boundaries: docs/ticket-list-contract.md
  - Curriculum lane: docs
  - Evidence: [ticket list contract](../docs/ticket-list-contract.md)
""",
        )
        self.assertEqual(
            (fixture.root / "docs/ticket-list-contract.md").read_text(encoding="utf-8"),
            """# Ticket list contract

## Claimant visibility

Ticket list output shows a claimant for every ticket.
""",
        )
        self.assertEqual(
            git(fixture.root, "status", "--porcelain", "--untracked-files=all").stdout,
            "",
        )

    def test_f03_checkpoint_declares_the_task_start_co_commit_binding(self) -> None:
        """Catches metadata/schema drift from the bounded board-plus-document proof."""
        checkpoint = load_checkpoint(
            SOURCE / "academy/checkpoints/F03-work-the-board.json"
        )

        self.assertEqual(checkpoint.predicates[0].id, "task_start_co_commit")
        self.assertEqual(
            checkpoint.predicates[0].data,
            {
                "profile": "task_start_co_commit",
                "board": ".codearbiter/open-tasks.md",
                "task_id": "academy.docs.0001",
                "work_file": "docs/ticket-list-contract.md",
            },
        )

    def _record_f01(self, fixture: AcademyRepository) -> str:
        path = fixture.root / ".codearbiter/reports/academy/F01-doctor.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "safe_for_push_labs": True,
                    "effective_push_remote": "origin",
                }
            ),
            encoding="utf-8",
        )
        return fixture.commit("record doctor result", str(path.relative_to(fixture.root)))

    def test_f01_accepts_intended_and_equivalent_remote_forms(self) -> None:
        for ssh in (False, True):
            with self.subTest(ssh=ssh):
                fixture = AcademyRepository()
                self.addCleanup(fixture.close)
                fixture.add_safe_upstream(ssh=ssh)
                prepare_lab(fixture.root, FOUNDATIONS[0])
                self._record_f01(fixture)

                result = evaluate_checkpoint(fixture.root, FOUNDATIONS[0])
                self.assertTrue(result.passed, result.failed_predicates)

    def test_f01_rejects_unsafe_live_configuration_and_dirty_evidence(self) -> None:
        cases = ("official-origin", "missing-upstream", "unsafe-push", "dirty")
        for case in cases:
            with self.subTest(case=case):
                fixture = self._prepared(FOUNDATIONS[0])
                self.addCleanup(fixture.close)
                if case == "official-origin":
                    git(fixture.root, "remote", "set-url", "origin", "https://github.com/arbiterForge/arbiter-academy.git")
                elif case == "missing-upstream":
                    git(fixture.root, "remote", "remove", "upstream")
                elif case == "unsafe-push":
                    git(fixture.root, "remote", "set-url", "--add", "--push", "origin", "https://github.com/arbiterForge/arbiter-academy.git")
                self._record_f01(fixture)
                if case == "dirty":
                    (fixture.root / "learner-notes.txt").write_text("uncommitted\n", encoding="utf-8")

                result = evaluate_checkpoint(fixture.root, FOUNDATIONS[0])
                self.assertFalse(result.passed)
                self.assertIn("remote_and_doctor", result.failed_predicates)

    def test_f01_rejects_untouched_partial_and_wrong_branch_evidence(self) -> None:
        for case in ("untouched", "copied", "wrong-branch"):
            with self.subTest(case=case):
                fixture = self._prepared(FOUNDATIONS[0])
                self.addCleanup(fixture.close)
                if case == "untouched":
                    fixture.commit("no report yet", allow_empty=True)
                elif case == "copied":
                    path = fixture.root / ".codearbiter/reports/academy/F01-doctor.json"
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(json.dumps({"schema_version": 1, "safe_for_push_labs": False, "effective_push_remote": "upstream"}), encoding="utf-8")
                    fixture.commit("copy stale report", str(path.relative_to(fixture.root)))
                else:
                    git(fixture.root, "switch", "-c", "learner/wrong-branch")
                    self._record_f01(fixture)

                result = evaluate_checkpoint(fixture.root, FOUNDATIONS[0])
                self.assertFalse(result.passed)

    def test_check_requires_the_current_attempt_branch_and_records_nothing_elsewhere(self) -> None:
        fixture = self._prepared(FOUNDATIONS[0])
        self.addCleanup(fixture.close)
        self._record_f01(fixture)
        self.assertTrue(evaluate_checkpoint(fixture.root, FOUNDATIONS[0]).passed)
        git(fixture.root, "switch", "main")

        result = evaluate_checkpoint(fixture.root, FOUNDATIONS[0])
        self.assertFalse(result.passed)
        self.assertEqual(result.attempt, "")
        command = subprocess.run(
            [
                sys.executable,
                str(SOURCE / "scripts/academy.py"),
                "--repository",
                str(fixture.root),
                "check",
                FOUNDATIONS[0],
            ],
            cwd=SOURCE,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )
        self.assertEqual(command.returncode, 1, command.stdout + command.stderr)
        self.assertIn("checkpoint F01-fork-clone-doctor: failed", command.stderr)
        self.assertFalse((fixture.root / ".academy/progress.json").exists())

    def _record_f02(
        self,
        fixture: AcademyRepository,
        *,
        compact_reordered: bool = False,
        extra_paths: tuple[str, ...] = (),
        **overrides: object,
    ) -> str:
        context = (fixture.root / ".codearbiter/CONTEXT.md").read_bytes()
        payload: dict[str, object] = {
            "schema_version": 1,
            "context_path": ".codearbiter/CONTEXT.md",
            "context_sha256": hashlib.sha256(context).hexdigest(),
            "stage": 2,
        }
        payload.update(overrides)
        path = fixture.root / ".codearbiter/reports/academy/F02-orientation.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        if compact_reordered:
            payload = {
                "stage": payload["stage"],
                "context_sha256": payload["context_sha256"],
                "context_path": payload["context_path"],
                "schema_version": payload["schema_version"],
            }
        path.write_text(
            json.dumps(payload, separators=(",", ":") if compact_reordered else None, indent=None if compact_reordered else 2),
            encoding="utf-8",
        )
        return fixture.commit(
            "record live orientation", str(path.relative_to(fixture.root)), *extra_paths
        )

    def test_f02_accepts_current_context_and_rejects_stale_or_uncommitted_records(self) -> None:
        positive_serializations: dict[str, bytes] = {}
        for case in ("intended", "equivalent", "missing", "stale-hash", "stale-stage", "wrong-path", "rendered-hash", "modified-after", "uncommitted"):
            with self.subTest(case=case):
                fixture = self._prepared(FOUNDATIONS[1])
                self.addCleanup(fixture.close)
                if case == "missing":
                    fixture.commit("orientation not recorded", allow_empty=True)
                elif case == "stale-hash":
                    self._record_f02(fixture, context_sha256="0" * 64)
                elif case == "stale-stage":
                    self._record_f02(fixture, stage=1)
                elif case == "wrong-path":
                    self._record_f02(fixture, context_path="README.md")
                elif case == "rendered-hash":
                    text = (fixture.root / ".codearbiter/CONTEXT.md").read_text(encoding="utf-8")
                    self._record_f02(fixture, context_sha256=hashlib.sha256(text.strip().encode()).hexdigest())
                elif case == "modified-after":
                    self._record_f02(fixture)
                    path = fixture.root / ".codearbiter/CONTEXT.md"
                    path.write_text(path.read_text(encoding="utf-8") + "\nChanged after orientation.\n", encoding="utf-8")
                    fixture.commit("change context", str(path.relative_to(fixture.root)))
                elif case == "uncommitted":
                    path = fixture.root / ".codearbiter/reports/academy/F02-orientation.json"
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text("{}\n", encoding="utf-8")
                    fixture.commit("leave record uncommitted", allow_empty=True)
                else:
                    self._record_f02(fixture, compact_reordered=case == "equivalent")
                    positive_serializations[case] = (
                        fixture.root / ".codearbiter/reports/academy/F02-orientation.json"
                    ).read_bytes()

                result = evaluate_checkpoint(fixture.root, FOUNDATIONS[1])
                if case in {"intended", "equivalent"}:
                    self.assertTrue(result.passed, result.failed_predicates)
                else:
                    self.assertFalse(result.passed)
        self.assertNotEqual(
            positive_serializations["intended"], positive_serializations["equivalent"]
        )

    def test_f02_rejects_evidence_outside_its_single_clean_commit_boundary(self) -> None:
        for case in ("co-committed", "context-rewritten-before-record", "dirty-worktree"):
            with self.subTest(case=case):
                fixture = self._prepared(FOUNDATIONS[1])
                self.addCleanup(fixture.close)
                if case == "co-committed":
                    extra = fixture.root / "learner-notes.md"
                    extra.write_text("A co-committed learner note.\n", encoding="utf-8")
                    self._record_f02(
                        fixture, extra_paths=(str(extra.relative_to(fixture.root)),)
                    )
                elif case == "context-rewritten-before-record":
                    context = fixture.root / ".codearbiter/CONTEXT.md"
                    context.write_bytes(context.read_bytes() + b"\nRewritten before orientation.\n")
                    fixture.commit("rewrite context", str(context.relative_to(fixture.root)))
                    self._record_f02(fixture)
                else:
                    self._record_f02(fixture)
                    (fixture.root / "uncommitted-learner-note.txt").write_text(
                        "This worktree is not clean.\n", encoding="utf-8"
                    )

                result = evaluate_checkpoint(fixture.root, FOUNDATIONS[1])
                self.assertFalse(result.passed)

    def _write_f03_work_file(
        self,
        fixture: AcademyRepository,
        *,
        sentence: str = (
            "Ticket list output shows the claimant for a claimed ticket and no claimant "
            "for an open ticket."
        ),
        append: str = "",
    ) -> None:
        work_file = fixture.root / "docs/ticket-list-contract.md"
        text = work_file.read_text(encoding="utf-8")
        work_file.write_text(
            text.replace(
                "Ticket list output shows a claimant for every ticket.",
                sentence,
                1,
            )
            + append,
            encoding="utf-8",
        )

    def _commit_f03_boundary(
        self,
        fixture: AcademyRepository,
        *,
        day: str = "2026-08-02",
        extra_paths: tuple[str, ...] = (),
    ) -> str:
        return fixture.commit(
            "start bounded claimant visibility docs task",
            ".codearbiter/open-tasks.md",
            "docs/ticket-list-contract.md",
            *extra_paths,
            commit_date=f"{day}T12:00:00-04:00",
        )

    def _manually_start_f03_board(
        self,
        fixture: AcademyRepository,
        *,
        task_id: str = "academy.docs.0001",
        stamp: str = "  (started 2026-08-02)",
        title: str = "Clarify claimant visibility in ticket list output",
    ) -> None:
        board = fixture.root / ".codearbiter/open-tasks.md"
        text = board.read_text(encoding="utf-8")
        queued = (
            "- [ ] academy.docs.0001 - "
            "Clarify claimant visibility in ticket list output"
        )
        started = f"- [~] {task_id} - {title}{stamp}"
        board.write_text(text.replace(queued, started, 1), encoding="utf-8")

    def test_f03_accepts_one_clean_dated_board_and_contract_commit_from_real_writer(
        self,
    ) -> None:
        for day in ("2026-08-02", "2026-08-13"):
            with self.subTest(day=day):
                fixture = self._prepared(FOUNDATIONS[2])
                self.addCleanup(fixture.close)
                run_task_writer(fixture, "start", day)
                self._write_f03_work_file(fixture)
                self._commit_f03_boundary(fixture, day=day)

                result = evaluate_checkpoint(fixture.root, FOUNDATIONS[2])

                self.assertTrue(result.passed, result.failed_predicates)

    def test_f03_rejects_executable_board_or_work_file_tree_entry(self) -> None:
        """Catches valid F03 content being accepted with non-ordinary Git modes."""
        for executable_path in (
            ".codearbiter/open-tasks.md",
            "docs/ticket-list-contract.md",
        ):
            with self.subTest(executable_path=executable_path):
                fixture = self._prepared(FOUNDATIONS[2])
                self.addCleanup(fixture.close)
                git(fixture.root, "config", "core.filemode", "false")
                run_task_writer(fixture, "start", "2026-08-02")
                self._write_f03_work_file(fixture)
                git(
                    fixture.root,
                    "add",
                    "--",
                    ".codearbiter/open-tasks.md",
                    "docs/ticket-list-contract.md",
                )
                git(
                    fixture.root,
                    "update-index",
                    "--chmod=+x",
                    "--",
                    executable_path,
                )
                fixture.commit(
                    "start bounded claimant visibility docs task",
                    commit_date="2026-08-02T12:00:00-04:00",
                )
                self.assertTrue(
                    git(fixture.root, "ls-tree", "HEAD", "--", executable_path).stdout.startswith(
                        "100755 blob "
                    )
                )
                self.assertEqual(
                    git(fixture.root, "status", "--porcelain", "--untracked-files=all").stdout,
                    "",
                )

                result = evaluate_checkpoint(fixture.root, FOUNDATIONS[2])

                self.assertFalse(result.passed)
                self.assertEqual(result.failed_predicates, ("task_start_co_commit",))

    def test_f03_rejects_manual_or_malformed_task_start_content(self) -> None:
        cases = {
            "checkbox-without-date": {"stamp": ""},
            "malformed-date": {"stamp": "  (started yesterday)"},
            "completed-instead": {"stamp": "  (done 2026-08-02)"},
            "wrong-task": {"task_id": "academy.docs.9999"},
            "changed-task-body": {"title": "Rewrite all ticket output documentation"},
            "changed-continuation": {},
            "date-not-author-date": {"stamp": "  (started 2026-08-01)"},
        }
        for case, transition in cases.items():
            with self.subTest(case=case):
                fixture = self._prepared(FOUNDATIONS[2])
                self.addCleanup(fixture.close)
                self._manually_start_f03_board(fixture, **transition)
                if case == "completed-instead":
                    board = fixture.root / ".codearbiter/open-tasks.md"
                    board.write_text(
                        board.read_text(encoding="utf-8").replace("- [~]", "- [x]", 1),
                        encoding="utf-8",
                    )
                elif case == "changed-continuation":
                    board = fixture.root / ".codearbiter/open-tasks.md"
                    board.write_text(
                        board.read_text(encoding="utf-8").replace(
                            "Correct the prepared contract",
                            "Rewrite the prepared contract",
                            1,
                        ),
                        encoding="utf-8",
                    )
                self._write_f03_work_file(fixture)
                self._commit_f03_boundary(fixture)

                result = evaluate_checkpoint(fixture.root, FOUNDATIONS[2])

                self.assertFalse(result.passed)
                self.assertEqual(result.failed_predicates, ("task_start_co_commit",))

    def test_f03_accepts_the_real_task_writer_lock_as_ignored_clean_state(self) -> None:
        fixture = self._prepared(FOUNDATIONS[2])
        self.addCleanup(fixture.close)
        run_task_writer(fixture, "start", "2026-08-02")
        self._write_f03_work_file(fixture)
        self._commit_f03_boundary(fixture)
        sidecar = fixture.root / ".codearbiter/open-tasks.md.lock"
        self.assertTrue(sidecar.is_file())
        self.assertEqual(
            git(fixture.root, "status", "--porcelain", "--untracked-files=all").stdout,
            "",
        )
        self.assertTrue(evaluate_checkpoint(fixture.root, FOUNDATIONS[2]).passed)

    def test_f03_rejects_missing_wrong_or_broader_contract_correction(self) -> None:
        cases = {
            "unchanged-work": "Ticket list output shows a claimant for every ticket.",
            "missing-text": "",
            "wrong": "Ticket list output shows a claimant for claimed and open tickets.",
            "broader": (
                "Ticket list output shows the claimant for a claimed ticket and no claimant "
                "for an open ticket."
            ),
        }
        for case, sentence in cases.items():
            with self.subTest(case=case):
                fixture = self._prepared(FOUNDATIONS[2])
                self.addCleanup(fixture.close)
                run_task_writer(fixture, "start", "2026-08-02")
                self._write_f03_work_file(
                    fixture,
                    sentence=sentence,
                    append="\nBroader documentation rewrite.\n" if case == "broader" else "",
                )
                self._commit_f03_boundary(fixture)

                result = evaluate_checkpoint(fixture.root, FOUNDATIONS[2])

                self.assertFalse(result.passed)
                self.assertEqual(result.failed_predicates, ("task_start_co_commit",))

    def test_f03_rejects_wider_history_or_dirty_worktree(self) -> None:
        for case in ("wider-commit", "extra-commit", "dirt"):
            with self.subTest(case=case):
                fixture = self._prepared(FOUNDATIONS[2])
                self.addCleanup(fixture.close)
                run_task_writer(fixture, "start", "2026-08-02")
                self._write_f03_work_file(fixture)
                if case == "wider-commit":
                    note = fixture.root / "learner-notes.md"
                    note.write_text("Outside the F03 boundary.\n", encoding="utf-8")
                    self._commit_f03_boundary(
                        fixture,
                        extra_paths=(str(note.relative_to(fixture.root)),),
                    )
                else:
                    self._commit_f03_boundary(fixture)
                    if case == "extra-commit":
                        fixture.commit("unrelated learner history", allow_empty=True)
                    else:
                        (fixture.root / "uncommitted-note.md").write_text(
                            "The worktree is dirty.\n", encoding="utf-8"
                        )

                result = evaluate_checkpoint(fixture.root, FOUNDATIONS[2])

                self.assertFalse(result.passed)
                self.assertEqual(
                    result.failed_predicates,
                    ("task_start_co_commit",),
                )

    def test_f04_requires_regression_commit_before_a_later_service_repair(self) -> None:
        regression = '''
    def test_claim_rejects_control_characters_in_volunteer_label(self) -> None:
        for volunteer in ("Sam\\nAdmin", "Sam\\tAdmin", "Sam\\x7fAdmin"):
            with self.subTest(volunteer=repr(volunteer)):
                with self.assertRaisesRegex(ValueError, "control characters"):
                    claim_ticket([open_ticket("RQ-104")], "RQ-104", volunteer, fixed_now())

        claimed = claim_ticket([open_ticket("RQ-104")], "RQ-104", "Sam Allen", fixed_now())
        self.assertEqual(claimed[0].claimed_by, "Sam Allen")

'''
        passing_regression = '''
    def test_claim_rejects_control_characters_in_volunteer_label(self) -> None:
        self.assertEqual("Sam\\nAdmin".splitlines()[0], "Sam")

'''
        intended_guard = '''            if any(ord(character) < 32 or ord(character) == 127 for character in volunteer):
                raise ValueError("volunteer must not contain control characters")
'''
        equivalent_guard = '''            if any(character < " " or character == "\\x7f" for character in volunteer):
                raise ValueError("volunteer label contains control characters")
'''
        overbroad_guard = '''            if volunteer:
                raise ValueError("volunteer label contains control characters")
'''
        overbroad_then_decoy_guard = overbroad_guard + intended_guard
        disconnected_regression = '''
    def test_claim_rejects_control_characters_in_volunteer_label(self) -> None:
        controls = ("Sam\\nAdmin", "Sam\\tAdmin", "Sam\\x7fAdmin")
        with self.assertRaisesRegex(ValueError, "control characters"):
            claim_ticket([open_ticket("RQ-104")], "RQ-104", "", fixed_now())

        claim_ticket([open_ticket("RQ-104")], "RQ-104", "Sam Allen", fixed_now())
        claimed_by = "Sam Allen"
        self.assertEqual(claimed_by, "Sam Allen")

'''

        def add_test(path: Path, method: str = regression) -> None:
            text = path.read_text(encoding="utf-8")
            path.write_text(text.replace('\n\nif __name__ == "__main__":', "\n" + method + '\nif __name__ == "__main__":'), encoding="utf-8")

        def repair(path: Path, guard: str = intended_guard) -> None:
            text = path.read_text(encoding="utf-8")
            needle = '            if not volunteer.strip():\n                raise ValueError("volunteer must be non-empty")\n'
            path.write_text(text.replace(needle, needle + guard), encoding="utf-8")

        def focused(fixture: AcademyRepository) -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                [sys.executable, "-m", "unittest", "tests.test_service.TicketTransitionTests.test_claim_rejects_control_characters_in_volunteer_label", "-v"],
                cwd=fixture.root,
                text=True,
                encoding="utf-8",
                capture_output=True,
                check=False,
            )

        cases = (
            "intended",
            "equivalent",
            "untouched",
            "test-only",
            "code-only",
            "same-commit",
            "code-first",
            "unrelated-test",
            "passing-regression",
            "unchanged-defect",
            "overbroad-repair",
            "unreachable-repair",
            "disconnected-regression",
            "overbroad-then-decoy-repair",
        )
        for case in cases:
            with self.subTest(case=case):
                fixture = self._prepared(FOUNDATIONS[3])
                self.addCleanup(fixture.close)
                test_path = fixture.root / "tests/test_service.py"
                code_path = fixture.root / "workshop_queue/service.py"
                if case == "untouched":
                    fixture.commit("no fix yet", allow_empty=True)
                elif case == "test-only":
                    add_test(test_path)
                    fixture.commit("add regression", "tests/test_service.py")
                elif case == "code-only":
                    repair(code_path)
                    fixture.commit("repair only", "workshop_queue/service.py")
                elif case == "same-commit":
                    add_test(test_path)
                    repair(code_path)
                    fixture.commit("test and repair together", "tests/test_service.py", "workshop_queue/service.py")
                elif case == "code-first":
                    repair(code_path)
                    fixture.commit("repair first", "workshop_queue/service.py")
                    add_test(test_path)
                    fixture.commit("late regression", "tests/test_service.py")
                elif case == "unrelated-test":
                    other = fixture.root / "tests/test_unrelated.py"
                    other.write_text("def test_unrelated():\n    assert True\n", encoding="utf-8")
                    fixture.commit("unrelated test", "tests/test_unrelated.py")
                    repair(code_path)
                    fixture.commit("repair", "workshop_queue/service.py")
                elif case == "passing-regression":
                    add_test(test_path, passing_regression)
                    fixture.commit("add passing non-regression", "tests/test_service.py")
                    repair(code_path)
                    fixture.commit("repair", "workshop_queue/service.py")
                elif case == "unchanged-defect":
                    add_test(test_path)
                    fixture.commit("add failing regression", "tests/test_service.py")
                    code_path.write_text(code_path.read_text(encoding="utf-8") + "\n# no behavioral repair\n", encoding="utf-8")
                    fixture.commit("claim repair without behavior", "workshop_queue/service.py")
                elif case == "overbroad-repair":
                    add_test(test_path)
                    fixture.commit("add failing regression", "tests/test_service.py")
                    repair(code_path, overbroad_guard)
                    fixture.commit("reject every volunteer", "workshop_queue/service.py")
                elif case == "unreachable-repair":
                    add_test(test_path)
                    fixture.commit("add failing regression", "tests/test_service.py")
                    text = code_path.read_text(encoding="utf-8")
                    needle = "    raise TicketNotFound(f\"ticket {ticket_id} was not found\")\n\n\ndef complete_ticket"
                    unreachable = '''    if any(ord(character) < 32 or ord(character) == 127 for character in volunteer):
        raise ValueError("volunteer must not contain control characters")
    raise TicketNotFound(f"ticket {ticket_id} was not found")


def complete_ticket'''
                    code_path.write_text(text.replace(needle, unreachable), encoding="utf-8")
                    fixture.commit("add unreachable claimant guard", "workshop_queue/service.py")
                elif case == "disconnected-regression":
                    add_test(test_path, disconnected_regression)
                    fixture.commit("add disconnected regression decoys", "tests/test_service.py")
                    repair(code_path)
                    fixture.commit("repair claimant validation", "workshop_queue/service.py")
                elif case == "overbroad-then-decoy-repair":
                    add_test(test_path)
                    fixture.commit("add failing regression", "tests/test_service.py")
                    repair(code_path, overbroad_then_decoy_guard)
                    fixture.commit("hide broad rejection behind valid guard", "workshop_queue/service.py")
                else:
                    add_test(test_path)
                    test_commit = fixture.commit("add failing regression", "tests/test_service.py")
                    red = focused(fixture)
                    self.assertNotEqual(red.returncode, 0, red.stdout + red.stderr)
                    self.assertIn("FAIL", red.stdout + red.stderr)
                    repair(code_path, equivalent_guard if case == "equivalent" else intended_guard)
                    fixture.commit("repair claimant validation", "workshop_queue/service.py")
                    self.assertEqual(git(fixture.root, "merge-base", "--is-ancestor", test_commit, "HEAD", check=False).returncode, 0)
                    green = focused(fixture)
                    self.assertEqual(green.returncode, 0, green.stdout + green.stderr)

                result = evaluate_checkpoint(fixture.root, FOUNDATIONS[3])
                if case in {"intended", "equivalent"}:
                    self.assertTrue(result.passed, result.failed_predicates)
                else:
                    self.assertFalse(result.passed)

    def test_f04_rejects_ignored_and_disguised_non_cache_worktree_dirt(self) -> None:
        """Only exact exercised cache files may remain outside the two evidence commits."""
        for case, relative, expected in (
            ("ignored-note", "ignored-f04-note.txt", True),
            (
                "nested-disguised-cache",
                "tests/__pycache__/test_service.cpython-311.pyc/payload.pyc",
                True,
            ),
            ("exact-service-cache", "tests/__pycache__/test_service.cpython-311.pyc", False),
        ):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                git(root, "init", "-b", "main")
                git(root, "config", "user.name", "Academy Learner")
                git(root, "config", "user.email", "learner@example.invalid")
                (root / ".gitignore").write_text(
                    "ignored-f04-note.txt\ntests/__pycache__/\n",
                    encoding="utf-8",
                )
                git(root, "add", ".gitignore")
                git(root, "commit", "-m", "baseline")
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(b"not an allowed interpreter cache")

                self.assertEqual(_f04_has_uncommitted_learner_changes(root), expected)

    def test_f04_rejects_unrelated_production_delta_beside_valid_guard(self) -> None:
        """Catches an F04 false green that compares only the repaired function AST."""
        regression = '''
    def test_claim_rejects_control_characters_in_volunteer_label(self) -> None:
        for volunteer in ("Sam\\nAdmin", "Sam\\tAdmin", "Sam\\x7fAdmin"):
            with self.subTest(volunteer=repr(volunteer)):
                with self.assertRaisesRegex(ValueError, "control characters"):
                    claim_ticket([open_ticket("RQ-104")], "RQ-104", volunteer, fixed_now())

        claimed = claim_ticket([open_ticket("RQ-104")], "RQ-104", "Sam Allen", fixed_now())
        self.assertEqual(claimed[0].claimed_by, "Sam Allen")

'''
        intended_guard = '''            if any(ord(character) < 32 or ord(character) == 127 for character in volunteer):
                raise ValueError("volunteer must not contain control characters")
'''
        unrelated_deltas = {
            "function": '''

def unrelated_production_helper() -> bool:
    return True
''',
            "class": '''

class UnrelatedProductionState:
    enabled = True
''',
            "module-executable": '''

UNRELATED_PRODUCTION_STATE = sum((1, 2, 3))
''',
        }

        for label, unrelated in unrelated_deltas.items():
            with self.subTest(label=label):
                fixture = self._prepared(FOUNDATIONS[3])
                self.addCleanup(fixture.close)
                test_path = fixture.root / "tests/test_service.py"
                test_text = test_path.read_text(encoding="utf-8")
                test_path.write_text(
                    test_text.replace(
                        '\n\nif __name__ == "__main__":',
                        "\n" + regression + '\nif __name__ == "__main__":',
                    ),
                    encoding="utf-8",
                )
                fixture.commit("add failing regression", "tests/test_service.py")

                code_path = fixture.root / "workshop_queue/service.py"
                code_text = code_path.read_text(encoding="utf-8")
                needle = '            if not volunteer.strip():\n                raise ValueError("volunteer must be non-empty")\n'
                code_path.write_text(
                    code_text.replace(needle, needle + intended_guard) + unrelated,
                    encoding="utf-8",
                )
                fixture.commit(
                    f"repair plus unrelated {label}", "workshop_queue/service.py"
                )

                result = evaluate_checkpoint(fixture.root, FOUNDATIONS[3])
                self.assertFalse(result.passed, result.failed_predicates)

    def test_f04_binds_an_immutable_regression_to_the_production_import(self) -> None:
        """Catches fake call targets and regression evidence removed before repair."""
        method_template = '''    def test_claim_rejects_control_characters_in_volunteer_label(self) -> None:
{shadow}        for volunteer in ("Sam\\nAdmin", "Sam\\tAdmin", "Sam\\x7fAdmin"):
            with self.subTest(volunteer=repr(volunteer)):
                with self.assertRaisesRegex(ValueError, "control characters"):
                    claim_ticket([open_ticket("RQ-104")], "RQ-104", volunteer, fixed_now())

        claimed = claim_ticket([open_ticket("RQ-104")], "RQ-104", "Sam Allen", fixed_now())
        self.assertEqual(claimed[0].claimed_by, "Sam Allen")

'''
        canonical_method = method_template.format(shadow="")
        shadows = {
            "nested": '''        def claim_ticket(*args, **kwargs):
            return []

''',
            "assigned": '''        claim_ticket = lambda *args, **kwargs: []

''',
            "import-aliased": '''        from workshop_queue.model import Ticket as claim_ticket

''',
            "pattern-captured": '''        match {"bound": object()}:
            case {"bound": claim_ticket}:
                pass

''',
        }
        module_fake = '''
def claim_ticket(*args, **kwargs):
    class FakeClaim:
        claimed_by = "Sam Allen"
    return [FakeClaim()]

'''
        replacement_method = '''    def test_claim_rejects_control_characters_in_volunteer_label(self) -> None:
        self.assertTrue(True)

'''
        intended_guard = '''            if any(ord(character) < 32 or ord(character) == 127 for character in volunteer):
                raise ValueError("volunteer must not contain control characters")
'''

        def insert_method(path: Path, method: str, prefix: str = "") -> None:
            text = path.read_text(encoding="utf-8")
            marker = '    def test_complete_requires_a_claimed_ticket_and_records_resolution(self) -> None:\n'
            path.write_text(
                text.replace(marker, prefix + method + marker), encoding="utf-8"
            )

        def replace_method(path: Path, replacement: str) -> None:
            text = path.read_text(encoding="utf-8")
            start = text.index(
                "    def test_claim_rejects_control_characters_in_volunteer_label"
            )
            end = text.index(
                "    def test_complete_requires_a_claimed_ticket_and_records_resolution",
                start,
            )
            path.write_text(text[:start] + replacement + text[end:], encoding="utf-8")

        def repair(path: Path) -> None:
            text = path.read_text(encoding="utf-8")
            needle = '            if not volunteer.strip():\n                raise ValueError("volunteer must be non-empty")\n'
            path.write_text(
                text.replace(needle, needle + intended_guard), encoding="utf-8"
            )

        cases = {
            "module-fake": (canonical_method, module_fake, None),
            **{
                f"local-{label}": (method_template.format(shadow=shadow), "", None)
                for label, shadow in shadows.items()
            },
            "removed-before-repair": (canonical_method, "", ""),
            "replaced-before-repair": (
                canonical_method,
                "",
                replacement_method,
            ),
        }
        for label, (method, prefix, later_replacement) in cases.items():
            with self.subTest(label=label):
                fixture = self._prepared(FOUNDATIONS[3])
                self.addCleanup(fixture.close)
                test_path = fixture.root / "tests/test_service.py"
                code_path = fixture.root / "workshop_queue/service.py"
                insert_method(test_path, method, prefix)
                fixture.commit("add apparent regression", "tests/test_service.py")
                if later_replacement is not None:
                    replace_method(test_path, later_replacement)
                    fixture.commit("change regression evidence", "tests/test_service.py")
                repair(code_path)
                fixture.commit("repair claimant validation", "workshop_queue/service.py")

                result = evaluate_checkpoint(fixture.root, FOUNDATIONS[3])
                self.assertFalse(result.passed, result.failed_predicates)

    def test_f04_requires_two_path_exact_learner_commits(self) -> None:
        """Catches unrelated production changes hidden in regression or repair commits."""
        regression = '''    def test_claim_rejects_control_characters_in_volunteer_label(self) -> None:
        for volunteer in ("Sam\\nAdmin", "Sam\\tAdmin", "Sam\\x7fAdmin"):
            with self.subTest(volunteer=repr(volunteer)):
                with self.assertRaisesRegex(ValueError, "control characters"):
                    claim_ticket([open_ticket("RQ-104")], "RQ-104", volunteer, fixed_now())

        claimed = claim_ticket([open_ticket("RQ-104")], "RQ-104", "Sam Allen", fixed_now())
        self.assertEqual(claimed[0].claimed_by, "Sam Allen")

'''
        intended_guard = '''            if any(ord(character) < 32 or ord(character) == 127 for character in volunteer):
                raise ValueError("volunteer must not contain control characters")
'''

        for polluted_commit, unrelated_path in (
            ("regression", "workshop_queue/model.py"),
            ("repair", "workshop_queue/store.py"),
        ):
            with self.subTest(polluted_commit=polluted_commit):
                fixture = self._prepared(FOUNDATIONS[3])
                self.addCleanup(fixture.close)
                test_path = fixture.root / "tests/test_service.py"
                test_text = test_path.read_text(encoding="utf-8")
                marker = '    def test_complete_requires_a_claimed_ticket_and_records_resolution(self) -> None:\n'
                test_path.write_text(
                    test_text.replace(marker, regression + marker), encoding="utf-8"
                )
                unrelated = fixture.root / unrelated_path
                if polluted_commit == "regression":
                    unrelated.write_text(
                        unrelated.read_text(encoding="utf-8")
                        + "\n# unrelated regression-commit delta\n",
                        encoding="utf-8",
                    )
                    fixture.commit(
                        "add regression plus unrelated model delta",
                        "tests/test_service.py",
                        unrelated_path,
                    )
                else:
                    fixture.commit("add failing regression", "tests/test_service.py")

                service_path = fixture.root / "workshop_queue/service.py"
                service_text = service_path.read_text(encoding="utf-8")
                needle = '            if not volunteer.strip():\n                raise ValueError("volunteer must be non-empty")\n'
                service_path.write_text(
                    service_text.replace(needle, needle + intended_guard),
                    encoding="utf-8",
                )
                repair_paths = ["workshop_queue/service.py"]
                if polluted_commit == "repair":
                    unrelated.write_text(
                        unrelated.read_text(encoding="utf-8")
                        + "\n# unrelated repair-commit delta\n",
                        encoding="utf-8",
                    )
                    repair_paths.append(unrelated_path)
                fixture.commit("repair claimant validation", *repair_paths)

                result = evaluate_checkpoint(fixture.root, FOUNDATIONS[3])
                self.assertFalse(result.passed, result.failed_predicates)


if __name__ == "__main__":
    unittest.main()
