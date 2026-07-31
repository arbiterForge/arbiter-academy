import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from academy_engine.receipt import export_catalog


class CatalogExportTests(unittest.TestCase):
    def test_export_rejects_missing_checkpoint_mapping(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "academy").mkdir()
            (root / "academy" / "catalog.json").write_text('{"schema_version":1,"labs":[]}', encoding="utf-8")
            subprocess.run(["git", "init", "-b", "main"], cwd=root, check=True, capture_output=True, text=True)
            subprocess.run(["git", "add", "."], cwd=root, check=True, capture_output=True, text=True)
            subprocess.run(
                ["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-m", "invalid source"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )
            with self.assertRaises(ValueError): export_catalog(root, root / "catalog-export.json")

    def test_current_repository_exports_pending_sources_with_source_commit(self):
        source = Path(__file__).resolve().parents[1]
        script = source / "scripts" / "academy.py"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "repo"
            shutil.copytree(
                source,
                root,
                ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"),
            )
            subprocess.run(["git", "init", "-b", "main"], cwd=root, check=True, capture_output=True, text=True)
            subprocess.run(["git", "add", "."], cwd=root, check=True, capture_output=True, text=True)
            subprocess.run(["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-m", "source"], cwd=root, check=True, capture_output=True, text=True)
            output = Path(directory) / "catalog.json"
            result = subprocess.run(
                [sys.executable, str(script), "export-catalog", str(output)],
                cwd=root,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(output.read_text(encoding="utf-8"))
            original = output.read_bytes()
            (root / "academy" / "contracts.json").write_text(
                '{"schema_version":2,"contracts":[]}',
                encoding="utf-8",
            )
            second = subprocess.run(
                [sys.executable, str(script), "export-catalog", str(output)],
                cwd=root,
                capture_output=True,
                text=True,
            )
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(output.read_bytes(), original)
        self.assertRegex(payload["source_commit"], r"^[0-9a-f]{40}$")
        self.assertEqual(len(payload["labs"]), 19)
        self.assertTrue(all(item["source_status"] == "pending" for item in payload["labs"]))
        self.assertTrue(all(item["contract_path"] == "academy/contracts.json" for item in payload["labs"]))
