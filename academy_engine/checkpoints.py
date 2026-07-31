"""Fail-closed, repository-derived Academy checkpoint evaluation."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from academy_engine.command import run_git
from academy_engine.paths import PathBoundaryError, ensure_within

_TYPES = frozenset({"file_exists", "file_contains", "json_equals", "git_branch", "git_ancestor", "command_success", "audit_contains"})
_MAX_COMMAND_ARGS = 16
_MAX_OUTPUT = 8192

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
    if set(data) != {"schema_version", "id", "predicates"} or data.get("schema_version") != 1: raise CheckpointError("checkpoint schema is invalid.")
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
        else: allowed |= {"argv", "timeout_seconds"}
        if set(item) != allowed: raise CheckpointError("checkpoint predicate has unknown or missing keys.")
        if kind in {"file_exists", "audit_contains", "file_contains", "json_equals"}: _safe_path(item["path"], "predicate path")
        if kind == "file_contains" and (not isinstance(item["text"], str) or not item["text"]): raise CheckpointError("file_contains text must be non-empty.")
        if kind == "json_equals" and (not isinstance(item["key"], str) or not item["key"]): raise CheckpointError("json_equals key must be non-empty.")
        if kind == "git_branch": _id(item["branch"], "branch")
        if kind == "git_ancestor": _hash(item["ancestor"], "ancestor"); _hash(item["descendant"], "descendant")
        if kind == "command_success":
            argv = item["argv"]; timeout = item["timeout_seconds"]
            if not isinstance(argv, list) or not argv or len(argv) > _MAX_COMMAND_ARGS or not all(isinstance(x, str) and x and len(x) <= 256 for x in argv) or type(timeout) is not int or not 1 <= timeout <= 10: raise CheckpointError("command predicate must be bounded argument-array execution.")
        predicates.append(Predicate(ident, kind, {key: value for key, value in item.items() if key not in {"id", "type"}}))
    return Checkpoint(lab_id, sha256(data), tuple(predicates))

def _text(root: Path, relative: str) -> str | None:
    try:
        path = ensure_within(root, Path(relative))
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 1_000_000: return None
        return path.read_text(encoding="utf-8", errors="surrogateescape")
    except (OSError, PathBoundaryError): return None

def _run(argv: list[str], root: Path, timeout: int) -> bool:
    environment = {key: os.environ[key] for key in ("SystemRoot", "WINDIR", "PATH", "PATHEXT", "COMSPEC") if key in os.environ}
    try:
        complete = subprocess.run(argv, cwd=root, shell=False, encoding="utf-8", errors="surrogateescape", text=True, capture_output=True, timeout=timeout, env=environment, check=False)
        return complete.returncode == 0 and len(complete.stdout) <= _MAX_OUTPUT and len(complete.stderr) <= _MAX_OUTPUT
    except (OSError, subprocess.TimeoutExpired): return False

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
    if predicate.type == "command_success": return _run(list(data["argv"]), root, int(data["timeout_seconds"]))
    try:
        if predicate.type == "git_branch": return run_git(root, ["branch", "--show-current"]).stdout.strip() == data["branch"]
        return run_git(root, ["merge-base", "--is-ancestor", str(data["ancestor"]), str(data["descendant"])], check=False).returncode == 0
    except Exception: return False

def evaluate_checkpoint(root: Path, lab_id: str) -> CheckpointResult:
    repository = Path(root).resolve(); definition = load_checkpoint(repository / "academy" / "checkpoints" / f"{lab_id}.json")
    if definition.id != lab_id: raise CheckpointError("checkpoint ID does not match requested lab.")
    passed = tuple(item.id for item in definition.predicates if _evaluate(repository, item)); failed = tuple(item.id for item in definition.predicates if item.id not in passed)
    catalog_digest = hashlib.sha256(canonical_json(json.loads((repository / "academy" / "catalog.json").read_text(encoding="utf-8")))).hexdigest()
    digest = sha256({"lab_id": lab_id, "definition": definition.digest, "catalog": catalog_digest, "passed": not failed, "passed_predicates": passed, "failed_predicates": failed})
    return CheckpointResult(lab_id, not failed, definition.digest, digest, passed, failed)
