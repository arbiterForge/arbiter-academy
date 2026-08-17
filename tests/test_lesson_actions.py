from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from academy_engine.checkpoints import _p05_red_regression_is_exact, canonical_json
from academy_engine.lesson_actions import (
    ActionResource,
    CommandVariant,
    LessonAction,
    LessonActionManifest,
    load_action_manifest,
    validate_action_resource_href,
    validate_action_manifest,
)
from academy_engine.preview import load_preview_manifest


CURRENT_RELEASE = load_preview_manifest(Path(__file__).parents[1]).release


DOCUMENT_ID = "F01-fork-clone-doctor"
F01_ACTION_IDS = (
    "F01-prepare",
    "F01-inspect-remotes",
    "F01-repair-origin",
    "F01-set-upstream",
    "F01-disable-upstream-push",
    "F01-select-push-default",
    "F01-host-doctor",
    "F01-academy-doctor",
    "F01-inspect-report",
    "F01-stage-report",
    "F01-review-commit-boundary",
    "F01-commit-report",
    "F01-confirm-clean",
    "F01-check",
    "F01-return-base",
    "F01-reset-retry",
)
F02_DOCUMENT_ID = "F02-orient-to-state"
F02_ACTION_IDS = (
    "F02-prepare",
    "F02-run-status",
    "F02-read-context",
    "F02-follow-context-links",
    "F02-hash-context",
    "F02-write-orientation",
    "F02-inspect-orientation",
    "F02-stage-orientation",
    "F02-review-commit-boundary",
    "F02-run-commit-gate",
    "F02-confirm-clean",
    "F02-check",
    "F02-return-base",
    "F02-reset-retry",
)
F03_DOCUMENT_ID = "F03-work-the-board"
PUBLIC_PREVIEW_0_8_DOCUMENT_IDS = frozenset(
    {
        "F01-fork-clone-doctor",
        "F02-orient-to-state",
        F03_DOCUMENT_ID,
        "F04-fix-with-evidence",
        "home",
        "recovery",
    }
)
F03_ACTION_IDS = (
    "F03-prepare",
    "F03-read-target-task",
    "F03-start-task",
    "F03-inspect-started-task",
    "F03-read-contract",
    "F03-run-docs-chore",
    "F03-review-co-commit-boundary",
    "F03-choose-keep-branch",
    "F03-confirm-clean",
    "F03-check",
    "F03-reset-retry",
    "F03-return-to-main",
)
P01_DOCUMENT_ID = "P01-feature-through-plan"
P01_ACTION_IDS = (
    "P01-prepare",
    "P01-draft-spec",
    "P01-read-spec",
    "P01-solo-review",
    "P01-discussion-review",
    "P01-revise-spec",
    "P01-proceed",
    "P01-check",
    "P01-return-base",
    "P01-reset-retry",
)
P04_DOCUMENT_ID = "P04-review-a-dependency"
P04_ACTION_IDS = (
    "P04-prepare", "P04-read-boundary", "P04-read-candidate-set", "P04-inspect-project-boundary",
    "P04-inspect-wheel-metadata", "P04-verify-wheel-hashes", "P04-read-licenses", "P04-assess-provenance",
    "P04-compare-stdlib", "P04-ask-context", "P04-draft-review", "P04-review-draft", "P04-select-reject",
    "P04-stage-review", "P04-commit-review", "P04-confirm-no-install", "P04-check", "P04-reset-retry",
)
P05_DOCUMENT_ID = "P05-checkpoint-remediation"
F01_DEPLOYED_LESSON = (
    "https://arbiterforge.github.io/arbiter-academy/labs/F01-fork-clone-doctor/"
)
P05_ACTION_IDS = (
    "P05-prerequisite",
    "P05-prepare",
    "P05-guard-attempt",
    "P05-read-prepared-boundary",
    "P05-surface-finding",
    "P05-inspect-finding",
    "P05-record-finding",
    "P05-verify-finding-commit",
    "P05-add-red-regression",
    "P05-observe-red",
    "P05-commit-red",
    "P05-apply-green-repair",
    "P05-commit-green",
    "P05-record-receipt",
    "P05-commit-receipt",
    "P05-confirm-clean",
    "P05-check",
    "P05-reset-retry",
)
P03_ACTION_DOCUMENT_ID = "P03-record-an-adr"
P03_ACTION_IDS = (
    "P03-read-boundary",
    "P03-identity-boundary",
    "P03-prepare",
    "P03-inspect-decision-context",
    "P03-request-decision-analysis",
    "P03-run-adr",
    "P03-run-commit-gate",
    "P03-confirm-native-evidence",
    "P03-check",
    "P03-reset",
)
P03_CHOICES = (
    "Use stable text for Workshop Queue summaries.",
    "Use structured JSON for Workshop Queue summaries.",
)
P08_DOCUMENT_ID = "P08-repository-hygiene"
U06_DOCUMENT_ID = "U06-preview-and-advanced-surfaces"
U06_ACTION_IDS = (
    "U06-confirm-public-boundary",
    "U06-prepare-attempt",
    "U06-inspect-scenario",
    "U06-inspect-seeded-candidate",
    "U06-create-contained-diff",
    "U06-inspect-preview-input",
    "U06-run-read-only-preview",
    "U06-assess-preview-output",
    "U06-stage-candidate",
    "U06-commit-candidate",
    "U06-classify-advanced-surfaces",
    "U06-write-binding-report",
    "U06-inspect-binding-report",
    "U06-stage-report",
    "U06-commit-report",
    "U06-confirm-clean",
    "U06-check-status",
    "U06-reset-retry",
)
U06_HEADINGS = (
    "Know before you begin",
    "What you will prove",
    "Prepare safely",
    "Create a contained preview",
    "Read the preview",
    "Record evidence",
    "Check the boundary",
    "Recover or continue",
)
P08_ACTION_IDS = (
    "P08-return-to-main",
    "P08-prepare",
    "P08-inventory-native",
    "P08-inventory-harness-shell",
    "P08-run-standup",
    "P08-inventory-after-standup",
    "P08-request-report-draft",
    "P08-review-report",
    "P08-stage-report",
    "P08-review-commit-boundary",
    "P08-run-commit-gate",
    "P08-confirm-clean",
    "P08-check",
    "P08-return-base",
    "P08-reset-retry",
)
P06_DOCUMENT_ID = "P06-context-drift-recovery"
P06_ACTION_IDS = (
    "P06-prepare",
    "P06-inspect-evidence",
    "P06-run-context-audit",
    "P06-select-rescout",
    "P06-apply-correction",
    "P06-review-correction-boundary",
    "P06-commit-correction",
    "P06-write-handoff",
    "P06-stage-handoff",
    "P06-review-handoff-boundary",
    "P06-commit-handoff",
    "P06-check",
    "P06-return-base",
    "P06-reset-retry",
)
P07_DOCUMENT_ID = "P07-threat-model"
P07_ACTION_IDS = (
    "P07-read-boundary",
    "P07-prepare",
    "P07-read-target",
    "P07-request-draft",
    "P07-review-model",
    "P07-write-binding",
    "P07-commit-report",
    "P07-inspect-commit",
    "P07-check",
    "P07-reset",
)

P02_DOCUMENT_ID = "P02-commit-review-pr"
P02_ACTION_IDS = (
    "P02-read-boundary", "P02-prepare", "P02-enter-and-guard",
    "P02-inspect-change", "P02-stage-work", "P02-request-review", "P02-run-review",
    "P02-run-work-commit", "P02-prove-and-push", "P02-record-receipt",
    "P02-stage-receipt", "P02-run-receipt-commit", "P02-confirm-clean",
    "P02-check", "P02-reset",
)
U04_DOCUMENT_ID = "U04-initialize-projects"
U04_ACTION_IDS = (
    "U04-confirm-private-boundary",
    "U04-prepare-attempt",
    "U04-inspect-root",
    "U04-inspect-greenfield",
    "U04-run-greenfield-init",
    "U04-run-greenfield-decompose",
    "U04-read-greenfield-plans",
    "U04-choose-greenfield-reconciliation",
    "U04-run-greenfield-reconcile",
    "U04-record-greenfield-adr",
    "U04-accept-greenfield-adr",
    "U04-inspect-greenfield-changes",
    "U04-stage-greenfield-changes",
    "U04-review-greenfield-commit-boundary",
    "U04-run-greenfield-commit-gate",
    "U04-confirm-greenfield-clean",
    "U04-inspect-brownfield",
    "U04-run-brownfield-init",
    "U04-run-brownfield-create-context",
    "U04-inspect-brownfield-changes",
    "U04-stage-brownfield-changes",
    "U04-review-brownfield-commit-boundary",
    "U04-run-brownfield-commit-gate",
    "U04-confirm-brownfield-clean",
    "U04-inspect-project-evidence",
    "U04-write-binding-report",
    "U04-inspect-report",
    "U04-stage-report",
    "U04-review-commit-boundary",
    "U04-run-commit-gate",
    "U04-confirm-clean",
    "U04-check-status",
    "U04-reset-retry",
)


