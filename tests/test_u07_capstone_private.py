from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from academy_engine.checkpoints import evaluate_checkpoint
from academy_engine.preview import load_preview_manifest, require_guided_lab, require_runnable_lab
from academy_engine.scenario import prepare_lab
from academy_engine.u07_fixture import u07_remediation_source_is_exact, u07_remediation_test_is_exact
from scripts import build_preview_site as preview_site
from scripts.build_preview_site import build_preview_site
from tests.test_foundations_labs import AcademyRepository, git


SOURCE = Path(__file__).resolve().parents[1]
LAB = "U07-capstone"
SPEC = ".codearbiter/specs/capstone.md"
PLAN = ".codearbiter/plans/capstone.md"
ADR = ".codearbiter/decisions/0004-capstone.md"
TEST = "tests/test_service.py"
CODE = "workshop_queue/service.py"


class U07PrivateCapstoneTests(unittest.TestCase):
    def _write(self, root: Path, relative: str, text: str) -> None:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")

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

    def test_checkpoint_requires_only_real_plugin_artifacts_and_live_repository_facts(self) -> None:
        checkpoint = json.loads(
            (SOURCE / "academy/checkpoints/U07-capstone.json").read_text(encoding="utf-8")
        )
        predicate = checkpoint["predicates"][0]
        self.assertEqual(
            set(predicate),
            {"id", "type", "profile", "spec_directory", "plan_directory", "adr_directory", "code", "test"},
        )
        encoded = json.dumps(predicate, sort_keys=True).casefold()
        for invented_claim in ("review", "receipt", "submission", "secret_scan", "reviewers", "pull request"):
            self.assertNotIn(invented_claim, encoded)

    def test_prepare_then_bounded_history_then_check_is_local_and_nonvacuous(self) -> None:
        fixture = AcademyRepository()
        self.addCleanup(fixture.close)
        fixture.add_safe_upstream()
        prepared = prepare_lab(fixture.root, LAB)
        self.assertEqual(prepared.branch, "academy/U07-capstone/1")

        prepared_test = (fixture.root / TEST).read_text(encoding="utf-8")
        self.assertIn("test_u07_prepared_resolution_control_is_accepted", prepared_test)

        self._write(fixture.root, SPEC, "# Capstone specification\n\n## Problem\n\nReject control characters in ticket resolutions.\n\n## Acceptance criteria\n\n- A resolution with a control character is rejected.\n")
        self._write(fixture.root, PLAN, "# Capstone plan\n\n## Plan\n\n1. Change the focused regression.\n2. Validate the service input.\n\n## Verification\n\n`python -m unittest tests.test_service`\n")
        self._write(fixture.root, ADR, "# ADR-0004: Resolution controls\n\n## Decision\n\nReject control characters in resolutions.\n\n## Consequences\n\nThe service boundary becomes explicit.\n")
        fixture.commit("record capstone scope", SPEC, PLAN, ADR)

        replacement = '''    def test_u07_rejects_control_characters_in_resolution(self) -> None:
        claimed = claim_ticket([open_ticket("RQ-U07")], "RQ-U07", "Sam", fixed_now())
        for resolution in ("done\\nagain", "done\\tagain", "done\\x7fagain"):
            with self.subTest(resolution=repr(resolution)):
                with self.assertRaisesRegex(ValueError, "control characters"):
                    complete_ticket(claimed, "RQ-U07", resolution, fixed_now())
\n'''
        start = prepared_test.index("    def test_u07_prepared_resolution_control_is_accepted")
        end = prepared_test.index("\n\nif __name__ == \"__main__\":", start)
        self._write(fixture.root, TEST, prepared_test[:start] + replacement + prepared_test[end:])
        fixture.commit("test capstone resolution boundary", TEST)

        service = (fixture.root / CODE).read_text(encoding="utf-8")
        needle = '            if not resolution.strip():\n                raise ValueError("resolution must be non-empty")\n'
        self.assertIn(needle, service)
        self._write(
            fixture.root,
            CODE,
            service.replace(
                needle,
                needle + '            if any(ord(character) < 32 or ord(character) == 127 for character in resolution):\n                raise ValueError("resolution must not contain control characters")\n',
                1,
            ),
        )
        candidate = fixture.commit("implement capstone resolution boundary", CODE)
        self.assertTrue(u07_remediation_test_is_exact((fixture.root / TEST).read_bytes()))
        self.assertTrue(u07_remediation_source_is_exact((fixture.root / CODE).read_bytes()))
        result = evaluate_checkpoint(fixture.root, LAB)
        self.assertTrue(result.passed, result.failed_predicates)

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
