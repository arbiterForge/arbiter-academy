import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from academy_engine.receipt import ReceiptPrivacyError, graduate, validate_receipt_value


class ReceiptTests(unittest.TestCase):
    def test_private_values_are_rejected(self):
        for value in ("C:\\Users\\learner\\academy", "/home/learner/academy", "learner@example.com", "https://token:ghp_abcdefghijklmnopqrstuvwxyz012345@github.com/x/y", "AKIA0123456789ABCDEF"):
            with self.subTest(value=value):
                with self.assertRaises(ReceiptPrivacyError): validate_receipt_value(value)

    def test_graduation_recomputes_even_when_progress_is_fabricated_or_definition_changes(self):
        source = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "repo"; root.mkdir()
            shutil.copytree(source / "academy", root / "academy")
            shutil.copytree(source / ".codearbiter", root / ".codearbiter")
            subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True, text=True)
            subprocess.run(["git", "add", "."], cwd=root, check=True, capture_output=True, text=True)
            subprocess.run(["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-m", "fixture"], cwd=root, check=True, capture_output=True, text=True)
            (root / "academy" / "progress.json").write_text('{"schema_version":1,"checkpoints":[{"id":"U07-capstone","digest":"0"}] }', encoding="utf-8")
            receipt = graduate(root)
            self.assertEqual(len(receipt.data["checkpoints"]), 19)
            self.assertNotIn("fixture@example", str(receipt.data))
            changed = root / "academy" / "checkpoints" / "F01-fork-clone-doctor.json"
            changed.write_text('{"schema_version":1,"id":"F01-fork-clone-doctor","predicates":[{"id":"missing","type":"file_exists","path":".codearbiter/missing.md"}]}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "F01-fork-clone-doctor"):
                graduate(root)
