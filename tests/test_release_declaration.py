from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TARGETS = ROOT / ".codearbiter" / "release-targets.md"
RELEASE_MANIFEST = ROOT / "academy" / "release.json"
PAGES_WORKFLOW = ROOT / ".github" / "workflows" / "academy-pages.yml"

EXPECTED_ASSETS = (
    "install.ps1",
    "install.ps1.sha256",
    "install.sh",
    "install.sh.sha256",
    "arbiter-academy-preview-0.31.zip",
    "arbiter-academy-preview-0.31.zip.sha256",
)


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
        self.assertRegex(version, r"^(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)$")
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

    def test_ac02_renders_exactly_six_safe_assets_without_a_candidate_literal(self) -> None:
        text, fields = self.declaration()
        self.assertIsNone(re.search(r"preview-(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)", text))
        templates = fields.get("release-asset", [])
        rendered = tuple(
            template.replace("{version}", "0.31").replace("{tag}", "preview-0.31")
            for template in templates
        )
        self.assertEqual(rendered, EXPECTED_ASSETS)
        self.assertEqual(len({name.casefold() for name in rendered}), 6)
        for name in rendered:
            with self.subTest(asset=name):
                self.assertRegex(name, r"^[A-Za-z0-9][A-Za-z0-9._+-]*$")

    def test_ac03_stable_manifest_starts_at_immutable_predecessor(self) -> None:
        self.assertEqual(self.stable_version(), "0.30")

    def test_ac04_candidate_surfaces_form_one_valid_release_step(self) -> None:
        stable = self.stable_version()
        workflow = PAGES_WORKFLOW.read_text(encoding="utf-8")
        publication = json.loads(
            (ROOT / "academy" / "publication" / "preview-0.31.json").read_text(encoding="utf-8")
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

        stable_parts = tuple(int(part) for part in stable.split("."))
        candidate_parts = tuple(int(part) for part in candidates.pop().split("."))
        self.assertEqual(len(candidate_parts), len(stable_parts))
        self.assertIn(candidate_parts, (stable_parts, (*stable_parts[:-1], stable_parts[-1] + 1)))

    def test_ac05_builder_uses_release_variables_and_pages_epoch(self) -> None:
        _text, fields = self.declaration()
        workflow = PAGES_WORKFLOW.read_text(encoding="utf-8")
        epoch_match = re.search(r"(?m)^\s*RELEASE_EPOCH:\s*(\d+)\s*$", workflow)
        self.assertIsNotNone(epoch_match)
        command = fields.get("release-build", [])
        self.assertEqual(len(command), 1)
        build = command[0]
        self.assertIn('"$PY" scripts/build_release_assets.py', build)
        self.assertIn('--output "$RELEASE_ASSET_DIR"', build)
        self.assertIn('--release "$RELEASE_TAG"', build)
        self.assertIn(f"--epoch {epoch_match.group(1)}", build)

    def test_ac06_pre_tag_checks_are_portable_complete_and_check_only(self) -> None:
        _text, fields = self.declaration()
        self.assertEqual(
            fields.get("pre-tag"),
            [
                '"$PY" -m unittest discover -v',
                '"$PY" -m tabnanny academy_engine workshop_queue scripts tests',
            ],
        )


if __name__ == "__main__":
    unittest.main()
