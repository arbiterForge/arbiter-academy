from __future__ import annotations

import unittest
from pathlib import Path

from academy_engine import curriculum
from academy_engine.lesson_actions import load_action_manifest
from academy_engine.preview import load_preview_manifest


SOURCE = Path(__file__).parents[1]
U07 = "U07-capstone"


class U07PrivateCapstoneContractTests(unittest.TestCase):
    """The capstone is source-only until its deterministic verifier is complete."""

    def test_private_guide_uses_shared_actions_and_never_claims_a_hosted_pr(self) -> None:
        manifest = load_action_manifest(SOURCE, U07)
        action_ids = tuple(action.id for action in manifest.actions)
        self.assertEqual(
            action_ids,
            (
                "U07-read-private-boundary",
                "U07-prepare-refusal",
                "U07-read-capstone-brief",
                "U07-run-governed-feature",
                "U07-record-architecture-decision",
                "U07-run-local-review",
                "U07-check-refusal",
            ),
        )
        by_id = {action.id: action for action in manifest.actions}
        self.assertIn("not published", by_id["U07-prepare-refusal"].expected_result.casefold())
        self.assertIn("read-only", by_id["U07-run-local-review"].expected_result.casefold())
        self.assertIn("hosted pull-request", by_id["U07-run-governed-feature"].evidence.casefold())
        guide_path = SOURCE / "academy/tracks/power-user/U07-capstone.md"
        guide = guide_path.read_text(encoding="utf-8")
        self.assertEqual(curriculum._parse_lab(guide_path).id, U07)
        self.assertIn("private source material", guide.casefold())
        self.assertIn("cannot prove", guide.casefold())
        self.assertIn("$ca-review", guide)
        self.assertIn("read-only", guide.casefold())
        self.assertNotIn("$ca-audit", guide)
        self.assertNotIn("GitHub PR exists", guide)
        self.assertNotIn("U07-review.json", guide)
        self.assertNotIn("U07-submission-boundary.json", guide)
        release = load_preview_manifest(SOURCE)
        self.assertNotIn(U07, release.guided_labs)


if __name__ == "__main__":
    unittest.main()
