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
from academy_engine.curriculum import CurriculumError, load_track, verify_track
from academy_engine.preview import load_preview_manifest
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
    def test_loader_rejects_repository_local_post_p02_practitioner_scenarios(self) -> None:
        """Preserved P02 records make a repository-local later transition noncanonical."""
        for lab_id in POST_P02_PRACTITIONER:
            with self.subTest(lab=lab_id), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                shutil.copytree(SOURCE / "academy", root / "academy")
                path = root / f"academy/tracks/practitioner/{lab_id}.md"
                text = path.read_text(encoding="utf-8")
                installed = (
                    "scenario_command: arbiter-academy --repository "
                    f"<learner-repository> prepare {lab_id}"
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
                    "arbiter-academy --repository <learner-repository> prepare "
                    + lab.id
                )
                self.assertEqual(lab.scenario_command, expected_prepare)
                guide = (
                    SOURCE / f"academy/tracks/practitioner/{lab.id}.md"
                ).read_text(encoding="utf-8")
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

    def test_post_p02_documented_transitions_dispatch_with_installed_authority(self) -> None:
        """The documented command shape must select the authoritative CLI route for prepare and reset."""
        try:
            track = load_track(SOURCE, "practitioner")
        except CurriculumError as error:
            self.fail(f"post-P02 source commands are not loadable: {error}")

        published = set(load_preview_manifest(SOURCE).available_labs)
        self.assertEqual(
            tuple(lab.id for lab in track.labs[2:] if lab.id in published),
            PRACTITIONER[2:5],
        )
        self.assertEqual(
            tuple(lab.id for lab in track.labs[2:] if lab.id not in published),
            PRACTITIONER[5:],
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

                if lab.id in published:
                    self.assertEqual(exit_code, 0)
                    validated.assert_called_once_with(SOURCE)
                    authoritative.assert_called_once_with(SOURCE)
                    transitioned.assert_called_once_with(
                        SOURCE,
                        lab.id,
                        installed_authority=True,
                    )
                else:
                    self.assertEqual(exit_code, 1)
                    self.assertEqual(
                        output.getvalue(),
                        f"error: {lab.id} is not available in Academy Preview 0.2\n",
                    )
                    validated.assert_not_called()
                    authoritative.assert_not_called()
                    transitioned.assert_not_called()

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
                next_section = guide_path.read_text(encoding="utf-8").partition(
                    "## Next lab"
                )[2]
                current_code = lab.id.partition("-")[0]
                next_code = lab.next_lab.partition("-")[0]
                with self.subTest(lab=lab.id, next_lab=lab.next_lab):
                    self.assertIn(
                        f"{next_code} is not available in Academy Preview 0.2.",
                        next_section,
                    )
                    self.assertNotIn(f"after {current_code} passes", next_section)

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

        self.assertIn(
            "arbiter-academy --repository $learnerRepository reset P02-commit-review-pr",
            track.labs[1].recovery,
        )
        self.assertNotIn(
            "arbiter-academy --repository <learner-repository> reset P02-commit-review-pr",
            track.labs[1].recovery,
        )
        self.assertNotIn("scripts/academy.py reset", track.labs[1].recovery)

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

    def test_p02_teaches_exact_identity_ref_and_two_commit_receipt_workflow(self) -> None:
        guide = (
            SOURCE / "academy/tracks/practitioner/P02-commit-review-pr.md"
        ).read_text(encoding="utf-8")

        for required in (
            "Origin repository ID: <64hex>",
            "Upstream repository ID: <64hex>",
            'git ls-remote origin "refs/heads/$branch"',
            'git ls-remote upstream "refs/heads/$branch"',
            "### Claude Code receipt commit\n\n```text\n/ca:commit\n```",
            "### Codex receipt commit\n\n```text\n$ca-commit\n```",
            "### Pi receipt commit\n\n```text\n/ca-commit\n```",
        ):
            with self.subTest(required=required):
                self.assertIn(required, guide)
        self.assertIn("logical receipt identities", guide)
        self.assertIn("not the temporary `file:` URLs", guide)

    def test_p02_workflow_orders_external_prepare_checkout_guards_and_two_commits(self) -> None:
        guide = (
            SOURCE / "academy/tracks/practitioner/P02-commit-review-pr.md"
        ).read_text(encoding="utf-8")
        markers = (
            "$prepareOutput = @(arbiter-academy --repository $learnerRepository prepare P02-commit-review-pr)",
            "$preparedCommit = $preparedMatch.Groups['commit'].Value",
            "$originRepositoryId = $originMatch.Groups['id'].Value",
            "Set-Location -LiteralPath $learnerRepository",
            "if ((git branch --show-current) -ne $branch)",
            "if ((git rev-parse HEAD) -ne $preparedCommit)",
            "git add -- tests/test_cli.py workshop_queue/cli.py",
            "$stagedWorkPaths = @(git diff --cached --name-only)",
            '/ca:review\n/ca:commit\n```',
            '$ca-review\n$ca-commit\n```',
            '/ca-review\n/ca-commit\n```',
            "$workHead = git rev-parse HEAD",
            "$commits = @(git rev-list --reverse \"$preparedCommit..$workHead\")",
            'git push origin "HEAD:refs/heads/$branch"',
            'git ls-remote origin "refs/heads/$branch"',
            'git ls-remote upstream "refs/heads/$branch"',
            "[IO.File]::WriteAllText($receiptPath",
            "git add -- .codearbiter/reports/academy/P02-pr-receipt.json",
            "$stagedReceiptPaths = @(git diff --cached --name-only)",
            "### Claude Code receipt commit\n\n```text\n/ca:commit\n```",
            "### Codex receipt commit\n\n```text\n$ca-commit\n```",
            "### Pi receipt commit\n\n```text\n/ca-commit\n```",
            "arbiter-academy --repository $learnerRepository check P02-commit-review-pr",
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
        self.assertIn("## 60-minute pacing guide", guide)
        for command in (
            "python -m unittest tests.test_cli -v",
            "python -m compileall -q workshop_queue tests/test_cli.py",
            "python scripts/scan_secrets.py --staged",
        ):
            self.assertIn(command, guide)
        self.assertIn("attempt-local", guide)
        self.assertIn(
            "Academy main keeps the full release verification profile",
            " ".join(guide.split()),
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
        self.assertEqual(report.matrix_cells, 80)
        self.assertNotIn(str(SOURCE), report.render())

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
            "P06 is not available in Academy Preview 0.2",
            "Keep your passing P05 evidence",
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
        self.assertIn("80 matrix cells", result.stdout)
        self.assertIn("structural", result.stdout.casefold())
        self.assertIn("checkpoints remain authoritative", result.stdout.casefold())
        self.assertNotIn("graduated", result.stdout.casefold())


if __name__ == "__main__":
    unittest.main()
