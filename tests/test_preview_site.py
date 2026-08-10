from __future__ import annotations

import errno
import hashlib
import html as html_module
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit

import scripts.build_preview_site as preview_site
import scripts.check_preview_site as preview_checker
from academy_engine.checkpoints import LAB_INVENTORY
from academy_engine.lesson_actions import (
    ActionResource,
    CommandVariant,
    load_action_manifest,
    validate_action_manifest,
)
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


class PreviewSiteTests(unittest.TestCase):
    def test_f01_renders_the_complete_evidence_and_recovery_contract(self) -> None:
        manifest = load_action_manifest(self.root, "F01-fork-clone-doctor")
        actions = {action.id: action for action in manifest.actions}
        document = preview_site._read_markdown_document(
            self.root,
            Path("academy/tracks/foundations/F01-fork-clone-doctor.md"),
            "F01-fork-clone-doctor",
            require_h1=True,
        )
        html = str(document["content"])

        self.assertEqual(document["referenced_actions"], tuple(actions))
        self.assertIn(".codearbiter/reports/academy/F01-doctor.json", html)
        self.assertIn("safe_for_push_labs", html)
        self.assertIn("effective_push_remote", html)
        self.assertIn("Git prints nothing", html)
        self.assertIn("externally installed Academy verifier", html)
        self.assertIn(
            "checkpoint F01-fork-clone-doctor: passed; progress: .academy/progress.json",
            html,
        )
        self.assertIn("only after the external verifier", html)
        self.assertIn("preserves the clean committed attempt", html)

    def setUp(self) -> None:
        self.root = Path(__file__).parents[1]
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.out = Path(self.temporary_directory.name) / "generated"

    def tearDown(self) -> None:
        cleanup_temporary_directory(self.temporary_directory)

    def non_command_manifest_action(
        self, *, action_id: str = "read-prerequisites", surface: str = "browser"
    ) -> dict[str, object]:
        return {
            "id": action_id,
            "sequence": 1,
            "title": "Read the prerequisites",
            "actor": "learner",
            "surface": surface,
            "instruction": "Read the prerequisite explanation before changing the repository.",
            "rationale": None,
            "resources": [],
            "variants": [],
            "expected_result": "You can identify the repository boundary.",
            "recovery": "Return to the prerequisite section and compare each repository role.",
            "evidence": None,
        }

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

    def test_retrying_directory_applies_the_same_policy_to_cleanup_method(self) -> None:
        from tests._temporary import RetryingTemporaryDirectory

        temporary = RetryingTemporaryDirectory()
        base_cleanup = tempfile.TemporaryDirectory.cleanup
        transient = OSError(errno.ENOTEMPTY, "directory not empty")
        try:
            with patch.object(
                tempfile.TemporaryDirectory,
                "cleanup",
                side_effect=(transient, None),
            ) as cleanup:
                temporary.cleanup()
            self.assertEqual(cleanup.call_count, 2)
        finally:
            base_cleanup(temporary)

    def test_build_emits_p06_and_p07_without_an_empty_coming_next_section(self) -> None:
        """Catches accepted labs remaining hidden or empty status-only markup being rendered."""
        build_preview_site(self.root, self.out, release_sha="a" * 40)

        self.assertTrue((self.out / "labs" / "P04-review-a-dependency" / "index.html").is_file())
        self.assertTrue((self.out / "labs" / "P05-checkpoint-remediation" / "index.html").is_file())
        self.assertTrue((self.out / "labs" / "P06-context-drift-recovery" / "index.html").is_file())
        self.assertTrue((self.out / "labs" / "P07-threat-model" / "index.html").is_file())
        self.assertFalse((self.out / "labs" / "P08-repository-hygiene" / "index.html").exists())
        index = (self.out / "index.html").read_text(encoding="utf-8")
        self.assertIn('href="labs/P05-checkpoint-remediation/index.html"', index)
        self.assertIn('href="labs/P06-context-drift-recovery/index.html"', index)
        self.assertIn('href="labs/P07-threat-model/index.html"', index)
        self.assertNotIn("coming-next", index)
        self.assertNotIn("Coming next", index)

    def test_home_names_fork_before_clone_and_never_invites_push_to_official_origin(self) -> None:
        """Catches onboarding that starts from or sends learner work to the canonical repository."""
        html = read_home(self.root, self.out)

        self.assertIn("Create your practice fork", html)
        self.assertIn("your fork", html)
        self.assertLess(html.index("Create your practice fork"), html.index("Clone it to your computer"))
        self.assertIn(
            "git clone https://github.com/&lt;your-account&gt;/arbiter-academy.git",
            html,
        )
        self.assertNotIn("push to arbiterForge/arbiter-academy", html)

    def test_bootstrap_fixture_copies_objects_into_the_mutable_learner_clone(self) -> None:
        """Catches the mutable learner fixture sharing hardlinked object inodes with its fork."""
        commands: list[tuple[str, ...]] = []
        run_git = self._git

        def record_git(cwd: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
            commands.append(arguments)
            return run_git(cwd, *arguments)

        with patch.object(self, "_git", side_effect=record_git):
            learner, _environment = self._bootstrap_fixture(
                "learner-clone-object-isolation", "powershell"
            )

        learner_clones = [
            arguments
            for arguments in commands
            if arguments[0] == "clone" and arguments[-1] == str(learner)
        ]
        self.assertEqual(
            learner_clones,
            [
                (
                    "clone",
                    "--no-hardlinks",
                    str(learner.parents[1] / "fork.git"),
                    str(learner),
                )
            ],
        )

    def test_home_states_preview_scope_prerequisites_pacing_and_exact_workflow(self) -> None:
        """Catches public guidance that overstates the preview or omits its runnable workflow."""
        html = read_home(self.root, self.out)

        self.assertIn("eleven runnable labs", html)
        self.assertIn("15 to 60 minutes", html)
        self.assertIn("Git", html)
        self.assertIn("codeArbiter", html)
        self.assertIn("Power User lessons are not included", html)
        for operation in ("Doctor", "console"):
            self.assertIn(operation, html)
        self.assertIn('href="recovery/index.html"', html)

    def test_home_teaches_every_prerequisite_before_first_use(self) -> None:
        """Catches a guided entry page that asks a novice to infer setup vocabulary or surfaces."""
        html = read_home(self.root, self.out)
        guide_path = self.root / "academy" / "guides" / "home.md"
        self.assertTrue(guide_path.is_file(), "guided Home source must exist")
        guide = guide_path.read_text(encoding="utf-8")
        manifest = load_action_manifest(self.root, "home")

        headings = (
            "Start here",
            "What the Academy changes",
            "Create your practice fork",
            "Clone it to your computer",
            "Install the reviewed Academy tools",
            "Open the operations console",
            "Run readiness checks",
            "Choose your first lesson",
            "Course status",
            "Get help",
        )
        positions = [html.index(f">{heading}</h") for heading in headings]
        self.assertEqual(positions, sorted(positions))

        for prerequisite in (
            "GitHub account",
            "Git",
            "codeArbiter",
            "Browser",
            "Native terminal",
            "repository",
            "fork",
            "clone",
            "origin",
            "upstream",
        ):
            self.assertIn(prerequisite, html)
        self.assertLess(html.index("A fork is"), html.index("home-fork"))
        self.assertLess(html.index("A clone is"), html.index("git clone"))
        self.assertLess(html.index("origin"), html.index("git clone"))
        self.assertLess(html.index("upstream"), html.index("git clone"))

        self.assertEqual(
            tuple(action.id for action in manifest.actions),
            (
                "home-fork",
                "home-clone",
                "home-enter-clone",
                "home-install",
                "home-launch-console",
                "home-doctor",
            ),
        )
        actions = {action.id: action for action in manifest.actions}
        self.assertEqual(
            tuple(variant.command for variant in actions["home-enter-clone"].variants),
            (
                "Set-Location -LiteralPath .\\arbiter-academy",
                "cd -- ./arbiter-academy",
                "cd -- ./arbiter-academy",
            ),
        )
        install = actions["home-install"]
        self.assertEqual(
            tuple(resource.href for resource in install.resources),
            (
                "https://github.com/arbiterForge/arbiter-academy/blob/preview-0.3/install/install.ps1",
                "https://github.com/arbiterForge/arbiter-academy/releases/download/preview-0.3/install.ps1.sha256",
                "https://github.com/arbiterForge/arbiter-academy/blob/preview-0.3/install/install.sh",
                "https://github.com/arbiterForge/arbiter-academy/releases/download/preview-0.3/install.sh.sha256",
            ),
        )
        launch_commands = tuple(variant.command for variant in actions["home-launch-console"].variants)
        self.assertIn(
            '$academy = "$env:LOCALAPPDATA\\ArbiterAcademy\\preview-0.3\\Scripts\\arbiter-academy.exe"\n'
            "& $academy --repository (Get-Location).Path console",
            launch_commands,
        )
        self.assertIn(
            'academy="${XDG_DATA_HOME:-$HOME/.local/share}/arbiter-academy/preview-0.3/bin/arbiter-academy"\n'
            '"$academy" --repository "$PWD" console',
            launch_commands,
        )
        self.assertNotIn("```", guide)
        self.assertNotIn('$ErrorActionPreference = "Stop"', html)
        self.assertIn(
            "irm https://github.com/arbiterForge/arbiter-academy/releases/download/preview-0.3/install.ps1 | iex",
            html,
        )
        self.assertIn(
            "curl -fsSL https://github.com/arbiterForge/arbiter-academy/releases/download/preview-0.3/install.sh | sh",
            html,
        )
        for label in ("You \u00b7 Browser", "You \u00b7 Native terminal", "You \u00b7 Academy console"):
            self.assertIn(label, html)

        self.assertIn('href="https://github.com/arbiterForge/arbiter-academy/fork"', html)
        self.assertIn(
            'href="https://github.com/arbiterForge/arbiter-academy/blob/preview-0.3/install/install.ps1"',
            html,
        )
        self.assertIn(
            'href="https://github.com/arbiterForge/arbiter-academy/blob/preview-0.3/install/install.sh"',
            html,
        )
        self.assertIn("validates the downloaded bundle", html)
        self.assertIn("does not verify its own already-executing bytes", html)
        for host in ("Claude Code", "Codex", "Pi"):
            self.assertIn(host, html)
        self.assertIn("expected fresh-clone remote findings", html)
        self.assertIn("does not need to pass before F01", html)
        self.assertIn("F01 teaches the remote repair", html)
        for state in (
            "Guided: F01",
            "Reference lessons: F02 through P07",
            "Not yet published",
        ):
            self.assertIn(state, html)

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

        self.assertIn("12 to 60 minutes", html)
        self.assertNotIn("15 to 60 minutes", html)

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
        manifest_path = source / "academy" / "publication" / "preview-0.3.json"
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

        self.assertIn("Preserve the branch", html)
        self.assertIn("Choose Check.", html)
        self.assertIn("Choose Reset.", html)
        self.assertIn("installed Academy checker", html)
        self.assertIn("your fork", html)
        self.assertIn(
            "Reset archives the current attempt and prepares the next numbered attempt",
            html,
        )

    def test_recovery_is_a_bounded_operational_decision_tree(self) -> None:
        """Catches recovery advice that skips diagnosis, loses evidence, or uses destructive shortcuts."""
        build_preview_site(self.root, self.out, release_sha="3" * 40)
        html = (self.out / "recovery" / "index.html").read_text(encoding="utf-8")
        guide_path = self.root / "academy" / "guides" / "recovery.md"
        self.assertTrue(guide_path.is_file(), "guided Recovery source must exist")
        guide = guide_path.read_text(encoding="utf-8")
        manifest = load_action_manifest(self.root, "recovery")

        decisions = (
            "Repository not found or not Git",
            "Dirty worktree",
            "Wrong branch or detached HEAD",
            "Unsafe or missing remotes",
            "No prepared attempt",
            "Failed Check with clean committed evidence",
            "Retry",
            "Return to main",
        )
        positions = [html.index(f">{decision}</h") for decision in decisions]
        self.assertEqual(positions, sorted(positions))
        self.assertEqual(guide.count("**Stop:**"), len(decisions))
        self.assertEqual(guide.count("**Observe:**"), len(decisions))
        self.assertEqual(guide.count("**Safe action:**"), len(decisions))
        self.assertEqual(guide.count("**Preserved:**"), len(decisions))
        self.assertEqual(
            tuple(action.id for action in manifest.actions),
            (
                "recovery-inspect",
                "recovery-return-attempt",
                "recovery-repair-remotes",
                "recovery-check",
                "recovery-reset",
                "recovery-return-base",
            ),
        )
        for action_id in (
            "recovery-inspect",
            "recovery-return-attempt",
            "recovery-repair-remotes",
            "recovery-check",
            "recovery-reset",
            "recovery-return-base",
        ):
            self.assertIn(f'data-action-id="{action_id}"', html)
        self.assertLess(html.index('data-action-id="recovery-inspect"'), positions[0])
        actions = {action.id: action for action in manifest.actions}
        self.assertEqual(
            {variant.command for variant in actions["recovery-return-attempt"].variants},
            {"git switch <attempt-branch>"},
        )
        repair_commands = "\n".join(
            variant.command for variant in actions["recovery-repair-remotes"].variants
        )
        for invariant in (
            "remote.origin.url https://github.com/YOUR-GITHUB-ACCOUNT/arbiter-academy.git",
            "remote.origin.pushurl https://github.com/YOUR-GITHUB-ACCOUNT/arbiter-academy.git",
            "remote.upstream.url https://github.com/arbiterForge/arbiter-academy.git",
            "remote.upstream.pushurl DISABLED",
            "git config remote.pushDefault origin",
            "pushRemote",
        ):
            self.assertIn(invariant, repair_commands)
        for shortcut in (
            "make the repository clean",
            "delete the branch",
            "reset --hard",
            "force-push",
        ):
            self.assertNotIn(shortcut, html.casefold())

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
            "P05-checkpoint-remediation",
            "P06-context-drift-recovery",
            "P07-threat-model",
        )
        expected_files = {
            "assets/academy.css",
            "assets/academy.js",
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
        self.assertNotIn("in verification", index)
        self.assertNotIn("coming-next", index)
        self.assertFalse((self.out / "labs" / "P08-repository-hygiene" / "index.html").exists())
        self.assertNotIn("P08-repository-hygiene", index)

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
            {"release": "preview-0.3", "commit": release_sha},
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
                "assets/academy.js",
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

    def test_static_checker_allows_only_repository_scoped_action_resources(self) -> None:
        """Catches a rendered action resource escaping the runtime URL contract."""
        root = Path(self.temporary_directory.name) / "resource-check"
        root.mkdir()
        page = root / "index.html"
        page.write_text("source", encoding="utf-8")
        approved = (
            "https://github.com/arbiterForge/arbiter-academy/blob/preview-0.3/install/install.ps1",
            "https://github.com/arbiterForge/arbiter-academy/releases/download/preview-0.3/install.ps1.sha256",
        )
        for target in approved:
            with self.subTest(target=target):
                self.assertIsNone(
                    preview_checker._resolve_local(root, page, target, allow_external=True)
                )
        for target in (
            "https://github.com/arbiterForge/other/blob/main/install.ps1",
            "https://github.com/arbiterForge/arbiter-academy/blob/main/../secret",
            "https://github.com/arbiterForge/arbiter-academy/blob/main/%252e%252e/secret",
            "https://github.com/arbiterForge/arbiter-academy/blob/main/file?raw=1",
            "https://github.com/arbiterForge/arbiter-academy/blob/main/file%0a",
            "/recovery/",
        ):
            with self.subTest(target=target):
                with self.assertRaises(ValueError):
                    preview_checker._resolve_local(root, page, target, allow_external=True)

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
                'id="know-before-you-begin"',
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
                self.assertIn("Graduation is not available in Preview 0.3", normalized)
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
        """Catches any byte mutation in every runtime asset reviewed for Preview 0.3."""
        assets = (
            "assets/academy.css",
            "assets/academy.js",
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

    def test_static_checker_rejects_html_release_identity_drift(self) -> None:
        """Catches deployed HTML claiming a different release than release.json."""
        build_preview_site(self.root, self.out, release_sha="b" * 40)
        index = self.out / "index.html"
        html = index.read_text(encoding="utf-8")
        current = '<meta name="academy-release" content="preview-0.3">'
        stale = '<meta name="academy-release" content="preview-0.2">'
        self.assertEqual(html.count(current), 1)
        index.write_text(html.replace(current, stale), encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "release identity"):
            check_preview_site(self.out)

    def test_build_renders_complete_reviewed_lesson_bodies(self) -> None:
        """Catches a published lab being reduced to a metadata shell."""
        build_preview_site(self.root, self.out, release_sha="c" * 40)

        f01 = (self.out / "labs" / "F01-fork-clone-doctor" / "index.html").read_text(encoding="utf-8")
        p02 = (self.out / "labs" / "P02-commit-review-pr" / "index.html").read_text(encoding="utf-8")
        p04 = (self.out / "labs" / "P04-review-a-dependency" / "index.html").read_text(encoding="utf-8")
        p05 = (self.out / "labs" / "P05-checkpoint-remediation" / "index.html").read_text(encoding="utf-8")
        p06 = (self.out / "labs" / "P06-context-drift-recovery" / "index.html").read_text(encoding="utf-8")
        self.assertIn('<article class="academy-content">', f01)
        self.assertIn("Know before you begin", f01)
        self.assertIn('class="language-powershell"', f01)
        self.assertIn("<strong>fork</strong>", f01)
        self.assertIn('data-action-id="F01-check"', f01)
        self.assertIn('<nav class="lab-toc" aria-label="On this page">', f01)
        self.assertIn('<div class="table-shell"><table>', p02)
        self.assertIn("Typical time", p02)
        self.assertIn('<code class="language-sh">', p02)
        self.assertIn("Candidate-Artifact", p04)
        self.assertIn("Continue to <strong>P05", p04)
        self.assertIn("test-only RED", p05)
        self.assertIn("ADR-0005", p05)
        self.assertIn("Continue to <strong>P06", p05)
        self.assertIn("<ol>", p06)
        self.assertIn("docs/preserved-note.md", p06)
        p07 = (self.out / "labs" / "P07-threat-model" / "index.html").read_text(encoding="utf-8")
        self.assertIn("P08 is not available in Academy Preview 0.3", p07)
        self.assertIn('<p class="lesson-publication-status">Guided lesson</p>', f01)
        for reference_lesson in (p02, p04, p05):
            self.assertIn("Reference lesson \u00b7 guided rewrite pending", reference_lesson)

    def test_guided_action_reference_renders_semantic_numbered_step(self) -> None:
        """Catches action rendering that loses execution identity or mutates commands."""
        source = Path(self.temporary_directory.name) / "guided-renderer"
        actions_directory = source / "academy" / "actions"
        actions_directory.mkdir(parents=True)
        manifest_data = {
            "schema_version": 1,
            "lesson_contract_version": 1,
            "document_id": "F01-fork-clone-doctor",
            "actions": [
                {
                    "id": "F01-prepare",
                    "sequence": 1,
                    "title": "Prepare the attempt",
                    "actor": "learner",
                    "surface": None,
                    "instruction": "Run <only> the command for your surface.",
                    "rationale": "Preparation creates a bounded attempt.",
                    "resources": [],
                    "variants": [
                        {
                            "id": "native-windows",
                            "surface": "native-terminal",
                            "operating_system": "windows",
                            "host": "none",
                            "language": "powershell",
                            "command": "& $academy --repository (Get-Location).Path prepare F01-fork-clone-doctor",
                            "copy": False,
                        },
                        {
                            "id": "codex-windows",
                            "surface": "harness",
                            "operating_system": "windows",
                            "host": "codex",
                            "language": "powershell",
                            "command": "! & $academy --repository (Get-Location).Path prepare F01-fork-clone-doctor",
                            "copy": True,
                        },
                    ],
                    "expected_result": "Academy prints attempt 1 prepared.",
                    "recovery": "If preparation refuses, preserve the message and inspect repository state.",
                    "evidence": "The attempt directory exists outside the learner branch.",
                }
            ],
        }
        (actions_directory / "F01-fork-clone-doctor.json").write_text(
            json.dumps(manifest_data), encoding="utf-8"
        )
        manifest = load_action_manifest(source, "F01-fork-clone-doctor")
        actions = {action.id: action for action in manifest.actions}

        rendered, headings, referenced = preview_site._render_markdown(
            "F01-fork-clone-doctor",
            ["# Fork and clone Doctor", "", "{{action:F01-prepare}}"],
            actions,
        )

        self.assertEqual(rendered.count('class="lesson-action"'), 1)
        self.assertEqual(rendered.count('class="academy-command-preferences"'), 1)
        self.assertIn('aria-labelledby="academy-os-heading"', rendered)
        self.assertIn('aria-labelledby="academy-host-heading"', rendered)
        self.assertIn('class="academy-command-preferences" hidden', rendered)
        self.assertIn(
            '<section class="lesson-action" data-action-id="F01-prepare" '
            'aria-labelledby="action-heading-F01-prepare">',
            rendered,
        )
        self.assertIn('id="action-heading-F01-prepare"', rendered)
        self.assertIn("Step 1", rendered)
        self.assertIn("You \u00b7 Native terminal \u00b7 Windows", rendered)
        self.assertIn("You \u00b7 Codex harness \u00b7 Windows", rendered)
        self.assertIn("Run &lt;only&gt; the command for your surface.", rendered)
        native_command = "&amp; $academy --repository (Get-Location).Path prepare F01-fork-clone-doctor"
        harness_command = "! &amp; $academy --repository (Get-Location).Path prepare F01-fork-clone-doctor"
        self.assertEqual(rendered.count(f">{native_command}</code>"), 1)
        self.assertEqual(rendered.count(f">{harness_command}</code>"), 1)
        self.assertNotIn('data-copy-target="command-F01-prepare-native-windows"', rendered)
        self.assertIn('data-copy-target="command-F01-prepare-codex-windows"', rendered)
        self.assertIn(
            '<code id="command-F01-prepare-codex-windows" tabindex="0"',
            rendered,
        )
        self.assertIn('aria-describedby="copy-status-F01-prepare-codex-windows"', rendered)
        self.assertIn('id="copy-status-F01-prepare-codex-windows"', rendered)
        self.assertIn('class="action-expected"', rendered)
        self.assertIn('class="action-recovery"', rendered)
        self.assertIn('class="action-evidence"', rendered)
        self.assertEqual(headings, ((1, "fork-and-clone-doctor", "Fork and clone Doctor"),))
        self.assertEqual(referenced, ("F01-prepare",))

        lesson_path = source / "academy" / "tracks" / "foundations" / "F01-fork-clone-doctor.md"
        lesson_path.parent.mkdir(parents=True)
        lesson_path.write_text(
            "---\n"
            "title: Fork and clone Doctor\n"
            "outcome: Establish a safe fork.\n"
            "estimated_minutes: 20\n"
            "next_lab: F02-orient-to-state\n"
            "---\n"
            "# Fork and clone Doctor\n\n"
            "{{action:F01-prepare}}\n",
            encoding="utf-8",
        )
        document = preview_site._read_markdown_document(
            source,
            Path("academy/tracks/foundations/F01-fork-clone-doctor.md"),
            "F01-fork-clone-doctor",
            require_h1=True,
        )
        self.assertEqual(document["referenced_actions"], ("F01-prepare",))
        self.assertEqual(document["heading"], "Fork and clone Doctor")
        self.assertIn('data-action-id="F01-prepare"', str(document["content"]))

    def test_guided_documents_require_one_to_one_action_references(self) -> None:
        """Catches ambiguous, missing, duplicated, or prose-injected action bindings."""
        action = preview_site.LessonAction(
            "F01-prepare",
            1,
            "Prepare",
            "learner",
            "browser",
            "Open the Academy fork page.",
            None,
            (),
            (),
            "The fork page opens.",
            "Return to the Academy home page and retry.",
            None,
        )
        actions = {action.id: action}
        invalid_documents = (
            (["# Guided", "Use {{action:F01-prepare}} now."], "standalone"),
            (["# Guided", "{{action:F01-prepare}}", "{{action:F01-prepare}}"], "duplicate"),
            (["# Guided", "{{action:F01-unknown}}"], "unknown"),
            (["# Guided", "No referenced action."], "unreferenced"),
            (["# Guided", "```powershell", "git status", "```", "{{action:F01-prepare}}"], "raw command"),
        )
        for lines, message in invalid_documents:
            with self.subTest(message=message):
                with self.assertRaisesRegex(ValueError, message):
                    preview_site._render_markdown("F01-fork-clone-doctor", lines, actions)

        injected = preview_site.LessonAction(
            "F01-injected",
            1,
            "<script>not markup</script>",
            "learner",
            "browser",
            "Open <b>nothing executable</b>.",
            None,
            (),
            (),
            "No script runs.",
            "Return safely.",
            None,
        )
        rendered = preview_site._render_action(injected)
        self.assertNotIn("<script>", rendered)
        self.assertNotIn("<b>", rendered)
        self.assertIn("&lt;script&gt;not markup&lt;/script&gt;", rendered)
        self.assertIn("Open &lt;b&gt;nothing executable&lt;/b&gt;.", rendered)

    def test_action_resources_render_adjacent_escaped_semantic_links(self) -> None:
        """Catches trusted source links rendered out of context or treated as active markup."""
        action = preview_site.LessonAction(
            "home-install",
            1,
            "Install the tools",
            "learner",
            "browser",
            "Review the installer source.",
            "The source is immutable.",
            (
                ActionResource(
                    "Review <installer> source",
                    "https://github.com/arbiterForge/arbiter-academy/blob/preview-0.3/install/install.ps1",
                ),
            ),
            (),
            "The source page opens.",
            "Return to the Academy Home page.",
            None,
        )

        rendered = preview_site._render_action(action)

        self.assertIn('<div class="action-resources">', rendered)
        self.assertIn("<strong>Reviewed resources for Install the tools</strong>", rendered)
        self.assertNotIn('<nav class="action-resources"', rendered)
        self.assertIn("Review &lt;installer&gt; source", rendered)
        self.assertNotIn("Review <installer> source", rendered)
        self.assertIn(
            'href="https://github.com/arbiterForge/arbiter-academy/blob/preview-0.3/install/install.ps1"',
            rendered,
        )
        self.assertLess(rendered.index("action-rationale"), rendered.index("action-resources"))
        self.assertLess(rendered.index("action-resources"), rendered.index("action-expected"))

    def test_non_command_renderer_labels_every_unambiguous_surface(self) -> None:
        """Catches loss of actor/surface/OS clarity on non-command lesson actions."""
        expected_labels = {
            "browser": "You \u00b7 Browser \u00b7 All operating systems",
            "native-terminal": "You \u00b7 Native terminal \u00b7 All operating systems",
            "academy-console": "You \u00b7 Academy console \u00b7 All operating systems",
            "active-harness": "You \u00b7 Active CodeArbiter harness \u00b7 All operating systems",
        }
        for surface, label in expected_labels.items():
            with self.subTest(surface=surface):
                action = preview_site.LessonAction(
                    f"F01-{surface}",
                    1,
                    "Inspect the surface",
                    "learner",
                    surface,
                    "Inspect the named surface.",
                    None,
                    (),
                    (),
                    "The surface is visible.",
                    "Return to the lesson and retry.",
                    None,
                )
                self.assertIn(label, preview_site._render_action(action))

        browser_action = preview_site.LessonAction(
            "F01-browser-only",
            1,
            "Open the fork page",
            "learner",
            "browser",
            "Open the fork page.",
            None,
            (),
            (),
            "The page opens.",
            "Return to the Academy home page.",
            None,
        )
        rendered, _headings, _references = preview_site._render_markdown(
            "F01-fork-clone-doctor",
            ["# Guided", "", "{{action:F01-browser-only}}"],
            {browser_action.id: browser_action},
        )
        self.assertNotIn("academy-command-preferences", rendered)

        console_variant = CommandVariant(
            "console-neutral",
            "academy-console",
            "all",
            "none",
            "text",
            "Run Check in the Academy console.",
            False,
        )
        console_action = preview_site.LessonAction(
            "F01-console-only",
            1,
            "Check the attempt",
            "academy",
            None,
            "Run Check.",
            None,
            (),
            (console_variant,),
            "Check passes.",
            "Open Recovery.",
            None,
        )
        rendered, _headings, _references = preview_site._render_markdown(
            "F01-fork-clone-doctor",
            ["# Guided", "", "{{action:F01-console-only}}"],
            {console_action.id: console_action},
        )
        self.assertNotIn("academy-command-preferences", rendered)

        ambiguous = self.non_command_manifest_action(surface="harness")
        with self.assertRaisesRegex(ValueError, "non-command actions cannot use harness"):
            validate_action_manifest(
                {
                    "schema_version": 1,
                    "lesson_contract_version": 1,
                    "document_id": "home",
                    "actions": [ambiguous],
                },
                expected_document_id="home",
            )

    def test_f01_review_boundary_renders_the_active_harness_without_a_command(self) -> None:
        manifest = load_action_manifest(self.root, "F01-fork-clone-doctor")
        action = next(
            action
            for action in manifest.actions
            if action.id == "F01-review-commit-boundary"
        )

        rendered = preview_site._render_action(action)

        self.assertIn(
            "You \u00b7 Active CodeArbiter harness \u00b7 All operating systems",
            rendered,
        )
        self.assertNotIn("Native terminal", rendered)
        self.assertNotIn("command-variant", rendered)
        self.assertNotIn("<pre>", rendered)

    def test_home_and_recovery_activate_only_with_complete_guide_action_pairs(self) -> None:
        """Catches partial or malformed guide publication and verifies real pair rendering."""
        source = self._copy_public_source()
        guides = source / "academy" / "guides"
        actions = source / "academy" / "actions"
        for document_id, action_id, heading in (
            ("home", "home-open", "Guided Academy home"),
            ("recovery", "recovery-inspect", "Guided recovery"),
        ):
            (guides / f"{document_id}.md").write_text(
                f"# {heading}\n\n{{{{action:{action_id}}}}}\n",
                encoding="utf-8",
            )
            (actions / f"{document_id}.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "lesson_contract_version": 1,
                        "document_id": document_id,
                        "actions": [self.non_command_manifest_action(action_id=action_id)],
                    }
                ),
                encoding="utf-8",
            )

        build_preview_site(source, self.out, release_sha="6" * 40)

        home = (self.out / "index.html").read_text(encoding="utf-8")
        recovery = (self.out / "recovery" / "index.html").read_text(encoding="utf-8")
        self.assertIn('data-action-id="home-open"', home)
        self.assertIn("Guided Academy home", home)
        self.assertIn('data-action-id="recovery-inspect"', recovery)
        self.assertIn("Guided recovery", recovery)

    def test_home_and_recovery_fail_closed_for_partial_or_malformed_pairs(self) -> None:
        """Catches a guide or action manifest reaching publication without its reviewed peer."""
        for document_id in ("home", "recovery"):
            for present in ("guide", "action"):
                with self.subTest(document_id=document_id, present=present):
                    source = self._copy_public_source(f"partial-{document_id}-{present}-source")
                    guide = source / "academy" / "guides" / f"{document_id}.md"
                    action = source / "academy" / "actions" / f"{document_id}.json"
                    guide.unlink()
                    action.unlink()
                    if present == "guide":
                        guide.write_text("# Partial guide\n", encoding="utf-8")
                    else:
                        action.write_text("{}", encoding="utf-8")
                    destination = self.out.parent / f"partial-{document_id}-{present}"
                    with self.assertRaisesRegex(ValueError, "guide/action pair"):
                        build_preview_site(source, destination, release_sha="7" * 40)
                    self.assertFalse(destination.exists())

        source = self._copy_public_source("malformed-home-source")
        guide = source / "academy" / "guides" / "home.md"
        action = source / "academy" / "actions" / "home.json"
        guide.write_text("# Malformed home\n\n{{action:home-open}}\n", encoding="utf-8")
        action.write_text("{", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "could not read lesson action manifest"):
            build_preview_site(source, self.out.parent / "malformed-home", release_sha="8" * 40)

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

    def test_markdown_renderer_rejects_block_syntax_nested_in_ordered_items(self) -> None:
        """Catches ordered-list continuations flattening nested block constructs into prose."""
        nested_blocks = (
            "> nested quote",
            "# nested heading",
            "1. nested ordered item",
            "| nested | table |",
        )
        source = self._copy_public_source()
        lesson = source / "academy" / "tracks" / "foundations" / "F01-fork-clone-doctor.md"
        original = lesson.read_text(encoding="utf-8")

        for index, nested_block in enumerate(nested_blocks):
            with self.subTest(nested_block=nested_block):
                lesson.write_text(
                    original + f"\n1. supported parent\n   {nested_block}\n",
                    encoding="utf-8",
                )
                destination = self.out.parent / f"nested-markdown-{index}"
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

    def test_home_action_code_blocks_use_the_bounded_scroll_container(self) -> None:
        """Catches long guided commands widening the whole home page instead of their code block."""
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
        self.assertIn('<script type="module" src="assets/academy.js"></script>', index)

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

    def test_generated_html_exposes_variants_without_javascript_and_checker_resolves_copy_references(self) -> None:
        """Catches hidden-by-default commands or copy controls detached from their exact code/status IDs."""
        action = preview_site.LessonAction(
            "F01-copy",
            1,
            "Copy one command",
            "learner",
            None,
            "Copy the command for your surface.",
            None,
            (),
            (
                CommandVariant(
                    "codex-windows",
                    "harness",
                    "windows",
                    "codex",
                    "powershell",
                    "!git status\n",
                    True,
                ),
            ),
            "Git reports status.",
            "Select the command manually.",
            None,
        )
        rendered, _headings, _references = preview_site._render_markdown(
            "F01-fork-clone-doctor",
            ["## Guided controls", "", "{{action:F01-copy}}"],
            {action.id: action},
        )
        self.assertIn('class="command-variant" data-os="windows" data-host="codex"', rendered)
        self.assertIn('class="academy-command-preferences" hidden', rendered)
        command_variant = rendered[rendered.index('class="command-variant"'):]
        self.assertNotIn(" hidden", command_variant.split(">", 1)[0])

        valid_destination = self.out.parent / "valid-command-controls"
        build_preview_site(self.root, valid_destination, release_sha="1" * 40)
        valid_page = valid_destination / "labs" / "F02-orient-to-state" / "index.html"
        valid_page.write_text(
            valid_page.read_text(encoding="utf-8").replace("</main>", f"{rendered}</main>", 1),
            encoding="utf-8",
        )
        check_preview_site(valid_destination)
        valid_html = valid_page.read_text(encoding="utf-8")
        valid_page.write_text(
            valid_html.replace('class="command-variant"', 'class="command-variant" hidden', 1),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "visible without JavaScript"):
            check_preview_site(valid_destination)
        for class_name in ("command-shell", "page-shell", "site-header__inner"):
            valid_page.write_text(
                valid_html.replace(
                    f'class="{class_name}"',
                    f'class="{class_name}" hidden',
                    1,
                ),
                encoding="utf-8",
            )
            with self.subTest(hidden=class_name):
                with self.assertRaisesRegex(ValueError, "hidden is reserved"):
                    check_preview_site(valid_destination)
        valid_page.write_text(
            valid_html.replace('<main id="main-content"', '<main hidden id="main-content"', 1),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "disallowed HTML attribute on main: hidden"):
            check_preview_site(valid_destination)
        valid_page.write_text(
            valid_html.replace('class="academy-command-preferences" hidden', 'class="academy-command-preferences"', 1),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "preference controls must be hidden"):
            check_preview_site(valid_destination)
        valid_page.write_text(
            valid_html.replace(
                'class="academy-command-preferences" hidden',
                'class="academy-command-preferences" hidden data-os="windows"',
                1,
            ),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "exact preference-container contract"):
            check_preview_site(valid_destination)
        valid_page.write_text(
            valid_html.replace(' tabindex="0" class="language-powershell"', ' class="language-powershell"', 1),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "command code is not focusable"):
            check_preview_site(valid_destination)

        build_preview_site(self.root, self.out, release_sha="1" * 40)
        page = self.out / "index.html"
        page.write_text(
            page.read_text(encoding="utf-8").replace(
                "</main>",
                '<button type="button" class="command-copy" data-copy-target="missing-command" '
                'aria-describedby="copy-status-probe">Copy</button>'
                '<p id="copy-status-probe" role="status" aria-live="polite"></p></main>',
                1,
            ),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "broken copy target"):
            check_preview_site(self.out)

        status_destination = self.out.parent / "copy-status-reference"
        build_preview_site(self.root, status_destination, release_sha="1" * 40)
        status_page = status_destination / "index.html"
        status_page.write_text(
            status_page.read_text(encoding="utf-8").replace(
                "</main>",
                '<code id="command-probe" tabindex="0">git status</code>'
                '<button type="button" class="command-copy" data-copy-target="command-probe" '
                'aria-describedby="missing-copy-status">Copy</button></main>',
                1,
            ),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "broken copy status"):
            check_preview_site(status_destination)

    def test_static_checker_requires_the_exact_local_module_on_every_page(self) -> None:
        """Catches a page substituting another local file for the reviewed Academy module."""
        build_preview_site(self.root, self.out, release_sha="1" * 40)
        page = self.out / "index.html"
        page.write_text(
            page.read_text(encoding="utf-8").replace(
                'src="assets/academy.js"',
                'src="assets/academy.css"',
                1,
            ),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "unapproved script asset"):
            check_preview_site(self.out)

    def _copy_public_source(self, label: str = "source") -> Path:
        source = Path(self.temporary_directory.name) / label
        academy = source / "academy"
        (academy / "publication").mkdir(parents=True)
        shutil.copy2(self.root / "academy" / "catalog.json", academy / "catalog.json")
        shutil.copy2(self.root / "academy" / "catalog.schema.json", academy / "catalog.schema.json")
        shutil.copy2(
            self.root / "academy" / "publication" / "preview-0.3.json",
            academy / "publication" / "preview-0.3.json",
        )
        for track in ("foundations", "practitioner"):
            shutil.copytree(
                self.root / "academy" / "tracks" / track,
                academy / "tracks" / track,
            )
        shutil.copytree(self.root / "academy" / "guides", academy / "guides")
        shutil.copytree(self.root / "academy" / "actions", academy / "actions")
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
        self._git(fixture, "clone", "--no-hardlinks", str(fork), str(learner))
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
        source = learner.parent / "arbiter-academy-source-preview-0.3"
        tools = learner.parent / "arbiter-academy-tools-preview-0.3"
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
