"""Fail-closed public eligibility validation for the Arbiter Academy preview."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlsplit

from academy_engine.catalog import Catalog, CatalogError


_RELEASE = "preview-0.22"
_RUNNABLE_LABS = (
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
    "P08-repository-hygiene",
    "U01-autonomous-sprint",
    "U02-override-audit-metrics",
    "U03-refactor-chore-release",
    "U04-initialize-projects",
    "U05-debug-spike-conflict",
    "U06-preview-and-advanced-surfaces",
    "U07-capstone",
)
_COMING_NEXT: tuple[str, ...] = ()
_PREREQUISITES = (
    "A GitHub account that can create a personal fork.",
    "Git 2.39 or newer.",
    "Python 3.11 or newer.",
    "A supported CodeArbiter host: Claude Code, Codex, or Pi.",
    "Complete Academy Home setup steps 1-5 before starting F01.",
)
_KNOWN_LIMITS = (
    "F01-F04, P01-P08, and U01-U07 are the guided lessons published in Preview 0.22.",
    "Graduation is available after all 19 Academy Checks pass in the same repository.",
)
_DISCUSSIONS_ORIGIN = "github.com"
_DISCUSSIONS_PATH = "/arbiterForge/arbiter-academy/discussions"
_DISCUSSIONS_PATH_PATTERN = re.compile(
    rf"{re.escape(_DISCUSSIONS_PATH)}(?:/[A-Za-z0-9_~-][A-Za-z0-9._~-]*)*/?"
)
_ASCII_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SCHEMA_PINNED_FIELDS = ("id", "track", "order", "manifest", "checkpoint")


@dataclass(frozen=True)
class PreviewManifest:
    release: str
    lesson_contract_version: int
    available_labs: tuple[str, ...]
    runnable_labs: tuple[str, ...]
    guided_labs: tuple[str, ...]
    coming_next: tuple[str, ...]
    prerequisites: tuple[str, ...]
    known_limits: tuple[str, ...]
    discussion_url: str
    catalog_sha256: str


def _require_object(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError("preview manifest must be an object")
    return value


def _require_ids(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"preview manifest {label} must be a list of lab IDs")
    ids = tuple(value)
    if len(set(ids)) != len(ids):
        raise ValueError(f"preview manifest {label} contains duplicate lab IDs")
    return ids


def _require_public_copy(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"preview manifest {label} must be a list of public text entries")
    entries = tuple(value)
    if (
        not entries
        or len(set(entries)) != len(entries)
        or any(not entry.strip() or _ASCII_CONTROL.search(entry) for entry in entries)
    ):
        raise ValueError(f"preview manifest {label} must contain unique non-empty public text entries")
    return entries


def _require_exact_keys(data: Mapping[str, object]) -> None:
    expected = {
        "release",
        "lesson_contract_version",
        "available_labs",
        "runnable_labs",
        "guided_labs",
        "coming_next",
        "prerequisites",
        "known_limits",
        "discussion_url",
        "catalog_sha256",
    }
    unknown = set(data) - expected
    missing = expected - set(data)
    if unknown:
        raise ValueError(f"preview manifest has unknown key(s): {', '.join(sorted(unknown))}")
    if missing:
        raise ValueError(f"preview manifest is missing key(s): {', '.join(sorted(missing))}")


def _validate_discussion_url(value: object) -> str:
    if not isinstance(value, str) or _ASCII_CONTROL.search(value):
        raise ValueError("preview manifest discussion_url must be an HTTPS GitHub Discussions URL")
    parsed = urlsplit(value)
    path = unquote(parsed.path)
    if (
        parsed.scheme != "https"
        or parsed.netloc != _DISCUSSIONS_ORIGIN
        or parsed.query
        or parsed.fragment
        or parsed.path != path
        or "\\" in value
        or "\\" in path
        or not _DISCUSSIONS_PATH_PATTERN.fullmatch(path)
    ):
        raise ValueError(
            "preview manifest discussion_url must stay within "
            "https://github.com/arbiterForge/arbiter-academy/discussions"
        )
    return value


def _validate_catalog_hash(catalog_path: Path, value: object) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ValueError("preview manifest catalog_sha256 must be a lowercase SHA-256 hex digest")
    try:
        actual = hashlib.sha256(catalog_path.read_bytes()).hexdigest()
    except OSError as error:
        raise ValueError(f"could not read Academy catalog for catalog_sha256 validation: {error}") from error
    if value != actual:
        raise ValueError("preview manifest catalog_sha256 does not match academy/catalog.json")
    return value


def _validate_known_ordered_closure(catalog: Catalog, available_labs: tuple[str, ...]) -> None:
    catalog_ids = tuple(lab.id for lab in catalog.labs)
    unknown = [lab_id for lab_id in available_labs if lab_id not in catalog_ids]
    if unknown:
        raise ValueError(f"preview manifest available_labs contains unknown lab ID(s): {', '.join(unknown)}")
    indexes = [catalog_ids.index(lab_id) for lab_id in available_labs]
    if indexes != sorted(indexes):
        raise ValueError("preview manifest available_labs must preserve catalog order")
    available = set(available_labs)
    for lab_id in available_labs:
        missing = [prerequisite for prerequisite in catalog.lab(lab_id).prerequisites if prerequisite not in available]
        if missing:
            raise ValueError(
                f"preview manifest available_labs is missing prerequisite(s) for {lab_id}: {', '.join(missing)}"
            )


def _validate_guided_labs(
    catalog: Catalog, runnable_labs: tuple[str, ...], guided_labs: tuple[str, ...]
) -> None:
    catalog_ids = tuple(lab.id for lab in catalog.labs)
    if any(lab_id not in catalog_ids or lab_id not in runnable_labs for lab_id in guided_labs):
        raise ValueError("preview manifest guided_labs must be an ordered subset of runnable_labs")
    indexes = [catalog_ids.index(lab_id) for lab_id in guided_labs]
    if indexes != sorted(indexes):
        raise ValueError("preview manifest guided_labs must preserve catalog order")


def _same_json_value(left: object, right: object) -> bool:
    return type(left) is type(right) and left == right


def _validate_catalog_schema_lock(root: Path, catalog: Catalog) -> None:
    schema_path = root / "academy" / "catalog.schema.json"
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        labs_schema = schema["properties"]["labs"]
        prefix_items = labs_schema["prefixItems"]
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as error:
        raise ValueError(f"could not read catalog schema lock: {error}") from error
    if (
        not isinstance(labs_schema, Mapping)
        or not isinstance(prefix_items, list)
        or len(prefix_items) != len(catalog.labs)
        or labs_schema.get("minItems") != len(catalog.labs)
        or labs_schema.get("maxItems") != len(catalog.labs)
        or labs_schema.get("items") is not False
    ):
        raise ValueError("catalog schema pinned inventory does not match the catalog")
    for lab, pinned in zip(catalog.labs, prefix_items, strict=True):
        try:
            constants = pinned["properties"]
            matches = all(
                _same_json_value(constants[field]["const"], getattr(lab, field))
                for field in _SCHEMA_PINNED_FIELDS
            )
        except (KeyError, TypeError):
            matches = False
        if not matches:
            raise ValueError("catalog schema pinned inventory does not match the catalog")


def validate_preview_manifest(
    root: Path, data: Mapping[str, object] | None = None
) -> PreviewManifest:
    """Validate an in-memory current Preview manifest against the raw Academy catalog."""
    if data is None:
        return load_preview_manifest(root)

    manifest = _require_object(data)
    _require_exact_keys(manifest)
    release = manifest["release"]
    if release != _RELEASE:
        raise ValueError(f"preview manifest release must be {_RELEASE}")
    lesson_contract_version = manifest["lesson_contract_version"]
    if type(lesson_contract_version) is not int or lesson_contract_version != 1:
        raise ValueError("preview manifest lesson_contract_version must be integer 1")

    catalog_path = root / "academy" / "catalog.json"
    catalog_sha256 = _validate_catalog_hash(catalog_path, manifest["catalog_sha256"])
    try:
        catalog = Catalog.load(catalog_path)
    except CatalogError as error:
        raise ValueError(f"could not validate Academy catalog: {error}") from error
    _validate_catalog_schema_lock(root, catalog)

    available_labs = _require_ids(manifest["available_labs"], "available_labs")
    runnable_labs = _require_ids(manifest["runnable_labs"], "runnable_labs")
    guided_labs = _require_ids(manifest["guided_labs"], "guided_labs")
    coming_next = _require_ids(manifest["coming_next"], "coming_next")
    prerequisites = _require_public_copy(manifest["prerequisites"], "prerequisites")
    known_limits = _require_public_copy(manifest["known_limits"], "known_limits")
    discussion_url = _validate_discussion_url(manifest["discussion_url"])
    if available_labs != runnable_labs:
        raise ValueError("preview manifest available_labs must equal runnable_labs")
    if set(runnable_labs) & set(coming_next):
        raise ValueError("preview manifest runnable_labs must not overlap coming_next")
    _validate_known_ordered_closure(catalog, runnable_labs)
    if runnable_labs != _RUNNABLE_LABS:
        raise ValueError(f"preview manifest runnable_labs contains lab(s) not eligible for {_RELEASE}")
    _validate_guided_labs(catalog, runnable_labs, guided_labs)
    if guided_labs != _RUNNABLE_LABS:
        raise ValueError("preview manifest guided_labs must list only the reviewed public lessons")
    if coming_next != _COMING_NEXT:
        raise ValueError("preview manifest coming_next must name the reviewed guided-rewrite sequence")
    if prerequisites != _PREREQUISITES:
        raise ValueError(f"preview manifest prerequisites must match the reviewed {_RELEASE} onboarding contract")
    if known_limits != _KNOWN_LIMITS:
        raise ValueError(f"preview manifest known_limits must match the reviewed {_RELEASE} public limits")

    return PreviewManifest(
        release,
        lesson_contract_version,
        available_labs,
        runnable_labs,
        guided_labs,
        coming_next,
        prerequisites,
        known_limits,
        discussion_url,
        catalog_sha256,
    )


def load_preview_manifest(root: Path) -> PreviewManifest:
    """Load and validate the checked-in current Preview eligibility manifest."""
    path = root / "academy" / "publication" / f"{_RELEASE}.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"could not read preview manifest: {error}") from error
    return validate_preview_manifest(root, data)


def require_runnable_lab(root: Path, lab_id: str) -> None:
    """Fail closed unless *lab_id* is runnable in the reviewed public release."""
    manifest = load_preview_manifest(root)
    if lab_id not in manifest.runnable_labs:
        raise ValueError(
            f"{lab_id} is not runnable in Academy Preview "
            f"{manifest.release.removeprefix('preview-')}"
        )


def require_guided_lab(root: Path, lab_id: str) -> None:
    """Fail closed unless *lab_id* has a reviewed guided lesson in the public release."""
    manifest = load_preview_manifest(root)
    if lab_id not in manifest.guided_labs:
        raise ValueError(
            f"{lab_id} is not guided in Academy Preview "
            f"{manifest.release.removeprefix('preview-')}"
        )


def require_published_lab(root: Path, lab_id: str) -> None:
    """Fail closed unless a runnable lab also has reviewed public guidance."""
    require_guided_lab(root, lab_id)


def require_graduation_available(root: Path) -> None:
    """Fail closed until the verifier publishes the complete catalog."""
    manifest = load_preview_manifest(root)
    catalog = Catalog.load(root / "academy" / "catalog.json")
    complete_catalog = tuple(lab.id for lab in catalog.labs)
    if manifest.available_labs != complete_catalog:
        raise ValueError(
            "Graduation is not available until the complete Academy catalog is published."
        )
