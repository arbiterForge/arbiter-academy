from __future__ import annotations

import unittest
from pathlib import Path

from academy_engine import curriculum
from academy_engine.lesson_actions import load_action_manifest
from academy_engine.preview import load_preview_manifest
from academy_engine.scenario import prepare_lab
from tests.test_foundations_labs import AcademyRepository, git


SOURCE = Path(__file__).parents[1]
U07 = "U07-capstone"


class U07PrivateCapstoneContractTests(unittest.TestCase):
    """U07 teaches the real feature lane without fabricating hosted proof."""

    def test_private_guide_uses_the_real_feature_lane_and_keeps_pr_proof_in_the_browser(self) -> None:
        manifest = load_action_manifest(SOURCE, U07)
        action_ids = tuple(action.id for action in manifest.actions)
        self.assertEqual(
            action_ids,
            (
                "U07-prepare",
                "U07-run-feature",
                "U07-open-pr",
                "U07-check",
                "U07-reset-retry",
            ),
        )
        by_id = {action.id: action for action in manifest.actions}
        self.assertEqual(
            {(variant.host, variant.command) for variant in by_id["U07-run-feature"].variants},
            {
                ("claude-code", '/ca:feature "Reject control characters in ticket resolutions"'),
                ("codex", '$ca-feature "Reject control characters in ticket resolutions"'),
                ("pi", '/ca-feature "Reject control characters in ticket resolutions"'),
                ("pi", '/skill:ca-feature "Reject control characters in ticket resolutions"'),
            },
        )
        self.assertIn("browser URL", by_id["U07-open-pr"].evidence)
        self.assertIn("does not authenticate", by_id["U07-open-pr"].evidence)
        self.assertNotIn("receipt", by_id["U07-check"].evidence.casefold())
        guide_path = SOURCE / "academy/tracks/power-user/U07-capstone.md"
        guide = guide_path.read_text(encoding="utf-8")
        self.assertEqual(curriculum._parse_lab(guide_path).id, U07)
        self.assertEqual(
            tuple(line for line in guide.splitlines() if line.startswith("## ")),
            (
                "## Know before you begin",
                "## What you will prove",
                "## Prepare safely",
                "## Practice",
                "## Recognize success",
                "## Check",
                "## Recover or continue",
                "## Understand the mechanism",
            ),
        )
        self.assertIn("real CodeArbiter feature lane", guide)
        self.assertIn("hosted pull request", guide)
        self.assertIn("does not prove that the feature command ran", guide)
        self.assertNotIn("U07-pr-receipt", guide)
        self.assertNotIn("$ca-adr", guide)
        self.assertNotIn("$ca-review", guide)
        release = load_preview_manifest(SOURCE)
        self.assertNotIn(U07, release.guided_labs)

    def test_private_capstone_prepares_the_real_feature_fixture(self) -> None:
        """The accepted capstone starts from a bounded, inspectable defect."""
        fixture = AcademyRepository()
        self.addCleanup(fixture.close)
        fixture.add_safe_upstream()

        prepared = prepare_lab(fixture.root, U07)
        self.assertEqual(prepared.branch, "academy/U07-capstone/1")

        self.assertIn("academy/U07-capstone/1", git(fixture.root, "branch", "--list").stdout)
        self.assertEqual(
            git(fixture.root, "status", "--porcelain", "--untracked-files=all").stdout,
            "",
        )


if __name__ == "__main__":
    unittest.main()
