from __future__ import annotations

import json
import tomllib
import unittest
from importlib.resources import files
from pathlib import Path


class PackageResourceTests(unittest.TestCase):
    def test_bundled_seed_contains_the_initial_workshop_ticket(self) -> None:
        resource = files("workshop_queue").joinpath("seed", "tickets.json")

        tickets = json.loads(resource.read_text(encoding="utf-8"))

        self.assertEqual(tickets[0]["id"], "RQ-101")
        self.assertEqual(tickets[0]["status"], "open")

    def test_lesson_contract_resources_are_in_the_distribution_contract(self) -> None:
        root = Path(__file__).parents[1]
        project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
        data_files = project["tool"]["setuptools"]["data-files"]

        self.assertIn(
            "academy/lesson-action.schema.json",
            data_files["share/arbiter-academy/academy"],
        )
        self.assertEqual(
            data_files["share/arbiter-academy/academy/actions"],
            [
                "academy/actions/home.json",
                "academy/actions/recovery.json",
                "academy/actions/F01-fork-clone-doctor.json",
                "academy/actions/F02-orient-to-state.json",
                "academy/actions/F03-work-the-board.json",
                "academy/actions/F04-fix-with-evidence.json",
                "academy/actions/P01-feature-through-plan.json",
                "academy/actions/P02-commit-review-pr.json",
                "academy/actions/P03-record-an-adr.json",
                "academy/actions/P04-review-a-dependency.json",
                "academy/actions/P05-checkpoint-remediation.json",
                "academy/actions/P06-context-drift-recovery.json",
                "academy/actions/P07-threat-model.json",
                "academy/actions/P08-repository-hygiene.json",
                "academy/actions/U01-autonomous-sprint.json",
                "academy/actions/U02-override-audit-metrics.json",
                "academy/actions/U03-refactor-chore-release.json",
                "academy/actions/U04-initialize-projects.json",
                "academy/actions/U05-debug-spike-conflict.json",
                "academy/actions/U06-preview-and-advanced-surfaces.json",
            ],
        )
        self.assertEqual(
            data_files["share/arbiter-academy/academy/guides"],
            ["academy/guides/*.md"],
        )


if __name__ == "__main__":
    unittest.main()
