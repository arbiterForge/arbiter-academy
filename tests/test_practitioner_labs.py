from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from academy_engine.cli import main
from academy_engine import curriculum
from academy_engine.curriculum import CurriculumError, load_track, verify_track
from academy_engine.lesson_actions import load_action_manifest
from academy_engine.preview import load_preview_manifest, validate_preview_manifest
from academy_engine.scenario import PreparedLab


SOURCE = Path(__file__).resolve().parents[1]
PRACTITIONER = (
    "P01-feature-through-plan",
    "P02-commit-review-pr",
    "P03-record-an-adr",
    "P04-review-a-dependency",
    "P05-checkpoint-remediation",
    "P06-context-drift-recovery",
    "P07-threat-model",
    "P08-repository-hygiene",
)
POST_P02_PRACTITIONER = PRACTITIONER[2:]
EXPECTED_HOST_ACTIONS = {
    PRACTITIONER[0]: ("feature",),
    # P02's action manifest owns its later commit gates. The compact track
    # metadata presents the first host entry point only.
    PRACTITIONER[1]: ("review",),
    PRACTITIONER[2]: ("adr",),
    PRACTITIONER[3]: ("btw",),
    PRACTITIONER[4]: ("checkpoint",),
    PRACTITIONER[5]: ("context-check",),
    PRACTITIONER[6]: ("threat-model",),
    PRACTITIONER[7]: ("standup",),
}


