from __future__ import annotations

import json
import re
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from academy_engine.lesson_actions import (
    CommandVariant,
    LessonAction,
    LessonActionManifest,
    load_action_manifest,
    validate_action_resource_href,
    validate_action_manifest,
)


DOCUMENT_ID = "F01-fork-clone-doctor"
F01_ACTION_IDS = (
    "F01-prepare",
    "F01-inspect-remotes",
    "F01-repair-origin",
    "F01-set-upstream",
    "F01-disable-upstream-push",
    "F01-select-push-default",
    "F01-host-doctor",
    "F01-academy-doctor",
    "F01-inspect-report",
    "F01-stage-report",
    "F01-review-commit-boundary",
    "F01-commit-report",
    "F01-confirm-clean",
    "F01-check",
    "F01-return-base",
    "F01-reset-retry",
)
F02_DOCUMENT_ID = "F02-orient-to-state"
F02_ACTION_IDS = (
    "F02-prepare",
    "F02-run-status",
    "F02-read-context",
    "F02-follow-context-links",
    "F02-hash-context",
    "F02-write-orientation",
    "F02-inspect-orientation",
    "F02-stage-orientation",
    "F02-review-commit-boundary",
    "F02-run-commit-gate",
    "F02-confirm-clean",
    "F02-check",
    "F02-return-base",
    "F02-reset-retry",
)
F03_DOCUMENT_ID = "F03-work-the-board"
F03_ACTION_IDS = (
    "F03-prepare",
    "F03-read-target-task",
    "F03-start-task",
    "F03-inspect-started-task",
    "F03-complete-task",
    "F03-inspect-final-diff",
    "F03-stage-board",
    "F03-review-commit-boundary",
    "F03-run-commit-gate",
    "F03-confirm-clean",
    "F03-check",
    "F03-return-base",
    "F03-reset-retry",
)


