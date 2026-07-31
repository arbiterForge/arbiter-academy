from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class WorkshopQueueCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
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

    def run_cli(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "workshop_queue", "--data-file", str(self.fixture), *arguments],
            text=True,
            capture_output=True,
            check=False,
        )

    def test_list_json_is_machine_readable(self) -> None:
        result = self.run_cli("list", "--format", "json")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)[0]["id"], "RQ-101")

    def test_claim_persists_attribution(self) -> None:
        result = self.run_cli("claim", "RQ-101", "--volunteer", "Sam")

        self.assertEqual(result.returncode, 0, result.stderr)
        claimed = json.loads(self.fixture.read_text(encoding="utf-8"))[0]
        self.assertEqual(claimed["status"], "claimed")
        self.assertEqual(claimed["claimed_by"], "Sam")

    def test_complete_rejects_an_open_ticket_without_rewriting_it(self) -> None:
        original = self.fixture.read_text(encoding="utf-8")

        result = self.run_cli("complete", "RQ-101", "--resolution", "Done")

        self.assertEqual(result.returncode, 2)
        self.assertIn("cannot be completed", result.stderr)
        self.assertEqual(self.fixture.read_text(encoding="utf-8"), original)

    def test_report_json_returns_status_counts(self) -> None:
        result = self.run_cli("report", "--format", "json")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {"claimed": 0, "completed": 0, "open": 1})


if __name__ == "__main__":
    unittest.main()