class PractitionerCurriculumTests(unittest.TestCase):
    def test_p08_uses_the_guided_lesson_contract_without_expanding_cleanup_authority(self) -> None:
        """Catches a P08 rewrite that hides a runnable surface or treats Check as cleanup approval."""
        guide = (SOURCE / "academy/tracks/practitioner/P08-repository-hygiene.md").read_text(encoding="utf-8")
        manifest = load_action_manifest(SOURCE, "P08-repository-hygiene")
        normalized_guide = " ".join(guide.split())
        headings = tuple(line[3:] for line in guide.splitlines() if line.startswith("## "))
        action_ids = tuple(action.id for action in manifest.actions)

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
        for action_id in action_ids:
            with self.subTest(action=action_id):
                self.assertEqual(guide.count("{{action:" + action_id + "}}"), 1)
        self.assertIn("The website is the primary lesson surface.", guide)
        self.assertIn("Academy CLI is limited to Prepare, Check, and Reset.", guide)
        self.assertIn("Check does not prove that the agent ran standup", guide)
        self.assertIn(
            "Check cannot prove personal understanding, agent invocation, or human review.",
            guide,
        )
        self.assertIn("A passing Check does not make a deletion safe", normalized_guide)
        self.assertIn("The agent drafts the report; you review it", normalized_guide)
        self.assertIn("Next safe course step: start U01, Autonomous sprint.", guide)
        self.assertNotIn("remains a source exercise", guide)
        self.assertLess(guide.index("{{action:P08-review-report}}"), guide.index("{{action:P08-stage-report}}"))
        self.assertLess(guide.index("{{action:P08-stage-report}}"), guide.index("{{action:P08-review-commit-boundary}}"))
        for destructive in ("git worktree remove", "git branch -D", "git prune", "git gc", "git reset --hard"):
            with self.subTest(destructive=destructive):
                self.assertNotIn(destructive, guide)

    def test_loader_rejects_repository_local_post_p02_practitioner_scenarios(self) -> None:
        """Preserved P02 records make a repository-local later transition noncanonical."""
        for lab_id in POST_P02_PRACTITIONER:
            with self.subTest(lab=lab_id), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                shutil.copytree(SOURCE / "academy", root / "academy")
                path = root / f"academy/tracks/practitioner/{lab_id}.md"
                text = path.read_text(encoding="utf-8")
                installed = (
                    f"scenario_command: {{{{action:{lab_id.partition('-')[0]}-prepare}}}}"
                    if lab_id == "P06-context-drift-recovery"
                    else (
                        "scenario_command: arbiter-academy --repository "
                        f"<learner-repository> prepare {lab_id}"
                    )
                )
                local = f"scenario_command: python scripts/academy.py prepare {lab_id}"
                self.assertIn(installed, text)
                path.write_text(text.replace(installed, local), encoding="utf-8")

                with self.assertRaisesRegex(
                    CurriculumError,
                    rf"{re.escape(lab_id)} scenario command is noncanonical",
                ):
                    load_track(root, "practitioner")

    def test_post_p02_practitioner_guides_expose_restart_safe_installed_commands(self) -> None:
        """The copyable path must retain external authority after P02 records are preserved."""
        try:
            track = load_track(SOURCE, "practitioner")
        except CurriculumError as error:
            self.fail(f"post-P02 source commands are not loadable: {error}")

        assignment = "$learnerRepository = (Resolve-Path -LiteralPath '.').Path"
        for lab in track.labs[2:]:
            with self.subTest(lab=lab.id):
                expected_prepare = (
                    "{{action:P06-prepare}}"
                    if lab.id == "P06-context-drift-recovery"
                    else "arbiter-academy --repository <learner-repository> prepare " + lab.id
                )
                self.assertEqual(lab.scenario_command, expected_prepare)
                if lab.id == "P05-checkpoint-remediation":
                    manifest = load_action_manifest(SOURCE, lab.id)
                    actions = {action.id: action for action in manifest.actions}
                    for action_id, operation in (
                        ("P05-prepare", "prepare"),
                        ("P05-check", "check"),
                        ("P05-reset-retry", "reset"),
                    ):
                        action = actions[action_id]
                        self.assertEqual(action.actor, "learner")
                        self.assertEqual(
                            {variant.operating_system for variant in action.variants},
                            {"windows", "macos", "linux"},
                        )
                        for variant in action.variants:
                            with self.subTest(action=action_id, variant=variant.id):
                                self.assertEqual(variant.surface, "native-terminal")
                                self.assertFalse(variant.command.startswith("!"))
                                self.assertIn(f"{operation} {lab.id}", variant.command)
                                self.assertNotIn("python scripts/academy.py", variant.command)
                    continue
                guide = (
                    SOURCE / f"academy/tracks/practitioner/{lab.id}.md"
                ).read_text(encoding="utf-8")
                if lab.id == "P08-repository-hygiene":
                    actions = {action.id: action for action in load_action_manifest(SOURCE, lab.id).actions}
                    self.assertEqual(
                        tuple(actions),
                        (
                            "P08-prepare", "P08-inventory-native", "P08-inventory-harness-shell",
                            "P08-run-standup", "P08-inventory-after-standup", "P08-request-report-draft", "P08-review-report",
                            "P08-stage-report", "P08-review-commit-boundary", "P08-run-commit-gate",
                            "P08-confirm-clean", "P08-check", "P08-return-base", "P08-reset-retry",
                        ),
                    )
                    for action_id, command in (
                        ("P08-prepare", "prepare P08-repository-hygiene"),
                        ("P08-check", "check P08-repository-hygiene"),
                        ("P08-reset-retry", "reset P08-repository-hygiene"),
                    ):
                        with self.subTest(action=action_id):
                            self.assertTrue(
                                any(
                                    "$academy" in variant.command
                                    and command in variant.command
                                    for variant in actions[action_id].variants
                                )
                            )
                    continue
                if lab.id == "P07-threat-model":
                    manifest = load_action_manifest(SOURCE, lab.id)
                    actions = {action.id: action for action in manifest.actions}
                    self.assertNotIn("```", guide)
                    for action_id, operation in (
                        ("P07-prepare", "prepare"),
                        ("P07-check", "check"),
                        ("P07-reset", "reset"),
                    ):
                        with self.subTest(action=action_id):
                            variants = actions[action_id].variants
                            self.assertEqual(
                                tuple(variant.operating_system for variant in variants),
                                ("windows", "macos", "linux"),
                            )
                            self.assertTrue(all(variant.surface == "native-terminal" for variant in variants))
                            self.assertTrue(all(variant.host == "none" for variant in variants))
                            self.assertTrue(all(variant.copy for variant in variants))
                            self.assertTrue(
                                all(
                                    load_preview_manifest(SOURCE).release in variant.command
                                    and f"{operation} {lab.id}" in variant.command
                                    and "!" not in variant.command
                                    for variant in variants
                                )
                            )
                    continue
                if lab.id == "P03-record-an-adr":
                    manifest = load_action_manifest(SOURCE, "P03-record-an-adr")
                    actions = {action.id: action for action in manifest.actions}
                    release = load_preview_manifest(SOURCE)
                    self.assertNotIn("```", guide)
                    self.assertEqual(release.release, "preview-0.24")
                    self.assertIn(lab.id, release.runnable_labs)
                    self.assertIn(lab.id, release.guided_labs)
                    for action_id in ("P03-prepare", "P03-check", "P03-reset"):
                        action = actions[action_id]
                        with self.subTest(action=action_id):
                            self.assertTrue(action.variants)
                            self.assertTrue(all(variant.copy for variant in action.variants))
                    p03_copy = guide + json.dumps(
                        json.loads((SOURCE / "academy/actions/P03-record-an-adr.json").read_text(encoding="utf-8"))
                    )
                    self.assertIn(release.release.casefold(), p03_copy.casefold())
                    self.assertNotIn("preview-0.5", p03_copy.casefold())
                    continue
                action_path = SOURCE / f"academy/actions/{lab.id}.json"
                if action_path.is_file():
                    manifest = load_action_manifest(SOURCE, lab.id)
                    actions = {action.id: action for action in manifest.actions}
                    for operation in ("prepare", "check", "reset-retry"):
                        with self.subTest(lab=lab.id, operation=operation):
                            action = actions[f"{lab.id.partition('-')[0]}-{operation}"]
                            self.assertTrue(
                            all(
                                load_preview_manifest(SOURCE).release in variant.command
                                for variant in action.variants
                            )
                            )
                    self.assertNotRegex(guide, r"(?m)^```(?:powershell|sh|text|bash|console)\s*$")
                    continue
                prepare_block = re.search(
                    rf"(?ms)^```powershell\n(?P<body>.*?prepare {re.escape(lab.id)}.*?)\n```$",
                    guide,
                )
                self.assertIsNotNone(prepare_block)
                self.assertEqual(
                    tuple(prepare_block.group("body").splitlines())[:2],
                    (
                        assignment,
                        f"arbiter-academy --repository $learnerRepository prepare {lab.id}",
                    ),
                )
                self.assertIn(assignment, lab.success_evidence)
                self.assertIn(
                    f"arbiter-academy --repository $learnerRepository check {lab.id}",
                    lab.success_evidence,
                )
                self.assertIn(assignment, lab.recovery)
                self.assertIn(
                    f"arbiter-academy --repository $learnerRepository reset {lab.id}",
                    lab.recovery,
                )
                self.assertNotIn("python scripts/academy.py reset", lab.recovery)

    def test_post_p02_transitions_are_available_only_after_their_guided_rewrites_are_accepted(self) -> None:
        """Every promoted Practitioner transition must use installed verifier authority."""
        try:
            track = load_track(SOURCE, "practitioner")
        except CurriculumError as error:
            self.fail(f"post-P02 source commands are not loadable: {error}")

        manifest = load_preview_manifest(SOURCE)
        guided = set(manifest.guided_labs)
        self.assertEqual(
            tuple(lab.id for lab in track.labs[2:] if lab.id in guided),
            POST_P02_PRACTITIONER,
        )
        self.assertEqual(
            tuple(lab.id for lab in track.labs[2:] if lab.id not in guided),
            (),
        )

        for lab in track.labs[2:]:
            result = PreparedLab(
                lab.id,
                1,
                f"academy/{lab.id}/1",
                "a" * 40,
                "b" * 40,
            )
            for command, target in (("prepare", "prepare_lab"), ("reset", "reset_lab")):
                output = StringIO()
                with self.subTest(lab=lab.id, command=command), patch(
                    "academy_engine.cli.repository_root", return_value=SOURCE
                ), patch(
                    "academy_engine.cli.validate_repository_git_config"
                ) as validated, patch(
                    "academy_engine.cli.ensure_authoritative_verifier"
                ) as authoritative, patch(
                    f"academy_engine.cli.{target}", return_value=result
                ) as transitioned, redirect_stdout(output), redirect_stderr(output):
                    exit_code = main(
                        [
                            "--repository",
                            str(SOURCE),
                            command,
                            lab.id,
                        ]
                    )

                self.assertIn(lab.id, guided)
                self.assertEqual(exit_code, 0)
                validated.assert_called_once_with(SOURCE)
                authoritative.assert_called_once_with(SOURCE)
                transitioned.assert_called_once_with(
                    SOURCE,
                    lab.id,
                    installed_authority=True,
                )

    def test_published_lessons_do_not_direct_progression_to_unavailable_labs(self) -> None:
        manifest = load_preview_manifest(SOURCE)
        published = set(manifest.available_labs)
        tracks = (
            load_track(SOURCE, "foundations"),
            load_track(SOURCE, "practitioner"),
        )

        for track in tracks:
            for lab in track.labs:
                if lab.id not in published or lab.next_lab in published:
                    continue
                guide_path = SOURCE / f"academy/tracks/{track.id}/{lab.id}.md"
                guide = guide_path.read_text(encoding="utf-8")
                current_code = lab.id.partition("-")[0]
                next_code = lab.next_lab.partition("-")[0]
                with self.subTest(lab=lab.id, next_lab=lab.next_lab):
                    self.assertRegex(
                        guide,
                        r"guided Academy\s+lesson is published",
                    )
                    self.assertNotIn(f"Continue to {next_code} only after {current_code} passes", guide)

    def test_promoted_practitioner_guides_describe_their_now_public_next_lessons(self) -> None:
        """Catches public lesson prose retaining a former private-release boundary."""
        p01 = (SOURCE / "academy/tracks/practitioner/P01-feature-through-plan.md").read_text(
            encoding="utf-8"
        )
        p06 = (SOURCE / "academy/tracks/practitioner/P06-context-drift-recovery.md").read_text(
            encoding="utf-8"
        )

        self.assertIn("P02 is public, guided, and runnable in this preview", p01)
        self.assertNotIn("P02 is unavailable", p01)
        self.assertIn("P07 is public, guided, and runnable in this preview", p06)
        self.assertNotIn("P07 appears on the course home only after", p06)

    def test_track_loader_exposes_the_exact_progression_and_action_contract(self) -> None:
        """Catches a missing/reordered lab or a guide wired to the wrong governed surface."""
        track = load_track(SOURCE, "practitioner")

        self.assertEqual(tuple(lab.id for lab in track.labs), PRACTITIONER)
        self.assertEqual(
            tuple(lab.prerequisites for lab in track.labs),
            (("F04-fix-with-evidence",),)
            + tuple((PRACTITIONER[index - 1],) for index in range(1, 8)),
        )
        self.assertEqual(
            track.labs[1].scenario_command,
            "arbiter-academy --repository <learner-repository> prepare P02-commit-review-pr",
        )
        for lab in track.labs:
            with self.subTest(lab=lab.id):
                self.assertTrue(lab.outcome)
                self.assertGreater(lab.estimated_minutes, 0)
                self.assertEqual(len(lab.hints), 3)
                self.assertTrue(all(hint.strip() for hint in lab.hints))
                self.assertEqual(set(lab.host_commands), {"claude-code", "codex", "pi"})
                for action in EXPECTED_HOST_ACTIONS[lab.id]:
                    self.assertIn(f"/ca:{action}", lab.host_commands["claude-code"])
                    self.assertIn(f"$ca-{action}", lab.host_commands["codex"])
                    self.assertIn(f"/ca-{action}", lab.host_commands["pi"])
                expected_check = (
                    "{{action:P06-check}}"
                    if lab.id == "P06-context-drift-recovery"
                    else f"arbiter-academy --repository <learner-repository> check {lab.id}"
                )
                self.assertEqual(lab.checkpoint_command, expected_check)
                self.assertTrue(lab.success_evidence)
                self.assertIn("reset", lab.recovery.casefold())

        self.assertIn("{{action:P02-reset}}", track.labs[1].recovery)
        self.assertNotIn(
            "arbiter-academy --repository $learnerRepository reset P02-commit-review-pr",
            track.labs[1].recovery,
        )
        self.assertNotIn(
            "arbiter-academy --repository <learner-repository> reset P02-commit-review-pr",
            track.labs[1].recovery,
        )
        self.assertNotIn("scripts/academy.py reset", track.labs[1].recovery)

    def test_p01_exposes_exact_feature_commands_before_the_separate_proceed_instruction(self) -> None:
        """Catches P01 beginning work without the host-native feature command."""
        p01 = load_track(SOURCE, "practitioner").labs[0]

        request = '"Show unresolved tickets in the Workshop Queue summary"'
        self.assertEqual(
            p01.host_commands,
            {
                "claude-code": f"/ca:feature {request}",
                "codex": f"$ca-feature {request}",
                "pi": f"/ca-feature {request}\n/skill:ca-feature {request}",
            },
        )

    def test_p01_separates_tdd_instruction_from_one_commit_checkpoint_proof(self) -> None:
        """Catches guide copy claiming the non-executing P01 verifier proves repair history."""
        guide = (
            SOURCE / "academy/tracks/practitioner/P01-feature-through-plan.md"
        ).read_text(encoding="utf-8")

        self.assertIn("Add and run a focused summary test before touching production code.", guide)
        self.assertIn("one final green commit", guide)
        self.assertIn("does not prove that you ran the test before production code", guide)
        self.assertNotIn("Immutable Git history places", guide)
        self.assertNotIn("a same-commit test/fix", guide)
        self.assertNotIn("manufacture the required history", guide)

    def test_p01_is_an_action_backed_rehearsal_with_honest_review_boundaries(self) -> None:
        """Catches P01 asking a learner to infer command surfaces or fabricate approval evidence."""
        guide_path = SOURCE / "academy/tracks/practitioner/P01-feature-through-plan.md"
        guide = guide_path.read_text(encoding="utf-8")
        manifest = load_action_manifest(SOURCE, "P01-feature-through-plan")

        expected_headings = (
            "## Know before you begin",
            "## What you will prove",
            "## Prepare safely",
            "## Practice",
            "## Recognize success",
            "## Check",
            "## Recover or continue",
            "## Understand the mechanism",
        )
        self.assertEqual(
            tuple(line for line in guide.splitlines() if line.startswith("## ")),
            expected_headings,
        )
        self.assertNotRegex(guide, r"(?m)^```(?:powershell|sh|text|bash|console)\s*$")
        self.assertEqual(
            tuple(re.findall(r"(?m)^\{\{action:([^}]+)\}\}$", guide)),
            tuple(action.id for action in manifest.actions),
        )
        self.assertIn("Solo practice", guide)
        self.assertIn("Arbiter Academy GitHub Discussion", guide)
        self.assertIn("does not authenticate a human approval", guide)
        self.assertIn("does not authenticate a GitHub Discussion response", guide)
        self.assertNotIn("approval record", guide.casefold())

        actions = {action.id: action for action in manifest.actions}
        self.assertEqual(
            tuple(actions),
            (
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
            ),
        )
        self.assertIn("P01 is the first Practitioner lesson in this preview.", guide)
        self.assertIn("### If review finds a concrete correction", guide)
        self.assertRegex(
            guide,
            r"### If review finds a concrete correction[\s\S]*?"
            r"\{\{action:P01-revise-spec\}\}[\s\S]*?"
            r"### When the draft is acceptable[\s\S]*?"
            r"\{\{action:P01-proceed\}\}",
        )
        self.assertIn("do not derive a plan", actions["P01-revise-spec"].instruction.casefold())
        self.assertEqual(actions["P01-draft-spec"].actor, "agent")
        self.assertEqual(actions["P01-revise-spec"].actor, "learner")
        self.assertEqual(actions["P01-proceed"].actor, "learner")
        self.assertEqual(actions["P01-check"].actor, "learner")






    def test_loader_requires_a_learner_visible_track_index(self) -> None:
        """Catches a wheel/source tree with guides but no usable Practitioner entry point."""
        for replacement in (None, "<!-- maintainer note only -->\n"):
            with self.subTest(replacement=replacement), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                shutil.copytree(SOURCE / "academy", root / "academy")
                index = root / "academy/tracks/practitioner/index.md"
                if replacement is None:
                    index.unlink()
                else:
                    index.write_text(replacement, encoding="utf-8")

                with self.assertRaisesRegex(CurriculumError, "track index"):
                    load_track(root, "practitioner")

    def test_loader_rejects_each_comment_only_progressive_hint(self) -> None:
        """Catches hint headings whose comments falsely count as progressive guidance."""
        for number in (1, 2, 3):
            with self.subTest(hint=number), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                shutil.copytree(SOURCE / "academy", root / "academy")
                path = root / "academy/tracks/practitioner/P06-context-drift-recovery.md"
                text = path.read_text(encoding="utf-8")
                heading = f"### Hint {number}\n"
                start = text.index(heading) + len(heading)
                terminator = (
                    f"### Hint {number + 1}\n"
                    if number < 3
                    else "## Understand the mechanism\n"
                )
                end = text.index(terminator, start)
                path.write_text(
                    text[:start]
                    + "\n<!-- no learner-visible guidance -->\n<!-- multiline\ncomment -->\n\n"
                    + text[end:],
                    encoding="utf-8",
                )

                with self.assertRaisesRegex(CurriculumError, "learner-visible"):
                    load_track(root, "practitioner")

    def test_loader_rejects_comment_only_required_content(self) -> None:
        """Catches a required guide section that renders as empty to a learner."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copytree(SOURCE / "academy", root / "academy")
            path = root / "academy/tracks/practitioner/P07-threat-model.md"
            text = path.read_text(encoding="utf-8")
            start = text.index("## Recognize success")
            end = text.index("## Check")
            path.write_text(
                text[:start] + "## Recognize success\n\n<!-- deliberately empty -->\n\n" + text[end:],
                encoding="utf-8",
            )

            with self.assertRaisesRegex(CurriculumError, "learner-visible content"):
                load_track(root, "practitioner")

    def test_loader_accepts_guided_inline_progressive_hints(self) -> None:
        """Guided lessons keep their eight-heading flow while retaining three usable hints."""
        track = load_track(SOURCE, "practitioner")
        p07 = next(lab for lab in track.labs if lab.id == "P07-threat-model")

        self.assertEqual(len(p07.hints), 3)
        self.assertTrue(all(hint.strip() for hint in p07.hints))
        self.assertNotIn("{{action:", p07.hints[2])

    def test_loader_rejects_comment_only_guided_inline_hint(self) -> None:
        """Inline hint labels cannot hide an empty learner experience behind comments."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copytree(SOURCE / "academy", root / "academy")
            path = root / "academy/tracks/practitioner/P07-threat-model.md"
            text = path.read_text(encoding="utf-8")
            start = text.index("**Hint 2.**") + len("**Hint 2.**")
            end = text.index("**Hint 3.**", start)
            path.write_text(
                text[:start] + "\n<!-- no learner-visible hint -->\n\n" + text[end:],
                encoding="utf-8",
            )

            with self.assertRaisesRegex(CurriculumError, "learner-visible"):
                load_track(root, "practitioner")

    def test_loader_rejects_empty_guided_inline_hint_before_the_next_paragraph(self) -> None:
        """A later hint paragraph cannot be misbound as content for an empty earlier hint."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copytree(SOURCE / "academy", root / "academy")
            path = root / "academy/tracks/practitioner/P07-threat-model.md"
            text = path.read_text(encoding="utf-8")
            start = text.index("**Hint 2.**") + len("**Hint 2.**")
            end = text.index("**Hint 3.**", start)
            text = text[:start] + "\n\n" + text[end:]
            hints = curriculum._guided_inline_hints(text, path)

            self.assertEqual(hints["Hint 2"], "")
            self.assertIn("Hint 3", hints)
            path.write_text(text, encoding="utf-8")

            with self.assertRaisesRegex(CurriculumError, "learner-visible"):
                load_track(root, "practitioner")

    def test_loader_rejects_unsafe_canonical_action_id_before_action_path_probe(self) -> None:
        """Canonical action document identifiers must not reach pathlib filesystem probing."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "academy/tracks/practitioner/P01-feature-through-plan.md"
            path.parent.mkdir(parents=True)
            source = (
                SOURCE / "academy/tracks/practitioner/P01-feature-through-plan.md"
            ).read_text(encoding="utf-8")
            path.write_text(
                source.replace("id: P01-feature-through-plan", "id: ../outside", 1),
                encoding="utf-8",
            )
            with patch.object(
                Path,
                "is_file",
                side_effect=AssertionError("filesystem probe"),
            ):
                with self.assertRaisesRegex(CurriculumError, "safe action document ID"):
                    curriculum._parse_lab(path)

    def test_verify_track_matrix_binds_exact_structural_inventory(self) -> None:
        """Catches a missing scenario/checkpoint binding or matrix declaration."""
        report = verify_track(SOURCE, "practitioner", matrix=True)

        self.assertTrue(report.passed, report.issues)
        self.assertEqual(report.lab_count, 8)
        self.assertEqual(report.matrix_cells, 115)
        self.assertNotIn(str(SOURCE), report.render())

    def test_p07_freezes_exact_semantic_matrix(self) -> None:
        """Catches P07 falling back to generic structural evidence labels."""
        from academy_engine.curriculum import _MATRIX_CASES

        self.assertEqual(
            _MATRIX_CASES["P07-threat-model"],
            (
                "untouched", "partial", "wrong", "intended", "equivalent",
                "missing-native-field", "wrong-stride-order", "generic-stride",
                "mixed-academy-field", "invocation-claim", "wrong-target-path",
                "wrong-target-blob", "stale-target-sha256", "target-mutated",
                "target-touch-revert", "noncanonical-bytes", "one-extra-path",
                "extra-commit", "merge-history", "uncommitted",
            ),
        )

    def test_p03_freezes_the_native_evidence_adversarial_matrix_and_privacy_guide(self) -> None:
        """Catches P03 falling back to the generic five-cell declaration or vague learner contract."""
        from academy_engine.curriculum import _MATRIX_CASES

        self.assertEqual(
            _MATRIX_CASES["P03-record-an-adr"],
            (
                "untouched", "partial", "wrong", "intended", "equivalent",
                "invalid-attribution", "normalized-attribution", "mismatched-attribution",
                "rewritten-log", "wrong-ordinal", "wrong-choice", "wrong-order",
                "uncommitted", "extra-path", "generic-event-decoy",
            ),
        )
        guide = (SOURCE / "academy/tracks/practitioner/P03-record-an-adr.md").read_text(encoding="utf-8")
        for required in (
            "1–80 Unicode scalar values", "No learner email", "one commit or two linear commits",
            "`%an`", "append-only byte prefix", "never echo a rejected name",
        ):
            with self.subTest(required=required):
                self.assertIn(required, guide)

    def test_p03_is_a_public_action_backed_decision_lesson(self) -> None:
        """Catches the canonical P03 action file or learner-facing decision boundary drifting."""
        guide_path = SOURCE / "academy/tracks/practitioner/P03-record-an-adr.md"
        guide = guide_path.read_text(encoding="utf-8")

        expected_headings = (
            "## Know before you begin",
            "## What you will prove",
            "## Prepare safely",
            "## Practice the decision",
            "## Recognize success",
            "## Check",
            "## Recover or continue",
            "## Understand the mechanism",
        )
        self.assertEqual(
            tuple(line for line in guide.splitlines() if line in expected_headings),
            expected_headings,
        )
        manifest = load_action_manifest(SOURCE, "P03-record-an-adr")
        lab = load_track(SOURCE, "practitioner").labs[2]
        self.assertNotIn("```", guide)
        self.assertEqual(
            tuple(re.findall(r"(?m)^\{\{action:([^}]+)\}\}$", guide)),
            tuple(action.id for action in manifest.actions),
        )
        self.assertEqual(lab.id, "P03-record-an-adr")
        self.assertEqual(lab.host_commands["codex"], '$ca-adr "Choose the Workshop Queue summary-format boundary"')
        normalized_guide = " ".join(guide.split())
        for required in (
            "stable text", "structured JSON", "learner chooses", "clean worktree", "1–2 linear commits",
            "only ADR/log paths", "ADR before log if split", "commit date/name", "artifact format/choice",
            "append-only log prefix", "cannot prove human acceptance", "host command use", "reasoning quality",
            "chronology", "independent review", "P03-record-an-adr",
        ):
            with self.subTest(required=required):
                self.assertIn(required, normalized_guide)

    def test_p04_freezes_offline_candidate_review_matrix_and_no_install_guide(self) -> None:
        """Catches P04 drifting back to generic review prose or an install-oriented exercise."""
        from academy_engine.curriculum import _MATRIX_CASES

        self.assertEqual(
            _MATRIX_CASES["P04-review-a-dependency"],
            (
                "untouched", "partial", "wrong", "intended", "equivalent", "candidate-tampered",
                "license-tampered", "apache-missing", "invented-notice", "stale-project-hash",
                "incomplete-review", "pre-review-manifest-edit", "same-commit-adoption", "incomplete-closure",
                "wrong-lock", "wrong-wrapper", "extra-dependency", "uncommitted", "extra-path",
            ),
        )
        guide = (SOURCE / "academy/tracks/practitioner/P04-review-a-dependency.md").read_text(encoding="utf-8")
        for required in (
            "candidate-set.json", "review-only-never-install", "Known", "Supply chain",
            "Install-Policy: no-install-in-p04", "2026-07-31", "No NOTICE", "no install during P04",
            "one later", "external installation",
        ):
            with self.subTest(required=required):
                self.assertIn(required, guide)
        self.assertNotIn("pip install", guide)

    def test_p04_is_a_public_action_backed_rejection_lesson(self) -> None:
        """Catches P04 teaching an undeclared install path or asking a learner to infer roles."""
        guide_path = SOURCE / "academy/tracks/practitioner/P04-review-a-dependency.md"
        guide = guide_path.read_text(encoding="utf-8")
        manifest = load_action_manifest(SOURCE, "P04-review-a-dependency")
        headings = (
            "## Know before you begin",
            "## What you will prove",
            "## Prepare safely",
            "## Practice",
            "## Recognize success",
            "## Check",
            "## Recover or continue",
            "## Understand the mechanism",
        )
        self.assertEqual(tuple(line for line in guide.splitlines() if line in headings), headings)
        self.assertNotRegex(guide, r"(?m)^```(?:powershell|sh|text|bash|console)\s*$")
        self.assertEqual(
            tuple(re.findall(r"(?m)^\{\{action:([^}]+)\}\}$", guide)),
            tuple(action.id for action in manifest.actions),
        )
        self.assertEqual(len(manifest.actions), 18)
        self.assertIn("The website is the primary lesson surface.", guide)
        self.assertIn("Academy CLI only handles Prepare, Check, and Reset.", guide)
        self.assertIn("bounded `datetime.strptime`", guide)
        self.assertIn("Decision: reject", guide)
        self.assertIn("does not prove that you ran a host command", guide)
        self.assertIn("does not authenticate your review or selection", guide)
        self.assertNotIn("pip install", guide)
        self.assertIn("P04-review-a-dependency", set(load_preview_manifest(SOURCE).guided_labs))

    def test_p04_cannot_be_public_before_p03_closes_its_prerequisite(self) -> None:
        """Catches P04 being promoted while its required P03 lesson remains absent."""
        path = SOURCE / "academy/publication/preview-0.24.json"
        candidate = json.loads(path.read_text(encoding="utf-8"))
        for field in ("available_labs", "runnable_labs", "guided_labs"):
            candidate[field].remove("P03-record-an-adr")

        with self.assertRaisesRegex(
            ValueError,
            r"missing prerequisite\(s\) for P04-review-a-dependency: P03-record-an-adr",
        ):
            validate_preview_manifest(SOURCE, candidate)


    def test_p05_freezes_remediation_evidence_matrix_and_receipt_guidance(self) -> None:
        from academy_engine.curriculum import _MATRIX_CASES

        self.assertEqual(
            _MATRIX_CASES["P05-checkpoint-remediation"],
            (
                "untouched", "partial", "wrong", "intended", "equivalent",
                "blocked-state-missing", "blocked-not-persisted", "defect-not-staged",
                "json-only-finding", "red-not-meaningful", "red-after-green",
                "changed-red-test", "broad-repair", "wrong-history-order",
                "receipt-too-early", "copied-attempt", "uncommitted",
                "malformed-receipt", "unsafe-path", "generic-event-decoy",
                "host-invocation-claim",
            ),
        )
        guide = (SOURCE / "academy/tracks/practitioner/P05-checkpoint-remediation.md").read_text(encoding="utf-8")
        for required in (
            "test-only RED", "code-only GREEN", "schema_version", "red_commit",
            "remediation_commit", "receipt last", "not evidence that either command was invoked",
            "`affected_paths` is exactly, in order, `tests/test_cli.py` then `workshop_queue/cli.py`",
            "P06 is the next public guided Academy lesson",
        ):
            with self.subTest(required=required):
                self.assertIn(required, guide)
        for obsolete in (
            "shared changed paths",
            "real shared path",
            "shared affected paths",
            "actually intersects it",
        ):
            with self.subTest(obsolete=obsolete):
                self.assertNotIn(obsolete, guide)

    def test_p05_guide_is_a_complete_private_guided_lesson(self) -> None:
        """Catches P05 drifting back to prose-only, raw-command instruction."""
        guide = (SOURCE / "academy/tracks/practitioner/P05-checkpoint-remediation.md").read_text(encoding="utf-8")
        headings = (
            "## Know before you begin",
            "## What you will prove",
            "## Prepare safely",
            "## Practice",
            "## Recognize success",
            "## Check",
            "## Recover or continue",
            "## Understand the mechanism",
        )
        positions = [guide.index(heading) for heading in headings]
        self.assertEqual(positions, sorted(positions))
        self.assertNotIn("```", guide)
        self.assertIn("{{action:P05-prepare}}", guide)
        self.assertIn("{{action:P05-check}}", guide)
        self.assertIn("{{action:P05-reset-retry}}", guide)
        self.assertIn("Check does not authenticate a checkpoint run", guide)
        self.assertIn("does not prove command chronology", guide)

    def test_p06_freezes_interrupted_lane_scenario_identity(self) -> None:
        """Catches P06 losing its interrupted-lane, provenance, or preservation boundary."""
        scenario_root = SOURCE / "academy/scenarios/P06-context-drift-recovery"
        manifest = json.loads((scenario_root / "manifest.json").read_text(encoding="utf-8"))
        scenario_bytes = (scenario_root / "files/scenario.json").read_bytes()

        self.assertEqual(
            manifest["files"],
            [
                {"source": "CONTEXT.md", "destination": ".codearbiter/CONTEXT.md"},
                {
                    "source": "CONTEXT.provenance.json",
                    "destination": ".codearbiter/.provenance/CONTEXT.json",
                },
                {"source": "preserved-note.md", "destination": "docs/preserved-note.md"},
                {
                    "source": "scenario.json",
                    "destination": "training_scenarios/P06-context-drift-recovery.json",
                },
            ],
        )
        self.assertEqual(manifest["removals"], [])
        self.assertEqual(manifest["starting_task"], "P06")
        self.assertEqual(
            manifest["checkpoint"],
            "academy/checkpoints/P06-context-drift-recovery.json",
        )
        self.assertIs(manifest["requires_push_safe_setup"], False)
        self.assertEqual(
            scenario_bytes,
            (
                b'{"interrupted_lane":"P05-checkpoint-remediation",'
                b'"lab_id":"P06-context-drift-recovery",'
                b'"operation":"provenance_recovery",'
                b'"preserved_path":"docs/preserved-note.md",'
                b'"provenance_path":".codearbiter/.provenance/CONTEXT.json",'
                b'"stale_claim":"Workshop Queue report output is JSON-only.",'
                b'"starting_condition":"interrupted-lane-context-stale",'
                b'"target":".codearbiter/CONTEXT.md"}\n'
            ),
        )

    def test_p06_guide_distinguishes_host_route_from_invocation_proof(self) -> None:
        """Catches route evidence being described as proof that a host command ran."""
        p06 = load_track(SOURCE, "practitioner").labs[5]
        actions = load_action_manifest(SOURCE, "P06-context-drift-recovery")
        guide = (
            SOURCE / "academy/tracks/practitioner/P06-context-drift-recovery.md"
        ).read_text(encoding="utf-8")

        self.assertEqual(
            p06.host_commands,
            {
                "claude-code": "/ca:context-check",
                "codex": "$ca-context-check",
                "pi": "/ca-context-check\n/skill:ca-context-check",
            },
        )
        audit = next(action for action in actions.actions if action.id == "P06-run-context-audit")
        self.assertEqual(
            tuple(variant.command for variant in audit.variants if variant.host == "pi"),
            ("/ca-context-check", "/skill:ca-context-check"),
        )
        for required in (
            "Workshop Queue report output is JSON-only.",
            "042746e43698e5d2a6de4c536f1024f893aef805",
            "5b41fb168a8b258cfae7eebc46e8b9ea7696ba56",
            "stable text is the default and structured JSON is optional",
            "Workshop Queue report output defaults to stable text and supports structured JSON with --format json.",
        ):
            with self.subTest(required=required):
                self.assertIn(required, guide)
        self.assertIn("`re-scout` is the sole permitted recovery route", guide)
        self.assertIn("does not prove that the host command ran", guide)
        self.assertNotIn("re-baseline", guide.casefold())
        self.assertNotIn("defer", guide.casefold())

        self.assertEqual(
            tuple(action.id for action in actions.actions),
            (
                "P06-prepare", "P06-inspect-evidence", "P06-run-context-audit",
                "P06-select-rescout", "P06-apply-correction", "P06-review-correction-boundary",
                "P06-commit-correction", "P06-write-handoff", "P06-stage-handoff", "P06-review-handoff-boundary",
                "P06-commit-handoff", "P06-check", "P06-return-base", "P06-reset-retry",
            ),
        )

    def test_p06_is_a_complete_eight_heading_guided_document_without_raw_command_fences(self) -> None:
        """Catches a public P06 rewrite regressing to prose-only or surface-ambiguous steps."""
        guide = (
            SOURCE / "academy/tracks/practitioner/P06-context-drift-recovery.md"
        ).read_text(encoding="utf-8")

        headings = (
            "## Know before you begin",
            "## What you will prove",
            "## Prepare safely",
            "## Practice",
            "## Recognize success",
            "## Check",
            "## Recover or continue",
            "## Understand the mechanism",
        )
        positions = [guide.index(heading) for heading in headings]
        self.assertEqual(positions, sorted(positions))
        self.assertNotIn("```", guide)
        for action_id in (
            "P06-prepare",
            "P06-inspect-evidence",
            "P06-run-context-audit",
            "P06-select-rescout",
            "P06-apply-correction",
            "P06-commit-correction",
            "P06-write-handoff",
            "P06-stage-handoff",
            "P06-commit-handoff",
            "P06-check",
            "P06-return-base",
            "P06-reset-retry",
        ):
            with self.subTest(action_id=action_id):
                self.assertIn(f"{{{{action:{action_id}}}}}", guide)

    def test_p06_recovery_uses_the_guided_reset_action_without_destructive_commands(self) -> None:
        """Catches P06 Reset regressing from a self-contained action card to raw prose."""
        p06 = load_track(SOURCE, "practitioner").labs[5]
        actions = load_action_manifest(SOURCE, "P06-context-drift-recovery")
        reset = next(action for action in actions.actions if action.id == "P06-reset-retry")

        self.assertEqual(p06.scenario_command, "{{action:P06-prepare}}")
        self.assertEqual(p06.checkpoint_command, "{{action:P06-check}}")
        self.assertIn("{{action:P06-reset-retry}}", p06.recovery)
        self.assertEqual(
            {variant.operating_system for variant in reset.variants},
            {"windows", "macos", "linux"},
        )
        for variant in reset.variants:
            with self.subTest(variant=variant.id):
                self.assertIn(load_preview_manifest(SOURCE).release, variant.command)
                self.assertIn("reset P06-context-drift-recovery", variant.command)
                self.assertNotIn("<learner-repository>", variant.command)

        self.assertIn("archives the earlier attempt", reset.expected_result)
        self.assertIn("archived branch remains reachable", reset.evidence or "")
        recovery = "\n".join((p06.recovery, reset.recovery))
        for destructive in (
            "git reset --hard",
            "git rebase",
            "git commit --amend",
            "git update-ref -d",
        ):
            with self.subTest(destructive=destructive):
                self.assertNotIn(destructive, recovery)

    def test_p06_freezes_all_eight_structural_scenario_expectations(self) -> None:
        """Catches structural verification checking only P06's old three-field prefix."""
        from academy_engine import curriculum

        expected_scenario = {
            "interrupted_lane": "P05-checkpoint-remediation",
            "lab_id": "P06-context-drift-recovery",
            "operation": "provenance_recovery",
            "preserved_path": "docs/preserved-note.md",
            "provenance_path": ".codearbiter/.provenance/CONTEXT.json",
            "stale_claim": "Workshop Queue report output is JSON-only.",
            "starting_condition": "interrupted-lane-context-stale",
            "target": ".codearbiter/CONTEXT.md",
        }
        expectations = getattr(curriculum, "_PRACTITIONER_SCENARIO_EXPECTATIONS", {})
        self.assertEqual(expectations.get("P06-context-drift-recovery"), expected_scenario)

    def test_p06_exact_scenario_is_not_duplicated_by_the_generic_registry(self) -> None:
        """Catches a dead three-field P06 tuple drifting from its exact descriptor."""
        from academy_engine import curriculum

        self.assertNotIn(
            "P06-context-drift-recovery",
            curriculum._PRACTITIONER_SCENARIOS,
        )

    def test_p06_checkpoint_declares_exact_six_field_trusted_contract(self) -> None:
        """Catches a checkpoint definition that leaves a P06 evidence path learner-controlled."""
        checkpoint = json.loads(
            (
                SOURCE / "academy/checkpoints/P06-context-drift-recovery.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(checkpoint["schema_version"], 2)
        self.assertEqual(checkpoint["id"], "P06-context-drift-recovery")
        self.assertEqual(len(checkpoint["predicates"]), 1)
        predicate = checkpoint["predicates"][0]
        self.assertEqual(
            set(predicate),
            {
                "id", "type", "profile", "context", "handoff", "source",
                "preserved_path", "provenance",
            },
        )
        self.assertEqual(predicate["id"], "provenance_drift_recovery")
        self.assertEqual(predicate["type"], "lab_semantics")
        self.assertEqual(
            {key: value for key, value in predicate.items() if key not in {"id", "type"}},
            {
                "profile": "provenance_recovery",
                "context": ".codearbiter/CONTEXT.md",
                "handoff": ".codearbiter/reports/academy/P06-recovery.json",
                "source": "workshop_queue/cli.py",
                "preserved_path": "docs/preserved-note.md",
                "provenance": ".codearbiter/.provenance/CONTEXT.json",
            },
        )

    def test_p06_checkpoint_trusted_paths_are_declared_by_the_public_schema(self) -> None:
        """Catches the published schema rejecting trusted P06 evidence paths."""
        schema = json.loads(
            (SOURCE / "academy/checkpoint.schema.json").read_text(encoding="utf-8")
        )
        checkpoint = json.loads(
            (
                SOURCE / "academy/checkpoints/P06-context-drift-recovery.json"
            ).read_text(encoding="utf-8")
        )
        properties = schema["properties"]["predicates"]["items"]["properties"]

        for field in ("source", "preserved_path", "provenance"):
            with self.subTest(field=field):
                self.assertEqual(properties.get(field), {"$ref": "#/$defs/path"})
        self.assertLessEqual(set(checkpoint["predicates"][0]), set(properties))

    def test_p06_declares_exact_twenty_five_case_matrix(self) -> None:
        """Catches P06 falling back to the generic five-case structural declaration."""
        from academy_engine import curriculum

        self.assertEqual(
            curriculum._MATRIX_CASES["P06-context-drift-recovery"],
            (
                "untouched", "partial", "wrong", "intended", "equivalent-rescout",
                "stale-claim", "source-not-contradictory", "unchanged-context",
                "wrong-correction", "missing-note", "recreated-note", "missing-provenance",
                "wrong-provenance-schema", "wrong-prior-source-hash", "provenance-not-rebased",
                "wrong-digest", "noncanonical-handoff", "unsafe-path", "wrong-route",
                "one-commit", "reversed-order", "extra-path", "extra-commit",
                "merge-history", "uncommitted",
            ),
        )

    def test_p07_freezes_native_and_academy_sections_without_invocation_claim(self) -> None:
        """Catches P07 mixing native fields, Academy binding, or host-invocation claims."""
        p07 = load_track(SOURCE, "practitioner").labs[6]
        guide = (
            SOURCE / "academy/tracks/practitioner/P07-threat-model.md"
        ).read_text(encoding="utf-8")

        self.assertEqual(p07.estimated_minutes, 35)
        self.assertEqual(p07.prerequisites, ("P06-context-drift-recovery",))
        self.assertEqual(p07.next_lab, "P08-repository-hygiene")
        self.assertEqual(
            p07.host_commands,
            {
                "claude-code": (
                    '/ca:threat-model "academy_engine/paths.py archive-import containment boundary"'
                ),
                "codex": (
                    '$ca-threat-model "academy_engine/paths.py archive-import containment boundary"'
                ),
                "pi": (
                    '/ca-threat-model "academy_engine/paths.py archive-import containment boundary"\n'
                    '/skill:ca-threat-model "academy_engine/paths.py archive-import containment boundary"'
                ),
            },
        )
        native_sections = (
            "Its sections are Scope, STRIDE findings",
            "Clearance, in that order",
            "S, T, R, I, D, E\norder",
            "## Academy Target-SHA256/identity binding",
        )
        self.assertTrue(
            all(section in guide for section in native_sections),
            "P07 must teach the native report sections, STRIDE order, and separate binding.",
        )
        positions = [guide.index(section) for section in native_sections]
        self.assertEqual(positions, sorted(positions))
        normalized = " ".join(guide.split())
        for required in (
            "opt-in and read-only",
            "It does not prove that a host command was invoked",
            "prepared blob, head blob, and SHA-256 values",
            "CLEAR TO IMPLEMENT",
            "BLOCKED - resolve findings first",
            "keep destination resolution under the selected repository root",
            "Reject absolute, traversal, symlink, and Windows reparse-point ancestors",
            "Fail closed on a different drive or an unrepresentable containment path",
        ):
            with self.subTest(required=required):
                self.assertIn(required, normalized)
        self.assertNotIn("proves that `$ca-threat-model`", guide)
        self.assertNotIn("native Academy", guide)

    def test_p07_is_a_public_action_backed_threat_model_lesson(self) -> None:
        """Catches P07 returning to raw commands or claiming Check proves live process."""
        guide = (SOURCE / "academy/tracks/practitioner/P07-threat-model.md").read_text(encoding="utf-8")
        manifest = load_action_manifest(SOURCE, "P07-threat-model")
        lab = load_track(SOURCE, "practitioner").labs[6]

        expected_headings = (
            "## Know before you begin",
            "## What you will prove",
            "## Prepare safely",
            "## Practice",
            "## Recognize success",
            "## Check",
            "## Recover or continue",
            "## Understand the mechanism",
        )
        self.assertEqual(tuple(line for line in guide.splitlines() if line in expected_headings), expected_headings)
        self.assertEqual(tuple(line for line in guide.splitlines() if line.startswith("## ")), expected_headings)
        self.assertFalse(re.search(r"(?m)^#{3,} ", guide))
        self.assertNotIn("```", guide)
        self.assertEqual(
            tuple(re.findall(r"(?m)^\{\{action:([^}]+)\}\}$", guide)),
            tuple(action.id for action in manifest.actions),
        )
        self.assertEqual(lab.id, "P07-threat-model")
        self.assertEqual(lab.host_commands["codex"], '$ca-threat-model "academy_engine/paths.py archive-import containment boundary"')
        normalized = " ".join(guide.split())
        for required in (
            "strict UTF-8 with LF line endings", "S, T, R, I, D, E order",
            "Academy Target-SHA256/identity binding", "does not prove that a host command was invoked",
            "does not prove that the agent drafted first", "does not prove that you reviewed",
            "Neither clearance outcome authorizes a P07 code change", "public guided and runnable Academy lesson",
        ):
            with self.subTest(required=required):
                self.assertIn(required, normalized)

    def test_p07_freezes_target_identity_descriptor_and_checkpoint(self) -> None:
        """Catches a P07 source contract that can silently rebind to changed target bytes."""
        descriptor = (
            b'{"lab_id":"P07-threat-model","operation":"stride_model",'
            b'"request":"academy_engine/paths.py archive-import containment boundary",'
            b'"schema_version":1,"starting_condition":"model-absent",'
            b'"target":"academy_engine/paths.py",'
            b'"target_blob":"b36801add4eb375f796d1107ee63dd604d08a034",'
            b'"target_sha256":"e40a7655ce6ba6cde58a91ae10a714f10046c055ac90dcbc58f0696c39133a5d"}\n'
        )
        checkpoint = (
            b'{"schema_version":2,"id":"P07-threat-model","predicates":['
            b'{"id":"stride_model","type":"lab_semantics","profile":"stride_model",'
            b'"model":".codearbiter/reports/academy/P07-threat-model.md",'
            b'"target":"academy_engine/paths.py",'
            b'"target_blob":"b36801add4eb375f796d1107ee63dd604d08a034",'
            b'"target_sha256":"e40a7655ce6ba6cde58a91ae10a714f10046c055ac90dcbc58f0696c39133a5d"}]}\n'
        )

        self.assertEqual(
            (SOURCE / "academy/scenarios/P07-threat-model/files/scenario.json").read_bytes(),
            descriptor,
        )
        self.assertEqual(
            (SOURCE / "academy/checkpoints/P07-threat-model.json").read_bytes(),
            checkpoint,
        )
        report = verify_track(SOURCE, "practitioner", matrix=True)
        self.assertTrue(report.passed, report.issues)

    def test_p07_checkpoint_identity_fields_are_declared_by_the_public_schema(self) -> None:
        """Catches a valid P07 checkpoint becoming invalid against its published schema."""
        schema = json.loads(
            (SOURCE / "academy/checkpoint.schema.json").read_text(encoding="utf-8")
        )
        checkpoint = json.loads(
            (SOURCE / "academy/checkpoints/P07-threat-model.json").read_text(
                encoding="utf-8"
            )
        )
        properties = schema["properties"]["predicates"]["items"]["properties"]

        self.assertEqual(
            properties.get("target_blob"),
            {"type": "string", "pattern": "^[0-9a-f]{40}$"},
        )
        self.assertEqual(
            properties.get("target_sha256"),
            {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        )
        self.assertLessEqual(set(checkpoint["predicates"][0]), set(properties))

    def test_p07_recovery_uses_archive_then_retry_without_destructive_commands(self) -> None:
        """Catches learner recovery copy that rewrites or discards the failed attempt."""
        manifest = load_action_manifest(SOURCE, "P07-threat-model")
        reset = next(action for action in manifest.actions if action.id == "P07-reset")
        recovery = " ".join((reset.instruction + " " + reset.recovery).split())

        self.assertTrue(
            all(
                "reset P07-threat-model" in variant.command
                and variant.surface == "native-terminal"
                and variant.host == "none"
                and "!" not in variant.command
                for variant in reset.variants
            )
        )
        self.assertIn("archives the earlier attempt", recovery)
        self.assertIn("retry", recovery)
        for destructive in (
            "git reset --hard",
            "git checkout",
            "git rebase",
            "git commit --amend",
            "git branch -D",
            "force-push",
        ):
            with self.subTest(destructive=destructive):
                self.assertNotIn(destructive, recovery)

    def test_verify_track_rejects_a_noncanonical_practitioner_binding(self) -> None:
        """Catches a catalog manifest path that drifts from the frozen lab tuple."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copytree(SOURCE / "academy", root / "academy")
            catalog = root / "academy/catalog.json"
            text = catalog.read_text(encoding="utf-8")
            catalog.write_text(
                text.replace(
                    '"manifest":"academy/scenarios/P08-repository-hygiene/manifest.json"',
                    '"manifest":"academy/scenarios/P07-threat-model/manifest.json"',
                ),
                encoding="utf-8",
            )

            report = verify_track(root, "practitioner", matrix=True)

        self.assertFalse(report.passed)
        self.assertIn("canonical", "\n".join(report.issues))

    def test_verify_track_rejects_each_noncanonical_manifest_identity_field(self) -> None:
        """Catches a manifest redirected away from its catalog lab, task, checkpoint, or safety."""
        cases = (
            (
                "id",
                "P01-feature-through-plan",
                "id",
                "P08-repository-hygiene",
            ),
            (
                "checkpoint",
                "P01-feature-through-plan",
                "checkpoint",
                "academy/checkpoints/P08-repository-hygiene.json",
            ),
            (
                "requires_push_safe_setup",
                "P02-commit-review-pr",
                "requires_push_safe_setup",
                False,
            ),
            (
                "starting_task",
                "P01-feature-through-plan",
                "starting_task",
                "P99",
            ),
        )
        for label, lab_id, field, value in cases:
            with self.subTest(field=label), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                shutil.copytree(SOURCE / "academy", root / "academy")
                manifest_path = root / f"academy/scenarios/{lab_id}/manifest.json"
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                manifest[field] = value
                manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

                report = verify_track(root, "practitioner", matrix=True)

                self.assertFalse(report.passed)
                self.assertIn(
                    "scenario manifest binding is noncanonical",
                    "\n".join(report.issues),
                )

    def test_verify_track_rejects_noncanonical_practitioner_scenario_semantics(self) -> None:
        """Catches a scenario target that drifts from the approved Practitioner exercise."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copytree(SOURCE / "academy", root / "academy")
            scenario = root / "academy/scenarios/P04-review-a-dependency/files/scenario.json"
            scenario.write_text(
                '{"schema_version":1,"lab_id":"P04-review-a-dependency",'
                '"operation":"dependency_review","target":"fictional-csv-helper",'
                '"starting_condition":"install-blocked"}\n',
                encoding="utf-8",
            )

            report = verify_track(root, "practitioner", matrix=True)

        self.assertFalse(report.passed)
        self.assertIn("scenario semantics are noncanonical", "\n".join(report.issues))

    def test_cli_reports_a_structural_matrix_without_semantic_success_claims(self) -> None:
        """Catches the structural command claiming checkpoint or graduation success."""
        result = subprocess.run(
            [
                sys.executable,
                str(SOURCE / "scripts/academy.py"),
                "verify-track",
                "practitioner",
                "--matrix",
            ],
            cwd=SOURCE,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Practitioner: 8 labs", result.stdout)
        self.assertIn("115 matrix cells", result.stdout)
        self.assertIn("structural", result.stdout.casefold())
        self.assertIn("checkpoints remain authoritative", result.stdout.casefold())
        self.assertNotIn("graduated", result.stdout.casefold())

    def test_promoted_practitioner_lessons_name_their_public_boundary(self) -> None:
        """Catches a public P06-P08 lesson retaining private-draft status copy."""
        for document_id in (
            "P06-context-drift-recovery",
            "P07-threat-model",
            "P08-repository-hygiene",
        ):
            with self.subTest(document_id=document_id):
                guide = (
                    SOURCE / f"academy/tracks/practitioner/{document_id}.md"
                ).read_text(encoding="utf-8")
                self.assertIn("public guided and runnable Academy lesson in this preview", guide)
                self.assertIn(document_id, load_preview_manifest(SOURCE).guided_labs)
                self.assertIn(document_id, load_preview_manifest(SOURCE).runnable_labs)

    def test_p02_uses_the_rendered_reset_action_and_records_the_stage_work_design_step(self) -> None:
        """Catches a private draft teaching a raw reset path or omitting the staging design step."""
        guide = (
            SOURCE / "academy/tracks/practitioner/P02-commit-review-pr.md"
        ).read_text(encoding="utf-8")
        design = (
            SOURCE / "docs/superpowers/specs/2026-08-11-p02-guided-lesson-design.md"
        ).read_text(encoding="utf-8")

        self.assertIn("{{action:P02-reset}}", guide)
        self.assertNotIn(
            "arbiter-academy --repository $learnerRepository reset P02-commit-review-pr",
            guide,
        )
        self.assertIn("inspect and stage the prepared exercise change", design)

    def test_p04_check_evidence_distinguishes_computation_from_human_authentication(self) -> None:
        """Catches malformed Check copy that obscures its verification limit."""
        manifest = load_action_manifest(SOURCE, "P04-review-a-dependency")
        check = next(action for action in manifest.actions if action.id == "P04-check")

        self.assertIn("and it does not authenticate your review or selection", check.evidence or "")
        self.assertNotIn("or does not authenticate your review or selection", check.evidence or "")


if __name__ == "__main__":
    unittest.main()


    def test_p02_teaches_exact_identity_ref_and_two_commit_receipt_workflow(self) -> None:
        guide = (
            SOURCE / "academy/tracks/practitioner/P02-commit-review-pr.md"
        ).read_text(encoding="utf-8")

        for required in (
            "offline-local pull-request rehearsal", "logical repository IDs",
            "not authenticated human approval", "not a hosted pull request",
            "receipt-only commit", "GitHub remote use",
        ):
            with self.subTest(required=required):
                self.assertIn(required, guide)
        self.assertNotIn("```", guide)
        self.assertIn("{{action:P02-record-receipt}}", guide)


    def test_p02_workflow_orders_external_prepare_checkout_guards_and_two_commits(self) -> None:
        guide = (
            SOURCE / "academy/tracks/practitioner/P02-commit-review-pr.md"
        ).read_text(encoding="utf-8")
        markers = (
            "{{action:P02-prepare}}", "{{action:P02-enter-and-guard}}",
            "{{action:P02-inspect-change}}", "{{action:P02-stage-work}}", "{{action:P02-request-review}}",
            "{{action:P02-run-review}}", "{{action:P02-run-work-commit}}",
            "{{action:P02-prove-and-push}}", "{{action:P02-record-receipt}}",
            "{{action:P02-stage-receipt}}", "{{action:P02-run-receipt-commit}}",
            "{{action:P02-check}}",
        )
        positions = [guide.index(marker) for marker in markers]
        self.assertEqual(positions, sorted(positions))


    def test_p02_patch_teaches_claimed_and_open_unresolved_counts(self) -> None:
        exercise_patch = (
            SOURCE / "academy/scenarios/P02-commit-review-pr/files/P02-worktree.patch"
        ).read_text(encoding="utf-8")

        self.assertIn('second["id"] = "RQ-102"', exercise_patch)
        self.assertNotIn('second["ticket_id"]', exercise_patch)
        self.assertIn('self.run_cli("claim", "RQ-102", "--volunteer", "Sam")', exercise_patch)
        self.assertIn(
            '{"claimed": 1, "completed": 0, "open": 1, "unresolved": 2}',
            exercise_patch,
        )


    def test_p02_patch_carries_the_attempt_local_gate_without_expanding_work_paths(self) -> None:
        """Catches an unpinned learner profile or a third learner work path."""
        exercise_patch = (
            SOURCE / "academy/scenarios/P02-commit-review-pr/files/P02-worktree.patch"
        ).read_text(encoding="utf-8")

        self.assertIn(
            "diff --git a/.codearbiter/tech-stack.md b/.codearbiter/tech-stack.md",
            exercise_patch,
        )
        learner_gate = exercise_patch.index("+### P02 learner commit gate")
        for preimage_context in (
            " evidence. Independent review remains required. `compileall` is syntax",
            " verification, not lint.",
            "-### Integration and release milestones",
        ):
            with self.subTest(preimage_context=preimage_context):
                self.assertIn(preimage_context, exercise_patch)
                self.assertLess(exercise_patch.index(preimage_context), learner_gate)
        self.assertIn("+### P02 learner commit gate", exercise_patch)
        self.assertIn("python -m unittest tests.test_cli -v", exercise_patch)
        self.assertIn(
            "python -m compileall -q workshop_queue tests/test_cli.py",
            exercise_patch,
        )
        self.assertIn("python scripts/scan_secrets.py --staged", exercise_patch)


    def test_p02_documents_the_bounded_gate_and_a_consistent_sixty_minute_pace(self) -> None:
        """Catches a learner schedule based on the multi-hour maintainer acceptance suite."""
        track = load_track(SOURCE, "practitioner")
        p02 = track.labs[1]
        guide = (
            SOURCE / "academy/tracks/practitioner/P02-commit-review-pr.md"
        ).read_text(encoding="utf-8")
        index = (
            SOURCE / "academy/tracks/practitioner/index.md"
        ).read_text(encoding="utf-8")

        self.assertEqual(p02.estimated_minutes, 60)
        self.assertIn("| P02 |", index)
        self.assertIn("| 60 minutes |", next(line for line in index.splitlines() if line.startswith("| P02 |")))
        self.assertIn("{{action:P02-run-work-commit}}", guide)
        self.assertIn("{{action:P02-run-receipt-commit}}", guide)
        self.assertIn("separate receipt-only commit", guide)
