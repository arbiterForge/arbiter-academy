from __future__ import annotations

import json
import unittest
from importlib.resources import files


class PackageResourceTests(unittest.TestCase):
    def test_bundled_seed_contains_the_initial_workshop_ticket(self) -> None:
        resource = files("workshop_queue").joinpath("seed", "tickets.json")

        tickets = json.loads(resource.read_text(encoding="utf-8"))

        self.assertEqual(tickets[0]["id"], "RQ-101")
        self.assertEqual(tickets[0]["status"], "open")


if __name__ == "__main__":
    unittest.main()
