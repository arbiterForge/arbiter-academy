from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from academy_engine.checkpoints import Predicate, _Attempt, _SemanticContext, _semantic, evaluate_checkpoint
from academy_engine import curriculum
from academy_engine.lesson_actions import load_action_manifest
from academy_engine.preview import load_preview_manifest
from academy_engine.scenario import prepare_lab
from scripts import build_preview_site


SOURCE = Path(__file__).parents[1]
U01 = "U01-autonomous-sprint"
U01_ACTION_IDS = (
    "U01-confirm-fork-boundary",
    "U01-prepare-attempt",
    "U01-inspect-scenario",
    "U01-run-sprint",
    "U01-approve-or-decline-spec",
    "U01-approve-or-decline-plan",
    "U01-inspect-artifacts",
    "U01-check-status",
    "U01-return-base",
    "U01-reset-retry",
)
U01_HEADINGS = (
    "## Know before you begin",
    "## What you will prove",
    "## Prepare safely",
    "## Practice",
    "## Recognize success",
    "## Check",
    "## Recover or continue",
    "## Understand the mechanism",
)


class U01GuidedContractTests(unittest.TestCase):
    def test_u01_public_guide_has_the_shared_eight_heading_action_contract(self) -> None:
        """Catches U01 drifting into a bespoke or partial public lesson."""
        guide = (
            SOURCE / "academy/tracks/power-user/U01-autonomous-sprint.md"
        ).read_text(encoding="utf-8")
        normalized = " ".join(guide.split())
        positions = [guide.index(heading) for heading in U01_HEADINGS]
        self.assertEqual(positions, sorted(positions))
        self.assertNotIn("```", guide)
        self.assertIn("The website remains the primary lesson surface.", normalized)
        release = load_preview_manifest(SOURCE).release.removeprefix("preview-")
        self.assertIn(f"guided, runnable lesson in Preview {release}", normalized)
        self.assertIn("non-destructive numbered retry", normalized)
        self.assertIn("docs/academy-sprint-summary.md", normalized)
        self.assertIn("It does not authenticate approval.", normalized)
        self.assertIn("opens a pull request", normalized)
        self.assertIn("does not prove that a pull request was created", normalized)
        self.assertNotIn("It does not push.", guide)
        for action_id in U01_ACTION_IDS:
            with self.subTest(action_id=action_id):
                self.assertIn(f"{{{{action:{action_id}}}}}", guide)

    def test_u01_action_manifest_keeps_execution_surfaces_and_limits_explicit(self) -> None:
        """Catches host syntax, shell markers, or public-boundary claims regressing."""
        manifest = load_action_manifest(SOURCE, U01)
        self.assertEqual(tuple(action.id for action in manifest.actions), U01_ACTION_IDS)
        by_id = {action.id: action for action in manifest.actions}

        sprint = by_id["U01-run-sprint"]
        self.assertEqual(sprint.actor, "agent")
        self.assertEqual(
            {(variant.host, variant.command) for variant in sprint.variants},
            {
                ("claude-code", "/ca:sprint academy-sprint"),
                ("codex", "$ca-sprint academy-sprint"),
                ("pi", "/ca-sprint academy-sprint"),
                ("pi", "/skill:ca-sprint academy-sprint"),
            },
        )
        self.assertTrue(all(not variant.command.startswith("!") for variant in sprint.variants))
        self.assertIn("opens a pull request", sprint.expected_result.casefold())
        self.assertIn("never merges", sprint.expected_result.casefold())
        self.assertIn("proposed specification and its derived plan", sprint.instruction)
        plan_gate = by_id["U01-approve-or-decline-plan"]
        self.assertEqual((plan_gate.actor, plan_gate.surface), ("learner", "active-harness"))
        self.assertIn("plan", plan_gate.instruction.casefold())
        self.assertIn("autonomous", plan_gate.expected_result.casefold())
        self.assertIn("approve only", plan_gate.instruction.casefold())
        self.assertIn(
            "no product-code, test, dependency, or remote changes",
            plan_gate.instruction.casefold(),
        )
        self.assertIn("fork-only pull-request terminal", plan_gate.instruction.casefold())
        self.assertIn("approved plan", plan_gate.expected_result.casefold())
        self.assertIn("plan revision", plan_gate.expected_result.casefold())
        self.assertIn("proposed specification and derived plan", plan_gate.recovery.casefold())

        for action_id in ("U01-prepare-attempt", "U01-check-status", "U01-reset-retry"):
            action = by_id[action_id]
            with self.subTest(action_id=action_id):
                self.assertEqual(
                    {variant.operating_system for variant in action.variants},
                    {"windows", "macos", "linux"},
                )
                self.assertTrue(
                    all(variant.surface == "native-terminal" for variant in action.variants)
                )
                self.assertTrue(all(not variant.command.startswith("!") for variant in action.variants))
                self.assertIn("Academy", action.expected_result)
                self.assertTrue(
                    all("preview-0.24" in variant.command for variant in action.variants)
                )

        inspect = by_id["U01-inspect-scenario"]
        self.assertEqual({variant.surface for variant in inspect.variants}, {"native-terminal", "harness"})
        self.assertTrue(
            all(
                variant.command.startswith("!")
                for variant in inspect.variants
                if variant.surface == "harness"
            )
        )

        self.assertNotIn("unavailable", by_id["U01-check-status"].title.casefold())
        self.assertNotIn("unavailable", by_id["U01-reset-retry"].title.casefold())

        return_base = by_id["U01-return-base"]
        for variant in return_base.variants:
            with self.subTest(return_base_variant=variant.id):
                self.assertIn("git status --short", variant.command)
                self.assertIn("exit 1", variant.command)
                self.assertIn("git switch main", variant.command)
                self.assertLess(
                    variant.command.index("exit 1"),
                    variant.command.index("git switch main"),
                )

    def test_u01_public_source_parses_and_renders_with_the_shared_renderer(self) -> None:
        """Catches a public Power User source contract becoming unparseable or bespoke HTML."""
        lab = curriculum._parse_lab(
            SOURCE / "academy/tracks/power-user/U01-autonomous-sprint.md"
        )
        self.assertEqual(lab.id, U01)
        self.assertEqual(lab.scenario_command, "{{action:U01-prepare-attempt}}")
        self.assertEqual(lab.checkpoint_command, "{{action:U01-check-status}}")

        document = build_preview_site._read_markdown_document(
            SOURCE,
            Path("academy/tracks/power-user/U01-autonomous-sprint.md"),
            U01,
            require_h1=True,
        )
        self.assertEqual(document["referenced_actions"], U01_ACTION_IDS)
        content = str(document["content"])
        self.assertEqual(content.count('class="lesson-action"'), len(U01_ACTION_IDS))
        self.assertIn('data-action-id="U01-run-sprint"', content)
        self.assertIn('data-copy-target="command-U01-run-sprint-codex"', content)
        self.assertNotIn("{{action:", content)

    def test_u01_through_u07_are_the_power_user_labs_in_the_preview_zero_twenty_public_boundary(self) -> None:
        """The complete public Power User track includes the U07 capstone."""
        release = load_preview_manifest(SOURCE)
        self.assertIn(U01, release.available_labs)
        self.assertIn(U01, release.runnable_labs)
        self.assertIn(U01, release.guided_labs)
        self.assertIn("U02-override-audit-metrics", release.available_labs)
        self.assertIn("U02-override-audit-metrics", release.runnable_labs)
        self.assertIn("U02-override-audit-metrics", release.guided_labs)
        self.assertIn("U03-refactor-chore-release", release.guided_labs)
        self.assertIn("U04-initialize-projects", release.available_labs)
        self.assertIn("U04-initialize-projects", release.runnable_labs)
        self.assertIn("U04-initialize-projects", release.guided_labs)
        self.assertIn("U05-debug-spike-conflict", release.available_labs)
        self.assertIn("U05-debug-spike-conflict", release.runnable_labs)
        self.assertIn("U05-debug-spike-conflict", release.guided_labs)
        self.assertIn("U06-preview-and-advanced-surfaces", release.available_labs)
        self.assertIn("U06-preview-and-advanced-surfaces", release.runnable_labs)
        self.assertIn("U06-preview-and-advanced-surfaces", release.guided_labs)
        self.assertIn("U07-capstone", release.available_labs)
        self.assertIn("U07-capstone", release.runnable_labs)
        self.assertIn("U07-capstone", release.guided_labs)

    def test_u01_declares_the_bounded_sprint_fixture_and_positive_predicate(self) -> None:
        """Catches the U01 guide, scenario, and durable Check contract drifting apart."""
        scenario = json.loads(
            (SOURCE / "academy/scenarios/U01-autonomous-sprint/files/scenario.json").read_text(
                encoding="utf-8"
            )
        )
        checkpoint = json.loads(
            (SOURCE / "academy/checkpoints/U01-autonomous-sprint.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            scenario,
            {
                "schema_version": 1,
                "lab_id": U01,
                "operation": "autonomous_sprint",
                "target": "academy-sprint",
                "starting_condition": "approval-required",
                "deliverable": "docs/academy-sprint-summary.md",
                "title": "Operate a bounded autonomous sprint",
                "required_topics": [
                    "approval boundary",
                    "SMARTS decision trail",
                    "hard-gate stop",
                ],
            },
        )
        self.assertEqual(
            checkpoint["predicates"],
            [
                {
                    "id": "approved_sprint_decisions",
                    "type": "lab_semantics",
                    "profile": "sprint_decisions",
                    "spec": ".codearbiter/specs/academy-sprint.md",
                    "plan": ".codearbiter/plans/academy-sprint.md",
                    "sprint_log": ".codearbiter/sprint-log.md",
                    "brief": "training_scenarios/U01-sprint-brief.json",
                    "deliverable": "docs/academy-sprint-summary.md",
                }
            ],
        )


class U01SprintDecisionSemanticsTests(unittest.TestCase):
    """The sprint Check proves durable evidence, not a host transcript or approval claim."""

    _predicate_data = {
        "profile": "sprint_decisions",
        "spec": ".codearbiter/specs/academy-sprint.md",
        "plan": ".codearbiter/plans/academy-sprint.md",
        "sprint_log": ".codearbiter/sprint-log.md",
        "brief": "training_scenarios/U01-sprint-brief.json",
        "deliverable": "docs/academy-sprint-summary.md",
    }

    def _git(self, root: Path, *arguments: str) -> str:
        result = subprocess.run(
            ["git", *arguments],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        return result.stdout.strip()

    def _context(
        self,
        root: Path,
        *,
        prepared_brief: dict[str, object] | None = None,
        extra_packet_path: bool = False,
    ) -> _SemanticContext:
        (root / ".codearbiter").mkdir()
        (root / "training_scenarios").mkdir()
        (root / ".codearbiter/sprint-log.md").write_text(
            "# Sprint log — Academy fixture\n\nAppend-only.\n",
            encoding="utf-8",
        )
        brief = prepared_brief if prepared_brief is not None else {
            "schema_version": 1,
            "lab_id": U01,
            "deliverable": "docs/academy-sprint-summary.md",
            "title": "Operate a bounded autonomous sprint",
            "required_topics": [
                "approval boundary",
                "SMARTS decision trail",
                "hard-gate stop",
            ],
        }
        (root / "training_scenarios/U01-sprint-brief.json").write_text(
            json.dumps(brief)
            + "\n",
            encoding="utf-8",
        )
        self._git(root, "init", "-b", "main")
        self._git(root, "config", "user.name", "Academy Learner")
        self._git(root, "config", "user.email", "learner@example.invalid")
        self._git(root, "remote", "add", "origin", "https://github.com/academy-learner/arbiter-academy.git")
        self._git(root, "remote", "add", "upstream", "https://github.com/arbiterForge/arbiter-academy.git")
        self._git(root, "remote", "set-url", "--push", "upstream", "DISABLED")
        self._git(root, "add", ".")
        self._git(root, "commit", "-m", "academy: prepare U01 base")
        prepared = self._git(root, "rev-parse", "HEAD")
        self._git(root, "switch", "-c", "academy/U01-autonomous-sprint/1")

        head = self._commit_packet(root, extra_packet_path=extra_packet_path)
        return _SemanticContext(
            root,
            _Attempt("academy/U01-autonomous-sprint/1", 1, prepared, prepared, head),
            Predicate("approved_sprint_decisions", "lab_semantics", self._predicate_data),
        )

    def _commit_packet(
        self,
        root: Path,
        *,
        extra_packet_path: bool = False,
        scope_suffix: str = "",
        scope_clause: str | None = None,
    ) -> str:
        (root / ".codearbiter/specs").mkdir(exist_ok=True)
        (root / ".codearbiter/plans").mkdir(exist_ok=True)
        (root / "docs").mkdir(exist_ok=True)
        scope_clause = scope_clause or (
            "The allowed final commit contains docs/academy-sprint-summary.md. It may push only the learner fork branch through the CodeArbiter pull request terminal. It never pushes directly to upstream and never merges. It does not change product code, tests, dependencies, or remotes."
        )
        (root / ".codearbiter/specs/academy-sprint.md").write_text(
            "# Academy sprint: operator guide\n\n"
            "## Problem\nNew operators need a compact explanation of the bounded autonomous sprint.\n\n"
            f"## Scope\n{scope_clause}"
            f"{scope_suffix}\n\n"
            "## Acceptance criteria\n"
            "1. The guide names the human approval boundary.\n"
            "2. The guide distinguishes SMARTS decisions from hard-gate stops.\n\n"
            "## Open questions\nNone.\n",
            encoding="utf-8",
        )
        (root / ".codearbiter/plans/academy-sprint.md").write_text(
            "# Academy sprint plan\n\n"
            "## Acceptance criteria ledger\n"
            "- AC-01: The guide names the human approval boundary.\n"
            "- AC-02: The guide distinguishes SMARTS decisions from hard-gate stops.\n\n"
            "## Tasks\n"
            "| ID | Path(s) | Verification | Maps to | Status |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| T-01 | docs/academy-sprint-summary.md | inspect headings and scope | AC-01, AC-02 | ACCEPTED |\n\n"
            "## MVP slice\nT-01\n",
            encoding="utf-8",
        )
        (root / "docs/academy-sprint-summary.md").write_text(
            "# Operate a bounded autonomous sprint\n\n"
            "## Approval boundary\nA person approves the spec and plan before autonomous work starts.\n\n"
            "## SMARTS decision trail\nNon-hard decisions are recorded in the append-only sprint log.\n\n"
            "## Hard-gate stop\nSecurity, destructive actions, overrides, unresolved confirmations, and merges remain stops.\n",
            encoding="utf-8",
        )
        sprint_log = root / ".codearbiter/sprint-log.md"
        sprint_log.write_text(
            sprint_log.read_text(encoding="utf-8")
            + "\n## SD-U01 — academy-sprint documentation scope · confidence: high · intent: per academy sprint brief\n"
            "- **Point:** Keep the exercise documentation-only.\n"
            "- **Options:** expand into product work; keep the bounded guide.\n"
            "- **SMARTS:** Reliable and Testable favor the bounded guide.\n"
            "- **Chosen:** keep the bounded guide.\n",
            encoding="utf-8",
        )
        paths = [
            ".codearbiter/specs/academy-sprint.md",
            ".codearbiter/plans/academy-sprint.md",
            ".codearbiter/sprint-log.md",
            "docs/academy-sprint-summary.md",
        ]
        if extra_packet_path:
            (root / "README.md").write_text("out of scope\n", encoding="utf-8")
            paths.append("README.md")
        self._git(root, "add", *paths)
        self._git(root, "commit", "-m", "docs: record bounded Academy sprint")
        return self._git(root, "rev-parse", "HEAD")

    def test_sprint_decisions_accepts_one_bounded_committed_sprint_packet(self) -> None:
        """Catches U01 remaining permanently unable to recognize its real durable evidence."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            context = self._context(root)

            self.assertTrue(_semantic(context))

    def test_sprint_decisions_rejects_a_rewritten_audit_prefix(self) -> None:
        """Catches a plausible packet that rewrites instead of appending to sprint history."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            context = self._context(root)
            log = root / ".codearbiter/sprint-log.md"
            log.write_text(log.read_text(encoding="utf-8").replace("Append-only.", "Rewritten."), encoding="utf-8")
            self._git(root, "add", ".codearbiter/sprint-log.md")
            self._git(root, "commit", "-m", "rewrite sprint history")
            head = self._git(root, "rev-parse", "HEAD")
            context = _SemanticContext(
                root,
                _Attempt(context.attempt.branch, 1, context.attempt.prepared, context.attempt.base, head),
                context.predicate,
            )

            self.assertFalse(_semantic(context))

    def test_sprint_decisions_rejects_a_missing_logged_decision_in_an_otherwise_bounded_packet(self) -> None:
        """Catches a packet that looks complete but omits the durable SMARTS record."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            context = self._context(root)
            self._git(root, "reset", "--soft", "HEAD^")
            log = root / ".codearbiter/sprint-log.md"
            log.write_text(
                log.read_text(encoding="utf-8").replace(" · intent: per academy sprint brief", ""),
                encoding="utf-8",
            )
            self._git(root, "add", ".")
            self._git(root, "commit", "-m", "docs: omit sprint intent")
            head = self._git(root, "rev-parse", "HEAD")
            context = _SemanticContext(
                root,
                _Attempt(context.attempt.branch, 1, context.attempt.prepared, context.attempt.base, head),
                context.predicate,
            )

            self.assertFalse(_semantic(context))

    def test_sprint_decisions_rejects_a_brief_tampered_after_prepare(self) -> None:
        """Catches a prepared contract whose seal differs before the valid packet exists."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            context = self._context(root, prepared_brief={"tampered": True})

            self.assertFalse(_semantic(context))

    def test_sprint_decisions_rejects_an_unrelated_committed_path(self) -> None:
        """Catches scope creep in the sole otherwise-valid sprint packet commit."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            context = self._context(root, extra_packet_path=True)

            self.assertFalse(_semantic(context))

    def test_sprint_decisions_accepts_the_fork_pr_terminal_but_rejects_direct_upstream_push(self) -> None:
        """The real sprint lane opens a PR, never a direct upstream push or merge."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            context = self._context(root)
            self.assertTrue(_semantic(context))
            self._git(root, "reset", "--soft", "HEAD^")
            head = self._commit_packet(
                root,
                scope_clause=(
                    "The allowed final commit contains docs/academy-sprint-summary.md. It may push only the learner fork branch through the CodeArbiter pull request terminal. It pushes directly to upstream and never merges. It does not change product code, tests, dependencies, or remotes."
                ),
            )
            context = _SemanticContext(
                root,
                _Attempt(context.attempt.branch, 1, context.attempt.prepared, context.attempt.base, head),
                context.predicate,
            )

            self.assertFalse(_semantic(context))

    def test_sprint_decisions_rejects_an_upstream_that_can_receive_a_push(self) -> None:
        """A real sprint PR may push the learner fork, never the upstream repository."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            context = self._context(root)
            self._git(root, "remote", "set-url", "--push", "upstream", "https://github.com/arbiterForge/arbiter-academy.git")
            self.assertFalse(_semantic(context))

    def test_prepare_materializes_the_sealed_u01_brief(self) -> None:
        """Catches a U01 Prepare that omits the verifier-owned sprint brief."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "learner"
            root.mkdir()
            shutil.copytree(SOURCE / "academy", root / "academy")
            shutil.copytree(SOURCE / "academy_engine", root / "academy_engine")
            shutil.copytree(SOURCE / ".codearbiter", root / ".codearbiter")
            (root / "scripts").mkdir()
            shutil.copy2(SOURCE / "scripts/academy.py", root / "scripts/academy.py")
            self._git(root, "init", "-b", "main")
            self._git(root, "config", "user.name", "Academy Learner")
            self._git(root, "config", "user.email", "learner@example.invalid")
            self._git(root, "add", ".")
            self._git(root, "commit", "-m", "base")
            self._git(root, "remote", "add", "origin", "https://github.com/learner/arbiter-academy.git")
            self._git(root, "remote", "add", "upstream", "https://github.com/arbiterForge/arbiter-academy.git")
            self._git(root, "remote", "set-url", "--push", "upstream", "DISABLED")

            prepared = prepare_lab(root, U01)

            descriptor = json.loads(
                (root / "training_scenarios/U01-autonomous-sprint.json").read_text(encoding="utf-8")
            )
            brief = json.loads(
                (root / "training_scenarios/U01-sprint-brief.json").read_text(encoding="utf-8")
            )
            self.assertEqual(prepared.branch, "academy/U01-autonomous-sprint/1")
            self.assertEqual(descriptor["deliverable"], "docs/academy-sprint-summary.md")
            self.assertEqual(brief["title"], "Operate a bounded autonomous sprint")
            self.assertEqual(
                brief["required_topics"],
                ["approval boundary", "SMARTS decision trail", "hard-gate stop"],
            )

    def test_full_check_accepts_the_prepared_u01_packet(self) -> None:
        """Catches a source-only semantic pass that cannot survive Academy preparation checks."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "learner"
            root.mkdir()
            shutil.copytree(SOURCE / "academy", root / "academy")
            shutil.copytree(SOURCE / "academy_engine", root / "academy_engine")
            shutil.copytree(SOURCE / ".codearbiter", root / ".codearbiter")
            (root / "scripts").mkdir()
            shutil.copy2(SOURCE / "scripts/academy.py", root / "scripts/academy.py")
            self._git(root, "init", "-b", "main")
            self._git(root, "config", "user.name", "Academy Learner")
            self._git(root, "config", "user.email", "learner@example.invalid")
            self._git(root, "add", ".")
            self._git(root, "commit", "-m", "base")
            self._git(root, "remote", "add", "origin", "https://github.com/learner/arbiter-academy.git")
            self._git(root, "remote", "add", "upstream", "https://github.com/arbiterForge/arbiter-academy.git")
            self._git(root, "remote", "set-url", "--push", "upstream", "DISABLED")

            prepare_lab(root, U01)
            self._commit_packet(root)
            result = evaluate_checkpoint(root, U01)

            self.assertTrue(result.passed, result.failed_predicates)
