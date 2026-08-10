"""Fresh, canonical, non-sensitive checkpoint progress documents."""
from __future__ import annotations

import json
import os
import re
import stat
import tempfile
from pathlib import Path

from academy_engine.checkpoints import (
    LAB_INVENTORY,
    CheckpointResult,
    canonical_json,
    evaluate_checkpoint,
)


def _digest(value: object) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError("checkpoint result has an invalid bound digest.")
    return value


def _valid_existing_entry(value: object) -> bool:
    if not isinstance(value, dict) or set(value) != {
        "id", "attempt", "attempt_head", "prepared_commit", "catalog_sha256",
        "definition_sha256", "manifest_sha256", "source_sha256",
        "contract_sha256", "result_sha256",
    }:
        return False
    lab_id = value["id"]
    if lab_id not in LAB_INVENTORY:
        return False
    if not re.fullmatch(rf"academy/{re.escape(lab_id)}/[1-9][0-9]*", str(value["attempt"])):
        return False
    if not all(
        isinstance(value[field], str)
        and len(value[field]) == 40
        and all(character in "0123456789abcdef" for character in value[field])
        for field in ("attempt_head", "prepared_commit")
    ):
        return False
    return all(
        isinstance(value[field], str)
        and len(value[field]) == 64
        and all(character in "0123456789abcdef" for character in value[field])
        for field in (
            "catalog_sha256", "definition_sha256", "manifest_sha256",
            "source_sha256", "contract_sha256", "result_sha256",
        )
    )


def _reject_unsafe_progress_path(progress_path: Path) -> None:
    if ".." in progress_path.parts:
        raise ValueError("unsafe progress path contains a lexical parent escape.")
    absolute = Path(os.path.abspath(progress_path))
    current = Path(absolute.anchor)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    for part in absolute.parts[1:]:
        current /= part
        try:
            details = current.lstat()
        except FileNotFoundError:
            break
        except OSError as error:
            raise ValueError("unsafe progress path could not be inspected.") from error
        if stat.S_ISLNK(details.st_mode) or bool(
            getattr(details, "st_file_attributes", 0) & reparse_flag
        ):
            raise ValueError("unsafe progress path contains a symlink or reparse point.")
        if current == absolute.parent and not stat.S_ISDIR(details.st_mode):
            raise ValueError("unsafe progress path parent is not a directory.")
        if current == absolute and (
            not stat.S_ISREG(details.st_mode) or details.st_nlink != 1
        ):
            raise ValueError("unsafe progress path is not an unshared regular file.")


def record_checkpoint(progress_path: Path, result: CheckpointResult) -> None:
    """Recompute and atomically upsert one fully-bound checkpoint result."""
    if progress_path.name != "progress.json" or progress_path.parent.name != ".academy":
        raise ValueError("progress path must be the canonical Academy progress document.")
    _reject_unsafe_progress_path(progress_path)
    if result.lab_id not in LAB_INVENTORY:
        raise ValueError("checkpoint result is not a known Academy lab.")
    recomputed = evaluate_checkpoint(progress_path.parent.parent, result.lab_id)
    if recomputed != result or not recomputed.passed:
        raise ValueError("checkpoint result is not fresh repository evidence.")
    entry = {
        "id": result.lab_id,
        "attempt": result.attempt,
        "attempt_head": result.head_commit,
        "prepared_commit": result.prepared_commit,
        "catalog_sha256": _digest(result.catalog_digest),
        "definition_sha256": _digest(result.definition_digest),
        "manifest_sha256": _digest(result.manifest_digest),
        "source_sha256": _digest(result.source_digest),
        "contract_sha256": _digest(result.contract_digest),
        "result_sha256": _digest(result.digest),
    }
    entries: dict[str, dict[str, object]] = {}
    if progress_path.exists():
        try:
            current = json.loads(progress_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("existing progress document is invalid.") from error
        if not isinstance(current, dict) or set(current) != {"schema_version", "checkpoints"}:
            raise ValueError("existing progress document is invalid.")
        if type(current["schema_version"]) is not int or current["schema_version"] != 2:
            raise ValueError("existing progress document is invalid.")
        if not isinstance(current["checkpoints"], list):
            raise ValueError("existing progress document is invalid.")
        for item in current["checkpoints"]:
            if not _valid_existing_entry(item):
                raise ValueError("existing progress document is invalid.")
            if item["id"] in entries:
                raise ValueError("existing progress document has duplicate IDs.")
            entries[item["id"]] = item
    entries[result.lab_id] = entry
    payload = {
        "schema_version": 2,
        "checkpoints": [entries[lab_id] for lab_id in LAB_INVENTORY if lab_id in entries],
    }
    progress_path.parent.mkdir(parents=True, exist_ok=True)
    _reject_unsafe_progress_path(progress_path)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".progress.", suffix=".tmp", dir=progress_path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(canonical_json(payload))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, progress_path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
