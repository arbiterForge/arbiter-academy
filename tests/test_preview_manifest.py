from __future__ import annotations

import hashlib
import unittest
from pathlib import Path

from academy_engine.preview import load_preview_manifest, validate_preview_manifest


PREVIEW_0_1 = [
    "F01-fork-clone-doctor",
    "F02-orient-to-state",
    "F03-work-the-board",
    "F04-fix-with-evidence",
    "P01-feature-through-plan",
    "P02-commit-review-pr",
    "P03-record-an-adr",
    "P04-review-a-dependency",
]
COMING_NEXT = [
    "P05-checkpoint-remediation",
    "P06-context-drift-recovery",
    "P07-threat-model",
]


class PreviewManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(__file__).parents[1]

    def make_manifest(self, **changes: object) -> dict[str, object]:
        manifest: dict[str, object] = {
            "release": "preview-0.1",
            "available_labs": PREVIEW_0_1,
            "coming_next": COMING_NEXT,
            "catalog_sha256": hashlib.sha256(
                (self.root / "academy" / "catalog.json").read_bytes()
            ).hexdigest(),
        }
        manifest.update(changes)
        return manifest

    def test_preview_manifest_requires_the_full_prerequisite_closure(self) -> None:
        """Catches publication of a lab whose required learning path is absent."""
        manifest = self.make_manifest(available_labs=["P04-review-a-dependency"])

        with self.assertRaisesRegex(ValueError, "missing prerequisite"):
            validate_preview_manifest(self.root, manifest)

    def test_preview_manifest_rejects_an_unavailable_future_lab(self) -> None:
        """Catches a future lab being relabeled as available in this release."""
        manifest = self.make_manifest(
            available_labs=PREVIEW_0_1 + ["P05-checkpoint-remediation"]
        )

        with self.assertRaisesRegex(ValueError, "not eligible"):
            validate_preview_manifest(self.root, manifest)

    def test_preview_manifest_requires_the_reviewed_available_and_status_only_lists(self) -> None:
        """Catches omission or substitution in the public Preview 0.1 boundary."""
        manifest = self.make_manifest(coming_next=["P05-checkpoint-remediation"])

        with self.assertRaisesRegex(ValueError, "coming_next"):
            validate_preview_manifest(self.root, manifest)

    def test_preview_manifest_rejects_catalog_drift(self) -> None:
        """Catches a tracked selection becoming detached from the raw catalog bytes."""
        manifest = self.make_manifest(catalog_sha256="0" * 64)

        with self.assertRaisesRegex(ValueError, "catalog_sha256"):
            validate_preview_manifest(self.root, manifest)

    def test_load_preview_manifest_returns_the_reviewed_public_boundary(self) -> None:
        """Catches a checked-in manifest that does not represent the reviewed release."""
        manifest = load_preview_manifest(self.root)

        self.assertEqual(manifest.release, "preview-0.1")
        self.assertEqual(manifest.available_labs, tuple(PREVIEW_0_1))
        self.assertEqual(manifest.coming_next, tuple(COMING_NEXT))


if __name__ == "__main__":
    unittest.main()
