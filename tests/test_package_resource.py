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
            ["academy/actions/*.json"],
        )
        self.assertEqual(
            data_files["share/arbiter-academy/academy/guides"],
            ["academy/guides/*.md"],
        )


if __name__ == "__main__":
    unittest.main()
