from __future__ import annotations

import hashlib
import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from academy_engine import preview
from academy_engine.preview import load_preview_manifest, validate_preview_manifest


PREVIEW_0_10 = [
    "F01-fork-clone-doctor",
    "F02-orient-to-state",
    "F03-work-the-board",
    "F04-fix-with-evidence",
    "P01-feature-through-plan",
    "P02-commit-review-pr",
    "P03-record-an-adr",
]
PREVIEW_0_11 = [
    *PREVIEW_0_10,
    "P04-review-a-dependency",
    "P05-checkpoint-remediation",
]
PREVIEW_0_12 = [
    *PREVIEW_0_11,
    "P06-context-drift-recovery",
    "P07-threat-model",
    "P08-repository-hygiene",
]
PREVIEW_0_15 = [
    *PREVIEW_0_12,
    "U01-autonomous-sprint",
    "U02-override-audit-metrics",
]
PREVIEW_0_16 = [*PREVIEW_0_15, "U03-refactor-chore-release"]
PREVIEW_0_20 = [
    *PREVIEW_0_16,
    "U04-initialize-projects",
    "U05-debug-spike-conflict",
    "U06-preview-and-advanced-surfaces",
    "U07-capstone",
]
COMING_NEXT_0_16 = ["U04-initialize-projects", "U05-debug-spike-conflict", "U06-preview-and-advanced-surfaces", "U07-capstone"]
COMING_NEXT: list[str] = []
DISCUSSION_URL = "https://github.com/arbiterForge/arbiter-academy/discussions"
PUBLIC_PREREQUISITES = (
    "A GitHub account that can create a personal fork.",
    "Git 2.39 or newer.",
    "Python 3.11 or newer.",
    "A supported CodeArbiter host: Claude Code, Codex, or Pi.",
    "Complete Academy Home setup steps 1-5 before starting F01.",
)
KNOWN_LIMITS = (
    "F01-F04, P01-P08, and U01-U07 are the guided lessons published in Preview 0.26.",
    "Graduation is available after all 19 Academy Checks pass in the same repository.",
)

PREVIEW_0_24 = [lab_id for lab_id in PREVIEW_0_20 if lab_id != "F03-work-the-board"]
PREVIEW_0_26 = PREVIEW_0_20



class PreviewManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(__file__).parents[1]

    def test_preview_zero_twenty_six_promotes_f03_without_rewriting_zero_twenty_five(
        self,
    ) -> None:
        """Catches a partial F03 promotion or a rewrite of immutable Preview 0.25."""
        publication = self.root / "academy" / "publication"
        historical = publication / "preview-0.25.json"
        current = publication / "preview-0.26.json"

        self.assertEqual(
            hashlib.sha256(historical.read_bytes()).hexdigest(),
            "de432144d003b299d5e9ddb8a68ba138f0da96b860a99e080d292b985a1983b4",
        )
        self.assertTrue(current.is_file())
        manifest = load_preview_manifest(self.root)
        old_data = json.loads(historical.read_text(encoding="utf-8"))
        new_data = json.loads(current.read_text(encoding="utf-8"))

        self.assertEqual(manifest.release, "preview-0.26")
        self.assertEqual(manifest.available_labs, tuple(PREVIEW_0_26))
        self.assertEqual(manifest.runnable_labs, tuple(PREVIEW_0_26))
        self.assertEqual(manifest.guided_labs, tuple(PREVIEW_0_26))
        self.assertEqual(manifest.available_labs[2], "F03-work-the-board")
        self.assertEqual(manifest.known_limits, KNOWN_LIMITS)
        self.assertEqual(new_data["catalog_sha256"], old_data["catalog_sha256"])

    def test_preview_zero_twenty_six_restores_f03_without_rewriting_f04(self) -> None:
        """F03 returns in catalog order without changing the accepted F04 prerequisite."""
        manifest = load_preview_manifest(self.root)
        catalog = json.loads((self.root / "academy/catalog.json").read_text(encoding="utf-8"))
        f04 = next(lab for lab in catalog["labs"] if lab["id"] == "F04-fix-with-evidence")

        self.assertEqual(manifest.release, "preview-0.26")
        self.assertEqual(manifest.available_labs, tuple(PREVIEW_0_26))
        self.assertEqual(manifest.runnable_labs, tuple(PREVIEW_0_26))
        self.assertEqual(manifest.guided_labs, tuple(PREVIEW_0_26))
        self.assertNotIn("F03-work-the-board", manifest.coming_next)
        self.assertEqual(f04["prerequisites"], ["F02-orient-to-state"])

    def test_preview_zero_sixteen_promotes_only_the_accepted_u03_closure(self) -> None:
        """U03 is public only with its prerequisites; U04-U07 remain private."""
        manifest = load_preview_manifest(self.root)

        self.assertEqual(manifest.release, "preview-0.26")
        self.assertEqual(manifest.available_labs, tuple(PREVIEW_0_26))
        self.assertEqual(manifest.runnable_labs, tuple(PREVIEW_0_26))
        self.assertEqual(manifest.guided_labs, tuple(PREVIEW_0_26))
        self.assertEqual(manifest.coming_next, tuple(COMING_NEXT))

    def test_preview_zero_nineteen_promotes_the_accepted_u06_closure(self) -> None:
        """U06 becomes public only with its five accepted Power User prerequisites."""
        manifest = load_preview_manifest(self.root)

        self.assertEqual(manifest.release, "preview-0.26")
        self.assertEqual(manifest.available_labs, tuple(PREVIEW_0_26))
        self.assertEqual(manifest.runnable_labs, tuple(PREVIEW_0_26))
        self.assertEqual(manifest.guided_labs, tuple(PREVIEW_0_26))
        self.assertEqual(manifest.coming_next, tuple(COMING_NEXT))

    def make_manifest(self, root: Path | None = None, **changes: object) -> dict[str, object]:
        root = root or self.root
        manifest: dict[str, object] = {
            "release": "preview-0.26",
            "lesson_contract_version": 1,
            "available_labs": PREVIEW_0_26,
            "runnable_labs": PREVIEW_0_26,
            "guided_labs": PREVIEW_0_26,
            "coming_next": COMING_NEXT,
            "prerequisites": list(PUBLIC_PREREQUISITES),
            "known_limits": list(KNOWN_LIMITS),
            "discussion_url": DISCUSSION_URL,
            "catalog_sha256": hashlib.sha256(
                (root / "academy" / "catalog.json").read_bytes()
            ).hexdigest(),
        }
        manifest.update(changes)
        return manifest

    def test_preview_zero_fifteen_preserves_the_practitioner_closure_and_adds_u01(self) -> None:
        manifest = load_preview_manifest(self.root)

        self.assertEqual(manifest.release, "preview-0.26")
        self.assertEqual(manifest.available_labs, tuple(PREVIEW_0_26))
        self.assertEqual(manifest.runnable_labs, tuple(PREVIEW_0_26))
        self.assertEqual(manifest.guided_labs, tuple(PREVIEW_0_26))
        self.assertEqual(manifest.coming_next, tuple(COMING_NEXT))

    def test_preview_zero_fifteen_keeps_u02_through_u07_private(self) -> None:
        manifest = load_preview_manifest(self.root)

        self.assertEqual(manifest.release, "preview-0.26")
        expected_public = tuple(PREVIEW_0_26)
        self.assertEqual(manifest.available_labs, expected_public)
        self.assertEqual(manifest.runnable_labs, expected_public)
        self.assertEqual(manifest.guided_labs, expected_public)
        self.assertEqual(manifest.coming_next, tuple(COMING_NEXT))

    def test_preview_zero_twelve_is_current_and_preserves_preview_zero_eleven_history(self) -> None:
        publication = self.root / "academy" / "publication"
        self.assertFalse((publication / "preview-0.6.json").exists())
        self.assertFalse((publication / "preview-0.7.json").exists())
        self.assertTrue((publication / "preview-0.9.json").is_file())
        self.assertTrue((publication / "preview-0.10.json").is_file())
        self.assertTrue((publication / "preview-0.11.json").is_file())
        self.assertTrue((publication / "preview-0.12.json").is_file())
        self.assertTrue((publication / "preview-0.13.json").is_file())
        manifest = load_preview_manifest(self.root)
        historical = json.loads((publication / "preview-0.10.json").read_text(encoding="utf-8"))
        self.assertEqual(historical["release"], "preview-0.10")
        self.assertEqual(historical["guided_labs"], PREVIEW_0_10)
        self.assertTrue((publication / "preview-0.14.json").is_file())
        self.assertTrue((publication / "preview-0.15.json").is_file())
        self.assertTrue((publication / "preview-0.19.json").is_file())
        self.assertTrue((publication / "preview-0.21.json").is_file())
        self.assertTrue((publication / "preview-0.22.json").is_file())
        self.assertTrue((publication / "preview-0.23.json").is_file())
        self.assertTrue((publication / "preview-0.24.json").is_file())
        self.assertTrue((publication / "preview-0.25.json").is_file())
        self.assertTrue((publication / "preview-0.26.json").is_file())
        expected = tuple(PREVIEW_0_26)
        self.assertEqual(manifest.release, "preview-0.26")
        self.assertEqual(manifest.available_labs, expected)
        self.assertEqual(manifest.runnable_labs, expected)
        self.assertEqual(manifest.guided_labs, expected)
        self.assertEqual(
            manifest.coming_next,
            tuple(COMING_NEXT),
        )

    def test_preview_manifest_separates_runnable_guided_and_coming_next(self) -> None:
        """Catches a public manifest that conflates runnable and guided readiness."""
        manifest = validate_preview_manifest(self.root, self.make_manifest())

        self.assertEqual(manifest.release, "preview-0.26")
        self.assertEqual(manifest.lesson_contract_version, 1)
        self.assertEqual(manifest.available_labs, tuple(PREVIEW_0_26))
        self.assertEqual(manifest.runnable_labs, tuple(PREVIEW_0_26))
        self.assertEqual(manifest.guided_labs, tuple(PREVIEW_0_26))
        self.assertEqual(manifest.coming_next, tuple(COMING_NEXT))

    def test_checked_in_public_boundary_is_preview_zero_sixteen_through_u03(self) -> None:
        """Catches a previous immutable preview identity being republished."""
        manifest = load_preview_manifest(self.root)

        self.assertEqual(manifest.release, "preview-0.26")
        self.assertEqual(manifest.available_labs, tuple(PREVIEW_0_26))
        self.assertEqual(manifest.runnable_labs, tuple(PREVIEW_0_26))
        self.assertEqual(manifest.guided_labs, tuple(PREVIEW_0_26))

    def test_public_release_exposes_only_lessons_that_are_fully_guided(self) -> None:
        """Reference material must not be advertised as a runnable public Academy lab."""
        manifest = load_preview_manifest(self.root)

        self.assertEqual(manifest.available_labs, manifest.guided_labs)
        self.assertEqual(manifest.runnable_labs, manifest.guided_labs)
        self.assertEqual(
            manifest.coming_next,
            tuple(COMING_NEXT),
        )

    def test_preview_manifest_exposes_public_onboarding_prerequisites_and_known_limits(self) -> None:
        """Catches a public release record that omits the conditions or limits of use."""
        manifest = load_preview_manifest(self.root)

        self.assertEqual(manifest.prerequisites, PUBLIC_PREREQUISITES)
        self.assertEqual(manifest.known_limits, KNOWN_LIMITS)

    def test_preview_manifest_rejects_the_immediately_stale_release_identity(self) -> None:
        """Catches immutable Preview 0.9 remaining the current publication identity."""
        with self.assertRaisesRegex(ValueError, "release must be preview-0.26"):
            validate_preview_manifest(
                self.root,
                self.make_manifest(release="preview-0.9"),
            )

    def test_preview_manifest_rejects_mismatched_compatibility_lists(self) -> None:
        """Catches the legacy available list disagreeing with runnable lab access."""
        with self.assertRaisesRegex(ValueError, "available_labs must equal runnable_labs"):
            validate_preview_manifest(
                self.root,
                self.make_manifest(available_labs=PREVIEW_0_26[:-1]),
            )

    def test_preview_manifest_rejects_a_boolean_lesson_contract_version(self) -> None:
        """Catches JSON booleans being mistaken for contract version integer 1."""
        with self.assertRaisesRegex(ValueError, "lesson_contract_version must be integer 1"):
            validate_preview_manifest(self.root, self.make_manifest(lesson_contract_version=True))

    def test_preview_manifest_rejects_unordered_guided_labs(self) -> None:
        """Catches an unpublished lab entering the guided claim."""
        with self.assertRaisesRegex(ValueError, "guided_labs must preserve catalog order"):
            validate_preview_manifest(
                self.root,
                self.make_manifest(guided_labs=["F02-orient-to-state", "F01-fork-clone-doctor"]),
            )

    def test_preview_manifest_rejects_an_omitted_required_guided_lab(self) -> None:
        """Catches F02 remaining runnable without the accepted guided publication claim."""
        with self.assertRaisesRegex(ValueError, "guided_labs"):
            validate_preview_manifest(
                self.root,
                self.make_manifest(guided_labs=["F01-fork-clone-doctor"]),
            )

    def test_preview_manifest_rejects_a_false_guided_claim(self) -> None:
        """Catches an unpublished lesson being publicly marked guided."""
        with self.assertRaisesRegex(ValueError, "guided_labs"):
            validate_preview_manifest(
                self.root,
                self.make_manifest(guided_labs=["P06-context-drift-recovery"]),
            )

    def test_preview_manifest_rejects_runnable_labs_also_marked_coming_next(self) -> None:
        """Catches a lab simultaneously advertised as runnable and upcoming."""
        with self.assertRaisesRegex(ValueError, "runnable_labs must not overlap coming_next"):
            validate_preview_manifest(
                self.root,
                self.make_manifest(coming_next=["F01-fork-clone-doctor"]),
            )

    def test_preview_manifest_exposes_distinct_runnable_and_guided_guards(self) -> None:
        """Catches verifier access and guided-lesson access silently sharing a claim."""
        preview.require_runnable_lab(self.root, "F01-fork-clone-doctor")
        preview.require_guided_lab(self.root, "F01-fork-clone-doctor")
        preview.require_published_lab(self.root, "F01-fork-clone-doctor")
        preview.require_runnable_lab(self.root, "P06-context-drift-recovery")
        preview.require_guided_lab(self.root, "P06-context-drift-recovery")

    def test_published_command_access_requires_a_guided_lesson(self) -> None:
        """Catches a future runnable-only lesson being dispatched before its public guidance exists."""
        future_manifest = preview.PreviewManifest(
            release="academy-1.0",
            lesson_contract_version=1,
            available_labs=("F01-fork-clone-doctor", "F02-orient-to-state"),
            runnable_labs=("F01-fork-clone-doctor", "F02-orient-to-state"),
            guided_labs=("F01-fork-clone-doctor",),
            coming_next=(),
            prerequisites=PUBLIC_PREREQUISITES,
            known_limits=KNOWN_LIMITS,
            discussion_url=DISCUSSION_URL,
            catalog_sha256="a" * 64,
        )

        with patch("academy_engine.preview.load_preview_manifest", return_value=future_manifest):
            preview.require_published_lab(self.root, "F01-fork-clone-doctor")
            with self.assertRaisesRegex(ValueError, "not guided"):
                preview.require_published_lab(self.root, "F02-orient-to-state")

    def test_preview_manifest_requires_the_full_prerequisite_closure(self) -> None:
        """Catches publication of a lab whose required learning path is absent."""
        manifest = self.make_manifest(
            available_labs=["P04-review-a-dependency"],
            runnable_labs=["P04-review-a-dependency"],
            coming_next=[],
        )

        with self.assertRaisesRegex(ValueError, "missing prerequisite"):
            validate_preview_manifest(self.root, manifest)

    def test_preview_manifest_rejects_an_unavailable_future_lab(self) -> None:
        """Catches a future lab being relabeled as available in this release."""
        manifest = self.make_manifest(
            available_labs=[*PREVIEW_0_11, "P06-context-drift-recovery"],
            runnable_labs=[*PREVIEW_0_11, "P06-context-drift-recovery"],
            guided_labs=[*PREVIEW_0_11, "P06-context-drift-recovery"],
            coming_next=COMING_NEXT,
        )

        with self.assertRaisesRegex(ValueError, "not eligible"):
            validate_preview_manifest(self.root, manifest)

    def test_preview_manifest_requires_the_reviewed_available_and_status_only_lists(self) -> None:
        """Catches omission or substitution in the public Preview 0.11 boundary."""
        manifest = self.make_manifest(coming_next=["P08-repository-hygiene"])

        with self.assertRaisesRegex(ValueError, "coming_next"):
            validate_preview_manifest(self.root, manifest)

    def test_preview_manifest_rejects_catalog_drift(self) -> None:
        """Catches a tracked selection becoming detached from the raw catalog bytes."""
        manifest = self.make_manifest(catalog_sha256="0" * 64)

        with self.assertRaisesRegex(ValueError, "catalog_sha256"):
            validate_preview_manifest(self.root, manifest)

    def test_repository_checkout_keeps_identity_bound_inputs_lf(self) -> None:
        """Catches platform checkout conversion changing catalog or P02 byte identities."""
        identity_paths = (
            "academy/catalog.json",
            ".codearbiter/tech-stack.md",
            "academy/scenarios/P02-commit-review-pr/files/P02-worktree.patch",
        )
        checked = subprocess.run(
            ["git", "check-attr", "-z", "eol", "--", *identity_paths],
            cwd=self.root,
            check=True,
            capture_output=True,
        ).stdout.rstrip(b"\0").split(b"\0")
        attributes = {
            path.decode("utf-8"): value.decode("ascii")
            for path, attribute, value in zip(
                checked[0::3], checked[1::3], checked[2::3], strict=True
            )
            if attribute == b"eol"
        }
        self.assertEqual(attributes, {path: "lf" for path in identity_paths})

        catalog = (self.root / "academy" / "catalog.json").read_bytes()
        self.assertNotIn(b"\r\n", catalog)
        manifest = json.loads(
            (self.root / "academy" / "publication" / "preview-0.26.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            manifest["catalog_sha256"],
            hashlib.sha256(catalog).hexdigest(),
        )

    def test_git_filters_keep_the_catalog_digest_stable_across_eol_modes(self) -> None:
        """Catches weakening the LF contract so Git rewrites identity-bound bytes."""
        catalog_path = "academy/catalog.json"
        manifest = json.loads(
            (self.root / "academy" / "publication" / "preview-0.26.json").read_text(
                encoding="utf-8"
            )
        )
        filtered_catalogs = {
            (autocrlf, eol): subprocess.run(
                [
                    "git",
                    "-c",
                    f"core.autocrlf={autocrlf}",
                    "-c",
                    f"core.eol={eol}",
                    "cat-file",
                    "--filters",
                    f"--path={catalog_path}",
                    f"HEAD:{catalog_path}",
                ],
                cwd=self.root,
                check=True,
                capture_output=True,
            ).stdout
            for autocrlf, eol in (("false", "lf"), ("true", "crlf"))
        }

        self.assertEqual(
            filtered_catalogs[("false", "lf")],
            filtered_catalogs[("true", "crlf")],
        )
        for mode, catalog in filtered_catalogs.items():
            with self.subTest(autocrlf=mode[0], eol=mode[1]):
                self.assertNotIn(b"\r\n", catalog)
                self.assertEqual(
                    hashlib.sha256(catalog).hexdigest(),
                    manifest["catalog_sha256"],
                )

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

    def test_publication_schema_pins_all_nineteen_guided_public_labs(self) -> None:
        """Catches F03 omission after its accepted guided promotion."""
        schema = json.loads(
            (self.root / "academy" / "publication" / "preview-manifest.schema.json").read_text(
                encoding="utf-8"
            )
        )
        available = schema["properties"]["available_labs"]
        runnable = schema["properties"]["runnable_labs"]
        guided = schema["properties"]["guided_labs"]
        coming_next = schema["properties"]["coming_next"]
        known_limits = schema["properties"]["known_limits"]

        self.assertEqual(schema["properties"]["release"]["const"], "preview-0.26")
        self.assertEqual(schema["properties"]["lesson_contract_version"]["const"], 1)
        self.assertEqual((available["minItems"], available["maxItems"]), (19, 19))
        self.assertEqual(
            [entry["const"] for entry in available["prefixItems"]],
            PREVIEW_0_26,
        )
        self.assertEqual((runnable["minItems"], runnable["maxItems"]), (19, 19))
        self.assertEqual(
            [entry["const"] for entry in runnable["prefixItems"]],
            PREVIEW_0_26,
        )
        self.assertEqual(
            [entry["const"] for entry in guided["prefixItems"]],
            PREVIEW_0_26,
        )
        self.assertEqual((coming_next["minItems"], coming_next["maxItems"]), (0, 0))
        self.assertEqual(
            [entry["const"] for entry in coming_next["prefixItems"]],
            COMING_NEXT,
        )
        self.assertEqual((known_limits["minItems"], known_limits["maxItems"]), (2, 2))
        self.assertEqual(
            [entry["const"] for entry in known_limits["prefixItems"]],
            list(KNOWN_LIMITS),
        )

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
        release_files = sorted(
            path.name
            for path in (self.root / "academy" / "publication").glob("preview-*.json")
            if path.name != "preview-manifest.schema.json"
        )
        manifest = load_preview_manifest(self.root)

        self.assertEqual(
            release_files,
            ["preview-0.10.json", "preview-0.11.json", "preview-0.12.json", "preview-0.13.json", "preview-0.14.json", "preview-0.15.json", "preview-0.16.json", "preview-0.17.json", "preview-0.18.json", "preview-0.19.json", "preview-0.20.json", "preview-0.21.json", "preview-0.22.json", "preview-0.23.json", "preview-0.24.json", "preview-0.25.json", "preview-0.26.json", "preview-0.4.json", "preview-0.9.json"],
        )
        historical = json.loads(
            (self.root / "academy" / "publication" / "preview-0.9.json").read_text(encoding="utf-8")
        )
        self.assertEqual(historical["release"], "preview-0.9")
        self.assertEqual(historical["guided_labs"], PREVIEW_0_10[:5])
        self.assertEqual(historical["coming_next"][:2], PREVIEW_0_10[5:])
        self.assertEqual(manifest.release, "preview-0.26")
        self.assertEqual(manifest.lesson_contract_version, 1)
        self.assertEqual(manifest.available_labs, tuple(PREVIEW_0_26))
        self.assertEqual(manifest.runnable_labs, tuple(PREVIEW_0_26))
        self.assertEqual(manifest.guided_labs, tuple(PREVIEW_0_26))
        self.assertEqual(manifest.coming_next, tuple(COMING_NEXT))
        self.assertEqual(manifest.prerequisites, PUBLIC_PREREQUISITES)
        self.assertEqual(manifest.known_limits, KNOWN_LIMITS)
        self.assertEqual(manifest.discussion_url, DISCUSSION_URL)


if __name__ == "__main__":
    unittest.main()
