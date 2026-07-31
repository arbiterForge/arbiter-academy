import json
import hashlib
import shutil
import tempfile
import subprocess
import sys
import unittest
from pathlib import Path

from academy_engine.checkpoints import (
    CheckpointError,
    Predicate,
    _Attempt,
    _SemanticContext,
    _git_blob,
    _json,
    _raw_digest,
    _semantic,
    evaluate_checkpoint,
    load_checkpoint,
    load_contracts,
)


class CheckpointTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "academy" / "checkpoints").mkdir(parents=True)
        (self.root / "academy" / "catalog.json").write_text('{"schema_version":1,"labs":[]}', encoding="utf-8")
        self.path = self.root / "academy" / "checkpoints" / "F01-fork-clone-doctor.json"
        self.write({"schema_version": 2, "id": "F01-fork-clone-doctor", "predicates": [{"id": "remote_and_doctor", "type": "lab_semantics", "profile": "remote_doctor", "artifact": ".codearbiter/reports/academy/F01-doctor.json"}]})

    def tearDown(self): self.temp.cleanup()

    def write(self, value): self.path.write_text(json.dumps(value), encoding="utf-8")

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
                [sys.executable, str(source / "scripts" / "academy.py"), "check", lab_id],
                cwd=root,
                capture_output=True,
                text=True,
            )
            self.assertEqual(checked.returncode, 0, checked.stderr)
            progress = json.loads((root / ".academy" / "progress.json").read_text(encoding="utf-8"))
            self.assertEqual(progress["checkpoints"][0]["attempt"], f"academy/{lab_id}/2")
            remotes_path = root / "academy_engine" / "remotes.py"
            remotes_original = remotes_path.read_bytes()
            remotes_path.write_bytes(remotes_original + b"\n# verifier substitution\n")
            substituted_verifier = evaluate_checkpoint(root, lab_id)
            self.assertFalse(substituted_verifier.passed)
            self.assertIn("source_integrity", substituted_verifier.failed_predicates)
            remotes_path.write_bytes(remotes_original)
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
