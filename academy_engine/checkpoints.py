"""Fail-closed, repository-derived Academy checkpoint evaluation."""
from __future__ import annotations

import ast
import copy
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tokenize
import tomllib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from academy_engine.catalog import Catalog, load_manifest
from academy_engine.candidate_data import CandidateDataError, P04_CANDIDATE_ROOT, validate_p04_candidate_blobs
from academy_engine.attribution import AttributionError, commit_author_name, validate_display_name
from academy_engine.command import repository_root, run_git, validate_repository_git_config
from academy_engine.exercise_state import (
    P02AttemptIdentity,
    P08AttemptIdentity,
    _parse_p02_receipt_bytes,
    open_existing_p02_store,
    open_p08_store,
    preflight_p08,
    validate_p02_checkpoint,
    validate_p02_prepared_commit,
    validate_p08_checkpoint,
)
from academy_engine.remotes import RemoteSafetyError, validate_training_remotes
from academy_engine.p05_fixture import validate_p05_fixture
from academy_engine.paths import ensure_within
from academy_engine.secret_rules import blob_is_secret_free
from academy_engine.u04_fixture import U04_SEED_CONTENT
from academy_engine.u07_fixture import (
    u07_remediation_source_is_exact,
    u07_remediation_test_is_exact,
    validate_u07_fixture,
)