class LessonActionTests(unittest.TestCase):
    def test_checked_in_f03_manifest_encodes_a_governed_one_commit_board_lifecycle(self) -> None:
        """Catches F03 becoming public without an explicit actor/surface/evidence contract."""
        manifest = load_action_manifest(Path(__file__).parents[1], F03_DOCUMENT_ID)

        self.assertEqual(tuple(action.id for action in manifest.actions), F03_ACTION_IDS)
        self.assertTrue(all(action.expected_result for action in manifest.actions))
        self.assertTrue(all(action.recovery for action in manifest.actions))
        by_id = {action.id: action for action in manifest.actions}

        for action_id in ("F03-start-task", "F03-complete-task", "F03-run-commit-gate"):
            action = by_id[action_id]
            self.assertEqual(action.actor, "agent")
            self.assertTrue(all(variant.language == "codearbiter" for variant in action.variants))
            self.assertFalse(any(variant.command.startswith("!") for variant in action.variants))

        shell_variants = tuple(
            variant
            for action in manifest.actions
            for variant in action.variants
            if variant.language in {"powershell", "sh"}
        )
        self.assertTrue(shell_variants)
        for variant in shell_variants:
            with self.subTest(variant=variant.id):
                if variant.surface == "harness":
                    self.assertNotEqual(variant.host, "none")
                    self.assertTrue(variant.command.startswith("!"))
                else:
                    self.assertEqual(variant.surface, "native-terminal")
                    self.assertEqual(variant.host, "none")
                    self.assertFalse(variant.command.startswith("!"))
                self.assertNotIn("python scripts/academy.py", variant.command)
                self.assertNotIn("<learner-repository>", variant.command)

        boundary = by_id["F03-review-commit-boundary"]
        self.assertEqual(boundary.actor, "learner")
        self.assertEqual(boundary.surface, None)
        self.assertIn(".codearbiter/open-tasks.md", boundary.expected_result)
        self.assertIn("whole worktree", boundary.instruction)
        self.assertIn("exactly one learner commit", by_id["F03-run-commit-gate"].evidence)
        final_diff = by_id["F03-inspect-final-diff"]
        self.assertTrue(
            all("git status --short" in variant.command for variant in final_diff.variants)
        )
    def test_active_public_action_paths_bind_to_preview_0_6(self) -> None:
        """Catches an active learner path routing to a prior Preview release."""
        root = Path(__file__).parents[1]
        for document_id in ("home", DOCUMENT_ID, F02_DOCUMENT_ID, F03_DOCUMENT_ID, "recovery"):
            with self.subTest(document_id=document_id):
                manifest = load_action_manifest(root, document_id)
                published_text = "\n".join(
                    part
                    for action in manifest.actions
                    for part in (
                        *(resource.href for resource in action.resources),
                        *(variant.command for variant in action.variants),
                        action.expected_result,
                        action.evidence or "",
                    )
                )
                self.assertNotIn("preview-0.4", published_text)
                self.assertIn("preview-0.6", published_text)

    def test_checked_in_f02_manifest_encodes_the_complete_ordered_lifecycle(self) -> None:
        manifest = load_action_manifest(Path(__file__).parents[1], F02_DOCUMENT_ID)

        self.assertEqual(tuple(action.id for action in manifest.actions), F02_ACTION_IDS)
        self.assertTrue(all(action.expected_result for action in manifest.actions))
        self.assertTrue(all(action.recovery for action in manifest.actions))

        by_id = {action.id: action for action in manifest.actions}
        for action_id in ("F02-run-status", "F02-run-commit-gate"):
            action = by_id[action_id]
            self.assertEqual(action.actor, "agent")
            self.assertEqual(
                tuple((variant.host, variant.command) for variant in action.variants),
                (
                    ("claude-code", "/ca:" + ("status" if action_id == "F02-run-status" else "commit")),
                    ("codex", "$ca-" + ("status" if action_id == "F02-run-status" else "commit")),
                    ("pi", "/ca-" + ("status" if action_id == "F02-run-status" else "commit")),
                    ("pi", "/skill:ca-" + ("status" if action_id == "F02-run-status" else "commit")),
                ),
            )
            self.assertTrue(all(variant.language == "codearbiter" for variant in action.variants))
            self.assertFalse(any(variant.command.startswith("!") for variant in action.variants))

        self.assertEqual(by_id["F02-write-orientation"].actor, "learner")
        self.assertEqual(by_id["F02-stage-orientation"].actor, "learner")

        context_links = by_id["F02-follow-context-links"]
        context_prompt = (
            "Open, do not summarize, these files in order: .codearbiter/specs/ticket-assignment.md, "
            ".codearbiter/plans/ticket-assignment.md, .codearbiter/decisions/0001-json-storage-boundary.md, "
            ".codearbiter/decisions/0002-explicit-ticket-state-machine.md, .codearbiter/coding-standards.md, "
            ".codearbiter/tech-stack.md, .codearbiter/security-controls.md, .codearbiter/open-tasks.md, "
            "and .codearbiter/open-questions.md. Then report the queued task ID, both ADR decisions, "
            "the verification command, and the local-only data boundary."
        )
        self.assertIsNone(context_links.surface)
        self.assertEqual(
            tuple(
                (variant.surface, variant.host, variant.language, variant.command, variant.copy)
                for variant in context_links.variants
            ),
            (
                ("harness", "claude-code", "text", context_prompt, True),
                ("harness", "codex", "text", context_prompt, True),
                ("harness", "pi", "text", context_prompt, True),
            ),
        )

        boundary = by_id["F02-review-commit-boundary"]
        review_prompt = (
            "Show the staged path list and staged diff. Do not commit. Report whether the staged path "
            "list is exactly .codearbiter/reports/academy/F02-orientation.json and whether the diff "
            "contains exactly schema_version, context_path, context_sha256, and stage."
        )
        self.assertIsNone(boundary.surface)
        self.assertEqual(
            tuple(
                (variant.surface, variant.host, variant.language, variant.command, variant.copy)
                for variant in boundary.variants
            ),
            (
                ("harness", "claude-code", "text", review_prompt, True),
                ("harness", "codex", "text", review_prompt, True),
                ("harness", "pi", "text", review_prompt, True),
            ),
        )

    def test_checked_in_f02_commands_are_surface_correct_and_beginner_safe(self) -> None:
        manifest = load_action_manifest(Path(__file__).parents[1], F02_DOCUMENT_ID)
        by_id = {action.id: action for action in manifest.actions}

        shell_variants = tuple(
            variant
            for action in manifest.actions
            for variant in action.variants
            if variant.language in {"powershell", "sh"}
        )
        self.assertTrue(shell_variants)
        for variant in shell_variants:
            with self.subTest(variant=variant.id):
                if variant.surface == "harness":
                    self.assertNotEqual(variant.host, "none")
                    self.assertTrue(variant.command.startswith("!"))
                    self.assertFalse(variant.command.startswith("!!"))
                else:
                    self.assertEqual(variant.surface, "native-terminal")
                    self.assertEqual(variant.host, "none")
                    self.assertFalse(variant.command.startswith("!"))
                self.assertNotIn("python scripts/academy.py", variant.command)
                self.assertNotIn("<learner-repository>", variant.command)

        write_commands = {
            variant.operating_system: variant.command
            for variant in by_id["F02-write-orientation"].variants
            if variant.surface == "native-terminal"
        }
        self.assertIn("ConvertTo-Json", write_commands["windows"])
        self.assertIn("WriteAllText", write_commands["windows"])
        self.assertIn("context_sha256", write_commands["windows"])
        windows_hash = next(
            variant.command
            for variant in by_id["F02-hash-context"].variants
            if variant.operating_system == "windows"
        )
        for command in (windows_hash, write_commands["windows"]):
            self.assertIn("ComputeHash", command)
            self.assertNotIn("HashData", command)
            self.assertNotIn("ToHexString", command)
        for operating_system in ("macos", "linux"):
            self.assertIn("json.dump", write_commands[operating_system])
            self.assertIn("context_sha256", write_commands[operating_system])

    def test_checked_in_f01_manifest_encodes_the_complete_ordered_lifecycle(self) -> None:
        manifest = load_action_manifest(Path(__file__).parents[1], DOCUMENT_ID)

        self.assertEqual(tuple(action.id for action in manifest.actions), F01_ACTION_IDS)
        self.assertTrue(all(action.expected_result for action in manifest.actions))
        self.assertTrue(all(action.recovery for action in manifest.actions))

        by_id = {action.id: action for action in manifest.actions}
        host_doctor = by_id["F01-host-doctor"]
        self.assertEqual(
            tuple((variant.host, variant.command) for variant in host_doctor.variants),
            (
                ("claude-code", "/ca:doctor"),
                ("codex", "$ca-doctor"),
                ("pi", "/ca-doctor"),
                ("pi", "/skill:ca-doctor"),
            ),
        )
        commit = by_id["F01-commit-report"]
        self.assertEqual(commit.actor, "agent")
        self.assertIsNone(commit.surface)
        self.assertEqual(
            tuple((variant.host, variant.command) for variant in commit.variants),
            (
                ("claude-code", "/ca:commit"),
                ("codex", "$ca-commit"),
                ("pi", "/ca-commit"),
                ("pi", "/skill:ca-commit"),
            ),
        )
        self.assertTrue(all(variant.language == "codearbiter" for variant in commit.variants))
        self.assertFalse(any(variant.command.startswith("!") for variant in commit.variants))
        self.assertEqual(by_id["F01-stage-report"].actor, "learner")
        self.assertEqual(by_id["F01-review-commit-boundary"].actor, "learner")
        self.assertEqual(by_id["F01-review-commit-boundary"].surface, "active-harness")
        self.assertFalse(by_id["F01-review-commit-boundary"].variants)

    def test_checked_in_f01_shell_variants_name_surface_and_passthrough_exactly(self) -> None:
        manifest = load_action_manifest(Path(__file__).parents[1], DOCUMENT_ID)
        shell_variants = tuple(
            variant
            for action in manifest.actions
            for variant in action.variants
            if variant.language in {"powershell", "sh"}
        )

        self.assertTrue(shell_variants)
        for variant in shell_variants:
            with self.subTest(variant=variant.id):
                if variant.surface == "harness":
                    self.assertNotEqual(variant.host, "none")
                    self.assertTrue(variant.command.startswith("!"))
                    self.assertFalse(variant.command.startswith("!!"))
                else:
                    self.assertEqual(variant.surface, "native-terminal")
                    self.assertEqual(variant.host, "none")
                    self.assertFalse(variant.command.startswith("!"))

    def schema(self) -> dict[str, object]:
        root = Path(__file__).parents[1]
        return json.loads(
            (root / "academy" / "lesson-action.schema.json").read_text(encoding="utf-8")
        )

    def schema_string_accepts(self, definition: dict[str, object], value: str) -> bool:
        return (
            int(definition["minLength"]) <= len(value) <= int(definition["maxLength"])
            and re.search(str(definition["pattern"]), value) is not None
        )

    def command_action(self, **variant_changes: object) -> dict[str, object]:
        variant: dict[str, object] = {
            "id": "status-codex-linux",
            "surface": "harness",
            "operating_system": "linux",
            "host": "codex",
            "language": "sh",
            "command": "!git status --short",
            "copy": True,
        }
        variant.update(variant_changes)
        return {
            "id": "inspect-status",
            "sequence": 1,
            "title": "Inspect the worktree",
            "actor": "learner",
            "surface": None,
            "instruction": "Run the status command in the named surface.",
            "rationale": "A clean worktree makes the evidence boundary explicit.",
            "resources": [],
            "variants": [variant],
            "expected_result": "Git prints no changed paths.",
            "recovery": "Restore only the lesson changes, then run the command again.",
            "evidence": "The later Academy Check reads the same worktree state.",
        }

    def non_command_action(self) -> dict[str, object]:
        return {
            "id": "read-prerequisites",
            "sequence": 1,
            "title": "Read the prerequisites",
            "actor": "learner",
            "surface": "browser",
            "instruction": "Read the prerequisite explanation before changing the repository.",
            "rationale": None,
            "resources": [],
            "variants": [],
            "expected_result": "You can identify the fork, origin, and upstream repositories.",
            "recovery": "Return to the prerequisite section and compare each repository role.",
            "evidence": None,
        }

    def manifest(self, action: dict[str, object] | None = None) -> dict[str, object]:
        return {
            "schema_version": 1,
            "lesson_contract_version": 1,
            "document_id": DOCUMENT_ID,
            "actions": [action or self.command_action()],
        }

    def test_valid_command_manifest_returns_frozen_typed_models(self) -> None:
        manifest = validate_action_manifest(self.manifest(), expected_document_id=DOCUMENT_ID)

        self.assertEqual(
            manifest,
            LessonActionManifest(
                schema_version=1,
                lesson_contract_version=1,
                document_id=DOCUMENT_ID,
                actions=(
                    LessonAction(
                        id="inspect-status",
                        sequence=1,
                        title="Inspect the worktree",
                        actor="learner",
                        surface=None,
                        instruction="Run the status command in the named surface.",
                        rationale="A clean worktree makes the evidence boundary explicit.",
                        resources=(),
                        variants=(
                            CommandVariant(
                                id="status-codex-linux",
                                surface="harness",
                                operating_system="linux",
                                host="codex",
                                language="sh",
                                command="!git status --short",
                                copy=True,
                            ),
                        ),
                        expected_result="Git prints no changed paths.",
                        recovery="Restore only the lesson changes, then run the command again.",
                        evidence="The later Academy Check reads the same worktree state.",
                    ),
                ),
            ),
        )
        with self.assertRaises(Exception):
            manifest.actions[0].title = "changed"  # type: ignore[misc]

    def test_valid_non_command_action_has_one_declared_surface(self) -> None:
        manifest = validate_action_manifest(
            self.manifest(self.non_command_action()), expected_document_id=DOCUMENT_ID
        )

        self.assertEqual(manifest.actions[0].surface, "browser")
        self.assertEqual(manifest.actions[0].variants, ())

    def test_action_resources_are_typed_bounded_and_repository_scoped(self) -> None:
        """Catches installer evidence links that escape the reviewed Academy repository."""
        action = self.command_action()
        action["resources"] = [
            {
                "label": "Review the immutable PowerShell installer",
                "href": "https://github.com/arbiterForge/arbiter-academy/blob/preview-0.3/install/install.ps1",
            }
        ]

        result = validate_action_manifest(self.manifest(action), expected_document_id=DOCUMENT_ID)

        self.assertEqual(result.actions[0].resources[0].label, "Review the immutable PowerShell installer")
        self.assertEqual(
            result.actions[0].resources[0].href,
            "https://github.com/arbiterForge/arbiter-academy/blob/preview-0.3/install/install.ps1",
        )

        invalid = (
            ("too-many", [{"label": "Source", "href": "https://github.com/arbiterForge/arbiter-academy"}] * 5),
            ("other-host", [{"label": "Source", "href": "https://example.com/arbiterForge/arbiter-academy"}]),
            ("credentials", [{"label": "Source", "href": "https://user@github.com/arbiterForge/arbiter-academy"}]),
            ("query", [{"label": "Source", "href": "https://github.com/arbiterForge/arbiter-academy?raw=1"}]),
            ("fragment", [{"label": "Source", "href": "https://github.com/arbiterForge/arbiter-academy#source"}]),
            ("root-relative", [{"label": "Source", "href": "/recovery/"}]),
            ("encoded-control", [{"label": "Source", "href": "https://github.com/arbiterForge/arbiter-academy/blob/main/file%0a"}]),
            ("traversal", [{"label": "Source", "href": "https://github.com/arbiterForge/arbiter-academy/blob/preview-0.3/%2e%2e/secret"}]),
            ("double-traversal", [{"label": "Source", "href": "https://github.com/arbiterForge/arbiter-academy/blob/preview-0.3/%252e%252e/secret"}]),
            ("scheme", [{"label": "Source", "href": "javascript:alert(1)"}]),
            ("backslash", [{"label": "Source", "href": "https://github.com/arbiterForge/arbiter-academy/blob\\main\\file"}]),
            ("blank-label", [{"label": "   ", "href": "https://github.com/arbiterForge/arbiter-academy"}]),
            ("long-label", [{"label": "x" * 161, "href": "https://github.com/arbiterForge/arbiter-academy"}]),
            ("long-href", [{"label": "Source", "href": "/" + "x" * 2048}]),
        )
        for label, resources in invalid:
            mutated = self.command_action()
            mutated["resources"] = resources
            with self.subTest(label=label):
                with self.assertRaises(ValueError):
                    validate_action_manifest(self.manifest(mutated), expected_document_id=DOCUMENT_ID)

    def test_resource_runtime_and_schema_share_exact_keys_and_bounds(self) -> None:
        schema = self.schema()
        resource = schema["$defs"]["resource"]  # type: ignore[index]

        self.assertFalse(resource["additionalProperties"])
        self.assertEqual(resource["required"], ["label", "href"])
        self.assertEqual(resource["properties"]["label"]["maxLength"], 160)
        self.assertEqual(resource["properties"]["href"]["maxLength"], 2048)
        self.assertEqual(schema["$defs"]["action"]["properties"]["resources"]["maxItems"], 4)
        href_schema = resource["properties"]["href"]
        self.assertTrue(
            self.schema_string_accepts(
                href_schema,
                "https://github.com/arbiterForge/arbiter-academy/blob/preview-0.3/install/install.sh",
            )
        )
        for href in (
            "https://example.com/arbiterForge/arbiter-academy",
            "https://github.com/arbiterForge/arbiter-academy?raw=1",
            "//github.com/arbiterForge/arbiter-academy",
            "/recovery/",
            "https://github.com/arbiterForge/arbiter-academy/blob/main/%0a",
            "https://github.com/arbiterForge/arbiter-academy/blob/main/%252e%252e/secret",
            "https://github.com/arbiterForge/arbiter-academy/blob/main/../secret",
            "https://github.com/arbiterForge/arbiter-academy/blob\\main\\file",
        ):
            self.assertFalse(self.schema_string_accepts(href_schema, href), href)

    def test_public_resource_validator_is_the_canonical_narrow_contract(self) -> None:
        accepted = (
            "https://github.com/arbiterForge/arbiter-academy",
            "https://github.com/arbiterForge/arbiter-academy/releases/download/preview-0.3/install.sh.sha256",
        )
        for href in accepted:
            with self.subTest(href=href):
                self.assertEqual(validate_action_resource_href(href), href)

        for href in (
            "/recovery/",
            "https://user@github.com/arbiterForge/arbiter-academy",
            "https://github.com/arbiterForge/arbiter-academy?raw=1",
            "https://github.com/arbiterForge/arbiter-academy#source",
            "https://github.com/arbiterForge/arbiter-academy/blob/main/%0a",
            "https://github.com/arbiterForge/arbiter-academy/blob/main/../secret",
        ):
            with self.subTest(href=href):
                with self.assertRaises(ValueError):
                    validate_action_resource_href(href)

    def test_non_command_actions_reject_harness_without_a_named_host(self) -> None:
        """Catches a host-ambiguous harness step with no command variant identity."""
        action = self.non_command_action()
        action["surface"] = "harness"

        with self.assertRaisesRegex(ValueError, "non-command actions cannot use harness"):
            validate_action_manifest(self.manifest(action), expected_document_id=DOCUMENT_ID)

        schema = self.schema()
        non_command_surfaces = schema["$defs"]["action"]["oneOf"][0]["properties"][  # type: ignore[index]
            "surface"
        ]["enum"]
        self.assertEqual(
            non_command_surfaces,
            ["browser", "native-terminal", "academy-console", "active-harness"],
        )

    def test_active_harness_is_closed_to_non_command_review_actions(self) -> None:
        action = self.non_command_action()
        action["surface"] = "active-harness"
        schema = self.schema()

        result = validate_action_manifest(
            self.manifest(action), expected_document_id=DOCUMENT_ID
        )

        self.assertEqual(result.actions[0].surface, "active-harness")
        self.assertNotIn(
            "active-harness", schema["$defs"]["variant"]["properties"]["surface"]["enum"]
        )
        action["variants"] = [self.command_action()["variants"][0]]
        action["surface"] = None
        action["id"] = "active-harness-command"
        action["variants"][0]["surface"] = "active-harness"  # type: ignore[index]
        with self.assertRaisesRegex(ValueError, "allowed"):
            validate_action_manifest(self.manifest(action), expected_document_id=DOCUMENT_ID)

    def test_rejects_unknown_or_missing_keys_at_every_level(self) -> None:
        cases: list[tuple[str, dict[str, object]]] = []
        unknown_manifest = self.manifest()
        unknown_manifest["extra"] = "no"
        cases.append(("manifest", unknown_manifest))
        missing_action = self.manifest()
        del missing_action["actions"][0]["recovery"]  # type: ignore[index]
        cases.append(("action", missing_action))
        unknown_variant = self.manifest()
        unknown_variant["actions"][0]["variants"][0]["display_command"] = "different"  # type: ignore[index]
        cases.append(("variant", unknown_variant))

        for level, data in cases:
            with self.subTest(level=level):
                with self.assertRaisesRegex(ValueError, "exact keys"):
                    validate_action_manifest(data, expected_document_id=DOCUMENT_ID)

    def test_versions_and_sequences_require_integers_not_booleans(self) -> None:
        mutations = (
            ("schema_version", True),
            ("lesson_contract_version", True),
            ("sequence", True),
        )
        for field, value in mutations:
            data = self.manifest()
            if field == "sequence":
                data["actions"][0][field] = value  # type: ignore[index]
            else:
                data[field] = value
            with self.subTest(field=field):
                with self.assertRaisesRegex(ValueError, "integer"):
                    validate_action_manifest(data, expected_document_id=DOCUMENT_ID)

    def test_contract_versions_are_pinned_to_one(self) -> None:
        for field in ("schema_version", "lesson_contract_version"):
            data = self.manifest()
            data[field] = 2
            with self.subTest(field=field):
                with self.assertRaisesRegex(ValueError, "must be integer 1"):
                    validate_action_manifest(data, expected_document_id=DOCUMENT_ID)

    def test_ids_are_bounded_and_path_safe(self) -> None:
        unsafe_ids = ("", ".", "..", "../lesson", "lesson/name", "lesson\\name", "-lesson", "a" * 97)
        for unsafe_id in unsafe_ids:
            data = self.manifest()
            data["actions"][0]["id"] = unsafe_id  # type: ignore[index]
            with self.subTest(unsafe_id=unsafe_id):
                with self.assertRaisesRegex(ValueError, "safe ID"):
                    validate_action_manifest(data, expected_document_id=DOCUMENT_ID)

    def test_runtime_and_schema_share_the_ascii_id_character_limit(self) -> None:
        schema = self.schema()
        id_schema = schema["$defs"]["id"]  # type: ignore[index]
        bounded_id = "a" * 96
        action = self.command_action()
        action["id"] = bounded_id
        action["variants"][0]["id"] = bounded_id  # type: ignore[index]
        data = self.manifest(action)
        data["document_id"] = bounded_id

        result = validate_action_manifest(data, expected_document_id=bounded_id)

        self.assertEqual(result.document_id, bounded_id)
        self.assertEqual(result.actions[0].id, bounded_id)
        self.assertEqual(result.actions[0].variants[0].id, bounded_id)
        self.assertTrue(self.schema_string_accepts(id_schema, bounded_id))
        self.assertFalse(self.schema_string_accepts(id_schema, "a" * 97))

    def test_document_id_must_match_the_requested_document(self) -> None:
        with self.assertRaisesRegex(ValueError, "document_id must match"):
            validate_action_manifest(self.manifest(), expected_document_id="F02-orient-to-state")

    def test_actions_are_limited_unique_and_contiguously_sequenced(self) -> None:
        duplicate = self.command_action()
        duplicate["sequence"] = 2
        for label, actions, message in (
            ("duplicate", [self.command_action(), duplicate], "unique action IDs"),
            ("gap", [self.command_action(), {**deepcopy(duplicate), "id": "second", "sequence": 3}], "contiguous"),
            ("too-many", [{**self.non_command_action(), "id": f"action-{index}", "sequence": index + 1} for index in range(65)], "at most 64"),
        ):
            data = self.manifest()
            data["actions"] = actions
            with self.subTest(label=label):
                with self.assertRaisesRegex(ValueError, message):
                    validate_action_manifest(data, expected_document_id=DOCUMENT_ID)

    def test_action_enumerations_are_closed(self) -> None:
        for field, value in (("actor", "operator"), ("surface", "terminal")):
            action = self.non_command_action()
            action[field] = value
            with self.subTest(field=field):
                with self.assertRaisesRegex(ValueError, "allowed"):
                    validate_action_manifest(self.manifest(action), expected_document_id=DOCUMENT_ID)

    def test_variant_enumerations_are_closed(self) -> None:
        for field, value in (
            ("surface", "terminal"),
            ("operating_system", "freebsd"),
            ("host", "other"),
            ("language", "bash"),
        ):
            with self.subTest(field=field):
                data = self.manifest(self.command_action(**{field: value}))
                with self.assertRaisesRegex(ValueError, "allowed"):
                    validate_action_manifest(data, expected_document_id=DOCUMENT_ID)

    def test_command_and_non_command_shapes_cannot_be_ambiguous(self) -> None:
        command_with_surface = self.command_action()
        command_with_surface["surface"] = "browser"
        non_command_without_surface = self.non_command_action()
        non_command_without_surface["surface"] = None
        for label, action in (
            ("command", command_with_surface),
            ("non-command", non_command_without_surface),
        ):
            with self.subTest(label=label):
                with self.assertRaisesRegex(ValueError, "command actions|non-command actions"):
                    validate_action_manifest(self.manifest(action), expected_document_id=DOCUMENT_ID)

    def test_variants_are_limited_and_unique(self) -> None:
        action = self.command_action()
        variant = deepcopy(action["variants"][0])  # type: ignore[index]
        action["variants"] = [deepcopy(variant), deepcopy(variant)]
        with self.assertRaisesRegex(ValueError, "unique variant IDs"):
            validate_action_manifest(self.manifest(action), expected_document_id=DOCUMENT_ID)

        action["variants"] = [{**deepcopy(variant), "id": f"variant-{index}"} for index in range(13)]
        with self.assertRaisesRegex(ValueError, "at most 12"):
            validate_action_manifest(self.manifest(action), expected_document_id=DOCUMENT_ID)

    def test_copy_policy_is_an_explicit_boolean(self) -> None:
        for copy in (1, "yes", None):
            with self.subTest(copy=copy):
                data = self.manifest(self.command_action(copy=copy))
                with self.assertRaisesRegex(ValueError, "copy must be a boolean"):
                    validate_action_manifest(data, expected_document_id=DOCUMENT_ID)

        result = validate_action_manifest(
            self.manifest(self.command_action(copy=False)), expected_document_id=DOCUMENT_ID
        )
        self.assertFalse(result.actions[0].variants[0].copy)

    def test_harness_shell_requires_exactly_one_passthrough_prefix(self) -> None:
        for command in ("git status", "!!git status"):
            with self.subTest(command=command):
                data = self.manifest(self.command_action(command=command))
                with self.assertRaisesRegex(ValueError, "exactly one !"):
                    validate_action_manifest(data, expected_document_id=DOCUMENT_ID)

    def test_codearbiter_invocations_reject_shell_passthrough(self) -> None:
        data = self.manifest(
            self.command_action(command="!$ca-doctor", language="codearbiter")
        )
        with self.assertRaisesRegex(ValueError, "must not begin with !"):
            validate_action_manifest(data, expected_document_id=DOCUMENT_ID)

    def test_native_terminal_uses_no_host_and_never_uses_passthrough(self) -> None:
        for field, value, message in (
            ("host", "codex", "host none"),
            ("command", "!git status", "must not begin with !"),
        ):
            action = self.command_action(
                surface="native-terminal",
                host="none",
                operating_system="windows",
                language="powershell",
                command="git status",
            )
            action["variants"][0][field] = value  # type: ignore[index]
            data = self.manifest(action)
            with self.subTest(field=field):
                with self.assertRaisesRegex(ValueError, message):
                    validate_action_manifest(data, expected_document_id=DOCUMENT_ID)

    def test_harness_requires_a_named_host(self) -> None:
        data = self.manifest(self.command_action(host="none"))
        with self.assertRaisesRegex(ValueError, "named host"):
            validate_action_manifest(data, expected_document_id=DOCUMENT_ID)

    def test_codearbiter_language_requires_a_harness_and_named_host(self) -> None:
        data = self.manifest(
            self.command_action(
                surface="native-terminal",
                host="none",
                operating_system="all",
                language="codearbiter",
                command="$ca-doctor",
            )
        )
        with self.assertRaisesRegex(ValueError, "CodeArbiter commands require a harness"):
            validate_action_manifest(data, expected_document_id=DOCUMENT_ID)

    def test_codearbiter_commands_use_each_hosts_native_invocation(self) -> None:
        cases = (
            ("claude-code", "/ca-doctor", "Claude Code"),
            ("codex", "/ca:doctor", "Codex"),
            ("pi", "$ca-doctor", "Pi"),
        )
        for host, command, message in cases:
            data = self.manifest(
                self.command_action(host=host, language="codearbiter", command=command)
            )
            with self.subTest(host=host):
                with self.assertRaisesRegex(ValueError, message):
                    validate_action_manifest(data, expected_document_id=DOCUMENT_ID)

    def test_prose_and_commands_are_bounded_and_control_safe(self) -> None:
        cases: list[tuple[str, dict[str, object], str]] = []
        for field in ("title", "instruction", "rationale", "expected_result", "recovery", "evidence"):
            action = self.command_action()
            action[field] = "x" * 1025
            cases.append((field, self.manifest(action), "at most 1024"))
        empty_expected = self.command_action()
        empty_expected["expected_result"] = "   "
        cases.append(("expected", self.manifest(empty_expected), "must not be empty"))
        empty_recovery = self.command_action()
        empty_recovery["recovery"] = ""
        cases.append(("recovery", self.manifest(empty_recovery), "must not be empty"))
        control = self.command_action()
        control["instruction"] = "unsafe\nprose"
        cases.append(("prose-control", self.manifest(control), "ASCII controls"))
        long_command = self.command_action(command="!" + "x" * 8192)
        cases.append(("long-command", self.manifest(long_command), "at most 8192"))
        command_control = self.command_action(command="!git\tstatus")
        cases.append(("command-control", self.manifest(command_control), "ASCII controls"))
        command_cr = self.command_action(command="!git status\r\n")
        cases.append(("command-cr", self.manifest(command_cr), "CR"))

        for label, data, message in cases:
            with self.subTest(label=label):
                with self.assertRaisesRegex(ValueError, message):
                    validate_action_manifest(data, expected_document_id=DOCUMENT_ID)

    def test_runtime_and_schema_use_unicode_code_point_limits_for_every_bounded_string(self) -> None:
        schema = self.schema()
        prose_schema = schema["$defs"]["prose"]  # type: ignore[index]
        command_schema = schema["$defs"]["variant"]["properties"]["command"]  # type: ignore[index]
        accepted_prose = "é" * 600
        rejected_prose = "é" * 1025
        accepted_command = "!" + "é" * 600
        rejected_command = "!" + "é" * 8192

        for field in (
            "title",
            "instruction",
            "rationale",
            "expected_result",
            "recovery",
            "evidence",
        ):
            action = self.command_action()
            action[field] = accepted_prose
            with self.subTest(field=field, boundary="accepted"):
                result = validate_action_manifest(
                    self.manifest(action), expected_document_id=DOCUMENT_ID
                )
                self.assertEqual(getattr(result.actions[0], field), accepted_prose)
                self.assertTrue(self.schema_string_accepts(prose_schema, accepted_prose))

            action[field] = rejected_prose
            with self.subTest(field=field, boundary="rejected"):
                with self.assertRaisesRegex(ValueError, "at most 1024 characters"):
                    validate_action_manifest(
                        self.manifest(action), expected_document_id=DOCUMENT_ID
                    )
                self.assertFalse(self.schema_string_accepts(prose_schema, rejected_prose))

        accepted = validate_action_manifest(
            self.manifest(self.command_action(command=accepted_command)),
            expected_document_id=DOCUMENT_ID,
        )
        self.assertEqual(accepted.actions[0].variants[0].command, accepted_command)
        self.assertTrue(self.schema_string_accepts(command_schema, accepted_command))
        with self.assertRaisesRegex(ValueError, "at most 8192 characters"):
            validate_action_manifest(
                self.manifest(self.command_action(command=rejected_command)),
                expected_document_id=DOCUMENT_ID,
            )
        self.assertFalse(self.schema_string_accepts(command_schema, rejected_command))

    def test_runtime_and_schema_reject_whitespace_only_bounded_strings(self) -> None:
        schema = self.schema()
        prose_schema = schema["$defs"]["prose"]  # type: ignore[index]
        command_schema = schema["$defs"]["variant"]["properties"]["command"]  # type: ignore[index]

        for field in (
            "title",
            "instruction",
            "rationale",
            "expected_result",
            "recovery",
            "evidence",
        ):
            action = self.command_action()
            action[field] = "   "
            with self.subTest(field=field):
                with self.assertRaisesRegex(ValueError, "must not be empty"):
                    validate_action_manifest(
                        self.manifest(action), expected_document_id=DOCUMENT_ID
                    )
                self.assertFalse(self.schema_string_accepts(prose_schema, "   "))

        whitespace_command = "   "
        with self.assertRaisesRegex(ValueError, "must not be empty"):
            validate_action_manifest(
                self.manifest(self.command_action(command=whitespace_command)),
                expected_document_id=DOCUMENT_ID,
            )
        self.assertFalse(self.schema_string_accepts(command_schema, whitespace_command))

    def test_command_newlines_are_allowed_and_preserved_as_visible_copy_bytes(self) -> None:
        command = "!git status --short\nprintf 'done\\n'"
        data = self.manifest(self.command_action(command=command))

        result = validate_action_manifest(data, expected_document_id=DOCUMENT_ID)

        self.assertEqual(result.actions[0].variants[0].command, command)

    def test_loader_rejects_unsafe_document_ids_before_filesystem_access(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for document_id in ("../outside", "lesson/name", "lesson\\name", ".", ".."):
                with self.subTest(document_id=document_id):
                    with self.assertRaisesRegex(ValueError, "safe ID"):
                        load_action_manifest(root, document_id)

    def test_loader_reads_only_the_named_action_manifest_and_validates_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            actions = root / "academy" / "actions"
            actions.mkdir(parents=True)
            (actions / f"{DOCUMENT_ID}.json").write_text(
                json.dumps(self.manifest()), encoding="utf-8", newline="\n"
            )

            result = load_action_manifest(root, DOCUMENT_ID)

            self.assertEqual(result.document_id, DOCUMENT_ID)

    def test_loader_rejects_an_actions_ancestor_symlink_outside_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "root"
            academy = root / "academy"
            outside = base / "outside-actions"
            academy.mkdir(parents=True)
            outside.mkdir()
            (outside / f"{DOCUMENT_ID}.json").write_text(
                json.dumps(self.manifest()), encoding="utf-8", newline="\n"
            )
            try:
                (academy / "actions").symlink_to(outside, target_is_directory=True)
            except OSError as error:
                self.skipTest(f"directory symlinks are unavailable: {error}")

            with self.assertRaisesRegex(ValueError, "symlink or reparse"):
                load_action_manifest(root, DOCUMENT_ID)

    def test_loader_rejects_a_manifest_symlink_outside_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "root"
            actions = root / "academy" / "actions"
            outside = base / "outside.json"
            actions.mkdir(parents=True)
            outside.write_text(json.dumps(self.manifest()), encoding="utf-8", newline="\n")
            try:
                (actions / f"{DOCUMENT_ID}.json").symlink_to(outside)
            except OSError as error:
                self.skipTest(f"file symlinks are unavailable: {error}")

            with self.assertRaisesRegex(ValueError, "symlink or reparse"):
                load_action_manifest(root, DOCUMENT_ID)

    def test_loader_fails_closed_for_missing_malformed_or_mismatched_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            actions = root / "academy" / "actions"
            actions.mkdir(parents=True)
            with self.assertRaisesRegex(ValueError, "could not read lesson action manifest"):
                load_action_manifest(root, DOCUMENT_ID)
            (actions / f"{DOCUMENT_ID}.json").write_text("{", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "could not read lesson action manifest"):
                load_action_manifest(root, DOCUMENT_ID)
            mismatched = self.manifest()
            mismatched["document_id"] = "F02-orient-to-state"
            (actions / f"{DOCUMENT_ID}.json").write_text(json.dumps(mismatched), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "document_id must match"):
                load_action_manifest(root, DOCUMENT_ID)

    def test_checked_in_schema_is_closed_and_models_both_action_shapes(self) -> None:
        schema = self.schema()

        self.assertFalse(schema["additionalProperties"])
        self.assertFalse(schema["$defs"]["action"]["additionalProperties"])
        self.assertFalse(schema["$defs"]["variant"]["additionalProperties"])
        self.assertEqual(len(schema["$defs"]["action"]["oneOf"]), 2)
        self.assertEqual(schema["properties"]["actions"]["maxItems"], 64)
        self.assertEqual(schema["$defs"]["variant"]["properties"]["command"]["maxLength"], 8192)


if __name__ == "__main__":
    unittest.main()
