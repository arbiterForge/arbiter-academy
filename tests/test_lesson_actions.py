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
F03_ACTION_IDS = (
    "F03-prepare",
    "F03-read-target-task",
    "F03-start-task",
    "F03-inspect-started-task",
    "F03-complete-task",
    "F03-inspect-final-diff",
    "F03-stage-board",
    "F03-review-commit-boundary",
    "F03-run-commit-gate",
    "F03-confirm-clean",
    "F03-check",
    "F03-reset-retry",
    "F03-return-base",
)
P01_DOCUMENT_ID = "P01-feature-through-plan"
P01_ACTION_IDS = (
    "P01-prepare",
    "P01-draft-spec",
    "P01-read-spec",
    "P01-solo-review",
    "P01-discussion-review",
    "P01-proceed",
    "P01-check",
    "P01-reset-retry",
)
P04_DOCUMENT_ID = "P04-review-a-dependency"
P04_ACTION_IDS = (
    "P04-prepare", "P04-read-boundary", "P04-read-candidate-set", "P04-inspect-project-boundary",
    "P04-inspect-wheel-metadata", "P04-verify-wheel-hashes", "P04-read-licenses", "P04-assess-provenance",
    "P04-compare-stdlib", "P04-draft-review", "P04-review-draft", "P04-select-reject",
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
P03_ACTION_DOCUMENT_ID = "P03-adr-decision-log"
P03_ACTION_IDS = (
    "P03-read-boundary",
    "P03-identity-boundary",
    "P03-prepare",
    "P03-read-decision-context",
    "P03-request-analysis",
    "P03-make-choice",
    "P03-author-adr",
    "P03-inspect-proposed-adr",
    "P03-accept-proposed-adr",
    "P03-commit-accepted-decision",
    "P03-inspect-committed-evidence",
    "P03-check",
    "P03-reset",
)
P03_CHOICES = (
    "Use stable text for Workshop Queue summaries.",
    "Use structured JSON for Workshop Queue summaries.",
)
P08_DOCUMENT_ID = "P08-repository-hygiene"
P08_ACTION_IDS = (
    "P08-prepare",
    "P08-inventory-native",
    "P08-inventory-harness-shell",
    "P08-run-standup",
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
    "P06-review-handoff-boundary",
    "P06-commit-handoff",
    "P06-check",
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


class LessonActionTests(unittest.TestCase):
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
        self.assertEqual(tuple(action.sequence for action in manifest.actions), tuple(range(1, 14)))
        for action in manifest.actions:
            with self.subTest(action=action.id):
                self.assertTrue(action.instruction)
                self.assertTrue(action.expected_result)
                self.assertTrue(action.recovery)
                self.assertIsNotNone(action.evidence)

        actions = {action.id: action for action in manifest.actions}
        self.assertEqual(actions["P08-run-standup"].actor, "agent")
        self.assertEqual(actions["P08-request-report-draft"].actor, "learner")
        self.assertEqual(actions["P08-review-report"].surface, "active-harness")
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

    def test_checked_in_p04_manifest_teaches_a_reviewed_no_install_rejection_path(self) -> None:
        """Catches P04 returning to vague dependency advice or an install-shaped command path."""
        manifest = load_action_manifest(Path(__file__).parents[1], P04_DOCUMENT_ID)
        self.assertEqual(tuple(action.id for action in manifest.actions), P04_ACTION_IDS)
        by_id = {action.id: action for action in manifest.actions}
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
        self.assertEqual(
            tuple((variant.host, variant.language, variant.command) for variant in draft.variants),
            (("claude-code", "codearbiter", '/ca:add-dep "python-dateutil==2.9.0.post0 for finite legacy date formats"'),
             ("codex", "codearbiter", '$ca-add-dep "python-dateutil==2.9.0.post0 for finite legacy date formats"'),
             ("pi", "codearbiter", '/ca-add-dep "python-dateutil==2.9.0.post0 for finite legacy date formats"'),
             ("pi", "codearbiter", '/skill:ca-add-dep "python-dateutil==2.9.0.post0 for finite legacy date formats"')),
        )
        self.assertFalse(any(variant.command.startswith("!") for variant in draft.variants))
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
        for action_id in ("P04-review-draft", "P04-select-reject"):
            action = by_id[action_id]
            with self.subTest(action=action_id):
                self.assertEqual((action.actor, action.surface, action.variants), ("learner", "active-harness", ()))
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
                self.assertTrue(all("preview-0.6" in variant.command for variant in action.variants))
                self.assertFalse(any(variant.command.startswith("!") for variant in action.variants))

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
        marker = "Insert this exact method in WorkshopQueueCliTests:\n"
        terminator = "\nRun only the exact focused test"

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

    def test_p05_installed_academy_actions_use_preview_0_6_locations(self) -> None:
        """Catches Prepare, Check, or Reset routing learners to the obsolete install."""
        manifest = load_action_manifest(Path(__file__).parents[1], P05_DOCUMENT_ID)
        by_id = {action.id: action for action in manifest.actions}
        expected_locations = {
            "windows": r"$env:LOCALAPPDATA\ArbiterAcademy\preview-0.6\Scripts\arbiter-academy.exe",
            "macos": "${XDG_DATA_HOME:-$HOME/.local/share}/arbiter-academy/preview-0.6/bin/arbiter-academy",
            "linux": "${XDG_DATA_HOME:-$HOME/.local/share}/arbiter-academy/preview-0.6/bin/arbiter-academy",
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
    def test_private_p03_manifest_has_one_ordered_action_for_each_lifecycle_boundary(self) -> None:
        """Catches P03 collapsing learner choice, draft review, or acceptance into an agent step."""
        root = Path(__file__).parents[1]
        self.assertTrue(
            (root / "academy/actions/P03-adr-decision-log.json").is_file(),
            "P03 must expose its one explicitly named action manifest",
        )
        manifest = load_action_manifest(root, P03_ACTION_DOCUMENT_ID)

        self.assertEqual(tuple(action.id for action in manifest.actions), P03_ACTION_IDS)
        self.assertTrue(all(action.expected_result and action.recovery for action in manifest.actions))

    def test_private_p03_never_offers_unpublished_prepare_check_or_reset_commands(self) -> None:
        """Catches a private lesson inventing an install path for Academy operations."""
        root = Path(__file__).parents[1]
        manifest = load_action_manifest(root, P03_ACTION_DOCUMENT_ID)
        by_id = {action.id: action for action in manifest.actions}

        for action_id in ("P03-prepare", "P03-check", "P03-reset"):
            action = by_id[action_id]
            with self.subTest(action=action_id):
                self.assertEqual((action.actor, action.surface), ("academy", "academy-console"))
                self.assertEqual(action.variants, ())
                contract = " ".join(
                    (
                        action.instruction,
                        action.expected_result,
                        action.recovery,
                        action.evidence or "",
                    )
                )
                self.assertIn("Preview 0.6", contract)
                self.assertIn("not published", contract)
                self.assertIn("future published release", contract)
                self.assertNotIn("preview-0.5", contract.casefold())

    def test_private_p03_gives_the_learner_two_copyable_exact_choice_actions(self) -> None:
        """Catches an agent retaining authority to select or rewrite the architecture choice."""
        manifest = load_action_manifest(Path(__file__).parents[1], P03_ACTION_DOCUMENT_ID)
        by_id = {action.id: action for action in manifest.actions}

        self.assertIn("P03-make-choice", by_id)
        choice = by_id["P03-make-choice"]
        self.assertEqual(choice.actor, "learner")
        self.assertIsNone(choice.surface)
        self.assertEqual({variant.host for variant in choice.variants}, {"claude-code", "codex", "pi"})
        for host in ("claude-code", "codex", "pi"):
            with self.subTest(host=host):
                host_variants = tuple(
                    variant for variant in choice.variants if variant.host == host
                )
                self.assertEqual(tuple(variant.command for variant in host_variants), P03_CHOICES)
                self.assertTrue(
                    all(
                        variant.surface == "harness"
                        and variant.language == "text"
                        and variant.copy
                        for variant in host_variants
                    )
                )
        self.assertIn("learner-owned", choice.evidence or "")
        self.assertIn("does not choose", choice.expected_result)

    def test_private_p03_local_context_actions_reference_the_real_adr_0003_path(self) -> None:
        """Catches source-only authoring copy pointing at a nonexistent governance artifact."""
        root = Path(__file__).parents[1]
        adr_path = ".codearbiter/decisions/0003-local-verifier-trust-boundary.md"
        self.assertTrue((root / adr_path).is_file())
        manifest = load_action_manifest(root, P03_ACTION_DOCUMENT_ID)
        by_id = {action.id: action for action in manifest.actions}

        for action_id in ("P03-read-decision-context", "P03-request-analysis"):
            with self.subTest(action=action_id):
                commands = tuple(variant.command for variant in by_id[action_id].variants)
                self.assertTrue(all(adr_path in command.replace("\\", "/") for command in commands))
                self.assertTrue(
                    all(".codearbiter/decisions/decision-log.md" in command.replace("\\", "/") for command in commands)
                )
                self.assertFalse(any("0003-academy-verifier-trust.md" in command for command in commands))

    def test_private_p03_uses_proposed_review_accept_then_commit_lifecycle(self) -> None:
        """Catches generic ca-adr being presented as accepted Check-compatible output."""
        manifest = load_action_manifest(Path(__file__).parents[1], P03_ACTION_DOCUMENT_ID)
        by_id = {action.id: action for action in manifest.actions}

        for action_id, command in (
            ("P03-author-adr", "adr"),
            ("P03-commit-accepted-decision", "commit"),
        ):
            action = by_id[action_id]
            with self.subTest(action=action_id):
                self.assertEqual(
                    tuple((variant.host, variant.command) for variant in action.variants),
                    (
                        ("claude-code", f'/ca:{command}' + (' "Choose the Workshop Queue summary-format boundary"' if command == "adr" else "")),
                        ("codex", f'$ca-{command}' + (' "Choose the Workshop Queue summary-format boundary"' if command == "adr" else "")),
                        ("pi", f'/ca-{command}' + (' "Choose the Workshop Queue summary-format boundary"' if command == "adr" else "")),
                        ("pi", f'/skill:ca-{command}' + (' "Choose the Workshop Queue summary-format boundary"' if command == "adr" else "")),
                    ),
                )
                self.assertTrue(all(variant.language == "codearbiter" for variant in action.variants))
                self.assertFalse(any(variant.command.startswith("!") for variant in action.variants))

        author = by_id["P03-author-adr"]
        self.assertEqual(author.actor, "agent")
        self.assertIn("proposed", author.expected_result.casefold())
        self.assertIn("does not by itself", (author.evidence or "").casefold())

        inspection = by_id["P03-inspect-proposed-adr"]
        self.assertEqual(inspection.actor, "learner")
        self.assertEqual(
            tuple(variant.surface for variant in inspection.variants),
            ("native-terminal", "native-terminal", "native-terminal"),
        )
        inspection_contract = " ".join(
            (inspection.instruction, inspection.expected_result, inspection.evidence or "")
        )
        for required in (
            ".codearbiter/decisions/0004-academy-lab.md",
            "status: proposed",
            "date:",
            "title: Choose the Workshop Queue summary-format boundary",
            "decided-by:",
            "supersedes: none",
            "governs: workshop_queue/cli.py",
            "# ADR-0004 — Choose the Workshop Queue summary-format boundary",
            "Status, Context, Decision, Alternatives considered, Consequences, Risks",
            "## DECISION-0004 — ADR-0004 — Choose the Workshop Queue summary-format boundary",
            "**Date:**, **Status:** proposed, **Supersedes:** none, **Decided by:**, **Decision category:** architecture, **Artifact-section-hash:** n/a",
            "Variance summary, Decision, SMARTS rationale, Implementation implication",
            "Status type: open-decision-closure",
        ):
            with self.subTest(required=required):
                self.assertIn(required, inspection_contract)

        acceptance = by_id["P03-accept-proposed-adr"]
        self.assertEqual(acceptance.actor, "learner")
        self.assertEqual(
            tuple((variant.surface, variant.host, variant.language, variant.copy) for variant in acceptance.variants),
            (
                ("harness", "claude-code", "text", True),
                ("harness", "codex", "text", True),
                ("harness", "pi", "text", True),
            ),
        )
        self.assertTrue(
            all("I accept" in variant.command and "Do not commit yet" in variant.command for variant in acceptance.variants)
        )
        self.assertIn("explicit learner direction", acceptance.evidence or "")
        self.assertIn("status: proposed to status: accepted", acceptance.expected_result)
        self.assertIn("Proposed to Accepted", acceptance.expected_result)
        self.assertIn("**Status:** proposed to **Status:** accepted", acceptance.expected_result)

    def test_checked_in_p06_manifest_names_every_actor_surface_and_recovery_boundary(self) -> None:
        """Catches private P06 guidance asking learners to infer execution surfaces."""
        manifest = load_action_manifest(Path(__file__).parents[1], P06_DOCUMENT_ID)
        self.assertEqual(tuple(action.id for action in manifest.actions), P06_ACTION_IDS)
        self.assertTrue(all(action.expected_result for action in manifest.actions))
        self.assertTrue(all(action.recovery for action in manifest.actions))
        by_id = {action.id: action for action in manifest.actions}
        self.assertEqual(by_id["P06-run-context-audit"].actor, "agent")
        self.assertEqual(by_id["P06-apply-correction"].actor, "agent")
        self.assertEqual(by_id["P06-select-rescout"].surface, "active-harness")
        self.assertEqual(by_id["P06-review-correction-boundary"].surface, "active-harness")
        self.assertEqual(by_id["P06-review-handoff-boundary"].surface, "active-harness")

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

        for action_id in ("P06-prepare", "P06-check", "P06-reset-retry"):
            self.assertEqual(
                {variant.operating_system for variant in by_id[action_id].variants},
                {"windows", "macos", "linux"},
            )

    def test_all_action_command_variants_bind_to_preview_0_6(self) -> None:
        """Catches any copied Academy command retaining a stale Preview 0.5 path."""
        root = Path(__file__).parents[1]
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
                if "preview-" in commands:
                    expected_preview = "preview-0.7" if document_id == F03_DOCUMENT_ID else "preview-0.6"
                    self.assertIn(expected_preview, commands)
                    if document_id == F03_DOCUMENT_ID:
                        self.assertNotIn("preview-0.6", commands)

    def test_checked_in_f03_manifest_guides_the_exact_board_lifecycle(self) -> None:
        """Catches F03 losing its exact board-only route or Preview 0.7 learner commands."""
        manifest = load_action_manifest(Path(__file__).parents[1], F03_DOCUMENT_ID)

        self.assertEqual(tuple(action.id for action in manifest.actions), F03_ACTION_IDS)
        self.assertTrue(all(action.expected_result and action.recovery for action in manifest.actions))
        by_id = {action.id: action for action in manifest.actions}

        for action_id in ("F03-prepare", "F03-check", "F03-reset-retry"):
            action = by_id[action_id]
            with self.subTest(action=action_id):
                self.assertEqual(
                    tuple((variant.surface, variant.operating_system, variant.host, variant.copy) for variant in action.variants),
                    (("native-terminal", "windows", "none", True), ("native-terminal", "macos", "none", True), ("native-terminal", "linux", "none", True)),
                )
                self.assertTrue(all("preview-0.7" in variant.command for variant in action.variants))
                self.assertFalse(any(variant.command.startswith("!") for variant in action.variants))

        for action_id, command in (
            ("F03-start-task", "task start academy.feature.0001"),
            ("F03-complete-task", "task done academy.feature.0001"),
            ("F03-run-commit-gate", "commit"),
        ):
            action = by_id[action_id]
            with self.subTest(action=action_id):
                self.assertEqual(action.actor, "agent")
                self.assertEqual(
                    tuple((variant.host, variant.command) for variant in action.variants),
                    (
                        ("claude-code", "/ca:" + command),
                        ("codex", "$ca-" + command),
                        ("pi", "/ca-" + command),
                        ("pi", "/skill:ca-" + command),
                    ),
                )
                self.assertFalse(any(variant.command.startswith("!") for variant in action.variants))

        check_copy = "\n".join(
            part
            for part in (
                by_id["F03-check"].instruction,
                by_id["F03-check"].expected_result,
                by_id["F03-check"].recovery,
                by_id["F03-check"].evidence or "",
            )
        )
        self.assertIn("cannot prove the agent command ran", check_copy)
        self.assertIn("cannot prove the learner observed the transient [~] state", check_copy)
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
        self.assertIn(".codearbiter/open-tasks.md.lock", clean_copy)

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

    def test_private_p02_manifest_binds_the_offline_receipt_workflow(self) -> None:
        """Catches an action rewrite that loses the local-only recorder boundary."""
        manifest = load_action_manifest(Path(__file__).parents[1], P02_DOCUMENT_ID)
        self.assertEqual(tuple(action.id for action in manifest.actions), P02_ACTION_IDS)
        self.assertTrue(all(action.expected_result and action.recovery for action in manifest.actions))
        by_id = {action.id: action for action in manifest.actions}
        boundary = by_id["P02-read-boundary"]
        self.assertIn("macOS or Linux", boundary.instruction)
        self.assertIn("native Windows", boundary.expected_result)
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
            self.assertTrue(all("preview-0.6" in command for command in commands))
            self.assertTrue(all("$academy" in command for command in commands))
            self.assertTrue(all(command.splitlines()[0].startswith("academy=") or command.splitlines()[0].startswith("$academy =") for command in commands))
        recorder = by_id["P02-record-receipt"]
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


if __name__ == "__main__":
    unittest.main()