LAB_INVENTORY = (
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
LAB_CONTRACT = dict.fromkeys(LAB_INVENTORY)
_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_ATTEMPT = re.compile(r"^academy/(?P<lab>[FPU][0-9]{2}-[a-z0-9]+(?:-[a-z0-9]+)*)/(?P<number>[1-9][0-9]*)$")
_P06_CONTEXT = b"""---
arbiter: enabled
stage: 2
---
<!--INITIALIZED-->

# Project: Workshop Queue

Workshop Queue is a local-first Python application used in Arbiter Academy labs.
It records, assigns, and moves teaching tickets through a small explicit lifecycle.
This directory is a pre-staged Academy fixture: learners inspect, reset, mutate,
review, and audit it during later labs.

## Fixture identity

- Product steward: Academy Facilitator (fictional Academy role).
- Historical records: all dates, events, findings, and names in this state are
  fictional Academy fixtures, not evidence about a live service or person.
- Runtime: Python 3 with the standard library only; the root license is AGPL-3.0-only.

## Scope and boundaries

- Durable ticket data is local JSON under an operator-selected application-data root.
- Assignment behavior is defined by the [ticket-assignment specification](specs/ticket-assignment.md)
  and [implementation plan](plans/ticket-assignment.md).
- The JSON boundary is recorded by [ADR-0001](decisions/0001-json-storage-boundary.md);
  lifecycle rules are recorded by [ADR-0002](decisions/0002-explicit-ticket-state-machine.md).
- Workshop Queue report output is JSON-only.

## Not this project

Workshop Queue is not a hosted ticketing service, identity system, payment system,
or team chat. Academy exercises use only fabricated ticket content and need no
network connection or credential.

## Governing artifacts

- [Coding standards](coding-standards.md)
- [Technology and verification commands](tech-stack.md)
- [Security controls](security-controls.md)
- [Open task board](open-tasks.md)
- [Academy training questions](open-questions.md)
"""
_P06_CONTEXT_AFTER = _P06_CONTEXT.replace(
    b"[ADR-0002](decisions/0002-explicit-ticket-state-machine.md)",
    b"[ADR-0005](decisions/0005-terminal-blocked-ticket-lifecycle.md)",
).replace(
    b"- Workshop Queue report output is JSON-only.",
    b"- Workshop Queue report output defaults to stable text and supports structured JSON with --format json.",
)
_P06_PROVENANCE = b'''{
  "created": "2026-07-30",
  "doc": "CONTEXT",
  "entries": [
    {
      "claims": [
        {
          "claim": "Workshop Queue report output is JSON-only.",
          "confidence": "strong",
          "lines": "60-67"
        }
      ],
      "drift_trigger": true,
      "hash": "042746e43698e5d2a6de4c536f1024f893aef805",
      "path": "workshop_queue/cli.py"
    }
  ],
  "interview_derived": false,
  "schema": 1
}
'''
_P06_SOURCE_OBJECT = "5b41fb168a8b258cfae7eebc46e8b9ea7696ba56"
_P06_PROVENANCE_AFTER = _P06_PROVENANCE.replace(
    b"042746e43698e5d2a6de4c536f1024f893aef805",
    _P06_SOURCE_OBJECT.encode("ascii"),
)
_P06_NOTE = (
    b"# Unrelated learner note\n\n"
    b"Keep this note unchanged while recovering the interrupted summary-format context.\n"
)
_U06_SEED_CANDIDATE = b"# U06 preview candidate\n\nThis draft is intentionally incomplete.\n"
_U06_SAFE_CANDIDATE = (
    b"# U06 preview candidate\n\n"
    b"## Read-only documentation policy\n\n"
    b"Preview may inspect the prepared attempt and report predicted reviewers. "
    b"It does not run a sandbox, create a skill, start watch, or convene a tribunal.\n\n"
    b"## Evidence\n\n"
    b"Record the reviewed commit, candidate tree, exact changed path, and "
    b"repository bindings in the U06 Academy record.\n"
)
_U06_ADVANCED_SURFACES = {
    "ca-sandbox": "not-executed",
    "ca-new-skill": "not-executed",
    "ca-watch": "not-executed",
    "ca-tribunal": "not-executed",
}
_PROFILES = {
    "remote_doctor": ("artifact",),
    "orientation": ("artifact", "context"),
    "task_transition": ("board", "task_id"),
    "tdd_history": ("code", "test"),
    "feature_spec_plan": (
        "spec",
        "plan",
        "board",
        "test",
        "code",
        "fixture",
        "source_identity",
        "task_id",
    ),
    "pr_receipt": ("receipt",),
    "accepted_adr": ("adr", "decision_log"),
    "dependency_review": ("review", "project"),
    "checkpoint_remediation": ("report",),
    "provenance_recovery": (
        "context", "handoff", "source", "preserved_path", "provenance",
    ),
    "stride_model": ("model", "target", "target_blob", "target_sha256"),
    "hygiene_snapshot": ("snapshot",),
    "p08_authenticated": (),
    "sprint_decisions": ("spec", "plan", "sprint_log", "brief", "deliverable"),
    "override_audit_metrics": ("overrides", "audit_packets"),
    "refactor_chore_release": (
        "scenario", "code", "test", "chore", "release_target", "release_version",
        "release_tag", "release_changelog", "release_targets",
    ),
    "initialized_fixture": ("workspace", "report"),
    "initialized_projects": ("greenfield", "brownfield", "report"),
    "debug_spike_conflict": ("spike", "board", "observation"),
    "preview_evidence": ("report",),
    "u06_preview_evidence": ("candidate", "report"),
    "feature_capstone": ("code", "test"),
}
_REMOTE_PROFILES = frozenset({"remote_doctor", "refactor_chore_release", "feature_capstone"})
_CANONICAL_PREDICATES: dict[str, tuple[str, str, dict[str, object]]] = {
    "F01-fork-clone-doctor": ("remote_and_doctor", "remote_doctor", {"artifact": ".codearbiter/reports/academy/F01-doctor.json"}),
    "F02-orient-to-state": ("live_context_orientation", "orientation", {"artifact": ".codearbiter/reports/academy/F02-orientation.json", "context": ".codearbiter/CONTEXT.md"}),
    "F03-work-the-board": ("canonical_board_transition", "task_transition", {"board": ".codearbiter/open-tasks.md", "task_id": "academy.feature.0001"}),
    "F04-fix-with-evidence": ("red_then_fix_history", "tdd_history", {"code": "workshop_queue/service.py", "test": "tests/test_service.py"}),
    "P01-feature-through-plan": ("feature_spec_plan_commit", "feature_spec_plan", {"spec": ".codearbiter/specs/academy-feature.md", "plan": ".codearbiter/plans/academy-feature.md", "board": ".codearbiter/open-tasks.md", "test": "tests/test_cli.py", "code": "workshop_queue/cli.py", "fixture": "data/p01-unresolved-tickets.json", "source_identity": "training_scenarios/P01-codearbiter-source.json", "task_id": "academy.feature.0002"}),
    "P02-commit-review-pr": ("review_pr_commit_range", "pr_receipt", {"receipt": ".codearbiter/reports/academy/P02-pr-receipt.json"}),
    "P03-record-an-adr": ("accepted_adr_and_log", "accepted_adr", {"adr": ".codearbiter/decisions/0004-academy-lab.md", "decision_log": ".codearbiter/decisions/decision-log.md"}),
    "P04-review-a-dependency": ("strict_dependency_review", "dependency_review", {"review": ".codearbiter/reports/academy/P04-dependency-review.md", "project": "pyproject.toml"}),
    "P05-checkpoint-remediation": ("finding_remediation_link", "checkpoint_remediation", {"report": ".codearbiter/checkpoints/P05-academy.json"}),
    "P06-context-drift-recovery": ("provenance_drift_recovery", "provenance_recovery", {"context": ".codearbiter/CONTEXT.md", "handoff": ".codearbiter/reports/academy/P06-recovery.json", "source": "workshop_queue/cli.py", "preserved_path": "docs/preserved-note.md", "provenance": ".codearbiter/.provenance/CONTEXT.json"}),
    "P07-threat-model": ("stride_model", "stride_model", {"model": ".codearbiter/reports/academy/P07-threat-model.md", "target": "academy_engine/paths.py", "target_blob": "b36801add4eb375f796d1107ee63dd604d08a034", "target_sha256": "e40a7655ce6ba6cde58a91ae10a714f10046c055ac90dcbc58f0696c39133a5d"}),
    "P08-repository-hygiene": ("live_ref_hygiene", "p08_authenticated", {}),
    "U01-autonomous-sprint": ("approved_sprint_decisions", "sprint_decisions", {"spec": ".codearbiter/specs/academy-sprint.md", "plan": ".codearbiter/plans/academy-sprint.md", "sprint_log": ".codearbiter/sprint-log.md", "brief": "training_scenarios/U01-sprint-brief.json", "deliverable": "docs/academy-sprint-summary.md"}),
    "U02-override-audit-metrics": ("linked_override_audit_metrics", "override_audit_metrics", {"overrides": ".codearbiter/overrides.log", "audit_packets": ".codearbiter/audits"}),
    "U03-refactor-chore-release": ("refactor_chore_release", "refactor_chore_release", {"scenario": "training_scenarios/U03-refactor-chore-release.json", "code": "workshop_queue/store.py", "test": "tests/test_store.py", "chore": "README.md", "release_target": "academy-private-training", "release_version": "0.0.1", "release_tag": "academy-v0.0.1", "release_changelog": "CHANGELOG.md", "release_targets": ".codearbiter/release-targets.md"}),
    "U04-initialize-projects": ("initialized_projects", "initialized_projects", {"greenfield": ".academy/workspaces/U04-greenfield", "brownfield": ".academy/workspaces/U04-brownfield", "report": ".codearbiter/reports/academy/U04-initialization.md"}),
    "U05-debug-spike-conflict": ("debug_spike_conflict_artifacts", "debug_spike_conflict", {"spike": ".codearbiter/spikes/u05-cache-key.md", "board": ".codearbiter/open-tasks.md", "observation": "docs/U05-cache-key-observation.md"}),
    "U06-preview-and-advanced-surfaces": ("preview_advanced_evidence", "u06_preview_evidence", {"candidate": "docs/U06-preview-candidate.md", "report": ".codearbiter/reports/academy/U06-preview.json"}),
    "U07-capstone": ("feature_capstone_range", "feature_capstone", {"code": "workshop_queue/service.py", "test": "tests/test_service.py"}),
}


class CheckpointError(ValueError):
    """A checkpoint definition, contract, or evidence set is invalid."""


@dataclass(frozen=True)
class Predicate:
    id: str
    type: str
    data: dict[str, object]


@dataclass(frozen=True)
class Checkpoint:
    id: str
    digest: str
    predicates: tuple[Predicate, ...]


@dataclass(frozen=True)
class LabContract:
    id: str
    title: str
    source_path: str
    checkpoint_path: str
    scenario_path: str


@dataclass(frozen=True)
class CheckpointResult:
    lab_id: str
    passed: bool
    definition_digest: str
    digest: str
    passed_predicates: tuple[str, ...]
    failed_predicates: tuple[str, ...]
    catalog_digest: str = ""
    manifest_digest: str = ""
    source_digest: str = ""
    contract_digest: str = ""
    attempt: str = ""
    prepared_commit: str = ""
    base_commit: str = ""
    head_commit: str = ""


@dataclass(frozen=True)
class _Attempt:
    branch: str
    number: int
    prepared: str
    base: str
    head: str


def canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def sha256(value: object) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def _raw_digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _version(value: object, expected: int) -> bool:
    return type(value) is int and value == expected


def _object(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CheckpointError(f"{label} must be an object.")
    return value


def _exact_keys(value: dict[str, Any], keys: set[str], label: str) -> None:
    if set(value) != keys:
        raise CheckpointError(f"{label} has unknown or missing keys.")


def _string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 256:
        raise CheckpointError(f"{label} must be a non-empty bounded string.")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise CheckpointError(f"{label} contains control characters.")
    return value


def _safe_path(value: object, label: str, *, directory: bool = False) -> str:
    path = _string(value, label)
    if "\\" in path or path.startswith("/") or ":" in path:
        raise CheckpointError(f"{label} must be a canonical repository-relative path.")
    parts = path.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise CheckpointError(f"{label} must be a canonical repository-relative path.")
    if not directory and path.endswith("/"):
        raise CheckpointError(f"{label} must name a file.")
    return path


def _identifier(value: object, label: str) -> str:
    text = _string(value, label)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}", text):
        raise CheckpointError(f"{label} must be a safe identifier.")
    return text


def _load_json_file(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
        data = _object(json.loads(raw.decode("utf-8")), label)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CheckpointError(f"{label} could not be read.") from error
    return data, raw


def load_checkpoint(path: Path) -> Checkpoint:
    data, raw = _load_json_file(path, "checkpoint")
    _exact_keys(data, {"schema_version", "id", "predicates"}, "checkpoint")
    if type(data["schema_version"]) is not int or data["schema_version"] != 2:
        raise CheckpointError("checkpoint schema_version must be integer 2.")
    lab_id = _string(data["id"], "checkpoint id")
    entries = data["predicates"]
    if not isinstance(entries, list) or len(entries) != 1:
        raise CheckpointError("checkpoint predicates must contain exactly one item.")
    predicates: list[Predicate] = []
    identifiers: set[str] = set()
    for index, value in enumerate(entries):
        item = _object(value, f"predicate {index}")
        ident = _identifier(item.get("id"), "predicate id")
        if ident in identifiers:
            raise CheckpointError("checkpoint has duplicate predicate IDs.")
        identifiers.add(ident)
        kind = _string(item.get("type"), "predicate type")
        if kind == "lab_semantics":
            profile = _string(item.get("profile"), "predicate profile")
            fields = _PROFILES.get(profile)
            if fields is None:
                raise CheckpointError("checkpoint has unsupported semantic profile.")
            expected = {"id", "type", "profile", *fields}
            _exact_keys(item, expected, "semantic predicate")
            data_fields: dict[str, object] = {"profile": profile}
            for field in fields:
                if field == "task_id":
                    data_fields[field] = _identifier(item[field], field)
                elif field == "tag_prefix":
                    prefix = _string(item[field], field)
                    if not re.fullmatch(r"[a-z][a-z0-9.-]{1,31}", prefix):
                        raise CheckpointError("tag_prefix is invalid.")
                    data_fields[field] = prefix
                elif field == "release_target":
                    target = _string(item[field], field)
                    if not re.fullmatch(r"[a-z][a-z0-9-]{1,63}", target):
                        raise CheckpointError("release_target is invalid.")
                    data_fields[field] = target
                elif field == "release_version":
                    version = _string(item[field], field)
                    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version):
                        raise CheckpointError("release_version is invalid.")
                    data_fields[field] = version
                elif field == "release_tag":
                    release_tag = _string(item[field], field)
                    if not re.fullmatch(r"[a-z][a-z0-9-]*-v[0-9]+\.[0-9]+\.[0-9]+", release_tag):
                        raise CheckpointError("release_tag is invalid.")
                    data_fields[field] = release_tag
                elif field in {"release_changelog", "release_targets"}:
                    data_fields[field] = _safe_path(item[field], field)
                else:
                    data_fields[field] = _safe_path(
                        item[field], field, directory=field == "workspace"
                    )
            predicates.append(Predicate(ident, kind, data_fields))
            continue
        raise CheckpointError("checkpoint has unsupported predicate type.")
    return Checkpoint(lab_id, _raw_digest(raw), tuple(predicates))


def load_contracts(root: Path) -> tuple[LabContract, ...]:
    data, _ = _load_json_file(root / "academy" / "contracts.json", "Academy contracts")
    _exact_keys(data, {"schema_version", "contracts"}, "Academy contracts")
    if type(data["schema_version"]) is not int or data["schema_version"] != 2:
        raise CheckpointError("Academy contract schema_version must be integer 2.")
    entries = data["contracts"]
    if not isinstance(entries, list) or len(entries) != len(LAB_INVENTORY):
        raise CheckpointError("Academy contracts must contain the exact 19-lab inventory.")
    catalog = Catalog.load(root / "academy" / "catalog.json")
    contracts: list[LabContract] = []
    all_paths: set[str] = set()
    for index, (expected_id, value) in enumerate(zip(LAB_INVENTORY, entries, strict=True)):
        item = _object(value, f"contract {index}")
        _exact_keys(
            item,
            {"id", "title", "source_path", "checkpoint_path", "scenario_path"},
            f"contract {index}",
        )
        if item["id"] != expected_id:
            raise CheckpointError("Academy contract IDs and order must match the exact inventory.")
        lab = catalog.labs[index]
        if lab.id != expected_id:
            raise CheckpointError("Academy catalog and contract order disagree.")
        checkpoint_path = _safe_path(item["checkpoint_path"], "checkpoint_path")
        source_path = _safe_path(item["source_path"], "source_path")
        scenario_path = _safe_path(item["scenario_path"], "scenario_path")
        if checkpoint_path != lab.checkpoint:
            raise CheckpointError("Academy contract checkpoint mapping disagrees with catalog.")
        expected_source = f"academy/tracks/{lab.track}/{lab.id}.md"
        if source_path != expected_source:
            raise CheckpointError("Academy contract source mapping is noncanonical.")
        if scenario_path != f"training_scenarios/{lab.id}.json":
            raise CheckpointError("Academy contract scenario mapping is noncanonical.")
        for path in (source_path, checkpoint_path, scenario_path):
            if path in all_paths:
                raise CheckpointError("Academy contract paths must be unique.")
            all_paths.add(path)
        checkpoint_data, _ = _load_json_file(root / checkpoint_path, "Academy checkpoint")
        if (
            type(checkpoint_data.get("schema_version")) is not int
            or checkpoint_data.get("schema_version") != 2
        ):
            raise CheckpointError("Academy checkpoint schema_version must be integer 2.")
        checkpoint = load_checkpoint(root / checkpoint_path)
        if checkpoint.id != expected_id or len(checkpoint.predicates) != 1:
            raise CheckpointError("Academy checkpoint mapping is inconsistent.")
        predicate = checkpoint.predicates[0]
        if predicate.type != "lab_semantics":
            raise CheckpointError("Academy checkpoints must use semantic predicates.")
        expected_predicate_id, expected_profile, expected_data = _CANONICAL_PREDICATES[expected_id]
        if (
            predicate.id != expected_predicate_id
            or predicate.data.get("profile") != expected_profile
            or {key: value for key, value in predicate.data.items() if key != "profile"}
            != expected_data
        ):
            raise CheckpointError("Academy checkpoint semantic mapping is noncanonical.")
        contracts.append(
            LabContract(
                expected_id,
                _string(item["title"], "contract title"),
                source_path,
                checkpoint_path,
                scenario_path,
            )
        )
    return tuple(contracts)


def _git_blob(root: Path, ref: str, path: str) -> bytes | None:
    result = run_git(root, ["show", f"{ref}:{path}"], check=False)
    if result.returncode:
        return None
    return result.stdout.encode("utf-8", "surrogateescape")


def _load_attempt_definition(
    root: Path, ref: str, lab_id: str
) -> tuple[tuple[LabContract, ...], LabContract, Checkpoint]:
    """Parse the canonical Academy rules from one immutable Git tree."""
    paths = (
        "academy/catalog.json",
        "academy/contracts.json",
        *(f"academy/checkpoints/{item}.json" for item in LAB_INVENTORY),
    )
    with TemporaryDirectory(prefix="academy-rules-") as directory:
        materialized = Path(directory)
        for path in paths:
            blob = _git_blob(root, ref, path)
            if blob is None:
                raise CheckpointError(f"Academy rule source is absent from {ref}: {path}")
            destination = materialized / path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(blob)
        contracts = load_contracts(materialized)
        contract = contracts[LAB_INVENTORY.index(lab_id)]
        definition = load_checkpoint(materialized / contract.checkpoint_path)
    return contracts, contract, definition


def _verifier_paths(root: Path, ref: str) -> tuple[str, ...]:
    """Return the complete tracked Python verifier boundary at one Git tree."""
    paths = run_git(
        root,
        [
            "ls-tree",
            "-r",
            "--name-only",
            ref,
            "--",
            "academy_engine",
            "scripts",
        ],
        check=False,
    ).stdout.splitlines()
    verifier = tuple(
        path
        for path in paths
        if path.endswith(".py")
        and (path.startswith("academy_engine/") or path == "scripts/academy.py")
    )
    if not verifier or "academy_engine/checkpoints.py" not in verifier or "scripts/academy.py" not in verifier:
        raise CheckpointError("Academy verifier boundary is incomplete.")
    return verifier


def _control_namespace_paths(root: Path, ref: str) -> tuple[str, ...]:
    paths = run_git(
        root,
        [
            "ls-tree",
            "-r",
            "--name-only",
            ref,
            "--",
            "academy_engine",
            "scripts",
            "academy",
        ],
        check=False,
    ).stdout.splitlines()
    controls = tuple(
        path
        for path in paths
        if (
            path.startswith("academy_engine/")
            or path == "scripts/academy.py"
            or path in {
                "academy/catalog.json",
                "academy/catalog.schema.json",
                "academy/contracts.json",
                "academy/checkpoint.schema.json",
                "academy/receipt.schema.json",
                "academy/scenario.schema.json",
            }
            or path.startswith("academy/checkpoints/")
            or path.startswith("academy/scenarios/")
        )
    )
    required = {
        "academy_engine/checkpoints.py",
        "academy_engine/cli.py",
        "scripts/academy.py",
        "academy/catalog.json",
        "academy/contracts.json",
    }
    if not required.issubset(controls):
        raise CheckpointError("Academy control namespace is incomplete.")
    return controls


def _text(root: Path, ref: str, path: str) -> str | None:
    value = _git_blob(root, ref, path)
    return None if value is None else value.decode("utf-8", "surrogateescape")


def _json(root: Path, ref: str, path: str) -> dict[str, Any] | None:
    value = _text(root, ref, path)
    try:
        data = json.loads(value) if value is not None else None
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _changed(root: Path, base: str, head: str, path: str) -> bool:
    return run_git(
        root,
        ["diff", "--no-ext-diff", "--quiet", base, head, "--", path],
        check=False,
    ).returncode == 1


def _repository_oid_pattern(root: Path) -> re.Pattern[str] | None:
    result = run_git(root, ["rev-parse", "--show-object-format"], check=False)
    if result.returncode:
        return None
    return {"sha1": _SHA40, "sha256": _SHA256}.get(result.stdout.strip().lower())


def _path_commits(root: Path, start: str, head: str, *paths: str) -> tuple[str, ...]:
    result = run_git(
        root,
        ["log", "--reverse", "--format=%H", f"{start}..{head}", "--", *paths],
        check=False,
    )
    return tuple(line for line in result.stdout.splitlines() if _SHA40.fullmatch(line))


def _commit_paths(root: Path, commit: str) -> tuple[str, ...]:
    result = run_git(
        root,
        ["diff-tree", "--no-commit-id", "--name-only", "-r", commit],
        check=False,
    )
    return tuple(result.stdout.splitlines()) if result.returncode == 0 else ()


def _exact_two_commit_range(
    root: Path, prepared: str, head: str
) -> tuple[str, str] | None:
    oid_pattern = _repository_oid_pattern(root)
    if oid_pattern is None:
        return None
    result = run_git(
        root,
        ["rev-list", "--reverse", f"{prepared}..{head}"],
        check=False,
    )
    commits = tuple(
        line for line in result.stdout.splitlines() if oid_pattern.fullmatch(line)
    )
    if result.returncode or len(commits) != 2:
        return None
    expected_parent = prepared
    for commit in commits:
        parent_result = run_git(
            root, ["rev-list", "--parents", "-n", "1", commit], check=False
        )
        if parent_result.returncode:
            return None
        parents = parent_result.stdout.split()
        if parents != [commit, expected_parent]:
            return None
        expected_parent = commit
    if commits[-1] != head:
        return None
    return commits[0], commits[1]


def _exact_three_commit_range(
    root: Path, prepared: str, head: str
) -> tuple[str, str, str] | None:
    """Return one linear three-commit learner range, or no bounded range."""
    oid_pattern = _repository_oid_pattern(root)
    if oid_pattern is None:
        return None
    result = run_git(root, ["rev-list", "--reverse", f"{prepared}..{head}"], check=False)
    commits = tuple(line for line in result.stdout.splitlines() if oid_pattern.fullmatch(line))
    if result.returncode or len(commits) != 3 or commits[-1] != head:
        return None
    parent = prepared
    for commit in commits:
        parents = run_git(root, ["rev-list", "--parents", "-n", "1", commit], check=False).stdout.split()
        if parents != [commit, parent]:
            return None
        parent = commit
    return commits[0], commits[1], commits[2]


def _predicted_reviewers(paths: list[str]) -> list[str]:
    reviewers: set[str] = set()
    if any(path.startswith(".codearbiter/") for path in paths):
        reviewers.add("governance")
    if any(path.endswith(".py") for path in paths):
        reviewers.add("python")
    if any(path.endswith((".md", ".rst")) for path in paths):
        reviewers.add("docs")
    if any(
        path.startswith(".github/")
        or any(part in path.casefold() for part in ("auth", "remote", "secret", "security"))
        for path in paths
    ):
        reviewers.add("security")
    return sorted(reviewers or {"general"})


def _changed_blobs_are_secret_free(root: Path, commit: str, paths: list[str]) -> bool:
    return all(
        (blob := _git_blob(root, commit, path)) is not None
        and blob_is_secret_free(blob)
        for path in paths
    )


def _discover_attempt(root: Path, lab_id: str, *, require_current: bool) -> _Attempt:
    refs = run_git(
        root,
        ["for-each-ref", "--format=%(refname:short)", f"refs/heads/academy/{lab_id}/"],
    ).stdout.splitlines()
    choices: list[tuple[int, str]] = []
    for ref in refs:
        match = _ATTEMPT.fullmatch(ref)
        if match is None or match.group("lab") != lab_id:
            raise CheckpointError("Academy attempt namespace contains a noncanonical ref.")
        choices.append((int(match.group("number")), ref))
    if not choices:
        raise CheckpointError("Academy attempt is unavailable.")
    current = run_git(root, ["branch", "--show-current"], check=False).stdout.strip()
    current_match = _ATTEMPT.fullmatch(current)
    if current_match is not None and current_match.group("lab") == lab_id:
        selected = (int(current_match.group("number")), current)
    elif require_current:
        raise CheckpointError(f"current branch is not an Academy attempt for {lab_id}.")
    else:
        selected = max(choices)
    number, branch = selected
    head = run_git(root, ["rev-parse", branch]).stdout.strip()
    subject = f"academy: prepare {lab_id} attempt {number}"
    candidates = run_git(
        root, ["log", "--format=%H%x00%s", branch]
    ).stdout.splitlines()
    commits = [line.split("\x00", 1)[0] for line in candidates if line.endswith("\x00" + subject)]
    commits = [
        commit
        for commit in commits
        if run_git(root, ["merge-base", "--is-ancestor", commit, head], check=False).returncode == 0
    ]
    if len(commits) != 1:
        raise CheckpointError("Academy attempt must contain one canonical prepare commit.")
    prepared = commits[0]
    base_result = run_git(root, ["rev-parse", f"{prepared}^"], check=False)
    if base_result.returncode:
        raise CheckpointError("Academy prepare commit has no base parent.")
    base = base_result.stdout.strip()
    if run_git(root, ["merge-base", "--is-ancestor", base, "main"], check=False).returncode:
        raise CheckpointError("Academy prepare base is not in main history.")
    if run_git(root, ["rev-list", "--count", f"{prepared}..{head}"]).stdout.strip() == "0":
        raise CheckpointError("Academy attempt has no learner commit after preparation.")
    return _Attempt(branch, number, prepared, base, head)


def _validate_prepare(root: Path, contract: LabContract, attempt: _Attempt) -> bool:
    manifest_path = f"academy/scenarios/{contract.id}/manifest.json"
    manifest_blob = _git_blob(root, attempt.base, manifest_path)
    try:
        manifest = load_manifest(
            json.loads(manifest_blob.decode("utf-8")) if manifest_blob is not None else None
        )
    except Exception:
        return False
    expected_paths = {
        *(overlay.destination for overlay in manifest.files),
        *manifest.removals,
    }
    if manifest.control_state_seed is not None:
        expected_paths.add(manifest.control_state_seed.destination)
    if contract.id == "P02-commit-review-pr":
        expected_paths.add(".codearbiter/tech-stack.md")
    if contract.id == "P05-checkpoint-remediation":
        expected_paths.update(
            {
                ".codearbiter/decisions/0005-terminal-blocked-ticket-lifecycle.md",
                ".codearbiter/decisions/decision-log.md",
                "tests/test_cli.py",
                "workshop_queue/cli.py",
                "workshop_queue/model.py",
                "workshop_queue/service.py",
            }
        )
    if contract.id == "U07-capstone":
        expected_paths.add("tests/test_service.py")
    actual_paths = set(
        run_git(
            root,
            [
                "diff-tree",
                "--no-commit-id",
                "--name-only",
                "-r",
                attempt.prepared,
            ],
            check=False,
        ).stdout.splitlines()
    )
    if not expected_paths or actual_paths != expected_paths or contract.scenario_path not in expected_paths:
        return False
    files_root = f"academy/scenarios/{contract.id}/files"
    for overlay in manifest.files:
        source_blob = _git_blob(root, attempt.base, f"{files_root}/{overlay.source}")
        if source_blob is None or _git_blob(root, attempt.prepared, overlay.destination) != source_blob:
            return False
    if manifest.control_state_seed is not None:
        seed = manifest.control_state_seed
        source_blob = _git_blob(root, attempt.base, f"{files_root}/{seed.source}")
        if source_blob is None or _git_blob(root, attempt.prepared, seed.destination) != source_blob:
            return False
    for removal in manifest.removals:
        if _git_blob(root, attempt.base, removal) is None or _git_blob(root, attempt.prepared, removal) is not None:
            return False
    if contract.id == "P02-commit-review-pr":
        return validate_p02_prepared_commit(
            root,
            base_commit=attempt.base,
            prepared_commit=attempt.prepared,
            branch=attempt.branch,
            attempt_number=attempt.number,
        )
    if contract.id == "P05-checkpoint-remediation":
        return validate_p05_fixture(root, attempt.prepared)
    if contract.id == "U07-capstone":
        return validate_u07_fixture(root, attempt.prepared)
    return True


def _p05_remediation(root: Path, attempt: _Attempt, report_path: str) -> bool:
    if run_git(root, ["status", "--porcelain", "--untracked-files=all"], check=False).stdout:
        return False
    if not validate_p05_fixture(root, attempt.prepared):
        return False
    oid_pattern = _repository_oid_pattern(root)
    if oid_pattern is None:
        return False
    raw = _git_blob(root, attempt.head, report_path)
    if raw is None or raw.startswith(b"\xef\xbb\xbf") or b"\r" in raw or not raw.endswith(b"\n"):
        return False
    try:
        report = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return False
    required = {"affected_paths", "finding_commit", "finding_id", "red_commit", "remediation_commit", "schema_version", "status"}
    if (
        canonical_json(report) + b"\n" != raw
        or not isinstance(report, dict)
        or set(report) != required
        or not _version(report["schema_version"], 2)
        or report["finding_id"] != "ACADEMY-P05-BLOCKED-UNRESOLVED"
        or report["status"] != "remediated"
        or report["affected_paths"] != ["tests/test_cli.py", "workshop_queue/cli.py"]
    ):
        return False
    finding, red, remediation = report["finding_commit"], report["red_commit"], report["remediation_commit"]
    if not all(isinstance(value, str) and oid_pattern.fullmatch(value) for value in (finding, red, remediation)):
        return False
    commits = tuple(line for line in run_git(root, ["rev-list", "--reverse", f"{attempt.prepared}..{attempt.head}"], check=False).stdout.splitlines() if oid_pattern.fullmatch(line))
    if commits != (finding, red, remediation, attempt.head):
        return False
    parent = attempt.prepared
    for commit in commits:
        if run_git(root, ["rev-list", "--parents", "-n", "1", commit], check=False).stdout.split() != [commit, parent]:
            return False
        parent = commit
    finding_paths, red_paths, remediation_paths, receipt_paths = (
        _commit_paths(root, commit) for commit in commits
    )
    checkpoint_paths = tuple(
        path
        for path in finding_paths
        if re.fullmatch(r"\.codearbiter/checkpoints/\d{4}-\d{2}-\d{2}\.md", path)
    )
    checkpoint_path = checkpoint_paths[0] if len(checkpoint_paths) == 1 else ""
    checkpoint_date = checkpoint_path.removeprefix(".codearbiter/checkpoints/").removesuffix(".md")
    if (
        len(checkpoint_paths) != 1
        or set(finding_paths)
        != {
            checkpoint_paths[0],
            ".codearbiter/last-checkpoint",
            ".codearbiter/reports/academy/P05-finding.md",
        }
        or red_paths != ("tests/test_cli.py",)
        or remediation_paths != ("workshop_queue/cli.py",)
        or receipt_paths != (report_path,)
    ):
        return False
    finding_blob = _text(root, finding, ".codearbiter/reports/academy/P05-finding.md")
    checkpoint_blob = _text(root, finding, checkpoint_paths[0])
    checkpoint_baseline = _text(root, finding, ".codearbiter/last-checkpoint")
    if (
        not _p05_finding_is_exact(finding_blob)
        or checkpoint_blob is None
        or re.fullmatch(
            rf"# CodeArbiter Checkpoint - {re.escape(checkpoint_date)}\n(?:.|\n)*",
            checkpoint_blob,
        ) is None
        or checkpoint_baseline is None
        or re.fullmatch(r"\d+\n", checkpoint_baseline) is None
    ):
        return False
    prepared_test, red_test, head_test = (
        _git_blob(root, attempt.prepared, "tests/test_cli.py"),
        _git_blob(root, red, "tests/test_cli.py"),
        _git_blob(root, attempt.head, "tests/test_cli.py"),
    )
    if prepared_test is None or red_test is None or head_test != red_test:
        return False
    if not _p05_red_regression(prepared_test, red_test):
        return False
    prepared_cli = _git_blob(root, attempt.prepared, "workshop_queue/cli.py")
    remediation_cli = _git_blob(root, remediation, "workshop_queue/cli.py")
    defect = b"sum(ticket.status in {TicketStatus.OPEN, TicketStatus.CLAIMED} for ticket in tickets)"
    correct = b"sum(ticket.status is not TicketStatus.COMPLETED for ticket in tickets)"
    return bool(prepared_cli and remediation_cli and defect in prepared_cli and correct in remediation_cli and remediation_cli.replace(correct, defect) == prepared_cli)


_P05_FINDING = (
    "# P05 Finding: blocked tickets omitted from unresolved summary\n\n"
    "Ticket `RQ-105` is blocked: `Venue access is awaiting facilities clearance`.\n"
    "Affected paths: `tests/test_cli.py`, `workshop_queue/cli.py`.\n"
)

_P05_RED_REGRESSION_SOURCE = (
    "def test_report_json_counts_blocked_ticket_as_unresolved(self) -> None:\n"
    "    tickets = json.loads(self.fixture.read_text(encoding=\"utf-8\"))\n"
    "    tickets[0][\"id\"] = \"RQ-105\"\n"
    "    self.fixture.write_text(json.dumps(tickets), encoding=\"utf-8\")\n"
    "    claim_result = self.run_cli(\"claim\", \"RQ-105\", \"--volunteer\", \"Sam\")\n"
    "    block_result = self.run_cli(\"block\", \"RQ-105\", \"--reason\", \"Venue access is awaiting facilities clearance\")\n"
    "    report = self.run_cli(\"report\", \"--format\", \"json\")\n"
    "    self.assertEqual(claim_result.returncode, 0, claim_result.stderr)\n"
    "    self.assertEqual(block_result.returncode, 0, block_result.stderr)\n"
    "    self.assertEqual(report.returncode, 0, report.stderr)\n"
    "    parsed = json.loads(report.stdout)\n"
    "    self.assertEqual(parsed[\"blocked\"], 1)\n"
    "    self.assertEqual(parsed[\"unresolved\"], 1)\n"
)
_P05_RED_REGRESSION_AST = ast.dump(
    ast.parse(_P05_RED_REGRESSION_SOURCE, filename="tests/test_cli.py").body[0],
    include_attributes=False,
)


def _p05_finding_is_exact(text: str | None) -> bool:
    """Accept only the short, reviewable P05 finding grammar.

    The canonical sentence form intentionally has no command/output/identity field in
    which a learner could smuggle host transcripts, absolute paths, or credentials.
    """
    return text == _P05_FINDING


def _p05_source_is_utf8(raw: bytes) -> bool:
    lines = iter(raw.splitlines(keepends=True))
    try:
        encoding, _ = tokenize.detect_encoding(lambda: next(lines, b""))
    except SyntaxError:
        return False
    return encoding == "utf-8"


def _p05_red_regression(prepared_raw: bytes, red_raw: bytes) -> bool:
    """Require RED to add only the named direct test method to the prepared AST."""
    if not _p05_source_is_utf8(prepared_raw) or not _p05_source_is_utf8(red_raw):
        return False
    try:
        prepared_tree = ast.parse(prepared_raw.decode("utf-8"), filename="tests/test_cli.py")
        red_tree = ast.parse(red_raw.decode("utf-8"), filename="tests/test_cli.py")
    except (UnicodeDecodeError, SyntaxError):
        return False

    def owners(tree: ast.Module) -> list[ast.ClassDef]:
        return [
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "WorkshopQueueCliTests"
        ]

    prepared_owners = owners(prepared_tree)
    red_owners = owners(red_tree)
    if len(prepared_owners) != 1 or len(red_owners) != 1:
        return False

    method_name = "test_report_json_counts_blocked_ticket_as_unresolved"
    prepared_methods = [
        node
        for node in prepared_owners[0].body
        if isinstance(node, ast.FunctionDef) and node.name == method_name
    ]
    red_methods = [
        node
        for node in red_owners[0].body
        if isinstance(node, ast.FunctionDef) and node.name == method_name
    ]
    if prepared_methods or len(red_methods) != 1 or red_methods[0].decorator_list:
        return False

    red_without_regression = copy.deepcopy(red_tree)
    red_owner = owners(red_without_regression)[0]
    red_owner.body = [
        node
        for node in red_owner.body
        if not (isinstance(node, ast.FunctionDef) and node.name == method_name)
    ]
    return (
        ast.dump(prepared_tree, include_attributes=False)
        == ast.dump(red_without_regression, include_attributes=False)
        and _p05_red_regression_is_exact(red_raw)
    )


def _p05_red_regression_is_exact(raw: bytes) -> bool:
    """Compare the committed direct regression with the exact taught method AST."""
    if not _p05_source_is_utf8(raw):
        return False
    try:
        tree = ast.parse(raw.decode("utf-8"), filename="tests/test_cli.py")
    except (UnicodeDecodeError, SyntaxError):
        return False
    owners = [
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "WorkshopQueueCliTests"
    ]
    if len(owners) != 1:
        return False
    methods = [
        node
        for node in owners[0].body
        if isinstance(node, ast.FunctionDef)
        and node.name == "test_report_json_counts_blocked_ticket_as_unresolved"
    ]
    return (
        len(methods) == 1
        and ast.dump(methods[0], include_attributes=False) == _P05_RED_REGRESSION_AST
    )

def _headings(text: str | None, required: tuple[str, ...]) -> bool:
    if text is None:
        return False
    headings = {line.strip().casefold() for line in text.splitlines() if line.startswith("#")}
    return all(f"## {heading}".casefold() in headings or f"### {heading}".casefold() in headings for heading in required)


def _plain_path_within(base: Path, target: Path, *, regular_file: bool) -> bool:
    """Require every target component below *base* to be a non-reparse path."""
    try:
        parts = target.relative_to(base).parts
    except ValueError:
        return False
    if not parts:
        return False
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    current = base
    for index, part in enumerate(parts):
        if part in {"", ".", ".."}:
            return False
        current /= part
        try:
            metadata = current.lstat()
        except OSError:
            return False
        if stat.S_ISLNK(metadata.st_mode) or (
            reparse_flag
            and getattr(metadata, "st_file_attributes", 0) & reparse_flag
        ):
            return False
        final = index == len(parts) - 1
        if final and regular_file:
            if not stat.S_ISREG(metadata.st_mode):
                return False
        elif not stat.S_ISDIR(metadata.st_mode):
            return False
    return True


def _remote_safe(root: Path) -> bool:
    try:
        report = validate_training_remotes(root, require_push_safe=True)
    except RemoteSafetyError:
        return False
    return bool(
        report.push_safe
        and report.origin_fork_compatible
        and report.effective_push_remote == "origin"
        and report.upstream_push_disabled
        and (root / ".codearbiter" / "CONTEXT.md").is_file()
    )


def _changed_document(context: "_SemanticContext", path: str) -> str | None:
    return _text(context.root, context.attempt.head, path) if _changed(
        context.root, context.attempt.prepared, context.attempt.head, path
    ) else None


def _f04_has_uncommitted_learner_changes(root: Path) -> bool:
    """Reject every F04 worktree change except exercised interpreter cache files."""
    status = run_git(
        root, ["status", "--porcelain", "--untracked-files=all"], check=False
    )
    ignored = run_git(
        root, ["ls-files", "--others", "--ignored", "--exclude-standard"], check=False
    )
    if status.returncode != 0 or ignored.returncode != 0:
        return True
    allowed_cache = re.compile(
        r"(?:tests/__pycache__/test_service|workshop_queue/__pycache__/service)"
        r"\.cpython-[0-9]+(?:\.opt-[12])?\.pyc"
    )
    paths = [line[3:] for line in status.stdout.splitlines()]
    paths.extend(ignored.stdout.splitlines())
    for path in paths:
        if allowed_cache.fullmatch(path):
            continue
        return True
    return False


def _control_regression_method_matches_contract(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
) -> bool:
    def is_control(value: object) -> bool:
        return isinstance(value, str) and any(
            ord(character) < 32 or ord(character) == 127 for character in value
        )

    invalid_bound = False
    for loop in (node for node in ast.walk(function) if isinstance(node, ast.For)):
        if not isinstance(loop.target, ast.Name) or not isinstance(loop.iter, (ast.Tuple, ast.List)):
            continue
        values = [item.value for item in loop.iter.elts if isinstance(item, ast.Constant)]
        if len(values) != len(loop.iter.elts) or not values or not all(is_control(value) for value in values):
            continue
        for context in (node for node in ast.walk(loop) if isinstance(node, ast.With)):
            raises_control = any(
                isinstance(call := item.context_expr, ast.Call)
                and isinstance(call.func, ast.Attribute)
                and call.func.attr == "assertRaisesRegex"
                and len(call.args) >= 2
                and isinstance(call.args[0], ast.Name)
                and call.args[0].id == "ValueError"
                and isinstance(call.args[1], ast.Constant)
                and isinstance(call.args[1].value, str)
                and "control character" in call.args[1].value.casefold()
                for item in context.items
            )
            if not raises_control:
                continue
            invalid_bound = any(
                isinstance(call, ast.Call)
                and isinstance(call.func, ast.Name)
                and call.func.id == "claim_ticket"
                and len(call.args) >= 3
                and (
                    isinstance(call.args[2], ast.Name)
                    and call.args[2].id == loop.target.id
                    or isinstance(call.args[2], ast.Constant)
                    and is_control(call.args[2].value)
                )
                for statement in context.body
                for call in ast.walk(statement)
            )
            if invalid_bound:
                break
        if invalid_bound:
            break

    valid_bindings: dict[str, str] = {}
    for statement in function.body:
        if not (
            isinstance(statement, ast.Assign)
            and len(statement.targets) == 1
            and isinstance(statement.targets[0], ast.Name)
            and isinstance(statement.value, ast.Call)
            and isinstance(statement.value.func, ast.Name)
            and statement.value.func.id == "claim_ticket"
            and len(statement.value.args) >= 3
            and isinstance(statement.value.args[2], ast.Constant)
            and isinstance(statement.value.args[2].value, str)
        ):
            continue
        label = statement.value.args[2].value
        if label.strip() and not is_control(label):
            valid_bindings[statement.targets[0].id] = label

    valid_assertion = False
    for call in (node for node in ast.walk(function) if isinstance(node, ast.Call)):
        if not (
            isinstance(call.func, ast.Attribute)
            and call.func.attr == "assertEqual"
            and len(call.args) == 2
            and isinstance(call.args[0], ast.Attribute)
            and call.args[0].attr == "claimed_by"
            and isinstance(call.args[0].value, ast.Subscript)
            and isinstance(call.args[0].value.value, ast.Name)
            and isinstance(call.args[0].value.slice, ast.Constant)
            and call.args[0].value.slice.value == 0
            and isinstance(call.args[1], ast.Constant)
            and isinstance(call.args[1].value, str)
        ):
            continue
        binding = call.args[0].value.value.id
        valid_assertion = valid_bindings.get(binding) == call.args[1].value
        if valid_assertion:
            break
    return invalid_bound and valid_assertion


def _imports_production_claim_ticket(tree: ast.Module) -> bool:
    imports = [
        alias
        for statement in tree.body
        if isinstance(statement, ast.ImportFrom)
        and statement.module == "workshop_queue.service"
        and statement.level == 0
        for alias in statement.names
        if alias.name == "claim_ticket" and alias.asname is None
    ]
    return len(imports) == 1


def _scope_binds_claim_ticket(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
) -> bool:
    arguments = (
        function.args.posonlyargs
        + function.args.args
        + function.args.kwonlyargs
        + ([function.args.vararg] if function.args.vararg else [])
        + ([function.args.kwarg] if function.args.kwarg else [])
    )
    if any(argument.arg == "claim_ticket" for argument in arguments):
        return True
    for node in ast.walk(function):
        if (
            isinstance(node, ast.Name)
            and node.id == "claim_ticket"
            and isinstance(node.ctx, (ast.Store, ast.Del))
        ):
            return True
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            and node is not function
            and node.name == "claim_ticket"
        ):
            return True
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                bound = alias.asname or alias.name.split(".", 1)[0]
                if bound == "claim_ticket":
                    return True
        if isinstance(node, ast.ExceptHandler) and node.name == "claim_ticket":
            return True
        if isinstance(node, (ast.MatchAs, ast.MatchStar)) and node.name == "claim_ticket":
            return True
        if isinstance(node, ast.MatchMapping) and node.rest == "claim_ticket":
            return True
    return False


