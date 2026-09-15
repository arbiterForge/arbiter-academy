from __future__ import annotations

import html
import hashlib
import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

from academy_engine import preview as preview_contract
from scripts.build_preview_site import build_preview_site


ROOT = Path(__file__).parents[1]
EXCLUDED_DOCUMENT = "U02-override-audit-metrics"
PROSE_FIELDS = (
    "title",
    "instruction",
    "rationale",
    "expected_result",
    "recovery",
    "evidence",
)
BASELINE_VARIANT_COUNT = 989
BASELINE_VARIANT_SHA256 = "dd53e90cd5d73a45ac64c2c5534fb1db9d9a7ac8edfb8715c89495aff902ba57"
MUTABLE_DISPLAY_COPY_PATHS = (
    "README.md",
    "academy_engine/curriculum.py",
    "academy_engine/lesson_actions.py",
    "scripts/build_preview_site.py",
    "tests/test_lesson_actions.py",
    "tests/test_power_user_u01.py",
    "tests/test_preview_site.py",
)
LAST_LEGACY_PUBLICATION = (0, 32)
PROTECTED_LEGACY_OCCURRENCE_COUNT = 95
PROTECTED_LEGACY_OCCURRENCE_SHA256 = (
    "ae5edb5831eedce67bedeba4c80fabdd5e8cbde4471c49b25f70876dd2558bf5"
)


def _markdown_prose(path: Path) -> str:
    """Return authored prose without code, link destinations, or quotations."""
    prose: list[str] = []
    in_fence = False
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.lstrip()
        if stripped.startswith(("```", "~~~")):
            in_fence = not in_fence
            continue
        if in_fence or stripped.startswith(">"):
            continue
        line = re.sub(r"`[^`]*`", "", line)
        line = re.sub(r"\]\([^)]+\)", "]", line)
        prose.append(line)
    return "\n".join(prose)


def _protected_legacy_occurrences() -> list[str]:
    """Return exact tracked legacy references outside this enforcement test."""
    tracked = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    ).stdout.decode("utf-8").split("\0")
    occurrences: list[str] = []
    for relative in tracked:
        if not relative or relative == "tests/test_product_naming.py":
            continue
        try:
            lines = (ROOT / relative).read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        occurrences.extend(
            f"{relative}:{line}" for line in lines if "CodeArbiter" in line
        )
    return occurrences


def _source_variants() -> dict[str, dict[str, object]]:
    variants: dict[str, dict[str, object]] = {}
    for path in sorted((ROOT / "academy" / "actions").glob("*.json")):
        manifest = json.loads(path.read_text(encoding="utf-8"))
        for action in manifest["actions"]:
            for variant in action["variants"]:
                command_id = f"command-{action['id']}-{variant['id']}"
                if command_id in variants:
                    raise AssertionError(f"duplicate source command identity: {command_id}")
                variants[command_id] = variant
    return variants


def _generated_commands(
    output: Path,
) -> tuple[dict[str, str], dict[str, dict[str, str]], int]:
    commands: dict[str, str] = {}
    metadata: dict[str, dict[str, str]] = {}
    variant_count = 0
    for path in sorted(output.rglob("*.html")):
        text = path.read_text(encoding="utf-8")
        variant_tags = re.findall(r'<div class="command-variant"[^>]*>', text)
        hidden = [tag for tag in variant_tags if re.search(r"\shidden(?:\s|=|>)", tag)]
        if hidden:
            raise AssertionError(
                f"command variants are hidden before JavaScript enhancement: {path.relative_to(output)}"
            )
        variant_count += len(variant_tags)
        for match in re.finditer(
            r'<div class="command-variant" data-os="([^"]+)" '
            r'data-host="([^"]+)" data-surface="([^"]+)">\s*'
            r'<p class="action-role">.*?</p>\s*<div class="command-shell">\s*'
            r'<pre><code id="(command-[^"]+)" tabindex="0" '
            r'class="language-([^"]+)">(.*?)</code></pre>',
            text,
            flags=re.DOTALL,
        ):
            operating_system, host, surface, command_id, language, encoded = match.groups()
            if command_id in commands:
                raise AssertionError(f"duplicate generated command identity: {command_id}")
            commands[command_id] = html.unescape(encoded)
            metadata[command_id] = {
                "operating_system": html.unescape(operating_system),
                "host": html.unescape(host),
                "surface": html.unescape(surface),
                "language": html.unescape(language),
            }
    return commands, metadata, variant_count


