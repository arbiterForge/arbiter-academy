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


class U07CapstoneContractTests(unittest.TestCase):
    """U07 teaches the real feature lane without fabricating hosted proof."""

    def test_public_guide_routes_a_known_bug_to_fix_and_keeps_pr_proof_external(self) -> None:
        manifest = load_action_manifest(SOURCE, U07)
        by_id = {action.id: action for action in manifest.actions}
        self.assertEqual(tuple(by_id), ("U07-return-to-main", "U07-prepare", "U07-run-fix", "U07-open-pr", "U07-check", "U07-reset-retry"))
        for variant in by_id["U07-run-fix"].variants:
            self.assertIn('fix "Reject control characters in ticket resolutions"', variant.command)
            self.assertNotIn("feature", variant.command)
            self.assertFalse(variant.command.startswith("!"))
        self.assertIn("base repository is your personal fork", by_id["U07-open-pr"].instruction)
        self.assertIn("do not merge", by_id["U07-open-pr"].instruction)
        self.assertIn("does not authenticate", by_id["U07-open-pr"].evidence)
        guide = (SOURCE / "academy/tracks/power-user/U07-capstone.md").read_text(encoding="utf-8")
        for action_id in by_id:
            self.assertEqual(sum(line == "{{action:" + action_id + "}}" for line in guide.splitlines()), 1)
        self.assertIn("known bug", guide)
        self.assertIn("regression fail", guide)
        self.assertIn("cannot prove", guide)
        self.assertIn(U07, load_preview_manifest(SOURCE).guided_labs)

    def test_capstone_prepares_the_real_feature_fixture(self) -> None:
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
