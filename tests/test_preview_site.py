from __future__ import annotations

import errno
import hashlib
import html as html_module
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit

import scripts.build_preview_site as preview_site
import scripts.check_preview_site as preview_checker
from academy_engine.checkpoints import LAB_INVENTORY
from academy_engine.preview import load_preview_manifest
from scripts.build_preview_site import build_preview_site
from scripts.check_preview_site import check_preview_site
from tests._temporary import cleanup_temporary_directory


def build_and_list_html(root: Path, out: Path) -> list[Path]:
    build_preview_site(root, out, release_sha="1" * 40)
    return sorted(out.rglob("*.html"))


def read_home(root: Path, out: Path) -> str:
    build_preview_site(root, out, release_sha="1" * 40)
    return (out / "index.html").read_text(encoding="utf-8")


def read_webp_dimensions(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    if data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        raise ValueError("not a WebP image")
    offset = 12
    while offset + 8 <= len(data):
        chunk_type = data[offset : offset + 4]
        chunk_size = int.from_bytes(data[offset + 4 : offset + 8], "little")
        payload = data[offset + 8 : offset + 8 + chunk_size]
        if len(payload) != chunk_size:
            raise ValueError("truncated WebP chunk")
        if chunk_type == b"VP8X" and len(payload) >= 10:
            return (
                int.from_bytes(payload[4:7], "little") + 1,
                int.from_bytes(payload[7:10], "little") + 1,
            )
        if chunk_type == b"VP8 " and len(payload) >= 10 and payload[3:6] == b"\x9d\x01\x2a":
            return (
                int.from_bytes(payload[6:8], "little") & 0x3FFF,
                int.from_bytes(payload[8:10], "little") & 0x3FFF,
            )
        if chunk_type == b"VP8L" and len(payload) >= 5 and payload[0] == 0x2F:
            dimensions = int.from_bytes(payload[1:5], "little")
            return (dimensions & 0x3FFF) + 1, ((dimensions >> 14) & 0x3FFF) + 1
        offset += 8 + chunk_size + (chunk_size % 2)
    raise ValueError("WebP image has no supported dimension chunk")


def extract_bootstrap_blocks(readme: str, rendered_home: str) -> dict[str, str]:
    patterns = {
        "powershell": (
            r"Windows PowerShell:[ \t]*\n(?:[ \t]*\n)*[ \t]*```powershell[ \t]*\n(?P<body>.*?)[ \t]*\n[ \t]*```",
            r'<p><strong>Windows PowerShell</strong></p><pre><code class="language-powershell">(?P<body>.*?)</code></pre>',
        ),
        "posix": (
            r"macOS or Linux shell:[ \t]*\n(?:[ \t]*\n)*[ \t]*```sh[ \t]*\n(?P<body>.*?)[ \t]*\n[ \t]*```",
            r'<p><strong>macOS or Linux shell</strong></p><pre><code class="language-sh">(?P<body>.*?)</code></pre>',
        ),
    }
    blocks: dict[str, str] = {}
    for platform, (readme_pattern, home_pattern) in patterns.items():
        readme_match = re.search(readme_pattern, readme, re.DOTALL)
        home_match = re.search(home_pattern, rendered_home, re.DOTALL)
        if readme_match is None or home_match is None:
            raise AssertionError(f"missing {platform} bootstrap block")
        readme_block = textwrap.dedent(readme_match.group("body")).strip()
        home_block = html_module.unescape(home_match.group("body")).strip()
        if readme_block != home_block:
            raise AssertionError(f"README and rendered {platform} bootstrap blocks differ")
        blocks[platform] = readme_block
    return blocks


class PreviewSiteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(__file__).parents[1]
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.out = Path(self.temporary_directory.name) / "generated"

    def tearDown(self) -> None:
        cleanup_temporary_directory(self.temporary_directory)

    def test_teardown_retries_a_transient_nonempty_directory(self) -> None:
        transient = OSError(errno.ENOTEMPTY, "directory not empty")
        temporary = unittest.mock.Mock()
        temporary.cleanup.side_effect = (transient, None)

        cleanup_temporary_directory(temporary, sleep=lambda _: None)

        self.assertEqual(temporary.cleanup.call_count, 2)

    def test_teardown_propagates_a_non_transient_cleanup_error(self) -> None:
        denied = OSError(errno.EACCES, "permission denied")
        temporary = unittest.mock.Mock()
        temporary.cleanup.side_effect = denied

        with self.assertRaisesRegex(OSError, "permission denied"):
            cleanup_temporary_directory(temporary, sleep=lambda _: None)

        self.assertEqual(temporary.cleanup.call_count, 1)

    def test_teardown_propagates_persistent_nonempty_after_retry_budget(self) -> None:
        temporary = unittest.mock.Mock()
        temporary.cleanup.side_effect = OSError(errno.ENOTEMPTY, "still not empty")

        with self.assertRaisesRegex(OSError, "still not empty"):
            cleanup_temporary_directory(temporary, sleep=lambda _: None)

        self.assertEqual(temporary.cleanup.call_count, 5)

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
        self.assertIn("15–60 minutes", html)
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

    def test_documented_bootstraps_install_a_clean_canonical_snapshot_outside_checkout(self) -> None:
        """Catches a bootstrap whose installed bytes can come from a between-step learner mutation."""
        blocks = self._documented_bootstrap_blocks()

        for platform, executable, arguments in self._bootstrap_shells(require_venv=True):
            with self.subTest(platform=platform):
                learner, environment = self._bootstrap_fixture(f"success-{platform}", platform)
                fixture = learner.parents[1]
                mutation_event = fixture / "mutation-event"
                hostile_sentinel = fixture / "hostile-shadow-imported"
                environment.update(
                    {
                        "ACADEMY_TEST_GIT_HOOK": "mutate-after-snapshot-identity",
                        "ACADEMY_TEST_MUTATION_EVENT": str(mutation_event),
                        "ACADEMY_TEST_HOSTILE_SENTINEL": str(hostile_sentinel),
                    }
                )
                result = self._run_bootstrap(
                    platform,
                    executable,
                    arguments,
                    blocks[platform],
                    learner,
                    environment,
                )

                self.assertTrue(
                    mutation_event.is_file(),
                    "the learner mutation hook did not run after snapshot identity verification",
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                source = learner.parent / "arbiter-academy-source-preview-0.1"
                tools = learner.parent / "arbiter-academy-tools-preview-0.1"
                self.assertTrue(source.is_dir())
                self.assertFalse(source.resolve().is_relative_to(learner.resolve()))
                reviewed_commit = self._git(learner, "rev-parse", "--verify", "HEAD").stdout.strip()
                self.assertEqual(
                    self._git(source, "rev-parse", "--verify", "HEAD").stdout.strip(),
                    reviewed_commit,
                )
                launcher = (
                    tools / "Scripts" / "arbiter-academy.exe"
                    if platform == "powershell"
                    else tools / "bin" / "arbiter-academy"
                )
                self.assertTrue(launcher.is_file())
                installed_cli = next(tools.glob("**/site-packages/academy_engine/cli.py"))
                self.assertFalse(installed_cli.resolve().is_relative_to(learner.resolve()))
                source_bytes = (source / "academy_engine" / "cli.py").read_bytes()
                learner_bytes = (learner / "academy_engine" / "cli.py").read_bytes()
                self.assertNotEqual(learner_bytes, source_bytes)
                self.assertEqual(
                    installed_cli.read_bytes(),
                    source_bytes,
                    "installed verifier bytes differ from the reviewed sibling snapshot",
                )
                launcher_environment = dict(environment)
                launcher_environment["ACADEMY_TEST_HOSTILE_SENTINEL"] = str(hostile_sentinel)
                launched = subprocess.run(
                    [str(launcher), "--repository", str(learner), "progress"],
                    cwd=learner,
                    env=launcher_environment,
                    text=True,
                    capture_output=True,
                    check=False,
                    timeout=60,
                )
                self.assertEqual(launched.returncode, 0, launched.stdout + launched.stderr)
                self.assertFalse(hostile_sentinel.exists())

    def test_documented_bootstraps_reject_a_clean_fork_after_canonical_advances(self) -> None:
        """Catches a stale but clean fork being mistaken for current canonical Preview source."""
        blocks = self._documented_bootstrap_blocks()

        for platform, executable, arguments in self._bootstrap_shells():
            with self.subTest(platform=platform):
                learner, environment = self._bootstrap_fixture(f"stale-fork-{platform}", platform)
                self._advance_canonical(learner)
                self.assertEqual(self._git(learner, "status", "--porcelain").stdout, "")

                result = self._run_bootstrap(
                    platform,
                    executable,
                    arguments,
                    blocks[platform],
                    learner,
                    environment,
                )

                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("Fork HEAD is not the reviewed canonical Preview source.", result.stderr)
                self.assertFalse((learner.parent / "arbiter-academy-source-preview-0.1").exists())
                self.assertFalse((learner.parent / "arbiter-academy-tools-preview-0.1").exists())

    def test_documented_bootstraps_reject_a_dirty_checkout_before_sibling_creation(self) -> None:
        """Catches dirty learner files reaching snapshot creation despite canonical commit identity."""
        blocks = self._documented_bootstrap_blocks()

        for platform, executable, arguments in self._bootstrap_shells():
            with self.subTest(platform=platform):
                learner, environment = self._bootstrap_fixture(f"dirty-{platform}", platform)
                with (learner / "academy_engine" / "cli.py").open("ab") as stream:
                    stream.write(b"\n# dirty learner verifier\n")
                self.assertNotEqual(self._git(learner, "status", "--porcelain").stdout, "")

                result = self._run_bootstrap(
                    platform,
                    executable,
                    arguments,
                    blocks[platform],
                    learner,
                    environment,
                )

                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("Bootstrap requires a clean learner checkout.", result.stderr)
                self.assertFalse((learner.parent / "arbiter-academy-source-preview-0.1").exists())
                self.assertFalse((learner.parent / "arbiter-academy-tools-preview-0.1").exists())

    def test_documented_bootstraps_refuse_each_preexisting_sibling_boundary(self) -> None:
        """Catches either an old source snapshot or stale wheel directory being silently reused."""
        blocks = self._documented_bootstrap_blocks()

        for platform, executable, arguments in self._bootstrap_shells():
            for boundary in ("source", "tools-with-stale-wheel"):
                with self.subTest(platform=platform, boundary=boundary):
                    learner, environment = self._bootstrap_fixture(
                        f"preexisting-{boundary}-{platform}", platform
                    )
                    source = learner.parent / "arbiter-academy-source-preview-0.1"
                    tools = learner.parent / "arbiter-academy-tools-preview-0.1"
                    if boundary == "source":
                        source.mkdir()
                    else:
                        wheels = tools / "wheels"
                        wheels.mkdir(parents=True)
                        (wheels / "workshop_queue-0.1.0-py3-none-any.whl").write_bytes(
                            b"stale same-version wheel"
                        )
                    self.assertEqual(self._git(learner, "status", "--porcelain").stdout, "")

                    result = self._run_bootstrap(
                        platform,
                        executable,
                        arguments,
                        blocks[platform],
                        learner,
                        environment,
                    )

                    self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertIn("Preview source/tools path already exists", result.stderr)
                    launcher = (
                        tools / "Scripts" / "arbiter-academy.exe"
                        if platform == "powershell"
                        else tools / "bin" / "arbiter-academy"
                    )
                    self.assertFalse(launcher.exists())

    def test_documented_bootstraps_stop_after_late_wheel_construction_failure(self) -> None:
        """Catches a real wheel-command failure falling through to a newly seeded stale wheel."""
        blocks = self._documented_bootstrap_blocks()

        for platform, executable, arguments in self._bootstrap_shells(require_venv=True):
            with self.subTest(platform=platform):
                learner, environment = self._bootstrap_fixture(f"late-wheel-{platform}", platform)
                fixture = learner.parents[1]
                tools = learner.parent / "arbiter-academy-tools-preview-0.1"
                stale_cache = fixture / "stale-cache"
                stale_cache.mkdir()
                stale_build = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "pip",
                        "wheel",
                        "--no-index",
                        "--find-links",
                        str(learner / ".github" / "wheelhouse"),
                        "--no-deps",
                        "--wheel-dir",
                        str(stale_cache),
                        str(learner),
                    ],
                    cwd=learner,
                    env=environment,
                    text=True,
                    capture_output=True,
                    check=False,
                    timeout=180,
                )
                self.assertEqual(stale_build.returncode, 0, stale_build.stdout + stale_build.stderr)
                stale_wheel = stale_cache / "workshop_queue-0.1.0-py3-none-any.whl"
                self.assertTrue(stale_wheel.is_file())
                wheel_event = fixture / "wheel-command-attempted"
                install_event = fixture / "install-command-attempted"
                environment.update(
                    {
                        "ACADEMY_TEST_PYTHON_HOOK": "seed-stale-and-fail-wheel",
                        "ACADEMY_TEST_STALE_WHEEL": str(stale_wheel),
                        "ACADEMY_TEST_WHEEL_EVENT": str(wheel_event),
                        "ACADEMY_TEST_INSTALL_EVENT": str(install_event),
                    }
                )
                self.assertEqual(self._git(learner, "status", "--porcelain").stdout, "")
                self.assertFalse((learner.parent / "arbiter-academy-source-preview-0.1").exists())
                self.assertFalse(tools.exists())

                result = self._run_bootstrap(
                    platform,
                    executable,
                    arguments,
                    blocks[platform],
                    learner,
                    environment,
                )

                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertTrue(wheel_event.is_file(), "the documented wheel command did not run")
                self.assertFalse(install_event.exists(), "install ran after wheel construction failed")
                seeded_wheel = tools / "wheels" / stale_wheel.name
                self.assertEqual(seeded_wheel.read_bytes(), stale_wheel.read_bytes())
                if platform == "powershell":
                    self.assertIn("Could not build the reviewed Academy wheel.", result.stderr)
                else:
                    self.assertIn("simulated wheel construction failure", result.stderr)
                launcher = (
                    tools / "Scripts" / "arbiter-academy.exe"
                    if platform == "powershell"
                    else tools / "bin" / "arbiter-academy"
                )
                self.assertFalse(launcher.exists())

    def test_posix_bootstrap_fails_closed_when_clean_status_inspection_fails(self) -> None:
        """Catches an empty failed status substitution being mistaken for a clean checkout."""
        block = self._documented_bootstrap_blocks()["posix"]
        posix_shells = [shell for shell in self._bootstrap_shells() if shell[0] == "posix"]
        self.assertTrue(posix_shells, "POSIX bootstrap shell is unavailable")

        for platform, executable, arguments in posix_shells:
            learner, environment = self._bootstrap_fixture("status-failure-posix", platform)
            environment["ACADEMY_TEST_GIT_HOOK"] = "fail-status"

            result = self._run_bootstrap(
                platform,
                executable,
                arguments,
                block,
                learner,
                environment,
            )

            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("Could not inspect learner checkout status.", result.stderr)
            self.assertFalse((learner.parent / "arbiter-academy-source-preview-0.1").exists())
            self.assertFalse((learner.parent / "arbiter-academy-tools-preview-0.1").exists())

    def test_documented_bootstrap_contract_retains_reviewed_offline_boundary_and_limits(self) -> None:
        """Catches executable bootstrap or prose drift from the reviewed local trust boundary."""
        blocks = self._documented_bootstrap_blocks()
        for platform, block in blocks.items():
            with self.subTest(platform=platform):
                self.assertIn("https://github.com/arbiterForge/arbiter-academy.git", block)
                self.assertIn("--no-index", block)
                self.assertIn("--no-deps", block)
                snapshot = "$academySource" if platform == "powershell" else "$academy_source"
                self.assertIn(f'{snapshot}\\.github\\wheelhouse' if platform == "powershell" else f'{snapshot}/.github/wheelhouse', block)

        readme = (self.root / "README.md").read_text(encoding="utf-8")
        rendered = read_home(self.root, self.out)
        self.assertIn(
            "does not provide cryptographic or malicious-operator resistance",
            " ".join(readme.split()),
        )
        self.assertIn("provides no cryptographic or malicious-operator resistance", rendered)

    def test_home_pacing_range_is_derived_from_published_lesson_metadata(self) -> None:
        """Catches the landing-page range drifting from published lesson durations."""
        source = self._copy_public_source()
        lesson = source / "academy" / "tracks" / "foundations" / "F02-orient-to-state.md"
        text = lesson.read_text(encoding="utf-8")
        self.assertIn("estimated_minutes: 15", text)
        lesson.write_text(
            text.replace("estimated_minutes: 15", "estimated_minutes: 12", 1),
            encoding="utf-8",
        )

        html = read_home(source, self.out)

        self.assertIn("12–60 minutes", html)
        self.assertNotIn("15–60 minutes", html)

    def test_home_workflow_is_one_semantic_six_step_ordered_list(self) -> None:
        """Catches visual numbering that exposes no ordered-list structure to assistive tech."""
        html = read_home(self.root, self.out)
        workflow = html.split("<h2>Start safely</h2>", 1)[1].split("</ol>", 1)[0] + "</ol>"

        self.assertEqual(workflow.count('<ol class="start-steps">'), 1)
        self.assertEqual(workflow.count("</ol>"), 1)
        self.assertEqual(workflow.count("<li>"), 6)
        self.assertEqual(workflow.count("</li>"), 6)
        self.assertNotRegex(workflow, r"<strong>[1-6]\. ")

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
            "assets/favicon.svg",
            "assets/fonts/jetbrains-mono-latin-wght-normal.woff2",
            "assets/fonts/manrope-latin-wght-normal.woff2",
            "assets/gate-mark.svg",
            "assets/hero-gates.webp",
            "assets/logo.svg",
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
                "assets/favicon.svg",
                "assets/fonts/jetbrains-mono-latin-wght-normal.woff2",
                "assets/fonts/manrope-latin-wght-normal.woff2",
                "assets/gate-mark.svg",
                "assets/hero-gates.webp",
                "assets/logo.svg",
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

    def test_static_checker_rejects_broken_fragments_aria_references_and_duplicate_ids(self) -> None:
        """Catches generated navigation or accessible names pointing at absent or ambiguous IDs."""
        cases = (
            (
                "fragment",
                Path("index.html"),
                'href="#main-content"',
                'href="#missing-section"',
                "broken HTML fragment",
            ),
            (
                "aria",
                Path("labs/F01-fork-clone-doctor/index.html"),
                'aria-labelledby="next-step-heading"',
                'aria-labelledby="missing-next-step-heading"',
                "broken aria-labelledby reference",
            ),
            (
                "duplicate",
                Path("labs/F01-fork-clone-doctor/index.html"),
                'id="why-this-mechanism-matters"',
                'id="main-content"',
                "duplicate HTML id",
            ),
        )
        for label, relative, original, mutation, message in cases:
            with self.subTest(case=label):
                destination = self.out.parent / f"id-integrity-{label}"
                build_preview_site(self.root, destination, release_sha="6" * 40)
                page = destination / relative
                source = page.read_text(encoding="utf-8")
                self.assertIn(original, source)
                page.write_text(source.replace(original, mutation, 1), encoding="utf-8")

                with self.assertRaisesRegex(ValueError, message):
                    check_preview_site(destination)

    def test_preview_guidance_does_not_offer_graduation_before_the_course_is_published(self) -> None:
        """Catches public instructions inviting a receipt the published lab set cannot satisfy."""
        manifest = load_preview_manifest(self.root)
        self.assertLess(len(manifest.available_labs), len(LAB_INVENTORY))

        readme = (self.root / "README.md").read_text(encoding="utf-8")
        rendered_home = read_home(self.root, self.out)
        for surface, text in (("README", readme), ("home", rendered_home)):
            with self.subTest(surface=surface):
                normalized = " ".join(text.split())
                self.assertIn("Graduation is not available in Preview 0.1", normalized)
                self.assertNotRegex(
                    text,
                    r"arbiter-academy\s+--repository\s+[^\n<]+\s+graduate\b",
                )

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
        """Catches any byte mutation in every runtime asset reviewed for Preview 0.1."""
        assets = (
            "assets/academy.css",
            "assets/favicon.svg",
            "assets/fonts/jetbrains-mono-latin-wght-normal.woff2",
            "assets/fonts/manrope-latin-wght-normal.woff2",
            "assets/gate-mark.svg",
            "assets/hero-gates.webp",
            "assets/logo.svg",
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

    def test_build_renders_complete_reviewed_lesson_bodies(self) -> None:
        """Catches a published lab being reduced to a metadata shell."""
        build_preview_site(self.root, self.out, release_sha="c" * 40)

        f01 = (self.out / "labs" / "F01-fork-clone-doctor" / "index.html").read_text(encoding="utf-8")
        p02 = (self.out / "labs" / "P02-commit-review-pr" / "index.html").read_text(encoding="utf-8")
        p04 = (self.out / "labs" / "P04-review-a-dependency" / "index.html").read_text(encoding="utf-8")
        self.assertIn('<article class="academy-content">', f01)
        self.assertIn("Why this mechanism matters", f01)
        self.assertIn('<pre><code class="language-powershell">', f01)
        self.assertIn("<strong>your fork</strong>", f01)
        self.assertIn('<nav class="lab-toc" aria-label="On this page">', f01)
        self.assertIn('<div class="table-shell"><table>', p02)
        self.assertIn("Typical time", p02)
        self.assertIn('<code class="language-sh">', p02)
        self.assertIn("Candidate-Artifact", p04)
        self.assertIn("Continue with P05 when it enters verification.", p04)

    def test_markdown_renderer_rejects_unreviewed_syntax_before_writing(self) -> None:
        """Catches unknown Markdown or active HTML being silently dropped or published."""
        injections = (
            '<script>alert("no")</script>',
            "[outside](https://example.invalid)",
            "![pixel](pixel.png)",
            "*unsupported emphasis*",
            "_unsupported emphasis_",
            "[outside][reference]\n\n[reference]: https://example.invalid",
            "[reference]: https://example.invalid",
            "[^note]\n\n[^note]: unsupported footnote",
            "~~~text\nunsupported fence\n~~~",
            "~~unsupported strikethrough~~",
            "    unsupported indented code",
            "\tunsupported tab-indented code",
            "  - unsupported nested list",
            "**unsupported *nested* emphasis**",
            r"\*unsupported escaped emphasis\*",
            r"\`unsupported escaped code\`",
            "inline <!-- unsupported comment -->",
            "- unsupported list item",
            "> unsupported quote",
            "#malformed heading",
            "## heading with closing hashes ##",
            "#### unsupported heading",
            "unsupported setext heading\n===",
            "unsupported hard break  \ncontinued",
        )
        source = self._copy_public_source()
        lesson = source / "academy" / "tracks" / "foundations" / "F01-fork-clone-doctor.md"
        original = lesson.read_text(encoding="utf-8")
        for index, injection in enumerate(injections):
            with self.subTest(injection=injection):
                lesson.write_text(
                    original + f"\n{injection}\n",
                    encoding="utf-8",
                )
                destination = self.out.parent / f"unknown-markdown-{index}"
                with self.assertRaisesRegex(ValueError, "unsupported Markdown"):
                    build_preview_site(source, destination, release_sha="c" * 40)
                self.assertFalse(destination.exists())

    def test_design_surface_is_academy_specific_and_project_relative(self) -> None:
        """Catches loss of the approved Academy identity, orientation, or lesson navigation."""
        build_preview_site(self.root, self.out, release_sha="d" * 40)
        index = (self.out / "index.html").read_text(encoding="utf-8")
        lab = (self.out / "labs" / "F02-orient-to-state" / "index.html").read_text(encoding="utf-8")
        css = (self.out / "assets" / "academy.css").read_text(encoding="utf-8")

        self.assertIn('rel="icon" href="assets/favicon.svg"', index)
        self.assertIn('class="academy-hero__art"', index)
        self.assertIn('src="assets/hero-gates.webp"', index)
        self.assertIn(
            'href="https://github.com/arbiterForge/arbiter-academy/fork"',
            index,
        )
        self.assertIn(
            'href="https://github.com/arbiterForge/arbiter-academy"',
            index,
        )
        self.assertIn('href="https://codearbiter.dev/"', index)
        self.assertIn('class="orientation-band"', lab)
        self.assertIn('aria-label="Course navigation"', lab)
        self.assertIn('aria-label="Breadcrumb"', lab)
        self.assertIn('aria-label="Lab sequence"', lab)
        self.assertIn('href="../F01-fork-clone-doctor/index.html"', lab)
        self.assertIn('href="../F03-work-the-board/index.html"', lab)
        self.assertIn(".academy-content", css)
        self.assertIn("overflow-x: auto", css)
        self.assertIn("min-height: 2.75rem", css)
        self.assertNotRegex(css, r"(?m)^ul\s*\{")
        self.assertNotRegex(css, r"(?m)^li\s*\{")

    def test_home_bootstrap_code_blocks_use_the_bounded_scroll_container(self) -> None:
        """Catches long setup commands widening the whole home page instead of their code block."""
        build_preview_site(self.root, self.out, release_sha="d" * 40)
        css = (self.out / "assets" / "academy.css").read_text(encoding="utf-8")

        block_rule = re.search(
            r"\.academy-content pre,\s*\.start-steps pre\s*\{(?P<body>.*?)\}",
            css,
            re.DOTALL,
        )
        self.assertIsNotNone(
            block_rule,
            "home-page and lesson code blocks must share one containment rule",
        )
        assert block_rule is not None
        self.assertRegex(block_rule.group("body"), r"\boverflow-x:\s*auto\s*;")
        code_rule = re.search(
            r"\.academy-content pre code,\s*\.start-steps pre code\s*\{(?P<body>.*?)\}",
            css,
            re.DOTALL,
        )
        self.assertIsNotNone(
            code_rule,
            "home-page and lesson code text must share one rendering rule",
        )

    def test_rendered_image_dimensions_match_the_intrinsic_reviewed_assets(self) -> None:
        """Catches image markup that distorts the reviewed hero or codeArbiter logo."""
        hero_path = self.root / "site" / "assets" / "hero-gates.webp"
        self.assertEqual(read_webp_dimensions(hero_path), (1881, 836))

        logo = ET.fromstring((self.root / "site" / "assets" / "logo.svg").read_text(encoding="utf-8"))
        self.assertEqual((logo.attrib.get("width"), logo.attrib.get("height")), ("160", "28"))
        self.assertEqual(logo.attrib.get("viewBox"), "0 0 160 28")

        html = read_home(self.root, self.out)
        self.assertIn(
            '<img class="academy-hero__art" src="assets/hero-gates.webp" alt="" width="1881" height="836">',
            html,
        )
        self.assertIn('<img src="assets/logo.svg" alt="" width="160" height="28">', html)

    def test_mobile_lesson_order_keeps_the_article_before_the_full_toc(self) -> None:
        """Catches the mobile grid pulling the long TOC ahead of the lesson H1."""
        build_preview_site(self.root, self.out, release_sha="d" * 40)
        lab = (self.out / "labs" / "F02-orient-to-state" / "index.html").read_text(
            encoding="utf-8"
        )
        css = (self.out / "assets" / "academy.css").read_text(encoding="utf-8")

        article = lab.index('<article class="academy-content">')
        sidebar = lab.index('<aside class="lesson-sidebar">')
        self.assertLess(article, sidebar, "the semantic article must precede the TOC")

        mobile = css.split("@media (max-width: 42rem) {", 1)[1].split(
            "@media (prefers-reduced-motion: reduce)", 1
        )[0]
        sidebar_rule = re.search(r"\.lesson-sidebar\s*\{(?P<body>.*?)\}", mobile, re.DOTALL)
        self.assertIsNotNone(sidebar_rule, "the mobile sidebar rule is missing")
        assert sidebar_rule is not None
        self.assertNotRegex(
            sidebar_rule.group("body"),
            r"\border\s*:\s*-\d+",
            "mobile CSS must not reorder the TOC ahead of the article",
        )

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
                self.assertIn('<nav aria-label="Course navigation">', html)
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

    def _documented_bootstrap_blocks(self) -> dict[str, str]:
        readme = (self.root / "README.md").read_text(encoding="utf-8")
        rendered_home = read_home(self.root, self.out)
        return extract_bootstrap_blocks(readme, rendered_home)

    def _bootstrap_shells(
        self, *, require_venv: bool = False
    ) -> tuple[tuple[str, str, tuple[str, ...]], ...]:
        shells: list[tuple[str, str, tuple[str, ...]]] = []
        if os.name == "nt":
            powershell = shutil.which("powershell.exe") or shutil.which("pwsh.exe")
            if powershell:
                shells.append(
                    (
                        "powershell",
                        powershell,
                        ("-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command"),
                    )
                )
            wsl_bash = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "bash.exe"
            bash = str(wsl_bash) if wsl_bash.is_file() else shutil.which("bash")
        else:
            bash = shutil.which("bash")
        if bash and (
            not require_venv
            or os.name != "nt"
            or subprocess.run(
                [bash, "-lc", "python3 -c 'import ensurepip'"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=15,
            ).returncode
            == 0
        ):
            shells.append(("posix", bash, ("--noprofile", "--norc", "-c")))
        self.assertTrue(shells, "no documented bootstrap shell is available")
        return tuple(shells)

    def _bootstrap_fixture(self, label: str, platform: str) -> tuple[Path, dict[str, str]]:
        fixture = Path(self.temporary_directory.name) / label
        seed = fixture / "reviewed-source"
        shutil.copytree(
            self.root,
            seed,
            ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc", ".superpowers"),
        )
        self._git(seed, "init", "--initial-branch=main")
        self._git(seed, "config", "user.name", "Academy Test")
        self._git(seed, "config", "user.email", "academy-test@example.invalid")
        self._git(seed, "add", "--all")
        self._git(seed, "commit", "-m", "reviewed Preview source")
        canonical = fixture / "canonical.git"
        fork = fixture / "fork.git"
        self._git(fixture, "clone", "--bare", str(seed), str(canonical))
        self._git(fixture, "clone", "--bare", str(seed), str(fork))
        learner_parent = fixture / "learner-work"
        learner_parent.mkdir()
        learner = learner_parent / "arbiter-academy"
        self._git(fixture, "clone", str(fork), str(learner))
        self._git(learner, "config", "user.name", "Academy Learner")
        self._git(learner, "config", "user.email", "learner@example.invalid")

        git_config = fixture / "gitconfig"
        canonical_url = canonical.resolve().as_uri()
        if platform == "posix" and os.name == "nt":
            drive, tail = os.path.splitdrive(str(canonical.resolve()))
            canonical_url = f"file:///mnt/{drive[0].lower()}{tail.replace(os.sep, '/')}"
        self._git(
            fixture,
            "config",
            "--file",
            str(git_config),
            f"url.{canonical_url}.insteadOf",
            "https://github.com/arbiterForge/arbiter-academy.git",
        )
        self._git(
            fixture,
            "config",
            "--file",
            str(git_config),
            "protocol.file.allow",
            "always",
        )
        environment = dict(os.environ)
        environment.update(
            {
                "GIT_CONFIG_GLOBAL": str(git_config),
                "GIT_CONFIG_NOSYSTEM": "1",
                "PIP_CONFIG_FILE": os.devnull,
                "PIP_DISABLE_PIP_VERSION_CHECK": "1",
                "PYTHONUTF8": "1",
            }
        )
        return learner, environment

    def _advance_canonical(self, learner: Path) -> None:
        fixture = learner.parents[1]
        canonical = fixture / "canonical.git"
        advance = fixture / "canonical-advance"
        self._git(fixture, "clone", str(canonical), str(advance))
        self._git(advance, "config", "user.name", "Academy Reviewer")
        self._git(advance, "config", "user.email", "reviewer@example.invalid")
        with (advance / "README.md").open("a", encoding="utf-8") as stream:
            stream.write("\nCanonical Preview review advanced.\n")
        self._git(advance, "add", "README.md")
        self._git(advance, "commit", "-m", "advance reviewed Preview source")
        self._git(advance, "push", "origin", "HEAD:main")

    def _prepare_bootstrap_shims(
        self,
        platform: str,
        learner: Path,
        environment: dict[str, str],
    ) -> None:
        git_hook = environment.get("ACADEMY_TEST_GIT_HOOK")
        python_hook = environment.get("ACADEMY_TEST_PYTHON_HOOK")
        if not git_hook and not python_hook:
            return

        fixture = learner.parents[1]
        shim_root = fixture / "command-shims"
        shim_root.mkdir(exist_ok=True)
        source = learner.parent / "arbiter-academy-source-preview-0.1"
        tools = learner.parent / "arbiter-academy-tools-preview-0.1"
        environment.update(
            {
                "ACADEMY_TEST_LEARNER_CLI": str(learner / "academy_engine" / "cli.py"),
                "ACADEMY_TEST_SOURCE": str(source),
                "ACADEMY_TEST_TOOLS": str(tools),
                "ACADEMY_TEST_SHIM_ROOT": str(shim_root),
            }
        )
        if platform == "posix" and os.name == "nt":
            environment["ACADEMY_REAL_GIT"] = "/usr/bin/git"
            environment["ACADEMY_REAL_PYTHON"] = "/usr/bin/python3"
        else:
            real_git = shutil.which("git")
            real_python = shutil.which("python3") if platform == "posix" else sys.executable
            self.assertIsNotNone(real_git, "real Git executable is unavailable")
            self.assertIsNotNone(real_python, "real Python executable is unavailable")
            environment["ACADEMY_REAL_GIT"] = str(real_git)
            environment["ACADEMY_REAL_PYTHON"] = str(real_python)

        if git_hook:
            git_shim = shim_root / "git_shim.py"
            git_shim.write_text(
                """from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

args = sys.argv[1:]
hook = os.environ.get("ACADEMY_TEST_GIT_HOOK", "")
if hook == "fail-status" and args == ["status", "--porcelain=v1", "--untracked-files=all"]:
    print("simulated git status inspection failure", file=sys.stderr)
    raise SystemExit(23)

result = subprocess.run(
    [os.environ["ACADEMY_REAL_GIT"], *args],
    stdin=subprocess.DEVNULL,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    check=False,
)
sys.stdout.buffer.write(result.stdout)
sys.stderr.buffer.write(result.stderr)
if result.returncode == 0 and hook == "mutate-after-snapshot-identity":
    source = Path(os.environ["ACADEMY_TEST_SOURCE"]).resolve()
    if len(args) == 5 and args[0] == "-C" and Path(args[1]).resolve() == source and args[2:] == ["rev-parse", "--verify", "HEAD"]:
        hostile = (
            'import os\\n'
            'from pathlib import Path\\n'
            'Path(os.environ["ACADEMY_TEST_HOSTILE_SENTINEL"]).write_text('
            '"learner shadow imported", encoding="utf-8")\\n'
            'raise RuntimeError("learner verifier shadow imported")\\n'
        )
        Path(os.environ["ACADEMY_TEST_LEARNER_CLI"]).write_text(hostile, encoding="utf-8")
        Path(os.environ["ACADEMY_TEST_MUTATION_EVENT"]).write_text(
            "mutated after snapshot identity", encoding="utf-8"
        )
raise SystemExit(result.returncode)
""",
                encoding="utf-8",
            )
            environment["ACADEMY_TEST_GIT_SHIM"] = str(git_shim)
            if platform == "powershell":
                (shim_root / "git.cmd").write_text(
                    f'@"{sys.executable}" "{git_shim}" %*\n@exit /b %ERRORLEVEL%\n',
                    encoding="utf-8",
                )
            else:
                wrapper = shim_root / "git"
                wrapper.write_text(
                    '#!/bin/sh\nexec "$ACADEMY_REAL_PYTHON" "$ACADEMY_TEST_GIT_SHIM" "$@"\n',
                    encoding="utf-8",
                    newline="\n",
                )
                wrapper.chmod(0o755)

        if python_hook:
            pip_shadow = shim_root / "pip-shadow"
            (pip_shadow / "pip").mkdir(parents=True)
            (pip_shadow / "pip" / "__init__.py").write_text("", encoding="utf-8")
            (pip_shadow / "pip" / "__main__.py").write_text(
                """from __future__ import annotations

import os
import sys
from pathlib import Path

operation = sys.argv[1] if len(sys.argv) > 1 else ""
if operation == "wheel":
    Path(os.environ["ACADEMY_TEST_WHEEL_EVENT"]).write_text(
        "wheel command attempted", encoding="utf-8"
    )
    print("simulated wheel construction failure", file=sys.stderr)
    raise SystemExit(23)
if operation == "install":
    Path(os.environ["ACADEMY_TEST_INSTALL_EVENT"]).write_text(
        "install command attempted", encoding="utf-8"
    )
    raise SystemExit(0)
print("unexpected pip operation", file=sys.stderr)
raise SystemExit(97)
""",
                encoding="utf-8",
            )
            launcher_shim = shim_root / "python_launcher_shim.py"
            launcher_shim.write_text(
                """from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

args = sys.argv[1:]
if args and args[0] == "-3":
    args = args[1:]
result = subprocess.run(
    [os.environ["ACADEMY_REAL_PYTHON"], *args],
    stdin=subprocess.DEVNULL,
    check=False,
)
if result.returncode == 0 and args[:2] == ["-m", "venv"]:
    tools = Path(os.environ["ACADEMY_TEST_TOOLS"])
    wheels = tools / "wheels"
    wheels.mkdir(parents=True, exist_ok=True)
    shutil.copy2(os.environ["ACADEMY_TEST_STALE_WHEEL"], wheels)
    candidates = [tools / "Lib" / "site-packages", *tools.glob("lib/python*/site-packages")]
    site_packages = next(path for path in candidates if path.is_dir())
    shadow = Path(os.environ["ACADEMY_TEST_PIP_SHADOW"])
    (site_packages / "academy_test_pip_shadow.pth").write_text(
        f"import sys; sys.path.insert(0, {str(shadow)!r})\\n", encoding="utf-8"
    )
raise SystemExit(result.returncode)
""",
                encoding="utf-8",
            )
            environment.update(
                {
                    "ACADEMY_TEST_PIP_SHADOW": str(pip_shadow),
                    "ACADEMY_TEST_PYTHON_LAUNCHER": str(launcher_shim),
                }
            )
            if platform == "powershell":
                (shim_root / "py.cmd").write_text(
                    f'@"{sys.executable}" "{launcher_shim}" %*\n@exit /b %ERRORLEVEL%\n',
                    encoding="utf-8",
                )
            else:
                wrapper = shim_root / "python3"
                wrapper.write_text(
                    '#!/bin/sh\nexec "$ACADEMY_REAL_PYTHON" "$ACADEMY_TEST_PYTHON_LAUNCHER" "$@"\n',
                    encoding="utf-8",
                    newline="\n",
                )
                wrapper.chmod(0o755)

        if platform == "powershell":
            environment["PATH"] = str(shim_root) + os.pathsep + environment.get("PATH", "")

    def _run_bootstrap(
        self,
        platform: str,
        executable: str,
        arguments: tuple[str, ...],
        block: str,
        learner: Path,
        environment: dict[str, str],
    ) -> subprocess.CompletedProcess[str]:
        self._prepare_bootstrap_shims(platform, learner, environment)
        child_environment = dict(environment)
        child_block = block
        if platform == "posix" and os.name == "nt":
            path_keys = (
                "GIT_CONFIG_GLOBAL",
                "ACADEMY_TEST_GIT_SHIM",
                "ACADEMY_TEST_HOSTILE_SENTINEL",
                "ACADEMY_TEST_INSTALL_EVENT",
                "ACADEMY_TEST_LEARNER_CLI",
                "ACADEMY_TEST_MUTATION_EVENT",
                "ACADEMY_TEST_PIP_SHADOW",
                "ACADEMY_TEST_PYTHON_LAUNCHER",
                "ACADEMY_TEST_SHIM_ROOT",
                "ACADEMY_TEST_SOURCE",
                "ACADEMY_TEST_STALE_WHEEL",
                "ACADEMY_TEST_TOOLS",
                "ACADEMY_TEST_WHEEL_EVENT",
            )
            for key in path_keys:
                if key in child_environment:
                    drive, tail = os.path.splitdrive(child_environment[key])
                    child_environment[key] = f"/mnt/{drive[0].lower()}{tail.replace(os.sep, '/')}"
            child_environment["PIP_CONFIG_FILE"] = "/dev/null"
            drive, tail = os.path.splitdrive(str(learner.resolve()))
            learner_path = f"/mnt/{drive[0].lower()}{tail.replace(os.sep, '/')}"
            export_keys = (
                "GIT_CONFIG_GLOBAL",
                "GIT_CONFIG_NOSYSTEM",
                "PIP_CONFIG_FILE",
                "PIP_DISABLE_PIP_VERSION_CHECK",
                "PYTHONUTF8",
                *sorted(
                    key
                    for key in child_environment
                    if key.startswith("ACADEMY_TEST_")
                    or key in {"ACADEMY_REAL_GIT", "ACADEMY_REAL_PYTHON"}
                ),
            )
            exports = "".join(
                f"export {key}={shlex.quote(child_environment[key])}\n"
                for key in export_keys
                if key in child_environment
            )
            child_block = f"{exports}cd {shlex.quote(learner_path)}\n{child_block}"
        if platform == "posix" and "ACADEMY_TEST_SHIM_ROOT" in child_environment:
            child_block = (
                f"PATH={shlex.quote(child_environment['ACADEMY_TEST_SHIM_ROOT'])}:\"$PATH\"\n"
                "export PATH\n"
                f"{child_block}"
            )
        if platform == "posix" and os.name == "nt":
            script = learner.parents[1] / "documented-bootstrap.sh"
            script.write_text(child_block, encoding="utf-8", newline="\n")
            drive, tail = os.path.splitdrive(str(script.resolve()))
            script_path = f"/mnt/{drive[0].lower()}{tail.replace(os.sep, '/')}"
            command = [executable, *arguments[:-1], script_path]
        else:
            command = [executable, *arguments, child_block]
        return subprocess.run(
            command,
            cwd=learner,
            env=child_environment,
            text=True,
            capture_output=True,
            check=False,
            timeout=240,
        )

    def _git(self, cwd: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            ["git", *arguments],
            cwd=cwd,
            text=True,
            capture_output=True,
            check=False,
            timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

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
