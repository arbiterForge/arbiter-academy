from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from academy_engine.preview import load_preview_manifest, require_guided_lab, require_runnable_lab
from academy_engine.scenario import PreparationError, prepare_lab
from academy_engine.u07_fixture import u07_remediation_source_is_exact, u07_remediation_test_is_exact
from scripts import build_preview_site as preview_site
from scripts.build_preview_site import build_preview_site
from tests.test_foundations_labs import AcademyRepository, git


SOURCE = Path(__file__).resolve().parents[1]
LAB = "U07-capstone"


class U07PrivateCapstoneTests(unittest.TestCase):
    def test_capstone_test_contract_rejects_a_vacuous_assertion(self) -> None:
        capstone_test = b'''\nimport unittest\n\nclass ServiceTests(unittest.TestCase):\n    def test_u07_rejects_control_characters_in_resolution(self) -> None:\n        claimed = claim_ticket([open_ticket("RQ-U07")], "RQ-U07", "Sam", fixed_now())\n        for resolution in ("done\\nagain", "done\\tagain", "done\\x7fagain"):\n            with self.subTest(resolution=repr(resolution)):\n                with self.assertRaisesRegex(ValueError, "control characters"):\n                    complete_ticket(claimed, "RQ-U07", resolution, fixed_now())\n'''
        self.assertTrue(u07_remediation_test_is_exact(capstone_test))
        self.assertFalse(
            u07_remediation_test_is_exact(
                b'''\n    def test_u07_rejects_control_characters_in_resolution(self) -> None:\n        claimed = claim_ticket([open_ticket("RQ-U07")], "RQ-U07", "Sam", fixed_now())\n        for resolution in ("done\\nagain", "done\\tagain", "done\\x7fagain"):\n            with self.assertRaisesRegex(ValueError, "control characters"):\n                complete_ticket(claimed, "RQ-U07", resolution, fixed_now())\n'''
            )
        )
        self.assertFalse(
            u07_remediation_test_is_exact(
                capstone_test.replace(
                    b"    def test_u07_rejects_control_characters_in_resolution",
                    b"    @unittest.skip('bypass')\n    def test_u07_rejects_control_characters_in_resolution",
                )
            )
        )

    def test_capstone_source_contract_rejects_a_string_shaped_nonimplementation(self) -> None:
        fake = b'''def complete_ticket(tickets, ticket_id, resolution, now):
    note = "if any(ord(character) < 32 or ord(character) == 127 for character in resolution): raise ValueError('resolution must not contain control characters')"
    return tickets
'''
        self.assertFalse(u07_remediation_source_is_exact(fake))

    def test_checkpoint_marks_the_retired_capstone_unavailable(self) -> None:
        checkpoint = json.loads(
            (SOURCE / "academy/checkpoints/U07-capstone.json").read_text(encoding="utf-8")
        )
        predicate = checkpoint["predicates"][0]
        self.assertEqual(
            predicate,
            {
                "id": "unavailable_until_accepted",
                "type": "lab_semantics",
                "profile": "unavailable",
            },
        )

    def test_retired_capstone_cannot_prepare_or_accept_a_local_history(self) -> None:
        fixture = AcademyRepository()
        self.addCleanup(fixture.close)
        fixture.add_safe_upstream()
        with self.assertRaisesRegex(PreparationError, "not accepted"):
            prepare_lab(fixture.root, LAB)

        self.assertEqual(git(fixture.root, "status", "--porcelain", "--untracked-files=all").stdout, "")

    def test_private_source_renders_for_review_but_is_excluded_from_every_preview_lifecycle_inventory(self) -> None:
        document = preview_site._read_markdown_document(
            SOURCE,
            Path("academy/tracks/power-user/U07-capstone.md"),
            LAB,
            require_h1=True,
        )
        self.assertIn('data-action-id="U07-read-private-boundary"', document["content"])
        self.assertIn('data-action-id="U07-check-refusal"', document["content"])
        manifest = load_preview_manifest(SOURCE)
        for inventory in (manifest.available_labs, manifest.runnable_labs, manifest.guided_labs):
            self.assertNotIn(LAB, inventory)
        self.assertIn(LAB, manifest.coming_next)
        with self.assertRaisesRegex(ValueError, "not runnable"):
            require_runnable_lab(SOURCE, LAB)
        with self.assertRaisesRegex(ValueError, "not guided"):
            require_guided_lab(SOURCE, LAB)
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "site"
            build_preview_site(SOURCE, output, release_sha="7" * 40)
            self.assertFalse((output / "power-user/U07-capstone/index.html").exists())
            lifecycle = json.loads((output / "release.json").read_text(encoding="utf-8"))
            self.assertNotIn(LAB, lifecycle["guided_labs"])
            self.assertIn(LAB, lifecycle["coming_next"])
