from __future__ import annotations

import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from academy_engine.lesson_actions import (
    CommandVariant,
    LessonAction,
    LessonActionManifest,
    load_action_manifest,
    validate_action_manifest,
)


DOCUMENT_ID = "F01-fork-clone-doctor"


class LessonActionTests(unittest.TestCase):
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
        root = Path(__file__).parents[1]
        schema = json.loads((root / "academy" / "lesson-action.schema.json").read_text(encoding="utf-8"))

        self.assertFalse(schema["additionalProperties"])
        self.assertFalse(schema["$defs"]["action"]["additionalProperties"])
        self.assertFalse(schema["$defs"]["variant"]["additionalProperties"])
        self.assertEqual(len(schema["$defs"]["action"]["oneOf"]), 2)
        self.assertEqual(schema["properties"]["actions"]["maxItems"], 64)
        self.assertEqual(schema["$defs"]["variant"]["properties"]["command"]["maxLength"], 8192)


if __name__ == "__main__":
    unittest.main()
