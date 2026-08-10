"""Fail-closed catalog and scenario-manifest validation for Academy labs."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


_LAB_ID = re.compile(r"^[FPU][0-9]{2}-[a-z0-9]+(?:-[a-z0-9]+)*$")
_TRACKS = ("foundations", "practitioner", "power-user")
_EXACT_LABS = (
    ("F01-fork-clone-doctor", "foundations", 1), ("F02-orient-to-state", "foundations", 2),
    ("F03-work-the-board", "foundations", 3), ("F04-fix-with-evidence", "foundations", 4),
    ("P01-feature-through-plan", "practitioner", 1), ("P02-commit-review-pr", "practitioner", 2),
    ("P03-record-an-adr", "practitioner", 3), ("P04-review-a-dependency", "practitioner", 4),
    ("P05-checkpoint-remediation", "practitioner", 5), ("P06-context-drift-recovery", "practitioner", 6),
    ("P07-threat-model", "practitioner", 7), ("P08-repository-hygiene", "practitioner", 8),
    ("U01-autonomous-sprint", "power-user", 1), ("U02-override-audit-metrics", "power-user", 2),
    ("U03-refactor-chore-release", "power-user", 3), ("U04-initialize-projects", "power-user", 4),
    ("U05-debug-spike-conflict", "power-user", 5), ("U06-preview-and-advanced-surfaces", "power-user", 6),
    ("U07-capstone", "power-user", 7),
)
_PROTECTED_SCENARIO_PARTS = frozenset({".git", ".academy", ".codearbiter", "academy"})
_CONTROL_STATE_SEED_TARGETS = {
    "P01-feature-through-plan": frozenset({".codearbiter/open-tasks.md"}),
}
_PROTECTED_OVERLAY_BINDINGS = {
    "P06-context-drift-recovery": frozenset(
        {
            ("CONTEXT.md", ".codearbiter/CONTEXT.md"),
            (
                "CONTEXT.provenance.json",
                ".codearbiter/.provenance/CONTEXT.json",
            ),
        }
    ),
}


class CatalogError(ValueError):
    """A catalog or scenario manifest is malformed or unsafe."""


@dataclass(frozen=True)
class Lab:
    id: str
    track: str
    order: int
    manifest: str
    checkpoint: str
    prerequisites: tuple[str, ...]
    requires_push_safe_setup: bool


@dataclass(frozen=True)
class OverlayFile:
    source: str
    destination: str


@dataclass(frozen=True)
class ControlStateSeed:
    source: str
    destination: str


@dataclass(frozen=True)
class ScenarioManifest:
    id: str
    files: tuple[OverlayFile, ...]
    control_state_seed: ControlStateSeed | None
    removals: tuple[str, ...]
    starting_task: str
    checkpoint: str
    requires_push_safe_setup: bool


def _require_object(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CatalogError(f"{label} must be an object.")
    return value


def _only_keys(value: dict[str, Any], allowed: set[str], label: str) -> None:
    unknown = set(value) - allowed
    missing = allowed - set(value)
    if unknown:
        raise CatalogError(f"{label} has unknown key(s): {', '.join(sorted(unknown))}.")
    if missing:
        raise CatalogError(f"{label} is missing key(s): {', '.join(sorted(missing))}.")


def _string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise CatalogError(f"{label} must be a non-empty string.")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise CatalogError(f"{label} must not contain control characters.")
    return value


def _path(value: object, label: str) -> str:
    text = _string(value, label)
    if "\\" in text or text.startswith("/") or ":" in text:
        raise CatalogError(f"{label} path must be a relative forward-slash path.")
    parts = text.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise CatalogError(f"{label} path is outside the Academy repository.")
    return text


def _scenario_path(value: object, label: str) -> str:
    path = _path(value, label)
    if any(part in _PROTECTED_SCENARIO_PARTS for part in path.split("/")):
        raise CatalogError(f"{label} path targets a protected Academy/control surface.")
    return path


def _scenario_destination(lab_id: str, source: str, value: object, label: str) -> str:
    path = _path(value, label)
    if (
        any(part in _PROTECTED_SCENARIO_PARTS for part in path.split("/"))
        and (source, path)
        not in _PROTECTED_OVERLAY_BINDINGS.get(lab_id, frozenset())
    ):
        raise CatalogError(f"{label} path targets a protected Academy/control surface.")
    return path


def _control_state_destination(lab_id: str, value: object) -> str:
    path = _path(value, "scenario manifest control_state_seed.destination")
    if path not in _CONTROL_STATE_SEED_TARGETS.get(lab_id, frozenset()):
        raise CatalogError(
            "scenario manifest binding is noncanonical: control_state_seed destination is not allowlisted."
        )
    return path


def _lab_id(value: object, label: str) -> str:
    text = _string(value, label)
    if not _LAB_ID.fullmatch(text):
        raise CatalogError(f"{label} is not a valid Academy lab ID.")
    return text


def _bool(value: object, label: str) -> bool:
    if type(value) is not bool:
        raise CatalogError(f"{label} must be a boolean.")
    return value


def _overlap(paths: tuple[str, ...], label: str) -> None:
    for index, left in enumerate(paths):
        for right in paths[index + 1 :]:
            if left == right or left.startswith(right + "/") or right.startswith(left + "/"):
                raise CatalogError(f"{label} paths overlap: {left} and {right}.")


def load_manifest(payload: object) -> ScenarioManifest:
    """Validate one in-memory manifest without touching the filesystem."""
    data = _require_object(payload, "scenario manifest")
    keys = {
        "schema_version",
        "id",
        "files",
        "removals",
        "starting_task",
        "checkpoint",
        "requires_push_safe_setup",
    }
    if "control_state_seed" in data:
        keys.add("control_state_seed")
    _only_keys(data, keys, "scenario manifest")
    if type(data["schema_version"]) is not int or data["schema_version"] != 1:
        raise CatalogError("scenario manifest schema_version must be 1.")
    lab_id = _lab_id(data["id"], "scenario manifest id")
    files_data = data["files"]
    if not isinstance(files_data, list):
        raise CatalogError("scenario manifest files must be a list.")
    files: list[OverlayFile] = []
    sources: list[str] = []
    destinations: list[str] = []
    for index, item in enumerate(files_data):
        entry = _require_object(item, f"scenario manifest files[{index}]")
        _only_keys(entry, {"source", "destination"}, f"scenario manifest files[{index}]")
        source = _scenario_path(entry["source"], f"scenario manifest files[{index}].source")
        destination = _scenario_destination(
            lab_id,
            source,
            entry["destination"],
            f"scenario manifest files[{index}].destination",
        )
        sources.append(source)
        destinations.append(destination)
        files.append(OverlayFile(source, destination))
    seed_value = data.get("control_state_seed")
    control_state_seed: ControlStateSeed | None = None
    if seed_value is not None:
        seed = _require_object(seed_value, "scenario manifest control_state_seed")
        _only_keys(seed, {"source", "destination"}, "scenario manifest control_state_seed")
        source = _scenario_path(seed["source"], "scenario manifest control_state_seed.source")
        destination = _control_state_destination(lab_id, seed["destination"])
        sources.append(source)
        destinations.append(destination)
        control_state_seed = ControlStateSeed(source, destination)
    if len(set(sources)) != len(sources):
        raise CatalogError("scenario manifest source paths must be unique.")
    _overlap(tuple(destinations), "scenario manifest destination")
    removals_data = data["removals"]
    if not isinstance(removals_data, list):
        raise CatalogError("scenario manifest removals must be a list.")
    removals = tuple(_scenario_path(item, f"scenario manifest removals[{index}]") for index, item in enumerate(removals_data))
    if len(set(removals)) != len(removals):
        raise CatalogError("scenario manifest removal paths must be unique.")
    _overlap(removals, "scenario manifest removal")
    _overlap(tuple(destinations) + removals, "scenario manifest write/removal")
    return ScenarioManifest(
        id=lab_id,
        files=tuple(files),
        control_state_seed=control_state_seed,
        removals=removals,
        starting_task=_string(data["starting_task"], "scenario manifest starting_task"),
        checkpoint=_path(data["checkpoint"], "scenario manifest checkpoint"),
        requires_push_safe_setup=_bool(data["requires_push_safe_setup"], "scenario manifest requires_push_safe_setup"),
    )


def load_manifest_file(path: Path) -> ScenarioManifest:
    try:
        raw = path.read_text(encoding="utf-8")
        return load_manifest(json.loads(raw))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CatalogError(f"could not read scenario manifest: {error}") from error


@dataclass(frozen=True)
class Catalog:
    labs: tuple[Lab, ...]

    @classmethod
    def load(cls, path: Path) -> "Catalog":
        try:
            raw = path.read_text(encoding="utf-8")
            data = _require_object(json.loads(raw), "catalog")
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise CatalogError(f"could not read catalog: {error}") from error
        _only_keys(data, {"schema_version", "labs"}, "catalog")
        if type(data["schema_version"]) is not int or data["schema_version"] != 1:
            raise CatalogError("catalog schema_version must be 1.")
        raw_labs = data["labs"]
        if not isinstance(raw_labs, list) or not raw_labs:
            raise CatalogError("catalog labs must be a non-empty list.")
        labs: list[Lab] = []
        ids: set[str] = set()
        per_track: dict[str, set[int]] = {track: set() for track in _TRACKS}
        for index, item in enumerate(raw_labs):
            entry = _require_object(item, f"catalog labs[{index}]")
            _only_keys(entry, {"id", "track", "order", "manifest", "checkpoint", "prerequisites", "requires_push_safe_setup"}, f"catalog labs[{index}]")
            lab_id = _lab_id(entry["id"], f"catalog labs[{index}].id")
            if lab_id in ids:
                raise CatalogError(f"catalog has duplicate lab ID: {lab_id}.")
            ids.add(lab_id)
            track = _string(entry["track"], f"catalog labs[{index}].track")
            if track not in _TRACKS:
                raise CatalogError(f"catalog labs[{index}].track is invalid.")
            order = entry["order"]
            if type(order) is not int or order < 1:
                raise CatalogError(f"catalog labs[{index}].order must be a positive integer.")
            if order in per_track[track]:
                raise CatalogError(f"catalog has duplicate {track} order {order}.")
            per_track[track].add(order)
            prerequisites_value = entry["prerequisites"]
            if not isinstance(prerequisites_value, list):
                raise CatalogError(f"catalog labs[{index}].prerequisites must be a list.")
            prerequisites = tuple(_lab_id(value, f"catalog labs[{index}].prerequisites") for value in prerequisites_value)
            if len(set(prerequisites)) != len(prerequisites) or lab_id in prerequisites:
                raise CatalogError(f"catalog labs[{index}] has invalid prerequisites.")
            labs.append(Lab(lab_id, track, order, _path(entry["manifest"], "catalog manifest"), _path(entry["checkpoint"], "catalog checkpoint"), prerequisites, _bool(entry["requires_push_safe_setup"], "catalog requires_push_safe_setup")))
        if any(lab.prerequisites and not set(lab.prerequisites).issubset(ids) for lab in labs):
            raise CatalogError("catalog prerequisite is not a catalog lab ID.")
        expected = sorted(labs, key=lambda lab: (_TRACKS.index(lab.track), lab.order))
        if labs != expected:
            raise CatalogError("catalog labs must be ordered by track and order.")
        if tuple((lab.id, lab.track, lab.order) for lab in labs) != _EXACT_LABS:
            raise CatalogError("catalog must contain the exact ordered Academy lab inventory.")
        for lab in labs:
            if lab.manifest != f"academy/scenarios/{lab.id}/manifest.json" or lab.checkpoint != f"academy/checkpoints/{lab.id}.json":
                raise CatalogError("catalog manifest/checkpoint mapping is not canonical for its lab ID.")
        return cls(tuple(labs))

    def lab(self, lab_id: str) -> Lab:
        for lab in self.labs:
            if lab.id == lab_id:
                return lab
        raise CatalogError("lab ID is not present in the Academy catalog.")