def _direct_control_regression(
    tree: ast.Module,
) -> tuple[ast.ClassDef, ast.FunctionDef | ast.AsyncFunctionDef] | None:
    classes = [
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "TicketTransitionTests"
    ]
    if len(classes) != 1:
        return None
    methods = [
        node
        for node in classes[0].body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "test_claim_rejects_control_characters_in_volunteer_label"
    ]
    if len(methods) != 1:
        return None
    return classes[0], methods[0]


def _without_control_regression(tree: ast.Module) -> ast.Module | None:
    candidate = copy.deepcopy(tree)
    located = _direct_control_regression(candidate)
    if located is None:
        return None
    test_class, method = located
    test_class.body.remove(method)
    return candidate


def _test_module_has_minimal_retained_control_regression(
    prepared_blob: bytes | None,
    regression_blob: bytes | None,
    final_blob: bytes | None,
) -> bool:
    if prepared_blob is None or regression_blob is None or final_blob is None:
        return False
    try:
        prepared_tree = ast.parse(prepared_blob.decode("utf-8"))
        regression_tree = ast.parse(regression_blob.decode("utf-8"))
        final_tree = ast.parse(final_blob.decode("utf-8"))
    except (UnicodeDecodeError, SyntaxError):
        return False
    if _direct_control_regression(prepared_tree) is not None:
        return False
    if not all(
        _imports_production_claim_ticket(tree)
        for tree in (prepared_tree, regression_tree, final_tree)
    ):
        return False
    regression = _direct_control_regression(regression_tree)
    final = _direct_control_regression(final_tree)
    if regression is None or final is None:
        return False
    regression_method, final_method = regression[1], final[1]
    if (
        _scope_binds_claim_ticket(regression_method)
        or _scope_binds_claim_ticket(final_method)
        or not _control_regression_method_matches_contract(regression_method)
        or not _control_regression_method_matches_contract(final_method)
        or ast.dump(regression_method, include_attributes=False)
        != ast.dump(final_method, include_attributes=False)
    ):
        return False
    regression_without = _without_control_regression(regression_tree)
    final_without = _without_control_regression(final_tree)
    if regression_without is None or final_without is None:
        return False
    prepared_dump = ast.dump(prepared_tree, include_attributes=False)
    return (
        ast.dump(regression_without, include_attributes=False) == prepared_dump
        and ast.dump(final_without, include_attributes=False) == prepared_dump
    )


def _character_control_predicate(test: ast.expr) -> bool:
    if not (
        isinstance(test, ast.Call)
        and isinstance(test.func, ast.Name)
        and test.func.id == "any"
        and len(test.args) == 1
        and not test.keywords
        and isinstance(test.args[0], ast.GeneratorExp)
    ):
        return False
    generator = test.args[0]
    if len(generator.generators) != 1:
        return False
    comprehension = generator.generators[0]
    if not (
        isinstance(comprehension.target, ast.Name)
        and isinstance(comprehension.iter, ast.Name)
        and comprehension.iter.id == "volunteer"
        and not comprehension.ifs
        and not comprehension.is_async
    ):
        return False
    character = comprehension.target.id
    terms = generator.elt.values if isinstance(generator.elt, ast.BoolOp) and isinstance(generator.elt.op, ast.Or) else ()

    def operand(expression: ast.expr) -> tuple[str, object] | None:
        if isinstance(expression, ast.Name) and expression.id == character:
            return ("character", character)
        if (
            isinstance(expression, ast.Call)
            and isinstance(expression.func, ast.Name)
            and expression.func.id == "ord"
            and len(expression.args) == 1
            and isinstance(expression.args[0], ast.Name)
            and expression.args[0].id == character
        ):
            return ("ord", character)
        return None

    lower = False
    delete = False
    for term in terms:
        if not isinstance(term, ast.Compare) or len(term.ops) != 1 or len(term.comparators) != 1:
            continue
        left = operand(term.left)
        right = term.comparators[0]
        if left == ("ord", character) and isinstance(right, ast.Constant) and type(right.value) is int:
            lower = lower or (isinstance(term.ops[0], ast.Lt) and right.value == 32)
            delete = delete or (isinstance(term.ops[0], ast.Eq) and right.value == 127)
        if left == ("character", character) and isinstance(right, ast.Constant) and isinstance(right.value, str):
            lower = lower or (isinstance(term.ops[0], ast.Lt) and right.value == " ")
            delete = delete or (isinstance(term.ops[0], ast.Eq) and right.value == "\x7f")
    return lower and delete


def _service_has_minimal_control_repair(
    prepared_blob: bytes | None, final_blob: bytes | None
) -> bool:
    if prepared_blob is None or final_blob is None:
        return False
    try:
        prepared_tree = ast.parse(prepared_blob.decode("utf-8"))
        final_tree = ast.parse(final_blob.decode("utf-8"))
    except (UnicodeDecodeError, SyntaxError):
        return False
    prepared_functions = [
        node for node in prepared_tree.body if isinstance(node, ast.FunctionDef) and node.name == "claim_ticket"
    ]
    final_functions = [
        node for node in final_tree.body if isinstance(node, ast.FunctionDef) and node.name == "claim_ticket"
    ]
    if len(prepared_functions) != 1 or len(final_functions) != 1:
        return False
    prepared_dump = ast.dump(prepared_tree, include_attributes=False)
    successful_removals = 0
    function = final_functions[0]
    for ticket_branch in (node for node in function.body if isinstance(node, ast.For)):
        for match_branch in (node for node in ticket_branch.body if isinstance(node, ast.If)):
            names = {node.id for node in ast.walk(match_branch.test) if isinstance(node, ast.Name)}
            attributes = {
                node.attr for node in ast.walk(match_branch.test) if isinstance(node, ast.Attribute)
            }
            if "ticket_id" not in names or "ticket_id" not in attributes:
                continue
            for index, branch in enumerate(match_branch.body):
                if (
                    not isinstance(branch, ast.If)
                    or branch.orelse
                    or index + 1 >= len(match_branch.body)
                    or not isinstance(match_branch.body[index + 1], ast.Return)
                ):
                    continue
                raises = [node for node in branch.body if isinstance(node, ast.Raise)]
                messages = {
                    node.value
                    for raised in raises
                    for node in ast.walk(raised)
                    if isinstance(node, ast.Constant) and isinstance(node.value, str)
                }
                if not (
                    len(branch.body) == 1
                    and len(raises) == 1
                    and _character_control_predicate(branch.test)
                    and any("control character" in value.casefold() for value in messages)
                ):
                    continue
                candidate = copy.deepcopy(final_tree)
                candidate_matches = [
                    node
                    for node in ast.walk(candidate)
                    if isinstance(node, ast.If)
                    and getattr(node, "lineno", None) == getattr(match_branch, "lineno", None)
                    and getattr(node, "col_offset", None)
                    == getattr(match_branch, "col_offset", None)
                ]
                if len(candidate_matches) != 1:
                    continue
                candidate_match = candidate_matches[0]
                del candidate_match.body[index]
                if ast.dump(candidate, include_attributes=False) == prepared_dump:
                    successful_removals += 1
    return successful_removals == 1


@dataclass(frozen=True)
class _SemanticContext:
    root: Path
    attempt: _Attempt
    predicate: Predicate


_P01_SOURCE_IDENTITY = {
    "schema_version": 1,
    "repository": "arbiterForge/codeArbiter",
    "commit": "debb49da71aa1b97bca0988f72e46bb5875a23e3",
    "task_writer_path": "core/pysrc/taskwrite.py",
    "task_writer_blob": "287d49a24cd8aaf7e33ee3852c2092aca03c4b78",
    "task_writer_sha256": "f834f3fcc9dafcdf31db16ad4f52cd232c17162dc1711bdba112c2cac8a30d29",
}
_P01_PATHS = frozenset(
    {
        ".codearbiter/specs/academy-feature.md",
        ".codearbiter/plans/academy-feature.md",
        ".codearbiter/open-tasks.md",
        "tests/test_cli.py",
        "workshop_queue/cli.py",
    }
)


def _p01_regular_blob(root: Path, ref: str, path: str) -> bytes | None:
    entry = run_git(root, ["ls-tree", ref, "--", path], check=False).stdout.strip()
    if not entry.startswith("100644 blob ") or not entry.endswith("\t" + path):
        return None
    return _git_blob(root, ref, path)


def _p01_one_commit(root: Path, attempt: _Attempt) -> str | None:
    commits = tuple(
        line for line in run_git(
            root, ["rev-list", "--reverse", f"{attempt.prepared}..{attempt.head}"], check=False
        ).stdout.splitlines() if line
    )
    if len(commits) != 1 or commits[0] != attempt.head:
        return None
    parents = run_git(root, ["rev-list", "--parents", "-n", "1", attempt.head], check=False).stdout.split()
    if parents != [attempt.head, attempt.prepared] or set(_commit_paths(root, attempt.head)) != _P01_PATHS:
        return None
    return attempt.head


def _p01_board_transition(root: Path, attempt: _Attempt, board: str, task_id: str) -> bool:
    before, after = _p01_regular_blob(root, attempt.prepared, board), _p01_regular_blob(root, attempt.head, board)
    if before is None or after is None:
        return False
    try:
        before_lines = before.decode("utf-8").splitlines(keepends=True)
        after_lines = after.decode("utf-8").splitlines(keepends=True)
    except UnicodeDecodeError:
        return False
    if len(before_lines) != len(after_lines):
        return False
    changed = [(old.rstrip("\r\n"), new.rstrip("\r\n")) for old, new in zip(before_lines, after_lines, strict=True) if old != new]
    if len(changed) != 1:
        return False
    old, new = changed[0]
    match = re.fullmatch(rf"- \[ \] {re.escape(task_id)} - (?P<body>.+)", old)
    started = re.fullmatch(rf"- \[~\] {re.escape(task_id)} - (?P<body>.+?)  \(started (?P<date>\d{{4}}-\d{{2}}-\d{{2}})\)", new)
    commit_date = run_git(root, ["show", "-s", "--format=%as", attempt.head], check=False).stdout.strip()
    return bool(match and started and match.group("body") == started.group("body") and started.group("date") == commit_date)


def _p01_exact_regression(prepared: bytes | None, final: bytes | None) -> bool:
    if prepared is None or final is None:
        return False
    expected = ast.parse(
        "def test_report_json_counts_open_and_claimed_as_unresolved(self) -> None:\n"
        "    result = self.run_cli_for(self.data_root / 'p01-unresolved-tickets.json', 'report', '--format', 'json')\n"
        "    self.assertEqual(result.returncode, 0, result.stderr)\n"
        "    self.assertEqual(json.loads(result.stdout), {'claimed': 1, 'completed': 1, 'open': 1, 'unresolved': 2})\n"
    ).body[0]
    try:
        prepared_tree = ast.parse(prepared.decode("utf-8"))
        final_tree = ast.parse(final.decode("utf-8"))
    except (UnicodeDecodeError, SyntaxError):
        return False
    classes = [item for item in final_tree.body if isinstance(item, ast.ClassDef) and item.name == "WorkshopQueueCliTests"]
    if len(classes) != 1:
        return False
    methods = [item for item in classes[0].body if isinstance(item, ast.FunctionDef) and item.name == expected.name]
    if len(methods) != 1 or ast.dump(methods[0], include_attributes=False) != ast.dump(expected, include_attributes=False):
        return False
    final_copy = copy.deepcopy(final_tree)
    final_class = next(item for item in final_copy.body if isinstance(item, ast.ClassDef) and item.name == "WorkshopQueueCliTests")
    final_class.body = [item for item in final_class.body if not (isinstance(item, ast.FunctionDef) and item.name == expected.name)]
    return ast.dump(final_copy, include_attributes=False) == ast.dump(prepared_tree, include_attributes=False)


def _p01_exact_repair(prepared: bytes | None, final: bytes | None) -> bool:
    if prepared is None or final is None:
        return False
    expected = ast.parse(
        "counts['unresolved'] = (counts[TicketStatus.OPEN.value] + counts[TicketStatus.CLAIMED.value])"
    ).body[0]
    try:
        prepared_tree = ast.parse(prepared.decode("utf-8"))
        final_tree = ast.parse(final.decode("utf-8"))
    except (UnicodeDecodeError, SyntaxError):
        return False
    functions = [item for item in final_tree.body if isinstance(item, ast.FunctionDef) and item.name == "_write_report"]
    if len(functions) != 1:
        return False
    candidates = [
        index
        for index, item in enumerate(functions[0].body)
        if ast.dump(item, include_attributes=False) == ast.dump(expected, include_attributes=False)
    ]
    expected_counts = ast.parse(
        "counts = {status.value: sum(ticket.status is status for ticket in tickets) for status in TicketStatus}"
    ).body[0]
    if (
        len(candidates) != 1
        or candidates[0] == 0
        or ast.dump(functions[0].body[candidates[0] - 1], include_attributes=False)
        != ast.dump(expected_counts, include_attributes=False)
    ):
        return False
    final_copy = copy.deepcopy(final_tree)
    final_function = next(item for item in final_copy.body if isinstance(item, ast.FunctionDef) and item.name == "_write_report")
    del final_function.body[candidates[0]]
    return ast.dump(final_copy, include_attributes=False) == ast.dump(prepared_tree, include_attributes=False)


