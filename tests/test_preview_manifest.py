from __future__ import annotations

import hashlib
import json
import re
import tempfile
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
DISCUSSION_URL = "https://github.com/arbiterForge/arbiter-academy/discussions"


class PreviewManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(__file__).parents[1]

    def make_manifest(self, root: Path | None = None, **changes: object) -> dict[str, object]:
        root = root or self.root
        manifest: dict[str, object] = {
            "release": "preview-0.1",
            "available_labs": PREVIEW_0_1,
            "coming_next": COMING_NEXT,
            "discussion_url": DISCUSSION_URL,
            "catalog_sha256": hashlib.sha256(
                (root / "academy" / "catalog.json").read_bytes()
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

    def test_preview_manifest_accepts_only_the_reviewed_discussions_url_boundary(self) -> None:
        """Catches feedback routing to insecure, lookalike, or unrelated GitHub destinations."""
        accepted = (
            DISCUSSION_URL,
            f"{DISCUSSION_URL}/categories/general",
        )
        rejected = (
            None,
            f"http://github.com/arbiterForge/arbiter-academy/discussions",
            "https://github.com/arbiterForge/arbiter-academy/issues",
            "https://github.com.evil.example/arbiterForge/arbiter-academy/discussions",
            f"{DISCUSSION_URL}-archive",
            f"{DISCUSSION_URL}/..\\issues",
            f"{DISCUSSION_URL}/%5c..%5cissues",
            f"{DISCUSSION_URL}/%2e%2e/issues",
            f"\x00{DISCUSSION_URL}",
            DISCUSSION_URL.replace("discussions", "discus\tsions"),
            DISCUSSION_URL.replace("discussions", "discus\nsions"),
        )
        schema = json.loads(
            (self.root / "academy" / "publication" / "preview-manifest.schema.json").read_text(
                encoding="utf-8"
            )
        )
        schema_pattern = schema["properties"]["discussion_url"]["pattern"]

        for discussion_url in accepted:
            with self.subTest(accepted=discussion_url):
                self.assertIsNotNone(re.fullmatch(schema_pattern, discussion_url))
                manifest = validate_preview_manifest(
                    self.root,
                    self.make_manifest(discussion_url=discussion_url),
                )
                self.assertEqual(manifest.discussion_url, discussion_url)

        for discussion_url in rejected:
            with self.subTest(rejected=discussion_url):
                if isinstance(discussion_url, str):
                    self.assertIsNone(re.fullmatch(schema_pattern, discussion_url))
                with self.assertRaisesRegex(ValueError, "discussion_url"):
                    validate_preview_manifest(
                        self.root,
                        self.make_manifest(discussion_url=discussion_url),
                    )

    def test_preview_manifest_rejects_a_catalog_schema_with_drifted_pinned_inventory(self) -> None:
        """Catches catalog-schema pins no longer matching the catalog the preview publishes."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            academy = root / "academy"
            academy.mkdir()
            for name in ("catalog.json", "catalog.schema.json"):
                (academy / name).write_bytes((self.root / "academy" / name).read_bytes())
            schema_path = academy / "catalog.schema.json"
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            schema["properties"]["labs"]["prefixItems"][0]["properties"]["id"]["const"] = "F99-schema-drift"
            schema_path.write_text(json.dumps(schema), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "catalog schema"):
                validate_preview_manifest(root, self.make_manifest(root))

    def test_preview_manifest_rejects_a_boolean_schema_order_pin(self) -> None:
        """Catches JSON Schema treating a boolean order pin as catalog integer 1."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            academy = root / "academy"
            academy.mkdir()
            for name in ("catalog.json", "catalog.schema.json"):
                (academy / name).write_bytes((self.root / "academy" / name).read_bytes())
            schema_path = academy / "catalog.schema.json"
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            schema["properties"]["labs"]["prefixItems"][0]["properties"]["order"]["const"] = True
            schema_path.write_text(json.dumps(schema), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "catalog schema"):
                validate_preview_manifest(root, self.make_manifest(root))

    def test_load_preview_manifest_returns_the_reviewed_public_boundary(self) -> None:
        """Catches a checked-in manifest that does not represent the reviewed release."""
        manifest = load_preview_manifest(self.root)

        self.assertEqual(manifest.release, "preview-0.1")
        self.assertEqual(manifest.available_labs, tuple(PREVIEW_0_1))
        self.assertEqual(manifest.coming_next, tuple(COMING_NEXT))
        self.assertEqual(manifest.discussion_url, DISCUSSION_URL)


if __name__ == "__main__":
    unittest.main()
