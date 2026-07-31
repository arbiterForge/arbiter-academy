"""Fail-closed, repository-derived Academy checkpoint evaluation."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from academy_engine.command import run_git
from academy_engine.paths import PathBoundaryError, ensure_within
from academy_engine.catalog import Catalog

_TYPES = frozenset({"file_exists", "file_contains", "json_equals", "git_branch", "git_ancestor", "audit_contains"})
LAB_CONTRACT = {
    "F01-fork-clone-doctor": ".codearbiter/CONTEXT.md", "F02-orient-to-state": ".codearbiter/open-tasks.md", "F03-work-the-board": ".codearbiter/open-tasks.md", "F04-fix-with-evidence": "workshop_queue/service.py",
    "P01-feature-through-plan": ".codearbiter/plans/ticket-assignment.md", "P02-commit-review-pr": ".codearbiter/sprint-log.md", "P03-record-an-adr": ".codearbiter/decisions/0001-json-storage-boundary.md", "P04-review-a-dependency": ".codearbiter/security-controls.md", "P05-checkpoint-remediation": ".codearbiter/checkpoints/2026-07-20-baseline.md", "P06-context-drift-recovery": ".codearbiter/CONTEXT.md", "P07-threat-model": ".codearbiter/security-controls.md", "P08-repository-hygiene": ".codearbiter/open-tasks.md",
    "U01-autonomous-sprint": ".codearbiter/sprint-log.md", "U02-override-audit-metrics": ".codearbiter/overrides.log", "U03-refactor-chore-release": ".codearbiter/tech-stack.md", "U04-initialize-projects": ".codearbiter/CONTEXT.md", "U05-debug-spike-conflict": ".codearbiter/open-questions.md", "U06-preview-and-advanced-surfaces": ".codearbiter/gate-events.log", "U07-capstone": ".codearbiter/reports/2026-07-20-baseline/summary.md",
}

class CheckpointError(ValueError):
    """A checkpoint definition or its evidence is invalid or unsafe."""

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

def canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")

def sha256(value: object) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()

def _obj(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict): raise CheckpointError(f"{label} must be an object.")
    return value

def _safe_path(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value or value.startswith("/") or ":" in value or any(x in {"", ".", ".."} for x in value.split("/")):
        raise CheckpointError(f"{label} must be a safe repository-relative path.")
    return value

def _id(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 96 or any(c.isspace() or ord(c) < 33 or ord(c) > 126 for c in value):
        raise CheckpointError(f"{label} must be a safe identifier.")
    return value

def _hash(value: object, label: str) -> str:
    if not isinstance(value, str) or len(value) != 40 or any(c not in "0123456789abcdef" for c in value): raise CheckpointError(f"{label} must be a lowercase Git SHA.")
    return value

def load_checkpoint(path: Path) -> Checkpoint:
    try: raw = path.read_text(encoding="utf-8"); data = _obj(json.loads(raw), "checkpoint")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error: raise CheckpointError("checkpoint could not be read.") from error
    if set(data) != {"schema_version", "id", "predicates"} or type(data.get("schema_version")) is not int or data.get("schema_version") != 1: raise CheckpointError("checkpoint schema is invalid.")
    lab_id = _id(data.get("id"), "checkpoint id")
    entries = data.get("predicates")
    if not isinstance(entries, list) or not entries: raise CheckpointError("checkpoint predicates must be a non-empty list.")
    predicates: list[Predicate] = []; ids: set[str] = set()
    for index, value in enumerate(entries):
        item = _obj(value, f"predicate {index}")
        if "id" not in item or "type" not in item: raise CheckpointError("predicate requires id and type.")
        ident = _id(item["id"], "predicate id")
        if ident in ids: raise CheckpointError("checkpoint has duplicate predicate IDs.")
        ids.add(ident); kind = item["type"]
        if kind not in _TYPES: raise CheckpointError("checkpoint has unsupported predicate type.")
        allowed = {"id", "type"}
        if kind in {"file_exists", "audit_contains"}: allowed |= {"path"}
        elif kind == "file_contains": allowed |= {"path", "text"}
        elif kind == "json_equals": allowed |= {"path", "key", "value"}
        elif kind == "git_branch": allowed |= {"branch"}
        elif kind == "git_ancestor": allowed |= {"ancestor", "descendant"}
        else: raise CheckpointError("checkpoint has unsupported predicate type.")
        if set(item) != allowed: raise CheckpointError("checkpoint predicate has unknown or missing keys.")
        if kind in {"file_exists", "audit_contains", "file_contains", "json_equals"}: _safe_path(item["path"], "predicate path")
        if kind == "file_contains" and (not isinstance(item["text"], str) or not item["text"]): raise CheckpointError("file_contains text must be non-empty.")
        if kind == "json_equals" and (not isinstance(item["key"], str) or not item["key"]): raise CheckpointError("json_equals key must be non-empty.")
        if kind == "git_branch": _id(item["branch"], "branch")
        if kind == "git_ancestor": _hash(item["ancestor"], "ancestor"); _hash(item["descendant"], "descendant")
        predicates.append(Predicate(ident, kind, {key: value for key, value in item.items() if key not in {"id", "type"}}))
    return Checkpoint(lab_id, sha256(data), tuple(predicates))

def _text(root: Path, relative: str) -> str | None:
    try:
        path = ensure_within(root, Path(relative))
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 1_000_000: return None
        return path.read_text(encoding="utf-8", errors="surrogateescape")
    except (OSError, PathBoundaryError): return None

def _evaluate(root: Path, predicate: Predicate) -> bool:
    data = predicate.data
    if predicate.type == "file_exists": return _text(root, str(data["path"])) is not None
    if predicate.type in {"file_contains", "audit_contains"}:
        text = _text(root, str(data["path"])); needle = str(data.get("text", "academy:"))
        return text is not None and needle in text
    if predicate.type == "json_equals":
        text = _text(root, str(data["path"]))
        try: return text is not None and json.loads(text).get(str(data["key"])) == data["value"]
        except json.JSONDecodeError: return False
    try:
        if predicate.type == "git_branch": return run_git(root, ["branch", "--show-current"]).stdout.strip() == data["branch"]
        return run_git(root, ["merge-base", "--is-ancestor", str(data["ancestor"]), str(data["descendant"])], check=False).returncode == 0
    except Exception: return False

def evaluate_checkpoint(root: Path, lab_id: str) -> CheckpointResult:
    if lab_id not in LAB_CONTRACT: raise CheckpointError("checkpoint ID is not in the exact Academy inventory.")
    repository = Path(root).resolve(); definition = load_checkpoint(repository / "academy" / "checkpoints" / f"{lab_id}.json")
    if definition.id != lab_id: raise CheckpointError("checkpoint ID does not match requested lab.")
    # A catalog fixture on its own is never learner evidence.  Every lab must
    # have a real, committed Academy attempt branch before its predicates count.
    attempt = f"academy/{lab_id}/1"
    try:
        attempt_exists = run_git(repository, ["show-ref", "--verify", "--quiet", f"refs/heads/{attempt}"], check=False).returncode == 0
        main_ancestor = attempt_exists and run_git(repository, ["merge-base", "--is-ancestor", "main", attempt], check=False).returncode == 0
        base = run_git(repository, ["merge-base", "main", attempt]).stdout.strip(); head = run_git(repository, ["rev-parse", "HEAD"]).stdout.strip()
        catalog = Catalog.load(repository / "academy" / "catalog.json"); lab = catalog.lab(lab_id)
        contract_bytes = run_git(repository, ["show", "HEAD:academy/contracts.json"]).stdout.encode("utf-8", "surrogateescape")
        contract_data = json.loads(contract_bytes)
        contract = next(item for item in contract_data["contracts"] if item["id"] == lab_id)
        if set(contract) != {"id", "title", "source_path", "checkpoint_path", "work_path", "governed_path", "corroboration_path", "outcome"} or contract["checkpoint_path"] != lab.checkpoint:
            raise CheckpointError("lab contract is invalid.")
        source_path = contract["source_path"]; work_path = contract["work_path"]; governed_path = contract["governed_path"]
        source_paths = ("academy/catalog.json", lab.manifest, lab.checkpoint, source_path, "academy/contracts.json")
        source_clean = all(run_git(repository, ["diff", "--quiet", base, "--", path], check=False).returncode == 0 for path in source_paths)
        raw = {path: run_git(repository, ["show", f"{base}:{path}"]).stdout.encode("utf-8", "surrogateescape") for path in source_paths}
        catalog_digest, manifest_digest, definition_digest, source_digest, contract_digest = (hashlib.sha256(raw[path]).hexdigest() for path in source_paths)
        changed_paths = run_git(repository, ["diff", "--name-only", f"{base}...{head}"], check=False).stdout.splitlines() if main_ancestor else []
        work_bytes = run_git(repository, ["show", f"HEAD:{work_path}"]).stdout.encode("utf-8", "surrogateescape") if work_path in changed_paths else b""
        governed_bytes = run_git(repository, ["show", f"HEAD:{governed_path}"]).stdout.encode("utf-8", "surrogateescape") if governed_path in changed_paths else b""
        prepared = any(line == f"academy: prepare {lab_id} attempt 1" for line in run_git(repository, ["log", "--format=%s", attempt]).stdout.splitlines())
        attempt_ancestor = run_git(repository, ["merge-base", "--is-ancestor", attempt, head], check=False).returncode == 0
        outcome = json.loads(work_bytes) if work_bytes else {}
        corroboration = run_git(repository, ["show", f"HEAD:{contract['corroboration_path']}"]).stdout
        committed_output = source_clean and prepared and attempt_ancestor and outcome == contract["outcome"] and json.loads(governed_bytes) == {"lab_id":lab_id,"status":"governed"} and bool(corroboration.strip())
    except Exception:
        attempt_exists = main_ancestor = committed_output = False; catalog_digest = manifest_digest = definition_digest = source_digest = contract_digest = ""
    passed_items = [item.id for item in definition.predicates if _evaluate(repository, item)]
    if attempt_exists and main_ancestor and committed_output:
        passed_items.extend(("prepared_attempt", "learner_evidence", "governed_output"))
    passed = tuple(passed_items); failed = tuple(item.id for item in definition.predicates if item.id not in passed)
    for required in ("prepared_attempt", "learner_evidence", "governed_output"):
        if required not in passed: failed += (required,)
    digest = sha256({"lab_id": lab_id, "definition": definition_digest or definition.digest, "manifest": manifest_digest, "source": source_digest, "contract": contract_digest, "catalog": catalog_digest, "passed": not failed, "passed_predicates": passed, "failed_predicates": failed})
    return CheckpointResult(lab_id, not failed, definition_digest or definition.digest, digest, passed, failed, catalog_digest, manifest_digest, source_digest, contract_digest)
