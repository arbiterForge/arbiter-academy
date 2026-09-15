from __future__ import annotations

import ast
import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TARGETS = ROOT / ".codearbiter" / "release-targets.md"
RECONCILIATIONS = ROOT / ".codearbiter" / "release-changelog-reconciliations.json"
RELEASE_MANIFEST = ROOT / "academy" / "release.json"
PAGES_WORKFLOW = ROOT / ".github" / "workflows" / "academy-pages.yml"

EXPECTED_ASSETS = (
    "install.ps1",
    "install.ps1.sha256",
    "install.sh",
    "install.sh.sha256",
    "arbiter-academy-preview-0.32.zip",
    "arbiter-academy-preview-0.32.zip.sha256",
)

NUMERIC_VERSION = re.compile(r"^(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)$")


def validate_release_step(stable: str, candidate: str) -> None:
    if NUMERIC_VERSION.fullmatch(stable) is None:
        raise ValueError(f"invalid stable version: {stable}")
    if NUMERIC_VERSION.fullmatch(candidate) is None:
        raise ValueError(f"invalid candidate version: {candidate}")

    stable_parts = tuple(int(part) for part in stable.split("."))
    candidate_parts = tuple(int(part) for part in candidate.split("."))
    allowed = (stable_parts, (*stable_parts[:-1], stable_parts[-1] + 1))
    if candidate_parts not in allowed:
        raise ValueError(f"candidate {candidate} is not stable or the next release after {stable}")


