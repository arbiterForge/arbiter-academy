from __future__ import annotations

import hashlib
import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import scripts.build_preview_site as preview_site
from scripts.build_preview_site import build_preview_site


def build_and_list_html(root: Path, out: Path) -> list[Path]:
    build_preview_site(root, out, release_sha="1" * 40)
    return sorted(out.rglob("*.html"))


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

    def test_build_emits_the_exact_reviewed_file_inventory_and_index_boundary(self) -> None:
        """Catches an unreviewed page, link, or status entry reaching the public artifact."""
        build_preview_site(self.root, self.out, release_sha="f" * 40)

        expected_labs = (
            "F01-fork-clone-doctor",
            "F02-orient-to-state",
            "F03-work-the-board",
            "F04-fix-with-evidence",
            "P01-feature-through-plan",
            "P02-commit-review-pr",
            "P03-record-an-adr",
            "P04-review-a-dependency",
        )
        expected_files = {
            "index.html",
            "recovery/index.html",
            "release.json",
            *(f"labs/{lab_id}/index.html" for lab_id in expected_labs),
        }
        actual_files = {
            path.relative_to(self.out).as_posix()
            for path in self.out.rglob("*")
            if path.is_file()
        }
        self.assertEqual(actual_files, expected_files)

        index = (self.out / "index.html").read_text(encoding="utf-8")
        expected_links = [f'labs/{lab_id}/index.html' for lab_id in expected_labs]
        actual_links = re.findall(r'href="(labs/[^\"]+/index\.html)"', index)
        self.assertEqual(actual_links, expected_links)
        self.assertEqual(
            re.findall(r"<li>([^<]+) \u2014 in verification</li>", index),
            ["P05", "P06", "P07"],
        )
        for future_lab in (
            "P05-checkpoint-remediation",
            "P06-context-drift-recovery",
            "P07-threat-model",
        ):
            self.assertFalse((self.out / "labs" / future_lab / "index.html").exists())
            self.assertNotIn(future_lab, index)

    def test_rendered_inventory_rejects_destinations_outside_the_approved_file_set(self) -> None:
        """Catches a future renderer adding a private, absolute, or traversing destination."""
        approved = {Path("index.html"), Path("release.json")}
        for rendered in (
            {Path("index.html"): "home"},
            {Path("index.html"): "home", Path("academy/catalog.json"): "private"},
            {Path("index.html"): "home", Path("../outside.html"): "outside"},
            {Path("index.html"): "home", Path.cwd() / "absolute.html": "absolute"},
        ):
            with self.assertRaisesRegex(ValueError, "rendered"):
                preview_site._validate_rendered_inventory(rendered, approved)

    def test_build_rejects_an_unapproved_renderer_destination_before_writing(self) -> None:
        """Catches a future renderer bypassing the reviewed output inventory."""
        with patch.object(
            preview_site,
            "_render_pages",
            return_value={Path("academy/catalog.json"): "private"},
        ):
            with self.assertRaisesRegex(ValueError, "rendered"):
                build_preview_site(self.root, self.out, release_sha="0" * 40)
        self.assertFalse(self.out.exists())

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

    def test_every_generated_page_has_landmarks_skip_link_and_single_h1(self) -> None:
        """Catches a generated page that keyboard or screen-reader users cannot orient within."""
        pages = build_and_list_html(self.root, self.out)

        for page in pages:
            with self.subTest(page=page.relative_to(self.out)):
                html = page.read_text(encoding="utf-8")
                self.assertEqual(html.count("<h1"), 1)
                self.assertIn('href="#main-content"', html)
                self.assertIn('<header class="site-header">', html)
                self.assertIn('<nav aria-label="Primary">', html)
                self.assertIn('<main id="main-content"', html)
                self.assertIn('<footer class="site-footer">', html)

    def test_generated_site_uses_only_local_assets(self) -> None:
        """Catches a runtime third-party request or drift from the reviewed local font bytes."""
        pages = build_and_list_html(self.root, self.out)
        for page in pages:
            html = page.read_text(encoding="utf-8")
            self.assertNotRegex(
                html,
                r'(?:src|href)=["\']https?://[^"\']+\.(?:css|js|woff2?)["\']',
            )

        index = (self.out / "index.html").read_text(encoding="utf-8")
        self.assertIn('href="/assets/academy.css"', index)

        asset_root = self.root / "site" / "assets"
        stylesheet = asset_root / "academy.css"
        self.assertTrue(stylesheet.is_file())
        css = stylesheet.read_text(encoding="utf-8")
        self.assertNotRegex(css, r"url\(\s*[\"']?https?://")

        expected_font_hashes = {
            "manrope-latin-wght-normal.woff2": "a30ddcd349703aff7464c34bef3fffdff405ee50c113440d7c8693c02d210972",
            "jetbrains-mono-latin-wght-normal.woff2": "18be452724bfdc236c074ca94a249a7f41a86752c7d04ab258ce9ed5651f6a7e",
        }
        for filename, expected_hash in expected_font_hashes.items():
            with self.subTest(font=filename):
                font = asset_root / "fonts" / filename
                self.assertTrue(font.is_file())
                self.assertEqual(hashlib.sha256(font.read_bytes()).hexdigest(), expected_hash)

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
