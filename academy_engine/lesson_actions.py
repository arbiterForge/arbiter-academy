"""Typed, fail-closed lesson action manifests for the Academy website."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlsplit

from academy_engine.paths import ensure_within


ACTORS = frozenset({"learner", "academy", "agent"})
SURFACES = frozenset({"browser", "native-terminal", "harness", "academy-console"})
OPERATING_SYSTEMS = frozenset({"all", "windows", "macos", "linux"})
HOSTS = frozenset({"none", "claude-code", "codex", "pi"})
LANGUAGES = frozenset({"none", "powershell", "sh", "text", "codearbiter"})

_SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]{0,95}")
_ASCII_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_COMMAND_CONTROL = re.compile(r"[\x00-\x09\x0b-\x1f\x7f]")
_MANIFEST_KEYS = frozenset(
    {"schema_version", "lesson_contract_version", "document_id", "actions"}
)
_ACTION_KEYS = frozenset(
    {
        "id",
        "sequence",
        "title",
        "actor",
        "surface",
        "instruction",
        "rationale",
        "resources",
        "variants",
        "expected_result",
        "recovery",
        "evidence",
    }
)
_RESOURCE_KEYS = frozenset({"label", "href"})
_VARIANT_KEYS = frozenset(
    {"id", "surface", "operating_system", "host", "language", "command", "copy"}
)
_PROSE_LIMIT = 1024
_COMMAND_LIMIT = 8192
_ACTION_LIMIT = 64
_VARIANT_LIMIT = 12
_RESOURCE_LIMIT = 4
_RESOURCE_LABEL_LIMIT = 160
_RESOURCE_HREF_LIMIT = 2048


@dataclass(frozen=True, slots=True)
class CommandVariant:
    id: str
    surface: str
    operating_system: str
    host: str
    language: str
    command: str
    copy: bool


@dataclass(frozen=True, slots=True)
class ActionResource:
    label: str
    href: str


@dataclass(frozen=True, slots=True)
class LessonAction:
    id: str
    sequence: int
    title: str
    actor: str
    surface: str | None
    instruction: str
    rationale: str | None
    resources: tuple[ActionResource, ...]
    variants: tuple[CommandVariant, ...]
    expected_result: str
    recovery: str
    evidence: str | None


@dataclass(frozen=True, slots=True)
class LessonActionManifest:
    schema_version: int
    lesson_contract_version: int
    document_id: str
    actions: tuple[LessonAction, ...]


def _require_exact_keys(
    value: object, expected: frozenset[str], label: str
) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object with exact keys")
    keys = set(value)
    if keys != expected:
        missing = sorted(expected - keys)
        unknown = sorted(keys - expected)
        detail = []
        if missing:
            detail.append(f"missing {', '.join(missing)}")
        if unknown:
            detail.append(f"unknown {', '.join(unknown)}")
        raise ValueError(f"{label} must use exact keys ({'; '.join(detail)})")
    return value


def _require_safe_id(value: object, label: str) -> str:
    if not isinstance(value, str) or _SAFE_ID.fullmatch(value) is None:
        raise ValueError(f"{label} must be a bounded safe ID")
    return value


def _require_pinned_integer(value: object, label: str) -> int:
    if type(value) is not int:
        raise ValueError(f"{label} must be an integer")
    if value != 1:
        raise ValueError(f"{label} must be integer 1")
    return value


def _require_sequence(value: object) -> int:
    if type(value) is not int:
        raise ValueError("lesson action sequence must be an integer")
    if value < 1:
        raise ValueError("lesson action sequence must begin at 1")
    return value


def _require_enum(value: object, allowed: frozenset[str], label: str) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise ValueError(f"{label} must be one of the allowed values")
    return value


def _require_prose(value: object, label: str, *, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must not be empty")
    if len(value) > _PROSE_LIMIT:
        raise ValueError(f"{label} must be at most {_PROSE_LIMIT} characters")
    if _ASCII_CONTROL.search(value):
        raise ValueError(f"{label} must not contain ASCII controls")
    return value


def _require_command(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("command must not be empty")
    if len(value) > _COMMAND_LIMIT:
        raise ValueError(f"command must be at most {_COMMAND_LIMIT} characters")
    if "\r" in value:
        raise ValueError("command must not contain CR bytes")
    if _COMMAND_CONTROL.search(value):
        raise ValueError("command must not contain ASCII controls other than LF")
    return value


def _safe_resource_path(path: str) -> bool:
    decoded = path
    for _ in range(16):
        candidate = unquote(decoded)
        if candidate == decoded:
            break
        decoded = candidate
    else:
        return False
    if "\\" in decoded or _ASCII_CONTROL.search(decoded):
        return False
    return all(segment not in {".", ".."} for segment in decoded.split("/"))


def _validate_resource(value: object) -> ActionResource:
    resource = _require_exact_keys(value, _RESOURCE_KEYS, "action resource")
    label = _require_prose(resource["label"], "action resource label")
    assert label is not None
    if len(label) > _RESOURCE_LABEL_LIMIT:
        raise ValueError(
            f"action resource label must be at most {_RESOURCE_LABEL_LIMIT} characters"
        )
    href = resource["href"]
    if not isinstance(href, str) or not href.strip():
        raise ValueError("action resource href must not be empty")
    if len(href) > _RESOURCE_HREF_LIMIT:
        raise ValueError(
            f"action resource href must be at most {_RESOURCE_HREF_LIMIT} characters"
        )
    if _ASCII_CONTROL.search(href):
        raise ValueError("action resource href must not contain ASCII controls")
    parsed = urlsplit(href)
    if parsed.query or parsed.fragment or parsed.username or parsed.password or parsed.port is not None:
        raise ValueError("action resource href contains an unsafe URL component")
    if parsed.scheme or parsed.netloc:
        if (
            parsed.scheme != "https"
            or parsed.hostname != "github.com"
            or parsed.netloc != "github.com"
            or not (
                parsed.path == "/arbiterForge/arbiter-academy"
                or parsed.path.startswith("/arbiterForge/arbiter-academy/")
            )
        ):
            raise ValueError("action resource href must stay within the Academy GitHub repository")
    elif not href.startswith("/") or href.startswith("//"):
        raise ValueError("action resource href must be HTTPS or a safe root-relative site path")
    if not _safe_resource_path(parsed.path):
        raise ValueError("action resource href must not contain path traversal")
    return ActionResource(label, href)


def _validate_execution_identity(
    *, surface: str, host: str, language: str, command: str
) -> None:
    if surface == "native-terminal":
        if host != "none":
            raise ValueError("native-terminal variants require host none")
        if command.startswith("!"):
            raise ValueError("native-terminal commands must not begin with !")
    elif surface == "harness":
        if host == "none":
            raise ValueError("harness variants require a named host")
    elif host != "none":
        raise ValueError(f"{surface} variants require host none")

    if language in {"powershell", "sh"}:
        if surface == "harness" and (not command.startswith("!") or command.startswith("!!")):
            raise ValueError("harness shell commands must begin with exactly one !")
        if surface not in {"harness", "native-terminal"}:
            raise ValueError("shell commands require a native-terminal or harness surface")
        return

    if language != "codearbiter":
        return
    if command.startswith("!"):
        raise ValueError("CodeArbiter commands must not begin with !")
    if surface != "harness" or host == "none":
        raise ValueError("CodeArbiter commands require a harness and named host")
    patterns = {
        "claude-code": re.compile(r"/ca:[A-Za-z0-9-]+(?: [^\r\n]+)?"),
        "codex": re.compile(r"\$ca-[A-Za-z0-9-]+(?: [^\r\n]+)?"),
        "pi": re.compile(r"/(?:ca-|skill:ca-)[A-Za-z0-9-]+(?: [^\r\n]+)?"),
    }
    if patterns[host].fullmatch(command) is None:
        host_label = {"claude-code": "Claude Code", "codex": "Codex", "pi": "Pi"}[host]
        raise ValueError(f"CodeArbiter command does not use {host_label} host-native syntax")


def _validate_variant(value: object) -> CommandVariant:
    variant = _require_exact_keys(value, _VARIANT_KEYS, "command variant")
    variant_id = _require_safe_id(variant["id"], "command variant id")
    surface = _require_enum(variant["surface"], SURFACES, "command variant surface")
    operating_system = _require_enum(
        variant["operating_system"], OPERATING_SYSTEMS, "command variant operating_system"
    )
    host = _require_enum(variant["host"], HOSTS, "command variant host")
    language = _require_enum(variant["language"], LANGUAGES, "command variant language")
    command = _require_command(variant["command"])
    copy = variant["copy"]
    if type(copy) is not bool:
        raise ValueError("command variant copy must be a boolean")
    _validate_execution_identity(
        surface=surface, host=host, language=language, command=command
    )
    return CommandVariant(
        variant_id, surface, operating_system, host, language, command, copy
    )


def _validate_action(value: object) -> LessonAction:
    action = _require_exact_keys(value, _ACTION_KEYS, "lesson action")
    action_id = _require_safe_id(action["id"], "lesson action id")
    sequence = _require_sequence(action["sequence"])
    title = _require_prose(action["title"], "lesson action title")
    actor = _require_enum(action["actor"], ACTORS, "lesson action actor")
    instruction = _require_prose(action["instruction"], "lesson action instruction")
    rationale = _require_prose(
        action["rationale"], "lesson action rationale", nullable=True
    )
    raw_resources = action["resources"]
    if not isinstance(raw_resources, list):
        raise ValueError("lesson action resources must be a list")
    if len(raw_resources) > _RESOURCE_LIMIT:
        raise ValueError(f"lesson actions may define at most {_RESOURCE_LIMIT} resources")
    resources = tuple(_validate_resource(item) for item in raw_resources)
    resource_hrefs = tuple(item.href for item in resources)
    if len(set(resource_hrefs)) != len(resource_hrefs):
        raise ValueError("lesson actions require unique resource hrefs")
    expected_result = _require_prose(
        action["expected_result"], "lesson action expected_result"
    )
    recovery = _require_prose(action["recovery"], "lesson action recovery")
    evidence = _require_prose(action["evidence"], "lesson action evidence", nullable=True)

    raw_variants = action["variants"]
    if not isinstance(raw_variants, list):
        raise ValueError("lesson action variants must be a list")
    if len(raw_variants) > _VARIANT_LIMIT:
        raise ValueError(f"lesson actions may define at most {_VARIANT_LIMIT} command variants")
    variants = tuple(_validate_variant(item) for item in raw_variants)
    variant_ids = tuple(item.id for item in variants)
    if len(set(variant_ids)) != len(variant_ids):
        raise ValueError("lesson actions require unique variant IDs")

    surface_value = action["surface"]
    if variants:
        if surface_value is not None:
            raise ValueError("command actions require surface null and variant-owned surfaces")
        surface = None
    else:
        if surface_value is None:
            raise ValueError("non-command actions require one action-level surface")
        surface = _require_enum(surface_value, SURFACES, "lesson action surface")
        if surface == "harness":
            raise ValueError(
                "non-command actions cannot use harness; use a command variant with a named host"
            )

    return LessonAction(
        action_id,
        sequence,
        title,
        actor,
        surface,
        instruction,
        rationale,
        resources,
        variants,
        expected_result,
        recovery,
        evidence,
    )


def validate_action_manifest(
    data: Mapping[str, object], *, expected_document_id: str
) -> LessonActionManifest:
    """Validate one in-memory action manifest into immutable runtime models."""
    expected_id = _require_safe_id(expected_document_id, "expected document id")
    manifest = _require_exact_keys(data, _MANIFEST_KEYS, "lesson action manifest")
    schema_version = _require_pinned_integer(manifest["schema_version"], "schema_version")
    lesson_contract_version = _require_pinned_integer(
        manifest["lesson_contract_version"], "lesson_contract_version"
    )
    document_id = _require_safe_id(manifest["document_id"], "document_id")
    if document_id != expected_id:
        raise ValueError("lesson action manifest document_id must match the requested document")
    raw_actions = manifest["actions"]
    if not isinstance(raw_actions, list):
        raise ValueError("lesson action manifest actions must be a list")
    if not raw_actions:
        raise ValueError("lesson action manifest must define at least one action")
    if len(raw_actions) > _ACTION_LIMIT:
        raise ValueError(f"lesson action manifest may define at most {_ACTION_LIMIT} actions")
    actions = tuple(_validate_action(item) for item in raw_actions)
    action_ids = tuple(action.id for action in actions)
    if len(set(action_ids)) != len(action_ids):
        raise ValueError("lesson action manifest requires unique action IDs")
    if tuple(action.sequence for action in actions) != tuple(range(1, len(actions) + 1)):
        raise ValueError("lesson action sequences must be contiguous and begin at 1")
    return LessonActionManifest(
        schema_version, lesson_contract_version, document_id, actions
    )


def load_action_manifest(root: Path, document_id: str) -> LessonActionManifest:
    """Load exactly ``academy/actions/{document_id}.json`` beneath *root*."""
    safe_document_id = _require_safe_id(document_id, "document id")
    path = ensure_within(
        root, root / "academy" / "actions" / f"{safe_document_id}.json"
    )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"could not read lesson action manifest: {error}") from error
    if not isinstance(data, Mapping):
        raise ValueError("lesson action manifest must be an object with exact keys")
    return validate_action_manifest(data, expected_document_id=safe_document_id)