class ProductNamingAndCommandParityTests(unittest.TestCase):
    def test_protected_legacy_occurrences_require_reclassification(self) -> None:
        """Makes any new or changed legacy reference an explicit review event."""
        occurrences = _protected_legacy_occurrences()
        self.assertEqual(PROTECTED_LEGACY_OCCURRENCE_COUNT, len(occurrences))
        self.assertEqual(
            PROTECTED_LEGACY_OCCURRENCE_SHA256,
            hashlib.sha256("\n".join(occurrences).encode("utf-8")).hexdigest(),
        )

    def test_mutable_display_copy_uses_the_product_name(self) -> None:
        """Keeps mutable repository, diagnostic, and rendered labels on codeArbiter."""
        violations = [
            relative
            for relative in MUTABLE_DISPLAY_COPY_PATHS
            if "CodeArbiter" in (ROOT / relative).read_text(encoding="utf-8")
        ]
        self.assertEqual([], violations)

    def test_future_publications_cannot_inherit_legacy_product_copy(self) -> None:
        """Allows frozen releases while making the next Preview correct the legacy copy."""
        release = tuple(
            int(part)
            for part in preview_contract._RELEASE.removeprefix("preview-").split(".")
        )
        if release > LAST_LEGACY_PUBLICATION:
            self.assertFalse(
                any("CodeArbiter" in item for item in preview_contract._PREREQUISITES)
            )

        schema = json.loads(
            (ROOT / "academy/publication/preview-manifest.schema.json").read_text(
                encoding="utf-8"
            )
        )
        schema_release = tuple(
            int(part)
            for part in schema["properties"]["release"]["const"]
            .removeprefix("preview-")
            .split(".")
        )
        if schema_release > LAST_LEGACY_PUBLICATION:
            prerequisites = schema["properties"]["prerequisites"]["prefixItems"]
            self.assertNotIn("CodeArbiter", json.dumps(prerequisites))

        for path in sorted((ROOT / "academy/publication").glob("preview-*.json")):
            if path.name == "preview-manifest.schema.json":
                continue
            manifest = json.loads(path.read_text(encoding="utf-8"))
            manifest_release = tuple(
                int(part)
                for part in manifest["release"].removeprefix("preview-").split(".")
            )
            if manifest_release > LAST_LEGACY_PUBLICATION:
                self.assertNotIn("CodeArbiter", json.dumps(manifest["prerequisites"]))

    def test_mutable_product_copy_and_generated_commands_obey_contract(self) -> None:
        """Catches brand drift without changing command bytes or fallback presentation."""
        expected_variants = _source_variants()
        canonical_variants = json.dumps(
            expected_variants,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        self.assertEqual(BASELINE_VARIANT_COUNT, len(expected_variants))
        self.assertEqual(
            BASELINE_VARIANT_SHA256,
            hashlib.sha256(canonical_variants).hexdigest(),
            "command variants changed without an intentional reviewed baseline update",
        )
        installer_digests = {
            "{{INSTALL_PS1_SHA256}}": (ROOT / "install" / "install.ps1.sha256")
            .read_text(encoding="ascii")
            .split()[0],
            "{{INSTALL_SH_SHA256}}": (ROOT / "install" / "install.sh.sha256")
            .read_text(encoding="ascii")
            .split()[0],
        }
        expected_commands = {
            command_id: variant["command"]
            .replace("{{INSTALL_PS1_SHA256}}", installer_digests["{{INSTALL_PS1_SHA256}}"])
            .replace("{{INSTALL_SH_SHA256}}", installer_digests["{{INSTALL_SH_SHA256}}"])
            for command_id, variant in expected_variants.items()
        }
        expected_metadata = {
            command_id: {
                "operating_system": variant["operating_system"],
                "host": variant["host"],
                "surface": variant["surface"],
                "language": variant["language"],
            }
            for command_id, variant in expected_variants.items()
        }

        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "site"
            build_preview_site(ROOT, output, release_sha="a" * 40)
            generated_commands, generated_metadata, variant_count = _generated_commands(output)

        self.assertEqual(generated_commands, expected_commands)
        self.assertEqual(generated_metadata, expected_metadata)
        self.assertEqual(variant_count, len(expected_commands))

        violations: list[str] = []
        for path in sorted((ROOT / "academy" / "actions").glob("*.json")):
            if path.stem == EXCLUDED_DOCUMENT:
                continue
            manifest = json.loads(path.read_text(encoding="utf-8"))
            for action in manifest["actions"]:
                for field in PROSE_FIELDS:
                    value = action[field]
                    if value and "CodeArbiter" in value:
                        violations.append(f"{path.relative_to(ROOT)}:{action['id']}:{field}")
                for resource_index, resource in enumerate(action["resources"], start=1):
                    if "CodeArbiter" in resource["label"]:
                        violations.append(
                            f"{path.relative_to(ROOT)}:{action['id']}:resource:{resource_index}:label"
                        )

        markdown_paths = [ROOT / "academy" / "guides" / "home.md"]
        markdown_paths.extend(
            path
            for path in sorted((ROOT / "academy" / "tracks").rglob("*.md"))
            if path.stem != EXCLUDED_DOCUMENT
        )
        for path in markdown_paths:
            if "CodeArbiter" in _markdown_prose(path):
                violations.append(str(path.relative_to(ROOT)))

        self.assertEqual(
            [],
            violations,
            "future mutable Academy-authored product prose must use codeArbiter",
        )


if __name__ == "__main__":
    unittest.main()