class AcademyPreviewReleaseDeclarationTests(unittest.TestCase):
    def required_text(self, path: Path) -> str:
        self.assertTrue(path.is_file(), f"required release artifact is absent: {path.relative_to(ROOT)}")
        return path.read_text(encoding="utf-8")

    def declaration(self) -> tuple[str, dict[str, list[str]]]:
        text = self.required_text(TARGETS)
        opening = "<!-- release-targets -->"
        closing = "<!-- /release-targets -->"
        self.assertEqual(text.count(opening), 1)
        self.assertEqual(text.count(closing), 1)
        block = text.split(opening, 1)[1].split(closing, 1)[0]
        headers = re.findall(r"(?m)^\[([A-Za-z0-9._-]+)\]$", block)
        self.assertEqual(headers, ["academy-preview"])

        fields: dict[str, list[str]] = {}
        for line in block.splitlines():
            line = line.strip()
            if not line or line.startswith("["):
                continue
            self.assertRegex(line, r"^[a-z][a-z-]*: .+$")
            key, value = line.split(":", 1)
            fields.setdefault(key, []).append(value.strip())
        return text, fields

    def stable_version(self) -> str:
        text = self.required_text(RELEASE_MANIFEST)
        try:
            manifest = json.loads(text)
        except json.JSONDecodeError as exc:
            self.fail(f"academy/release.json is not valid JSON: {exc}")
        self.assertIsInstance(manifest, dict)
        version = manifest.get("version")
        self.assertIsInstance(version, str)
        self.assertRegex(version, NUMERIC_VERSION)
        return version

    def test_ac01_declares_one_generic_numeric_preview_target(self) -> None:
        _text, fields = self.declaration()
        expected = {
            "display-name": ["Arbiter Academy Preview"],
            "prefix": ["preview-"],
            "version-policy": ["numeric-sequence"],
            "initial-version": ["0.1"],
            "manifest": ["academy/release.json"],
            "changelog": ["CHANGELOG.md"],
            "payload": ["."],
            "latest-eligible": ["true"],
        }
        for key, value in expected.items():
            with self.subTest(field=key):
                self.assertEqual(fields.get(key), value)

    def test_ac01_excludes_only_governance_scratch_from_the_release_payload(self) -> None:
        _text, fields = self.declaration()
        self.assertEqual(
            fields.get("payload-exclude"),
            [".codearbiter/gate-events.log", ".codearbiter/.markers"],
        )

    def test_ac01_declares_the_exact_published_footer_reconciliation(self) -> None:
        _text, fields = self.declaration()
        self.assertEqual(
            fields.get("changelog-reconciliations"),
            [".codearbiter/release-changelog-reconciliations.json"],
        )

        ledger = json.loads(self.required_text(RECONCILIATIONS))
        self.assertEqual(set(ledger), {"schema_version", "entries"})
        self.assertEqual(ledger["schema_version"], 1)
        self.assertEqual(
            ledger["entries"],
            [
                {
                    "target": "academy-preview",
                    "commit_sha": "58eae666ce0013366cabb5c4d9674d6de4ac94c0",
                    "changelog": "Make Academy Preview release checks reusable across versions.",
                    "reason": "The published squash commit stored escaped newlines before its CHANGELOG footer.",
                    "authorization": "Campaign owner approved evidence-backed correction on 2026-09-14.",
                }
            ],
        )

    def test_ac02_renders_exactly_six_safe_assets_without_a_candidate_literal(self) -> None:
        text, fields = self.declaration()
        self.assertIsNone(re.search(r"preview-(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)", text))
        templates = fields.get("release-asset", [])
        rendered = tuple(
            template.replace("{version}", "0.32").replace("{tag}", "preview-0.32")
            for template in templates
        )
        self.assertEqual(rendered, EXPECTED_ASSETS)
        self.assertEqual(len({name.casefold() for name in rendered}), 6)
        for name in rendered:
            with self.subTest(asset=name):
                self.assertRegex(name, r"^[A-Za-z0-9][A-Za-z0-9._+-]*$")

    def test_ac03_stable_manifest_uses_the_declared_numeric_policy(self) -> None:
        _text, fields = self.declaration()
        self.assertEqual(fields.get("version-policy"), ["numeric-sequence"])
        self.assertRegex(self.stable_version(), NUMERIC_VERSION)

    def test_ac03_declaration_suite_does_not_pin_a_mutable_stable_version(self) -> None:
        tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
        pinned_versions = [
            constant.value
            for method in ast.walk(tree)
            if isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef))
            and method.name.startswith("test_ac03")
            for constant in ast.walk(method)
            if isinstance(constant, ast.Constant)
            and isinstance(constant.value, str)
            and NUMERIC_VERSION.fullmatch(constant.value)
        ]
        self.assertEqual(
            pinned_versions,
            [],
            "the reusable release declaration must not pin a mutable Preview version",
        )

    def test_ac04_candidate_surfaces_form_one_valid_release_step(self) -> None:
        stable = self.stable_version()
        workflow = PAGES_WORKFLOW.read_text(encoding="utf-8")
        publication = json.loads(
            (ROOT / "academy" / "publication" / "preview-0.32.json").read_text(encoding="utf-8")
        )
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        asset_tests = (ROOT / "tests" / "test_release_assets.py").read_text(encoding="utf-8")
        package = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

        patterns = {
            "Pages workflow": re.search(r"(?m)^\s*RELEASE_TAG:\s*preview-(\d+\.\d+)\s*$", workflow),
            "publication manifest": re.fullmatch(r"preview-(\d+\.\d+)", publication["release"]),
            "README heading": re.search(r"(?m)^## Preview (\d+\.\d+)\s*$", readme),
            "release-asset tests": re.search(r'(?m)^RELEASE = "preview-(\d+\.\d+)"$', asset_tests),
            "package-data path": re.search(r'academy/publication/preview-(\d+\.\d+)\.json', package),
        }
        for surface, match in patterns.items():
            with self.subTest(surface=surface):
                self.assertIsNotNone(match)
        candidates = {match.group(1) for match in patterns.values() if match is not None}
        self.assertEqual(len(candidates), 1)

        validate_release_step(stable, candidates.pop())

    def test_ac04_rejects_malformed_regressing_skipped_and_shape_changed_candidates(self) -> None:
        invalid_candidates = ("0.3x", "0.29", "0.32", "0.30.0")
        for candidate in invalid_candidates:
            with self.subTest(candidate=candidate), self.assertRaises(ValueError):
                validate_release_step("0.30", candidate)

    def test_ac04_accepts_the_stable_and_exactly_next_versions(self) -> None:
        for candidate in ("0.30", "0.31"):
            with self.subTest(candidate=candidate):
                validate_release_step("0.30", candidate)

    def test_ac05_builder_uses_release_variables_and_pages_epoch(self) -> None:
        _text, fields = self.declaration()
        workflow = PAGES_WORKFLOW.read_text(encoding="utf-8")
        epoch_match = re.search(r"(?m)^\s*RELEASE_EPOCH:\s*(\d+)\s*$", workflow)
        self.assertIsNotNone(epoch_match)
        command = fields.get("release-build", [])
        self.assertEqual(
            command,
            [
                '"$PY" scripts/build_release_assets.py --source . '
                '--output "$RELEASE_ASSET_DIR" '
                f'--epoch {epoch_match.group(1)} --release "$RELEASE_TAG"'
            ],
        )

    def test_ac06_pre_tag_checks_are_portable_focused_and_check_only(self) -> None:
        _text, fields = self.declaration()
        self.assertEqual(
            fields.get("pre-tag"),
            [
                '"$PY" -m unittest '
                'tests.test_preview_manifest '
                'tests.test_codearbiter_compatibility '
                'tests.test_preview_site '
                'tests.test_pages_workflow '
                'tests.test_release_declaration '
                'tests.test_release_assets '
                'tests.test_foundations_labs.PreviewCompatibilitySourceTests -v',
                '"$PY" -m tabnanny academy_engine workshop_queue scripts tests',
            ],
        )


if __name__ == "__main__":
    unittest.main()
