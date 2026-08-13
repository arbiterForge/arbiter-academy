from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

import academy_engine.checkpoints as checkpoints
from academy_engine.checkpoints import _Attempt, _SemanticContext, _semantic, load_checkpoint
from tests._temporary import RetryingTemporaryDirectory, remove_tree_with_retry


SOURCE = Path(__file__).parents[1]
U04 = "U04-initialize-projects"
REPORT_PATH = ".codearbiter/reports/academy/U04-initialization.md"
GREENFIELD_PATH = ".academy/workspaces/U04-greenfield"
BROWNFIELD_PATH = ".academy/workspaces/U04-brownfield"
COMMON_CHILD_DOCUMENTS = (
    ".codearbiter/CONTEXT.md",
    ".codearbiter/tech-stack.md",
    ".codearbiter/coding-standards.md",
    ".codearbiter/security-controls.md",
    ".codearbiter/open-questions.md",
    ".codearbiter/open-tasks.md",
    ".codearbiter/overrides.log",
)
GREENFIELD_DOCUMENTS = (
    *COMMON_CHILD_DOCUMENTS,
    ".codearbiter/plans/01-architecture-breakdown.md",
    ".codearbiter/plans/02-phased-build-plan.md",
    ".codearbiter/plans/03-task-backlog.md",
    ".codearbiter/decisions/0001-local-storage.md",
)
def git(root: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", *arguments],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


class PrivateU04CheckpointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = RetryingTemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        git(self.root, "init", "-b", "main")
        git(self.root, "config", "user.name", "U04 Fixture")
        git(self.root, "config", "user.email", "u04-fixture@example.invalid")
        (self.root / ".gitignore").write_text(".academy/\n", encoding="utf-8")
        (self.root / "README.md").write_text("root fixture\n", encoding="utf-8")
        git(self.root, "add", ".gitignore", "README.md")
        git(self.root, "commit", "-m", "root base")
        self.base = git(self.root, "rev-parse", "HEAD")
        self.branch = f"academy/{U04}/1"
        git(self.root, "switch", "-c", self.branch)
        git(self.root, "commit", "--allow-empty", "-m", "prepare U04")
        self.prepared = git(self.root, "rev-parse", "HEAD")

    def _child(self, relative_path: str, kind: str) -> tuple[str, str, str]:
        child = self.root / relative_path
        child.mkdir(parents=True)
        git(child, "init", "-b", "main")
        git(child, "config", "user.name", "U04 Child Fixture")
        git(child, "config", "user.email", "u04-child@example.invalid")
        seed_path, seed_contents = (
            ("README.md", "# Greenfield fixture\n")
            if kind == "greenfield"
            else (
                "workshop_queue/legacy_queue.py",
                "def summarize(items: list[str]) -> str:\n    return \",\".join(items)\n",
            )
        )
        seed = child / seed_path
        seed.parent.mkdir(parents=True, exist_ok=True)
        seed.write_text(seed_contents, encoding="utf-8", newline="\n")
        git(child, "add", "--", seed_path)
        git(child, "commit", "-m", f"seed {kind} fixture")
        contents = {
            ".codearbiter/CONTEXT.md": (
                f"---\narbiter: enabled\nstage: 1\n---\n<!--INITIALIZED-->\n\n"
                f"# {kind.title()} context\n\nDurable local scope.\n"
            ),
            ".codearbiter/tech-stack.md": "# Technology\n\nPython standard library.\n",
            ".codearbiter/coding-standards.md": "# Coding standards\n\nTest first.\n",
            ".codearbiter/security-controls.md": "# Security controls\n\nNo credentials.\n",
            ".codearbiter/open-questions.md": "# Open questions\n\nNo open questions.\n",
            ".codearbiter/open-tasks.md": "# Open tasks\n\nNo open tasks.\n",
            ".codearbiter/overrides.log": "# codeArbiter override log\n",
        }
        if kind == "greenfield":
            contents.update(
                {
                    ".codearbiter/plans/01-architecture-breakdown.md": (
                        "# Architecture breakdown\n\nBounded components.\n"
                    ),
                    ".codearbiter/plans/02-phased-build-plan.md": (
                        "# Phased build plan\n\nDeliver incrementally.\n"
                    ),
                    ".codearbiter/plans/03-task-backlog.md": (
                        "# Task backlog\n\nNo unresolved tasks.\n"
                    ),
                    ".codearbiter/decisions/0001-local-storage.md": (
                        "---\nstatus: accepted\n---\n# Local storage\n\nUse local storage.\n"
                    ),
                }
            )
        for path, value in contents.items():
            target = child / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(value, encoding="utf-8", newline="\n")
        git(child, "add", ".")
        git(child, "commit", "-m", f"initialize {kind} governance")
        head = git(child, "rev-parse", "HEAD")
        tree = git(child, "rev-parse", "HEAD^{tree}")
        context = subprocess.run(
            ["git", "show", f"{head}:.codearbiter/CONTEXT.md"],
            cwd=child,
            check=True,
            capture_output=True,
        ).stdout
        return head, tree, hashlib.sha256(context).hexdigest()

    def _binding(self, relative_path: str) -> tuple[str, str, str]:
        child = self.root / relative_path
        head = git(child, "rev-parse", "HEAD")
        tree = git(child, "rev-parse", "HEAD^{tree}")
        context = subprocess.run(
            ["git", "show", f"{head}:.codearbiter/CONTEXT.md"],
            cwd=child,
            check=True,
            capture_output=True,
        ).stdout
        return head, tree, hashlib.sha256(context).hexdigest()

    def _report(
        self,
        greenfield: tuple[str, str, str],
        brownfield: tuple[str, str, str],
    ) -> str:
        return "\n".join(
            (
                "# U04 initialization evidence",
                "",
                "## Greenfield",
                f"Path: {GREENFIELD_PATH}",
                f"HEAD: {greenfield[0]}",
                f"Tree: {greenfield[1]}",
                f"CONTEXT-SHA256: {greenfield[2]}",
                "",
                "## Brownfield",
                f"Path: {BROWNFIELD_PATH}",
                f"HEAD: {brownfield[0]}",
                f"Tree: {brownfield[1]}",
                f"CONTEXT-SHA256: {brownfield[2]}",
                "",
                "## Route evidence",
                (
                    "Greenfield-Plans: .codearbiter/plans/01-architecture-breakdown.md; "
                    ".codearbiter/plans/02-phased-build-plan.md; "
                    ".codearbiter/plans/03-task-backlog.md"
                ),
                (
                    "Brownfield-Context: .codearbiter/CONTEXT.md; "
                    ".codearbiter/tech-stack.md; .codearbiter/coding-standards.md; "
                    ".codearbiter/security-controls.md"
                ),
                "",
            )
        )

    def _commit_report(self, context: _SemanticContext, report_text: str) -> _SemanticContext:
        report = self.root / REPORT_PATH
        report.write_text(report_text, encoding="utf-8", newline="\n")
        git(self.root, "add", "--", REPORT_PATH)
        git(self.root, "commit", "-m", "update U04 initialization evidence")
        head = git(self.root, "rev-parse", "HEAD")
        return _SemanticContext(
            self.root,
            _Attempt(self.branch, 1, self.prepared, self.base, head),
            context.predicate,
        )

    def _context(self) -> _SemanticContext:
        greenfield = self._child(GREENFIELD_PATH, "greenfield")
        brownfield = self._child(BROWNFIELD_PATH, "brownfield")
        report = self.root / REPORT_PATH
        report.parent.mkdir(parents=True)
        report.write_text(self._report(greenfield, brownfield), encoding="utf-8", newline="\n")
        git(self.root, "add", "--", REPORT_PATH)
        git(self.root, "commit", "-m", "record U04 initialization evidence")
        head = git(self.root, "rev-parse", "HEAD")
        predicate = load_checkpoint(
            SOURCE / "academy/checkpoints/U04-initialize-projects.json"
        ).predicates[0]
        return _SemanticContext(
            self.root,
            _Attempt(self.branch, 1, self.prepared, self.base, head),
            predicate,
        )

    def test_accepts_two_bound_clean_initialized_projects(self) -> None:
        self.assertTrue(_semantic(self._context()))

    def test_canonical_writer_renders_the_exact_report_from_clean_child_heads(self) -> None:
        """Catches asking a learner to hand-compose verifier-sensitive report bytes."""
        greenfield = self._child(GREENFIELD_PATH, "greenfield")
        brownfield = self._child(BROWNFIELD_PATH, "brownfield")
        writer = getattr(checkpoints, "write_u04_initialization_report", None)
        self.assertTrue(
            callable(writer),
            "U04 needs one canonical report writer instead of a prose-only template.",
        )

        destination = writer(self.root)

        self.assertEqual(destination, self.root / REPORT_PATH)
        self.assertEqual(destination.read_bytes(), self._report(greenfield, brownfield).encode())

    def test_canonical_writer_refuses_uncommitted_child_governance(self) -> None:
        """Catches binding a dirty child head before its generated docs are committed."""
        self._child(GREENFIELD_PATH, "greenfield")
        self._child(BROWNFIELD_PATH, "brownfield")
        child = self.root / BROWNFIELD_PATH
        (child / ".codearbiter/tech-stack.md").write_text(
            "# Technology\n\nUncommitted correction.\n", encoding="utf-8", newline="\n"
        )
        writer = getattr(checkpoints, "write_u04_initialization_report", None)
        self.assertTrue(callable(writer), "U04 canonical report writer is missing.")

        with self.assertRaisesRegex(ValueError, "clean and committed"):
            writer(self.root)

    def test_rejects_only_one_child_project(self) -> None:
        context = self._context()
        remove_tree_with_retry(self.root / BROWNFIELD_PATH)
        self.assertFalse(_semantic(context))

    def test_rejects_swapped_greenfield_and_brownfield_bindings(self) -> None:
        context = self._context()
        context = self._commit_report(
            context,
            self._report(
                self._binding(BROWNFIELD_PATH), self._binding(GREENFIELD_PATH)
            ),
        )
        self.assertFalse(_semantic(context))

    def test_rejects_children_swapped_after_their_routes_complete(self) -> None:
        """The paths must remain bound to their prepared greenfield/brownfield seeds."""
        context = self._context()
        greenfield = self.root / GREENFIELD_PATH
        brownfield = self.root / BROWNFIELD_PATH
        exchange = self.root / ".academy" / "workspaces" / "exchange"
        greenfield.rename(exchange)
        brownfield.rename(greenfield)
        exchange.rename(brownfield)
        context = self._commit_report(
            context,
            self._report(
                self._binding(GREENFIELD_PATH), self._binding(BROWNFIELD_PATH)
            ),
        )
        self.assertFalse(_semantic(context))

    def test_rejects_symlinked_child_context(self) -> None:
        context = self._context()
        child = self.root / GREENFIELD_PATH
        external = tempfile.TemporaryDirectory()
        self.addCleanup(external.cleanup)
        external_context = Path(external.name) / "CONTEXT.md"
        external_context.write_text("# External context\n", encoding="utf-8")
        child_context = child / ".codearbiter/CONTEXT.md"
        child_context.unlink()
        try:
            child_context.symlink_to(external_context)
        except OSError as error:
            self.skipTest(f"symlink/reparse creation unavailable: {error}")
        git(child, "add", ".codearbiter/CONTEXT.md")
        git(child, "commit", "-m", "replace context with symlink")
        context = self._commit_report(
            context,
            self._report(self._binding(GREENFIELD_PATH), self._binding(BROWNFIELD_PATH)),
        )
        self.assertEqual(git(child, "status", "--porcelain", "--untracked-files=all"), "")
        self.assertFalse(_semantic(context))

    def test_rejects_dirty_or_untracked_child_state(self) -> None:
        context = self._context()
        (self.root / BROWNFIELD_PATH / "untracked.txt").write_text("dirty\n", encoding="utf-8")
        self.assertFalse(_semantic(context))

    def test_rejects_child_commit_after_report_binding(self) -> None:
        context = self._context()
        child = self.root / BROWNFIELD_PATH
        (child / ".codearbiter/CONTEXT.md").write_text("# Later context\n", encoding="utf-8")
        git(child, "add", ".codearbiter/CONTEXT.md")
        git(child, "commit", "-m", "change context after report")
        self.assertFalse(_semantic(context))

    def test_rejects_report_without_reconciliation_inputs(self) -> None:
        context = self._context()
        report = self._report(self._binding(GREENFIELD_PATH), self._binding(BROWNFIELD_PATH))
        context = self._commit_report(
            context,
            report.replace(
                "Greenfield-Plans: .codearbiter/plans/01-architecture-breakdown.md; "
                ".codearbiter/plans/02-phased-build-plan.md; "
                ".codearbiter/plans/03-task-backlog.md\n",
                "",
            ),
        )
        self.assertFalse(_semantic(context))

    def test_rejects_greenfield_plans_moved_under_decisions(self) -> None:
        """Catches validating synthetic paths that ca-decompose never generates."""
        context = self._context()
        child = self.root / GREENFIELD_PATH
        source = child / ".codearbiter/plans/01-architecture-breakdown.md"
        destination = child / ".codearbiter/decisions/01-architecture-breakdown.md"
        destination.parent.mkdir(parents=True, exist_ok=True)
        source.replace(destination)
        git(child, "add", "--all")
        git(child, "commit", "-m", "move architecture to the wrong location")
        context = self._commit_report(
            context,
            self._report(self._binding(GREENFIELD_PATH), self._binding(BROWNFIELD_PATH)),
        )

        self.assertFalse(_semantic(context))

    def test_rejects_unresolved_confirmation_in_child_evidence(self) -> None:
        context = self._context()
        child = self.root / GREENFIELD_PATH
        decision_log = child / ".codearbiter/decisions/decision-log.md"
        decision_log.write_text(
            "# Decision log\n\n[CONFIRM-01] Confirm owner.\n", encoding="utf-8"
        )
        git(child, "add", ".codearbiter/decisions/decision-log.md")
        git(child, "commit", "-m", "leave unresolved confirmation")
        context = self._commit_report(
            context,
            self._report(self._binding(GREENFIELD_PATH), self._binding(BROWNFIELD_PATH)),
        )
        self.assertFalse(_semantic(context))

    def test_rejects_report_claiming_host_or_human_proof(self) -> None:
        context = self._context()
        report = self._report(self._binding(GREENFIELD_PATH), self._binding(BROWNFIELD_PATH))
        context = self._commit_report(
            context,
            report + "Host command and human choice were proved.\n",
        )
        self.assertFalse(_semantic(context))

    def test_rejects_dirty_root_worktree(self) -> None:
        context = self._context()
        (self.root / "README.md").write_text("dirty root\n", encoding="utf-8")
        self.assertFalse(_semantic(context))

    def test_u04_checkpoint_and_scenario_name_the_two_fixture_contract(self) -> None:
        checkpoint = json.loads(
            (SOURCE / "academy/checkpoints/U04-initialize-projects.json").read_text(
                encoding="utf-8"
            )
        )
        scenario = json.loads(
            (SOURCE / "academy/scenarios/U04-initialize-projects/files/scenario.json").read_text(
                encoding="utf-8"
            )
        )
        schema = json.loads(
            (SOURCE / "academy/checkpoint.schema.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            checkpoint["predicates"],
            [
                {
                    "id": "initialized_projects",
                    "type": "lab_semantics",
                    "profile": "initialized_projects",
                    "greenfield": GREENFIELD_PATH,
                    "brownfield": BROWNFIELD_PATH,
                    "report": REPORT_PATH,
                }
            ],
        )
        self.assertEqual(
            scenario,
            {
                "schema_version": 1,
                "lab_id": U04,
                "operation": "two_fixture_initialization",
                "target": "greenfield-and-brownfield",
                "starting_condition": "projects-absent",
            },
        )
        properties = schema["properties"]["predicates"]["items"]["properties"]
        self.assertIn("initialized_projects", properties["profile"]["enum"])
        self.assertEqual(properties["greenfield"], {"$ref": "#/$defs/path"})
        self.assertEqual(properties["brownfield"], {"$ref": "#/$defs/path"})
        self.assertLessEqual(set(checkpoint["predicates"][0]), set(properties))


if __name__ == "__main__":
    unittest.main()
