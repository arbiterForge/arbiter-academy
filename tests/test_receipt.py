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
                    governed = root / LAB_CONTRACT[lab]; governed.parent.mkdir(parents=True, exist_ok=True); governed.write_text(governed.read_text(encoding="utf-8") + "\nlearner evidence", encoding="utf-8")
                    work = root / ".academy" / "work" / lab / "outcome.json"; work.parent.mkdir(parents=True, exist_ok=True); work.write_text(json.dumps({"lab_id": lab, "outcome": "complete"}, sort_keys=True, separators=(",", ":")), encoding="utf-8")
                    subprocess.run(["git", "add", str(governed.relative_to(root)), str(work.relative_to(root))], cwd=root, check=True, capture_output=True, text=True)
                    subprocess.run(["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-m", lab + " output"], cwd=root, check=True, capture_output=True, text=True)
                    attempt_commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True).stdout.strip()
                    blob = lambda path: subprocess.run(["git", "show", f"HEAD:{path}"], cwd=root, check=True, capture_output=True, text=True, encoding="utf-8", errors="surrogateescape").stdout.encode("utf-8", "surrogateescape")
                    evidence = root / ".academy" / "evidence" / f"{lab}.json"; evidence.parent.mkdir(parents=True, exist_ok=True)
                    track = next(item["track"] for item in json.loads((root / "academy" / "catalog.json").read_text(encoding="utf-8"))["labs"] if item["id"] == lab)
                    evidence.write_text(json.dumps({"attempt_branch":f"academy/{lab}/1","attempt_commit":attempt_commit,"base_commit":subprocess.run(["git","rev-parse","main"],cwd=root,check=True,capture_output=True,text=True).stdout.strip(),"catalog_sha256":hashlib.sha256(blob("academy/catalog.json")).hexdigest(),"governed_blob_sha256":hashlib.sha256(blob(LAB_CONTRACT[lab])).hexdigest(),"governed_path":LAB_CONTRACT[lab],"lab_id":lab,"schema_version":1,"source_sha256":hashlib.sha256(blob(f"academy/tracks/{track}/{lab}.md")).hexdigest(),"status":"passed","work_blob_sha256":hashlib.sha256(blob(f".academy/work/{lab}/outcome.json")).hexdigest(),"work_path":f".academy/work/{lab}/outcome.json"}, sort_keys=True, separators=(",", ":")), encoding="utf-8")
                    subprocess.run(["git", "add", str(evidence.relative_to(root))], cwd=root, check=True, capture_output=True, text=True)
                    subprocess.run(["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-m", lab + " evidence"], cwd=root, check=True, capture_output=True, text=True)
                    subprocess.run(["git", "switch", "main"], cwd=root, check=True, capture_output=True, text=True)
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
