"""Fail-closed, repository-derived Academy checkpoint evaluation."""
from __future__ import annotations

import hashlib
import json
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from academy_engine.catalog import Catalog, load_manifest
from academy_engine.command import repository_root, run_git, validate_repository_git_config
from academy_engine.remotes import RemoteSafetyError, validate_training_remotes

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
_PROFILES = {
    "remote_doctor": ("artifact",),
    "orientation": ("artifact", "context"),
    "task_transition": ("board", "audit", "task_id"),
    "tdd_history": ("code", "test"),
    "approved_spec_plan": ("spec", "plan", "board"),
    "pr_receipt": ("receipt",),
    "accepted_adr": ("adr", "decision_log"),
    "dependency_review": ("review", "project"),
    "checkpoint_remediation": ("report",),
    "provenance_recovery": ("context", "handoff"),
    "stride_model": ("model", "target"),
    "hygiene_snapshot": ("snapshot",),
    "sprint_decisions": ("spec", "plan", "sprint_log"),
    "override_audit_metrics": ("overrides", "audit", "metrics"),
    "refactor_chore_release": ("code", "test", "chore", "tag_prefix"),
    "initialized_fixture": ("workspace", "report"),
    "debug_spike_conflict": ("debug", "spike", "conflict"),
    "preview_evidence": ("report",),
    "capstone": ("spec", "plan", "adr", "review", "pr_receipt", "audit", "code", "test"),
}
_REMOTE_PROFILES = frozenset({"remote_doctor", "pr_receipt", "refactor_chore_release", "capstone"})
_CANONICAL_PREDICATES: dict[str, tuple[str, str, dict[str, object]]] = {
    "F01-fork-clone-doctor": ("remote_and_doctor", "remote_doctor", {"artifact": ".codearbiter/reports/academy/F01-doctor.json"}),
    "F02-orient-to-state": ("live_context_orientation", "orientation", {"artifact": ".codearbiter/reports/academy/F02-orientation.json", "context": ".codearbiter/CONTEXT.md"}),
    "F03-work-the-board": ("board_transition_and_audit", "task_transition", {"board": ".codearbiter/open-tasks.md", "audit": ".codearbiter/gate-events.log", "task_id": "academy.feature.0001"}),
    "F04-fix-with-evidence": ("red_then_fix_history", "tdd_history", {"code": "workshop_queue/service.py", "test": "tests/test_service.py"}),
    "P01-feature-through-plan": ("approved_spec_plan_task", "approved_spec_plan", {"spec": ".codearbiter/specs/academy-feature.md", "plan": ".codearbiter/plans/academy-feature.md", "board": ".codearbiter/open-tasks.md"}),
    "P02-commit-review-pr": ("review_pr_commit_range", "pr_receipt", {"receipt": ".codearbiter/reports/academy/P02-pr-receipt.json"}),
    "P03-record-an-adr": ("accepted_adr_and_log", "accepted_adr", {"adr": ".codearbiter/decisions/0003-academy-lab.md", "decision_log": ".codearbiter/decisions/decision-log.md"}),
    "P04-review-a-dependency": ("strict_dependency_review", "dependency_review", {"review": ".codearbiter/reports/academy/P04-dependency-review.md", "project": "pyproject.toml"}),
    "P05-checkpoint-remediation": ("finding_remediation_link", "checkpoint_remediation", {"report": ".codearbiter/checkpoints/P05-academy.json"}),
    "P06-context-drift-recovery": ("provenance_drift_recovery", "provenance_recovery", {"context": ".codearbiter/CONTEXT.md", "handoff": ".codearbiter/reports/academy/P06-recovery.json"}),
    "P07-threat-model": ("stride_model", "stride_model", {"model": ".codearbiter/reports/academy/P07-threat-model.md", "target": "academy_engine/paths.py"}),
    "P08-repository-hygiene": ("live_ref_hygiene", "hygiene_snapshot", {"snapshot": ".codearbiter/reports/academy/P08-hygiene.json"}),
    "U01-autonomous-sprint": ("approved_sprint_decisions", "sprint_decisions", {"spec": ".codearbiter/specs/academy-sprint.md", "plan": ".codearbiter/plans/academy-sprint.md", "sprint_log": ".codearbiter/sprint-log.md"}),
    "U02-override-audit-metrics": ("linked_override_audit_metrics", "override_audit_metrics", {"overrides": ".codearbiter/overrides.log", "audit": ".codearbiter/reports/academy/U02-audit.md", "metrics": ".codearbiter/reports/academy/U02-metrics.json"}),
    "U03-refactor-chore-release": ("refactor_chore_release", "refactor_chore_release", {"code": "workshop_queue/store.py", "test": "tests/test_store.py", "chore": "README.md", "tag_prefix": "academy-v"}),
    "U04-initialize-projects": ("initialized_secondary_fixture", "initialized_fixture", {"workspace": ".academy/workspaces/U04-secondary", "report": ".codearbiter/reports/academy/U04-initialization.md"}),
    "U05-debug-spike-conflict": ("debug_spike_conflict_artifacts", "debug_spike_conflict", {"debug": ".codearbiter/reports/academy/U05-debug.md", "spike": ".codearbiter/reports/academy/U05-spike.md", "conflict": ".codearbiter/reports/academy/U05-conflict.md"}),
    "U06-preview-and-advanced-surfaces": ("preview_advanced_evidence", "preview_evidence", {"report": ".codearbiter/reports/academy/U06-preview.json"}),
    "U07-capstone": ("capstone_governed_range", "capstone", {"spec": ".codearbiter/specs/capstone.md", "plan": ".codearbiter/plans/capstone.md", "adr": ".codearbiter/decisions/0004-capstone.md", "review": ".codearbiter/reports/academy/U07-review.json", "pr_receipt": ".codearbiter/reports/academy/U07-pr-receipt.json", "audit": ".codearbiter/reports/academy/U07-audit.json", "code": "workshop_queue/service.py", "test": "tests/test_service.py"}),
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
    if not isinstance(entries, list) or not entries:
        raise CheckpointError("checkpoint predicates must be a non-empty list.")
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


def _path_commits(root: Path, start: str, head: str, *paths: str) -> tuple[str, ...]:
    result = run_git(
        root,
        ["log", "--reverse", "--format=%H", f"{start}..{head}", "--", *paths],
        check=False,
    )
    return tuple(line for line in result.stdout.splitlines() if _SHA40.fullmatch(line))


def _commit_paths(root: Path, commit: str) -> tuple[str, ...]:
    return tuple(
        run_git(
            root,
            ["diff-tree", "--no-commit-id", "--name-only", "-r", commit],
            check=False,
        ).stdout.splitlines()
    )


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
    secret = re.compile(
        rb"(?i)(?:ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|"
        rb"sk-[A-Za-z0-9]{20,}|AKIA[A-Z0-9]{16}|"
        rb"https?://[^/\s:@]+:[^@\s/]+@)"
    )
    return all(
        (blob := _git_blob(root, commit, path)) is not None and secret.search(blob) is None
        for path in paths
    )


def _discover_attempt(root: Path, lab_id: str) -> _Attempt:
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
    selected = (
        (int(current_match.group("number")), current)
        if current_match is not None and current_match.group("lab") == lab_id
        else max(choices)
    )
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
    for removal in manifest.removals:
        if _git_blob(root, attempt.base, removal) is None or _git_blob(root, attempt.prepared, removal) is not None:
            return False
    return True


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
    except (RemoteSafetyError, Exception):
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


@dataclass(frozen=True)
class _SemanticContext:
    root: Path
    attempt: _Attempt
    predicate: Predicate


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


def _semantic(context: _SemanticContext) -> bool:
    data = context.predicate.data
    profile = str(data["profile"])
    root, attempt = context.root, context.attempt
    if profile in _REMOTE_PROFILES and not _remote_safe(root):
        return False
    if profile == "remote_doctor":
        artifact = _json(root, attempt.head, str(data["artifact"]))
        return bool(
            artifact
            and _changed(root, attempt.prepared, attempt.head, str(data["artifact"]))
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
        match = re.search(r"(?m)^stage:\s*(\d+)\s*$", context_blob.decode("utf-8", "surrogateescape"))
        return bool(
            set(artifact) == {"schema_version", "context_path", "context_sha256", "stage"}
            and _version(artifact["schema_version"], 1)
            and artifact["context_path"] == context_path
            and artifact["context_sha256"] == _raw_digest(context_blob)
            and match
            and artifact["stage"] == int(match.group(1))
        )
    if profile == "task_transition":
        board, audit, task_id = str(data["board"]), str(data["audit"]), str(data["task_id"])
        before, after = _text(root, attempt.prepared, board), _changed_document(context, board)
        appended = _changed_document(context, audit)
        same_commit = set(_path_commits(root, attempt.prepared, attempt.head, board)) & set(
            _path_commits(root, attempt.prepared, attempt.head, audit)
        )
        return bool(
            before
            and after
            and appended
            and re.search(rf"(?m)^- \[ \] {re.escape(task_id)}\b", before)
            and re.search(rf"(?m)^- \[x\] {re.escape(task_id)}\b", after)
            and task_id in appended
            and same_commit
        )
    if profile == "tdd_history":
        code, test = str(data["code"]), str(data["test"])
        code_commits = _path_commits(root, attempt.prepared, attempt.head, code)
        test_commits = _path_commits(root, attempt.prepared, attempt.head, test)
        return bool(
            code_commits
            and test_commits
            and code_commits[0] != test_commits[0]
            and run_git(
                root, ["merge-base", "--is-ancestor", test_commits[0], code_commits[-1]], check=False
            ).returncode == 0
        )
    if profile == "approved_spec_plan":
        # Task 8 supplies an independently recomputable approval predicate and fixture.
        # Learner-authored ``status: approved`` prose is never sufficient evidence.
        return False
    if profile == "pr_receipt":
        return _valid_pr_receipt(context, str(data["receipt"]))
    if profile == "accepted_adr":
        adr, decision_log = str(data["adr"]), str(data["decision_log"])
        adr_text, log_text = _changed_document(context, adr), _changed_document(context, decision_log)
        adr_id = Path(adr).stem.split("-", 1)[0]
        return bool(
            _headings(adr_text, ("Context", "Decision", "Consequences"))
            and "status: accepted" in (adr_text or "").casefold()
            and log_text
            and adr_id in log_text
        )
    if profile == "dependency_review":
        review = _changed_document(context, str(data["review"]))
        project = str(data["project"])
        project_blob = _git_blob(root, attempt.prepared, project)
        return bool(
            _headings(review, ("Candidate", "Provenance", "License", "Supply chain", "SMARTS", "Decision"))
            and project_blob is not None
            and _git_blob(root, attempt.head, project) == project_blob
            and f"Project-SHA256: {_raw_digest(project_blob)}" in (review or "")
        )
    if profile == "checkpoint_remediation":
        report = _json(root, attempt.head, str(data["report"]))
        if not report or not _changed(root, attempt.prepared, attempt.head, str(data["report"])):
            return False
        required = {"schema_version", "finding_id", "finding_commit", "remediation_commit", "paths", "status"}
        if (
            set(report) != required
            or not _version(report["schema_version"], 1)
            or report["status"] != "remediated"
        ):
            return False
        finding, remediation = report["finding_commit"], report["remediation_commit"]
        paths = report["paths"]
        if (
            not isinstance(finding, str)
            or not _SHA40.fullmatch(finding)
            or not isinstance(remediation, str)
            or not _SHA40.fullmatch(remediation)
            or not isinstance(report["finding_id"], str)
            or not isinstance(paths, list)
            or len(paths) < 2
        ):
            return False
        try:
            safe_paths = [_safe_path(path, "path") for path in paths]
        except CheckpointError:
            return False
        if len(set(safe_paths)) != len(safe_paths):
            return False
        finding_paths = set(
            run_git(
                root, ["diff-tree", "--no-commit-id", "--name-only", "-r", finding],
                check=False,
            ).stdout.splitlines()
        )
        remediation_paths = set(
            run_git(
                root, ["diff-tree", "--no-commit-id", "--name-only", "-r", remediation],
                check=False,
            ).stdout.splitlines()
        )
        return bool(
            all(
                _changed(root, attempt.prepared, attempt.head, path)
                for path in safe_paths
            )
            and set(safe_paths).issubset(finding_paths | remediation_paths)
            and finding_paths
            and remediation_paths
            and bool(finding_paths & remediation_paths)
            and finding != remediation
            and finding != attempt.prepared
            and remediation != attempt.head
            and run_git(root, ["merge-base", "--is-ancestor", attempt.prepared, str(finding)], check=False).returncode == 0
            and run_git(root, ["merge-base", "--is-ancestor", str(finding), str(remediation)], check=False).returncode == 0
            and run_git(root, ["merge-base", "--is-ancestor", str(remediation), attempt.head], check=False).returncode == 0
        )
    if profile == "provenance_recovery":
        context_path, handoff_path = str(data["context"]), str(data["handoff"])
        handoff = _json(root, attempt.head, handoff_path)
        before, after = _git_blob(root, attempt.prepared, context_path), _git_blob(root, attempt.head, context_path)
        if not handoff or before is None or after is None or before == after:
            return False
        required = {"schema_version", "context_before_sha256", "context_after_sha256", "preserved_path"}
        preserved = handoff.get("preserved_path")
        preserved_before = (
            _git_blob(root, attempt.prepared, preserved)
            if isinstance(preserved, str) and _safe_path(preserved, "preserved_path")
            else None
        )
        return bool(
            set(handoff) == required
            and _version(handoff["schema_version"], 1)
            and _changed(root, attempt.prepared, attempt.head, handoff_path)
            and handoff["context_before_sha256"] == _raw_digest(before)
            and handoff["context_after_sha256"] == _raw_digest(after)
            and isinstance(preserved, str)
            and preserved_before is not None
            and preserved_before == _git_blob(root, attempt.head, preserved)
        )
    if profile == "stride_model":
        model = _changed_document(context, str(data["model"]))
        target_blob = _git_blob(root, attempt.head, str(data["target"]))
        return bool(
            _headings(model, ("Scope", "Spoofing", "Tampering", "Repudiation", "Information disclosure", "Denial of service", "Elevation of privilege", "Mitigations"))
            and target_blob is not None
            and f"Target-SHA256: {_raw_digest(target_blob)}" in (model or "")
        )
    if profile == "hygiene_snapshot":
        snapshot = _json(root, attempt.head, str(data["snapshot"]))
        if not snapshot or not _changed(root, attempt.prepared, attempt.head, str(data["snapshot"])):
            return False
        if (
            set(snapshot) != {"schema_version", "refs", "worktrees"}
            or not _version(snapshot["schema_version"], 1)
        ):
            return False
        expected_refs, expected_worktrees = _live_hygiene_inventory(root, attempt)
        return snapshot["refs"] == expected_refs and snapshot["worktrees"] == expected_worktrees
    if profile == "sprint_decisions":
        # Task 9 supplies the governed sprint approval/decision predicate and fixture.
        return False
    if profile == "override_audit_metrics":
        overrides, audit, metrics = (str(data[key]) for key in ("overrides", "audit", "metrics"))
        override_text = _changed_document(context, overrides)
        audit_text = _changed_document(context, audit)
        metric_data = _json(root, attempt.head, metrics)
        if not override_text or not audit_text or not metric_data or not _changed(root, attempt.prepared, attempt.head, metrics):
            return False
        new_lines = [
            line for line in override_text.splitlines()
            if "| BY:" in line and "| GATE:" in line and "| REASON:" in line
        ]
        return bool(
            new_lines
            and all(hashlib.sha256(line.encode("utf-8")).hexdigest() in audit_text for line in new_lines)
            and set(metric_data) == {"schema_version", "override_count", "low_confidence_count"}
            and _version(metric_data["schema_version"], 1)
            and metric_data["override_count"] == len(new_lines)
            and type(metric_data["low_confidence_count"]) is int
            and metric_data["low_confidence_count"] >= 0
        )
    if profile == "refactor_chore_release":
        code, test, chore = (str(data[key]) for key in ("code", "test", "chore"))
        commits = [
            _path_commits(root, attempt.prepared, attempt.head, code),
            _path_commits(root, attempt.prepared, attempt.head, test),
            _path_commits(root, attempt.prepared, attempt.head, chore),
        ]
        tags = run_git(root, ["tag", "--points-at", attempt.head], check=False).stdout.splitlines()
        return bool(
            all(commits)
            and len({item[0] for item in commits}) >= 2
            and any(tag.startswith(str(data["tag_prefix"])) for tag in tags)
        )
    if profile == "initialized_fixture":
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
    if profile == "debug_spike_conflict":
        debug, spike, conflict = (_changed_document(context, str(data[key])) for key in ("debug", "spike", "conflict"))
        spike_refs = run_git(
            root,
            ["for-each-ref", "--format=%(refname:short)%00%(objectname)", "refs/heads/academy/spike/U05-"],
            check=False,
        ).stdout.splitlines()
        linked_spike = any(
            "\x00" in item
            and item.split("\x00", 1)[0] in (spike or "")
            and item.split("\x00", 1)[1] in (spike or "")
            for item in spike_refs
        )
        return bool(
            _headings(debug, ("Symptom", "Root cause", "Disposition"))
            and _headings(spike, ("Question", "Experiment", "Finding", "Disposable branch"))
            and _headings(conflict, ("Rule A", "Rule B", "Resolution", "Attribution"))
            and linked_spike
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
    if profile == "capstone":
        # Task 9 supplies the complete positive capstone predicate and fixture.
        return False
    return False


def _valid_pr_receipt(context: _SemanticContext, path: str) -> bool:
    receipt = _json(context.root, context.attempt.head, path)
    if not receipt or not _changed(context.root, context.attempt.prepared, context.attempt.head, path):
        return False
    required = {
        "schema_version", "receipt_id", "mode", "repository", "branch",
        "prepared_base", "work_head", "commits", "review_status", "pr_reference",
    }
    if set(receipt) != required or not _version(receipt["schema_version"], 1):
        return False
    try:
        remotes = validate_training_remotes(context.root, require_push_safe=True)
    except RemoteSafetyError:
        return False
    if remotes.origin is None:
        return False
    origin_identity = f"{remotes.origin.owner}/{remotes.origin.repository}"
    commits = receipt["commits"]
    work_head = receipt["work_head"]
    expected = run_git(
        context.root,
        ["rev-list", "--reverse", f"{context.attempt.prepared}..{work_head}"],
        check=False,
    ).stdout.splitlines()
    receipt_commits = _path_commits(
        context.root, context.attempt.prepared, context.attempt.head, path
    )
    receipt_commit = receipt_commits[0] if len(receipt_commits) == 1 else ""
    receipt_parent = (
        run_git(
            context.root, ["rev-parse", f"{receipt_commit}^"], check=False
        ).stdout.strip()
        if receipt_commit
        else ""
    )
    reference = receipt["pr_reference"]
    github_reference = (
        re.fullmatch(
            r"https://github\.com/(?P<owner>[A-Za-z0-9_.-]+)/"
            r"(?P<repository>arbiter-academy)/pull/[1-9][0-9]*",
            reference,
        )
        if isinstance(reference, str)
        else None
    )
    reference_ok = (
        reference == f"local-pr:{work_head[:12]}"
        if receipt["mode"] == "offline-local" and isinstance(work_head, str)
        else bool(
            receipt["mode"] == "github"
            and github_reference is not None
            and f"{github_reference.group('owner')}/{github_reference.group('repository')}".casefold()
            == origin_identity.casefold()
        )
    )
    return bool(
        isinstance(receipt["receipt_id"], str)
        and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{7,63}", receipt["receipt_id"])
        and receipt["mode"] in {"offline-local", "github"}
        and isinstance(receipt["repository"], str)
        and re.fullmatch(r"[A-Za-z0-9_.-]+/arbiter-academy", receipt["repository"])
        and receipt["repository"].casefold() == origin_identity.casefold()
        and receipt["branch"] == context.attempt.branch
        and receipt["prepared_base"] == context.attempt.prepared
        and isinstance(work_head, str)
        and _SHA40.fullmatch(work_head)
        and isinstance(commits, list)
        and bool(commits)
        and work_head != context.attempt.prepared
        and commits == expected
        and receipt_parent == work_head
        and receipt_commit == context.attempt.head
        and set(_commit_paths(context.root, receipt_commit)) == {path}
        and receipt["review_status"] == "cleared"
        and reference_ok
        and run_git(context.root, ["merge-base", "--is-ancestor", str(work_head), context.attempt.head], check=False).returncode == 0
    )


def evaluate_checkpoint(root: Path, lab_id: str) -> CheckpointResult:
    if lab_id not in LAB_INVENTORY:
        raise CheckpointError("checkpoint ID is not in the exact Academy inventory.")
    repository = Path(root).resolve()
    try:
        repository = repository_root(repository)
        validate_repository_git_config(repository)
        attempt = _discover_attempt(repository, lab_id)
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
        control_worktree_clean = (
            run_git(
                repository,
                ["diff", "--quiet", attempt.base, "--", *control_paths],
                check=False,
            ).returncode
            == 0
            and not run_git(
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
            ).stdout
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
