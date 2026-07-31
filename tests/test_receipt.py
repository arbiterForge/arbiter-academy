import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
import sys
import hashlib
import json
from academy_engine.receipt import ReceiptPrivacyError, graduate, validate_receipt_value
from academy_engine.checkpoints import LAB_CONTRACT


class ReceiptTests(unittest.TestCase):
    def test_private_values_are_rejected(self):
        for value in ("C:\\Users\\learner\\academy", "\\\\server\\share\\academy", "/opt/private/academy", "learner@example.com", "https://token:ghp_abcdefghijklmnopqrstuvwxyz012345@github.com/x/y", "AKIA0123456789ABCDEF", "sk-proj-abcdefghijklmnopqrstuvwxyz012345", "github_pat_abcdefghijklmnopqrstuvwxyz012345", "xoxb-1234567890-secret"):
            with self.subTest(value=value):
                with self.assertRaises(ReceiptPrivacyError): validate_receipt_value(value)

    def test_graduation_recomputes_even_when_progress_is_fabricated_or_definition_changes(self):
        source = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "repo"; root.mkdir()
            shutil.copytree(source / "academy", root / "academy")
            shutil.copytree(source / ".codearbiter", root / ".codearbiter")
            shutil.copytree(source / "workshop_queue", root / "workshop_queue")
            for lab in json.loads((root / "academy" / "catalog.json").read_text(encoding="utf-8"))["labs"]:
                lab_source = root / "academy" / "tracks" / lab["track"] / f"{lab['id']}.md"
                lab_source.parent.mkdir(parents=True, exist_ok=True); lab_source.write_text(f"# {lab['id']} fixture\n", encoding="utf-8")
            subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True, text=True)
            subprocess.run(["git", "add", "."], cwd=root, check=True, capture_output=True, text=True)
            subprocess.run(["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-m", "fixture"], cwd=root, check=True, capture_output=True, text=True)
            for prefix, count in (("F", 4), ("P", 8), ("U", 7)):
                for number in range(1, count + 1):
                    lab = next(item["id"] for item in json.loads((root / "academy" / "catalog.json").read_text(encoding="utf-8"))["labs"] if item["id"].startswith(f"{prefix}{number:02d}"))
                    subprocess.run(["git", "switch", "-c", f"academy/{lab}/1", "main"], cwd=root, check=True, capture_output=True, text=True)
                    subprocess.run(["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "--allow-empty", "-m", f"academy: prepare {lab} attempt 1"], cwd=root, check=True, capture_output=True, text=True)
                    contract = next(item for item in json.loads((root / "academy" / "contracts.json").read_text(encoding="utf-8"))["contracts"] if item["id"] == lab)
                    governed = root / contract["governed_path"]; governed.parent.mkdir(parents=True, exist_ok=True); governed.write_text(json.dumps({"lab_id": lab, "status": "governed"}, sort_keys=True, separators=(",", ":")), encoding="utf-8")
                    work = root / contract["work_path"]; work.parent.mkdir(parents=True, exist_ok=True); work.write_text(json.dumps(contract["outcome"], sort_keys=True, separators=(",", ":")), encoding="utf-8")
                    subprocess.run(["git", "add", str(governed.relative_to(root)), str(work.relative_to(root))], cwd=root, check=True, capture_output=True, text=True)
                    subprocess.run(["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-m", lab + " output"], cwd=root, check=True, capture_output=True, text=True)
                    subprocess.run(["git", "switch", "main"], cwd=root, check=True, capture_output=True, text=True)
            subprocess.run(["git", "switch", "academy/U07-capstone/1"], cwd=root, check=True, capture_output=True, text=True)
            for item in json.loads((root / "academy" / "catalog.json").read_text(encoding="utf-8"))["labs"]:
                if item["id"] != "U07-capstone": subprocess.run(["git", "merge", "--no-edit", f"academy/{item['id']}/1"], cwd=root, check=True, capture_output=True, text=True)
            (root / "academy" / "progress.json").write_text('{"schema_version":1,"checkpoints":[{"id":"U07-capstone","digest":"0"}] }', encoding="utf-8")
            receipt = graduate(root)
            self.assertEqual(len(receipt.data["checkpoints"]), 19)
            self.assertNotIn("fixture@example", str(receipt.data))
            changed = root / "academy" / "checkpoints" / "F01-fork-clone-doctor.json"
            changed.write_text('{"schema_version":1,"id":"F01-fork-clone-doctor","predicates":[{"id":"missing","type":"file_exists","path":".codearbiter/missing.md"}]}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "F01-fork-clone-doctor"):
                graduate(root)

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