def _p01_sections(text: str, headings: tuple[str, ...]) -> tuple[str, dict[str, str]] | None:
    if len(text.encode("utf-8")) > 16_384 or len(text.splitlines()) > 160:
        return None
    lines = text.splitlines()
    if not lines or not re.fullmatch(r"# [^#\r\n]{1,120}", lines[0]):
        return None
    found = [index for index, line in enumerate(lines) if line.startswith("## ")]
    if [lines[index][3:] for index in found] != list(headings):
        return None
    if any(line.startswith("#") and not line.startswith("## ") for line in lines[1:]):
        return None
    sections: dict[str, str] = {}
    for index, start in enumerate(found):
        end = found[index + 1] if index + 1 < len(found) else len(lines)
        sections[lines[start][3:]] = "\n".join(lines[start + 1:end]).strip()
    return lines[0][2:].strip(), sections


def _p01_normalize_markdown(text: str) -> str:
    return " ".join(text.replace("`", "").split()).casefold()


def _p01_private_text(text: str) -> bool:
    return (
        any(
            (ord(character) < 32 and character not in {"\r", "\n", "\t"})
            or ord(character) == 127
            for character in text
        )
        or bool(
            re.search(
                r"(?i)(?:\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b|"
                r"https?://[^/\s:@]+:[^@\s/]+@|"
                r"\b(?:ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9]{20,}|AKIA[A-Z0-9]{16})\b|"
                r"-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----|"
                r"\b(?:secret|password|token|api[_-]?key)\s*[:=]|"
                r"(?<![:\w/])/(?:[^\s/]+/)*[^\s/]+|"
                r"(?:[A-Za-z]:\\|\\\\))",
                text,
            )
        )
    )


def _p01_source_identity(value: object) -> bool:
    if not isinstance(value, dict) or set(value) != set(_P01_SOURCE_IDENTITY):
        return False
    if type(value.get("schema_version")) is not int:
        return False
    if any(not isinstance(item, str) or _p01_private_text(item) for key, item in value.items() if key != "schema_version"):
        return False
    return value == _P01_SOURCE_IDENTITY


def _p01_timestamp(value: str) -> datetime | None:
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return None


def _p01_criterion(text: str, *, first: bool) -> bool:
    value = _p01_normalize_markdown(text)
    if " or " in value or " either " in value or " alternatively " in value:
        return False
    required = (
        ("json", "report", "integer", "unresolved", "equal", "open", "claimed"),
        ("integer", "open", "claimed", "completed", "exact", "completed", "unresolved"),
    )[int(not first)]
    if not all(token in value for token in required):
        return False
    if first:
        return "open + claimed" in value
    return "completed tickets do not contribute to unresolved" in value


def _p01_parse_criteria(section: str) -> tuple[str, str] | None:
    lines = [line.strip() for line in section.splitlines() if line.strip()]
    if len(lines) != 2:
        return None
    parsed: list[str] = []
    for index, line in enumerate(lines, start=1):
        match = re.fullmatch(rf"{index}\.\s+(.+)", line)
        if not match or not _p01_criterion(match.group(1), first=index == 1):
            return None
        parsed.append(match.group(1))
    return tuple(parsed)  # type: ignore[return-value]


def _p01_parse_table(section: str) -> list[list[str]] | None:
    rows = [line.strip() for line in section.splitlines() if line.strip()]
    if len(rows) != 4 or not all(row.startswith("|") and row.endswith("|") for row in rows):
        return None
    parsed = [[cell.strip() for cell in row[1:-1].split("|")] for row in rows]
    if any(len(row) != 7 for row in parsed):
        return None
    if parsed[0] != ["ID", "Path(s)", "Verification", "Maps to", "Covers", "Depends on", "Status"]:
        return None
    if any(not re.fullmatch(r"-+", cell) for cell in parsed[1]):
        return None
    return parsed[2:]


def _p01_spec_and_plan(spec: bytes | None, plan: bytes | None) -> bool:
    if spec is None or plan is None:
        return False
    try:
        spec_text, plan_text = spec.decode("utf-8"), plan.decode("utf-8")
    except UnicodeDecodeError:
        return False
    if _p01_private_text(spec_text) or _p01_private_text(plan_text):
        return False
    spec_parts = _p01_sections(spec_text, ("Problem", "Scope", "Acceptance criteria", "Open questions"))
    plan_parts = _p01_sections(plan_text, ("Acceptance criteria ledger", "Tasks", "MVP slice"))
    if spec_parts is None or plan_parts is None:
        return False
    _, spec_sections = spec_parts
    _, plan_sections = plan_parts
    problem = _p01_normalize_markdown(spec_sections["Problem"])
    scope = _p01_normalize_markdown(spec_sections["Scope"])
    criteria = _p01_parse_criteria(spec_sections["Acceptance criteria"])
    if criteria is None or not all(token in problem for token in ("workshop", "queue", "json", "report", "unresolved")):
        return False
    if not all(token in scope for token in ("json", "report", "workshop_queue/cli.py", "tests/test_cli.py", "text-output", "lifecycle", "storage", "dependencies", "network", "credentials", "real", "personal", "data")):
        return False
    if _p01_normalize_markdown(spec_sections["Open questions"]) not in {"none", "none."}:
        return False
    lower_all = _p01_normalize_markdown(spec_text + "\n" + plan_text)
    if any(token in lower_all for token in ("[confirm-", "[needs-triage]", "approved by", "approval id", "approved-plan")):
        return False
    if re.search(
        r"(?im)^\s*(?:status|approval(?:\s+id)?|event)\s*:\s*(?:approved|accepted|confirmed|complete|passed|granted)\b",
        spec_text + "\n" + plan_text,
    ):
        return False
    ledger = [line.strip() for line in plan_sections["Acceptance criteria ledger"].splitlines() if line.strip()]
    expected_ledger = [f"- AC-01: {criteria[0]}", f"- AC-02: {criteria[1]}"]
    if len(ledger) != 2 or any(_p01_normalize_markdown(actual) != _p01_normalize_markdown(expected) for actual, expected in zip(ledger, expected_ledger, strict=True)):
        return False
    tasks = _p01_parse_table(plan_sections["Tasks"])
    if tasks is None:
        return False
    first, second = tasks
    if first != ["T-01", "tests/test_cli.py", first[2], "AC-01, AC-02", "AC-01, AC-02", "none", "ACCEPTED"]:
        return False
    if "focused unresolved-summary test" not in _p01_normalize_markdown(first[2]):
        return False
    if second != ["T-02", "workshop_queue/cli.py", second[2], "AC-01, AC-02", "AC-01, AC-02", "T-01", "ACCEPTED"]:
        return False
    if [entry.strip() for entry in second[2].split(";")] != [
        "focused unresolved-summary test",
        "python -m unittest discover -v",
        "python -m compileall workshop_queue tests",
    ]:
        return False
    return _p01_normalize_markdown(plan_sections["MVP slice"]) == "t-01 through t-02"


def _p01_json(value: bytes) -> object | None:
    def reject_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, item in pairs:
            if key in result:
                raise ValueError("duplicate key")
            result[key] = item
        return result

    try:
        return json.loads(value.decode("utf-8"), object_pairs_hook=reject_duplicates, parse_constant=lambda _: (_ for _ in ()).throw(ValueError("non-finite")))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return None


def _p01_fixture_models(value: bytes) -> tuple[dict[str, int], dict[str, int]] | None:
    fixture = _p01_json(value)
    if not isinstance(fixture, list) or len(fixture) != 3:
        return None
    expected_keys = {"id", "title", "description", "status", "created_at", "claimed_by", "claimed_at", "completed_at", "resolution"}
    statuses: list[str] = []
    identifiers: set[str] = set()
    for item in fixture:
        if not isinstance(item, dict) or set(item) != expected_keys:
            return None
        if any(isinstance(value, str) and _p01_private_text(value) for value in item.values()):
            return None
        identifier, status = item.get("id"), item.get("status")
        if not isinstance(identifier, str) or not re.fullmatch(r"RQ-P01-[0-9]{3}", identifier) or identifier in identifiers:
            return None
        identifiers.add(identifier)
        if not isinstance(status, str) or status not in {"open", "claimed", "completed"}:
            return None
        if not all(isinstance(item.get(key), str) and 1 <= len(item[key]) <= 160 for key in ("title", "description", "created_at")):
            return None
        if not re.fullmatch(r"2026-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", item["created_at"]):
            return None
        created_at = _p01_timestamp(item["created_at"])
        if created_at is None:
            return None
        claimed = status in {"claimed", "completed"}
        completed = status == "completed"
        if (claimed != isinstance(item.get("claimed_by"), str) or claimed != isinstance(item.get("claimed_at"), str) or completed != isinstance(item.get("completed_at"), str) or completed != isinstance(item.get("resolution"), str)):
            return None
        if claimed and (not item["claimed_by"] or not re.fullmatch(r"2026-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", item["claimed_at"])):
            return None
        claimed_at = _p01_timestamp(item["claimed_at"]) if claimed else None
        if claimed and (claimed_at is None or claimed_at < created_at):
            return None
        if completed and (not item["resolution"] or not re.fullmatch(r"2026-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", item["completed_at"])):
            return None
        completed_at = _p01_timestamp(item["completed_at"]) if completed else None
        if completed and (completed_at is None or claimed_at is None or completed_at < claimed_at):
            return None
        if not claimed and any(item[key] is not None for key in ("claimed_by", "claimed_at", "completed_at", "resolution")):
            return None
        if claimed and not completed and any(item[key] is not None for key in ("completed_at", "resolution")):
            return None
        statuses.append(status)
    if statuses != ["open", "claimed", "completed"]:
        return None
    prepared = {"open": 1, "claimed": 1, "completed": 1}
    return prepared, {**prepared, "unresolved": 2}


def _p01_prepared_defect(value: bytes | None) -> bool:
    if value is None:
        return False
    expected = ast.parse("counts = {status.value: sum(ticket.status is status for ticket in tickets) for status in TicketStatus}").body[0]
    try:
        tree = ast.parse(value.decode("utf-8"))
    except (UnicodeDecodeError, SyntaxError):
        return False
    functions = [item for item in tree.body if isinstance(item, ast.FunctionDef) and item.name == "_write_report"]
    if len(functions) != 1 or not functions[0].body or ast.dump(functions[0].body[0], include_attributes=False) != ast.dump(expected, include_attributes=False):
        return False
    return not any(
        isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Subscript) and isinstance(target.value, ast.Name) and target.value.id == "counts" and isinstance(target.slice, ast.Constant) and target.slice.value == "unresolved" for target in node.targets)
        for node in ast.walk(functions[0])
    )


_P03_ADR = ".codearbiter/decisions/0004-academy-lab.md"
_P03_LOG = ".codearbiter/decisions/decision-log.md"
_P03_TITLE = "Choose the Workshop Queue summary-format boundary"
_P03_CHOICES = (
    "Use stable text for Workshop Queue summaries.",
    "Use structured JSON for Workshop Queue summaries.",
)


def _p03_utf8(blob: bytes | None) -> str | None:
    if blob is None:
        return None
    try:
        return blob.decode("utf-8", "strict")
    except UnicodeDecodeError:
        return None


def _p03_front_matter(text: str) -> tuple[dict[str, str], str] | None:
    match = re.fullmatch(r"---\r?\n(?P<fields>(?:[^\r\n]+\r?\n)+)---\r?\n\r?\n(?P<body>.*)", text, re.DOTALL)
    if match is None:
        return None
    fields: dict[str, str] = {}
    for line in match.group("fields").splitlines():
        key, marker, value = line.partition(": ")
        if not marker or not key or key in fields or not re.fullmatch(r"[a-z-]+", key):
            return None
        if not value or value[:1] in "'\"|>" or value.endswith(" "):
            return None
        fields[key] = value
    return fields, match.group("body")


def _p03_sections(body: str) -> dict[str, str] | None:
    h1 = f"# ADR-0004 — {_P03_TITLE}"
    h1_matches = list(re.finditer(r"(?m)^# (?P<name>[^\r\n]+)\r?$", body))
    if len(h1_matches) != 1 or h1_matches[0].group("name") != h1[2:]:
        return None
    if re.match(rf"^{re.escape(h1)}\r?\n", body) is None:
        return None
    matches = list(re.finditer(r"(?m)^## (?P<name>[^\r\n]+)\r?$", body))
    required = ("Status", "Context", "Decision", "Alternatives considered", "Consequences", "Risks")
    if tuple(match.group("name") for match in matches) != required:
        return None
    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        sections[match.group("name")] = body[match.end() : end].strip()
    return sections


def _p03_parse_adr(blob: bytes | None, author: str, date: str) -> tuple[str, str] | None:
    text = _p03_utf8(blob)
    if text is None:
        return None
    parsed = _p03_front_matter(text)
    if parsed is None:
        return None
    fields, body = parsed
    expected = {
        "status": "accepted", "date": date, "title": _P03_TITLE,
        "decided-by": author, "supersedes": "none", "governs": "workshop_queue/cli.py",
    }
    if fields != expected:
        return None
    sections = _p03_sections(body)
    if sections is None or sections["Status"] != "Accepted":
        return None
    if not all(phrase.casefold() in sections["Context"].casefold() for phrase in ("stable text", "structured json")):
        return None
    if not all(phrase.casefold() in sections["Alternatives considered"].casefold() for phrase in ("stable text", "structured json")):
        return None
    choices = tuple(choice for choice in _P03_CHOICES if re.search(rf"(?m)^{re.escape(choice)}$", sections["Decision"]))
    if len(choices) != 1 or sections["Decision"].strip() != choices[0]:
        return None
    rejected = _P03_CHOICES[1] if choices[0] == _P03_CHOICES[0] else _P03_CHOICES[0]
    consequence = sections["Consequences"].casefold()
    chosen_format = "stable text" if choices[0] == _P03_CHOICES[0] else "structured json"
    rejected_format = "structured json" if chosen_format == "stable text" else "stable text"
    cost = r"(?:costs?|trade-?off|risks?|drawbacks?|expenses?|burdens?|overhead|version(?:ing)?)"
    negated_cost = re.compile(
        rf"(?:\b(?:no|without|not|never|zero)\b.{{0,24}}{cost}|{cost}.{{0,24}}\b(?:no|without|not|never|zero)\b)",
        re.IGNORECASE,
    )
    affirmative_cost = re.compile(
        rf"{re.escape(rejected_format)}.{{0,100}}{cost}|{cost}.{{0,100}}{re.escape(rejected_format)}",
        re.IGNORECASE,
    )
    sentences = re.split(r"(?<=[.!?])\s+", consequence)
    if chosen_format not in consequence or not any(
        affirmative_cost.search(sentence) and not negated_cost.search(sentence)
        for sentence in sentences
    ):
        return None
    return choices[0], text


def _p03_parse_log(blob: bytes | None, prefix: bytes, author: str, date: str, choice: str) -> bool:
    if blob is None or not prefix or not blob.startswith(prefix):
        return False
    suffix = _p03_utf8(blob[len(prefix) :])
    if suffix is None:
        return False
    header = "## DECISION-0004 — ADR-0004 — " + _P03_TITLE
    nl = r"\r?\n"
    body = r"(?P<{name}>[^\r\n](?:(?!\r?\n(?:#+ |\*\*)).)*?)"
    pattern = (
        rf"{re.escape(header)}{nl}{nl}"
        rf"\*\*Date:\*\* {re.escape(date)}{nl}"
        rf"\*\*Status:\*\* accepted{nl}"
        rf"\*\*Supersedes:\*\* none{nl}"
        rf"\*\*Decided by:\*\* {re.escape(author)}{nl}"
        rf"\*\*Decision category:\*\* architecture{nl}"
        rf"\*\*Artifact-section-hash:\*\* n/a{nl}{nl}"
        rf"## Variance summary{nl}{nl}{body.format(name='variance')}{nl}{nl}"
        rf"## Decision{nl}{nl}{re.escape(choice)}{nl}{nl}"
        rf"## SMARTS rationale{nl}{nl}{body.format(name='smarts')}{nl}{nl}"
        rf"## Implementation implication{nl}{nl}{body.format(name='implication')}{nl}"
    )
    if "Re-evaluation trigger" in suffix or "Resolves same-level conflict between" in suffix:
        return False
    match = re.fullmatch(pattern, suffix, re.DOTALL)
    return bool(match and "Status type: open-decision-closure" in match.group("variance"))


def _p03_accepted_adr(root: Path, attempt: _Attempt, adr: str, decision_log: str) -> bool:
    """Validate P03 from immutable blobs and its narrow linear learner range."""
    if adr != _P03_ADR or decision_log != _P03_LOG:
        return False
    if run_git(root, ["status", "--porcelain", "--untracked-files=all"], check=False).stdout:
        return False
    try:
        author = commit_author_name(root, attempt.prepared)
    except AttributionError:
        return False
    commits = tuple(line for line in run_git(root, ["rev-list", "--reverse", f"{attempt.prepared}..{attempt.head}"], check=False).stdout.splitlines() if _SHA40.fullmatch(line))
    if len(commits) not in {1, 2} or commits[-1] != attempt.head:
        return False
    parent = attempt.prepared
    for commit in commits:
        if run_git(root, ["rev-list", "--parents", "-n", "1", commit], check=False).stdout.split() != [commit, parent]:
            return False
        parent = commit
    changed = [set(_commit_paths(root, commit)) for commit in commits]
    if set().union(*changed) != {adr, decision_log}:
        return False
    adr_commits = _path_commits(root, attempt.prepared, attempt.head, adr)
    log_commits = _path_commits(root, attempt.prepared, attempt.head, decision_log)
    if len(adr_commits) != 1 or len(log_commits) != 1 or (len(commits) == 2 and commits.index(adr_commits[0]) >= commits.index(log_commits[0])):
        return False
    date_value = run_git(root, ["show", "-s", "--format=%aI", adr_commits[0]], check=False).stdout.strip()
    date_match = re.fullmatch(r"(\d{4}-\d{2}-\d{2})T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}", date_value)
    if date_match is None:
        return False
    choice = _p03_parse_adr(_git_blob(root, attempt.head, adr), author, date_match.group(1))
    prepared_log = _git_blob(root, attempt.prepared, decision_log)
    return bool(prepared_log is not None and choice and _p03_parse_log(_git_blob(root, attempt.head, decision_log), prepared_log, author, date_match.group(1), choice[0]))


_P04_REVIEW = ".codearbiter/reports/academy/P04-dependency-review.md"
_P04_LOCK = "requirements.lock"
_P04_WRAPPER = ".codearbiter/reports/academy/P04-approved-dependency.lock.json"
_P04_SECTIONS = (
    "Candidate", "Provenance", "License", "Maintenance", "Known vulnerabilities",
    "Supply chain", "Compatibility", "Alternatives", "SMARTS", "Decision",
)
_P04_LOCK_BYTES = (
    b"python-dateutil==2.9.0.post0 --hash=sha256:a8b2bc7bffae282281c8140a97d3aa9c14da0b136dfe83f850eea9a5f7470427 # artifact=python_dateutil-2.9.0.post0-py2.py3-none-any.whl\n"
    b"six==1.17.0 --hash=sha256:4721f391ed90541fddacab5acf947aa0d3dc7d27b2e1e8eda2be8970586c3274 # artifact=six-1.17.0-py2.py3-none-any.whl\n"
)
_P04_WRAPPER_BYTES = (
    b'{"schema_version":1,"name":"python-dateutil","version":"2.9.0.post0","artifact":"python_dateutil-2.9.0.post0-py2.py3-none-any.whl","sha256":"a8b2bc7bffae282281c8140a97d3aa9c14da0b136dfe83f850eea9a5f7470427","install_policy":"later-only-after-review"}\n'
)
_P04_HEADER_PREFIX = (
    "# P04 Dependency Review - python-dateutil==2.9.0.post0\n"
    "Academy-Schema-Version: 1\n"
)
_P04_HEADER_SUFFIX = (
    "Candidate: python-dateutil==2.9.0.post0\n"
    "Candidate-Artifact: python_dateutil-2.9.0.post0-py2.py3-none-any.whl\n"
    "Candidate-SHA256: a8b2bc7bffae282281c8140a97d3aa9c14da0b136dfe83f850eea9a5f7470427\n"
    "Closure-Requirement: six>=1.5\n"
    "Closure-Package: six==1.17.0\n"
    "Closure-Artifact: six-1.17.0-py2.py3-none-any.whl\n"
    "Closure-SHA256: 4721f391ed90541fddacab5acf947aa0d3dc7d27b2e1e8eda2be8970586c3274\n"
    "Install-Policy: no-install-in-p04\n"
)


