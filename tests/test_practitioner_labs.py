from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from academy_engine.curriculum import CurriculumError, load_track, verify_track


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
EXPECTED_HOST_ACTIONS = {
    PRACTITIONER[0]: ("feature", "task"),
    PRACTITIONER[1]: ("review", "commit"),
    PRACTITIONER[2]: ("adr",),
    PRACTITIONER[3]: ("add-dep",),
    PRACTITIONER[4]: ("checkpoint", "fix"),
    PRACTITIONER[5]: ("context-check",),
    PRACTITIONER[6]: ("threat-model",),
    PRACTITIONER[7]: ("standup",),
}


class PractitionerCurriculumTests(unittest.TestCase):
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
                self.assertEqual(
                    lab.checkpoint_command,
                    f"arbiter-academy --repository <learner-repository> check {lab.id}",
                )
                self.assertTrue(lab.success_evidence)
                self.assertIn("reset", lab.recovery.casefold())

    def test_p01_exposes_exact_feature_and_task_start_commands_for_each_host(self) -> None:
        """Catches a guide that describes task movement without a copyable sanctioned command."""
        p01 = load_track(SOURCE, "practitioner").labs[0]

        request = '"Show unresolved tickets in the Workshop Queue summary"'
        self.assertEqual(
            p01.host_commands,
            {
                "claude-code": (
                    f"/ca:feature {request}\n"
                    "/ca:task start academy.feature.0002"
                ),
                "codex": (
                    f"$ca-feature {request}\n"
                    "$ca-task start academy.feature.0002"
                ),
                "pi": (
                    f"/ca-feature {request}\n"
                    "/ca-task start academy.feature.0002"
                ),
            },
        )

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
                terminator = f"### Hint {number + 1}\n" if number < 3 else "## Success evidence\n"
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
            start = text.index("## Success evidence")
            end = text.index("## Recovery")
            path.write_text(
                text[:start] + "## Success evidence\n\n<!-- deliberately empty -->\n\n" + text[end:],
                encoding="utf-8",
            )

            with self.assertRaisesRegex(CurriculumError, "learner-visible content"):
                load_track(root, "practitioner")

    def test_verify_track_matrix_binds_exact_structural_inventory(self) -> None:
        """Catches a missing scenario/checkpoint binding or matrix declaration."""
        report = verify_track(SOURCE, "practitioner", matrix=True)

        self.assertTrue(report.passed, report.issues)
        self.assertEqual(report.lab_count, 8)
        self.assertEqual(report.matrix_cells, 40)
        self.assertNotIn(str(SOURCE), report.render())

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
        self.assertIn("40 matrix cells", result.stdout)
        self.assertIn("structural", result.stdout.casefold())
        self.assertIn("checkpoints remain authoritative", result.stdout.casefold())
        self.assertNotIn("graduated", result.stdout.casefold())


if __name__ == "__main__":
    unittest.main()
