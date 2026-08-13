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
            subprocess.run(["git", "-c", "gc.auto=0", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-m", "source"], cwd=root, check=True, capture_output=True, text=True)
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
        statuses = {item["id"]: item["source_status"] for item in payload["labs"]}
        authored = {
                "F01-fork-clone-doctor",
                "F02-orient-to-state",
                "F03-work-the-board",
                "F04-fix-with-evidence",
                "P01-feature-through-plan",
                "P02-commit-review-pr",
                "P03-record-an-adr",
                "P04-review-a-dependency",
                "P05-checkpoint-remediation",
                "P06-context-drift-recovery",
                "P07-threat-model",
                "P08-repository-hygiene",
                "U01-autonomous-sprint",
                "U04-initialize-projects",
                "U05-debug-spike-conflict",
                "U06-preview-and-advanced-surfaces",
        }
        self.assertEqual({lab_id for lab_id, status in statuses.items() if status == "authored"}, authored)
        self.assertTrue(
            all(
                status == "pending"
                for lab_id, status in statuses.items()
                if lab_id not in authored
            )
        )
        self.assertTrue(all(item["contract_path"] == "academy/contracts.json" for item in payload["labs"]))

    def test_cli_rejects_non_object_or_unknown_key_manifest_without_traceback(self):
        source = Path(__file__).resolve().parents[1]
        script = source / "scripts" / "academy.py"
        for label, malformed in (
            ("non-object", []),
            (
                "unknown-key",
                {
                    "schema_version": 1,
                    "id": "F01-fork-clone-doctor",
                    "files": [],
                    "removals": [],
                    "starting_task": "F01",
                    "checkpoint": "academy/checkpoints/F01-fork-clone-doctor.json",
                    "requires_push_safe_setup": True,
                    "unexpected": "value",
                },
            ),
        ):
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                root = Path(directory) / "repo"
                shutil.copytree(
                    source,
                    root,
                    ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"),
                )
                manifest = root / "academy/scenarios/F01-fork-clone-doctor/manifest.json"
                manifest.write_text(json.dumps(malformed), encoding="utf-8")
                subprocess.run(["git", "init", "-b", "main"], cwd=root, check=True, capture_output=True, text=True)
                subprocess.run(["git", "add", "."], cwd=root, check=True, capture_output=True, text=True)
                subprocess.run(["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-m", "malformed manifest"], cwd=root, check=True, capture_output=True, text=True)
                result = subprocess.run(
                    [sys.executable, str(script), "export-catalog", str(Path(directory) / "catalog.json")],
                    cwd=root,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("error:", result.stderr)
                self.assertNotIn("Traceback", result.stderr)
                self.assertNotIn(directory, result.stderr)