def _p04_review_text(blob: bytes | None, project_digest: str) -> str | None:
    if blob is None or blob.startswith(b"\xef\xbb\xbf") or b"\r" in blob:
        return None
    try:
        text = blob.decode("utf-8")
    except UnicodeDecodeError:
        return None
    required_header = _P04_HEADER_PREFIX + f"Project-SHA256: {project_digest}\n" + _P04_HEADER_SUFFIX + "\n"
    if not text.startswith(required_header):
        return None
    body = text[len(required_header) :]
    all_headings = list(re.finditer(r"(?m)^## ([^\n]+)\n", body))
    if (
        [match.group(1) for match in all_headings] != list(_P04_SECTIONS)
        or any(not body[match.end() :].startswith("\n") for match in all_headings)
    ):
        return None
    matches = list(re.finditer(r"(?m)^## ([^\n]+)\n\n", body))
    if [match.group(1) for match in matches] != list(_P04_SECTIONS) or not matches or matches[0].start() != 0:
        return None
    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        content = body[match.end() : end].strip()
        if not content:
            return None
        sections[match.group(1)] = content
    required_words = {
        "Candidate": (
            "python-dateutil==2.9.0.post0", "python_dateutil-2.9.0.post0-py2.py3-none-any.whl",
            "six>=1.5", "six==1.17.0", "six-1.17.0-py2.py3-none-any.whl", "complete",
        ),
        "Provenance": (
            "PyPI", "dateutil", "dateutil/dateutil", "benjaminp/six", "filename", "hash", "bind",
        ),
        "License": (
            "Apache-2.0 OR BSD-3-Clause", "MIT", "python_dateutil-2.9.0.post0.LICENSE",
            "ba00f51a0d92823b5a1cde27d8b5b9d2321e67ed8da9bc163eff96d5e17e577e",
            "six-1.17.0.LICENSE", "4375ba20e2b9c6c4e7cad2940a628fd90e95cc3d50ee92aae755715d8ba1fbd0",
            "Apache-2.0.txt", "cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30",
        ),
        "Maintenance": ("Frozen 2026-07-31 review snapshot", "not current truth"),
        "Known vulnerabilities": ("Frozen 2026-07-31 review snapshot", "not a guarantee"),
        "Supply chain": ("pure-Python", "no sdist", "no resolver", "no install"),
        "Compatibility": ("Python 3.10+", "Requires-Python"),
        "Alternatives": ("datetime.strptime", "finite", "length", "timezone", "default", "fail-closed", "trailing"),
    }
    if any(any(word not in sections[name] for word in words) for name, words in required_words.items()):
        return None
    table = [line.strip() for line in sections["SMARTS"].splitlines()]
    if len(table) != 8 or table[:2] != ["| Lens | Bounded stdlib | Two-wheel closure |", "| --- | --- | --- |"]:
        return None
    lenses = ("Scalable", "Maintainable", "Available", "Reliable", "Testable", "Securable")
    allowed = ("Strong.", "Adequate.", "Weak.", "Indifferent.")
    for line, lens in zip(table[2:], lenses, strict=True):
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) != 3 or cells[0] != lens or any(not cell.startswith(allowed) or len(cell.split()) > 25 for cell in cells[1:]):
            return None
    decision_body = sections["Decision"].casefold()
    decision = sections["Decision"].splitlines()[-1]
    if decision == "Decision: reject":
        return "reject" if (
            "bounded stdlib parser is selected" in decision_body
            and "broader parsing surface is required" not in decision_body
        ) else None
    if decision == "Decision: accept":
        return "accept" if (
            "broader parsing surface is required" in decision_body
            and "install is deferred" in decision_body
            and "bounded stdlib parser is selected" not in decision_body
        ) else None
    return None


def _p04_prepared_candidates(root: Path, prepared: str) -> bool:
    names = (
        "candidate-set.json", "python_dateutil-2.9.0.post0-py2.py3-none-any.whl",
        "six-1.17.0-py2.py3-none-any.whl", "python_dateutil-2.9.0.post0.LICENSE",
        "six-1.17.0.LICENSE", "Apache-2.0.txt",
    )
    expected_paths = {f"{P04_CANDIDATE_ROOT}/{name}" for name in names}
    listed_paths = {
        line for line in run_git(root, ["ls-tree", "-r", "--name-only", prepared, "--", P04_CANDIDATE_ROOT], check=False).stdout.splitlines()
        if line
    }
    if listed_paths != expected_paths:
        return False
    blobs = {name: _git_blob(root, prepared, f"{P04_CANDIDATE_ROOT}/{name}") for name in names}
    if any(value is None for value in blobs.values()):
        return False
    try:
        validate_p04_candidate_blobs({name: value for name, value in blobs.items() if value is not None})
    except CandidateDataError:
        return False
    return True


def _p04_linear_range(root: Path, attempt: _Attempt) -> tuple[str, ...] | None:
    commits = tuple(line for line in run_git(root, ["rev-list", "--reverse", f"{attempt.prepared}..{attempt.head}"], check=False).stdout.splitlines() if _SHA40.fullmatch(line))
    if not commits or commits[-1] != attempt.head:
        return None
    parent = attempt.prepared
    for commit in commits:
        if run_git(root, ["rev-list", "--parents", "-n", "1", commit], check=False).stdout.split() != [commit, parent]:
            return None
        parent = commit
    return commits


def _p04_projects_match(prepared: bytes, head: bytes) -> bool:
    try:
        before = tomllib.loads(prepared.decode("utf-8"))
        after = tomllib.loads(head.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError):
        return False
    expected = copy.deepcopy(before)
    project = expected.get("project")
    if not isinstance(project, dict):
        return False
    project["dependencies"] = ["python-dateutil==2.9.0.post0"]
    return after == expected


def _p04_dependency_review(root: Path, attempt: _Attempt, review: str, project: str) -> bool:
    """Validate P04's immutable candidate evidence and review-before-adoption history."""
    if review != _P04_REVIEW or project != "pyproject.toml":
        return False
    if run_git(root, ["status", "--porcelain", "--untracked-files=all"], check=False).stdout or not _p04_prepared_candidates(root, attempt.prepared):
        return False
    prepared_project = _git_blob(root, attempt.prepared, project)
    head_project = _git_blob(root, attempt.head, project)
    decision = _p04_review_text(_git_blob(root, attempt.head, review), _raw_digest(prepared_project or b""))
    commits = _p04_linear_range(root, attempt)
    if prepared_project is None or head_project is None or decision is None or commits is None:
        return False
    if decision == "reject":
        return bool(
            len(commits) == 1
            and set(_commit_paths(root, commits[0])) == {review}
            and head_project == prepared_project
            and _git_blob(root, attempt.head, _P04_LOCK) == _git_blob(root, attempt.prepared, _P04_LOCK)
            and _git_blob(root, attempt.head, _P04_WRAPPER) == _git_blob(root, attempt.prepared, _P04_WRAPPER)
        )
    if len(commits) != 2 or set(_commit_paths(root, commits[0])) != {review}:
        return False
    if _p04_review_text(_git_blob(root, commits[0], review), _raw_digest(prepared_project)) != "accept":
        return False
    return bool(
        set(_commit_paths(root, commits[1])) == {project, _P04_LOCK, _P04_WRAPPER}
        and _p04_projects_match(prepared_project, head_project)
        and _git_blob(root, attempt.head, _P04_LOCK) == _P04_LOCK_BYTES
        and _git_blob(root, attempt.head, _P04_WRAPPER) == _P04_WRAPPER_BYTES
    )


_P07_MODEL = ".codearbiter/reports/academy/P07-threat-model.md"
_P07_TARGET = "academy_engine/paths.py"
_P07_TARGET_BLOB = "b36801add4eb375f796d1107ee63dd604d08a034"
_P07_TARGET_SHA256 = "e40a7655ce6ba6cde58a91ae10a714f10046c055ac90dcbc58f0696c39133a5d"
_P07_SECTION_PATTERN = re.compile(
    r"\A# P07 Threat Model - Archive import containment boundary\n\n"
    r"## Scope\n(?P<scope>[^\n]+(?:\n[^\n]+){0,5})\n\n"
    r"## STRIDE findings\n(?P<stride>[^\n]+(?:\n[^\n]+){7})\n\n"
    r"## Recommended controls before implementation\n(?P<controls>[^\n]+(?:\n[^\n]+){2})\n\n"
    r"## Clearance\n(?P<clearance>[^\n]+)\n\n"
    r"## Academy Target-SHA256/identity binding\n(?P<binding>[^\n]+(?:\n[^\n]+){3})\n\Z"
)
_P07_CONTROLS = (
    "- Keep destination resolution under the selected repository root before creating or copying a file.",
    "- Reject absolute, traversal, symlink, and Windows reparse-point ancestors in archive destinations.",
    "- Fail closed on a different drive or an unrepresentable containment path before any write.",
)
_P07_BINDING = (
    "Academy-Target-Path: academy_engine/paths.py",
    "Academy-Target-Prepared-Blob: b36801add4eb375f796d1107ee63dd604d08a034",
    "Academy-Target-Head-Blob: b36801add4eb375f796d1107ee63dd604d08a034",
    "Academy-Target-SHA256: e40a7655ce6ba6cde58a91ae10a714f10046c055ac90dcbc58f0696c39133a5d",
)


def _p07_sections(raw: bytes | None) -> dict[str, str] | None:
    if (
        raw is None
        or not raw
        or len(raw) > 12 * 1024
        or raw.startswith(b"\xef\xbb\xbf")
        or b"\r" in raw
        or b"<" in raw
        or b">" in raw
        or any((byte < 32 and byte != 10) or byte > 126 for byte in raw)
        or not raw.endswith(b"\n")
        or raw.endswith(b"\n\n")
    ):
        return None
    try:
        text = raw.decode("utf-8", "strict")
    except UnicodeDecodeError:
        return None
    match = _P07_SECTION_PATTERN.fullmatch(text)
    return match.groupdict() if match is not None else None


def _p07_table_cells(line: str) -> tuple[str, ...] | None:
    if not line.startswith("| ") or not line.endswith(" |"):
        return None
    cells = tuple(line[2:-2].split(" | "))
    return cells if len(cells) == 5 and all(cells) else None


_P07_FIRST_PERSON = frozenset({"i", "we"})
_P07_STRONG_SUBJECTS = frozenset(
    {
        "checker",
        "command",
        "host",
        "tool",
        "skill",
        "route",
        "verifier",
        "host-tool",
    }
)
_P07_HYPOTHETICAL = frozenset({"could", "may", "might", "would", "can", "should", "will", "planned", "proposed", "potential", "risk", "threat", "if"})
_P07_UNCERTAIN = frozenset({"no", "not", "never", "cannot", "without", "unproven", "unknown"})
_P07_THREAT_MARKERS = frozenset({"malicious", "untrusted", "risk", "threat", "threats", "threatens", "threatened", "threatening"})
_P07_THREAT_ANCHORS = frozenset({"archive", "path", "destination", "traversal", "reparse", "containment"})
_P07_SCOPE_HYPOTHETICAL = frozenset(
    {
        "could", "may", "might", "would", "can", "should", "will",
        "planned", "proposed", "potential", "if",
    }
) | _P07_UNCERTAIN
_P07_CONTROL_DENIAL = frozenset(
    {
        "block", "blocked", "deny", "denied", "prevent", "prevented",
        "reject", "rejected", "stop", "stopped",
    }
)
_P07_THREAT_RELATION_MARKERS = frozenset(
    {"can", "cannot", "could", "may", "might", "should", "will", "would"}
)
_P07_CATEGORY_WORDS = {
    "S": frozenset(
        {
            "authenticate", "authenticated", "authentication", "identity",
            "impersonate", "impersonation", "principal", "provenance",
            "spoof", "spoofing", "trust", "trusted",
        }
    ),
    "T": frozenset(
        {
            "alter", "change", "corrupt", "corruption", "integrity",
            "modification", "modify", "overwrite", "tamper", "tampering",
            "traversal",
        }
    ),
    "R": frozenset(
        {
            "accountability", "attribute", "attribution", "audit", "dispute",
            "log", "logging", "provenance", "repudiate", "repudiation",
            "trace", "traceability",
        }
    ),
    "I": frozenset(
        {
            "confidentiality", "disclose", "disclosure", "expose", "exposure",
            "leak", "leakage", "location", "reveal", "sensitive",
        }
    ),
    "D": frozenset(
        {
            "availability", "consume", "consumption", "denial", "excessive",
            "exhaust", "exhaustion", "flood", "oversized", "quota", "resource",
            "starvation", "starve",
        }
    ),
    "E": frozenset(
        {
            "authority", "authorization", "elevate", "elevation", "escalate",
            "escalation", "permission", "privilege", "privileged", "reparse",
            "symlink",
        }
    ),
}
_P07_CATEGORY_RELATIONS = {
    "S": frozenset(
        {
            "authenticate", "authenticated", "impersonate", "impersonates",
            "mistake", "mistaken", "spoof", "spoofs", "suggest", "suggests",
            "trust", "trusted",
        }
    ),
    "T": frozenset(
        {
            "alter", "alters", "corrupt", "corrupts", "modify", "modifies",
            "overwrite", "overwrites", "tamper", "tampers", "traverse",
            "traverses",
        }
    ),
    "R": frozenset(
        {
            "attribute", "attributes", "audit", "audits", "dispute", "disputes",
            "log", "logs", "repudiate", "repudiates", "trace", "traces",
        }
    ),
    "I": frozenset(
        {
            "disclose", "discloses", "expose", "exposes", "leak", "leaks",
            "reveal", "reveals",
        }
    ),
    "D": frozenset(
        {
            "consume", "consumes", "deny", "denies", "exhaust", "exhausts",
            "flood", "floods", "starve", "starves",
        }
    ),
    "E": frozenset(
        {
            "cross", "crosses", "elevate", "elevates", "escalate", "escalates",
        }
    ),
}
_P07_SCOPE_REVIEW_RELATIONS = frozenset(
    {"analyzes", "assesses", "covers", "examines", "models", "reviews"}
)
_P07_SCOPE_INPUT_RELATIONS = frozenset(
    {"bounds", "checks", "handling", "resolves", "validates"}
)
_P07_SCOPE_PREWRITE_RELATIONS = frozenset(
    {
        "enforce", "enforces", "ensure", "ensures", "establish", "establishes",
        "prove", "proves", "reject", "rejects", "resolve", "resolves",
        "validate", "validates",
    }
)
_P07_CONTROL_PREFIX = re.compile(r"\A\s*(?:PRESENT|PLANNED|GAP|N/A):\s*", re.IGNORECASE)
_P07_TOKEN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*", re.IGNORECASE)
_P07_CLAUSE_BOUNDARY = re.compile(
    r"(?:\n|[,.;:!?]+|\b(?:although|and|but|however|while|yet)\b)",
    re.IGNORECASE,
)
_P07_EXACT_ROUTE = re.compile(r"(?<![a-z0-9-])ca-threat-model(?![a-z0-9-])|/ca:threat-model", re.IGNORECASE)
_P07_CONTRACTED_NEGATION = re.compile(r"\b[a-z][a-z0-9-]*n['\u2019]t\b", re.IGNORECASE)
_P07_FAIL_POLARITY = re.compile(r"\bfail(?:s|ed|ing)?\b", re.IGNORECASE)
_P07_AUTHORITY_SUBJECT = re.compile(
    r"\b(?:academy|codearbiter|host)(?:[ -]+)[a-z0-9][a-z0-9-]*\b",
    re.IGNORECASE,
)
_P07_INLINE_MARKDOWN = re.compile(
    r"(?:~~|`|\*\*|__|\[[^\]\n]*\]\([^\)\n]*\)"
    r"|(?<!\*)\*(?=\S)[^*\n]+(?<=\S)\*(?!\*)"
    r"|(?<![a-z0-9_])_(?=[a-z0-9])[^_\n]+(?<=[a-z0-9])_(?![a-z0-9_]))",
    re.IGNORECASE,
)
_P07_OUTCOME_WORDS = frozenset({"successful", "successfully"})
_P07_REPUDIATION_GAP_RELATIONS = frozenset(
    {"attribute", "attributes", "audit", "audits", "log", "logs", "trace", "traces"}
)


def _p07_clauses(text: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in _P07_CLAUSE_BOUNDARY.split(text) if part.strip())


def _p07_tokens(clause: str) -> tuple[str, ...]:
    stripped = _P07_CONTROL_PREFIX.sub("", clause, count=1)
    return tuple(match.group(0).casefold() for match in _P07_TOKEN.finditer(stripped))


def _p07_semantic_words(text: str) -> frozenset[str]:
    return frozenset(
        part
        for token in _p07_tokens(text)
        for part in token.split("-")
        if part
    )


def _p07_host_tools(tokens: tuple[str, ...]) -> tuple[tuple[int, int], ...]:
    return tuple(
        (index, index + 1)
        for index, token in enumerate(tokens)
        if token in _P07_STRONG_SUBJECTS
    )


def _p07_has_negative_polarity(text: str, words: frozenset[str]) -> bool:
    return bool(
        words & _P07_UNCERTAIN
        or _P07_CONTRACTED_NEGATION.search(text)
        or _P07_FAIL_POLARITY.search(text)
    )


def _p07_realized_outcome_claim(tokens: tuple[str, ...]) -> bool:
    outcome_indexes = tuple(
        index for index, token in enumerate(tokens) if token in _P07_OUTCOME_WORDS
    )
    return bool(
        outcome_indexes
        and (
            outcome_indexes[-1] == len(tokens) - 1
            or any(
                token.endswith(("ed", "en"))
                for token in tokens
                if token not in _P07_OUTCOME_WORDS
            )
        )
    )


def _p07_generic_threat_is_allowed(tokens: tuple[str, ...]) -> bool:
    words = {part for token in tokens for part in token.split("-") if part}
    anchored = bool(words & _P07_THREAT_ANCHORS)
    marked = any(token in _P07_HYPOTHETICAL or token in _P07_UNCERTAIN or token in _P07_THREAT_MARKERS for token in tokens)
    return anchored and marked


def _p07_invocation_claim(text: str, *, field: str) -> bool:
    if _P07_EXACT_ROUTE.search(text):
        return True
    for clause in _p07_clauses(text):
        tokens = _p07_tokens(clause)
        words = {part for token in tokens for part in token.split("-") if part}
        if words & _P07_FIRST_PERSON or _p07_realized_outcome_claim(tokens):
            return True
        if not _p07_host_tools(tokens) and not _P07_AUTHORITY_SUBJECT.search(clause):
            continue
        if field == "scope" and not words & _P07_SCOPE_HYPOTHETICAL:
            return True
        if field == "threat" and not _p07_generic_threat_is_allowed(tokens):
            return True
        if field == "control" and not (
            _p07_generic_threat_is_allowed(tokens) or words & _P07_CONTROL_DENIAL
        ):
            return True
    return False


def _p07_scope_is_affirmative(scope_lines: tuple[str, ...]) -> bool:
    semantic_lines = tuple(
        (line.casefold(), _p07_semantic_words(line)) for line in scope_lines
    )
    if any(
        _p07_has_negative_polarity(line, words)
        or _P07_INLINE_MARKDOWN.search(line)
        for line, words in semantic_lines
    ):
        return False
    input_relation = any(
        _P07_TARGET.casefold() in line
        and (
            "archive-member" in line
            or "archive member" in line
            or "overlay destination" in line
        )
        and "repository root" in line
        and bool(words & _P07_SCOPE_REVIEW_RELATIONS)
        and bool(words & _P07_SCOPE_INPUT_RELATIONS)
        for line, words in semantic_lines
    )
    prewrite_relation = any(
        "boundary" in words
        and "before" in words
        and "destination write" in line
        and ("containment" in words or {"rejects", "escape"} <= words)
        and bool(words & _P07_SCOPE_PREWRITE_RELATIONS)
        for line, words in semantic_lines
    )
    return input_relation and prewrite_relation


