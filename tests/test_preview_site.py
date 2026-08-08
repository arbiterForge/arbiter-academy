from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit

import scripts.build_preview_site as preview_site
import scripts.check_preview_site as preview_checker
from scripts.build_preview_site import build_preview_site
from scripts.check_preview_site import check_preview_site


def build_and_list_html(root: Path, out: Path) -> list[Path]:
    build_preview_site(root, out, release_sha="1" * 40)
    return sorted(out.rglob("*.html"))


def read_home(root: Path, out: Path) -> str:
    build_preview_site(root, out, release_sha="1" * 40)
    return (out / "index.html").read_text(encoding="utf-8")


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

    def test_home_names_fork_before_clone_and_never_invites_push_to_official_origin(self) -> None:
        """Catches onboarding that starts from or sends learner work to the canonical repository."""
        html = read_home(self.root, self.out)

        self.assertIn("Fork the Academy", html)
        self.assertIn("your fork", html)
        self.assertLess(html.index("Fork the Academy"), html.index("Clone your fork"))
        self.assertIn(
            "git clone https://github.com/&lt;your-account&gt;/arbiter-academy.git",
            html,
        )
        self.assertNotIn("push to arbiterForge/arbiter-academy", html)

    def test_home_states_preview_scope_prerequisites_pacing_and_exact_workflow(self) -> None:
        """Catches public guidance that overstates the preview or omits its runnable workflow."""
        html = read_home(self.root, self.out)

        self.assertIn("eight available labs", html)
        self.assertIn("20–35 minutes", html)
        self.assertIn("Git", html)
        self.assertIn("codeArbiter", html)
        self.assertIn("P05–P07 are status-only", html)
        self.assertIn("Power User labs are not included", html)
        for operation in ("prepare", "check", "reset"):
            self.assertIn(
                f"arbiter-academy --repository &lt;learner-repository&gt; {operation} &lt;lab-id&gt;",
                html,
            )
        self.assertIn('href="recovery/index.html"', html)

    def test_home_workflow_is_one_semantic_five_step_ordered_list(self) -> None:
        """Catches visual numbering that exposes no ordered-list structure to assistive tech."""
        html = read_home(self.root, self.out)
        workflow = html.split("<h2>Start safely</h2>", 1)[1].split(
            '<p>The installed verifier is the trust anchor.', 1
        )[0]

        self.assertEqual(workflow.count("<ol>"), 1)
        self.assertEqual(workflow.count("</ol>"), 1)
        self.assertEqual(workflow.count("<li>"), 5)
        self.assertEqual(workflow.count("</li>"), 5)
        self.assertNotRegex(workflow, r"<strong>[1-5]\. ")

    def test_feedback_url_is_https_github_discussions_and_is_rendered(self) -> None:
        """Catches feedback being hidden or routed away from the reviewed Discussions boundary."""
        html = read_home(self.root, self.out)

        self.assertIn(
            'href="https://github.com/arbiterForge/arbiter-academy/discussions"',
            html,
        )

    def test_build_rejects_missing_or_out_of_boundary_discussion_url_before_writing(self) -> None:
        """Catches a missing or attacker-controlled feedback destination reaching generated HTML."""
        source = self._copy_public_source()
        manifest_path = source / "academy" / "publication" / "preview-0.1.json"
        original = json.loads(manifest_path.read_text(encoding="utf-8"))
        invalid_urls = (
            None,
            "http://github.com/arbiterForge/arbiter-academy/discussions",
            "https://github.com/arbiterForge/arbiter-academy/issues",
            "https://github.com.evil.example/arbiterForge/arbiter-academy/discussions",
            "https://github.com/arbiterForge/arbiter-academy/discussions-archive",
            "https://github.com/arbiterForge/arbiter-academy/discussions/..\\issues",
            "https://github.com/arbiterForge/arbiter-academy/discussions/%5c..%5cissues",
            "https://github.com/arbiterForge/arbiter-academy/discussions/%2e%2e/issues",
            "\x00https://github.com/arbiterForge/arbiter-academy/discussions",
            "https://github.com/arbiterForge/arbiter-academy/discus\tsions",
            "https://github.com/arbiterForge/arbiter-academy/discus\nsions",
        )

        for index, discussion_url in enumerate(invalid_urls):
            with self.subTest(discussion_url=discussion_url):
                manifest = dict(original)
                if discussion_url is None:
                    manifest.pop("discussion_url", None)
                else:
                    manifest["discussion_url"] = discussion_url
                manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
                destination = self.out.parent / f"invalid-{index}"
                with self.assertRaisesRegex(ValueError, "discussion_url"):
                    build_preview_site(source, destination, release_sha="2" * 40)
                self.assertFalse(destination.exists())

    def test_recovery_page_preserves_evidence_and_routes_prepare_check_reset(self) -> None:
        """Catches recovery guidance that hides evidence or treats an in-checkout check as trusted."""
        build_preview_site(self.root, self.out, release_sha="3" * 40)
        html = (self.out / "recovery" / "index.html").read_text(encoding="utf-8")

        self.assertIn("Preserve the failed attempt", html)
        self.assertIn(
            "arbiter-academy --repository &lt;learner-repository&gt; check &lt;lab-id&gt;",
            html,
        )
        self.assertIn(
            "arbiter-academy --repository &lt;learner-repository&gt; reset &lt;lab-id&gt;",
            html,
        )
        self.assertIn("installed verifier", html)
        self.assertIn("your fork", html)
        self.assertIn(
            "Reset already prepares the next numbered attempt; do not run prepare again.",
            html,
        )

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
            "assets/academy.css",
            "assets/fonts/jetbrains-mono-latin-wght-normal.woff2",
            "assets/fonts/manrope-latin-wght-normal.woff2",
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

    def test_build_cli_honors_output_and_release_sha(self) -> None:
        """Catches the release workflow arguments being ignored by the real script entry point."""
        release_sha = "4" * 40
        result = subprocess.run(
            [
                sys.executable,
                "scripts/build_preview_site.py",
                "--output",
                str(self.out),
                "--release-sha",
                release_sha,
            ],
            cwd=self.root,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(
            json.loads((self.out / "release.json").read_text(encoding="utf-8")),
            {"release": "preview-0.1", "commit": release_sha},
        )

    def test_build_copies_only_the_reviewed_runtime_assets(self) -> None:
        """Catches Pages artifacts that omit fonts/CSS or publish unreviewed source assets."""
        build_preview_site(self.root, self.out, release_sha="5" * 40)

        actual_assets = {
            path.relative_to(self.out).as_posix()
            for path in (self.out / "assets").rglob("*")
            if path.is_file()
        }
        self.assertEqual(
            actual_assets,
            {
                "assets/academy.css",
                "assets/fonts/jetbrains-mono-latin-wght-normal.woff2",
                "assets/fonts/manrope-latin-wght-normal.woff2",
            },
        )
        for relative in actual_assets:
            self.assertEqual(
                (self.out / relative).read_bytes(),
                (self.root / "site" / relative).read_bytes(),
            )

    def test_generated_internal_urls_are_project_pages_safe_and_resolve(self) -> None:
        """Catches root-relative links that escape the /arbiter-academy Pages prefix."""
        pages = build_and_list_html(self.root, self.out)

        for page in pages:
            html = page.read_text(encoding="utf-8")
            for target in re.findall(r'(?:href|src)=["\']([^"\']+)', html):
                parsed = urlsplit(target)
                if parsed.scheme in {"http", "https"} or target.startswith("#"):
                    continue
                with self.subTest(page=page.relative_to(self.out), target=target):
                    self.assertFalse(parsed.path.startswith("/"), target)
                    resolved = (page.parent / parsed.path).resolve()
                    resolved.relative_to(self.out.resolve())
                    self.assertTrue(resolved.is_file(), target)

    def test_static_checker_accepts_the_artifact_then_rejects_a_broken_local_link(self) -> None:
        """Catches a release checker that passes missing project-local destinations."""
        build_preview_site(self.root, self.out, release_sha="6" * 40)
        command = [sys.executable, "scripts/check_preview_site.py", str(self.out)]

        accepted = subprocess.run(
            command,
            cwd=self.root,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(accepted.returncode, 0, accepted.stdout + accepted.stderr)

        index = self.out / "index.html"
        index.write_text(
            index.read_text(encoding="utf-8").replace(
                'href="recovery/index.html"',
                'href="missing/index.html"',
                1,
            ),
            encoding="utf-8",
        )
        rejected = subprocess.run(
            command,
            cwd=self.root,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(rejected.returncode, 0)
        self.assertIn("broken internal link", rejected.stderr)

    def test_build_rejects_redirected_output_paths_before_external_write(self) -> None:
        """Catches output roots, expected leaves, or directories redirected outside the artifact."""
        cases = ("output-root", "expected-leaf", "expected-directory")
        for case in cases:
            with self.subTest(case=case):
                destination = self.out.parent / case
                outside = self.out.parent / f"outside-{case}"
                outside.mkdir()
                sentinel = outside / "index.html"
                sentinel.write_bytes(b"external sentinel")
                redirect: Path

                if case == "output-root":
                    redirect = destination
                    self._make_directory_redirect(redirect, outside)
                elif case == "expected-leaf":
                    destination.mkdir()
                    redirect = destination / "index.html"
                    try:
                        redirect.symlink_to(sentinel)
                    except OSError as error:
                        self.skipTest(f"file symlinks are unavailable: {error}")
                else:
                    (destination / "labs").mkdir(parents=True)
                    redirect = destination / "labs" / "F01-fork-clone-doctor"
                    try:
                        redirect.symlink_to(outside, target_is_directory=True)
                    except OSError as error:
                        self.skipTest(f"directory symlinks are unavailable: {error}")

                try:
                    with self.assertRaisesRegex(ValueError, "symlink or reparse"):
                        build_preview_site(self.root, destination, release_sha="7" * 40)
                    self.assertEqual(sentinel.read_bytes(), b"external sentinel")
                finally:
                    if os.path.lexists(redirect):
                        if redirect.is_dir() and not redirect.is_symlink():
                            os.rmdir(redirect)
                        else:
                            redirect.unlink()

    def test_static_checker_rejects_external_and_missing_local_css_import_forms(self) -> None:
        """Catches quoted or url() imports escaping the reviewed stylesheet inventory."""
        imports = (
            ('@import "https://assets.example/remote.css";', "unapproved external URL"),
            ('@import url("https://assets.example/remote.css");', "unapproved external URL"),
            (
                '@import "https://github.com/arbiterForge/arbiter-academy/discussions";',
                "unapproved external URL",
            ),
            ('@import "missing.css";', "broken internal link"),
            ('@import url("missing.css");', "broken internal link"),
        )
        for index, (directive, message) in enumerate(imports):
            with self.subTest(directive=directive):
                destination = self.out.parent / f"css-import-{index}"
                build_preview_site(self.root, destination, release_sha="8" * 40)
                stylesheet = destination / "assets" / "academy.css"
                stylesheet.write_text(
                    f"{directive}\n{stylesheet.read_text(encoding='utf-8')}",
                    encoding="utf-8",
                )
                with self.assertRaisesRegex(ValueError, message):
                    preview_checker._check_stylesheet_dependencies(
                        destination,
                        stylesheet,
                        stylesheet.read_text(encoding="utf-8"),
                    )

    def test_static_checker_rejects_a_symlink_artifact_root_before_resolve(self) -> None:
        """Catches resolving away the caller-supplied artifact-root trust boundary."""
        build_preview_site(self.root, self.out, release_sha="9" * 40)
        redirected = self.out.parent / "artifact-root-link"
        try:
            redirected.symlink_to(self.out, target_is_directory=True)
        except OSError as error:
            self.skipTest(f"directory symlinks are unavailable: {error}")
        try:
            with self.assertRaisesRegex(ValueError, "real directory"):
                check_preview_site(redirected)
        finally:
            if os.path.lexists(redirected):
                redirected.unlink()

    def test_build_rejects_a_redirected_output_ancestor_before_external_write(self) -> None:
        """Catches a safe-looking output leaf reached through an ancestor junction or symlink."""
        outside = self.out.parent / "outside-output-ancestor"
        destination = outside / "generated"
        destination.mkdir(parents=True)
        sentinel = destination / "index.html"
        sentinel.write_bytes(b"ancestor sentinel")
        redirected = self.out.parent / "redirected-output-parent"
        self._make_directory_redirect(redirected, outside)
        try:
            with self.assertRaisesRegex(ValueError, "symlink or reparse"):
                build_preview_site(
                    self.root,
                    redirected / "generated",
                    release_sha="a" * 40,
                )
            self.assertEqual(sentinel.read_bytes(), b"ancestor sentinel")
        finally:
            if os.path.lexists(redirected):
                if redirected.is_dir() and not redirected.is_symlink():
                    os.rmdir(redirected)
                else:
                    redirected.unlink()

    def test_static_checker_rejects_a_redirected_artifact_ancestor_before_resolve(self) -> None:
        """Catches resolving through a caller-supplied ancestor junction before inspection."""
        outside = self.out.parent / "outside-checker-ancestor"
        artifact = outside / "artifact"
        build_preview_site(self.root, artifact, release_sha="b" * 40)
        redirected = self.out.parent / "redirected-checker-parent"
        self._make_directory_redirect(redirected, outside)
        try:
            with self.assertRaisesRegex(ValueError, "symlink or reparse"):
                check_preview_site(redirected / "artifact")
        finally:
            if os.path.lexists(redirected):
                if redirected.is_dir() and not redirected.is_symlink():
                    os.rmdir(redirected)
                else:
                    redirected.unlink()

    def test_build_rejects_a_hardlinked_expected_leaf_before_external_write(self) -> None:
        """Catches writes through a shared leaf in the approved output inventory."""
        hardlink_output = self.out.parent / "hardlink-output"
        hardlink_output.mkdir()
        sentinel = self.out.parent / "hardlink-sentinel.html"
        sentinel.write_bytes(b"hardlink sentinel")
        os.link(sentinel, hardlink_output / "index.html")
        self.assertGreater(sentinel.stat().st_nlink, 1)

        with self.assertRaisesRegex(ValueError, "unshared regular file"):
            build_preview_site(self.root, hardlink_output, release_sha="c" * 40)
        self.assertEqual(sentinel.read_bytes(), b"hardlink sentinel")

    def test_build_rejects_a_nonregular_expected_leaf_before_write(self) -> None:
        """Catches a directory or other non-file occupying an approved output leaf."""
        nonregular_output = self.out.parent / "nonregular-output"
        nonregular_output.mkdir()
        (nonregular_output / "release.json").mkdir()
        with self.assertRaisesRegex(ValueError, "unshared regular file"):
            build_preview_site(self.root, nonregular_output, release_sha="d" * 40)

    def test_static_checker_pins_each_reviewed_runtime_asset_digest(self) -> None:
        """Catches any byte mutation in the exact CSS and font artifacts reviewed for Preview 0.1."""
        assets = (
            "assets/academy.css",
            "assets/fonts/jetbrains-mono-latin-wght-normal.woff2",
            "assets/fonts/manrope-latin-wght-normal.woff2",
        )
        for index, relative in enumerate(assets):
            with self.subTest(asset=relative):
                destination = self.out.parent / f"asset-digest-{index}"
                build_preview_site(self.root, destination, release_sha="e" * 40)
                asset = destination / relative
                content = asset.read_bytes()
                asset.write_bytes(content[:-1] + bytes((content[-1] ^ 1,)))
                with self.assertRaisesRegex(ValueError, "runtime asset digest mismatch"):
                    check_preview_site(destination)

    def test_static_checker_rejects_comment_case_and_escape_css_mutations_by_digest(self) -> None:
        """Catches CSS-tokenizer evasions without relying on parsing attacker-controlled CSS."""
        mutations = (
            '/* @import "https://assets.example/comment.css"; */',
            '@IMPORT "https://assets.example/case.css";',
            '@\\69 mport "https://assets.example/escape.css";',
        )
        for index, mutation in enumerate(mutations):
            with self.subTest(mutation=mutation):
                destination = self.out.parent / f"css-digest-{index}"
                build_preview_site(self.root, destination, release_sha="f" * 40)
                stylesheet = destination / "assets" / "academy.css"
                stylesheet.write_text(
                    f"{stylesheet.read_text(encoding='utf-8')}\n{mutation}\n",
                    encoding="utf-8",
                )
                with self.assertRaisesRegex(ValueError, "runtime asset digest mismatch"):
                    check_preview_site(destination)

    def test_static_checker_rejects_unapproved_html_fetch_surfaces(self) -> None:
        """Catches fetch-capable elements and attributes outside the reviewed HTML vocabulary."""
        discussion = "https://github.com/arbiterForge/arbiter-academy/discussions"
        injections = (
            f'<a href="#main-content" srcset="{discussion} 1x">source set</a>',
            f'<p style="background-image: url({discussion})">inline style</p>',
            f'<style>@import "{discussion}";</style>',
            f'<script src="{discussion}"></script>',
            f'<img src="{discussion}" alt="external image">',
            f'<link rel="stylesheet" href="{discussion}">',
        )
        for index, injection in enumerate(injections):
            with self.subTest(injection=injection):
                destination = self.out.parent / f"html-surface-{index}"
                build_preview_site(self.root, destination, release_sha="0" * 40)
                page = destination / "index.html"
                page.write_text(
                    page.read_text(encoding="utf-8").replace(
                        "</body>",
                        f"{injection}\n</body>",
                    ),
                    encoding="utf-8",
                )
                with self.assertRaisesRegex(ValueError, "disallowed HTML|unapproved external URL"):
                    check_preview_site(destination)

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
        with self.assertRaisesRegex(ValueError, "release SHA"):
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
        self.assertIn('href="assets/academy.css"', index)

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
        shutil.copytree(self.root / "site" / "assets", source / "site" / "assets")
        return source

    def _make_directory_redirect(self, link: Path, target: Path) -> None:
        if os.name != "nt":
            link.symlink_to(target, target_is_directory=True)
            return
        command = Path(os.environ["SystemRoot"]) / "System32" / "cmd.exe"
        created = subprocess.run(
            [str(command), "/d", "/v:off", "/c", "mklink", "/J", str(link), str(target)],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        self.assertEqual(created.returncode, 0, created.stdout + created.stderr)


if __name__ == "__main__":
    unittest.main()