class LessonActionTests(unittest.TestCase):
    def test_public_u04_starts_from_the_academy_root_and_keeps_reset_safe(self) -> None:
        """A public U04 starts a real attempt but never pretends Reset can erase child history."""
        manifest = load_action_manifest(Path(__file__).parents[1], U04_DOCUMENT_ID)
        actions = {action.id: action for action in manifest.actions}
        self.assertEqual(tuple(actions), U04_ACTION_IDS)
        self.assertEqual(
            tuple(action.sequence for action in manifest.actions),
            tuple(range(1, len(U04_ACTION_IDS) + 1)),
        )

        prepare = actions["U04-prepare-attempt"]
        self.assertIn("Academy root", prepare.instruction)
        self.assertIn("U04-greenfield", prepare.expected_result)
        self.assertIn("U04-brownfield", prepare.expected_result)
        self.assertIn("academy/U04-initialize-projects/", prepare.expected_result)

        writer = actions["U04-write-binding-report"]
        self.assertEqual(writer.surface, None)
        self.assertEqual(len(writer.variants), 3)
        self.assertTrue(all("write-report U04-initialize-projects" in variant.command for variant in writer.variants))

        reset = actions["U04-reset-retry"]
        self.assertIn("archive both child repository histories", reset.expected_result)
        self.assertIn("leaves all three repositories unchanged", reset.expected_result)
        self.assertIn("Do not delete, reset, or rewrite", reset.recovery)

    def test_public_u04_cards_expose_the_real_two_child_lifecycle(self) -> None:
        """A published U04 must not retain the old refusal-only private source wording."""
        manifest = load_action_manifest(Path(__file__).parents[1], U04_DOCUMENT_ID)
        actions = {action.id: action for action in manifest.actions}

        self.assertNotIn("future private-source", "\n".join(
            part
            for action in manifest.actions
            for part in (action.instruction, action.expected_result, action.recovery, action.evidence or "")
        ).casefold())
        prepare = actions["U04-prepare-attempt"]
        self.assertIn("U04-greenfield", prepare.expected_result)
        self.assertIn("U04-brownfield", prepare.expected_result)
        self.assertIn("academy/U04-initialize-projects/", prepare.expected_result)

        writer = actions["U04-write-binding-report"]
        self.assertEqual(writer.surface, None)
        self.assertEqual(len(writer.variants), 3)
        self.assertTrue(all("write-report U04-initialize-projects" in variant.command for variant in writer.variants))
        self.assertIn("canonical generated bytes", writer.expected_result)

        check = actions["U04-check-status"]
        self.assertIn("checkpoint U04-initialize-projects: passed", check.expected_result)
        self.assertIn("committed child", check.evidence or "")

    def test_public_u04_cards_keep_action_specific_results_evidence_and_recovery(self) -> None:
        """Catches replacing newcomer lifecycle guidance with a generic repeated template."""
        manifest = load_action_manifest(Path(__file__).parents[1], U04_DOCUMENT_ID)
        actions = {action.id: action for action in manifest.actions}
        self.assertEqual(tuple(actions), U04_ACTION_IDS)

        generic_fragments = (
            "The step completes without crossing its boundary.",
            "Stop and preserve current evidence; correct only the named repository boundary.",
            "Check verifies durable repository bytes only, never host invocation or learner judgment.",
        )
        next_steps = dict(
            zip(
                U04_ACTION_IDS,
                (
                    "prepare attempt",
                    "inspect root",
                    "inspect greenfield",
                    "run greenfield init",
                    "run greenfield decompose",
                    "read greenfield plans",
                    "choose greenfield reconciliation",
                    "run greenfield reconcile",
                    "record greenfield ADR",
                    "accept greenfield ADR",
                    "inspect greenfield changes",
                    "stage greenfield changes",
                    "review greenfield commit boundary",
                    "run greenfield commit gate",
                    "confirm greenfield clean",
                    "inspect brownfield",
                    "run brownfield init",
                    "run brownfield create context",
                    "inspect brownfield changes",
                    "stage brownfield changes",
                    "review brownfield commit boundary",
                    "run brownfield commit gate",
                    "confirm brownfield clean",
                    "inspect project evidence",
                    "write binding report",
                    "inspect report",
                    "stage report",
                    "review commit boundary",
                    "run commit gate",
                    "confirm clean",
                    "recognize the accepted result",
                    "preserve the completed attempt",
                    "preserve state and correct the named child or parent boundary",
                ),
                strict=True,
            )
        )
        for action in manifest.actions:
            guidance = " ".join(
                (action.expected_result, action.recovery, action.evidence or "")
            )
            with self.subTest(action=action.id):
                self.assertFalse(any(fragment in guidance for fragment in generic_fragments))
                self.assertNotEqual(
                    action.rationale,
                    "This step preserves the real repository lifecycle.",
                )
                self.assertTrue(
                    action.expected_result.endswith(
                        f"Next safe step: {next_steps[action.id]}."
                    )
                )
        self.assertEqual(len({action.rationale for action in manifest.actions}), len(manifest.actions))

        prepare = actions["U04-prepare-attempt"]
        self.assertIn("creates clean", prepare.expected_result)
        self.assertIn("attempt branch", prepare.evidence or "")

        decompose = actions["U04-run-greenfield-decompose"]
        for filename in (
            "01-architecture-breakdown.md",
            "02-phased-build-plan.md",
            "03-task-backlog.md",
        ):
            self.assertIn(filename, decompose.expected_result)

        reconcile = actions["U04-run-greenfield-reconcile"]
        adr = actions["U04-record-greenfield-adr"]
        accept_adr = actions["U04-accept-greenfield-adr"]
        self.assertNotIn("accepted ADR", reconcile.expected_result)
        self.assertTrue(
            all(
                "ca-adr" in variant.command or "ca:adr" in variant.command
                for variant in adr.variants
            )
        )
        self.assertIn("explicit learner attribution", adr.instruction)
        self.assertEqual(adr.title, "record the proposed greenfield ADR")
        self.assertIn("proposed", adr.expected_result)
        self.assertEqual(accept_adr.actor, "learner")
        self.assertEqual(accept_adr.surface, "active-harness")
        self.assertIn("explicitly accept", accept_adr.instruction)

        for kind in ("greenfield", "brownfield"):
            stage = actions[f"U04-stage-{kind}-changes"]
            review = actions[f"U04-review-{kind}-commit-boundary"]
            commit = actions[f"U04-run-{kind}-commit-gate"]
            clean = actions[f"U04-confirm-{kind}-clean"]
            with self.subTest(child=kind):
                self.assertIn("staged", stage.expected_result)
                self.assertIn(".codearbiter", stage.expected_result)
                self.assertIn("cached diff", review.expected_result)
                self.assertIn("no whitespace errors", review.expected_result)
                self.assertIn("new child commit", commit.expected_result)
                self.assertIn("working tree is clean", clean.expected_result)
                self.assertIn("committed HEAD", clean.evidence or "")

        writer = actions["U04-write-binding-report"]
        self.assertIn(".codearbiter/reports/academy/U04-initialization.md", writer.expected_result)
        self.assertIn("canonical generated bytes", writer.expected_result)

        binding = actions["U04-inspect-project-evidence"]
        for phrase in ("committed HEAD", "committed tree", "context digest"):
            self.assertIn(phrase, binding.expected_result)
            self.assertIn(phrase, writer.evidence or "")

    def test_private_p07_manifest_separates_threat_analysis_from_learner_review(self) -> None:
        """Catches P07 losing its real target, surface, or verifier-limit boundaries."""
        manifest = load_action_manifest(Path(__file__).parents[1], P07_DOCUMENT_ID)
        self.assertEqual(tuple(action.id for action in manifest.actions), P07_ACTION_IDS)
        self.assertTrue(all(action.expected_result and action.recovery for action in manifest.actions))
        by_id = {action.id: action for action in manifest.actions}

        self.assertEqual(by_id["P07-read-boundary"].actor, "learner")
        self.assertEqual(by_id["P07-request-draft"].actor, "agent")
        self.assertEqual(by_id["P07-review-model"].actor, "learner")
        self.assertEqual(by_id["P07-write-binding"].actor, "learner")
        self.assertEqual(by_id["P07-commit-report"].actor, "agent")
        self.assertEqual(by_id["P07-inspect-commit"].actor, "learner")

        for action_id in ("P07-prepare", "P07-read-target", "P07-inspect-commit", "P07-check", "P07-reset"):
            action = by_id[action_id]
            with self.subTest(action=action_id):
                self.assertEqual(
                    tuple((variant.surface, variant.operating_system, variant.host, variant.copy) for variant in action.variants),
                    (
                        ("native-terminal", "windows", "none", True),
                        ("native-terminal", "macos", "none", True),
                        ("native-terminal", "linux", "none", True),
                    ),
                )
                self.assertFalse(any(variant.command.startswith("!") for variant in action.variants))

        draft = by_id["P07-request-draft"]
        self.assertEqual(
            tuple((variant.host, variant.command) for variant in draft.variants),
            (
                ("claude-code", '/ca:threat-model "academy_engine/paths.py archive-import containment boundary"'),
                ("codex", '$ca-threat-model "academy_engine/paths.py archive-import containment boundary"'),
                ("pi", '/ca-threat-model "academy_engine/paths.py archive-import containment boundary"'),
                ("pi", '/skill:ca-threat-model "academy_engine/paths.py archive-import containment boundary"'),
            ),
        )
        self.assertTrue(all(variant.language == "codearbiter" for variant in draft.variants))
        self.assertFalse(any(variant.command.startswith("!") for variant in draft.variants))
        self.assertIn("writes no file", draft.expected_result)
        model_review = by_id["P07-review-model"]
        self.assertIn("advisory analysis", model_review.recovery)
        self.assertNotIn("revise only the report", model_review.recovery)
        writer = by_id["P07-write-binding"]
        self.assertIn("learner-owned Academy evidence", writer.instruction)
        self.assertEqual(writer.actor, "learner")
        self.assertEqual(
            tuple((variant.host, variant.language, variant.command) for variant in writer.variants),
            (
                ("claude-code", "text", "Draft only .codearbiter/reports/academy/P07-threat-model.md from the reviewed advisory STRIDE analysis and exact prepared scenario values. Keep the four learner-authored native sections in order, then append the Academy Target-SHA256/identity binding with exact target path, prepared blob, head blob, and SHA-256 values. Validate strict UTF-8 with LF line endings and one final newline. Stage only that report, show the staged path list and diff, then stop for my review. Do not change academy_engine/paths.py, commit, or claim that $ca-threat-model wrote the report."),
                ("codex", "text", "Draft only .codearbiter/reports/academy/P07-threat-model.md from the reviewed advisory STRIDE analysis and exact prepared scenario values. Keep the four learner-authored native sections in order, then append the Academy Target-SHA256/identity binding with exact target path, prepared blob, head blob, and SHA-256 values. Validate strict UTF-8 with LF line endings and one final newline. Stage only that report, show the staged path list and diff, then stop for my review. Do not change academy_engine/paths.py, commit, or claim that $ca-threat-model wrote the report."),
                ("pi", "text", "Draft only .codearbiter/reports/academy/P07-threat-model.md from the reviewed advisory STRIDE analysis and exact prepared scenario values. Keep the four learner-authored native sections in order, then append the Academy Target-SHA256/identity binding with exact target path, prepared blob, head blob, and SHA-256 values. Validate strict UTF-8 with LF line endings and one final newline. Stage only that report, show the staged path list and diff, then stop for my review. Do not change academy_engine/paths.py, commit, or claim that $ca-threat-model wrote the report."),
            ),
        )
        self.assertIn("Stage only that report", writer.variants[0].command)
        self.assertIn("stop for my review", writer.variants[0].command)
        self.assertIn("does not prove", writer.evidence or "")

        commit = by_id["P07-commit-report"]
        self.assertEqual(
            tuple((variant.host, variant.command) for variant in commit.variants),
            (("claude-code", "/ca:commit"), ("codex", "$ca-commit"), ("pi", "/ca-commit"), ("pi", "/skill:ca-commit")),
        )
        self.assertTrue(all(variant.language == "codearbiter" for variant in commit.variants))
        self.assertFalse(any(variant.command.startswith("!") for variant in commit.variants))

    def test_p08_manifest_binds_each_execution_surface_to_one_safe_command_form(self) -> None:
        """Catches P08 losing the boundary between terminal, harness, and agent commands."""
        root = Path(__file__).parents[1]
        manifest = load_action_manifest(root, P08_DOCUMENT_ID)

        self.assertEqual(tuple(action.id for action in manifest.actions), P08_ACTION_IDS)
        self.assertEqual(tuple(action.sequence for action in manifest.actions), tuple(range(1, 16)))
        for action in manifest.actions:
            with self.subTest(action=action.id):
                self.assertTrue(action.instruction)
                self.assertTrue(action.expected_result)
                self.assertTrue(action.recovery)
                self.assertIsNotNone(action.evidence)

        actions = {action.id: action for action in manifest.actions}
        handoff = actions["P08-return-to-main"]
        self.assertEqual((handoff.actor, handoff.surface), ("learner", None))
        self.assertTrue(all("git switch main\ngit status --short" == variant.command for variant in handoff.variants))
        self.assertIn("completed P07 attempt", handoff.expected_result)
        self.assertIn("Do not force", handoff.recovery)
        self.assertLess(P08_ACTION_IDS.index("P08-return-to-main"), P08_ACTION_IDS.index("P08-prepare"))
        self.assertEqual(actions["P08-run-standup"].actor, "agent")
        self.assertIn("git fetch", actions["P08-run-standup"].instruction)
        self.assertIn("--ff-only pull", actions["P08-run-standup"].instruction)
        self.assertIn("refresh", actions["P08-run-standup"].expected_result)
        post_inventory = actions["P08-inventory-after-standup"]
        self.assertEqual(post_inventory.actor, "learner")
        self.assertIn("post-fetch", post_inventory.instruction)
        self.assertEqual(post_inventory.variants[0].surface, "native-terminal")
        self.assertIn("post-fetch", actions["P08-request-report-draft"].instruction)
        self.assertEqual(actions["P08-request-report-draft"].actor, "learner")
        report_review = actions["P08-review-report"]
        self.assertEqual((report_review.actor, report_review.surface), ("learner", None))
        self.assertEqual(tuple(variant.host for variant in report_review.variants), ("claude-code", "codex", "pi"))
        self.assertTrue(
            all(
                variant.surface == "harness"
                and variant.language == "text"
                and variant.copy
                and "five refs" in variant.command
                and "three worktrees" in variant.command
                and "git for-each-ref" in variant.command
                and "git worktree list --porcelain" in variant.command
                and "Do not change files" in variant.command
                for variant in report_review.variants
            )
        )
        stage_report = actions["P08-stage-report"]
        self.assertEqual(stage_report.actor, "learner")
        self.assertEqual(
            tuple(
                (variant.surface, variant.host, variant.command, variant.copy)
                for variant in stage_report.variants
            ),
            (
                ("native-terminal", "none", "git add -- .codearbiter/reports/academy/P08-hygiene.json", True),
                ("native-terminal", "none", "git add -- .codearbiter/reports/academy/P08-hygiene.json", True),
                ("native-terminal", "none", "git add -- .codearbiter/reports/academy/P08-hygiene.json", True),
            ),
        )
        self.assertEqual(
            tuple(variant.operating_system for variant in stage_report.variants),
            ("windows", "macos", "linux"),
        )
        self.assertLess(P08_ACTION_IDS.index("P08-review-report"), P08_ACTION_IDS.index("P08-stage-report"))
        self.assertLess(P08_ACTION_IDS.index("P08-run-standup"), P08_ACTION_IDS.index("P08-inventory-after-standup"))
        self.assertLess(P08_ACTION_IDS.index("P08-inventory-after-standup"), P08_ACTION_IDS.index("P08-request-report-draft"))
        self.assertLess(P08_ACTION_IDS.index("P08-stage-report"), P08_ACTION_IDS.index("P08-review-commit-boundary"))
        review_boundary = actions["P08-review-commit-boundary"]
        self.assertEqual((review_boundary.actor, review_boundary.surface), ("learner", None))
        self.assertEqual(
            tuple(
                (
                    variant.surface,
                    variant.operating_system,
                    variant.host,
                    variant.language,
                    variant.command,
                    variant.copy,
                )
                for variant in review_boundary.variants
            ),
            (
                (
                    "native-terminal",
                    "windows",
                    "none",
                    "powershell",
                    "git diff --cached --name-only\n"
                    "git diff --cached -- .codearbiter/reports/academy/P08-hygiene.json",
                    True,
                ),
                (
                    "native-terminal",
                    "macos",
                    "none",
                    "sh",
                    "git diff --cached --name-only\n"
                    "git diff --cached -- .codearbiter/reports/academy/P08-hygiene.json",
                    True,
                ),
                (
                    "native-terminal",
                    "linux",
                    "none",
                    "sh",
                    "git diff --cached --name-only\n"
                    "git diff --cached -- .codearbiter/reports/academy/P08-hygiene.json",
                    True,
                ),
            ),
        )
        self.assertFalse(
            any(
                verb in variant.command
                for variant in review_boundary.variants
                for verb in ("git add", "git commit", "git reset", "git restore", "git push")
            )
        )
        self.assertTrue(any(variant.surface == "native-terminal" for variant in actions["P08-inventory-native"].variants))
        self.assertTrue(
            any(variant.surface == "harness" and variant.language == "sh" for variant in actions["P08-inventory-harness-shell"].variants)
        )
        self.assertTrue(
            any(variant.surface == "harness" and variant.language == "text" for variant in actions["P08-request-report-draft"].variants)
        )

        for action_id, command in (
            ("P08-run-standup", "standup"),
            ("P08-run-commit-gate", "commit"),
        ):
            action = actions[action_id]
            with self.subTest(action=action_id):
                self.assertEqual(action.actor, "agent")
                self.assertEqual(
                    tuple((variant.host, variant.command) for variant in action.variants),
                    (
                        ("claude-code", f"/ca:{command}"),
                        ("codex", f"$ca-{command}"),
                        ("pi", f"/ca-{command}"),
                        ("pi", f"/skill:ca-{command}"),
                    ),
                )
                self.assertTrue(all(variant.copy for variant in action.variants))
                self.assertTrue(
                    all(variant.language == "codearbiter" for variant in action.variants)
                )

        for action in manifest.actions:
            for variant in action.variants:
                with self.subTest(action=action.id, variant=variant.id):
                    if variant.surface == "native-terminal":
                        self.assertFalse(variant.command.startswith("!"))
                    if variant.surface == "harness" and variant.language in {"powershell", "sh"}:
                        self.assertTrue(variant.command.startswith("!"))
                        self.assertFalse(variant.command.startswith("!!"))
                    if variant.language == "codearbiter":
                        self.assertEqual(action.actor, "agent")
                        self.assertFalse(variant.command.startswith("!"))

    def test_p08_installed_academy_actions_use_current_preview_locations(self) -> None:
        """Catches P08 routing a first-time learner to a command absent from PATH."""
        manifest = load_action_manifest(Path(__file__).parents[1], P08_DOCUMENT_ID)
        by_id = {action.id: action for action in manifest.actions}
        expected_locations = {
            "windows": rf"$env:LOCALAPPDATA\ArbiterAcademy\{CURRENT_RELEASE}\Scripts\arbiter-academy.exe",
            "macos": f"${{XDG_DATA_HOME:-$HOME/.local/share}}/arbiter-academy/{CURRENT_RELEASE}/bin/arbiter-academy",
            "linux": f"${{XDG_DATA_HOME:-$HOME/.local/share}}/arbiter-academy/{CURRENT_RELEASE}/bin/arbiter-academy",
        }

        for action_id in ("P08-prepare", "P08-check", "P08-reset-retry"):
            variants = {variant.operating_system: variant for variant in by_id[action_id].variants}
            for platform, location in expected_locations.items():
                with self.subTest(action_id=action_id, platform=platform):
                    self.assertIn(location, variants[platform].command)
                    self.assertIn(CURRENT_RELEASE, variants[platform].command)

    def test_checked_in_p04_manifest_teaches_a_reviewed_no_install_rejection_path(self) -> None:
        """Catches P04 returning to vague dependency advice or an install-shaped command path."""
        manifest = load_action_manifest(Path(__file__).parents[1], P04_DOCUMENT_ID)
        self.assertEqual(tuple(action.id for action in manifest.actions), P04_ACTION_IDS)
        by_id = {action.id: action for action in manifest.actions}
        boundary = by_id["P04-read-boundary"]
        self.assertEqual(
            (boundary.actor, boundary.surface, boundary.variants),
            ("learner", "browser", ()),
        )
        self.assertIn("website", boundary.instruction)
        self.assertIn("Prepare, Check, and Reset", boundary.expected_result)
        for action_id in ("P04-prepare", "P04-check", "P04-reset-retry"):
            action = by_id[action_id]
            with self.subTest(action=action_id):
                self.assertEqual(action.actor, "learner")
                self.assertEqual(
                    tuple((variant.surface, variant.operating_system, variant.host) for variant in action.variants),
                    (("native-terminal", "windows", "none"), ("native-terminal", "macos", "none"), ("native-terminal", "linux", "none")),
                )
                self.assertFalse(any(variant.command.startswith("!") for variant in action.variants))
        draft = by_id["P04-draft-review"]
        self.assertEqual(draft.actor, "agent")
        self.assertTrue(all(variant.language == "text" for variant in draft.variants))
        self.assertTrue(all("Academy evidence" in variant.command for variant in draft.variants))
        context = by_id["P04-ask-context"]
        self.assertEqual(context.actor, "learner")
        self.assertIsNone(context.surface)
        self.assertTrue(all("btw" in variant.command for variant in context.variants))
        self.assertIn("cannot inspect the supplied wheel artifacts", context.expected_result + context.instruction)
        self.assertTrue(all("not $ca-add-dep output" in variant.command for variant in draft.variants))
        self.assertFalse(any(variant.command.startswith("!") for variant in draft.variants))
        self.assertFalse(
            any(
                variant.language == "codearbiter" and "add-dep" in variant.command
                for action in manifest.actions
                for variant in action.variants
            )
        )
        checksum_variants = by_id["P04-verify-wheel-hashes"].variants
        self.assertEqual(
            tuple((variant.operating_system, variant.command) for variant in checksum_variants),
            (
                (
                    "windows",
                    "Get-FileHash -Algorithm SHA256 "
                    "academy/candidates/P04-review-a-dependency/"
                    "python_dateutil-2.9.0.post0-py2.py3-none-any.whl\n"
                    "Get-FileHash -Algorithm SHA256 "
                    "academy/candidates/P04-review-a-dependency/"
                    "six-1.17.0-py2.py3-none-any.whl",
                ),
                (
                    "macos",
                    "shasum -a 256 "
                    "academy/candidates/P04-review-a-dependency/"
                    "python_dateutil-2.9.0.post0-py2.py3-none-any.whl "
                    "academy/candidates/P04-review-a-dependency/"
                    "six-1.17.0-py2.py3-none-any.whl",
                ),
                (
                    "linux",
                    "sha256sum academy/candidates/P04-review-a-dependency/"
                    "python_dateutil-2.9.0.post0-py2.py3-none-any.whl "
                    "academy/candidates/P04-review-a-dependency/"
                    "six-1.17.0-py2.py3-none-any.whl",
                ),
            ),
        )
        for action_id, required_terms in (
            ("P04-assess-provenance", ("candidate-set.json", "2026-07-31", "Do not use live registry or CVE data")),
            ("P04-compare-stdlib", ("datetime.strptime", "SMARTS", "Do not change files")),
            ("P04-review-draft", ("P04-dependency-review.md", "2026-07-31", "Do not change files")),
            ("P04-select-reject", ("Decision: reject", "datetime.strptime", "Do not change files")),
        ):
            action = by_id[action_id]
            with self.subTest(action=action_id):
                self.assertEqual((action.actor, action.surface), ("learner", None))
                self.assertEqual(tuple(variant.host for variant in action.variants), ("claude-code", "codex", "pi"))
                self.assertTrue(all(variant.surface == "harness" and variant.language == "text" for variant in action.variants))
                self.assertTrue(all(variant.copy for variant in action.variants))
                self.assertTrue(all(term in variant.command for variant in action.variants for term in required_terms))
        self.assertEqual(by_id["P04-commit-review"].actor, "agent")
        no_install = by_id["P04-confirm-no-install"]
        self.assertIn("pyproject.toml", no_install.expected_result)
        self.assertIn("requirements.lock", no_install.expected_result)
        self.assertFalse(any(forbidden in variant.command for action in manifest.actions for variant in action.variants for forbidden in ("pip install", "pyproject.toml", "requirements.lock", "approved-dependency.lock")))

    def test_checked_in_p01_manifest_separates_review_process_from_check_evidence(self) -> None:
        """Catches P01 losing actor, surface, or copy identity before its future publication slice."""
        manifest = load_action_manifest(Path(__file__).parents[1], P01_DOCUMENT_ID)
        self.assertEqual(tuple(action.id for action in manifest.actions), P01_ACTION_IDS)
        by_id = {action.id: action for action in manifest.actions}

        self.assertEqual(by_id["P01-draft-spec"].actor, "agent")
        self.assertIsNone(by_id["P01-draft-spec"].surface)
        self.assertEqual(
            tuple(
                (variant.host, variant.language, variant.command, variant.copy)
                for variant in by_id["P01-draft-spec"].variants
            ),
            (
                ("claude-code", "codearbiter", '/ca:feature "Show unresolved tickets in the Workshop Queue summary"', True),
                ("codex", "codearbiter", '$ca-feature "Show unresolved tickets in the Workshop Queue summary"', True),
                ("pi", "codearbiter", '/ca-feature "Show unresolved tickets in the Workshop Queue summary"', True),
                ("pi", "codearbiter", '/skill:ca-feature "Show unresolved tickets in the Workshop Queue summary"', True),
            ),
        )
        self.assertFalse(any(variant.command.startswith("!") for variant in by_id["P01-draft-spec"].variants))

        solo = by_id["P01-solo-review"]
        self.assertEqual((solo.actor, solo.surface, solo.variants), ("learner", "active-harness", ()))
        discussion = by_id["P01-discussion-review"]
        self.assertEqual((discussion.actor, discussion.surface, discussion.variants), ("learner", "browser", ()))
        self.assertEqual(
            tuple((resource.label, resource.href) for resource in discussion.resources),
            (("Arbiter Academy GitHub Discussion", "https://github.com/arbiterForge/arbiter-academy/discussions"),),
        )

        revise = by_id["P01-revise-spec"]
        self.assertEqual((revise.actor, revise.surface), ("learner", None))
        self.assertEqual(
            tuple((variant.surface, variant.host, variant.language, variant.copy) for variant in revise.variants),
            (("harness", "claude-code", "text", True), ("harness", "codex", "text", True), ("harness", "pi", "text", True)),
        )
        self.assertTrue(all("Revise only .codearbiter/specs/academy-feature.md" in variant.command for variant in revise.variants))
        self.assertTrue(all("Do not derive a plan" in variant.command for variant in revise.variants))
        self.assertTrue(all("[paste the concrete finding here]" in variant.command for variant in revise.variants))
        self.assertFalse(any(variant.command.startswith("!") for variant in revise.variants))

        for action_id in ("P01-read-spec", "P01-proceed"):
            action = by_id[action_id]
            with self.subTest(action=action_id):
                self.assertEqual(action.actor, "learner")
                self.assertIsNone(action.surface)
                self.assertEqual(
                    tuple((variant.surface, variant.host, variant.language, variant.copy) for variant in action.variants),
                    (("harness", "claude-code", "text", True), ("harness", "codex", "text", True), ("harness", "pi", "text", True)),
                )
                self.assertFalse(any(variant.command.startswith("!") for variant in action.variants))

        for action_id in ("P01-prepare", "P01-check", "P01-reset-retry"):
            action = by_id[action_id]
            with self.subTest(action=action_id):
                self.assertEqual(action.actor, "learner")
                self.assertIsNone(action.surface)
                self.assertEqual(
                    tuple((variant.surface, variant.operating_system, variant.host, variant.copy) for variant in action.variants),
                    (("native-terminal", "windows", "none", True), ("native-terminal", "macos", "none", True), ("native-terminal", "linux", "none", True)),
                )
                self.assertTrue(all(CURRENT_RELEASE in variant.command for variant in action.variants))
                self.assertFalse(any(variant.command.startswith("!") for variant in action.variants))

        return_base = by_id["P01-return-base"]
        self.assertEqual((return_base.actor, return_base.surface), ("learner", None))
        self.assertEqual(
            tuple((variant.surface, variant.operating_system, variant.host, variant.command, variant.copy) for variant in return_base.variants),
            (
                ("native-terminal", "windows", "none", "git switch main", True),
                ("native-terminal", "macos", "none", "git switch main", True),
                ("native-terminal", "linux", "none", "git switch main", True),
            ),
        )

    def test_p05_prerequisite_routes_first_time_learners_to_rendered_f01(self) -> None:
        """Catches P05 exposing raw Markdown action tokens as runnable guidance."""
        manifest = load_action_manifest(Path(__file__).parents[1], P05_DOCUMENT_ID)
        prerequisite = manifest.actions[0]

        self.assertEqual(
            prerequisite.resources,
            (
                ActionResource(
                    "F01 fork, clone, and Doctor guided lesson",
                    F01_DEPLOYED_LESSON,
                ),
            ),
        )
        self.assertNotIn("/blob/", prerequisite.resources[0].href)
        self.assertNotIn(".md", prerequisite.resources[0].href)

    def test_p05_red_action_supplies_the_exact_verifier_accepted_regression(self) -> None:
        """Catches a prose sketch that cannot pass the strict P05 RED verifier."""
        manifest = load_action_manifest(Path(__file__).parents[1], P05_DOCUMENT_ID)
        action = next(action for action in manifest.actions if action.id == "P05-add-red-regression")
        observation = next(action for action in manifest.actions if action.id == "P05-observe-red")
        marker = "Insert this exact method in WorkshopQueueCliTests:\n"
        terminator = "\nRun only the exact focused test"

        self.assertIn("report, not a syntax", observation.instruction)
        self.assertNotIn("\u00e2\u20ac\u201d", observation.instruction)

        for variant in action.variants:
            with self.subTest(variant=variant.id):
                self.assertEqual(variant.surface, "harness")
                self.assertEqual(variant.language, "text")
                self.assertIn("does not accept an equivalent test", variant.command)
                scaffold = variant.command.partition(marker)[2].partition(terminator)[0]
                self.assertTrue(scaffold, "RED action must contain the executable method scaffold")
                self.assertEqual(scaffold.count(".returncode"), 3)
                self.assertTrue(
                    _p05_red_regression_is_exact(
                        ("class WorkshopQueueCliTests:\n" + scaffold + "\n").encode("utf-8")
                    )
                )

    def test_p05_receipt_action_executes_a_canonical_byte_generator(self) -> None:
        """Catches asking a learner or agent to invent verifier-sensitive JSON bytes."""
        manifest = load_action_manifest(Path(__file__).parents[1], P05_DOCUMENT_ID)
        action = next(action for action in manifest.actions if action.id == "P05-record-receipt")

        self.assertEqual(action.actor, "learner")
        self.assertEqual(
            tuple(
                (variant.id, variant.surface, variant.host, variant.language)
                for variant in action.variants
            ),
            (
                ("windows", "native-terminal", "none", "powershell"),
                ("macos", "native-terminal", "none", "sh"),
                ("linux", "native-terminal", "none", "sh"),
            ),
        )

        scripts = []
        for variant in action.variants:
            if variant.id == "windows":
                prefix, suffix = "@'\n", "\n'@ | python -"
            else:
                prefix, suffix = "python3 - <<'PY'\n", "\nPY"
            self.assertTrue(variant.command.startswith(prefix))
            self.assertTrue(variant.command.endswith(suffix))
            scripts.append(variant.command[len(prefix) : -len(suffix)])
        self.assertEqual(scripts[1:], scripts[:1] * 2)
        self.assertTrue(
            all('git("rev-parse", "HEAD").strip()' in script for script in scripts)
        )
        self.assertTrue(
            all("reference_oid" in script and "len(reference_oid)" in script for script in scripts)
        )
        self.assertTrue(all("show-object-format" not in script for script in scripts))
        self.assertTrue(all("oid_length" not in script for script in scripts))

        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary)

            def git(*arguments: str) -> subprocess.CompletedProcess[str]:
                return subprocess.run(
                    ["git", *arguments],
                    cwd=repository,
                    check=True,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )

            git("init", "--quiet")
            git("config", "user.name", "Academy Test")
            git("config", "user.email", "academy-test@example.invalid")
            for number in range(4):
                (repository / "evidence.txt").write_text(f"{number}\n", encoding="utf-8")
                git("add", "evidence.txt")
                git("commit", "--quiet", "-m", f"evidence {number}")

            commits = git("rev-list", "--reverse", "HEAD~3..HEAD").stdout.splitlines()
            subprocess.run(
                [sys.executable, "-c", scripts[0]],
                cwd=repository,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            receipt = repository / ".codearbiter/checkpoints/P05-academy.json"
            expected = {
                "affected_paths": ["tests/test_cli.py", "workshop_queue/cli.py"],
                "finding_commit": commits[0],
                "finding_id": "ACADEMY-P05-BLOCKED-UNRESOLVED",
                "red_commit": commits[1],
                "remediation_commit": commits[2],
                "schema_version": 2,
                "status": "remediated",
            }
            self.assertEqual(
                receipt.read_bytes(),
                canonical_json(expected) + b"\n",
            )

    def test_checked_in_p05_manifest_encodes_the_complete_guided_remediation_lifecycle(self) -> None:
        manifest = load_action_manifest(Path(__file__).parents[1], P05_DOCUMENT_ID)

        self.assertEqual(tuple(action.id for action in manifest.actions), P05_ACTION_IDS)
        self.assertTrue(all(action.expected_result for action in manifest.actions))
        self.assertTrue(all(action.recovery for action in manifest.actions))

        by_id = {action.id: action for action in manifest.actions}
        self.assertEqual(by_id["P05-prerequisite"].surface, "browser")
        self.assertEqual(by_id["P05-prerequisite"].actor, "learner")
        self.assertTrue(by_id["P05-prerequisite"].resources)

        checkpoint = by_id["P05-surface-finding"]
        self.assertEqual(checkpoint.actor, "agent")
        self.assertEqual(
            tuple((variant.host, variant.command) for variant in checkpoint.variants),
            (
                ("claude-code", "/ca:checkpoint"),
                ("codex", "$ca-checkpoint"),
                ("pi", "/ca-checkpoint"),
                ("pi", "/skill:ca-checkpoint"),
            ),
        )
        self.assertTrue(all(variant.language == "codearbiter" for variant in checkpoint.variants))
        self.assertFalse(any(variant.command.startswith("!") for variant in checkpoint.variants))
        finding = by_id["P05-record-finding"]
        self.assertIn("generated checkpoint report", finding.instruction)
        self.assertIn(".codearbiter/last-checkpoint", finding.instruction)

        for action_id in ("P05-prepare", "P05-check", "P05-reset-retry"):
            action = by_id[action_id]
            self.assertEqual(action.actor, "learner")
            self.assertTrue(action.variants)
            for variant in action.variants:
                with self.subTest(action_id=action_id, variant=variant.id):
                    self.assertEqual(variant.surface, "native-terminal")
                    self.assertEqual(variant.host, "none")
                    self.assertIn(variant.operating_system, {"windows", "macos", "linux"})
                    self.assertTrue(variant.copy)
                    self.assertFalse(variant.command.startswith("!"))

        for action_id in (
            "P05-read-prepared-boundary",
            "P05-record-finding",
            "P05-add-red-regression",
            "P05-apply-green-repair",
        ):
            action = by_id[action_id]
            self.assertEqual(action.actor, "agent")
            self.assertTrue(action.variants)
            for variant in action.variants:
                with self.subTest(action_id=action_id, variant=variant.id):
                    self.assertEqual(variant.surface, "harness")
                    self.assertEqual(variant.language, "text")
                    self.assertFalse(variant.command.startswith("!"))
                    self.assertTrue(variant.copy)

        check_copy = "\n".join(
            part
            for action in manifest.actions
            for part in (action.instruction, action.expected_result, action.recovery, action.evidence or "")
        )
        self.assertIn("does not authenticate", check_copy)
        self.assertIn("does not prove command chronology", check_copy)

    def test_p05_installed_academy_actions_use_current_preview_locations(self) -> None:
        """Catches Prepare, Check, or Reset routing learners to the obsolete install."""
        manifest = load_action_manifest(Path(__file__).parents[1], P05_DOCUMENT_ID)
        by_id = {action.id: action for action in manifest.actions}
        expected_locations = {
            "windows": rf"$env:LOCALAPPDATA\ArbiterAcademy\{CURRENT_RELEASE}\Scripts\arbiter-academy.exe",
            "macos": f"${{XDG_DATA_HOME:-$HOME/.local/share}}/arbiter-academy/{CURRENT_RELEASE}/bin/arbiter-academy",
            "linux": f"${{XDG_DATA_HOME:-$HOME/.local/share}}/arbiter-academy/{CURRENT_RELEASE}/bin/arbiter-academy",
        }

        for action_id in ("P05-prepare", "P05-check", "P05-reset-retry"):
            variants = {variant.id: variant for variant in by_id[action_id].variants}
            for platform, location in expected_locations.items():
                with self.subTest(action_id=action_id, platform=platform):
                    self.assertIn(location, variants[platform].command)
                    self.assertNotIn("preview-0.5", variants[platform].command)

    def test_p05_finding_commit_action_requires_the_verifier_record_bytes(self) -> None:
        """Catches ambiguous prose that cannot reproduce the verifier's three-line record."""
        manifest = load_action_manifest(Path(__file__).parents[1], P05_DOCUMENT_ID)
        action = next(action for action in manifest.actions if action.id == "P05-record-finding")
        required_record = (
            "# P05 Finding: blocked tickets omitted from unresolved summary\n"
            "\n"
            "Ticket `RQ-105` is blocked: `Venue access is awaiting facilities clearance`.\n"
            "Affected paths: `tests/test_cli.py`, `workshop_queue/cli.py`.\n"
        )

        for variant in action.variants:
            with self.subTest(variant=variant.id):
                self.assertIn(required_record, variant.command)
                self.assertNotIn("workshop_queue/cli.py`..", variant.command)
    def test_p03_guided_contract_uses_the_exact_ten_action_renderer_boundaries(self) -> None:
        """Catches P03 drifting from its renderer-backed decision and evidence contract."""
        root = Path(__file__).parents[1]
        self.assertTrue(
            (root / "academy/actions/P03-record-an-adr.json").is_file(),
            "P03 must expose its canonical public action manifest",
        )
        self.assertEqual(
            [path.name for path in sorted((root / "academy/actions").glob("P03*.json"))],
            ["P03-record-an-adr.json"],
        )
        manifest = load_action_manifest(root, P03_ACTION_DOCUMENT_ID)
        by_id = {action.id: action for action in manifest.actions}

        self.assertEqual(tuple(action.id for action in manifest.actions), P03_ACTION_IDS)
        for action in manifest.actions:
            with self.subTest(action=action.id):
                self.assertTrue(action.actor)
                self.assertTrue(action.variants)
                self.assertTrue(action.expected_result)
                self.assertTrue(action.recovery)
                self.assertTrue(action.evidence)
                self.assertTrue(all(variant.copy for variant in action.variants))
                self.assertTrue(all(variant.surface for variant in action.variants))
                self.assertFalse(
                    any(
                        variant.surface == "native-terminal" and "!" in variant.command
                        for variant in action.variants
                    )
                )

        prepare = by_id["P03-prepare"]
        self.assertIn("not a directory you can paste literally", prepare.instruction)
        self.assertIn("fork clone you used for P01", prepare.instruction)
        self.assertTrue(all("<learner-repository>" in variant.command for variant in prepare.variants))

        choice = by_id["P03-request-decision-analysis"]
        self.assertEqual(choice.actor, "learner")
        self.assertEqual(
            tuple(
                variant.command
                for variant in choice.variants
                if variant.command in P03_CHOICES
            ),
            P03_CHOICES * 3,
        )
        self.assertIn("learner chooses", choice.instruction.casefold())
        self.assertIn("agent may analyze and draft", choice.instruction.casefold())

        for action_id, commands in (
            (
                "P03-run-adr",
                (
                    '/ca:adr "Choose the Workshop Queue summary-format boundary"',
                    '$ca-adr "Choose the Workshop Queue summary-format boundary"',
                    '/ca-adr "Choose the Workshop Queue summary-format boundary"',
                    '/skill:ca-adr "Choose the Workshop Queue summary-format boundary"',
                ),
            ),
            ("P03-run-commit-gate", ("/ca:commit", "$ca-commit", "/ca-commit", "/skill:ca-commit")),
        ):
            action = by_id[action_id]
            with self.subTest(action=action_id):
                self.assertEqual(action.actor, "agent")
                self.assertEqual(tuple(variant.command for variant in action.variants), commands)
                self.assertTrue(all(variant.language == "codearbiter" for variant in action.variants))

    def test_checked_in_p06_manifest_names_every_actor_surface_and_recovery_boundary(self) -> None:
        """Catches public P06 guidance asking learners to infer execution surfaces."""
        manifest = load_action_manifest(Path(__file__).parents[1], P06_DOCUMENT_ID)
        self.assertEqual(tuple(action.id for action in manifest.actions), P06_ACTION_IDS)
        self.assertTrue(all(action.expected_result for action in manifest.actions))
        self.assertTrue(all(action.recovery for action in manifest.actions))
        by_id = {action.id: action for action in manifest.actions}
        self.assertEqual(by_id["P06-run-context-audit"].actor, "agent")
        self.assertEqual(by_id["P06-apply-correction"].actor, "agent")
        self.assertEqual(by_id["P06-write-handoff"].actor, "learner")
        self.assertEqual(by_id["P06-select-rescout"].surface, "active-harness")
        for action_id, required_terms in (
            ("P06-review-correction-boundary", ("git diff --cached --name-only", "git diff --cached", "docs/preserved-note.md", "Do not change files")),
            ("P06-review-handoff-boundary", ("git diff --cached --name-only", "git diff --cached", "P06-recovery.json", "Do not change files")),
        ):
            action = by_id[action_id]
            with self.subTest(action=action_id):
                self.assertEqual((action.actor, action.surface), ("learner", None))
                self.assertEqual(tuple(variant.host for variant in action.variants), ("claude-code", "codex", "pi"))
                self.assertTrue(all(variant.surface == "harness" and variant.language == "text" and variant.copy for variant in action.variants))
                self.assertTrue(all(term in variant.command for variant in action.variants for term in required_terms))

        audit = by_id["P06-run-context-audit"]
        self.assertEqual(
            tuple((variant.host, variant.command) for variant in audit.variants),
            (
                ("claude-code", "/ca:context-check"),
                ("codex", "$ca-context-check"),
                ("pi", "/ca-context-check"),
                ("pi", "/skill:ca-context-check"),
            ),
        )

        inspection = by_id["P06-inspect-evidence"]
        self.assertTrue(
            all(
                ".codearbiter/decisions/0005-terminal-blocked-ticket-lifecycle.md"
                in variant.command
                for variant in inspection.variants
            )
        )

        for action in manifest.actions:
            for variant in action.variants:
                with self.subTest(action=action.id, variant=variant.id):
                    self.assertTrue(variant.copy)
                    if variant.language == "codearbiter":
                        self.assertFalse(variant.command.startswith("!"))
                    if variant.surface == "native-terminal":
                        self.assertEqual(variant.host, "none")
                        self.assertFalse(variant.command.startswith("!"))

        for action_id in ("P06-prepare", "P06-write-handoff", "P06-check", "P06-return-base", "P06-reset-retry"):
            self.assertEqual(
                {variant.operating_system for variant in by_id[action_id].variants},
                {"windows", "macos", "linux"},
            )

        handoff = by_id["P06-write-handoff"]
        self.assertTrue(
            all(
                variant.surface == "native-terminal"
                and variant.host == "none"
                and "write-handoff P06-context-drift-recovery" in variant.command
                and not variant.command.startswith("!")
                for variant in handoff.variants
            )
        )

        stage_handoff = by_id["P06-stage-handoff"]
        self.assertEqual(stage_handoff.actor, "learner")
        self.assertEqual(
            tuple(variant.command for variant in stage_handoff.variants),
            (
                "git add -- .codearbiter/reports/academy/P06-recovery.json",
                "git add -- .codearbiter/reports/academy/P06-recovery.json",
                "git add -- .codearbiter/reports/academy/P06-recovery.json",
            ),
        )
        self.assertTrue(
            all(
                variant.surface == "native-terminal"
                and variant.host == "none"
                and not variant.command.startswith("!")
                for variant in stage_handoff.variants
            )
        )
        self.assertIn("only .codearbiter/reports/academy/P06-recovery.json", stage_handoff.expected_result)
        self.assertIn("use Reset", stage_handoff.recovery)
        self.assertIn("second commit", stage_handoff.evidence or "")

        return_base = by_id["P06-return-base"]
        self.assertEqual(return_base.actor, "learner")
        self.assertTrue(all("git switch main" in variant.command for variant in return_base.variants))

    def test_all_action_command_variants_bind_to_their_release_boundary(self) -> None:
        """Catches release-bound commands retaining stale paths or missing a planned boundary."""
        root = Path(__file__).parents[1]
        guided = set(load_preview_manifest(root).guided_labs)
        for path in sorted((root / "academy" / "actions").glob("*.json")):
            document_id = path.stem
            with self.subTest(document_id=document_id):
                manifest = load_action_manifest(root, document_id)
                commands = "\n".join(
                    variant.command
                    for action in manifest.actions
                    for variant in action.variants
                )
                self.assertNotIn("preview-0.5", commands)
                if document_id in guided and "preview-" in commands:
                    self.assertIn(load_preview_manifest(root).release, commands)
                    for stale in ("preview-0.6", "preview-0.7", "preview-0.8", "preview-0.9"):
                        self.assertNotIn(stale, commands)

    def test_checked_in_f03_manifest_encodes_the_public_preview_026_lifecycle(self) -> None:
        """Catches F03 publishing without its installed lifecycle commands and co-commit limits."""
        root = Path(__file__).parents[1]
        manifest = load_action_manifest(root, F03_DOCUMENT_ID)

        self.assertEqual(tuple(action.id for action in manifest.actions), F03_ACTION_IDS)
        self.assertTrue(all(action.expected_result and action.recovery for action in manifest.actions))
        by_id = {action.id: action for action in manifest.actions}

        for action_id, operation in (("F03-prepare", "prepare"), ("F03-check", "check"), ("F03-reset-retry", "reset")):
            action = by_id[action_id]
            with self.subTest(action=action_id):
                self.assertEqual(action.actor, "learner")
                self.assertIsNone(action.surface)
                self.assertEqual(tuple((variant.operating_system, variant.command) for variant in action.variants), (
                    ("windows", '$academy = "$env:LOCALAPPDATA\\ArbiterAcademy\\preview-0.30\\Scripts\\arbiter-academy.exe"\n' f"& $academy --repository (Get-Location).Path {operation} F03-work-the-board"),
                    ("macos", 'academy="${XDG_DATA_HOME:-$HOME/.local/share}/arbiter-academy/preview-0.30/bin/arbiter-academy"\n' f'"$academy" --repository "$PWD" {operation} F03-work-the-board'),
                    ("linux", 'academy="${XDG_DATA_HOME:-$HOME/.local/share}/arbiter-academy/preview-0.30/bin/arbiter-academy"\n' f'"$academy" --repository "$PWD" {operation} F03-work-the-board'),
                ))

        expected_agent_commands = {
            "F03-start-task": (
                ("claude-code", "/ca:task start academy.docs.0001"),
                ("codex", "$ca-task start academy.docs.0001"),
                ("pi", "/ca-task start academy.docs.0001"),
                ("pi", "/skill:ca-task start academy.docs.0001"),
            ),
            "F03-run-docs-chore": (
                (
                    "claude-code",
                    "/ca:chore docs Correct claimant visibility in docs/ticket-list-contract.md",
                ),
                (
                    "codex",
                    "$ca-chore docs Correct claimant visibility in docs/ticket-list-contract.md",
                ),
                (
                    "pi",
                    "/ca-chore docs Correct claimant visibility in docs/ticket-list-contract.md",
                ),
                (
                    "pi",
                    "/skill:ca-chore docs Correct claimant visibility in docs/ticket-list-contract.md",
                ),
            ),
        }
        for action_id, expected_commands in expected_agent_commands.items():
            action = by_id[action_id]
            with self.subTest(action=action_id):
                self.assertEqual(action.actor, "agent")
                self.assertEqual(
                    tuple((variant.host, variant.command) for variant in action.variants),
                    expected_commands,
                )
                self.assertFalse(any(variant.command.startswith("!") for variant in action.variants))

        commands = "\n".join(
            variant.command for action in manifest.actions for variant in action.variants
        )
        self.assertNotIn("git commit", commands)
        self.assertNotIn("ca-commit", commands)
        self.assertNotIn("ca:commit", commands)
        self.assertNotIn("task done", commands)
        self.assertIn("prepare F03-work-the-board", commands)
        self.assertIn("check F03-work-the-board", commands)
        self.assertIn("reset F03-work-the-board", commands)
        self.assertIn("preview-0.30", commands)
        self.assertIn("From the clean retained F03 attempt branch", by_id["F03-reset-retry"].instruction)
        self.assertNotIn("From clean main", by_id["F03-reset-retry"].instruction)
        handoff = by_id["F03-return-to-main"]
        self.assertEqual((handoff.actor, handoff.surface), ("learner", None))
        for variant in handoff.variants:
            with self.subTest(variant=variant.id):
                self.assertEqual(variant.command, "git switch main\ngit status --short")
        self.assertIn("completed numbered F03 attempt branch", handoff.expected_result)
        self.assertIn("do not force-switch", handoff.recovery)

        action_copy = "\n".join(
            part for action in manifest.actions
            for part in (action.instruction, action.expected_result, action.recovery, action.evidence or "")
        )
        self.assertNotIn("Future private-source walkthrough", action_copy)
        self.assertNotIn("future", action_copy.casefold())
        self.assertNotIn("refuse", action_copy)
        self.assertNotIn("Preview 0.25", action_copy)

        review_copy = "\n".join(
            part
            for part in (
                by_id["F03-review-co-commit-boundary"].instruction,
                by_id["F03-review-co-commit-boundary"].expected_result,
                by_id["F03-review-co-commit-boundary"].recovery,
                by_id["F03-review-co-commit-boundary"].evidence or "",
            )
        )
        self.assertIn(".codearbiter/open-tasks.md", review_copy)
        self.assertIn("docs/ticket-list-contract.md", review_copy)
        self.assertIn("staged", review_copy)
        self.assertIn("[~]", review_copy)
        self.assertIn("one commit", review_copy)
        review = by_id["F03-review-co-commit-boundary"]
        self.assertEqual((review.actor, review.surface), ("learner", None))
        self.assertEqual(
            tuple(
                (
                    variant.surface,
                    variant.operating_system,
                    variant.host,
                    variant.language,
                    variant.command,
                    variant.copy,
                )
                for variant in review.variants
            ),
            (
                (
                    "native-terminal",
                    "windows",
                    "none",
                    "powershell",
                    "git diff --staged --name-only\ngit diff --staged",
                    True,
                ),
                (
                    "native-terminal",
                    "macos",
                    "none",
                    "sh",
                    "git diff --staged --name-only\ngit diff --staged",
                    True,
                ),
                (
                    "native-terminal",
                    "linux",
                    "none",
                    "sh",
                    "git diff --staged --name-only\ngit diff --staged",
                    True,
                ),
            ),
        )
        self.assertIn("only after both", review.instruction)
        self.assertIn("exactly .codearbiter/open-tasks.md and docs/ticket-list-contract.md", review.expected_result)
        self.assertIn("both inspections", review.recovery)

        finish_copy = "\n".join(
            part
            for part in (
                by_id["F03-choose-keep-branch"].instruction,
                by_id["F03-choose-keep-branch"].expected_result,
                by_id["F03-choose-keep-branch"].recovery,
                by_id["F03-choose-keep-branch"].evidence or "",
            )
        )
        self.assertIn("Keep the branch as-is", finish_copy)
        self.assertIn("no hosted pull request", finish_copy)

        check_copy = "\n".join(
            part
            for part in (
                by_id["F03-check"].instruction,
                by_id["F03-check"].expected_result,
                by_id["F03-check"].recovery,
                by_id["F03-check"].evidence or "",
            )
        )
        self.assertIn("cannot prove `$ca-task` ran", check_copy)
        self.assertIn("cannot prove `$ca-chore` ran", check_copy)
        self.assertNotIn("reconstruct an agent invocation", check_copy)

        clean_copy = "\n".join(
            part
            for part in (
                by_id["F03-confirm-clean"].instruction,
                by_id["F03-confirm-clean"].expected_result,
                by_id["F03-confirm-clean"].recovery,
                by_id["F03-confirm-clean"].evidence or "",
            )
        )
        self.assertIn("no non-ignored worktree state", clean_copy)
        self.assertIn("one post-Prepare commit", clean_copy)

    def test_checked_in_f02_manifest_encodes_the_complete_ordered_lifecycle(self) -> None:
        manifest = load_action_manifest(Path(__file__).parents[1], F02_DOCUMENT_ID)

        self.assertEqual(tuple(action.id for action in manifest.actions), F02_ACTION_IDS)
        self.assertTrue(all(action.expected_result for action in manifest.actions))
        self.assertTrue(all(action.recovery for action in manifest.actions))

        by_id = {action.id: action for action in manifest.actions}
        for action_id in ("F02-run-status", "F02-run-commit-gate"):
            action = by_id[action_id]
            self.assertEqual(action.actor, "agent")
            self.assertEqual(
                tuple((variant.host, variant.command) for variant in action.variants),
                (
                    ("claude-code", "/ca:" + ("status" if action_id == "F02-run-status" else "commit")),
                    ("codex", "$ca-" + ("status" if action_id == "F02-run-status" else "commit")),
                    ("pi", "/ca-" + ("status" if action_id == "F02-run-status" else "commit")),
                    ("pi", "/skill:ca-" + ("status" if action_id == "F02-run-status" else "commit")),
                ),
            )
            self.assertTrue(all(variant.language == "codearbiter" for variant in action.variants))
            self.assertFalse(any(variant.command.startswith("!") for variant in action.variants))

        self.assertEqual(by_id["F02-write-orientation"].actor, "learner")
        self.assertEqual(by_id["F02-stage-orientation"].actor, "learner")

        context_links = by_id["F02-follow-context-links"]
        context_prompt = (
            "Open each file in order, then give this four-item orientation report: the queued task ID, "
            "both ADR decisions, the verification command, and the local-only data boundary. Read these files "
            "in order: .codearbiter/specs/ticket-assignment.md, "
            ".codearbiter/plans/ticket-assignment.md, .codearbiter/decisions/0001-json-storage-boundary.md, "
            ".codearbiter/decisions/0002-explicit-ticket-state-machine.md, .codearbiter/coding-standards.md, "
            ".codearbiter/tech-stack.md, .codearbiter/security-controls.md, .codearbiter/open-tasks.md, "
            "and .codearbiter/open-questions.md."
        )
        self.assertIsNone(context_links.surface)
        self.assertEqual(
            tuple(
                (variant.surface, variant.host, variant.language, variant.command, variant.copy)
                for variant in context_links.variants
            ),
            (
                ("harness", "claude-code", "text", context_prompt, True),
                ("harness", "codex", "text", context_prompt, True),
                ("harness", "pi", "text", context_prompt, True),
            ),
        )

        boundary = by_id["F02-review-commit-boundary"]
        review_prompt = (
            "Show the staged path list and staged diff. Do not commit. Report whether the staged path "
            "list is exactly .codearbiter/reports/academy/F02-orientation.json and whether the diff "
            "contains exactly schema_version, context_path, context_sha256, and stage."
        )
        self.assertIsNone(boundary.surface)
        self.assertEqual(
            tuple(
                (variant.surface, variant.host, variant.language, variant.command, variant.copy)
                for variant in boundary.variants
            ),
            (
                ("harness", "claude-code", "text", review_prompt, True),
                ("harness", "codex", "text", review_prompt, True),
                ("harness", "pi", "text", review_prompt, True),
            ),
        )

    def test_checked_in_f02_commands_are_surface_correct_and_beginner_safe(self) -> None:
        manifest = load_action_manifest(Path(__file__).parents[1], F02_DOCUMENT_ID)
        by_id = {action.id: action for action in manifest.actions}

        shell_variants = tuple(
            variant
            for action in manifest.actions
            for variant in action.variants
            if variant.language in {"powershell", "sh"}
        )
        self.assertTrue(shell_variants)
        for variant in shell_variants:
            with self.subTest(variant=variant.id):
                if variant.surface == "harness":
                    self.assertNotEqual(variant.host, "none")
                    self.assertTrue(variant.command.startswith("!"))
                    self.assertFalse(variant.command.startswith("!!"))
                else:
                    self.assertEqual(variant.surface, "native-terminal")
                    self.assertEqual(variant.host, "none")
                    self.assertFalse(variant.command.startswith("!"))
                self.assertNotIn("python scripts/academy.py", variant.command)
                self.assertNotIn("<learner-repository>", variant.command)

        write_commands = {
            variant.operating_system: variant.command
            for variant in by_id["F02-write-orientation"].variants
            if variant.surface == "native-terminal"
        }
        self.assertIn("ConvertTo-Json", write_commands["windows"])
        self.assertIn("WriteAllText", write_commands["windows"])
        self.assertIn("context_sha256", write_commands["windows"])
        windows_hash = next(
            variant.command
            for variant in by_id["F02-hash-context"].variants
            if variant.operating_system == "windows"
        )
        for command in (windows_hash, write_commands["windows"]):
            self.assertIn("ComputeHash", command)
            self.assertNotIn("HashData", command)
            self.assertNotIn("ToHexString", command)
        for operating_system in ("macos", "linux"):
            self.assertIn("json.dump", write_commands[operating_system])
            self.assertIn("context_sha256", write_commands[operating_system])

    def test_checked_in_f01_manifest_encodes_the_complete_ordered_lifecycle(self) -> None:
        manifest = load_action_manifest(Path(__file__).parents[1], DOCUMENT_ID)

        self.assertEqual(tuple(action.id for action in manifest.actions), F01_ACTION_IDS)
        self.assertTrue(all(action.expected_result for action in manifest.actions))
        self.assertTrue(all(action.recovery for action in manifest.actions))

        by_id = {action.id: action for action in manifest.actions}
        host_doctor = by_id["F01-host-doctor"]
        self.assertEqual(
            tuple((variant.host, variant.command) for variant in host_doctor.variants),
            (
                ("claude-code", "/ca:doctor"),
                ("codex", "$ca-doctor"),
                ("pi", "/ca-doctor"),
                ("pi", "/skill:ca-doctor"),
            ),
        )
        commit = by_id["F01-commit-report"]
        self.assertEqual(commit.actor, "agent")
        self.assertIsNone(commit.surface)
        self.assertEqual(
            tuple((variant.host, variant.command) for variant in commit.variants),
            (
                ("claude-code", "/ca:commit"),
                ("codex", "$ca-commit"),
                ("pi", "/ca-commit"),
                ("pi", "/skill:ca-commit"),
            ),
        )
        self.assertTrue(all(variant.language == "codearbiter" for variant in commit.variants))
        self.assertFalse(any(variant.command.startswith("!") for variant in commit.variants))
        self.assertEqual(by_id["F01-stage-report"].actor, "learner")
        self.assertEqual(by_id["F01-review-commit-boundary"].actor, "learner")
        self.assertIsNone(by_id["F01-review-commit-boundary"].surface)
        boundary_variants = by_id["F01-review-commit-boundary"].variants
        self.assertEqual(
            tuple((variant.host, variant.language, variant.surface, variant.copy) for variant in boundary_variants),
            (("claude-code", "text", "harness", True), ("codex", "text", "harness", True), ("pi", "text", "harness", True)),
        )
        self.assertTrue(
            all(
                "Show the staged path list and staged diff. Do not commit." in variant.command
                and ".codearbiter/reports/academy/F01-doctor.json" in variant.command
                and not variant.command.startswith("!")
                for variant in boundary_variants
            )
        )

    def test_checked_in_f01_shell_variants_name_surface_and_passthrough_exactly(self) -> None:
        manifest = load_action_manifest(Path(__file__).parents[1], DOCUMENT_ID)
        shell_variants = tuple(
            variant
            for action in manifest.actions
            for variant in action.variants
            if variant.language in {"powershell", "sh"}
        )

        self.assertTrue(shell_variants)
        for variant in shell_variants:
            with self.subTest(variant=variant.id):
                if variant.surface == "harness":
                    self.assertNotEqual(variant.host, "none")
                    self.assertTrue(variant.command.startswith("!"))
                    self.assertFalse(variant.command.startswith("!!"))
                else:
                    self.assertEqual(variant.surface, "native-terminal")
                    self.assertEqual(variant.host, "none")
                    self.assertFalse(variant.command.startswith("!"))

    def schema(self) -> dict[str, object]:
        root = Path(__file__).parents[1]
        return json.loads(
            (root / "academy" / "lesson-action.schema.json").read_text(encoding="utf-8")
        )

    def schema_string_accepts(self, definition: dict[str, object], value: str) -> bool:
        return (
            int(definition["minLength"]) <= len(value) <= int(definition["maxLength"])
            and re.search(str(definition["pattern"]), value) is not None
        )

    def command_action(self, **variant_changes: object) -> dict[str, object]:
        variant: dict[str, object] = {
            "id": "status-codex-linux",
            "surface": "harness",
            "operating_system": "linux",
            "host": "codex",
            "language": "sh",
            "command": "!git status --short",
            "copy": True,
        }
        variant.update(variant_changes)
        return {
            "id": "inspect-status",
            "sequence": 1,
            "title": "Inspect the worktree",
            "actor": "learner",
            "surface": None,
            "instruction": "Run the status command in the named surface.",
            "rationale": "A clean worktree makes the evidence boundary explicit.",
            "resources": [],
            "variants": [variant],
            "expected_result": "Git prints no changed paths.",
            "recovery": "Restore only the lesson changes, then run the command again.",
            "evidence": "The later Academy Check reads the same worktree state.",
        }

    def non_command_action(self) -> dict[str, object]:
        return {
            "id": "read-prerequisites",
            "sequence": 1,
            "title": "Read the prerequisites",
            "actor": "learner",
            "surface": "browser",
            "instruction": "Read the prerequisite explanation before changing the repository.",
            "rationale": None,
            "resources": [],
            "variants": [],
            "expected_result": "You can identify the fork, origin, and upstream repositories.",
            "recovery": "Return to the prerequisite section and compare each repository role.",
            "evidence": None,
        }

    def manifest(self, action: dict[str, object] | None = None) -> dict[str, object]:
        return {
            "schema_version": 1,
            "lesson_contract_version": 1,
            "document_id": DOCUMENT_ID,
            "actions": [action or self.command_action()],
        }

    def test_valid_command_manifest_returns_frozen_typed_models(self) -> None:
        manifest = validate_action_manifest(self.manifest(), expected_document_id=DOCUMENT_ID)

        self.assertEqual(
            manifest,
            LessonActionManifest(
                schema_version=1,
                lesson_contract_version=1,
                document_id=DOCUMENT_ID,
                actions=(
                    LessonAction(
                        id="inspect-status",
                        sequence=1,
                        title="Inspect the worktree",
                        actor="learner",
                        surface=None,
                        instruction="Run the status command in the named surface.",
                        rationale="A clean worktree makes the evidence boundary explicit.",
                        resources=(),
                        variants=(
                            CommandVariant(
                                id="status-codex-linux",
                                surface="harness",
                                operating_system="linux",
                                host="codex",
                                language="sh",
                                command="!git status --short",
                                copy=True,
                            ),
                        ),
                        expected_result="Git prints no changed paths.",
                        recovery="Restore only the lesson changes, then run the command again.",
                        evidence="The later Academy Check reads the same worktree state.",
                    ),
                ),
            ),
        )
        with self.assertRaises(Exception):
            manifest.actions[0].title = "changed"  # type: ignore[misc]

    def test_valid_non_command_action_has_one_declared_surface(self) -> None:
        manifest = validate_action_manifest(
            self.manifest(self.non_command_action()), expected_document_id=DOCUMENT_ID
        )

        self.assertEqual(manifest.actions[0].surface, "browser")
        self.assertEqual(manifest.actions[0].variants, ())

    def test_action_resources_are_typed_bounded_and_repository_scoped(self) -> None:
        """Catches installer evidence links that escape the reviewed Academy repository."""
        action = self.command_action()
        action["resources"] = [
            {
                "label": "Review the immutable PowerShell installer",
                "href": "https://github.com/arbiterForge/arbiter-academy/blob/preview-0.3/install/install.ps1",
            }
        ]

        result = validate_action_manifest(self.manifest(action), expected_document_id=DOCUMENT_ID)

        self.assertEqual(result.actions[0].resources[0].label, "Review the immutable PowerShell installer")
        self.assertEqual(
            result.actions[0].resources[0].href,
            "https://github.com/arbiterForge/arbiter-academy/blob/preview-0.3/install/install.ps1",
        )

        invalid = (
            ("too-many", [{"label": "Source", "href": "https://github.com/arbiterForge/arbiter-academy"}] * 5),
            ("other-host", [{"label": "Source", "href": "https://example.com/arbiterForge/arbiter-academy"}]),
            ("credentials", [{"label": "Source", "href": "https://user@github.com/arbiterForge/arbiter-academy"}]),
            ("query", [{"label": "Source", "href": "https://github.com/arbiterForge/arbiter-academy?raw=1"}]),
            ("fragment", [{"label": "Source", "href": "https://github.com/arbiterForge/arbiter-academy#source"}]),
            ("root-relative", [{"label": "Source", "href": "/recovery/"}]),
            ("encoded-control", [{"label": "Source", "href": "https://github.com/arbiterForge/arbiter-academy/blob/main/file%0a"}]),
            ("traversal", [{"label": "Source", "href": "https://github.com/arbiterForge/arbiter-academy/blob/preview-0.3/%2e%2e/secret"}]),
            ("double-traversal", [{"label": "Source", "href": "https://github.com/arbiterForge/arbiter-academy/blob/preview-0.3/%252e%252e/secret"}]),
            ("scheme", [{"label": "Source", "href": "javascript:alert(1)"}]),
            ("backslash", [{"label": "Source", "href": "https://github.com/arbiterForge/arbiter-academy/blob\\main\\file"}]),
            ("blank-label", [{"label": "   ", "href": "https://github.com/arbiterForge/arbiter-academy"}]),
            ("long-label", [{"label": "x" * 161, "href": "https://github.com/arbiterForge/arbiter-academy"}]),
            ("long-href", [{"label": "Source", "href": "/" + "x" * 2048}]),
        )
        for label, resources in invalid:
            mutated = self.command_action()
            mutated["resources"] = resources
            with self.subTest(label=label):
                with self.assertRaises(ValueError):
                    validate_action_manifest(self.manifest(mutated), expected_document_id=DOCUMENT_ID)

    def test_resource_runtime_and_schema_share_exact_keys_and_bounds(self) -> None:
        schema = self.schema()
        resource = schema["$defs"]["resource"]  # type: ignore[index]

        self.assertFalse(resource["additionalProperties"])
        self.assertEqual(resource["required"], ["label", "href"])
        self.assertEqual(resource["properties"]["label"]["maxLength"], 160)
        self.assertEqual(resource["properties"]["href"]["maxLength"], 2048)
        self.assertEqual(schema["$defs"]["action"]["properties"]["resources"]["maxItems"], 4)
        href_schema = resource["properties"]["href"]
        self.assertTrue(
            self.schema_string_accepts(
                href_schema,
                "https://github.com/arbiterForge/arbiter-academy/blob/preview-0.3/install/install.sh",
            )
        )
        self.assertTrue(self.schema_string_accepts(href_schema, F01_DEPLOYED_LESSON))
        for href in (
            "https://example.com/arbiterForge/arbiter-academy",
            "https://github.com/arbiterForge/arbiter-academy?raw=1",
            "//github.com/arbiterForge/arbiter-academy",
            "/recovery/",
            "https://github.com/arbiterForge/arbiter-academy/blob/main/%0a",
            "https://github.com/arbiterForge/arbiter-academy/blob/main/%252e%252e/secret",
            "https://github.com/arbiterForge/arbiter-academy/blob/main/../secret",
            "https://github.com/arbiterForge/arbiter-academy/blob\\main\\file",
        ):
            self.assertFalse(self.schema_string_accepts(href_schema, href), href)

    def test_public_resource_validator_is_the_canonical_narrow_contract(self) -> None:
        accepted = (
            "https://github.com/arbiterForge/arbiter-academy",
            "https://github.com/arbiterForge/arbiter-academy/releases/download/preview-0.3/install.sh.sha256",
            F01_DEPLOYED_LESSON,
        )
        for href in accepted:
            with self.subTest(href=href):
                self.assertEqual(validate_action_resource_href(href), href)

        for href in (
            "/recovery/",
            "https://user@github.com/arbiterForge/arbiter-academy",
            "https://github.com/arbiterForge/arbiter-academy?raw=1",
            "https://github.com/arbiterForge/arbiter-academy#source",
            "https://github.com/arbiterForge/arbiter-academy/blob/main/%0a",
            "https://github.com/arbiterForge/arbiter-academy/blob/main/../secret",
        ):
            with self.subTest(href=href):
                with self.assertRaises(ValueError):
                    validate_action_resource_href(href)

    def test_non_command_actions_reject_harness_without_a_named_host(self) -> None:
        """Catches a host-ambiguous harness step with no command variant identity."""
        action = self.non_command_action()
        action["surface"] = "harness"

        with self.assertRaisesRegex(ValueError, "non-command actions cannot use harness"):
            validate_action_manifest(self.manifest(action), expected_document_id=DOCUMENT_ID)

        schema = self.schema()
        non_command_surfaces = schema["$defs"]["action"]["oneOf"][0]["properties"][  # type: ignore[index]
            "surface"
        ]["enum"]
        self.assertEqual(
            non_command_surfaces,
            ["browser", "native-terminal", "academy-console", "active-harness"],
        )

    def test_active_harness_is_closed_to_non_command_review_actions(self) -> None:
        action = self.non_command_action()
        action["surface"] = "active-harness"
        schema = self.schema()

        result = validate_action_manifest(
            self.manifest(action), expected_document_id=DOCUMENT_ID
        )

        self.assertEqual(result.actions[0].surface, "active-harness")
        self.assertNotIn(
            "active-harness", schema["$defs"]["variant"]["properties"]["surface"]["enum"]
        )
        action["variants"] = [self.command_action()["variants"][0]]
        action["surface"] = None
        action["id"] = "active-harness-command"
        action["variants"][0]["surface"] = "active-harness"  # type: ignore[index]
        with self.assertRaisesRegex(ValueError, "allowed"):
            validate_action_manifest(self.manifest(action), expected_document_id=DOCUMENT_ID)

    def test_rejects_unknown_or_missing_keys_at_every_level(self) -> None:
        cases: list[tuple[str, dict[str, object]]] = []
        unknown_manifest = self.manifest()
        unknown_manifest["extra"] = "no"
        cases.append(("manifest", unknown_manifest))
        missing_action = self.manifest()
        del missing_action["actions"][0]["recovery"]  # type: ignore[index]
        cases.append(("action", missing_action))
        unknown_variant = self.manifest()
        unknown_variant["actions"][0]["variants"][0]["display_command"] = "different"  # type: ignore[index]
        cases.append(("variant", unknown_variant))

        for level, data in cases:
            with self.subTest(level=level):
                with self.assertRaisesRegex(ValueError, "exact keys"):
                    validate_action_manifest(data, expected_document_id=DOCUMENT_ID)

    def test_versions_and_sequences_require_integers_not_booleans(self) -> None:
        mutations = (
            ("schema_version", True),
            ("lesson_contract_version", True),
            ("sequence", True),
        )
        for field, value in mutations:
            data = self.manifest()
            if field == "sequence":
                data["actions"][0][field] = value  # type: ignore[index]
            else:
                data[field] = value
            with self.subTest(field=field):
                with self.assertRaisesRegex(ValueError, "integer"):
                    validate_action_manifest(data, expected_document_id=DOCUMENT_ID)

    def test_contract_versions_are_pinned_to_one(self) -> None:
        for field in ("schema_version", "lesson_contract_version"):
            data = self.manifest()
            data[field] = 2
            with self.subTest(field=field):
                with self.assertRaisesRegex(ValueError, "must be integer 1"):
                    validate_action_manifest(data, expected_document_id=DOCUMENT_ID)

    def test_ids_are_bounded_and_path_safe(self) -> None:
        unsafe_ids = ("", ".", "..", "../lesson", "lesson/name", "lesson\\name", "-lesson", "a" * 97)
        for unsafe_id in unsafe_ids:
            data = self.manifest()
            data["actions"][0]["id"] = unsafe_id  # type: ignore[index]
            with self.subTest(unsafe_id=unsafe_id):
                with self.assertRaisesRegex(ValueError, "safe ID"):
                    validate_action_manifest(data, expected_document_id=DOCUMENT_ID)

    def test_runtime_and_schema_share_the_ascii_id_character_limit(self) -> None:
        schema = self.schema()
        id_schema = schema["$defs"]["id"]  # type: ignore[index]
        bounded_id = "a" * 96
        action = self.command_action()
        action["id"] = bounded_id
        action["variants"][0]["id"] = bounded_id  # type: ignore[index]
        data = self.manifest(action)
        data["document_id"] = bounded_id

        result = validate_action_manifest(data, expected_document_id=bounded_id)

        self.assertEqual(result.document_id, bounded_id)
        self.assertEqual(result.actions[0].id, bounded_id)
        self.assertEqual(result.actions[0].variants[0].id, bounded_id)
        self.assertTrue(self.schema_string_accepts(id_schema, bounded_id))
        self.assertFalse(self.schema_string_accepts(id_schema, "a" * 97))

    def test_document_id_must_match_the_requested_document(self) -> None:
        with self.assertRaisesRegex(ValueError, "document_id must match"):
            validate_action_manifest(self.manifest(), expected_document_id="F02-orient-to-state")

    def test_actions_are_limited_unique_and_contiguously_sequenced(self) -> None:
        duplicate = self.command_action()
        duplicate["sequence"] = 2
        for label, actions, message in (
            ("duplicate", [self.command_action(), duplicate], "unique action IDs"),
            ("gap", [self.command_action(), {**deepcopy(duplicate), "id": "second", "sequence": 3}], "contiguous"),
            ("too-many", [{**self.non_command_action(), "id": f"action-{index}", "sequence": index + 1} for index in range(65)], "at most 64"),
        ):
            data = self.manifest()
            data["actions"] = actions
            with self.subTest(label=label):
                with self.assertRaisesRegex(ValueError, message):
                    validate_action_manifest(data, expected_document_id=DOCUMENT_ID)

    def test_action_enumerations_are_closed(self) -> None:
        for field, value in (("actor", "operator"), ("surface", "terminal")):
            action = self.non_command_action()
            action[field] = value
            with self.subTest(field=field):
                with self.assertRaisesRegex(ValueError, "allowed"):
                    validate_action_manifest(self.manifest(action), expected_document_id=DOCUMENT_ID)

    def test_variant_enumerations_are_closed(self) -> None:
        for field, value in (
            ("surface", "terminal"),
            ("operating_system", "freebsd"),
            ("host", "other"),
            ("language", "bash"),
        ):
            with self.subTest(field=field):
                data = self.manifest(self.command_action(**{field: value}))
                with self.assertRaisesRegex(ValueError, "allowed"):
                    validate_action_manifest(data, expected_document_id=DOCUMENT_ID)

    def test_command_and_non_command_shapes_cannot_be_ambiguous(self) -> None:
        command_with_surface = self.command_action()
        command_with_surface["surface"] = "browser"
        non_command_without_surface = self.non_command_action()
        non_command_without_surface["surface"] = None
        for label, action in (
            ("command", command_with_surface),
            ("non-command", non_command_without_surface),
        ):
            with self.subTest(label=label):
                with self.assertRaisesRegex(ValueError, "command actions|non-command actions"):
                    validate_action_manifest(self.manifest(action), expected_document_id=DOCUMENT_ID)

    def test_variants_are_limited_and_unique(self) -> None:
        action = self.command_action()
        variant = deepcopy(action["variants"][0])  # type: ignore[index]
        action["variants"] = [deepcopy(variant), deepcopy(variant)]
        with self.assertRaisesRegex(ValueError, "unique variant IDs"):
            validate_action_manifest(self.manifest(action), expected_document_id=DOCUMENT_ID)

        action["variants"] = [{**deepcopy(variant), "id": f"variant-{index}"} for index in range(13)]
        with self.assertRaisesRegex(ValueError, "at most 12"):
            validate_action_manifest(self.manifest(action), expected_document_id=DOCUMENT_ID)

    def test_copy_policy_is_an_explicit_boolean(self) -> None:
        for copy in (1, "yes", None):
            with self.subTest(copy=copy):
                data = self.manifest(self.command_action(copy=copy))
                with self.assertRaisesRegex(ValueError, "copy must be a boolean"):
                    validate_action_manifest(data, expected_document_id=DOCUMENT_ID)

        result = validate_action_manifest(
            self.manifest(self.command_action(copy=False)), expected_document_id=DOCUMENT_ID
        )
        self.assertFalse(result.actions[0].variants[0].copy)

    def test_harness_shell_requires_exactly_one_passthrough_prefix(self) -> None:
        for command in ("git status", "!!git status"):
            with self.subTest(command=command):
                data = self.manifest(self.command_action(command=command))
                with self.assertRaisesRegex(ValueError, "exactly one !"):
                    validate_action_manifest(data, expected_document_id=DOCUMENT_ID)

    def test_codearbiter_invocations_reject_shell_passthrough(self) -> None:
        data = self.manifest(
            self.command_action(command="!$ca-doctor", language="codearbiter")
        )
        with self.assertRaisesRegex(ValueError, "must not begin with !"):
            validate_action_manifest(data, expected_document_id=DOCUMENT_ID)

    def test_native_terminal_uses_no_host_and_never_uses_passthrough(self) -> None:
        for field, value, message in (
            ("host", "codex", "host none"),
            ("command", "!git status", "must not begin with !"),
        ):
            action = self.command_action(
                surface="native-terminal",
                host="none",
                operating_system="windows",
                language="powershell",
                command="git status",
            )
            action["variants"][0][field] = value  # type: ignore[index]
            data = self.manifest(action)
            with self.subTest(field=field):
                with self.assertRaisesRegex(ValueError, message):
                    validate_action_manifest(data, expected_document_id=DOCUMENT_ID)

    def test_harness_requires_a_named_host(self) -> None:
        data = self.manifest(self.command_action(host="none"))
        with self.assertRaisesRegex(ValueError, "named host"):
            validate_action_manifest(data, expected_document_id=DOCUMENT_ID)

    def test_codearbiter_language_requires_a_harness_and_named_host(self) -> None:
        data = self.manifest(
            self.command_action(
                surface="native-terminal",
                host="none",
                operating_system="all",
                language="codearbiter",
                command="$ca-doctor",
            )
        )
        with self.assertRaisesRegex(ValueError, "CodeArbiter commands require a harness"):
            validate_action_manifest(data, expected_document_id=DOCUMENT_ID)

    def test_codearbiter_commands_use_each_hosts_native_invocation(self) -> None:
        cases = (
            ("claude-code", "/ca-doctor", "Claude Code"),
            ("codex", "/ca:doctor", "Codex"),
            ("pi", "$ca-doctor", "Pi"),
        )
        for host, command, message in cases:
            data = self.manifest(
                self.command_action(host=host, language="codearbiter", command=command)
            )
            with self.subTest(host=host):
                with self.assertRaisesRegex(ValueError, message):
                    validate_action_manifest(data, expected_document_id=DOCUMENT_ID)

    def test_prose_and_commands_are_bounded_and_control_safe(self) -> None:
        cases: list[tuple[str, dict[str, object], str]] = []
        for field in ("title", "instruction", "rationale", "expected_result", "recovery", "evidence"):
            action = self.command_action()
            action[field] = "x" * 1025
            cases.append((field, self.manifest(action), "at most 1024"))
        empty_expected = self.command_action()
        empty_expected["expected_result"] = "   "
        cases.append(("expected", self.manifest(empty_expected), "must not be empty"))
        empty_recovery = self.command_action()
        empty_recovery["recovery"] = ""
        cases.append(("recovery", self.manifest(empty_recovery), "must not be empty"))
        control = self.command_action()
        control["instruction"] = "unsafe\nprose"
        cases.append(("prose-control", self.manifest(control), "ASCII controls"))
        long_command = self.command_action(command="!" + "x" * 8192)
        cases.append(("long-command", self.manifest(long_command), "at most 8192"))
        command_control = self.command_action(command="!git\tstatus")
        cases.append(("command-control", self.manifest(command_control), "ASCII controls"))
        command_cr = self.command_action(command="!git status\r\n")
        cases.append(("command-cr", self.manifest(command_cr), "CR"))

        for label, data, message in cases:
            with self.subTest(label=label):
                with self.assertRaisesRegex(ValueError, message):
                    validate_action_manifest(data, expected_document_id=DOCUMENT_ID)

    def test_runtime_and_schema_use_unicode_code_point_limits_for_every_bounded_string(self) -> None:
        schema = self.schema()
        prose_schema = schema["$defs"]["prose"]  # type: ignore[index]
        command_schema = schema["$defs"]["variant"]["properties"]["command"]  # type: ignore[index]
        accepted_prose = "é" * 600
        rejected_prose = "é" * 1025
        accepted_command = "!" + "é" * 600
        rejected_command = "!" + "é" * 8192

        for field in (
            "title",
            "instruction",
            "rationale",
            "expected_result",
            "recovery",
            "evidence",
        ):
            action = self.command_action()
            action[field] = accepted_prose
            with self.subTest(field=field, boundary="accepted"):
                result = validate_action_manifest(
                    self.manifest(action), expected_document_id=DOCUMENT_ID
                )
                self.assertEqual(getattr(result.actions[0], field), accepted_prose)
                self.assertTrue(self.schema_string_accepts(prose_schema, accepted_prose))

            action[field] = rejected_prose
            with self.subTest(field=field, boundary="rejected"):
                with self.assertRaisesRegex(ValueError, "at most 1024 characters"):
                    validate_action_manifest(
                        self.manifest(action), expected_document_id=DOCUMENT_ID
                    )
                self.assertFalse(self.schema_string_accepts(prose_schema, rejected_prose))

        accepted = validate_action_manifest(
            self.manifest(self.command_action(command=accepted_command)),
            expected_document_id=DOCUMENT_ID,
        )
        self.assertEqual(accepted.actions[0].variants[0].command, accepted_command)
        self.assertTrue(self.schema_string_accepts(command_schema, accepted_command))
        with self.assertRaisesRegex(ValueError, "at most 8192 characters"):
            validate_action_manifest(
                self.manifest(self.command_action(command=rejected_command)),
                expected_document_id=DOCUMENT_ID,
            )
        self.assertFalse(self.schema_string_accepts(command_schema, rejected_command))

    def test_runtime_and_schema_reject_whitespace_only_bounded_strings(self) -> None:
        schema = self.schema()
        prose_schema = schema["$defs"]["prose"]  # type: ignore[index]
        command_schema = schema["$defs"]["variant"]["properties"]["command"]  # type: ignore[index]

        for field in (
            "title",
            "instruction",
            "rationale",
            "expected_result",
            "recovery",
            "evidence",
        ):
            action = self.command_action()
            action[field] = "   "
            with self.subTest(field=field):
                with self.assertRaisesRegex(ValueError, "must not be empty"):
                    validate_action_manifest(
                        self.manifest(action), expected_document_id=DOCUMENT_ID
                    )
                self.assertFalse(self.schema_string_accepts(prose_schema, "   "))

        whitespace_command = "   "
        with self.assertRaisesRegex(ValueError, "must not be empty"):
            validate_action_manifest(
                self.manifest(self.command_action(command=whitespace_command)),
                expected_document_id=DOCUMENT_ID,
            )
        self.assertFalse(self.schema_string_accepts(command_schema, whitespace_command))

    def test_command_newlines_are_allowed_and_preserved_as_visible_copy_bytes(self) -> None:
        command = "!git status --short\nprintf 'done\\n'"
        data = self.manifest(self.command_action(command=command))

        result = validate_action_manifest(data, expected_document_id=DOCUMENT_ID)

        self.assertEqual(result.actions[0].variants[0].command, command)

    def test_loader_rejects_unsafe_document_ids_before_filesystem_access(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for document_id in ("../outside", "lesson/name", "lesson\\name", ".", ".."):
                with self.subTest(document_id=document_id):
                    with self.assertRaisesRegex(ValueError, "safe ID"):
                        load_action_manifest(root, document_id)

    def test_loader_reads_only_the_named_action_manifest_and_validates_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            actions = root / "academy" / "actions"
            actions.mkdir(parents=True)
            (actions / f"{DOCUMENT_ID}.json").write_text(
                json.dumps(self.manifest()), encoding="utf-8", newline="\n"
            )

            result = load_action_manifest(root, DOCUMENT_ID)

            self.assertEqual(result.document_id, DOCUMENT_ID)

    def test_loader_rejects_an_actions_ancestor_symlink_outside_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "root"
            academy = root / "academy"
            outside = base / "outside-actions"
            academy.mkdir(parents=True)
            outside.mkdir()
            (outside / f"{DOCUMENT_ID}.json").write_text(
                json.dumps(self.manifest()), encoding="utf-8", newline="\n"
            )
            try:
                (academy / "actions").symlink_to(outside, target_is_directory=True)
            except OSError as error:
                self.skipTest(f"directory symlinks are unavailable: {error}")

            with self.assertRaisesRegex(ValueError, "symlink or reparse"):
                load_action_manifest(root, DOCUMENT_ID)

    def test_loader_rejects_a_manifest_symlink_outside_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "root"
            actions = root / "academy" / "actions"
            outside = base / "outside.json"
            actions.mkdir(parents=True)
            outside.write_text(json.dumps(self.manifest()), encoding="utf-8", newline="\n")
            try:
                (actions / f"{DOCUMENT_ID}.json").symlink_to(outside)
            except OSError as error:
                self.skipTest(f"file symlinks are unavailable: {error}")

            with self.assertRaisesRegex(ValueError, "symlink or reparse"):
                load_action_manifest(root, DOCUMENT_ID)

    def test_loader_fails_closed_for_missing_malformed_or_mismatched_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            actions = root / "academy" / "actions"
            actions.mkdir(parents=True)
            with self.assertRaisesRegex(ValueError, "could not read lesson action manifest"):
                load_action_manifest(root, DOCUMENT_ID)
            (actions / f"{DOCUMENT_ID}.json").write_text("{", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "could not read lesson action manifest"):
                load_action_manifest(root, DOCUMENT_ID)
            mismatched = self.manifest()
            mismatched["document_id"] = "F02-orient-to-state"
            (actions / f"{DOCUMENT_ID}.json").write_text(json.dumps(mismatched), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "document_id must match"):
                load_action_manifest(root, DOCUMENT_ID)

    def test_checked_in_schema_is_closed_and_models_both_action_shapes(self) -> None:
        schema = self.schema()

        self.assertFalse(schema["additionalProperties"])
        self.assertFalse(schema["$defs"]["action"]["additionalProperties"])
        self.assertFalse(schema["$defs"]["variant"]["additionalProperties"])
        self.assertEqual(len(schema["$defs"]["action"]["oneOf"]), 2)
        self.assertEqual(schema["properties"]["actions"]["maxItems"], 64)
        self.assertEqual(schema["$defs"]["variant"]["properties"]["command"]["maxLength"], 8192)

    def test_public_p02_manifest_binds_the_offline_receipt_workflow(self) -> None:
        """Catches an action rewrite that loses the local-only recorder boundary."""
        manifest = load_action_manifest(Path(__file__).parents[1], P02_DOCUMENT_ID)
        self.assertEqual(tuple(action.id for action in manifest.actions), P02_ACTION_IDS)
        self.assertTrue(all(action.expected_result and action.recovery for action in manifest.actions))
        by_id = {action.id: action for action in manifest.actions}
        boundary = by_id["P02-read-boundary"]
        self.assertIn("Windows, macOS, and Linux", boundary.instruction)
        self.assertIn("native Windows", boundary.expected_result)
        self.assertNotIn("cannot complete", boundary.expected_result)
        guide = (Path(__file__).parents[1] / "academy/tracks/practitioner/P02-commit-review-pr.md").read_text(encoding="utf-8")
        self.assertNotIn("Native Windows cannot complete", guide)
        prepare = by_id["P02-prepare"]
        self.assertIn("not a directory you can paste literally", prepare.instruction)
        self.assertIn("fork clone you used for P01", prepare.instruction)
        self.assertTrue(all("<learner-repository>" in variant.command for variant in prepare.variants))
        review_request = by_id["P02-request-review"]
        self.assertEqual(
            tuple((variant.host, variant.language) for variant in review_request.variants),
            (("claude-code", "text"), ("codex", "text"), ("pi", "text")),
        )
        self.assertTrue(all("tests/test_cli.py" in variant.command for variant in review_request.variants))
        self.assertTrue(all("workshop_queue/cli.py" in variant.command for variant in review_request.variants))
        self.assertTrue(all("Do not stage, commit, push" in variant.command for variant in review_request.variants))
        staged_work = by_id["P02-stage-work"]
        self.assertEqual(staged_work.sequence, 5)
        self.assertEqual(staged_work.actor, "learner")
        self.assertEqual(
            tuple(variant.surface for variant in staged_work.variants),
            ("native-terminal", "native-terminal", "native-terminal"),
        )
        for variant in staged_work.variants:
            self.assertIn(
                "git add -- tests/test_cli.py workshop_queue/cli.py", variant.command
            )
            self.assertIn("git diff --cached --name-only", variant.command)
        pushed = {
            variant.operating_system: variant.command
            for variant in by_id["P02-prove-and-push"].variants
        }
        self.assertEqual(set(pushed), {"windows", "macos", "linux"})
        self.assertTrue(pushed["windows"].startswith("$branch = git branch --show-current\n"))
        for command in pushed.values():
            self.assertEqual(command.count("git branch --show-current"), 1)
            self.assertIn("git push origin", command)
            self.assertIn("git ls-remote origin", command)
            self.assertIn("git ls-remote upstream", command)
        for action_id in ("P02-record-receipt", "P02-check", "P02-reset"):
            commands = tuple(variant.command for variant in by_id[action_id].variants)
            self.assertTrue(all(CURRENT_RELEASE in command for command in commands))
            self.assertTrue(all("$academy" in command for command in commands))
            self.assertTrue(all(command.splitlines()[0].startswith("academy=") or command.splitlines()[0].startswith("$academy =") for command in commands))
        recorder = by_id["P02-record-receipt"]
        self.assertEqual(
            tuple(variant.operating_system for variant in recorder.variants),
            ("windows", "macos", "linux"),
        )
        commands = tuple(variant.command for variant in recorder.variants)
        self.assertTrue(all("record P02-commit-review-pr --review-declared-cleared" in command for command in commands))
        self.assertNotIn("git add", "\n".join(commands))
        self.assertNotIn("git commit", "\n".join(commands))
        self.assertNotIn("git push", "\n".join(commands))
        for action_id, command in (
            ("P02-run-review", "review"),
            ("P02-run-work-commit", "commit"),
            ("P02-run-receipt-commit", "commit"),
        ):
            self.assertEqual(
                tuple(
                    (variant.host, variant.command)
                    for variant in by_id[action_id].variants
                    if variant.language == "codearbiter"
                ),
                (
                    ("claude-code", f"/ca:{command}"),
                    ("codex", f"$ca-{command}"),
                    ("pi", f"/ca-{command}"),
                    ("pi", f"/skill:ca-{command}"),
                ),
            )

    def test_public_u06_manifest_teaches_preview_without_executing_advanced_surfaces(self) -> None:
        """Catches U06 losing its public boundary, command ownership, or evidence sequence."""
        root = Path(__file__).parents[1]
        manifest = load_action_manifest(root, U06_DOCUMENT_ID)
        manifest_source = (root / "academy/actions/U06-preview-and-advanced-surfaces.json").read_text(encoding="utf-8")
        guide = (root / "academy/tracks/power-user/U06-preview-and-advanced-surfaces.md").read_text(encoding="utf-8")

        self.assertEqual(tuple(action.id for action in manifest.actions), U06_ACTION_IDS)
        self.assertEqual(tuple(action.sequence for action in manifest.actions), tuple(range(1, 19)))
        self.assertEqual(
            tuple(re.findall(r"^## (.+)$", guide, flags=re.MULTILINE)),
            U06_HEADINGS,
        )
        self.assertEqual(
            tuple(re.findall(r"^\{\{action:([^}]+)\}\}$", guide, flags=re.MULTILINE)),
            U06_ACTION_IDS,
        )
        self.assertNotIn("```", guide)

        by_id = {action.id: action for action in manifest.actions}
        self.assertEqual((by_id["U06-confirm-public-boundary"].actor, by_id["U06-confirm-public-boundary"].surface), ("learner", "browser"))
        self.assertEqual(by_id["U06-create-contained-diff"].actor, "agent")
        exact_candidate = (
            "# U06 preview candidate\n\n"
            "## Read-only documentation policy\n\n"
            "Preview may inspect the prepared attempt and report predicted reviewers. "
            "It does not run a sandbox, create a skill, start watch, or convene a tribunal.\n\n"
            "## Evidence\n\n"
            "Record the reviewed commit, candidate tree, exact changed path, and "
            "repository bindings in the U06 Academy record.\n"
        )
        writer = by_id["U06-create-contained-diff"]
        self.assertEqual(
            tuple((variant.id, variant.host) for variant in writer.variants),
            (("claude", "claude-code"), ("codex", "codex"), ("pi-direct", "pi"), ("pi-fallback", "pi")),
        )
        for variant in writer.variants:
            with self.subTest(writer_variant=variant.id):
                marker = "Write this exact UTF-8 body, including final LF:\n"
                body = variant.command.partition(marker)[2].partition(
                    "\nDo not stage, commit, create a report, or run any advanced surface."
                )[0]
                self.assertEqual(body, exact_candidate)
        self.assertEqual(by_id["U06-assess-preview-output"].surface, "active-harness")
        self.assertEqual(by_id["U06-classify-advanced-surfaces"].actor, "learner")
        self.assertEqual(by_id["U06-classify-advanced-surfaces"].surface, "active-harness")

        for action_id in (
            "U06-prepare-attempt", "U06-inspect-scenario", "U06-inspect-seeded-candidate",
            "U06-inspect-preview-input", "U06-stage-candidate", "U06-inspect-binding-report",
            "U06-stage-report", "U06-confirm-clean", "U06-check-status", "U06-reset-retry",
        ):
            variants = by_id[action_id].variants
            with self.subTest(action=action_id):
                self.assertEqual(tuple(variant.operating_system for variant in variants), ("windows", "macos", "linux"))
                self.assertTrue(all(variant.surface == "native-terminal" and variant.host == "none" and variant.copy for variant in variants))
                self.assertFalse(any(variant.command.startswith("!") for variant in variants))

        preview = by_id["U06-run-read-only-preview"]
        self.assertEqual(preview.actor, "agent")
        self.assertEqual(
            tuple((variant.host, variant.command) for variant in preview.variants),
            (("claude-code", "/ca:preview"), ("codex", "$ca-preview"), ("pi", "/ca-preview"), ("pi", "/skill:ca-preview")),
        )
        self.assertTrue(all(variant.language == "codearbiter" and not variant.command.startswith("!") for variant in preview.variants))
        report_writer = by_id["U06-write-binding-report"]
        self.assertTrue(
            all("predicted_reviewers" not in variant.command for variant in report_writer.variants)
        )
        self.assertTrue(
            all("secret_scan" not in variant.command for variant in report_writer.variants)
        )
        self.assertNotIn("reviewers [docs]", "\n".join(variant.command for variant in report_writer.variants))
        for action_id in ("U06-commit-candidate", "U06-commit-report"):
            self.assertEqual(
                tuple((variant.host, variant.command) for variant in by_id[action_id].variants),
                (("claude-code", "/ca:commit"), ("codex", "$ca-commit"), ("pi", "/ca-commit"), ("pi", "/skill:ca-commit")),
            )

        commands = "\n".join(variant.command for action in manifest.actions for variant in action.variants)
        for forbidden in ("ca-sandbox", "ca-new-skill", "ca-watch", "ca-tribunal"):
            self.assertNotIn(forbidden, commands)
            self.assertIn(forbidden, guide)
        classifications = by_id["U06-classify-advanced-surfaces"]
        self.assertIn("Do not execute", classifications.instruction)
        self.assertIn("not run here", classifications.expected_result)
        for action in manifest.actions:
            for variant in action.variants:
                with self.subTest(action=action.id, variant=variant.id):
                    if variant.surface == "native-terminal" or variant.language == "codearbiter":
                        self.assertFalse(variant.command.startswith("!"))
        self.assertIn(f"Academy Preview {CURRENT_RELEASE.removeprefix('preview-')}", guide)
        self.assertIn("`ca-preview`", guide)
        self.assertIn("not `ca-preview` output", guide)
        self.assertIn("whether a secret scan ran", guide)
        self.assertNotIn("reports `docs` as the reviewer", guide)
        self.assertIn("No committed record preserves this advisory output", manifest_source)
        self.assertNotRegex(manifest_source, r"\bdocs(?:-reviewed| reviewer)\b")
        self.assertNotRegex(guide, r"\bdocs(?:-reviewed| reviewer)\b")
        self.assertIn("not run here", guide)
        self.assertIn("Check limit", guide)

    def test_published_lesson_copy_uses_the_installed_release_identity(self) -> None:
        """A public guide must not send a newcomer to an older installed Preview."""
        root = Path(__file__).parents[1]
        public = load_preview_manifest(root)
        expected = f"Preview {CURRENT_RELEASE.removeprefix('preview-')}"
        preview_name = re.compile(
            r"(?:Academy )?Preview \d+\.\d+|preview-\d+\.\d+"
        )

        for document_id in public.guided_labs:
            guide_path = next((root / "academy" / "tracks").glob(f"*/{document_id}.md"))
            for source_path in (
                root / "academy" / "actions" / f"{document_id}.json",
                guide_path,
            ):
                source = source_path.read_text(encoding="utf-8")
                matches = preview_name.findall(source)
                with self.subTest(document_id=document_id, source=source_path):
                    self.assertTrue(
                        all(
                            found.removeprefix("Academy ").replace(
                                "preview-", "Preview ", 1
                            )
                            == expected
                            for found in matches
                        ),
                        matches,
                    )


class PublicU02LessonActionTests(unittest.TestCase):
    def test_u02_observes_the_real_h05_guard_without_an_override(self) -> None:
        """Catches the public lesson teaching a fictional gate or a real audit-log mutation."""
        manifest = load_action_manifest(
            Path(__file__).parents[1], "U02-override-audit-metrics"
        )
        actions = {action.id: action for action in manifest.actions}

        self.assertEqual(
            tuple(action.id for action in manifest.actions),
            (
                "U02-read-boundary",
                "U02-prepare",
                "U02-inspect-baseline",
                "U02-attempt-guarded-restore",
                "U02-record-observation",
                "U02-review-observation-boundary",
                "U02-stage-observation",
                "U02-commit-observation",
                "U02-check",
                "U02-reset",
            ),
        )
        self.assertEqual(
            tuple(action.sequence for action in manifest.actions), tuple(range(1, 11))
        )

        native_actions = (
            "U02-prepare",
            "U02-stage-observation",
            "U02-check",
            "U02-reset",
        )
        for action_id in native_actions:
            with self.subTest(action=action_id):
                action = actions[action_id]
                self.assertEqual(
                    tuple(variant.surface for variant in action.variants),
                    ("native-terminal", "native-terminal", "native-terminal"),
                )
                self.assertFalse(
                    any(variant.command.startswith("!") for variant in action.variants)
                )

        boundary = actions["U02-read-boundary"]
        self.assertIn("cannot prove", boundary.evidence or "")
        self.assertIn("manual imitation", boundary.evidence or "")
        self.assertIn("numbered U02 attempt", actions["U02-prepare"].expected_result)
        self.assertIn("observation-note commit", actions["U02-check"].expected_result)
        self.assertIn("archives the failed U02 attempt", actions["U02-reset"].expected_result)

        guarded_restore = actions["U02-attempt-guarded-restore"]
        self.assertEqual(guarded_restore.actor, "learner")
        self.assertTrue(all(variant.surface == "harness" for variant in guarded_restore.variants))
        self.assertTrue(all(variant.command == "!git restore --source=HEAD -- .codearbiter/overrides.log" for variant in guarded_restore.variants))
        self.assertEqual(
            tuple((variant.operating_system, variant.host) for variant in guarded_restore.variants),
            (("all", "claude-code"), ("all", "codex"), ("all", "pi")),
        )
        self.assertIn("H-05", guarded_restore.expected_result)
        self.assertNotIn("override", guarded_restore.title.casefold())

        baseline_variants = actions["U02-inspect-baseline"].variants
        self.assertEqual(
            tuple((variant.operating_system, variant.command) for variant in baseline_variants if variant.host == "codex"),
            (
                ("windows", "!Get-FileHash .codearbiter\\overrides.log -Algorithm SHA256"),
                ("macos", "!shasum -a 256 .codearbiter/overrides.log"),
                ("linux", "!sha256sum .codearbiter/overrides.log"),
            ),
        )

        evidence = actions["U02-record-observation"]
        self.assertEqual((evidence.actor, evidence.surface), ("agent", None))
        self.assertIn("SHA-256", evidence.instruction)
        self.assertIn("event_line", evidence.instruction)
        self.assertIn("Do not stage, commit, or push", evidence.instruction)
        self.assertEqual(tuple(variant.host for variant in evidence.variants), ("claude-code", "codex", "pi"))
        self.assertTrue(all(variant.copy for variant in evidence.variants))
        self.assertTrue(all(".codearbiter/reports/academy/U02-observation.md" in variant.command for variant in evidence.variants))
        self.assertTrue(all("Do not stage, commit, push, or edit .codearbiter/overrides.log." in variant.command for variant in evidence.variants))
        self.assertTrue(all("# U02 audit-guard observation" in variant.command for variant in evidence.variants))
        self.assertTrue(all("event: H-05 guarded restore refusal" in variant.command for variant in evidence.variants))
        self.assertTrue(all("target: .codearbiter/overrides.log" in variant.command for variant in evidence.variants))
        self.assertTrue(all("baseline_sha256:" in variant.command for variant in evidence.variants))
        self.assertTrue(all("event_sha256:" in variant.command for variant in evidence.variants))
        self.assertTrue(all("event_line:" in variant.command for variant in evidence.variants))
        self.assertTrue(all("limitation: This record cannot prove the refusal chronology; manual imitation remains possible." in variant.command for variant in evidence.variants))
        self.assertTrue(all("UTF-8" in variant.command for variant in evidence.variants))

        review = actions["U02-review-observation-boundary"]
        self.assertEqual((review.actor, review.surface), ("learner", "browser"))
        self.assertIn("overrides.log", review.instruction)
        self.assertIn("U02-observation.md", review.instruction)
        self.assertIn("one-path", review.expected_result)
        self.assertIn("another path", review.recovery)
        stage = actions["U02-stage-observation"]
        self.assertIn("observation note", stage.instruction)
        self.assertIn("Exactly one path", stage.expected_result)
        self.assertTrue(all("U02-observation.md" in variant.command for variant in stage.variants))
        self.assertNotIn("$ca-override", "\n".join(variant.command for action in manifest.actions for variant in action.variants))


class U03LessonActionTests(unittest.TestCase):
    def test_u03_manifest_teaches_the_declared_runnable_local_release_contract(self) -> None:
        """Catches U03 publishing a fake remote release or an incomplete learner path."""
        manifest = load_action_manifest(
            Path(__file__).parents[1], "U03-refactor-chore-release"
        )
        actions = {action.id: action for action in manifest.actions}

        self.assertEqual(
            tuple(action.id for action in manifest.actions),
            (
                "U03-read-boundary",
                "U03-prepare",
                "U03-confirm-prepared",
                "U03-review-sealed-brief",
                "U03-run-refactor",
                "U03-inspect-refactor",
                "U03-review-refactor",
                "U03-stage-refactor",
                "U03-commit-refactor",
                "U03-dry-run-release",
                "U03-review-release-blocker",
                "U03-approve-refactor-footer",
                "U03-amend-refactor-message",
                "U03-verify-amended-refactor",
                "U03-run-chore",
                "U03-inspect-chore",
                "U03-review-chore",
                "U03-stage-chore",
                "U03-commit-chore",
                "U03-run-release",
                "U03-review-release",
                "U03-inspect-tag",
                "U03-check",
                "U03-reset",
            ),
        )
        self.assertEqual(
            tuple(action.sequence for action in manifest.actions), tuple(range(1, 25))
        )

        for action_id in (
            "U03-prepare",
            "U03-confirm-prepared",
            "U03-inspect-refactor",
            "U03-stage-refactor",
            "U03-inspect-chore",
            "U03-stage-chore",
            "U03-inspect-tag",
            "U03-check",
            "U03-reset",
        ):
            with self.subTest(action=action_id):
                action = actions[action_id]
                self.assertEqual(action.actor, "learner")
                self.assertEqual(
                    tuple(variant.surface for variant in action.variants),
                    ("native-terminal", "native-terminal", "native-terminal"),
                )
                self.assertFalse(
                    any(variant.command.startswith("!") for variant in action.variants)
                )

        for action_id, command in (
            ("U03-run-refactor", "refactor"),
            ("U03-commit-refactor", "commit"),
            ("U03-run-chore", "chore docs"),
            ("U03-commit-chore", "commit"),
            ("U03-run-release", "release academy-private-training"),
        ):
            with self.subTest(action=action_id):
                action = actions[action_id]
                self.assertEqual(action.actor, "agent")
                self.assertEqual(
                    tuple((variant.host, variant.command) for variant in action.variants),
                    (
                        ("claude-code", f"/ca:{command}"),
                        ("codex", f"$ca-{command}"),
                        ("pi", f"/ca-{command}"),
                        ("pi", f"/skill:ca-{command}"),
                    ),
                )
                self.assertTrue(
                    all(variant.language == "codearbiter" for variant in action.variants)
                )
                self.assertFalse(
                    any(variant.command.startswith("!") for variant in action.variants)
                )

        for action_id in (
            "U03-read-boundary",
            "U03-review-refactor",
            "U03-review-chore",
            "U03-review-release",
        ):
            with self.subTest(action=action_id):
                self.assertEqual(
                    (actions[action_id].actor, actions[action_id].surface),
                    ("learner", "active-harness"),
                )

        sealed_brief = actions["U03-review-sealed-brief"]
        self.assertEqual((sealed_brief.actor, sealed_brief.surface), ("learner", None))
        self.assertEqual(
            {variant.surface for variant in sealed_brief.variants},
            {"native-terminal", "harness"},
        )
        self.assertTrue(
            all(
                "training_scenarios/U03-refactor-chore-release.json" in variant.command
                for variant in sealed_brief.variants
            )
        )
        self.assertIn("refactor.scope", sealed_brief.instruction)
        self.assertIn("chore.approved_readme_fact", sealed_brief.instruction)
        self.assertTrue(
            any(
                variant.host == "codex" and variant.command.startswith("! ")
                for variant in sealed_brief.variants
            )
        )

        boundary = actions["U03-read-boundary"]
        self.assertIn("does not prove", boundary.evidence or "")
        for limitation in (
            "behavioral parity",
            "human approval",
            "CodeArbiter command execution",
            "tag push",
            "publication",
        ):
            with self.subTest(limitation=limitation):
                self.assertIn(limitation, boundary.evidence or "")

        for action in manifest.actions:
            with self.subTest(action=action.id):
                self.assertNotIn("future private", action.instruction.casefold())
                self.assertIn("Next safe step:", action.recovery)

        prepare = actions["U03-prepare"]
        self.assertIn("academy/U03-refactor-chore-release/1", prepare.expected_result)
        self.assertIn("sealed brief", prepare.expected_result)
        self.assertIn("academy-v0.0.1", actions["U03-run-release"].expected_result)
        self.assertIn("does not push", actions["U03-run-release"].expected_result)
        self.assertIn("passed", actions["U03-check"].expected_result)
        self.assertIn("archive", actions["U03-reset"].expected_result)

        self.assertIn("workshop_queue/store.py", actions["U03-stage-refactor"].instruction)
        self.assertIn("README.md", actions["U03-stage-chore"].instruction)
        ids = tuple(actions)
        self.assertLess(ids.index("U03-dry-run-release"), ids.index("U03-run-chore"))
        self.assertLess(ids.index("U03-amend-refactor-message"), ids.index("U03-run-chore"))
        self.assertEqual(actions["U03-commit-refactor"].variants[1].command, "$ca-commit")
        self.assertIn("unpublished HEAD", actions["U03-amend-refactor-message"].instruction)
        self.assertTrue(
            all(
                "git merge-base --is-ancestor HEAD origin/main" in variant.command
                for variant in actions["U03-amend-refactor-message"].variants
            )
        )
        dry_run = actions["U03-dry-run-release"]
        self.assertIn("already has the approved footer", dry_run.expected_result)
        self.assertIn("skip the amend", actions["U03-review-release-blocker"].recovery)
        tag = actions["U03-inspect-tag"]
        self.assertIn("academy-v0.0.1", tag.instruction)
        self.assertIn("generated 0.0.1 changelog section", tag.instruction)
        self.assertIn("matching Released-at date", tag.expected_result)
        self.assertIn("does not point at HEAD", tag.recovery)
        self.assertTrue(
            all("git cat-file -t academy-v0.0.1" in variant.command for variant in tag.variants)
        )
        self.assertTrue(
            all("git show --no-patch --format=%B academy-v0.0.1" in variant.command for variant in tag.variants)
        )




if __name__ == "__main__":
    unittest.main()
