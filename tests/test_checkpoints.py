import json
import hashlib
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
