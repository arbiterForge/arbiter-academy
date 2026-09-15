"""Real-Git contract tests for the codeArbiter compatibility checker."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

from tests._temporary import RetryingTemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "scripts" / "check_codearbiter_compatibility.py"

COMPONENTS = (
    {
        "component_id": "codearbiter",
        "display_name": "codeArbiter",
        "release_tag": "v2.17.11",
        "version": "2.17.11",
        "manifest_path": "plugins/ca/.claude-plugin/plugin.json",
        "manifest_bytes": b'{\n  "name": "ca",\n  "version": "2.17.11"\n}\n',
        "older_tags": ("v2.17.9", "v2.17.10"),
    },
    {
        "component_id": "ca-codex",
        "display_name": "Codex",
        "release_tag": "ca-codex-v0.9.11",
        "version": "0.9.11",
        "manifest_path": "plugins/ca-codex/.codex-plugin/plugin.json",
        "manifest_bytes": b'{\n  "name": "ca-codex",\n  "version": "0.9.11"\n}\n',
        "older_tags": ("ca-codex-v0.9.9", "ca-codex-v0.9.10"),
    },
    {
        "component_id": "ca-pi",
        "display_name": "Pi",
        "release_tag": "ca-pi-v0.10.13",
        "version": "0.10.13",
        "manifest_path": "plugins/ca-pi/package.json",
        "manifest_bytes": b'{\n  "name": "@arbiterforge/ca-pi",\n  "version": "0.10.13"\n}\n',
        "older_tags": ("ca-pi-v0.10.9", "ca-pi-v0.10.10"),
    },
)


class CompatibilityFixture:
    """A deterministic local repository plus its matching Preview declaration."""

    def __init__(
        self,
        root: Path,
        *,
        manifest_overrides: dict[str, bytes] | None = None,
    ) -> None:
        self.root = root
        self.repository = root / "codearbiter"
        self.manifest = root / "preview-fixture.json"
        self.environment = os.environ.copy()
        self.environment.update(
            {
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_GLOBAL": os.devnull,
                "GIT_AUTHOR_NAME": "Academy Compatibility Fixture",
                "GIT_AUTHOR_EMAIL": "academy-compatibility@example.invalid",
                "GIT_COMMITTER_NAME": "Academy Compatibility Fixture",
                "GIT_COMMITTER_EMAIL": "academy-compatibility@example.invalid",
                "GIT_AUTHOR_DATE": "2026-09-14T12:00:00+00:00",
                "GIT_COMMITTER_DATE": "2026-09-14T12:00:00+00:00",
            }
        )
        self.repository.mkdir()
        self.git("init", "--quiet", "--initial-branch=main")

        overrides = manifest_overrides or {}
        self.manifest_bytes: dict[str, bytes] = {}
        for component in COMPONENTS:
            component_id = str(component["component_id"])
            payload = overrides.get(component_id, component["manifest_bytes"])
            if not isinstance(payload, bytes):
                raise TypeError("fixture manifest payloads must be bytes")
            self.manifest_bytes[component_id] = payload
            path = self.repository / str(component["manifest_path"])
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)

        self.git("add", ".")
        self.git("commit", "--quiet", "-m", "fixture: shared component source")
        self.source_commit = self.git("rev-parse", "HEAD").stdout.strip()

        for component in COMPONENTS:
            release_tag = str(component["release_tag"])
            self.annotated_tag(release_tag)
            for older_tag in component["older_tags"]:
                self.annotated_tag(str(older_tag))

        self.declaration = {
            "release": "preview-fixture",
            "integration_compatibility": {
                "academy_release": "preview-fixture",
                "evidence_level": "release-and-command-contract",
                "components": [
                    {
                        "component_id": component["component_id"],
                        "display_name": component["display_name"],
                        "release_tag": component["release_tag"],
                        "version": component["version"],
                        "source_commit": self.source_commit,
                        "manifest_path": component["manifest_path"],
                        "manifest_sha256": hashlib.sha256(
                            self.manifest_bytes[str(component["component_id"])]
                        ).hexdigest(),
                    }
                    for component in COMPONENTS
                ],
            },
        }
        self.write_declaration()

    def git(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *arguments],
            cwd=self.repository,
            env=self.environment,
            check=True,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
        )

    def annotated_tag(self, name: str, target: str | None = None, *, force: bool = False) -> None:
        arguments = ["tag"]
        if force:
            arguments.append("--force")
        arguments.extend(("--annotate", name, target or self.source_commit, "-m", f"fixture {name}"))
        self.git(*arguments)

    def lightweight_tag(
        self, name: str, target: str | None = None, *, force: bool = False
    ) -> None:
        arguments = ["tag"]
        if force:
            arguments.append("--force")
        arguments.extend((name, target or self.source_commit))
        self.git(*arguments)

    def component(self, component_id: str) -> dict[str, object]:
        components = self.declaration["integration_compatibility"]["components"]
        return next(
            component
            for component in components
            if component["component_id"] == component_id
        )

    def write_declaration(self) -> None:
        self.manifest.write_text(
            json.dumps(self.declaration, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )

    def commit_unrelated_change(self) -> str:
        readme = self.repository / "README.md"
        readme.write_text("different tag target\n", encoding="utf-8", newline="\n")
        self.git("add", "README.md")
        self.git("commit", "--quiet", "-m", "fixture: different tag target")
        return self.git("rev-parse", "HEAD").stdout.strip()


class CodeArbiterCompatibilityTests(unittest.TestCase):
    maxDiff = 2048

    def setUp(self) -> None:
        self.temporary = RetryingTemporaryDirectory()
        self.fixture = CompatibilityFixture(Path(self.temporary.name))

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def run_checker(self) -> subprocess.CompletedProcess[str]:
        self.assertTrue(
            CHECKER.is_file(),
            "compatibility checker contract is absent: "
            "scripts/check_codearbiter_compatibility.py",
        )
        return subprocess.run(
            [
                sys.executable,
                str(CHECKER),
                "--manifest",
                str(self.fixture.manifest),
                "--codearbiter-root",
                str(self.fixture.repository),
            ],
            cwd=ROOT,
            env=self.fixture.environment,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=15,
        )

    def assert_bounded_rejection(
        self, component_id: str, *diagnostic_fragments: str
    ) -> None:
        result = self.run_checker()
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertNotIn("Traceback", result.stderr)
        self.assertLessEqual(len(result.stderr.encode("utf-8")), 512)
        self.assertLessEqual(len(result.stderr.splitlines()), 2)
        self.assertNotIn(str(self.fixture.root), result.stderr)
        self.assertIn(component_id, result.stderr)
        for fragment in diagnostic_fragments:
            self.assertIn(fragment, result.stderr.lower())

    def test_accepts_annotated_tags_that_peel_to_one_declared_source(self) -> None:
        result = self.run_checker()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stderr, "")

    def test_accepts_lightweight_release_tags_that_resolve_to_the_declared_source(self) -> None:
        """AC-02: release identity supports both annotated and lightweight Git tags."""
        self.fixture.lightweight_tag("ca-codex-v0.9.11", force=True)

        result = self.run_checker()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stderr, "")

    def test_numeric_freshness_accepts_lower_tags_in_all_three_families(self) -> None:
        """The fixture includes 0.9.9 and 0.9.10 so lexical max is observably wrong."""
        result = self.run_checker()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_numeric_freshness_ignores_well_formed_semver_prerelease_tags(self) -> None:
        """A historical prerelease is not a malformed member of the stable release family."""
        self.fixture.annotated_tag("v2.1.0-beta.2")

        result = self.run_checker()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_rejects_a_tag_that_peels_to_a_different_source_commit(self) -> None:
        wrong_target = self.fixture.commit_unrelated_change()
        self.fixture.annotated_tag(
            "ca-codex-v0.9.11", wrong_target, force=True
        )

        self.assert_bounded_rejection("ca-codex", "tag", "source")

    def test_rejects_a_missing_declared_manifest_path(self) -> None:
        self.fixture.component("ca-codex")["manifest_path"] = (
            "plugins/ca-codex/renamed/plugin.json"
        )
        self.fixture.write_declaration()

        self.assert_bounded_rejection("ca-codex", "manifest", "path")

    def test_rejects_unsafe_declared_manifest_paths_before_git_inspection(self) -> None:
        """AC-02/security: untrusted paths never escape into Git process arguments."""
        cases = {
            "nul": "plugins/ca-codex/bad\x00path.json",
            "control": "plugins/ca-codex/bad\x1fpath.json",
            "surrogate": "plugins/ca-codex/bad\ud800path.json",
            "oversized": "plugins/ca-codex/" + "x" * 4096 + ".json",
            "dot-segment": "./plugins/ca-codex/.codex-plugin/plugin.json",
            "empty-segment": "plugins//ca-codex/.codex-plugin/plugin.json",
        }
        for label, manifest_path in cases.items():
            with self.subTest(label=label):
                self.fixture.component("ca-codex")["manifest_path"] = manifest_path
                self.fixture.write_declaration()

                self.assert_bounded_rejection(
                    "ca-codex", "manifest", "path", "invalid"
                )

    def test_rejects_a_raw_manifest_version_mismatch(self) -> None:
        self.temporary.cleanup()
        self.temporary = RetryingTemporaryDirectory()
        self.fixture = CompatibilityFixture(
            Path(self.temporary.name),
            manifest_overrides={
                "ca-codex": b'{\n  "name": "ca-codex",\n  "version": "0.9.12"\n}\n'
            },
        )

        self.assert_bounded_rejection("ca-codex", "version")

    def test_rejects_a_digest_of_canonical_json_instead_of_the_raw_blob(self) -> None:
        raw = self.fixture.manifest_bytes["ca-codex"]
        canonical = json.dumps(
            json.loads(raw), sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        self.assertNotEqual(hashlib.sha256(raw).digest(), hashlib.sha256(canonical).digest())
        self.fixture.component("ca-codex")["manifest_sha256"] = hashlib.sha256(
            canonical
        ).hexdigest()
        self.fixture.write_declaration()

        self.assert_bounded_rejection("ca-codex", "sha-256")

    def test_rejects_malformed_members_of_a_release_tag_family(self) -> None:
        self.fixture.annotated_tag("ca-codex-v0.9.next")

        self.assert_bounded_rejection("ca-codex", "malformed", "tag")

    def test_rejects_ambiguous_numeric_versions_in_a_release_tag_family(self) -> None:
        self.fixture.annotated_tag("ca-codex-v0.09.11")

        self.assert_bounded_rejection("ca-codex", "ambiguous", "tag")

    def test_rejects_a_stale_codearbiter_declaration(self) -> None:
        self.fixture.annotated_tag("v2.17.12")

        self.assert_bounded_rejection("codearbiter", "stale", "v2.17.12")

    def test_rejects_a_stale_ca_codex_declaration(self) -> None:
        self.fixture.annotated_tag("ca-codex-v0.9.12")

        self.assert_bounded_rejection("ca-codex", "stale", "ca-codex-v0.9.12")

    def test_rejects_a_stale_ca_pi_declaration(self) -> None:
        self.fixture.annotated_tag("ca-pi-v0.10.14")

        self.assert_bounded_rejection("ca-pi", "stale", "ca-pi-v0.10.14")


if __name__ == "__main__":
    unittest.main()