def _p07_threat_is_concrete(threat: str, category: str) -> bool:
    if (
        "[" in threat
        or "]" in threat
        or _P07_INLINE_MARKDOWN.search(threat)
    ):
        return False
    for clause in _p07_clauses(threat):
        words = _p07_semantic_words(clause)
        category_relations = words & _P07_CATEGORY_RELATIONS[category]
        negative_polarity = _p07_has_negative_polarity(clause.casefold(), words)
        negative_accountability_gap = bool(
            category == "R"
            and category_relations
            and category_relations <= _P07_REPUDIATION_GAP_RELATIONS
        )
        if (
            not words & _P07_THREAT_RELATION_MARKERS
            or not category_relations
            or _P07_FAIL_POLARITY.search(clause)
            or (negative_polarity and not negative_accountability_gap)
        ):
            continue
        return True
    return False


def _p07_native_conversation(sections: dict[str, str]) -> bool:
    scope_lines = tuple(sections["scope"].splitlines())
    scope = " ".join(scope_lines).casefold()
    native = "\n".join(sections[name] for name in ("scope", "stride")).casefold()
    if (
        not 1 <= len(scope_lines) <= 6
        or any(not line.strip() or len(line) > 512 for line in scope_lines)
        or any(re.match(r"^\s*#{1,6}(?:\s|$)", line) for line in scope_lines)
        or "[" in sections["scope"]
        or "]" in sections["scope"]
        or not _p07_scope_is_affirmative(scope_lines)
        or "academy-target-" in native
        or _p07_invocation_claim(sections["scope"], field="scope")
        or "invocation proof" in scope
    ):
        return False

    lines = sections["stride"].splitlines()
    if lines[0] != "| Threat | Category | Likelihood | Impact | Control |":
        return False
    separator = _p07_table_cells(lines[1])
    if separator is None or any(not re.fullmatch(r":?-{3,}:?", cell) for cell in separator):
        return False
    categories = ("S", "T", "R", "I", "D", "E")
    threats: set[str] = set()
    for line, category in zip(lines[2:], categories, strict=True):
        cells = _p07_table_cells(line)
        if cells is None:
            return False
        threat, observed, likelihood, impact, control = cells
        folded_threat = threat.casefold()
        folded_control = control.casefold()
        threat_words = _p07_semantic_words(threat)
        if (
            observed != category
            or likelihood not in {"H", "M", "L"}
            or impact not in {"H", "M", "L"}
            or not 1 <= len(threat) <= 180
            or folded_threat in threats
            or "generic" in folded_threat
            or not threat_words & _P07_THREAT_ANCHORS
            or not threat_words & _P07_CATEGORY_WORDS[category]
            or not _p07_threat_is_concrete(threat, category)
            or _p07_invocation_claim(threat, field="threat")
            or _p07_invocation_claim(control, field="control")
            or not re.match(r"^(?:PRESENT|PLANNED|GAP|N/A): .{20,200}$", control)
            or re.search(r"\bnone\b", folded_control) is not None
        ):
            return False
        threats.add(folded_threat)
    return bool(
        tuple(sections["controls"].splitlines()) == _P07_CONTROLS
        and sections["clearance"]
        in {"CLEAR TO IMPLEMENT", "BLOCKED - resolve findings first"}
    )


def _p07_target_binding(sections: dict[str, str]) -> bool:
    return tuple(sections["binding"].splitlines()) == _P07_BINDING


def _p07_report_history(root: Path, attempt: _Attempt, model: str) -> bytes | None:
    history = run_git(
        root,
        ["rev-list", "--reverse", f"{attempt.prepared}..{attempt.head}"],
        check=False,
    )
    commits = tuple(line for line in history.stdout.splitlines() if _SHA40.fullmatch(line))
    if history.returncode or commits != (attempt.head,):
        return None
    parents = run_git(
        root,
        ["rev-list", "--parents", "-n", "1", attempt.head],
        check=False,
    ).stdout.split()
    if parents != [attempt.head, attempt.prepared] or _commit_paths(root, attempt.head) != (model,):
        return None
    if not _changed_blobs_are_secret_free(root, attempt.head, [model]):
        return None
    status = run_git(
        root, ["status", "--porcelain", "--untracked-files=all"], check=False
    )
    if status.returncode or status.stdout:
        return None
    return _git_blob(root, attempt.head, model)


def _p07_git_blob_identity(raw: bytes) -> str:
    header = f"blob {len(raw)}\0".encode("ascii")
    return hashlib.sha1(header + raw, usedforsecurity=False).hexdigest()


def _p07_target_object(root: Path, ref: str, target: str) -> bytes | None:
    raw = _git_blob(root, ref, target)
    if raw is None:
        return None
    identity = _p07_git_blob_identity(raw)
    tree = run_git(root, ["ls-tree", ref, "--", target], check=False)
    expected = f"100644 blob {identity}\t{target}"
    if (
        tree.returncode
        or tree.stdout.strip() != expected
        or identity != _P07_TARGET_BLOB
        or len(raw) != 1860
        or _raw_digest(raw) != _P07_TARGET_SHA256
    ):
        return None
    return raw


def _p07_model(context: _SemanticContext) -> bool:
    expected = {
        "profile": "stride_model",
        "model": _P07_MODEL,
        "target": _P07_TARGET,
        "target_blob": _P07_TARGET_BLOB,
        "target_sha256": _P07_TARGET_SHA256,
    }
    if context.predicate.data != expected:
        return False
    report = _p07_report_history(context.root, context.attempt, _P07_MODEL)
    prepared_target = _p07_target_object(
        context.root, context.attempt.prepared, _P07_TARGET
    )
    head_target = _p07_target_object(context.root, context.attempt.head, _P07_TARGET)
    sections = _p07_sections(report)
    return bool(
        prepared_target is not None
        and head_target is not None
        and prepared_target == head_target
        and sections is not None
        and _p07_native_conversation(sections)
        and _p07_target_binding(sections)
    )


def _p01_feature_spec_plan(context: _SemanticContext) -> bool:
    data, root, attempt = context.predicate.data, context.root, context.attempt
    paths = {name: str(data[name]) for name in ("spec", "plan", "board", "test", "code", "fixture", "source_identity")}
    if _p01_one_commit(root, attempt) is None:
        return False
    if any(_p01_regular_blob(root, attempt.prepared, path) is None for path in (paths["board"], paths["test"], paths["code"], paths["fixture"], paths["source_identity"])):
        return False
    if any(_git_blob(root, attempt.prepared, path) is not None for path in (paths["spec"], paths["plan"])):
        return False
    fixture_models = _p01_fixture_models(_p01_regular_blob(root, attempt.prepared, paths["fixture"]) or b"")
    identity = _p01_json(_p01_regular_blob(root, attempt.prepared, paths["source_identity"]) or b"")
    if fixture_models is None or not _p01_source_identity(identity):
        return False
    prepared_model, intended_model = fixture_models
    expected_model = {"open": 1, "claimed": 1, "completed": 1, "unresolved": 2}
    if prepared_model == expected_model or intended_model != expected_model:
        return False
    return bool(
        _p01_board_transition(root, attempt, paths["board"], str(data["task_id"]))
        and _p01_spec_and_plan(_p01_regular_blob(root, attempt.head, paths["spec"]), _p01_regular_blob(root, attempt.head, paths["plan"]))
        and _p01_prepared_defect(_p01_regular_blob(root, attempt.prepared, paths["code"]))
        and _p01_exact_regression(_p01_regular_blob(root, attempt.prepared, paths["test"]), _p01_regular_blob(root, attempt.head, paths["test"]))
        and _p01_exact_repair(_p01_regular_blob(root, attempt.prepared, paths["code"]), _p01_regular_blob(root, attempt.head, paths["code"]))
        and run_git(root, ["diff", "--no-ext-diff", "--quiet", attempt.head], check=False).returncode == 0
    )


_U01_BRIEF = {
    "schema_version": 1,
    "lab_id": "U01-autonomous-sprint",
    "deliverable": "docs/academy-sprint-summary.md",
    "title": "Operate a bounded autonomous sprint",
    "required_topics": (
        "approval boundary",
        "SMARTS decision trail",
        "hard-gate stop",
    ),
}


def _u01_sections(text: str, title: str, headings: tuple[str, ...]) -> dict[str, str] | None:
    if not text.startswith(f"# {title}\n"):
        return None
    matches = list(re.finditer(r"(?m)^## (?P<heading>[^\n]+)\n", text))
    if tuple(match.group("heading") for match in matches) != headings:
        return None
    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[match.end():end].strip()
        if not body:
            return None
        sections[match.group("heading")] = body
    return sections


def _u01_sprint_decisions(context: _SemanticContext) -> bool:
    data, root, attempt = context.predicate.data, context.root, context.attempt
    paths = {key: str(data[key]) for key in ("spec", "plan", "sprint_log", "brief", "deliverable")}
    brief = _json(root, attempt.prepared, paths["brief"])
    if brief is None or brief != {**_U01_BRIEF, "required_topics": list(_U01_BRIEF["required_topics"])}:
        return False
    baseline_log = _git_blob(root, attempt.prepared, paths["sprint_log"])
    final_log = _git_blob(root, attempt.head, paths["sprint_log"])
    spec = _text(root, attempt.head, paths["spec"])
    plan = _text(root, attempt.head, paths["plan"])
    deliverable = _text(root, attempt.head, paths["deliverable"])
    if (
        baseline_log is None
        or final_log is None
        or not final_log.startswith(baseline_log)
        or len(final_log) <= len(baseline_log)
        or spec is None
        or plan is None
        or deliverable is None
        or any(_git_blob(root, attempt.prepared, paths[key]) is not None for key in ("spec", "plan", "deliverable"))
    ):
        return False
    commits = tuple(
        line
        for line in run_git(root, ["rev-list", "--reverse", f"{attempt.prepared}..{attempt.head}"], check=False).stdout.splitlines()
        if _SHA40.fullmatch(line)
    )
    expected_paths = {paths["spec"], paths["plan"], paths["sprint_log"], paths["deliverable"]}
    clean = not run_git(root, ["status", "--porcelain", "--untracked-files=all"], check=False).stdout
    spec_sections = _u01_sections(spec, "Academy sprint: operator guide", ("Problem", "Scope", "Acceptance criteria", "Open questions"))
    plan_sections = _u01_sections(plan, "Academy sprint plan", ("Acceptance criteria ledger", "Tasks", "MVP slice"))
    deliverable_sections = _u01_sections(deliverable, str(brief["title"]), ("Approval boundary", "SMARTS decision trail", "Hard-gate stop"))
    if spec_sections is None or plan_sections is None or deliverable_sections is None:
        return False
    scope = spec_sections["Scope"].casefold()
    required_scope = paths["deliverable"].casefold()
    topics = tuple(str(item) for item in brief["required_topics"])
    suffix = final_log[len(baseline_log):].decode("utf-8", "surrogateescape")
    try:
        remote = validate_training_remotes(root, require_push_safe=True)
    except RemoteSafetyError:
        return False
    return bool(
        commits == (attempt.head,)
        and set(_commit_paths(root, attempt.head)) == expected_paths
        and clean
        and remote.origin is not None
        and required_scope in scope
        and all(
            token in scope
            for token in (
                "does not change",
                "product code",
                "tests",
                "dependencies",
                "remotes",
                "fork branch",
                "pull request",
                "never pushes directly to upstream",
                "never merges",
            )
        )
        and scope.count("push") == 2
        and "none." == spec_sections["Open questions"].casefold()
        and all(topic.casefold() in deliverable.casefold() for topic in topics)
        and all(token in plan_sections["Acceptance criteria ledger"] for token in ("AC-01", "AC-02"))
        and paths["deliverable"] in plan_sections["Tasks"]
        and plan_sections["MVP slice"].strip() == "T-01"
        and "academy-sprint" in suffix
        and "**SMARTS:**" in suffix
        and "**Chosen:**" in suffix
        and re.search(r"(?i)confidence:\s*(?:high|low)", suffix) is not None
        and "intent:" in suffix
    )


