"""Build the bounded, learner-reviewed P06 recovery handoff."""

from __future__ import annotations

import hashlib
from pathlib import Path

from academy_engine.checkpoints import (
    CheckpointError,
    _P06_CONTEXT,
    _P06_CONTEXT_AFTER,
    _P06_NOTE,
    _P06_PROVENANCE,
    _P06_PROVENANCE_AFTER,
    _P06_SOURCE_OBJECT,
    _commit_paths,
    _discover_attempt,
    _git_blob,
    _p06_context_transition,
    _p06_provenance_transition,
    _p06_summary_format_contract,
    canonical_json,
)
from academy_engine.command import GitCommandError, repository_root, run_git
from academy_engine.paths import PathBoundaryError, ensure_within


P06_LAB_ID = "P06-context-drift-recovery"
_CONTEXT_PATH = ".codearbiter/CONTEXT.md"
_PROVENANCE_PATH = ".codearbiter/.provenance/CONTEXT.json"
_SOURCE_PATH = "workshop_queue/cli.py"
_PRESERVED_PATH = "docs/preserved-note.md"
_HANDOFF_PATH = ".codearbiter/reports/academy/P06-recovery.json"


class P06HandoffError(ValueError):
    """The current checkout cannot safely receive a P06 handoff candidate."""


def _failure() -> P06HandoffError:
    return P06HandoffError(
        "P06 handoff requires one clean prepared attempt followed by its exact correction commit."
    )


def _single_correction_commit(root: Path, prepared: str, head: str) -> str:
    result = run_git(root, ["rev-list", "--reverse", f"{prepared}..{head}"], check=False)
    commits = tuple(line for line in result.stdout.splitlines() if len(line) == 40)
    if result.returncode or len(commits) != 1 or commits[0] != head:
        raise _failure()
    recovery = commits[0]
    parents = run_git(root, ["rev-list", "--parents", "-n", "1", recovery], check=False)
    if parents.returncode or parents.stdout.split() != [recovery, prepared]:
        raise _failure()
    if set(_commit_paths(root, recovery)) != {_CONTEXT_PATH, _PROVENANCE_PATH}:
        raise _failure()
    return recovery


def _source_object(root: Path, ref: str) -> str:
    result = run_git(root, ["ls-tree", ref, "--", _SOURCE_PATH], check=False)
    fields = result.stdout.strip().split(None, 2)
    if result.returncode or len(fields) != 3:
        return ""
    object_id, tab, path = fields[2].partition("\t")
    if tab != "\t" or path != _SOURCE_PATH:
        return ""
    return object_id


def _payload(root: Path) -> dict[str, object]:
    attempt = _discover_attempt(root, P06_LAB_ID, require_current=True)
    recovery = _single_correction_commit(root, attempt.prepared, attempt.head)
    context_before = _git_blob(root, attempt.prepared, _CONTEXT_PATH)
    context_after = _git_blob(root, recovery, _CONTEXT_PATH)
    provenance_before = _git_blob(root, attempt.prepared, _PROVENANCE_PATH)
    provenance_after = _git_blob(root, recovery, _PROVENANCE_PATH)
    source = _git_blob(root, attempt.prepared, _SOURCE_PATH)
    note_before = _git_blob(root, attempt.prepared, _PRESERVED_PATH)
    note_after = _git_blob(root, recovery, _PRESERVED_PATH)
    if not (
        _p06_context_transition(context_before, context_after)
        and _p06_provenance_transition(provenance_before, provenance_after)
        and _source_object(root, attempt.prepared) == _P06_SOURCE_OBJECT
        and _p06_summary_format_contract(source)
        and note_before == _P06_NOTE
        and note_after == _P06_NOTE
        and _git_blob(root, recovery, _HANDOFF_PATH) is None
    ):
        raise _failure()
    return {
        "context_after_sha256": hashlib.sha256(_P06_CONTEXT_AFTER).hexdigest(),
        "context_before_sha256": hashlib.sha256(_P06_CONTEXT).hexdigest(),
        "context_path": _CONTEXT_PATH,
        "prepared_commit": attempt.prepared,
        "preserved_after_sha256": hashlib.sha256(_P06_NOTE).hexdigest(),
        "preserved_before_sha256": hashlib.sha256(_P06_NOTE).hexdigest(),
        "preserved_path": _PRESERVED_PATH,
        "provenance_after_sha256": hashlib.sha256(_P06_PROVENANCE_AFTER).hexdigest(),
        "provenance_before_sha256": hashlib.sha256(_P06_PROVENANCE).hexdigest(),
        "provenance_path": _PROVENANCE_PATH,
        "recovery_commit": recovery,
        "recovery_route": "re-scout",
        "schema_version": 2,
        "source_path": _SOURCE_PATH,
        "stale_claim": "Workshop Queue report output is JSON-only.",
    }


def write_p06_handoff(root: Path) -> Path:
    """Write one untracked P06 candidate from committed evidence, without staging it."""
    try:
        repository = repository_root(root)
        status = run_git(
            repository, ["status", "--porcelain", "--untracked-files=all"], check=False
        )
        if status.returncode or status.stdout:
            raise _failure()
        payload = _payload(repository)
        destination = ensure_within(repository, repository / _HANDOFF_PATH)
        if destination.exists() or destination.is_symlink():
            raise _failure()
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination = ensure_within(repository, destination)
        destination.write_bytes(canonical_json(payload) + b"\n")
        return destination
    except (CheckpointError, GitCommandError, OSError, PathBoundaryError) as error:
        raise _failure() from error
