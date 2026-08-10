from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

from workshop_queue.cli import main
from workshop_queue.store import StoreWriteError


class WorkshopQueueCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.data_root = Path(__file__).resolve().parents[1] / "data"
        self.temporary_directory = tempfile.TemporaryDirectory(dir=self.data_root)
        self.fixture = Path(self.temporary_directory.name) / "tickets.json"
        self.fixture.write_text(
            json.dumps(
                [
                    {
                        "id": "RQ-101",
                        "title": "Set up projector",
                        "description": "Room A",
                        "status": "open",
                        "created_at": "2026-07-30T10:00:00Z",
                        "claimed_by": None,
                        "claimed_at": None,
                        "completed_at": None,
                        "resolution": None,
                    }
                ]
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def run_cli_for(self, data_file: Path | str, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "workshop_queue", "--data-file", str(data_file), *arguments],
            text=True,
            capture_output=True,
            check=False,
        )

    def run_cli(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return self.run_cli_for(self.fixture, *arguments)

    def test_list_json_is_machine_readable(self) -> None:
        result = self.run_cli("list", "--format", "json")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)[0]["id"], "RQ-101")

    def test_explicit_data_root_is_seeded_without_touching_user_data(self) -> None:
        with tempfile.TemporaryDirectory() as isolated_root:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "workshop_queue",
                    "--data-root",
                    isolated_root,
                    "list",
                    "--format",
                    "json",
                ],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)[0]["id"], "RQ-101")
            self.assertTrue((Path(isolated_root) / "tickets.json").is_file())

    def test_explicit_data_root_does_not_authorize_an_outside_data_file(self) -> None:
        with tempfile.TemporaryDirectory() as isolated_root, tempfile.TemporaryDirectory() as outside:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "workshop_queue",
                    "--data-root",
                    isolated_root,
                    "--data-file",
                    str(Path(outside) / "tickets.json"),
                    "list",
                    "--format",
                    "json",
                ],
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(result.returncode, 2)
        self.assertIn("trusted data root", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_source_checkout_default_reads_repository_data(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "workshop_queue", "list", "--format", "json"],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)[0]["id"], "RQ-101")

    def test_seed_initialization_failure_returns_a_stable_cli_error(self) -> None:
        stderr = io.StringIO()
        with tempfile.TemporaryDirectory() as isolated_root, patch(
            "workshop_queue.cli.initialize_ticket_store",
            side_effect=StoreWriteError("could not initialize ticket store"),
        ), redirect_stderr(stderr):
            return_code = main(["--data-root", isolated_root, "list", "--format", "json"])

        self.assertEqual(return_code, 2)
        self.assertEqual(stderr.getvalue(), "error: could not initialize ticket store\n")
        self.assertNotIn("Traceback", stderr.getvalue())

    def test_claim_persists_attribution(self) -> None:
        result = self.run_cli("claim", "RQ-101", "--volunteer", "Sam")

        self.assertEqual(result.returncode, 0, result.stderr)
        claimed = json.loads(self.fixture.read_text(encoding="utf-8"))[0]
        self.assertEqual(claimed["status"], "claimed")
        self.assertEqual(claimed["claimed_by"], "Sam")

    def test_store_write_failure_returns_a_stable_cli_error(self) -> None:
        stderr = io.StringIO()
        arguments = ["--data-file", str(self.fixture), "claim", "RQ-101", "--volunteer", "Sam"]

        with patch(
            "workshop_queue.cli.JsonTicketStore.save",
            side_effect=StoreWriteError("could not save ticket store"),
        ), redirect_stderr(stderr):
            return_code = main(arguments)

        self.assertEqual(return_code, 2)
        self.assertEqual(stderr.getvalue(), "error: could not save ticket store\n")
        self.assertNotIn("Traceback", stderr.getvalue())

    def test_complete_rejects_an_open_ticket_without_rewriting_it(self) -> None:
        original = self.fixture.read_text(encoding="utf-8")

        result = self.run_cli("complete", "RQ-101", "--resolution", "Done")

        self.assertEqual(result.returncode, 2)
        self.assertIn("cannot be completed", result.stderr)
        self.assertEqual(self.fixture.read_text(encoding="utf-8"), original)

    def test_claim_then_complete_persists_the_resolution(self) -> None:
        claim_result = self.run_cli("claim", "RQ-101", "--volunteer", "Sam")
        complete_result = self.run_cli("complete", "RQ-101", "--resolution", "Projector ready")

        self.assertEqual(claim_result.returncode, 0, claim_result.stderr)
        self.assertEqual(complete_result.returncode, 0, complete_result.stderr)
        completed = json.loads(self.fixture.read_text(encoding="utf-8"))[0]
        self.assertEqual(completed["status"], "completed")
        self.assertEqual(completed["resolution"], "Projector ready")
        self.assertIsNotNone(completed["completed_at"])

    def test_missing_claim_volunteer_is_rejected_without_rewriting(self) -> None:
        original = self.fixture.read_bytes()

        result = self.run_cli("claim", "RQ-101")

        self.assertEqual(result.returncode, 2)
        self.assertIn("--volunteer", result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertEqual(self.fixture.read_bytes(), original)

    def test_malformed_data_returns_a_stable_cli_error(self) -> None:
        self.fixture.write_bytes(b"\xff\xfe")

        result = self.run_cli("list", "--format", "json")

        self.assertEqual(result.returncode, 2)
        self.assertIn("could not read ticket store", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_report_json_returns_status_counts(self) -> None:
        result = self.run_cli("report", "--format", "json")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {"claimed": 0, "completed": 0, "open": 1})

    def test_absolute_path_outside_project_data_root_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as outside_directory:
            outside_path = Path(outside_directory) / "tickets.json"
            outside_path.write_text(self.fixture.read_text(encoding="utf-8"), encoding="utf-8")

            result = self.run_cli_for(outside_path, "list", "--format", "json")

        self.assertEqual(result.returncode, 2)
        self.assertIn("trusted data root", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_relative_path_is_resolved_under_project_data_root(self) -> None:
        relative_path = self.fixture.relative_to(self.data_root)

        result = self.run_cli_for(relative_path, "list", "--format", "json")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)[0]["id"], "RQ-101")

    def test_relative_parent_escape_is_rejected(self) -> None:
        result = self.run_cli_for(Path("..") / "outside.json", "report", "--format", "json")

        self.assertEqual(result.returncode, 2)
        self.assertIn("trusted data root", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    @unittest.skipUnless(os.name == "nt", "Windows path normalization coverage")
    def test_windows_case_normalized_absolute_path_inside_root_is_accepted(self) -> None:
        case_variant = str(self.fixture).swapcase()

        result = self.run_cli_for(case_variant, "list", "--format", "json")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)[0]["id"], "RQ-101")


if __name__ == "__main__":
    unittest.main()