def _live_hygiene_inventory(
    root: Path, attempt: _Attempt
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    worktrees: list[dict[str, object]] = []
    dirty_branches: set[str] = set()
    porcelain = run_git(root, ["worktree", "list", "--porcelain"]).stdout
    for block in (item for item in porcelain.strip().split("\n\n") if item.strip()):
        fields: dict[str, str] = {}
        detached = False
        for line in block.splitlines():
            key, _, value = line.partition(" ")
            if key == "detached":
                detached = True
            elif value:
                fields[key] = value
        location = fields.get("worktree", "")
        head = fields.get("HEAD", "")
        branch_ref = fields.get("branch", "")
        branch = (
            branch_ref.removeprefix("refs/heads/")
            if branch_ref.startswith("refs/heads/")
            else f"(detached:{head[:12]})" if detached and _SHA40.fullmatch(head) else ""
        )
        if not location or not branch:
            raise CheckpointError("Git worktree inventory is malformed.")
        dirty = bool(
            run_git(
                Path(location),
                ["status", "--porcelain", "--untracked-files=all"],
                check=False,
            ).stdout
        )
        if dirty and branch_ref.startswith("refs/heads/"):
            dirty_branches.add(branch)
        worktrees.append({"branch": branch, "dirty": dirty})
    worktrees.sort(key=lambda item: str(item["branch"]))

    refs: list[dict[str, object]] = []
    raw_refs = run_git(
        root,
        [
            "for-each-ref",
            "--format=%(refname:short)%00%(objectname)",
            "refs/heads",
        ],
    ).stdout.splitlines()
    for raw in raw_refs:
        if "\x00" not in raw:
            raise CheckpointError("Git ref inventory is malformed.")
        name, head = raw.split("\x00", 1)
        if not name or not _SHA40.fullmatch(head):
            raise CheckpointError("Git ref inventory is malformed.")
        if name in dirty_branches:
            classification = "dirty"
        elif name in {"main", attempt.branch}:
            classification = "retain"
        elif run_git(
            root,
            ["merge-base", "--is-ancestor", head, "main"],
            check=False,
        ).returncode == 0:
            classification = "merged"
        elif run_git(
            root,
            ["rev-list", "--count", f"main..{head}"],
            check=False,
        ).stdout.strip() not in {"", "0"}:
            classification = "unique"
        else:
            raise CheckpointError("Git ref classification is indeterminate.")
        refs.append({"name": name, "classification": classification})
    refs.sort(key=lambda item: str(item["name"]))
    return refs, worktrees


def _p06_summary_format_contract(source: bytes | None) -> bool:
    if source is None:
        return False
    try:
        tree = ast.parse(source.decode("utf-8"))
    except (UnicodeDecodeError, SyntaxError):
        return False
    calls: list[ast.Call] = []
    writer: ast.FunctionDef | None = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_write_report":
            writer = node
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        owner = node.func.value
        if (
            node.func.attr == "add_argument"
            and isinstance(owner, ast.Name)
            and owner.id == "report_parser"
            and len(node.args) == 1
            and isinstance(node.args[0], ast.Constant)
            and node.args[0].value == "--format"
        ):
            calls.append(node)
    if len(calls) != 1 or writer is None:
        return False
    keywords = {item.arg: item.value for item in calls[0].keywords}
    try:
        choices = ast.literal_eval(keywords["choices"])
        default = ast.literal_eval(keywords["default"])
    except (KeyError, ValueError, TypeError):
        return False
    json_branch = any(
        isinstance(node, ast.If)
        and isinstance(node.test, ast.Compare)
        and isinstance(node.test.left, ast.Name)
        and node.test.left.id == "output_format"
        and len(node.test.ops) == 1
        and isinstance(node.test.ops[0], ast.Eq)
        and len(node.test.comparators) == 1
        and isinstance(node.test.comparators[0], ast.Constant)
        and node.test.comparators[0].value == "json"
        for node in ast.walk(writer)
    )
    return bool(
        tuple(choices) == ("text", "json")
        and default == "text"
        and json_branch
        and any(isinstance(node, ast.For) for node in writer.body)
    )


def _p06_context_transition(before: bytes | None, after: bytes | None) -> bool:
    return bool(
        before == _P06_CONTEXT
        and after == _P06_CONTEXT_AFTER
        and len(before) == 1664
        and len(after) == 1727
        and _raw_digest(before) == "3c496fe68bfc6042663c9b1d697c6b7f314e1f814533acbb30fd5169c39752f4"
        and _raw_digest(after) == "f6840aedb9f55ae370f1b3b3e4d69235e82a3733e52148f93e2a6af32fe9e9b1"
    )


def _p06_provenance_transition(before: bytes | None, after: bytes | None) -> bool:
    if before != _P06_PROVENANCE or after != _P06_PROVENANCE_AFTER:
        return False
    before_record, after_record = _p01_json(before), _p01_json(after)
    try:
        return bool(
            isinstance(before_record, dict)
            and isinstance(after_record, dict)
            and before_record.get("schema") == 1
            and before_record.get("doc") == "CONTEXT"
            and before_record["entries"][0]["path"] == "workshop_queue/cli.py"
            and before_record["entries"][0]["hash"] == "042746e43698e5d2a6de4c536f1024f893aef805"
            and after_record["entries"][0]["hash"] == _P06_SOURCE_OBJECT
            and _raw_digest(before) == "4831a0db68f47f7f63fd6d0925942184488ce65231fb3acb747b753aae38a915"
            and _raw_digest(after) == "c48d6b8d06de435e52f74d17a33ae17636276c43c361b6ab4acbf0ac0e4b2e7b"
        )
    except (KeyError, IndexError, TypeError):
        return False


def _p06_recovery_history(
    root: Path,
    attempt: _Attempt,
    context_path: str,
    provenance_path: str,
    handoff_path: str,
) -> tuple[str, str] | None:
    commits = _exact_two_commit_range(root, attempt.prepared, attempt.head)
    if commits is None:
        return None
    recovery, handoff = commits
    if set(_commit_paths(root, recovery)) != {context_path, provenance_path}:
        return None
    if set(_commit_paths(root, handoff)) != {handoff_path}:
        return None
    return recovery, handoff


def _p06_handoff(
    raw: bytes | None,
    *,
    prepared: str,
    recovery: str,
    context_path: str,
    provenance_path: str,
    source_path: str,
    preserved_path: str,
) -> bool:
    value = _p01_json(raw) if raw is not None else None
    if not isinstance(value, dict):
        return False
    keys = {
        "context_after_sha256", "context_before_sha256", "context_path",
        "prepared_commit", "preserved_after_sha256", "preserved_before_sha256",
        "preserved_path", "recovery_commit", "recovery_route", "schema_version",
        "source_path", "stale_claim", "provenance_path",
        "provenance_before_sha256", "provenance_after_sha256",
    }
    if set(value) != keys or not _version(value.get("schema_version"), 2):
        return False
    expected_paths = {
        "context_path": context_path,
        "provenance_path": provenance_path,
        "source_path": source_path,
        "preserved_path": preserved_path,
    }
    try:
        if any(_safe_path(value.get(field), field) != expected for field, expected in expected_paths.items()):
            return False
    except CheckpointError:
        return False
    digest_values = {
        "context_before_sha256": _raw_digest(_P06_CONTEXT),
        "context_after_sha256": _raw_digest(_P06_CONTEXT_AFTER),
        "provenance_before_sha256": _raw_digest(_P06_PROVENANCE),
        "provenance_after_sha256": _raw_digest(_P06_PROVENANCE_AFTER),
        "preserved_before_sha256": _raw_digest(_P06_NOTE),
        "preserved_after_sha256": _raw_digest(_P06_NOTE),
    }
    if any(
        not isinstance(value.get(field), str)
        or not _SHA256.fullmatch(str(value[field]))
        for field in digest_values
    ):
        return False
    expected: dict[str, object] = {
        **digest_values,
        **expected_paths,
        "prepared_commit": prepared,
        "recovery_commit": recovery,
        "recovery_route": "re-scout",
        "schema_version": 2,
        "stale_claim": "Workshop Queue report output is JSON-only.",
    }
    return bool(
        value == expected
        and _SHA40.fullmatch(prepared)
        and _SHA40.fullmatch(recovery)
        and raw == canonical_json(expected) + b"\n"
    )


def _p06_provenance_recovery(context: _SemanticContext) -> bool:
    root, attempt, data = context.root, context.attempt, context.predicate.data
    if run_git(root, ["status", "--porcelain", "--untracked-files=all"], check=False).stdout:
        return False
    required = {"context", "handoff", "source", "preserved_path", "provenance"}
    if not required.issubset(data):
        return False
    context_path = str(data["context"])
    handoff_path = str(data["handoff"])
    source_path = str(data["source"])
    preserved_path = str(data["preserved_path"])
    provenance_path = str(data["provenance"])
    history = _p06_recovery_history(root, attempt, context_path, provenance_path, handoff_path)
    if history is None:
        return False
    recovery, _handoff_commit = history
    context_before = _git_blob(root, attempt.prepared, context_path)
    context_after = _git_blob(root, recovery, context_path)
    provenance_before = _git_blob(root, attempt.prepared, provenance_path)
    provenance_after = _git_blob(root, recovery, provenance_path)
    source = _git_blob(root, attempt.prepared, source_path)
    note_before = _git_blob(root, attempt.prepared, preserved_path)
    note_after = _git_blob(root, attempt.head, preserved_path)
    source_object = (
        hashlib.sha1(b"blob " + str(len(source)).encode("ascii") + b"\0" + source).hexdigest()
        if source is not None
        else ""
    )
    return bool(
        _p06_context_transition(context_before, context_after)
        and _p06_provenance_transition(provenance_before, provenance_after)
        and source_object == _P06_SOURCE_OBJECT
        and _p06_summary_format_contract(source)
        and note_before == _P06_NOTE
        and note_after == _P06_NOTE
        and _git_blob(root, attempt.head, context_path) == _P06_CONTEXT_AFTER
        and _git_blob(root, attempt.head, provenance_path) == _P06_PROVENANCE_AFTER
        and _p06_handoff(
            _git_blob(root, attempt.head, handoff_path),
            prepared=attempt.prepared,
            recovery=recovery,
            context_path=context_path,
            provenance_path=provenance_path,
            source_path=source_path,
            preserved_path=preserved_path,
        )
    )


_U04_CHILD_PATHS = {
    "greenfield": ".academy/workspaces/U04-greenfield",
    "brownfield": ".academy/workspaces/U04-brownfield",
}
_U04_COMMON_CHILD_DOCUMENTS = (
    ".codearbiter/CONTEXT.md",
    ".codearbiter/tech-stack.md",
    ".codearbiter/coding-standards.md",
    ".codearbiter/security-controls.md",
    ".codearbiter/open-questions.md",
    ".codearbiter/open-tasks.md",
    ".codearbiter/overrides.log",
)
_U04_GREENFIELD_PLANS = (
    ".codearbiter/plans/01-architecture-breakdown.md",
    ".codearbiter/plans/02-phased-build-plan.md",
    ".codearbiter/plans/03-task-backlog.md",
)
_U04_REPORT_PATH = ".codearbiter/reports/academy/U04-initialization.md"


def _u04_child_binding(root: Path, path: str, kind: str) -> tuple[str, str, str] | None:
    child = root / path
    required_documents = (
        *_U04_COMMON_CHILD_DOCUMENTS,
        *(_U04_GREENFIELD_PLANS if kind == "greenfield" else ()),
    )
    if not (
        _plain_path_within(root, child, regular_file=False)
        and _plain_path_within(child, child / ".git", regular_file=False)
        and all(
            _plain_path_within(child, child / document, regular_file=True)
            for document in required_documents
        )
    ):
        return None
    child_root = run_git(child, ["rev-parse", "--show-toplevel"], check=False)
    if child_root.returncode or Path(child_root.stdout.strip()).resolve() != child.resolve():
        return None
    head_result = run_git(child, ["rev-parse", "HEAD"], check=False)
    head = head_result.stdout.strip()
    if head_result.returncode or not _SHA40.fullmatch(head):
        return None
    initial = run_git(child, ["rev-list", "--max-parents=0", head], check=False)
    initial_commits = tuple(
        line for line in initial.stdout.splitlines() if _SHA40.fullmatch(line)
    )
    seed = U04_SEED_CONTENT.get(kind)
    if initial.returncode or len(initial_commits) != 1 or seed is None:
        return None
    seed_commit = initial_commits[0]
    seed_paths = tuple(
        run_git(child, ["ls-tree", "-r", "--name-only", seed_commit], check=False)
        .stdout.splitlines()
    )
    if seed_paths != tuple(sorted(seed)) or any(
        _git_blob(child, seed_commit, document) != contents
        for document, contents in seed.items()
    ):
        return None
    tree_result = run_git(child, ["rev-parse", "HEAD^{tree}"], check=False)
    tree = tree_result.stdout.strip()
    if tree_result.returncode or not _SHA40.fullmatch(tree):
        return None
    status = run_git(child, ["status", "--porcelain", "--untracked-files=all"], check=False)
    if status.returncode or status.stdout:
        return None
    documents = tuple(_git_blob(child, head, document) for document in required_documents)
    if any(document is None or b"[CONFIRM-" in document.upper() for document in documents):
        return None
    markdown_paths = tuple(
        path
        for path in run_git(
            child,
            ["ls-tree", "-r", "--name-only", head, "--", ".codearbiter"],
            check=False,
        ).stdout.splitlines()
        if path.endswith(".md")
    )
    if any(
        blob is None or b"[CONFIRM-" in blob.upper()
        for blob in (_git_blob(child, head, path) for path in markdown_paths)
    ):
        return None
    context = documents[0]
    if not (
        re.search(rb"(?mi)^arbiter:\s*enabled\s*$", context)
        and b"<!--INITIALIZED-->" in context
    ):
        return None
    if kind == "greenfield":
        decision_paths = tuple(
            path
            for path in run_git(
                child,
                ["ls-tree", "-r", "--name-only", head, "--", ".codearbiter/decisions"],
                check=False,
            ).stdout.splitlines()
            if path.endswith(".md") and path != ".codearbiter/decisions/decision-log.md"
        )
        decisions = tuple(_git_blob(child, head, path) for path in decision_paths)
        if not any(
            decision is not None
            and b"[CONFIRM-" not in decision.upper()
            and re.search(rb"(?mi)^status:\s*accepted\s*$", decision)
            for decision in decisions
        ):
            return None
    elif any(_git_blob(child, head, plan) is not None for plan in _U04_GREENFIELD_PLANS):
        return None
    return head, tree, _raw_digest(context)


def _u04_report(bindings: dict[str, tuple[str, str, str]]) -> bytes:
    greenfield, brownfield = (bindings[name] for name in ("greenfield", "brownfield"))
    return (
        "# U04 initialization evidence\n\n"
        "## Greenfield\n"
        f"Path: {_U04_CHILD_PATHS['greenfield']}\n"
        f"HEAD: {greenfield[0]}\n"
        f"Tree: {greenfield[1]}\n"
        f"CONTEXT-SHA256: {greenfield[2]}\n\n"
        "## Brownfield\n"
        f"Path: {_U04_CHILD_PATHS['brownfield']}\n"
        f"HEAD: {brownfield[0]}\n"
        f"Tree: {brownfield[1]}\n"
        f"CONTEXT-SHA256: {brownfield[2]}\n\n"
        "## Route evidence\n"
        "Greenfield-Plans: .codearbiter/plans/01-architecture-breakdown.md; "
        ".codearbiter/plans/02-phased-build-plan.md; "
        ".codearbiter/plans/03-task-backlog.md\n"
        "Brownfield-Context: .codearbiter/CONTEXT.md; .codearbiter/tech-stack.md; "
        ".codearbiter/coding-standards.md; .codearbiter/security-controls.md\n"
    ).encode("utf-8")


def write_u04_initialization_report(root: Path) -> Path:
    """Write the canonical U04 report only from clean, committed child state."""
    bindings = {
        name: _u04_child_binding(root, path, name)
        for name, path in _U04_CHILD_PATHS.items()
    }
    if any(binding is None for binding in bindings.values()):
        raise ValueError(
            "U04 child repositories must be clean and committed before report generation."
        )
    concrete_bindings = {
        name: binding for name, binding in bindings.items() if binding is not None
    }
    destination = ensure_within(root, Path(_U04_REPORT_PATH))
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(_u04_report(concrete_bindings))
    return destination


def _u04_initialized_projects(context: _SemanticContext) -> bool:
    root, attempt, data = context.root, context.attempt, context.predicate.data
    if (
        data.get("greenfield") != _U04_CHILD_PATHS["greenfield"]
        or data.get("brownfield") != _U04_CHILD_PATHS["brownfield"]
        or data.get("report") != _U04_REPORT_PATH
    ):
        return False
    root_status = run_git(root, ["status", "--porcelain", "--untracked-files=all"], check=False)
    history = run_git(root, ["rev-list", "--reverse", f"{attempt.prepared}..{attempt.head}"], check=False)
    commits = tuple(line for line in history.stdout.splitlines() if _SHA40.fullmatch(line))
    if (
        root_status.returncode
        or root_status.stdout
        or history.returncode
        or not commits
        or commits[-1] != attempt.head
        or any(_commit_paths(root, commit) != (_U04_REPORT_PATH,) for commit in commits)
        or not _changed(root, attempt.prepared, attempt.head, _U04_REPORT_PATH)
    ):
        return False
    bindings = {
        name: _u04_child_binding(root, path, name)
        for name, path in _U04_CHILD_PATHS.items()
    }
    if any(binding is None for binding in bindings.values()):
        return False
    concrete_bindings = {
        name: binding for name, binding in bindings.items() if binding is not None
    }
    return _git_blob(root, attempt.head, _U04_REPORT_PATH) == _u04_report(concrete_bindings)


def _u07_capstone(context: _SemanticContext) -> bool:
    """Verify the local U07 history without claiming a command or hosted event occurred."""
    root, attempt = context.root, context.attempt
    data = context.predicate.data
    if set(data) != {"profile", "code", "test"}:
        return False
    paths = {name: str(data[name]) for name in ("code", "test")}
    if not validate_u07_fixture(root, attempt.prepared):
        return False
    learner_commits = tuple(
        line
        for line in run_git(
            root, ["rev-list", "--reverse", f"{attempt.prepared}..{attempt.head}"], check=False
        ).stdout.splitlines()
        if _SHA40.fullmatch(line)
    )
    if not learner_commits or learner_commits[-1] != attempt.head:
        return False
    parent = attempt.prepared
    for commit in learner_commits:
        if run_git(root, ["rev-list", "--parents", "-n", "1", commit], check=False).stdout.split() != [commit, parent]:
            return False
        parent = commit
    changed_paths = run_git(
        root,
        ["diff", "--no-ext-diff", "--name-only", attempt.prepared, attempt.head],
        check=False,
    ).stdout.splitlines()
    specs = sorted(
        path for path in changed_paths
        if path.startswith(".codearbiter/specs/") and path.endswith(".md")
    )
    plans = sorted(
        path for path in changed_paths
        if path.startswith(".codearbiter/plans/") and path.endswith(".md")
    )
    allowed_governance = {
        ".codearbiter/open-tasks.md",
        ".codearbiter/triage.log",
        ".codearbiter/last-checkpoint",
    }
    allowed_paths = {paths["code"], paths["test"], *specs, *plans, *allowed_governance}
    if (
        len(specs) != 1
        or len(plans) != 1
        or Path(specs[0]).stem != Path(plans[0]).stem
        or paths["code"] not in changed_paths
        or paths["test"] not in changed_paths
        or any(path not in allowed_paths for path in changed_paths)
    ):
        return False
    documents = {
        "spec": _text(root, attempt.head, specs[0]),
        "plan": _text(root, attempt.head, plans[0]),
    }
    if not (
        _headings(documents["spec"], ("Problem", "Acceptance criteria"))
        and _headings(documents["plan"], ("Plan", "Verification"))
    ):
        return False
    document_text = "\n".join(item or "" for item in documents.values()).casefold()
    if any(token not in document_text for token in ("control", "character", "resolution")):
        return False
    test_blob = _git_blob(root, attempt.head, paths["test"])
    code_blob = _git_blob(root, attempt.head, paths["code"])
    if (
        test_blob is None
        or code_blob is None
        or not u07_remediation_test_is_exact(test_blob)
        or not u07_remediation_source_is_exact(code_blob)
    ):
        return False
    try:
        remote = validate_training_remotes(root, require_push_safe=True)
    except (RemoteSafetyError, Exception):
        return False
    if remote.origin is None:
        return False
    try:
        test_result = subprocess.run(
            [sys.executable, "-m", "unittest", paths["test"].replace("/", ".").removesuffix(".py")],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            timeout=10,
        )
        control_probe = subprocess.run(
            [
                sys.executable,
                "-c",
                "\n".join(
                    (
                        "from datetime import datetime, timezone",
                        "from workshop_queue.model import Ticket, TicketStatus",
                        "from workshop_queue.service import claim_ticket, complete_ticket",
                        "now = datetime(2026, 7, 30, 12, 0, tzinfo=timezone.utc)",
                        "ticket = Ticket('RQ-U07', 'title', 'description', TicketStatus.OPEN, now)",
                        "claimed = claim_ticket([ticket], 'RQ-U07', 'Sam', now)",
                        "for resolution in ('done\\nagain', 'done\\tagain', 'done\\x7fagain'):",
                        "    try:",
                        "        complete_ticket(claimed, 'RQ-U07', resolution, now)",
                        "    except ValueError as error:",
                        "        assert 'control characters' in str(error)",
                        "    else:",
                        "        raise AssertionError(resolution)",
                    )
                ),
            ],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            timeout=10,
        )
    except subprocess.TimeoutExpired:
        return False
    clean = run_git(root, ["status", "--porcelain", "--untracked-files=all"], check=False)
    return bool(
        _changed_blobs_are_secret_free(root, attempt.head, changed_paths)
        and test_result.returncode == 0
        and control_probe.returncode == 0
        and clean.returncode == 0
        and not clean.stdout
    )


def _initialized_fixture(context: _SemanticContext) -> bool:
    """Keep direct strictness-fixture coverage for the retired noncanonical profile."""
    root, attempt, data = context.root, context.attempt, context.predicate.data
    report = _changed_document(context, str(data["report"]))
    workspace = root / str(data["workspace"])
    live_context = workspace / ".codearbiter" / "CONTEXT.md"
    workspace_plain = _plain_path_within(root, workspace, regular_file=False)
    git_directory_plain = workspace_plain and _plain_path_within(
        workspace, workspace / ".git", regular_file=False
    )
    context_plain = workspace_plain and _plain_path_within(
        workspace, live_context, regular_file=True
    )
    child_root = (
        run_git(workspace, ["rev-parse", "--show-toplevel"], check=False).stdout.strip()
        if workspace_plain and git_directory_plain and context_plain
        else ""
    )
    child_head = (
        run_git(workspace, ["rev-parse", "HEAD"], check=False).stdout.strip()
        if child_root and Path(child_root).resolve() == workspace.resolve()
        else ""
    )
    child_tree = (
        run_git(workspace, ["rev-parse", "HEAD^{tree}"], check=False).stdout.strip()
        if _SHA40.fullmatch(child_head)
        else ""
    )
    context_blob = (
        _git_blob(workspace, child_head, ".codearbiter/CONTEXT.md")
        if _SHA40.fullmatch(child_head)
        else None
    )
    clean = (
        not run_git(
            workspace,
            ["status", "--porcelain", "--untracked-files=all"],
            check=False,
        ).stdout
        if child_root
        else False
    )
    return bool(
        report
        and _headings(report, ("Init", "Brownfield", "Greenfield", "Reconciliation"))
        and _SHA40.fullmatch(child_head)
        and _SHA40.fullmatch(child_tree)
        and Path(child_root).resolve() == workspace.resolve()
        and workspace_plain
        and git_directory_plain
        and context_plain
        and context_blob is not None
        and clean
        and re.search(rf"(?m)^Child-HEAD:\s*{re.escape(child_head)}\s*$", report)
        and re.search(rf"(?m)^Child-Tree:\s*{re.escape(child_tree)}\s*$", report)
        and re.search(
            rf"(?m)^CONTEXT-SHA256:\s*{re.escape(_raw_digest(context_blob))}\s*$",
            report,
        )
    )


def _u03_refactor_chore_release(root: Path, attempt: _Attempt, data: dict[str, object]) -> bool:
    """Check the observable local artifacts of the real release lane, not publication."""
    scenario, code, test, chore = (str(data[key]) for key in ("scenario", "code", "test", "chore"))
    target, version, tag, changelog, targets_path = (
        str(data[key])
        for key in ("release_target", "release_version", "release_tag", "release_changelog", "release_targets")
    )
    brief = _json(root, attempt.prepared, scenario)
    expected_brief = {
        "schema_version": 2,
        "lab_id": "U03-refactor-chore-release",
        "operation": "refactor_chore_release",
        "starting_condition": "first-release",
        "refactor": {"code_path": code, "test_path": test},
        "chore": {"path": chore},
        "release": {"target": target, "version": version, "tag": tag, "changelog": changelog},
    }
    commits = _exact_three_commit_range(root, attempt.prepared, attempt.head)
    prepared_test = _git_blob(root, attempt.prepared, test)
    prepared_targets = _git_blob(root, attempt.prepared, targets_path)
    if (
        brief != expected_brief
        or commits is None
        or set(_commit_paths(root, commits[0])) != {code}
        or set(_commit_paths(root, commits[1])) != {chore}
        or set(_commit_paths(root, commits[2])) != {changelog}
        or prepared_test is None
        or prepared_test != _git_blob(root, attempt.head, test)
        or prepared_targets != (
            b"<!-- release-targets -->\n"
            + f"[{target}]\n".encode()
            + b"prefix: academy-v\n"
            + f"changelog: {changelog}\n".encode()
            + b"payload: .\n<!-- /release-targets -->\n"
        )
    ):
        return False
    refactor_message = run_git(root, ["log", "-1", "--format=%B", commits[0]], check=False).stdout
    changelog_blob = _git_blob(root, attempt.head, changelog)
    if changelog_blob is None:
        return False
    try:
        changelog_text = changelog_blob.decode("utf-8")
    except UnicodeDecodeError:
        return False
    section = re.search(
        rf"(?s)^# Changelog\n\n(## \[{re.escape(version)}\] — (\d{{4}}-\d{{2}}-\d{{2}})\n.*)\Z",
        changelog_text,
    )
    if (
        not section
        or not re.search(r"\Arefactor(?:\([^\n)]+\))?: .+\n", refactor_message)
        or not re.search(r"(?m)^CHANGELOG:\s*.+$", refactor_message)
    ):
        return False
    release_date = section.group(2)
    status = run_git(root, ["status", "--porcelain", "--untracked-files=all"], check=False)
    tag_ref = f"refs/tags/{tag}"
    tag_type = run_git(root, ["cat-file", "-t", tag_ref], check=False)
    tag_head = run_git(root, ["rev-parse", "--verify", f"{tag_ref}^{{}}"], check=False)
    tag_body = run_git(root, ["cat-file", "-p", tag_ref], check=False)
    _metadata, separator, body = tag_body.stdout.partition("\n\n")
    return bool(
        version and tag == f"academy-v{version}" and status.returncode == 0 and not status.stdout
        and tag_type.returncode == 0 and tag_type.stdout.strip() == "tag"
        and tag_head.returncode == 0 and tag_head.stdout.strip() == attempt.head
        and tag_body.returncode == 0 and separator
        and body.replace("\r\n", "\n") == f"{section.group(1)}\nReleased-at: {release_date}\n"
    )


def _semantic(context: _SemanticContext) -> bool:
    data = context.predicate.data
    profile = str(data["profile"])
    root, attempt = context.root, context.attempt
    if profile in _REMOTE_PROFILES and not _remote_safe(root):
        return False
    if profile == "remote_doctor":
        artifact_path = str(data["artifact"])
        artifact = _json(root, attempt.head, artifact_path)
        clean = not run_git(
            root, ["status", "--porcelain", "--untracked-files=all"], check=False
        ).stdout
        learner_commits = tuple(
            line
            for line in run_git(
                root,
                ["rev-list", "--reverse", f"{attempt.prepared}..{attempt.head}"],
                check=False,
            ).stdout.splitlines()
            if _SHA40.fullmatch(line)
        )
        exact_commit_boundary = bool(
            learner_commits == (attempt.head,)
            and _commit_paths(root, attempt.head) == (artifact_path,)
        )
        return bool(
            artifact
            and clean
            and exact_commit_boundary
            and _changed(root, attempt.prepared, attempt.head, artifact_path)
            and set(artifact) == {"schema_version", "safe_for_push_labs", "effective_push_remote"}
            and _version(artifact["schema_version"], 1)
            and artifact == {
                "schema_version": 1,
                "safe_for_push_labs": True,
                "effective_push_remote": "origin",
            }
        )
    if profile == "orientation":
        artifact_path, context_path = str(data["artifact"]), str(data["context"])
        artifact = _json(root, attempt.head, artifact_path)
        context_blob = _git_blob(root, attempt.head, context_path)
        if not artifact or context_blob is None or not _changed(root, attempt.prepared, attempt.head, artifact_path):
            return False
        learner_commits = tuple(
            line
            for line in run_git(
                root,
                ["rev-list", "--reverse", f"{attempt.prepared}..{attempt.head}"],
                check=False,
            ).stdout.splitlines()
            if _SHA40.fullmatch(line)
        )
        clean = not run_git(
            root, ["status", "--porcelain", "--untracked-files=all"], check=False
        ).stdout
        exact_commit_boundary = bool(
            learner_commits == (attempt.head,)
            and _commit_paths(root, attempt.head) == (artifact_path,)
        )
        match = re.search(r"(?m)^stage:\s*(\d+)\s*$", context_blob.decode("utf-8", "surrogateescape"))
        return bool(
            clean
            and exact_commit_boundary
            and context_blob == _git_blob(root, attempt.prepared, context_path)
            and set(artifact) == {"schema_version", "context_path", "context_sha256", "stage"}
            and _version(artifact["schema_version"], 1)
            and artifact["context_path"] == context_path
            and artifact["context_sha256"] == _raw_digest(context_blob)
            and match
            and artifact["stage"] == int(match.group(1))
        )
    if profile == "task_transition":
        board, task_id = str(data["board"]), str(data["task_id"])
        before, after = _text(root, attempt.prepared, board), _changed_document(context, board)
        if not before or not after:
            return False
        before_lines = before.splitlines(keepends=True)
        after_lines = after.splitlines(keepends=True)
        if len(before_lines) != len(after_lines):
            return False
        changed = [
            (old, new)
            for old, new in zip(before_lines, after_lines, strict=True)
            if old != new
        ]
        if len(changed) != 1:
            return False
        old_line, new_line = (line.rstrip("\r\n") for line in changed[0])
        old_match = re.fullmatch(
            rf"- \[ \] {re.escape(task_id)} - (?P<body>.+)", old_line
        )
        new_match = re.fullmatch(
            rf"- \[x\] {re.escape(task_id)} - (?P<body>.+?)  \(done (?P<date>\d{{4}}-\d{{2}}-\d{{2}})\)",
            new_line,
        )
        learner_commits = tuple(
            line
            for line in run_git(
                root,
                ["rev-list", "--reverse", f"{attempt.prepared}..{attempt.head}"],
                check=False,
            ).stdout.splitlines()
            if _SHA40.fullmatch(line)
        )
        exact_commit_boundary = bool(
            learner_commits == (attempt.head,)
            and _commit_paths(root, attempt.head) == (board,)
        )
        commit_date = run_git(
            root, ["show", "-s", "--format=%as", attempt.head], check=False
        ).stdout.strip()
        clean = not run_git(
            root, ["status", "--porcelain", "--untracked-files=all"], check=False
        ).stdout
        return bool(
            old_match
            and new_match
            and old_match.group("body") == new_match.group("body")
            and new_match.group("date") == commit_date
            and exact_commit_boundary
            and clean
        )
    if profile == "tdd_history":
        code, test = str(data["code"]), str(data["test"])
        commits = _exact_two_commit_range(root, attempt.prepared, attempt.head)
        if commits is None:
            return False
        test_commit, code_commit = commits
        return bool(
            set(_commit_paths(root, test_commit)) == {test}
            and set(_commit_paths(root, code_commit)) == {code}
            and run_git(
                root, ["merge-base", "--is-ancestor", test_commit, code_commit], check=False
            ).returncode == 0
            and _git_blob(root, test_commit, code) == _git_blob(root, attempt.prepared, code)
            and _test_module_has_minimal_retained_control_regression(
                _git_blob(root, attempt.prepared, test),
                _git_blob(root, test_commit, test),
                _git_blob(root, attempt.head, test),
            )
            and _service_has_minimal_control_repair(
                _git_blob(root, attempt.prepared, code),
                _git_blob(root, attempt.head, code),
            )
            and not _f04_has_uncommitted_learner_changes(root)
        )
    if profile == "feature_spec_plan":
        return _p01_feature_spec_plan(context)
    if profile == "pr_receipt":
        return _valid_offline_p02_receipt(context, str(data["receipt"]))
    if profile == "accepted_adr":
        adr, decision_log = str(data["adr"]), str(data["decision_log"])
        return _p03_accepted_adr(root, attempt, adr, decision_log)
    if profile == "dependency_review":
        return _p04_dependency_review(root, attempt, str(data["review"]), str(data["project"]))
    if profile == "checkpoint_remediation":
        return _p05_remediation(root, attempt, str(data["report"]))
    if profile == "provenance_recovery":
        return _p06_provenance_recovery(context)
    if profile == "stride_model":
        return _p07_model(context)
    if profile == "hygiene_snapshot":
        return False
    if profile == "p08_authenticated":
        try:
            base, _lab, authority = preflight_p08(root)
            store = open_p08_store(root, base=base, authority=authority)
            identity = P08AttemptIdentity(
                context.attempt.number,
                context.attempt.branch,
                context.attempt.prepared,
                context.attempt.head,
            )
            return validate_p08_checkpoint(root, store, identity)
        except (OSError, TypeError, ValueError):
            return False
    if profile == "sprint_decisions":
        return _u01_sprint_decisions(context)
    if profile == "override_audit_metrics":
        overrides, audit_packets = (
            str(data[key]) for key in ("overrides", "audit_packets")
        )
        prepared_overrides = _git_blob(root, attempt.prepared, overrides)
        final_overrides = _git_blob(root, attempt.head, overrides)
        object_ids = _repository_oid_pattern(root)
        commits = tuple(
            line for line in run_git(
                root, ["rev-list", "--reverse", f"{attempt.prepared}..{attempt.head}"], check=False
            ).stdout.splitlines() if object_ids is not None and object_ids.fullmatch(line)
        )
        commit_parents = run_git(root, ["rev-list", "--parents", "-n", "1", attempt.head], check=False).stdout.split()
        expected_paths = {overrides}
        changed_paths = set(_commit_paths(root, attempt.head))
        audit_packet_name = re.compile(
            rf"^{re.escape(audit_packets)}/\d{{4}}-\d{{2}}-\d{{2}}(?:-\d+)?\.md$"
        )
        audit_packet_paths = {path for path in changed_paths if audit_packet_name.fullmatch(path)}
        status = run_git(root, ["status", "--porcelain", "--untracked-files=all"], check=False)
        if (
            prepared_overrides is None or final_overrides is None
            or not prepared_overrides.endswith(b"\n") or not final_overrides.startswith(prepared_overrides)
            or commits != (attempt.head,) or commit_parents != [attempt.head, attempt.prepared]
            or len(audit_packet_paths) != 1 or changed_paths != expected_paths | audit_packet_paths
            or status.returncode != 0 or status.stdout
        ):
            return False
        try:
            new_lines = final_overrides[len(prepared_overrides):].decode("utf-8").splitlines()
        except UnicodeDecodeError:
            return False
        override_line = re.compile(r"^\[[^\]\r\n]+\] \| BY: [^|\r\n]+ \| GATE: safe-training-gate \| REASON: [^\r\n]+$")
        audit_packet = _text(root, attempt.head, next(iter(audit_packet_paths)))
        return bool(
            len(new_lines) == 1
            and all(override_line.fullmatch(line) for line in new_lines)
            and audit_packet is not None
            and re.search(r"(?m)^## Overrides\s*$", audit_packet)
            and all(
                re.search(rf"(?m)^{re.escape(line)}$", audit_packet)
                for line in new_lines
            )
        )
    if profile == "refactor_chore_release":
        return _u03_refactor_chore_release(root, attempt, data)
    if profile == "initialized_projects":
        return _u04_initialized_projects(context)
    if profile == "initialized_fixture":
        return _initialized_fixture(context)
    if profile == "debug_spike_conflict":
        spike = _changed_document(context, str(data["spike"]))
        board = _changed_document(context, str(data["board"]))
        observation = _text(root, attempt.prepared, str(data["observation"]))
        commits = _exact_two_commit_range(root, attempt.prepared, attempt.head)
        board_before = (
            _text(root, f"{commits[0]}^", str(data["board"])) if commits is not None else None
        )
        board_delta = (
            board.removeprefix(board_before)
            if board is not None and board_before is not None and board.startswith(board_before)
            else None
        )
        status = run_git(
            root,
            ["status", "--porcelain", "--untracked-files=all"],
            check=False,
        )
        changed_paths = set(
            run_git(
                root,
                ["diff", "--no-ext-diff", "--name-only", attempt.prepared, attempt.head],
                check=False,
            ).stdout.splitlines()
        )
        spike_refs = run_git(
            root,
            ["for-each-ref", "--format=%(refname:short)", "refs/heads/spike/u05-cache-key"],
            check=False,
        ).stdout.strip()
        return bool(
            observation
            and _headings(
                observation,
                ("Observed behavior", "Reproduction", "Expected behavior", "Spike question"),
            )
            and "debug.note" not in observation
            and _headings(spike, ("Question", "What tried", "Answer", "Implication"))
            and board_delta is not None
            and commits is not None
            and _commit_paths(root, commits[0]) == (str(data["board"]),)
            and _commit_paths(root, commits[1]) == (str(data["spike"]),)
            and re.fullmatch(
                r"## In-flight\n"
                r"- \[ \] (?:debug\.note\.\d{4} - (?=[^\n]*closed without code changes)[^\n]*|U05 cache-key observation)\n"
                r"  - Desc: [^\n]+\n",
                board_delta,
            )
            and not spike_refs
            and status.returncode == 0
            and not status.stdout
            and changed_paths == {str(data["spike"]), str(data["board"])}
        )
    if profile == "u06_preview_evidence":
        candidate_path, report_path = (str(data[key]) for key in ("candidate", "report"))
        commits = _exact_two_commit_range(root, attempt.prepared, attempt.head)
        if commits is None:
            return False
        candidate_commit, report_commit = commits
        candidate_blob = _git_blob(root, candidate_commit, candidate_path)
        report_blob = _git_blob(root, report_commit, report_path)
        if candidate_blob is None or report_blob is None or not blob_is_secret_free(candidate_blob) or not blob_is_secret_free(report_blob):
            return False
        try:
            report = _object(json.loads(report_blob.decode("utf-8")), "U06 report")
        except (UnicodeDecodeError, json.JSONDecodeError, CheckpointError):
            return False
        status = run_git(
            root, ["status", "--porcelain", "--untracked-files=all"], check=False
        )
        tracked_index = run_git(root, ["ls-files", "-v"], check=False)
        candidate_tree_result = run_git(
            root, ["rev-parse", f"{candidate_commit}^{{tree}}"], check=False
        )
        candidate_tree = candidate_tree_result.stdout.strip()
        oid_pattern = _repository_oid_pattern(root)
        return bool(
            status.returncode == 0
            and not status.stdout
            and tracked_index.returncode == 0
            and bool(tracked_index.stdout.splitlines())
            and all(line.startswith("H ") for line in tracked_index.stdout.splitlines())
            and candidate_tree_result.returncode == 0
            and oid_pattern is not None
            and oid_pattern.fullmatch(candidate_tree)
            and _git_blob(root, attempt.prepared, candidate_path) == _U06_SEED_CANDIDATE
            and _git_blob(root, attempt.prepared, report_path) is None
            and candidate_blob == _U06_SAFE_CANDIDATE
            and _git_blob(root, attempt.head, candidate_path) == _U06_SAFE_CANDIDATE
            and set(_commit_paths(root, candidate_commit)) == {candidate_path}
            and set(_commit_paths(root, report_commit)) == {report_path}
            and report_blob == canonical_json(report)
            and set(report) == {
                "schema_version", "prepared_commit", "candidate_commit", "candidate_tree",
                "candidate_path", "candidate_sha256", "changed_paths", "read_only",
                "advanced_surfaces",
            }
            and _version(report["schema_version"], 1)
            and report["prepared_commit"] == attempt.prepared
            and report["candidate_commit"] == candidate_commit
            and report["candidate_tree"] == candidate_tree
            and report["candidate_path"] == candidate_path
            and report["candidate_sha256"] == _raw_digest(candidate_blob)
            and report["changed_paths"] == [candidate_path]
            and report["read_only"] is True
            and report["advanced_surfaces"] == _U06_ADVANCED_SURFACES
        )
    if profile == "preview_evidence":
        report_path = str(data["report"])
        report = _json(root, attempt.head, report_path)
        if not report:
            return False
        reviewed_commit = report.get("reviewed_commit")
        changed_paths = report.get("changed_paths")
        expected_paths = (
            run_git(
                root,
                [
                    "diff",
                    "--no-ext-diff",
                    "--name-only",
                    attempt.prepared,
                    str(reviewed_commit),
                ],
                check=False,
            ).stdout.splitlines()
            if _SHA40.fullmatch(str(reviewed_commit))
            else []
        )
        reviewed_tree = (
            run_git(root, ["rev-parse", f"{reviewed_commit}^{{tree}}"], check=False).stdout.strip()
            if _SHA40.fullmatch(str(reviewed_commit))
            else ""
        )
        report_commits = _path_commits(
            root, attempt.prepared, attempt.head, report_path
        )
        report_commit = report_commits[0] if len(report_commits) == 1 else ""
        report_parent = (
            run_git(root, ["rev-parse", f"{report_commit}^"], check=False).stdout.strip()
            if report_commit
            else ""
        )
        return bool(
            _changed(root, attempt.prepared, attempt.head, report_path)
            and set(report) == {
                "schema_version", "reviewed_commit", "reviewed_tree", "changed_paths",
                "read_only", "secret_scan", "predicted_reviewers", "optional_surfaces",
            }
            and _version(report["schema_version"], 1)
            and run_git(root, ["merge-base", "--is-ancestor", str(reviewed_commit), attempt.head], check=False).returncode == 0
            and reviewed_commit != attempt.prepared
            and report["reviewed_tree"] == reviewed_tree
            and isinstance(changed_paths, list)
            and changed_paths == expected_paths
            and bool(changed_paths)
            and report_parent == reviewed_commit
            and set(_commit_paths(root, report_commit)) == {report_path}
            and report["read_only"] is True
            and report["secret_scan"] == "passed"
            and _changed_blobs_are_secret_free(root, str(reviewed_commit), changed_paths)
            and report["predicted_reviewers"] == _predicted_reviewers(changed_paths)
            and report["optional_surfaces"] == ["ca-sandbox", "ca-new-skill", "ca-watch", "ca-tribunal"]
        )
    if profile == "feature_capstone":
        return _u07_capstone(context)
    return False


def _valid_offline_p02_receipt(context: _SemanticContext, path: str) -> bool:
    try:
        raw = _git_blob(context.root, context.attempt.head, path)
        if raw is None:
            return False
        object_format = "sha1" if len(context.attempt.base) == 40 else "sha256"
        receipt = _parse_p02_receipt_bytes(raw, object_format=object_format)
        store = open_existing_p02_store(context.root, base=context.attempt.base)
        if store is None:
            return False
        identity = P02AttemptIdentity(
            context.attempt.number,
            context.attempt.branch,
            context.attempt.prepared,
            context.attempt.head,
        )
        return validate_p02_checkpoint(context.root, store, identity, receipt)
    except (OSError, TypeError, ValueError):
        return False


def evaluate_checkpoint(
    root: Path, lab_id: str, *, require_current_attempt: bool = True
) -> CheckpointResult:
    if lab_id not in LAB_INVENTORY:
        raise CheckpointError("checkpoint ID is not in the exact Academy inventory.")
    repository = Path(root).resolve()
    try:
        repository = repository_root(repository)
        validate_repository_git_config(repository)
        attempt = _discover_attempt(
            repository, lab_id, require_current=require_current_attempt
        )
        contracts, contract, definition = _load_attempt_definition(
            repository, attempt.base, lab_id
        )
        prepared_ok = _validate_prepare(repository, contract, attempt)
        digest_paths = (
            "academy/catalog.json",
            f"academy/scenarios/{lab_id}/manifest.json",
            contract.checkpoint_path,
            contract.source_path,
            "academy/contracts.json",
        )
        base_namespace = _control_namespace_paths(repository, attempt.base)
        head_namespace = _control_namespace_paths(repository, attempt.head)
        control_paths = tuple(dict.fromkeys((*base_namespace, contract.source_path)))
        control_diff = run_git(
            repository,
            ["diff", "--quiet", attempt.base, "--", *control_paths],
            check=False,
        )
        control_status = run_git(
            repository,
            [
                "status",
                "--porcelain",
                "--untracked-files=all",
                "--",
                "academy_engine",
                "scripts/academy.py",
                "academy/catalog.json",
                "academy/catalog.schema.json",
                "academy/contracts.json",
                "academy/checkpoint.schema.json",
                "academy/receipt.schema.json",
                "academy/scenario.schema.json",
                "academy/checkpoints",
                "academy/scenarios",
                contract.source_path,
            ],
            check=False,
        )
        control_worktree_clean = bool(
            control_diff.returncode == 0
            and control_status.returncode == 0
            and not control_status.stdout
        )
        source_blobs = [
            _git_blob(repository, attempt.base, path) for path in digest_paths
        ]
        source_integrity = bool(
            all(blob is not None for blob in source_blobs)
            and base_namespace == head_namespace
            and run_git(
                repository,
                [
                    "diff",
                    "--no-ext-diff",
                    "--quiet",
                    attempt.base,
                    attempt.head,
                    "--",
                    *control_paths,
                ],
                check=False,
            ).returncode
            == 0
            and control_worktree_clean
        )
        catalog_digest, manifest_digest, definition_digest, source_digest, contract_digest = (
            _raw_digest(blob) if blob is not None else ""
            for blob in source_blobs
        )
        passed: list[str] = []
        if prepared_ok:
            passed.append("prepared_scenario")
        if source_integrity:
            passed.append("source_integrity")
        context = _SemanticContext(repository, attempt, definition.predicates[0])
        for predicate in definition.predicates:
            ok = _semantic(context)
            if ok:
                passed.append(predicate.id)
        required = ("prepared_scenario", "source_integrity", *(item.id for item in definition.predicates))
        failed = tuple(item for item in required if item not in passed)
        passed_tuple = tuple(passed)
    except Exception:
        definition = locals().get("definition")
        attempt = locals().get("attempt")
        catalog_digest = manifest_digest = source_digest = contract_digest = ""
        definition_digest = definition.digest if isinstance(definition, Checkpoint) else ""
        passed_tuple = ()
        failed = ("prepared_scenario", "source_integrity", "semantic_evidence")
    payload = {
        "lab_id": lab_id,
        "attempt": attempt.branch if isinstance(attempt, _Attempt) else "",
        "prepared_commit": attempt.prepared if isinstance(attempt, _Attempt) else "",
        "base_commit": attempt.base if isinstance(attempt, _Attempt) else "",
        "head_commit": attempt.head if isinstance(attempt, _Attempt) else "",
        "definition": definition_digest,
        "manifest": manifest_digest,
        "source": source_digest,
        "contract": contract_digest,
        "catalog": catalog_digest,
        "passed": not failed,
        "passed_predicates": passed_tuple,
        "failed_predicates": failed,
    }
    return CheckpointResult(
        lab_id,
        not failed,
        definition_digest,
        sha256(payload),
        passed_tuple,
        failed,
        catalog_digest,
        manifest_digest,
        source_digest,
        contract_digest,
        attempt.branch if isinstance(attempt, _Attempt) else "",
        attempt.prepared if isinstance(attempt, _Attempt) else "",
        attempt.base if isinstance(attempt, _Attempt) else "",
        attempt.head if isinstance(attempt, _Attempt) else "",
    )
