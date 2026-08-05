import json
import hashlib
import os
import shutil
import tempfile
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

from academy_engine.checkpoints import (
    CheckpointError,
    LabContract,
    Predicate,
    _Attempt,
    _SemanticContext,
    _git_blob,
    _json,
    _raw_digest,
    _p01_spec_and_plan,
    _p01_criterion,
    _p01_board_transition,
    _p01_exact_repair,
    _p01_fixture_models,
    _p01_prepared_defect,
    _p01_source_identity,
    _semantic,
    _validate_prepare,
    evaluate_checkpoint,
    load_checkpoint,
    load_contracts,
)
from academy_engine.exercise_state import P08AttemptIdentity


class CheckpointTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "academy" / "checkpoints").mkdir(parents=True)
        (self.root / "academy" / "catalog.json").write_text('{"schema_version":1,"labs":[]}', encoding="utf-8")
        self.path = self.root / "academy" / "checkpoints" / "F01-fork-clone-doctor.json"
        self.write({"schema_version": 2, "id": "F01-fork-clone-doctor", "predicates": [{"id": "remote_and_doctor", "type": "lab_semantics", "profile": "remote_doctor", "artifact": ".codearbiter/reports/academy/F01-doctor.json"}]})

    def tearDown(self): self.temp.cleanup()

    def test_p01_spec_and_plan_reject_ambiguous_approval_and_scope_creep_variants(self):
        """Catches a P01 verifier that merely token-matches native feature artifacts."""
        spec = (
            "# Unresolved ticket report\n\n"
            "## Problem\nThe Workshop Queue JSON report lacks an unresolved count.\n\n"
            "## Scope\nJSON report behavior in workshop_queue/cli.py and verification in tests/test_cli.py only; "
            "exclude text-output changes, lifecycle changes, storage changes, dependencies, network behavior, credentials, and real personal data.\n\n"
            "## Acceptance criteria\n"
            "1. The JSON report adds integer unresolved equal to open + claimed.\n"
            "2. Existing integer open, claimed, and completed counts remain exact, and completed tickets do not contribute to unresolved.\n\n"
            "## Open questions\nNone.\n"
        )
        plan = (
            "# Academy feature plan\n\n"
            "## Acceptance criteria ledger\n"
            "- AC-01: The JSON report adds integer unresolved equal to open + claimed.\n"
            "- AC-02: Existing integer open, claimed, and completed counts remain exact, and completed tickets do not contribute to unresolved.\n\n"
            "## Tasks\n"
            "| ID | Path(s) | Verification | Maps to | Covers | Depends on | Status |\n"
            "| --- | --- | --- | --- | --- | --- | --- |\n"
            "| T-01 | tests/test_cli.py | focused unresolved-summary test | AC-01, AC-02 | AC-01, AC-02 | none | ACCEPTED |\n"
            "| T-02 | workshop_queue/cli.py | focused unresolved-summary test; python -m unittest discover -v; python -m compileall workshop_queue tests | AC-01, AC-02 | AC-01, AC-02 | T-01 | ACCEPTED |\n\n"
            "## MVP slice\nT-01 through T-02\n"
        )
        self.assertTrue(_p01_spec_and_plan(spec.encode(), plan.encode()))
        bad_specs = (
            spec.replace("open + claimed.", "open + claimed or open + completed."),
            spec.replace("open + claimed.", "open and claimed."),
            spec.replace("do not contribute to unresolved", "contribute to unresolved"),
            spec.replace("None.\n", "None.\nApproved by system at 2026-08-04.\n"),
            spec.replace(
                "The Workshop Queue JSON report lacks an unresolved count.",
                "The Workshop Queue JSON report lacks an unresolved count.\nStatus: approved 2026-08-04.",
            ),
            spec.replace(
                "The Workshop Queue JSON report lacks an unresolved count.",
                "The Workshop Queue JSON report lacks an unresolved count.\nApproval: granted by a system.",
            ),
            spec.replace(
                "The Workshop Queue JSON report lacks an unresolved count.",
                "The Workshop Queue JSON report lacks an unresolved count for learner@example.com.",
            ),
            spec.replace("2. Existing", "3. Existing"),
        )
        private_markers = (
            " https://learner:token@example.invalid/",
            " gh" + "p_aaaaaaaaaaaaaaaaaaaa",
            " -----BEGIN " + "PRIVATE KEY-----",
            " secret = 'academy-only'",
            r" C:\\Users\\learner\\private.txt",
            r" \\server\\share\\private.txt",
            " /private/path",
            " path=/private/data",
            " see (/private/data)",
            "\x01",
        )
        bad_specs += tuple(
            spec.replace(
                "The Workshop Queue JSON report lacks an unresolved count.",
                "The Workshop Queue JSON report lacks an unresolved count." + marker,
            )
            for marker in private_markers
        )
        bad_plans = (
            plan.replace(
                "## MVP slice\n",
                "| T-03 | README.md | python -m unittest discover -v | AC-01 | AC-01 | T-02 | ACCEPTED |\n\n## MVP slice\n",
            ),
            plan.replace("T-01 | tests/test_cli.py", "T-01 | tests/test_cli.py, README.md"),
            plan.replace("T-01 through T-02", "T-02 through T-01"),
            plan.replace(
                "| T-02 | workshop_queue/cli.py | focused unresolved-summary test; python -m unittest discover -v",
                "| T-02 | workshop_queue/cli.py | python -m unittest discover -v",
            ),
            plan.replace(
                "; python -m compileall workshop_queue tests",
                "; whoami; python -m compileall workshop_queue tests",
            ),
        )
        for bad_spec in bad_specs:
            with self.subTest(kind="spec"):
                self.assertFalse(_p01_spec_and_plan(bad_spec.encode(), plan.encode()))
        for bad_plan in bad_plans:
            with self.subTest(kind="plan"):
                self.assertFalse(_p01_spec_and_plan(spec.encode(), bad_plan.encode()))

    def test_p01_frozen_model_requires_the_prepared_no_unresolved_defect(self):
        """Catches a P01 proof that accepts a regression already green before the repair."""
        source = Path(__file__).resolve().parents[1]
        fixture = (source / "academy/scenarios/P01-feature-through-plan/files/p01-unresolved-tickets.json").read_bytes()
        cli = (source / "workshop_queue/cli.py").read_bytes()
        prepared, intended = _p01_fixture_models(fixture)
        expected = {"open": 1, "claimed": 1, "completed": 1, "unresolved": 2}
        self.assertEqual(prepared, {"open": 1, "claimed": 1, "completed": 1})
        self.assertNotEqual(prepared, expected)
        self.assertEqual(intended, expected)
        self.assertTrue(_p01_prepared_defect(cli))

        redundant = cli.replace(
            b"    if output_format == \"json\":\n",
            b"    counts['unresolved'] = counts[TicketStatus.OPEN.value] + counts[TicketStatus.CLAIMED.value]\n    if output_format == \"json\":\n",
        )
        duplicate_status = fixture.replace(b'"status":"claimed"', b'"status":"open"')
        invalid_lifecycle = fixture.replace(b'"claimed_by":"Academy Volunteer"', b'"claimed_by":null')
        private_description = fixture.replace(
            b'"description":"Fictional Academy ticket."',
            b'"description":"Contact learner@example.com for this fictional ticket."',
            1,
        )
        invalid_chronology = fixture.replace(
            b'"completed_at":"2026-08-01T09:25:00Z"',
            b'"completed_at":"2026-08-01T09:00:00Z"',
        )
        invalid_calendar_time = fixture.replace(
            b'"created_at":"2026-08-01T09:00:00Z"',
            b'"created_at":"2026-02-30T09:00:00Z"',
        )
        private_fixtures = tuple(
            fixture.replace(
                b'"description":"Fictional Academy ticket."',
                f'"description":"{marker}"'.encode("utf-8"),
                1,
            )
            for marker in (
                "gh" + "p_aaaaaaaaaaaaaaaaaaaa",
                "secret = academy-only",
                r"C:\\private\\ticket.txt",
            )
        )
        self.assertFalse(_p01_prepared_defect(redundant))
        for candidate in (
            duplicate_status,
            invalid_lifecycle,
            private_description,
            invalid_chronology,
            invalid_calendar_time,
            *private_fixtures,
        ):
            with self.subTest(fixture=candidate):
                self.assertIsNone(_p01_fixture_models(candidate))

    def test_p01_source_identity_is_typed_private_and_exact(self):
        """Catches source identity comparisons where Python bools satisfy integer fields."""
        source = Path(__file__).resolve().parents[1]
        identity = json.loads(
            (source / "academy/scenarios/P01-feature-through-plan/files/codearbiter-source.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertTrue(_p01_source_identity(identity))
        for mutation in (
            {**identity, "schema_version": True},
            {**identity, "repository": "learner@example.com"},
        ):
            with self.subTest(mutation=mutation):
                self.assertFalse(_p01_source_identity(mutation))

    def test_p01_board_transition_returns_false_when_line_counts_differ(self):
        """Catches a strict zip exception escaping a malformed board comparison."""
        attempt = _Attempt("academy/P01-feature-through-plan/1", 1, "prepared", "base", "head")
        with mock.patch(
            "academy_engine.checkpoints._p01_regular_blob",
            side_effect=(
                b"- [ ] academy.feature.0002 - Show unresolved tickets in the summary\n",
                b"- [~] academy.feature.0002 - Show unresolved tickets in the summary  (started 2026-08-04)\nextra\n",
            ),
        ):
            self.assertFalse(
                _p01_board_transition(
                    self.root,
                    attempt,
                    ".codearbiter/open-tasks.md",
                    "academy.feature.0002",
                )
            )

    def test_p01_criteria_require_the_actual_formula_and_completed_exclusion(self):
        """Catches a criterion parser that accepts a semantic inversion by token presence."""
        self.assertTrue(
            _p01_criterion(
                "The JSON report adds integer unresolved equal to open + claimed.",
                first=True,
            )
        )
        self.assertTrue(
            _p01_criterion(
                "Existing integer open, claimed, and completed counts remain exact, and completed tickets do not contribute to unresolved.",
                first=False,
            )
        )
        self.assertFalse(
            _p01_criterion(
                "The JSON report adds integer unresolved equal to open and claimed.",
                first=True,
            )
        )
        self.assertFalse(
            _p01_criterion(
                "Existing integer open, claimed, and completed counts remain exact, and completed tickets contribute to unresolved.",
                first=False,
            )
        )

    def test_p01_repair_must_follow_the_status_count_comprehension(self):
        """Catches a syntactically exact assignment placed after JSON output or return."""
        source = Path(__file__).resolve().parents[1]
        prepared = (source / "workshop_queue/cli.py").read_bytes()
        assignment = (
            b"    counts['unresolved'] = (\n"
            b"        counts[TicketStatus.OPEN.value]\n"
            b"        + counts[TicketStatus.CLAIMED.value]\n"
            b"    )\n"
        )
        count_to_json = (
            b"    counts = {status.value: sum(ticket.status is status for ticket in tickets) for status in TicketStatus}\n"
            b'    if output_format == "json":\n'
        )
        correct = prepared.replace(
            count_to_json,
            count_to_json.removesuffix(b'    if output_format == "json":\n')
            + assignment
            + b'    if output_format == "json":\n',
        )
        after_json = prepared.replace(
            b"    for status in TicketStatus:\n",
            assignment + b"    for status in TicketStatus:\n",
        )
        self.assertTrue(_p01_exact_repair(prepared, correct))
        self.assertFalse(_p01_exact_repair(prepared, after_json))

    def test_p08_authenticated_profile_proves_authority_before_external_checkpoint(self):
        attempt = _Attempt(
            "academy/P08-repository-hygiene/1", 1, "a" * 40, "b" * 40, "c" * 40
        )
        predicate = Predicate("live_ref_hygiene", "lab_semantics", {"profile": "p08_authenticated"})
        context = _SemanticContext(self.root, attempt, predicate)
        store, authority = mock.Mock(), mock.Mock()

        sequence = mock.Mock()
        with mock.patch(
            "academy_engine.checkpoints.preflight_p08",
            return_value=("b" * 40, mock.Mock(), authority),
        ) as preflight, mock.patch(
            "academy_engine.checkpoints.open_p08_store", return_value=store
        ) as opened, mock.patch(
            "academy_engine.checkpoints.validate_p08_checkpoint", return_value=True
        ) as verified:
            sequence.attach_mock(preflight, "preflight")
            sequence.attach_mock(opened, "opened")
            sequence.attach_mock(verified, "verified")
            self.assertTrue(_semantic(context))

        preflight.assert_called_once_with(self.root)
        opened.assert_called_once_with(self.root, base="b" * 40, authority=authority)
        identity = P08AttemptIdentity(1, attempt.branch, attempt.prepared, attempt.head)
        verified.assert_called_once_with(self.root, store, identity)
        self.assertEqual(
            sequence.mock_calls,
            [
                mock.call.preflight(self.root),
                mock.call.opened(self.root, base="b" * 40, authority=authority),
                mock.call.verified(self.root, store, identity),
            ],
        )

    def write(self, value): self.path.write_text(json.dumps(value), encoding="utf-8")

    def test_p02_prepare_requires_the_exact_patch_derived_learner_profile(self):
        source = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            installed_data = root / "installed-data"
            installed = installed_data / "share/arbiter-academy/academy"
            installed.parent.mkdir(parents=True)
            shutil.copytree(source / "academy", installed)
            shutil.copytree(source / "academy", root / "academy")
            scenario_root = root / "academy/scenarios/P02-commit-review-pr"
            profile = root / ".codearbiter/tech-stack.md"
            profile.parent.mkdir(parents=True)
            shutil.copy2(source / ".codearbiter/tech-stack.md", profile)
            subprocess.run(["git", "init", "-b", "main"], cwd=root, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.name", "Fixture"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.email", "fixture@example.invalid"], cwd=root, check=True)
            subprocess.run(["git", "add", "."], cwd=root, check=True)
            subprocess.run(["git", "commit", "-m", "base"], cwd=root, check=True, capture_output=True)
            base = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True).stdout.strip()
            contract = LabContract(
                "P02-commit-review-pr",
                "Commit, review, and PR",
                "academy/tracks/practitioner/P02-commit-review-pr.md",
                "academy/checkpoints/P02-commit-review-pr.json",
                "training_scenarios/P02-commit-review-pr.json",
            )

            def prepare(kind: str) -> _Attempt:
                subprocess.run(["git", "switch", "--detach", base], cwd=root, check=True, capture_output=True)
                destination = root / contract.scenario_path
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(scenario_root / "files/scenario.json", destination)
                if kind != "missing":
                    subprocess.run(
                        [
                            "git",
                            "apply",
                            "--include=.codearbiter/tech-stack.md",
                            "--",
                            "academy/scenarios/P02-commit-review-pr/files/P02-worktree.patch",
                        ],
                        cwd=root,
                        check=True,
                        capture_output=True,
                    )
                if kind == "wrong":
                    profile.write_text("# unverified learner profile\n", encoding="utf-8")
                if kind == "extra":
                    (root / "unexpected.txt").write_text("extra\n", encoding="utf-8")
                subprocess.run(["git", "add", "."], cwd=root, check=True)
                subprocess.run(
                    ["git", "commit", "-m", "academy: prepare P02-commit-review-pr attempt 1"],
                    cwd=root,
                    check=True,
                    capture_output=True,
                )
                prepared = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True).stdout.strip()
                return _Attempt("academy/P02-commit-review-pr/1", 1, prepared, base, prepared)

            with mock.patch(
                "academy_engine.exercise_state.sysconfig.get_path",
                return_value=str(installed_data),
            ):
                self.assertTrue(_validate_prepare(root, contract, prepare("exact")))
                for kind in ("missing", "wrong", "extra"):
                    with self.subTest(kind=kind):
                        self.assertFalse(_validate_prepare(root, contract, prepare(kind)))

    def test_non_p02_prepare_remains_manifest_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            files = root / "academy/scenarios/F99-control/files"
            files.mkdir(parents=True)
            (files / "scenario.json").write_text('{"control":true}\n', encoding="utf-8")
            (files.parent / "manifest.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "id": "F99-control",
                        "files": [
                            {
                                "source": "scenario.json",
                                "destination": "training_scenarios/F99-control.json",
                            }
                        ],
                        "removals": [],
                        "starting_task": "F99",
                        "checkpoint": "academy/checkpoints/F99-control.json",
                        "requires_push_safe_setup": False,
                    }
                ),
                encoding="utf-8",
            )
            subprocess.run(["git", "init", "-b", "main"], cwd=root, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.name", "Fixture"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.email", "fixture@example.invalid"], cwd=root, check=True)
            subprocess.run(["git", "add", "."], cwd=root, check=True)
            subprocess.run(["git", "commit", "-m", "base"], cwd=root, check=True, capture_output=True)
            base = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True).stdout.strip()
            destination = root / "training_scenarios/F99-control.json"
            destination.parent.mkdir()
            shutil.copy2(files / "scenario.json", destination)
            subprocess.run(["git", "add", "."], cwd=root, check=True)
            subprocess.run(["git", "commit", "-m", "prepare"], cwd=root, check=True, capture_output=True)
            prepared = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True).stdout.strip()
            contract = LabContract("F99-control", "Control", "guide.md", "checkpoint.json", "training_scenarios/F99-control.json")
            attempt = _Attempt("academy/F99-control/1", 1, prepared, base, prepared)

            self.assertTrue(_validate_prepare(root, contract, attempt))

    def test_p02_semantics_use_external_state_and_strict_offline_receipt(self):
        attempt = _Attempt(
            "academy/P02-commit-review-pr/1",
            1,
            "b" * 40,
            "a" * 40,
            "c" * 40,
        )
        predicate = Predicate(
            "review_pr_commit_range",
            "lab_semantics",
            {
                "profile": "pr_receipt",
                "receipt": ".codearbiter/reports/academy/P02-pr-receipt.json",
            },
        )
        context = _SemanticContext(self.root, attempt, predicate)
        receipt = {"strict": "offline"}
        store = object()

        with mock.patch(
            "academy_engine.checkpoints._git_blob", return_value=b"receipt-bytes"
        ), mock.patch(
            "academy_engine.checkpoints.open_existing_p02_store", return_value=store
        ) as opened, mock.patch(
            "academy_engine.checkpoints._parse_p02_receipt_bytes", return_value=receipt
        ) as parsed, mock.patch(
            "academy_engine.checkpoints.validate_p02_checkpoint", return_value=True
        ) as validated:
            self.assertTrue(_semantic(context))

        opened.assert_called_once_with(self.root, base=attempt.base)
        parsed.assert_called_once_with(b"receipt-bytes", object_format="sha1")
        validated.assert_called_once()

    def test_untouched_partial_and_wrong_value_fail_closed(self):
        for label, contents in (("untouched", None), ("partial", ""), ("wrong", "wrong")):
            with self.subTest(label=label):
                target = self.root / ".codearbiter" / "specs" / "proof.md"
                if contents is not None:
                    target.parent.mkdir(parents=True, exist_ok=True); target.write_text(contents, encoding="utf-8")
                result = evaluate_checkpoint(self.root, "F01-fork-clone-doctor")
                self.assertFalse(result.passed)

    def test_passing_command_does_not_replace_missing_governed_artifact(self):
        self.write({"schema_version": 2, "id": "F01-fork-clone-doctor", "predicates": [{"id": "remote_and_doctor", "type": "lab_semantics", "profile": "remote_doctor", "artifact": ".codearbiter/reports/academy/F01-doctor.json"}]})
        self.assertFalse(evaluate_checkpoint(self.root, "F01-fork-clone-doctor").passed)

    def test_definition_rejects_unknown_unsafe_and_unbounded_values(self):
        for predicate in (
            {"id":"x","type":"unknown"},
            {"id":"x","type":"lab_semantics","profile":"remote_doctor","artifact":"../private"},
            {"id":"x","type":"lab_semantics","profile":"remote_doctor","artifact":".codearbiter/report.json","timeout_seconds":999},
        ):
            with self.subTest(predicate=predicate):
                self.write({"schema_version":2,"id":"F01-fork-clone-doctor","predicates":[predicate]})
                with self.assertRaises(CheckpointError): load_checkpoint(self.path)
        self.write({"schema_version":1,"id":"F01-fork-clone-doctor","predicates":[{"id":"x","type":"file_exists","path":"proof"}]})
        with self.assertRaises(CheckpointError):
            load_checkpoint(self.path)

    def test_wrong_branch_fails_recomputed_git_evidence(self):
        subprocess.run(["git", "init"], cwd=self.root, check=True, capture_output=True, text=True)
        subprocess.run(["git", "switch", "-c", "wrong-branch"], cwd=self.root, check=True, capture_output=True, text=True)
        self.write({"schema_version":2,"id":"F01-fork-clone-doctor","predicates":[{"id":"remote_and_doctor","type":"lab_semantics","profile":"remote_doctor","artifact":".codearbiter/reports/academy/F01-doctor.json"}]})
        self.assertFalse(evaluate_checkpoint(self.root, "F01-fork-clone-doctor").passed)

    def test_p06_rejects_a_nonexistent_preserved_path(self):
        subprocess.run(["git", "init", "-b", "main"], cwd=self.root, check=True, capture_output=True, text=True)
        subprocess.run(["git", "config", "user.name", "Fixture"], cwd=self.root, check=True, capture_output=True, text=True)
        subprocess.run(["git", "config", "user.email", "fixture@example.invalid"], cwd=self.root, check=True, capture_output=True, text=True)
        context_path = self.root / ".codearbiter" / "CONTEXT.md"
        context_path.parent.mkdir(parents=True)
        context_path.write_text("stage: 1\n", encoding="utf-8")
        preserved_path = self.root / "docs" / "preserved.txt"
        preserved_path.parent.mkdir(parents=True)
        preserved_path.write_text("preserve this\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=self.root, check=True, capture_output=True, text=True)
        subprocess.run(["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-m", "base"], cwd=self.root, check=True, capture_output=True, text=True)
        base = subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.root, check=True, capture_output=True, text=True).stdout.strip()
        subprocess.run(["git", "commit", "--allow-empty", "-m", "prepare"], cwd=self.root, check=True, capture_output=True, text=True)
        prepared = subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.root, check=True, capture_output=True, text=True).stdout.strip()
        before_blob_at_prepare = _git_blob(self.root, prepared, ".codearbiter/CONTEXT.md")
        self.assertIsNotNone(before_blob_at_prepare)
        context_path.write_text("stage: 2\n", encoding="utf-8")
        subprocess.run(["git", "add", str(context_path.relative_to(self.root))], cwd=self.root, check=True, capture_output=True, text=True)
        subprocess.run(["git", "commit", "-m", "recover context"], cwd=self.root, check=True, capture_output=True, text=True)
        recovery_commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.root, check=True, capture_output=True, text=True).stdout.strip()
        after_blob_at_recovery = _git_blob(self.root, recovery_commit, ".codearbiter/CONTEXT.md")
        self.assertIsNotNone(after_blob_at_recovery)
        handoff = self.root / ".codearbiter" / "reports" / "academy" / "P06-recovery.json"
        handoff.parent.mkdir(parents=True)
        handoff.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "context_before_sha256": _raw_digest(before_blob_at_prepare),
                    "context_after_sha256": _raw_digest(after_blob_at_recovery),
                    "preserved_path": "docs/preserved.txt",
                }
            ),
            encoding="utf-8",
        )
        subprocess.run(["git", "add", "."], cwd=self.root, check=True, capture_output=True, text=True)
        subprocess.run(["git", "commit", "-m", "record recovery handoff"], cwd=self.root, check=True, capture_output=True, text=True)
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.root, check=True, capture_output=True, text=True).stdout.strip()
        predicate = Predicate(
            "provenance_drift_recovery",
            "lab_semantics",
            {
                "profile": "provenance_recovery",
                "context": ".codearbiter/CONTEXT.md",
                "handoff": ".codearbiter/reports/academy/P06-recovery.json",
            },
        )
        attempt = _Attempt("academy/P06-context-drift-recovery/1", 1, prepared, base, head)
        handoff_data = _json(self.root, head, ".codearbiter/reports/academy/P06-recovery.json")
        before_blob = _git_blob(self.root, prepared, ".codearbiter/CONTEXT.md")
        after_blob = _git_blob(self.root, head, ".codearbiter/CONTEXT.md")
        self.assertIsNotNone(handoff_data)
        self.assertIsNotNone(before_blob)
        self.assertIsNotNone(after_blob)
        self.assertEqual(handoff_data["context_before_sha256"], _raw_digest(before_blob))
        self.assertEqual(handoff_data["context_after_sha256"], _raw_digest(after_blob))
        self.assertEqual(
            _git_blob(self.root, prepared, "docs/preserved.txt"),
            _git_blob(self.root, head, "docs/preserved.txt"),
        )
        self.assertTrue(_semantic(_SemanticContext(self.root, attempt, predicate)))
        payload = json.loads(handoff.read_text(encoding="utf-8"))
        payload["preserved_path"] = "missing/preserved.txt"
        handoff.write_text(json.dumps(payload), encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=self.root, check=True, capture_output=True, text=True)
        subprocess.run(["git", "commit", "-m", "claim missing preservation"], cwd=self.root, check=True, capture_output=True, text=True)
        forged_head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.root, check=True, capture_output=True, text=True).stdout.strip()
        forged = _Attempt("academy/P06-context-drift-recovery/1", 1, prepared, base, forged_head)
        self.assertFalse(_semantic(_SemanticContext(self.root, forged, predicate)))

    def test_p05_rejects_finding_and_remediation_commits_before_prepare(self):
        subprocess.run(["git", "init", "-b", "main"], cwd=self.root, check=True, capture_output=True, text=True)
        subprocess.run(["git", "config", "user.name", "Fixture"], cwd=self.root, check=True, capture_output=True, text=True)
        subprocess.run(["git", "config", "user.email", "fixture@example.invalid"], cwd=self.root, check=True, capture_output=True, text=True)
        paths = ("workshop_queue/service.py", "tests/test_service.py")
        seed = self.root / "README.md"
        seed.write_text("seed\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=self.root, check=True, capture_output=True, text=True)
        subprocess.run(["git", "commit", "-m", "seed"], cwd=self.root, check=True, capture_output=True, text=True)
        for path in paths:
            target = self.root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("finding\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=self.root, check=True, capture_output=True, text=True)
        subprocess.run(["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-m", "historical finding"], cwd=self.root, check=True, capture_output=True, text=True)
        finding = subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.root, check=True, capture_output=True, text=True).stdout.strip()
        for path in paths:
            (self.root / path).write_text("historical remediation\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=self.root, check=True, capture_output=True, text=True)
        subprocess.run(["git", "commit", "-m", "historical remediation"], cwd=self.root, check=True, capture_output=True, text=True)
        remediation = subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.root, check=True, capture_output=True, text=True).stdout.strip()
        subprocess.run(["git", "commit", "--allow-empty", "-m", "prepare"], cwd=self.root, check=True, capture_output=True, text=True)
        prepared = subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.root, check=True, capture_output=True, text=True).stdout.strip()
        for path in paths:
            (self.root / path).write_text("learner edit\n", encoding="utf-8")
        report = self.root / ".codearbiter" / "checkpoints" / "P05-academy.json"
        report.parent.mkdir(parents=True)
        report.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "finding_id": "ACADEMY-P05",
                    "finding_commit": finding,
                    "remediation_commit": remediation,
                    "paths": list(paths),
                    "status": "remediated",
                }
            ),
            encoding="utf-8",
        )
        subprocess.run(["git", "add", "."], cwd=self.root, check=True, capture_output=True, text=True)
        subprocess.run(["git", "commit", "-m", "claim old remediation"], cwd=self.root, check=True, capture_output=True, text=True)
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.root, check=True, capture_output=True, text=True).stdout.strip()
        predicate = Predicate(
            "finding_remediation_link",
            "lab_semantics",
            {"profile": "checkpoint_remediation", "report": ".codearbiter/checkpoints/P05-academy.json"},
        )
        attempt = _Attempt("academy/P05-checkpoint-remediation/1", 1, prepared, remediation, head)
        self.assertFalse(_semantic(_SemanticContext(self.root, attempt, predicate)))

    def test_contract_loader_rejects_duplicate_and_boolean_schema_versions(self):
        source = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copytree(source / "academy", root / "academy")
            path = root / "academy" / "contracts.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["contracts"].append(payload["contracts"][0])
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(CheckpointError):
                load_contracts(root)
            payload["contracts"].pop()
            payload["schema_version"] = True
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(CheckpointError):
                load_contracts(root)
            shutil.copyfile(source / "academy" / "contracts.json", path)
            checkpoint = root / "academy" / "checkpoints" / "F01-fork-clone-doctor.json"
            checkpoint.write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "id": "F01-fork-clone-doctor",
                        "predicates": [
                            {
                                "id": "live_context_orientation",
                                "type": "lab_semantics",
                                "profile": "orientation",
                                "artifact": ".codearbiter/reports/academy/F02-orientation.json",
                                "context": ".codearbiter/CONTEXT.md",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(CheckpointError, "noncanonical"):
                load_contracts(root)

    def test_generic_one_commit_answers_without_remotes_do_not_pass(self):
        source = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "repo"
            root.mkdir()
            shutil.copytree(source / "academy", root / "academy")
            shutil.copytree(source / "academy_engine", root / "academy_engine")
            shutil.copytree(source / "scripts", root / "scripts")
            shutil.copytree(source / ".codearbiter", root / ".codearbiter")
            shutil.copytree(source / "workshop_queue", root / "workshop_queue")
            subprocess.run(["git", "init", "-b", "main"], cwd=root, check=True, capture_output=True, text=True)
            subprocess.run(
                ["git", "add", "-f", "academy", "academy_engine", "scripts", ".codearbiter"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-m", "base"], cwd=root, check=True, capture_output=True, text=True)
            lab_id = "F01-fork-clone-doctor"
            subprocess.run(["git", "switch", "-c", f"academy/{lab_id}/1"], cwd=root, check=True, capture_output=True, text=True)
            scenario = root / "training_scenarios" / f"{lab_id}.json"
            scenario.parent.mkdir(parents=True)
            shutil.copyfile(
                root / "academy" / "scenarios" / lab_id / "files" / "scenario.json",
                scenario,
            )
            subprocess.run(["git", "add", str(scenario.relative_to(root))], cwd=root, check=True, capture_output=True, text=True)
            subprocess.run(["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-m", f"academy: prepare {lab_id} attempt 1"], cwd=root, check=True, capture_output=True, text=True)
            for item in json.loads((root / "academy" / "contracts.json").read_text(encoding="utf-8"))["contracts"]:
                for name, payload in (
                    ("outcome.json", {"lab_id": item["id"], "status": "completed"}),
                    ("governed.json", {"lab_id": item["id"], "status": "governed"}),
                ):
                    path = root / ".academy" / "work" / item["id"] / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(json.dumps(payload), encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=root, check=True, capture_output=True, text=True)
            subprocess.run(["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-m", "all answers"], cwd=root, check=True, capture_output=True, text=True)
            self.assertFalse(evaluate_checkpoint(root, lab_id).passed)

    def test_current_semantic_attempt_two_is_selected_and_bound_to_its_head(self):
        source = Path(__file__).resolve().parents[1]
        lab_id = "F02-orient-to-state"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "repo"
            root.mkdir()
            shutil.copytree(source / "academy", root / "academy")
            shutil.copytree(source / "academy_engine", root / "academy_engine")
            shutil.copytree(source / "scripts", root / "scripts")
            shutil.copytree(source / ".codearbiter", root / ".codearbiter")
            track = root / "academy" / "tracks" / "foundations"
            track.mkdir(parents=True, exist_ok=True)
            (track / f"{lab_id}.md").write_text("# Orientation lab\n", encoding="utf-8")
            subprocess.run(["git", "init", "-b", "main"], cwd=root, check=True, capture_output=True, text=True)
            subprocess.run(
                ["git", "add", "-f", "academy", "academy_engine", "scripts", ".codearbiter"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-m", "base"], cwd=root, check=True, capture_output=True, text=True)
            for attempt in (1, 2):
                subprocess.run(["git", "switch", "-c", f"academy/{lab_id}/{attempt}", "main"], cwd=root, check=True, capture_output=True, text=True)
                prepared = root / "training_scenarios" / f"{lab_id}.json"
                prepared.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(
                    root / "academy" / "scenarios" / lab_id / "files" / "scenario.json",
                    prepared,
                )
                subprocess.run(["git", "add", str(prepared.relative_to(root))], cwd=root, check=True, capture_output=True, text=True)
                subprocess.run(["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-m", f"academy: prepare {lab_id} attempt {attempt}"], cwd=root, check=True, capture_output=True, text=True)
                if attempt == 1:
                    subprocess.run(["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "--allow-empty", "-m", "incomplete"], cwd=root, check=True, capture_output=True, text=True)
                    subprocess.run(["git", "switch", "main"], cwd=root, check=True, capture_output=True, text=True)
                    continue
                context = (root / ".codearbiter" / "CONTEXT.md").read_bytes()
                artifact = root / ".codearbiter" / "reports" / "academy" / "F02-orientation.json"
                artifact.parent.mkdir(parents=True, exist_ok=True)
                artifact.write_text(
                    json.dumps(
                        {
                            "schema_version": 1,
                            "context_path": ".codearbiter/CONTEXT.md",
                            "context_sha256": hashlib.sha256(context).hexdigest(),
                            "stage": 2,
                        }
                    ),
                    encoding="utf-8",
                )
                subprocess.run(["git", "add", str(artifact.relative_to(root))], cwd=root, check=True, capture_output=True, text=True)
                subprocess.run(["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-m", "record live context orientation"], cwd=root, check=True, capture_output=True, text=True)
            result = evaluate_checkpoint(root, lab_id)
            self.assertTrue(result.passed, result.failed_predicates)
            self.assertEqual(result.attempt, f"academy/{lab_id}/2")
            self.assertEqual(
                result.head_commit,
                subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True).stdout.strip(),
            )
            checked = subprocess.run(
                [
                    sys.executable,
                    str(source / "scripts" / "academy.py"),
                    "--repository",
                    str(root),
                    "check",
                    lab_id,
                ],
                cwd=root,
                capture_output=True,
                text=True,
            )
            self.assertEqual(checked.returncode, 0, checked.stderr)
            progress = json.loads((root / ".academy" / "progress.json").read_text(encoding="utf-8"))
            self.assertEqual(progress["checkpoints"][0]["attempt"], f"academy/{lab_id}/2")
            added_verifier = root / "academy_engine" / "benign_extension.py"
            added_verifier.write_text("# benign but unreviewed verifier extension\n", encoding="utf-8")
            subprocess.run(["git", "add", str(added_verifier.relative_to(root))], cwd=root, check=True, capture_output=True, text=True)
            subprocess.run(["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-m", "add verifier extension"], cwd=root, check=True, capture_output=True, text=True)
            extended_verifier = evaluate_checkpoint(root, lab_id)
            self.assertFalse(extended_verifier.passed)
            self.assertIn("source_integrity", extended_verifier.failed_predicates)
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=Fixture",
                    "-c",
                    "user.email=fixture@example.invalid",
                    "revert",
                    "--no-edit",
                    "HEAD",
                ],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )
            restored_baseline = evaluate_checkpoint(root, lab_id)
            self.assertTrue(restored_baseline.passed, restored_baseline.failed_predicates)
            remotes_path = root / "academy_engine" / "remotes.py"
            remotes_original = remotes_path.read_bytes()
            remotes_path.write_bytes(remotes_original + b"\n# verifier substitution\n")
            substituted_verifier = evaluate_checkpoint(root, lab_id)
            self.assertFalse(substituted_verifier.passed)
            self.assertIn("source_integrity", substituted_verifier.failed_predicates)
            remotes_path.write_bytes(remotes_original)
            restored_baseline = evaluate_checkpoint(root, lab_id)
            self.assertTrue(restored_baseline.passed, restored_baseline.failed_predicates)
            checkpoint_path = root / "academy" / "checkpoints" / f"{lab_id}.json"
            checkpoint_original = checkpoint_path.read_bytes()
            checkpoint_path.write_text(
                checkpoint_path.read_text(encoding="utf-8") + "\n",
                encoding="utf-8",
            )
            substituted = evaluate_checkpoint(root, lab_id)
            self.assertFalse(substituted.passed)
            self.assertIn("source_integrity", substituted.failed_predicates)
            checkpoint_path.write_bytes(checkpoint_original)
            restored_baseline = evaluate_checkpoint(root, lab_id)
            self.assertTrue(restored_baseline.passed, restored_baseline.failed_predicates)
            subprocess.run(
                ["git", "switch", "-c", "alternate-rules"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )
            checkpoint_path.write_bytes(checkpoint_original + b"\n")
            subprocess.run(
                ["git", "add", str(checkpoint_path.relative_to(root))],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=Fixture",
                    "-c",
                    "user.email=fixture@example.invalid",
                    "commit",
                    "-m",
                    "alternate checkpoint rules",
                ],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )
            clean_alternate = evaluate_checkpoint(root, lab_id)
            self.assertFalse(clean_alternate.passed)
            self.assertIn("source_integrity", clean_alternate.failed_predicates)


class P03NativeEvidenceTests(unittest.TestCase):
    """Exercise the P03 evidence predicate against immutable, real Git history."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        subprocess.run(["git", "init", "-b", "main"], cwd=self.root, check=True, capture_output=True, text=True)
        subprocess.run(["git", "config", "user.name", "Ada Learner"], cwd=self.root, check=True)
        subprocess.run(["git", "config", "user.email", "p03-private-canary" + "@example.invalid"], cwd=self.root, check=True)
        log = self.root / ".codearbiter/decisions/decision-log.md"
        log.parent.mkdir(parents=True)
        log.write_text("# Decision log\n\n", encoding="utf-8")
        (self.root / ".codearbiter/decisions/0003-verifier-trust.md").write_text("# ADR-0003\n", encoding="utf-8")
        (self.root / "README.md").write_text("base\n", encoding="utf-8")
        self._commit("base")
        subprocess.run(["git", "switch", "-c", "academy/P03-record-an-adr/1"], cwd=self.root, check=True, capture_output=True, text=True)
        self._commit("academy: prepare P03-record-an-adr attempt 1", empty=True)
        self.prepared = self._head()
        self._write_valid_evidence("Ada Learner")
        self._commit("record decision")
        self.head = self._head()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _head(self) -> str:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.root, check=True, capture_output=True, text=True).stdout.strip()

    def _commit(self, message: str, *, empty: bool = False) -> None:
        subprocess.run(["git", "add", "-A"], cwd=self.root, check=True, capture_output=True, text=True)
        command = ["git", "commit", "-m", message]
        if empty:
            command.insert(2, "--allow-empty")
        environment = os.environ.copy()
        environment["GIT_AUTHOR_DATE"] = "2026-08-04T12:00:00-04:00"
        environment["GIT_COMMITTER_DATE"] = "2026-08-04T12:00:00-04:00"
        subprocess.run(command, cwd=self.root, env=environment, check=True, capture_output=True, text=True)

    def _write_valid_evidence(self, name: str) -> None:
        date = subprocess.run(["git", "show", "-s", "--format=%aI", "HEAD"], cwd=self.root, check=True, capture_output=True, text=True).stdout[:10]
        adr = self.root / ".codearbiter/decisions/0004-academy-lab.md"
        adr.write_text(
            "---\nstatus: accepted\ndate: " + date + "\ntitle: Choose the Workshop Queue summary-format boundary\n"
            + "decided-by: " + name + "\nsupersedes: none\ngoverns: workshop_queue/cli.py\n---\n\n"
            + "# ADR-0004 — Choose the Workshop Queue summary-format boundary\n\n## Status\n\nAccepted\n\n"
            + "## Context\n\nStable text supports people; structured JSON supports automation.\n\n## Decision\n\n"
            + "Use stable text for Workshop Queue summaries.\n\n## Alternatives considered\n\nStable text and structured JSON were considered.\n\n"
            + "## Consequences\n\nStable text remains readable, while the rejected structured JSON costs a versioned schema.\n\n"
            + "## Risks\n\nConsumers must parse text carefully.\n",
            encoding="utf-8",
        )
        log = self.root / ".codearbiter/decisions/decision-log.md"
        log.write_text(log.read_text(encoding="utf-8") + "## DECISION-0004 — ADR-0004 — Choose the Workshop Queue summary-format boundary\n\n"
            + "**Date:** " + date + "\n**Status:** accepted\n**Supersedes:** none\n**Decided by:** " + name + "\n"
            + "**Decision category:** architecture\n**Artifact-section-hash:** n/a\n\n## Variance summary\n\nStatus type: open-decision-closure\n\n"
            + "## Decision\n\nUse stable text for Workshop Queue summaries.\n\n## SMARTS rationale\n\nStable and measurable.\n\n"
            + "## Implementation implication\n\nKeep workshop_queue/cli.py stable.\n",
            encoding="utf-8")

    def test_p03_accepts_one_real_co_commit_with_native_artifacts(self) -> None:
        from academy_engine.checkpoints import _p03_accepted_adr

        attempt = _Attempt("academy/P03-record-an-adr/1", 1, self.prepared, "0" * 40, self.head)
        self.assertTrue(_p03_accepted_adr(self.root, attempt, ".codearbiter/decisions/0004-academy-lab.md", ".codearbiter/decisions/decision-log.md"))

    def test_p03_accepts_the_equivalent_ordered_two_commit_history(self) -> None:
        from academy_engine.checkpoints import _p03_accepted_adr

        subprocess.run(["git", "reset", "--hard", self.prepared], cwd=self.root, check=True, capture_output=True, text=True)
        self._write_valid_evidence("Ada Learner")
        log = self.root / ".codearbiter/decisions/decision-log.md"
        prepared_log = "# Decision log\n\n"
        log.write_text(prepared_log, encoding="utf-8")
        self._commit("record ADR")
        log.write_text((self.root / ".codearbiter/decisions/decision-log.md").read_text(encoding="utf-8") + "## DECISION-0004 — ADR-0004 — Choose the Workshop Queue summary-format boundary\n\n"
            + "**Date:** " + subprocess.run(["git", "show", "-s", "--format=%aI", "HEAD"], cwd=self.root, check=True, capture_output=True, text=True).stdout[:10]
            + "\n**Status:** accepted\n**Supersedes:** none\n**Decided by:** Ada Learner\n**Decision category:** architecture\n**Artifact-section-hash:** n/a\n\n## Variance summary\n\nStatus type: open-decision-closure\n\n## Decision\n\nUse stable text for Workshop Queue summaries.\n\n## SMARTS rationale\n\nStable and measurable.\n\n## Implementation implication\n\nKeep workshop_queue/cli.py stable.\n", encoding="utf-8")
        self._commit("append decision log")
        attempt = _Attempt("academy/P03-record-an-adr/1", 1, self.prepared, "0" * 40, self._head())
        self.assertTrue(_p03_accepted_adr(self.root, attempt, ".codearbiter/decisions/0004-academy-lab.md", ".codearbiter/decisions/decision-log.md"))

    def test_p03_rejects_an_attribution_mismatch_even_when_old_headings_match(self) -> None:
        from academy_engine.checkpoints import _p03_accepted_adr

        subprocess.run(["git", "reset", "--hard", self.prepared], cwd=self.root, check=True, capture_output=True, text=True)
        self._write_valid_evidence("Other Learner")
        self._commit("record mismatched attribution")
        attempt = _Attempt("academy/P03-record-an-adr/1", 1, self.prepared, "0" * 40, self._head())
        self.assertFalse(_p03_accepted_adr(self.root, attempt, ".codearbiter/decisions/0004-academy-lab.md", ".codearbiter/decisions/decision-log.md"))

    def test_p03_log_is_ordered_unique_and_has_no_trailing_content(self) -> None:
        from academy_engine.checkpoints import _git_blob, _p03_parse_log

        prefix = _git_blob(self.root, self.prepared, ".codearbiter/decisions/decision-log.md")
        head = _git_blob(self.root, self.head, ".codearbiter/decisions/decision-log.md")
        self.assertIsNotNone(prefix)
        self.assertIsNotNone(head)
        for mutation in (
            b"\n## Extra section\n",
            b"**Status:** accepted\n",
            b"## DECISION-0004 \xe2\x80\x94 ADR-0004 \xe2\x80\x94 Choose the Workshop Queue summary-format boundary\n",
            b"**Supersedes:** none\n**Date:** 2026-08-04\n",
        ):
            with self.subTest(mutation=mutation[:16]):
                candidate = head + mutation
                self.assertFalse(_p03_parse_log(candidate, prefix, "Ada Learner", "2026-08-04", "Use stable text for Workshop Queue summaries."))

    def test_p03_requires_the_prepared_log_blob_and_strict_adr_structure(self) -> None:
        from academy_engine import checkpoints
        from academy_engine.checkpoints import _p03_accepted_adr

        attempt = _Attempt("academy/P03-record-an-adr/1", 1, self.prepared, "0" * 40, self.head)
        original = checkpoints._git_blob

        def missing_prepared_log(root: Path, ref: str, path: str):
            if ref == self.prepared and path == ".codearbiter/decisions/decision-log.md":
                return None
            return original(root, ref, path)

        with mock.patch("academy_engine.checkpoints._git_blob", side_effect=missing_prepared_log):
            self.assertFalse(checkpoints._p03_accepted_adr(self.root, attempt, ".codearbiter/decisions/0004-academy-lab.md", ".codearbiter/decisions/decision-log.md"))

        adr = original(self.root, self.head, ".codearbiter/decisions/0004-academy-lab.md")
        self.assertIsNotNone(adr)
        self.assertIsNotNone(checkpoints._p03_parse_adr(adr.replace(b"\n", b"\r\n"), "Ada Learner", "2026-08-04"))
        self.assertIsNone(checkpoints._p03_parse_adr(adr + b"\n# Extra heading\n", "Ada Learner", "2026-08-04"))
        self.assertIsNone(checkpoints._p03_parse_adr(adr.replace(b"costs a versioned schema", b"is merely another available format"), "Ada Learner", "2026-08-04"))

    def test_p03_rejects_negated_cost_and_prohibited_log_markers_but_allows_multiline_narrative(self) -> None:
        from academy_engine import checkpoints

        adr = checkpoints._git_blob(self.root, self.head, ".codearbiter/decisions/0004-academy-lab.md")
        prefix = checkpoints._git_blob(self.root, self.prepared, ".codearbiter/decisions/decision-log.md")
        log = checkpoints._git_blob(self.root, self.head, ".codearbiter/decisions/decision-log.md")
        self.assertIsNotNone(adr)
        self.assertIsNotNone(prefix)
        self.assertIsNotNone(log)
        for replacement in (b"structured JSON has no cost", b"structured JSON is without risk"):
            with self.subTest(replacement=replacement):
                candidate = adr.replace(b"costs a versioned schema", replacement)
                self.assertIsNone(checkpoints._p03_parse_adr(candidate, "Ada Learner", "2026-08-04"))
        for marker in (b"Re-evaluation trigger", b"Resolves same-level conflict between"):
            with self.subTest(marker=marker):
                candidate = log.replace(b"Stable and measurable.", b"Stable and measurable. " + marker)
                self.assertFalse(checkpoints._p03_parse_log(candidate, prefix, "Ada Learner", "2026-08-04", "Use stable text for Workshop Queue summaries."))
        multiline = log.replace(b"Stable and measurable.", b"Stable and measurable.\nThis is a second bounded rationale line.")
        self.assertTrue(checkpoints._p03_parse_log(multiline, prefix, "Ada Learner", "2026-08-04", "Use stable text for Workshop Queue summaries."))
        injected_heading = log.replace(b"Stable and measurable.", b"Stable and measurable.\n# Injected heading")
        self.assertFalse(checkpoints._p03_parse_log(injected_heading, prefix, "Ada Learner", "2026-08-04", "Use stable text for Workshop Queue summaries."))

    def test_p03_native_artifact_mutation_matrix_rejects_each_schema_decoy(self) -> None:
        """Keep the brief's native-artifact adversarial cases attached to immutable Git blobs."""
        from academy_engine import checkpoints

        adr = checkpoints._git_blob(self.root, self.head, ".codearbiter/decisions/0004-academy-lab.md")
        prefix = checkpoints._git_blob(self.root, self.prepared, ".codearbiter/decisions/decision-log.md")
        log = checkpoints._git_blob(self.root, self.head, ".codearbiter/decisions/decision-log.md")
        self.assertIsNotNone(adr)
        self.assertIsNotNone(prefix)
        self.assertIsNotNone(log)
        adr_mutations = (
            adr.replace(b"ADR-0004", b"ADR-0005", 1),
            adr.replace(b"status: accepted\n", b"", 1),
            adr.replace(b"status: accepted\n", b"status: accepted\nstatus: accepted\n", 1),
            adr.replace(b"## Status", b"## State", 1),
            adr + b"\n# Duplicate ADR heading\n",
            adr.replace(b"Accepted", b"Proposed", 1),
            adr.replace(b"Use stable text for Workshop Queue summaries.", b"Use stable text for Workshop Queue summaries.\nUse structured JSON for Workshop Queue summaries.", 1),
            adr.replace(b"Use stable text for Workshop Queue summaries.", b"No choice is recorded.", 1),
            adr.replace(b"decided-by: Ada Learner", b"decided-by: 'Ada Learner'", 1),
            adr.replace(b"decided-by: Ada Learner", b"decided-by: |\n  Ada Learner", 1),
        )
        for candidate in adr_mutations:
            with self.subTest(kind="adr"):
                self.assertIsNone(checkpoints._p03_parse_adr(candidate, "Ada Learner", "2026-08-04"))
        log_mutations = (
            log.replace(b"**Date:** 2026-08-04", b"**Date:** 1999-01-01", 1),
            log.replace(b"Use stable text for Workshop Queue summaries.", b"Use structured JSON for Workshop Queue summaries.", 1),
            log.replace(b"**Decided by:** Ada Learner", b"**Decided by:** 'Ada Learner'", 1),
            log.replace(b"## Decision", b"## Decision\n\nUse stable text for Workshop Queue summaries.\n\n## Decision", 1),
        )
        for candidate in log_mutations:
            with self.subTest(kind="log"):
                self.assertFalse(checkpoints._p03_parse_log(candidate, prefix, "Ada Learner", "2026-08-04", "Use stable text for Workshop Queue summaries."))
        self.assertFalse(checkpoints._p03_parse_log(log, prefix + b"rewritten", "Ada Learner", "2026-08-04", "Use stable text for Workshop Queue summaries."))

    def test_p03_real_git_history_mutation_matrix_rejects_noncanonical_evidence(self) -> None:
        """Exercise path/order/cleanliness mutations in real commits, not mocked history."""
        from academy_engine.checkpoints import _p03_accepted_adr

        def reset_with_valid() -> None:
            subprocess.run(["git", "reset", "--hard", self.prepared], cwd=self.root, check=True, capture_output=True, text=True)
            self._write_valid_evidence("Ada Learner")

        def attempt() -> _Attempt:
            return _Attempt("academy/P03-record-an-adr/1", 1, self.prepared, "0" * 40, self._head())

        # The uncommitted lookalike is rejected without creating any learner evidence commit.
        (self.root / ".codearbiter/decisions/0004-academy-lab.md").write_text("lookalike\n", encoding="utf-8")
        self.assertFalse(_p03_accepted_adr(self.root, attempt(), ".codearbiter/decisions/0004-academy-lab.md", ".codearbiter/decisions/decision-log.md"))
        subprocess.run(["git", "reset", "--hard", "HEAD"], cwd=self.root, check=True, capture_output=True, text=True)

        reset_with_valid()
        (self.root / ".codearbiter/decisions/0004-academy-lab.md").rename(self.root / ".codearbiter/decisions/0004-alternate.md")
        self._commit("alternate ADR filename")
        self.assertFalse(_p03_accepted_adr(self.root, attempt(), ".codearbiter/decisions/0004-academy-lab.md", ".codearbiter/decisions/decision-log.md"))

        reset_with_valid()
        (self.root / "generic-governance-event.md").write_text("decoy\n", encoding="utf-8")
        self._commit("generic event decoy")
        self.assertFalse(_p03_accepted_adr(self.root, attempt(), ".codearbiter/decisions/0004-academy-lab.md", ".codearbiter/decisions/decision-log.md"))

        reset_with_valid()
        adr = self.root / ".codearbiter/decisions/0004-academy-lab.md"
        adr_bytes = adr.read_bytes()
        adr.unlink()
        self._commit("log before ADR")
        adr.write_bytes(adr_bytes)
        self._commit("late ADR")
        self.assertFalse(_p03_accepted_adr(self.root, attempt(), ".codearbiter/decisions/0004-academy-lab.md", ".codearbiter/decisions/decision-log.md"))

        reset_with_valid()
        self._commit("valid evidence")
        (self.root / "README.md").write_text("later mutation\n", encoding="utf-8")
        self._commit("extra path")
        self.assertFalse(_p03_accepted_adr(self.root, attempt(), ".codearbiter/decisions/0004-academy-lab.md", ".codearbiter/decisions/decision-log.md"))

        reset_with_valid()
        (self.root / ".codearbiter/decisions/0003-verifier-trust.md").write_text("rewritten ADR-0003\n", encoding="utf-8")
        self._commit("edit ADR-0003")
        self.assertFalse(_p03_accepted_adr(self.root, attempt(), ".codearbiter/decisions/0004-academy-lab.md", ".codearbiter/decisions/decision-log.md"))

        reset_with_valid()
        self._commit("valid evidence")
        subprocess.run(["git", "branch", "p03-merge-side", self.prepared], cwd=self.root, check=True, capture_output=True, text=True)
        subprocess.run(["git", "switch", "p03-merge-side"], cwd=self.root, check=True, capture_output=True, text=True)
        (self.root / "README.md").write_text("side history\n", encoding="utf-8")
        self._commit("side history")
        subprocess.run(["git", "switch", "academy/P03-record-an-adr/1"], cwd=self.root, check=True, capture_output=True, text=True)
        subprocess.run(["git", "merge", "--no-ff", "p03-merge-side", "-m", "merge side history"], cwd=self.root, check=True, capture_output=True, text=True)
        self.assertFalse(_p03_accepted_adr(self.root, attempt(), ".codearbiter/decisions/0004-academy-lab.md", ".codearbiter/decisions/decision-log.md"))

        reset_with_valid()
        self._commit("valid evidence")
        adr.write_text(adr.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        self._commit("later ADR mutation")
        self.assertFalse(_p03_accepted_adr(self.root, attempt(), ".codearbiter/decisions/0004-academy-lab.md", ".codearbiter/decisions/decision-log.md"))

    def test_p03_rejects_a_stale_copied_native_pair_from_a_prior_attempt(self) -> None:
        """A byte-for-byte native pair must still bind to its introducing commit's date."""
        from academy_engine import checkpoints

        adr_path = ".codearbiter/decisions/0004-academy-lab.md"
        log_path = ".codearbiter/decisions/decision-log.md"
        prior_adr = checkpoints._git_blob(self.root, self.head, adr_path)
        prior_log = checkpoints._git_blob(self.root, self.head, log_path)
        self.assertIsNotNone(prior_adr)
        self.assertIsNotNone(prior_log)
        prior_attempt = _Attempt("academy/P03-record-an-adr/1", 1, self.prepared, "0" * 40, self.head)
        self.assertTrue(checkpoints._p03_accepted_adr(self.root, prior_attempt, adr_path, log_path))

        subprocess.run(["git", "reset", "--hard", self.prepared], cwd=self.root, check=True, capture_output=True, text=True)
        (self.root / adr_path).write_bytes(prior_adr)
        (self.root / log_path).write_bytes(prior_log)
        subprocess.run(["git", "add", adr_path, log_path], cwd=self.root, check=True, capture_output=True, text=True)
        environment = os.environ.copy()
        environment["GIT_AUTHOR_DATE"] = "2030-01-02T03:04:05+00:00"
        environment["GIT_COMMITTER_DATE"] = "2030-01-02T03:04:05+00:00"
        subprocess.run(["git", "commit", "-m", "copy prior native pair"], cwd=self.root, env=environment, check=True, capture_output=True, text=True)
        copied_attempt = _Attempt("academy/P03-record-an-adr/1", 1, self.prepared, "0" * 40, self._head())
        self.assertFalse(checkpoints._p03_accepted_adr(self.root, copied_attempt, adr_path, log_path))
