from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from scripts.build_preview_site import build_preview_site


class PreviewSiteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(__file__).parents[1]
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.out = Path(self.temporary_directory.name) / "generated"

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_build_emits_only_eligible_labs_and_nonlinked_coming_next_status(self) -> None:
        """Catches a future lab being published or linked as available."""
        build_preview_site(self.root, self.out, release_sha="a" * 40)

        self.assertTrue((self.out / "labs" / "P04-review-a-dependency" / "index.html").is_file())
        self.assertFalse((self.out / "labs" / "P05-checkpoint-remediation" / "index.html").exists())
        index = (self.out / "index.html").read_text(encoding="utf-8")
        self.assertIn("P05 \u2014 in verification", index)
        self.assertNotIn('href="labs/P05-checkpoint-remediation/', index)

    def test_release_json_uses_build_time_sha_and_never_copies_internal_catalog(self) -> None:
        """Catches release provenance drift or publication of the private catalog."""
        build_preview_site(self.root, self.out, release_sha="b" * 40)

        self.assertEqual(json.loads((self.out / "release.json").read_text(encoding="utf-8"))["commit"], "b" * 40)
        self.assertFalse((self.out / "academy" / "catalog.json").exists())

    def test_build_renders_only_public_lesson_metadata(self) -> None:
        """Catches a lab page leaking private lesson body or omitting its public next step."""
        build_preview_site(self.root, self.out, release_sha="c" * 40)

        page = (self.out / "labs" / "P04-review-a-dependency" / "index.html").read_text(encoding="utf-8")
        self.assertIn("Review a real dependency before installation", page)
        self.assertIn("Make a complete SMARTS-backed accept or reject decision", page)
        self.assertIn("Continue with P05 when it enters verification.", page)
        self.assertNotIn("Candidate-Artifact", page)

    def test_build_rejects_a_missing_eligible_lesson(self) -> None:
        """Catches a partial publication when a manifest-selected lesson is absent."""
        source = self._copy_public_source()
        (source / "academy" / "tracks" / "foundations" / "F01-fork-clone-doctor.md").unlink()

        with self.assertRaisesRegex(ValueError, "eligible lesson"):
            build_preview_site(source, self.out, release_sha="d" * 40)

    def test_build_rejects_malformed_sha_and_unexpected_generated_path(self) -> None:
        """Catches untraceable releases and stale output outside the approved artifact set."""
        with self.assertRaisesRegex(ValueError, "ACADEMY_RELEASE_SHA"):
            build_preview_site(self.root, self.out, release_sha="not-a-sha")

        self.out.mkdir()
        (self.out / "unreviewed.html").write_text("stale", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "unexpected generated path"):
            build_preview_site(self.root, self.out, release_sha="e" * 40)

    def _copy_public_source(self) -> Path:
        source = Path(self.temporary_directory.name) / "source"
        academy = source / "academy"
        (academy / "publication").mkdir(parents=True)
        shutil.copy2(self.root / "academy" / "catalog.json", academy / "catalog.json")
        shutil.copy2(self.root / "academy" / "catalog.schema.json", academy / "catalog.schema.json")
        shutil.copy2(
            self.root / "academy" / "publication" / "preview-0.1.json",
            academy / "publication" / "preview-0.1.json",
        )
        for track in ("foundations", "practitioner"):
            shutil.copytree(
                self.root / "academy" / "tracks" / track,
                academy / "tracks" / track,
            )
        shutil.copytree(self.root / "site" / "templates", source / "site" / "templates")
        return source


if __name__ == "__main__":
    unittest.main()
