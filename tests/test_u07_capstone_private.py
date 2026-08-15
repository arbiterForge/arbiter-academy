from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from academy_engine.preview import load_preview_manifest, require_guided_lab, require_runnable_lab
from academy_engine.checkpoints import evaluate_checkpoint
from academy_engine.scenario import prepare_lab
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

    def test_checkpoint_binds_real_feature_artifacts_without_a_pr_receipt(self) -> None:
        checkpoint = json.loads(
            (SOURCE / "academy/checkpoints/U07-capstone.json").read_text(encoding="utf-8")
        )
        predicate = checkpoint["predicates"][0]
        self.assertEqual(
            predicate,
            {"id": "feature_capstone_range", "type": "lab_semantics", "profile": "feature_capstone", "code": "workshop_queue/service.py", "test": "tests/test_service.py"},
        )

    def test_prepare_creates_a_bounded_real_feature_fixture(self) -> None:
        fixture = AcademyRepository()
        self.addCleanup(fixture.close)
        fixture.add_safe_upstream()
        prepared = prepare_lab(fixture.root, LAB)
        self.assertEqual(prepared.branch, "academy/U07-capstone/1")
        self.assertIn(
            "test_u07_prepared_resolution_control_is_accepted",
            (fixture.root / "tests/test_service.py").read_text(encoding="utf-8"),
        )

        self.assertEqual(git(fixture.root, "status", "--porcelain", "--untracked-files=all").stdout, "")

    def test_check_accepts_real_small_lane_evidence_without_a_pr_receipt(self) -> None:
        """The valid two-file small lane has a triage record, not invented full-lane documents."""
        fixture = AcademyRepository()
        self.addCleanup(fixture.close)
        fixture.add_safe_upstream()
        prepare_lab(fixture.root, LAB)

        test_path = fixture.root / "tests/test_service.py"
        prepared_test = test_path.read_text(encoding="utf-8")
        start = prepared_test.index("    def test_u07_prepared_resolution_control_is_accepted")
        end = prepared_test.index("\n\nif __name__ == \"__main__\":", start)
        test_path.write_text(
            prepared_test[:start]
            + "    def test_u07_rejects_control_characters_in_resolution(self) -> None:\n"
            + "        claimed = claim_ticket([open_ticket(\"RQ-U07\")], \"RQ-U07\", \"Sam\", fixed_now())\n"
            + "        for resolution in (\"done\\nagain\", \"done\\tagain\", \"done\\x7fagain\"):\n"
            + "            with self.subTest(resolution=repr(resolution)):\n"
            + "                with self.assertRaisesRegex(ValueError, \"control characters\"):\n"
            + "                    complete_ticket(claimed, \"RQ-U07\", resolution, fixed_now())\n"
            + prepared_test[end:],
            encoding="utf-8",
        )
        service_path = fixture.root / "workshop_queue/service.py"
        service = service_path.read_text(encoding="utf-8")
        marker = '            if not resolution.strip():\n                raise ValueError("resolution must be non-empty")\n'
        service_path.write_text(
            service.replace(
                marker,
                marker
                + '            if any(ord(character) < 32 or ord(character) == 127 for character in resolution):\n'
                + '                raise ValueError("resolution must not contain control characters")\n',
                1,
            ),
            encoding="utf-8",
        )
        triage = fixture.root / ".codearbiter/triage.log"
        triage.write_text(
            "[2026-08-15T00:00:00Z] | BY: learner@example.test | LANE: small | SCOPE: reject control characters in ticket resolutions | BASIS: two files, no public surface, three testable criteria\n",
            encoding="utf-8",
        )
        fixture.commit("feature: reject control characters", triage.relative_to(fixture.root).as_posix(), "tests/test_service.py", "workshop_queue/service.py")

        result = evaluate_checkpoint(fixture.root, LAB)
        self.assertTrue(result.passed, result)

        (fixture.root / "README.md").write_text("copied spike code\n", encoding="utf-8")
        fixture.commit("feature: unrelated transfer", "README.md")
        self.assertFalse(evaluate_checkpoint(fixture.root, LAB).passed)

    def test_public_source_renders_as_the_complete_preview_capstone(self) -> None:
        document = preview_site._read_markdown_document(
            SOURCE,
            Path("academy/tracks/power-user/U07-capstone.md"),
            LAB,
            require_h1=True,
        )
        self.assertIn('data-action-id="U07-run-feature"', document["content"])
        self.assertIn('data-action-id="U07-open-pr"', document["content"])
        manifest = load_preview_manifest(SOURCE)
        for inventory in (manifest.available_labs, manifest.runnable_labs, manifest.guided_labs):
            self.assertIn(LAB, inventory)
        self.assertNotIn(LAB, manifest.coming_next)
        require_runnable_lab(SOURCE, LAB)
        require_guided_lab(SOURCE, LAB)
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "site"
            build_preview_site(SOURCE, output, release_sha="7" * 40)
            self.assertTrue((output / "labs/U07-capstone/index.html").is_file())
            lifecycle = json.loads((output / "release.json").read_text(encoding="utf-8"))
            self.assertIn(LAB, lifecycle["guided_labs"])
            self.assertNotIn(LAB, lifecycle["coming_next"])
