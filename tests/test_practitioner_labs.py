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
        guide = (
            SOURCE / "academy/tracks/practitioner/P06-context-drift-recovery.md"
        ).read_text(encoding="utf-8")

        self.assertEqual(
            p06.host_commands,
            {
                "claude-code": "/ca:context-check",
                "codex": "$ca-context-check",
                "pi": "/ca-context-check",
            },
        )
        self.assertIn("`/skill:ca-context-check`", guide)
        for required in (
            "Workshop Queue report output is JSON-only.",
            "042746e43698e5d2a6de4c536f1024f893aef805",
            "5b41fb168a8b258cfae7eebc46e8b9ea7696ba56",
            "text is the default and JSON is optional",
            "Workshop Queue report output defaults to stable text and supports structured JSON with --format json.",
            "update only the provenance record's sole source hash to the prepared CLI object ID",
            "Commit exactly `.codearbiter/CONTEXT.md` and `.codearbiter/.provenance/CONTEXT.json` together.",
            "write the canonical v2 handoff",
            "commit only the handoff",
        ):
            with self.subTest(required=required):
                self.assertIn(required, guide)
        self.assertIn("`re-scout` is the sole permitted recovery route", guide)
        self.assertIn("does not prove that any host command was invoked", guide)
        self.assertNotIn("re-baseline", guide.casefold())
        self.assertNotIn("defer", guide.casefold())

        ordered_work = (
            "Read `.codearbiter/CONTEXT.md`",
            "select scoped `re-scout`",
            "Commit exactly `.codearbiter/CONTEXT.md` and `.codearbiter/.provenance/CONTEXT.json` together.",
            "write the canonical v2 handoff",
            "commit only the handoff",
            "arbiter-academy --repository $learnerRepository check P06-context-drift-recovery",
        )
        positions = [guide.index(marker) for marker in ordered_work]
        self.assertEqual(positions, sorted(positions))

    def test_p06_recovery_uses_archive_then_retry_without_destructive_commands(self) -> None:
        """Catches retry guidance that discards or rewrites the failed attempt."""
        recovery = load_track(SOURCE, "practitioner").labs[5].recovery

        self.assertIn(
            "arbiter-academy --repository $learnerRepository reset P06-context-drift-recovery",
            recovery,
        )
        self.assertIn("archives rather than discards the attempt", recovery)
        self.assertIn("failed branch remains available for diagnosis", recovery)
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

        self.assertEqual(p07.estimated_minutes, 30)
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
                    '/ca-threat-model "academy_engine/paths.py archive-import containment boundary"'
                ),
            },
        )
        ordered_headings = (
            "## Scope",
            "## STRIDE findings",
            "## Recommended controls before implementation",
            "## Clearance",
            "## Academy Target-SHA256/identity binding",
        )
        self.assertTrue(
            all(heading in guide for heading in ordered_headings),
            "P07 guide must expose the complete ordered learner report template.",
        )
        positions = [guide.index(heading) for heading in ordered_headings]
        self.assertEqual(positions, sorted(positions))
        for required in (
            "opt-in and read-only",
            "The check cannot prove that a host command was invoked",
            "Academy-Target-Prepared-Blob:",
            "Academy-Target-Head-Blob:",
            "CLEAR TO IMPLEMENT",
            "BLOCKED - resolve findings first",
            "- Keep destination resolution under the selected repository root before creating or copying a file.",
            "- Reject absolute, traversal, symlink, and Windows reparse-point ancestors in archive destinations.",
            "- Fail closed on a different drive or an unrepresentable containment path before any write.",
        ):
            with self.subTest(required=required):
                self.assertIn(required, guide)
        self.assertNotIn("proves that `$ca-threat-model`", guide)
        self.assertNotIn("native Academy", guide)

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
        guide = (
            SOURCE / "academy/tracks/practitioner/P07-threat-model.md"
        ).read_text(encoding="utf-8")
        recovery = guide[guide.index("## Recovery") : guide.index("## Next lab")]
        normalized_recovery = " ".join(recovery.split())

        self.assertIn(
            "arbiter-academy --repository $learnerRepository reset P07-threat-model",
            recovery,
        )
        self.assertIn("archives the failed attempt", normalized_recovery)
        self.assertIn("prepare an independent retry", normalized_recovery)
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


if __name__ == "__main__":
    unittest.main()
