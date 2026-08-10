import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
import sys
import hashlib
import json
from unittest.mock import patch
from academy_engine.receipt import (
    ReceiptPrivacyError,
    graduate,
    validate_graduation_receipt,
    validate_receipt_value,
)
from academy_engine.checkpoints import CheckpointResult, LAB_INVENTORY


class ReceiptTests(unittest.TestCase):
    def test_private_values_are_rejected(self):
        # Assemble credential-shaped fixtures at runtime so repository scanners
        # can distinguish these synthetic test values from committed credentials.
        github_token = "gh" + "p_abcdefghijklmnopqrstuvwxyz012345"
        aws_access_key = "AK" + "IA0123456789ABCDEF"
        openai_project = "sk-" + "proj-abcdefghijklmnopqrstuvwxyz012345"
        github_fine_grained = "github_" + "pat_abcdefghijklmnopqrstuvwxyz012345"
        slack_token = "xox" + "b-1234567890-secret"
        for value in ("C:\\Users\\learner\\academy", "C:/Users/learner/academy", "\\\\server\\share\\academy", "/opt/private/academy", "learner@example.com", f"https://token:{github_token}@github.com/x/y", aws_access_key, openai_project, github_fine_grained, slack_token):
            with self.subTest(value=value):
                with self.assertRaises(ReceiptPrivacyError): validate_receipt_value(value)

    def test_repository_relative_artifact_paths_are_not_private(self):
        validate_receipt_value(
            {
                "source_path": "academy/tracks/foundations/F01-fork-clone-doctor.md",
                "checkpoint_path": "academy/checkpoints/F01-fork-clone-doctor.json",
            }
        )

    def test_graduate_writes_validated_receipt_and_rejects_range_or_duplicate_tampering(self):
        source = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "repo"; root.mkdir()
            shutil.copytree(source / "academy", root / "academy")
            subprocess.run(["git", "init", "-b", "main"], cwd=root, check=True, capture_output=True, text=True)
            subprocess.run(["git", "add", "."], cwd=root, check=True, capture_output=True, text=True)
            subprocess.run(["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-m", "fixture"], cwd=root, check=True, capture_output=True, text=True)
            head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True).stdout.strip()
            catalog_digest = hashlib.sha256((root / "academy" / "catalog.json").read_bytes()).hexdigest()
            results = [
                CheckpointResult(
                    lab_id=lab_id,
                    passed=True,
                    definition_digest="a" * 64,
                    digest="b" * 64,
                    passed_predicates=("semantic",),
                    failed_predicates=(),
                    catalog_digest=catalog_digest,
                    manifest_digest="c" * 64,
                    source_digest="d" * 64,
                    contract_digest="e" * 64,
                    attempt=f"academy/{lab_id}/2",
                    prepared_commit=head,
                    base_commit=head,
                    head_commit=head,
                )
                for lab_id in LAB_INVENTORY
            ]
            with patch("academy_engine.receipt.evaluate_checkpoint", side_effect=results):
                receipt = graduate(root)
            self.assertEqual(receipt.data["trust_model"], "installed-local-verifier")
            self.assertEqual(json.loads(receipt.path.read_text(encoding="utf-8")), receipt.data)
            self.assertEqual(hashlib.sha256(receipt.path.read_bytes()).hexdigest(), receipt.digest)
            tampered = json.loads(receipt.path.read_text(encoding="utf-8"))
            tampered["capstone_commit_range"]["to"] = "f" * 40
            with self.assertRaisesRegex(ValueError, "exact attempt"):
                validate_graduation_receipt(tampered)
            duplicated = json.loads(receipt.path.read_text(encoding="utf-8"))
            duplicated["checkpoints"][1]["id"] = duplicated["checkpoints"][0]["id"]
            with self.assertRaisesRegex(ValueError, "exact and unique"):
                validate_graduation_receipt(duplicated)

    def test_receipt_rejects_numeric_identity_coercion_and_boolean_version(self):
        source = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "repo"; root.mkdir()
            shutil.copytree(source / "academy", root / "academy")
            subprocess.run(["git", "init", "-b", "main"], cwd=root, check=True, capture_output=True, text=True)
            subprocess.run(["git", "add", "."], cwd=root, check=True, capture_output=True, text=True)
            subprocess.run(["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-m", "fixture"], cwd=root, check=True, capture_output=True, text=True)
            head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True).stdout.strip()
            catalog_digest = hashlib.sha256((root / "academy" / "catalog.json").read_bytes()).hexdigest()
            results = [
                CheckpointResult(
                    lab_id=lab_id, passed=True, definition_digest="a" * 64,
                    digest="b" * 64, passed_predicates=("semantic",), failed_predicates=(),
                    catalog_digest=catalog_digest, manifest_digest="c" * 64,
                    source_digest="d" * 64, contract_digest="e" * 64,
                    attempt=f"academy/{lab_id}/2", prepared_commit=head,
                    base_commit=head, head_commit=head,
                )
                for lab_id in LAB_INVENTORY
            ]
            with patch("academy_engine.receipt.evaluate_checkpoint", side_effect=results):
                valid = graduate(root).data
            for field, value in (("source_commit", int("1" * 40)), ("catalog_sha256", int("2" * 64)), ("schema_version", True)):
                with self.subTest(field=field):
                    malformed = json.loads(json.dumps(valid))
                    malformed[field] = value
                    with self.assertRaises(ValueError):
                        validate_graduation_receipt(malformed)
            malformed = json.loads(json.dumps(valid))
            malformed["checkpoints"][0]["attempt_head"] = int("3" * 40)
            with self.assertRaises(ValueError):
                validate_graduation_receipt(malformed)

    def test_fresh_catalog_repository_cannot_graduate_from_static_fixture_files(self):
        source = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "repo"; root.mkdir()
            shutil.copytree(source / "academy", root / "academy")
            shutil.copytree(source / ".codearbiter", root / ".codearbiter")
            shutil.copytree(source / "workshop_queue", root / "workshop_queue")
            subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True, text=True)
            subprocess.run(["git", "add", "."], cwd=root, check=True, capture_output=True, text=True)
            subprocess.run(["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-m", "fixture"], cwd=root, check=True, capture_output=True, text=True)
            with self.assertRaisesRegex(ValueError, "graduation blocked"):
                graduate(root)

    def test_empty_directory_cli_fails_without_traceback_or_path(self):
        script = Path(__file__).resolve().parents[1] / "scripts" / "academy.py"
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run([sys.executable, str(script), "graduate"], cwd=directory, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("error:", result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertNotIn(directory, result.stderr)
