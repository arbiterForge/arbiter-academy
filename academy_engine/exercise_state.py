"""Reversible, verifier-owned state for the hermetic P02 exercise."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import sysconfig
from collections.abc import Callable, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

from academy_engine.catalog import Catalog, CatalogError, Lab, load_manifest_file
from academy_engine.command import (
    GitCommandError,
    run_git,
    run_git_unbound,
    validate_repository_git_config,
)
from academy_engine.external_state import ExternalStateError, ExternalStateStore, LockedExternalState
from academy_engine.paths import PathBoundaryError, ensure_within
from academy_engine.remotes import RemoteSafetyError, validate_training_remotes

if TYPE_CHECKING:
    from academy_engine.scenario import PreparedLab


_LAB = "P02-commit-review-pr"
_P08_LAB = "P08-repository-hygiene"
_P08_REPORT_PATH = ".codearbiter/reports/academy/P08-hygiene.json"
_CONFIG_KEYS = (
    "remote.origin.url",
    "remote.origin.pushurl",
    "remote.upstream.url",
    "remote.upstream.pushurl",
    "remote.pushDefault",
    "push.default",
    "branch.main.remote",
    "branch.main.pushRemote",
)
_URL_KEYS = frozenset(_CONFIG_KEYS[:4])
_PHASES = (
    "captured", "origin-ready", "bares-ready", "attempt-ready", "worktree-ready",
    "activating-origin-url", "activating-origin-pushurl", "activating-upstream-url",
    "activating-upstream-pushurl", "active", "archiving", "switching-base",
    "restoring-origin-url", "restoring-origin-pushurl", "restoring-upstream-url",
    "restoring-upstream-pushurl", "restored",
)
_RECORD_KEYS = frozenset({
    "schema_version", "generation", "lab", "attempt", "phase", "base_branch",
    "base_head", "attempt_branch", "prepared_commit", "archive_ref", "archive_target",
    "transition_target", "original_topology", "origin_repository", "upstream_repository",
})
_P08_RECORD_KEYS = frozenset({
    "schema_version", "generation", "lab_id", "attempt", "phase", "namespace",
    "base_ref", "base_oid", "attempt_ref", "prepared_oid", "refs", "worktrees",
})
_P08_PHASES = frozenset({
    "creating-attempt", "creating-refs", "planning-worktrees", "creating-worktrees",
    "active", "superseding", "superseded",
})
_REPOSITORY_KEYS = frozenset({
    "repository_id", "role", "relative_directory", "object_format", "initial_refs",
    "reachable_object_count", "reachable_objects_sha256",
})
_CONSUMED = (
    "academy/catalog.json",
    "academy/contracts.json",
    "academy/scenarios/P02-commit-review-pr/manifest.json",
    "academy/checkpoints/P02-commit-review-pr.json",
    "academy/scenarios/P02-commit-review-pr/files/scenario.json",
    "academy/tracks/practitioner/P02-commit-review-pr.md",
    "academy/scenarios/P02-commit-review-pr/files/P02-worktree.patch",
)
_P08_CONSUMED = (
    "academy/catalog.json",
    "academy/contracts.json",
    "academy/scenarios/P08-repository-hygiene/manifest.json",
    "academy/checkpoints/P08-repository-hygiene.json",
    "academy/scenarios/P08-repository-hygiene/files/scenario.json",
    "academy/tracks/practitioner/P08-repository-hygiene.md",
)
_PATCH_PATHS = ("workshop_queue/cli.py", "tests/test_cli.py")
_PROFILE_PATH = ".codearbiter/tech-stack.md"
_BASE_PROFILE_SHA256 = "da8a9d082405da913a9b579d8ce9e26fbd2f26cf2093dacb37534ace86ade165"
_WORK_PATCH_INCLUDES = tuple(f"--include={path}" for path in _PATCH_PATHS)
_LATER_LABS = (
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
_HEX64 = re.compile(r"[0-9a-f]{64}")
_ARCHIVE = re.compile(r"refs/heads/academy/archive/P02-commit-review-pr/([1-9]|[12][0-9]|3[0-2])/[0-9]{8}T[0-9]{6}Z")
_MESSAGES = {
    "invalid-exercise-state": "P02 exercise state is invalid.",
    "transition-incomplete": "P02 transition is incomplete.",
    "remote-topology-mismatch": "P02 remote topology does not match.",
    "exercise-evidence-mismatch": "P02 exercise evidence does not match.",
    "installed-authority-required": "P02 requires installed Academy authority.",
    "p08-transition-incomplete": "P08 repository transition is incomplete.",
    "p08-resource-missing": "P08 prepared resource is missing.",
    "p08-resource-moved": "P08 prepared resource moved.",
    "p08-resource-rebound": "P08 prepared resource was rebound.",
    "p08-state-mismatch": "P08 exercise state does not match.",
    "p08-report-mismatch": "P08 report does not match.",
}


class ExerciseStateError(ValueError):
    """Stable, bounded, path-free P02 failure."""

    code: str

    def __init__(self, code: str) -> None:
        self.code = code if code in _MESSAGES else "invalid-exercise-state"
        super().__init__(_MESSAGES[self.code])


@dataclass(frozen=True)
class P02AttemptIdentity:
    attempt: int
    branch: str
    prepared_commit: str
    head_commit: str


@dataclass(frozen=True)
class P02LiveState:
    origin_repository_id: str
    upstream_repository_id: str
    branch: str
    prepared_commit: str
    origin_tip: str
    upstream_unchanged: bool


@dataclass(frozen=True)
class P08LiveRef:
    ref_name: str
    role: str
    observation_oid: str
    live_oid: str
    worktree_state: str
    merged_into_base: bool
    unique_commits: int
    classification: str
    recommendation: str


@dataclass(frozen=True)
class P08LiveWorktree:
    worktree_id: str
    role: str
    branch_ref: str
    observation_oid: str
    live_oid: str
    dirty: bool
    classification: str
    recommendation: str


@dataclass(frozen=True)
class P08AttemptIdentity:
    attempt: int
    branch: str
    prepared_commit: str
    head_commit: str


@dataclass(frozen=True)
class P08LiveState:
    repository_id: str
    base_ref: str
    base_oid: str
    attempt_ref: str
    prepared_oid: str
    observation_oid: str
    live_head_oid: str
    refs: tuple[P08LiveRef, ...]
    worktrees: tuple[P08LiveWorktree, ...]
    state_digest: str


@dataclass(frozen=True)
class _VerifiedAuthority:
    installed_root: Path
    catalog_sha256: str
    sources: Mapping[str, bytes]
    catalog: Catalog

    def read(self, canonical: str) -> bytes:
        try:
            return self.sources[canonical]
        except KeyError as error:
            raise _fail("installed-authority-required", error)


def _fail(code: str, error: BaseException | None = None) -> ExerciseStateError:
    failure = ExerciseStateError(code)
    if error is not None:
        failure.__cause__ = error
    return failure


@contextmanager
def _locked_store(store: ExternalStateStore):
    """Translate every sidecar-boundary failure at the public exercise seam."""
    try:
        with store.locked() as locked:
            yield locked
    except ExerciseStateError:
        raise
    except ExternalStateError as error:
        raise _fail("invalid-exercise-state", error)


def _oid_pattern(object_format: str) -> re.Pattern[str]:
    if object_format not in {"sha1", "sha256"}:
        raise _fail("invalid-exercise-state")
    return re.compile(r"[0-9a-f]{40}" if object_format == "sha1" else r"[0-9a-f]{64}")


def _git(repository: Path, args: Sequence[str], *, code: str = "transition-incomplete") -> str:
    try:
        result = run_git(repository, args, check=False)
    except (GitCommandError, OSError) as error:
        raise _fail(code, error)
    if result.returncode:
        raise _fail(code)
    return result.stdout


def _git_result(repository: Path, args: Sequence[str], *, code: str = "transition-incomplete"):
    try:
        return run_git(repository, args, check=False)
    except (GitCommandError, OSError) as error:
        raise _fail(code, error)


def _bare_object_format(directory: Path) -> str:
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)

    def safe_entry(path: Path, *, directory_expected: bool) -> None:
        try:
            details = path.lstat()
        except OSError as error:
            raise _fail("transition-incomplete", error)
        expected = stat.S_ISDIR(details.st_mode) if directory_expected else stat.S_ISREG(details.st_mode)
        if (
            not expected
            or stat.S_ISLNK(details.st_mode)
            or bool(getattr(details, "st_file_attributes", 0) & reparse_flag)
        ):
            raise _fail("transition-incomplete")

    safe_entry(directory / "config", directory_expected=False)
    safe_entry(directory / "objects", directory_expected=True)
    safe_entry(directory / "objects" / "info", directory_expected=True)
    safe_entry(directory / "objects" / "pack", directory_expected=True)
    safe_entry(directory / "refs", directory_expected=True)
    safe_entry(directory / "HEAD", directory_expected=False)

    def validate_authority_tree(root: Path, *, required: bool) -> None:
        if not os.path.lexists(root):
            if required:
                raise _fail("transition-incomplete")
            return
        pending = [root]
        while pending:
            current = pending.pop()
            try:
                details = current.lstat()
            except OSError as error:
                raise _fail("transition-incomplete", error)
            if stat.S_ISLNK(details.st_mode) or bool(
                getattr(details, "st_file_attributes", 0) & reparse_flag
            ):
                raise _fail("transition-incomplete")
            if stat.S_ISDIR(details.st_mode):
                try:
                    pending.extend(current.iterdir())
                except OSError as error:
                    raise _fail("transition-incomplete", error)
            elif not stat.S_ISREG(details.st_mode):
                raise _fail("transition-incomplete")

    validate_authority_tree(directory / "refs", required=True)
    validate_authority_tree(directory / "objects", required=True)
    validate_authority_tree(directory / "info", required=False)
    validate_authority_tree(directory / "logs", required=False)
    if os.path.lexists(directory / "packed-refs"):
        safe_entry(directory / "packed-refs", directory_expected=False)
    forbidden = (
        directory / "objects" / "info" / "alternates",
        directory / "objects" / "info" / "http-alternates",
        directory / "info" / "grafts",
        directory / "shallow",
    )
    if any(os.path.lexists(path) for path in forbidden):
        raise _fail("transition-incomplete")
    try:
        if any(path.name.endswith(".promisor") for path in (directory / "objects" / "pack").iterdir()):
            raise _fail("transition-incomplete")
    except OSError as error:
        raise _fail("transition-incomplete", error)
    try:
        config_result = run_git_unbound(
            directory.parent,
            [
                f"--git-dir={directory}",
                "--no-replace-objects",
                "config",
                "--local",
                "--null",
                "--list",
                "--no-includes",
            ],
            check=False,
        )
    except (GitCommandError, OSError) as error:
        raise _fail("transition-incomplete", error)
    if config_result.returncode:
        raise _fail("transition-incomplete")
    allowed = {
        "core.repositoryformatversion": {"0", "1"},
        "core.filemode": {"true", "false"},
        "core.bare": {"true"},
        "core.logallrefupdates": {"true", "false"},
        "core.symlinks": {"true", "false"},
        "core.ignorecase": {"true", "false"},
        "core.precomposeunicode": {"true", "false"},
        "extensions.objectformat": {"sha256"},
    }
    parsed: dict[str, str] = {}
    entries = config_result.stdout.split("\0")
    if entries and entries[-1] == "":
        entries.pop()
    for entry in entries:
        if "\n" not in entry:
            raise _fail("transition-incomplete")
        key, value = entry.split("\n", 1)
        key = key.casefold()
        if key in parsed or key not in allowed or value not in allowed[key]:
            raise _fail("transition-incomplete")
        parsed[key] = value
    required = {"core.repositoryformatversion", "core.bare"}
    if not required.issubset(parsed):
        raise _fail("transition-incomplete")
    if parsed["core.repositoryformatversion"] == "0":
        if "extensions.objectformat" in parsed:
            raise _fail("transition-incomplete")
        object_format = "sha1"
    elif parsed.get("extensions.objectformat") == "sha256":
        object_format = "sha256"
    else:
        raise _fail("transition-incomplete")
    try:
        replace = run_git_unbound(
            directory.parent,
            [
                f"--git-dir={directory}",
                "--no-replace-objects",
                "for-each-ref",
                "--format=%(refname)",
                "refs/replace/",
            ],
            check=False,
        )
    except (GitCommandError, OSError) as error:
        raise _fail("transition-incomplete", error)
    if replace.returncode or replace.stdout:
        raise _fail("transition-incomplete")
    return object_format


def _bare(
    directory: Path,
    args: Sequence[str],
    *,
    code: str = "transition-incomplete",
    missing_ok: bool = False,
) -> str | None:
    _bare_object_format(directory)
    try:
        result = run_git_unbound(
            directory.parent,
            [f"--git-dir={directory}", "--no-replace-objects", *args],
            check=False,
        )
    except (GitCommandError, OSError) as error:
        raise _fail(code, error)
    if result.returncode == 1 and missing_ok:
        return None
    if result.returncode:
        raise _fail(code)
    return result.stdout


def _object_format(repository: Path) -> str:
    value = _git(repository, ["rev-parse", "--show-object-format"]).strip()
    if value not in {"sha1", "sha256"}:
        raise _fail("invalid-exercise-state")
    return value


def _p02_repository_id(external_repository_id: str, attempt: int, role: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{32}", external_repository_id):
        raise _fail("invalid-exercise-state")
    if type(attempt) is not int or not 1 <= attempt <= 32 or role not in {"learner", "official"}:
        raise _fail("invalid-exercise-state")
    preimage = (
        "arbiter-academy/p02-repository-id/v1\0"
        f"{external_repository_id}\0{_LAB}\0{attempt}\0{role}\n"
    ).encode("ascii")
    return hashlib.sha256(preimage).hexdigest()


def _p08_worktree_id(repository_id: str, attempt: int, role: str) -> str:
    if not isinstance(repository_id, str) or not re.fullmatch(r"[0-9a-f]{32}", repository_id):
        raise _fail("invalid-exercise-state")
    if (
        type(attempt) is not int
        or not 1 <= attempt <= 32
        or role not in {"current-attempt", "merged-clean", "dirty-unmerged"}
    ):
        raise _fail("invalid-exercise-state")
    preimage = (
        "arbiter-academy/p08-worktree-id/v1\0"
        f"{repository_id}\0P08-repository-hygiene\0{attempt}\0{role}\n"
    ).encode("ascii")
    return hashlib.sha256(preimage).hexdigest()


def _p08_live_state_digest(state: P08LiveState) -> str:
    """Hash the public P08 observation without carrying a path-bearing state locator."""
    def canonical_roles(values: Sequence[Any], roles: tuple[str, ...]) -> list[Any]:
        by_role: dict[str, Any] = {}
        for value in values:
            role = getattr(value, "role", None)
            if role not in roles or role in by_role:
                raise _fail("invalid-exercise-state")
            by_role[role] = value
        return [by_role[role] for role in roles if role in by_role]

    refs = canonical_roles(
        state.refs,
        ("selected-base", "current-attempt", "merged-clean", "dirty-unmerged", "unique-unmerged"),
    )
    worktrees = canonical_roles(
        state.worktrees, ("current-attempt", "merged-clean", "dirty-unmerged")
    )
    payload = {
        "base_ref": state.base_ref,
        "base_oid": state.base_oid,
        "attempt_ref": state.attempt_ref,
        "prepared_oid": state.prepared_oid,
        "observation_oid": state.observation_oid,
        "live_head_oid": state.live_head_oid,
        "refs": [
            {
                "ref_name": ref.ref_name,
                "role": ref.role,
                "observation_oid": ref.observation_oid,
                "live_oid": ref.live_oid,
                "worktree_state": ref.worktree_state,
                "merged_into_base": ref.merged_into_base,
                "unique_commits": ref.unique_commits,
                "classification": ref.classification,
                "recommendation": ref.recommendation,
            }
            for ref in refs
        ],
        "worktrees": [
            {
                "worktree_id": worktree.worktree_id,
                "role": worktree.role,
                "branch_ref": worktree.branch_ref,
                "observation_oid": worktree.observation_oid,
                "live_oid": worktree.live_oid,
                "dirty": worktree.dirty,
                "classification": worktree.classification,
                "recommendation": worktree.recommendation,
            }
            for worktree in worktrees
        ],
    }
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(
        b"arbiter-academy/p08-live-state/v1\0" + canonical + b"\n"
    ).hexdigest()


def _exact_keys(value: object, expected: frozenset[str]) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != expected:
        raise _fail("invalid-exercise-state")
    return value


def _string_list(value: object, *, empty: bool) -> list[str]:
    if not isinstance(value, list) or (not empty and not value):
        raise _fail("invalid-exercise-state")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or len(item.encode("utf-8")) > 2048 or any(ord(c) < 32 or ord(c) == 127 for c in item):
            if item != "":
                raise _fail("invalid-exercise-state")
        result.append(item)
    return result


def _validate_original_url(key: str, value: str) -> None:
    if key == "remote.upstream.pushurl" and value == "DISABLED":
        return
    if (
        not isinstance(value, str)
        or value != value.strip()
        or any(ord(character) < 0x20 or ord(character) == 0x7F for character in value)
    ):
        raise _fail("invalid-exercise-state")
    match = re.fullmatch(
        r"(?:https://(?i:github\.com)/|ssh://git@(?i:github\.com)/|git@(?i:github\.com):)"
        r"(?P<owner>[A-Za-z0-9](?:[A-Za-z0-9-]{0,38}))/(?P<repository>[A-Za-z0-9](?:[A-Za-z0-9-]{0,38}))(?:\.git)?",
        value,
    )
    if match is None or match.group("repository").casefold().endswith(".git"):
        raise _fail("invalid-exercise-state")


def _decode_repository(value: object, *, role: str, attempt: int, base_head: str, object_format: str) -> dict[str, Any]:
    data = _exact_keys(value, _REPOSITORY_KEYS)
    oid = _oid_pattern(object_format)
    repository_id = data["repository_id"]
    if not isinstance(repository_id, str) or _HEX64.fullmatch(repository_id) is None or data["role"] != role:
        raise _fail("invalid-exercise-state")
    relative = data["relative_directory"]
    if (
        not isinstance(relative, str)
        or re.fullmatch(r"remotes/[0-9a-f]{64}", relative) is None
        or data["object_format"] != object_format
    ):
        raise _fail("invalid-exercise-state")
    refs = data["initial_refs"]
    if refs != [{"ref": "refs/heads/main", "object_id": base_head}]:
        raise _fail("invalid-exercise-state")
    count = data["reachable_object_count"]
    digest = data["reachable_objects_sha256"]
    if type(count) is not int or count < 1 or not isinstance(digest, str) or _HEX64.fullmatch(digest) is None:
        raise _fail("invalid-exercise-state")
    if oid.fullmatch(base_head) is None:
        raise _fail("invalid-exercise-state")
    return data


def _decode_p02_record(value: object, *, object_format: str) -> dict[str, Any]:
    data = _exact_keys(value, _RECORD_KEYS)
    oid = _oid_pattern(object_format)
    if type(data["schema_version"]) is not int or data["schema_version"] != 1 or type(data["generation"]) is not int or data["generation"] < 1:
        raise _fail("invalid-exercise-state")
    attempt = data["attempt"]
    if type(attempt) is not int or not 1 <= attempt <= 32 or data["lab"] != _LAB or data["phase"] not in _PHASES:
        raise _fail("invalid-exercise-state")
    if data["base_branch"] != "main" or data["attempt_branch"] != f"academy/{_LAB}/{attempt}":
        raise _fail("invalid-exercise-state")
    base_head = data["base_head"]
    if not isinstance(base_head, str) or oid.fullmatch(base_head) is None:
        raise _fail("invalid-exercise-state")
    phase_index = _PHASES.index(data["phase"])
    prepared = data["prepared_commit"]
    if phase_index < _PHASES.index("attempt-ready"):
        if prepared is not None:
            raise _fail("invalid-exercise-state")
    elif not isinstance(prepared, str) or oid.fullmatch(prepared) is None:
        raise _fail("invalid-exercise-state")
    archive = (data["archive_ref"], data["archive_target"], data["transition_target"])
    if phase_index < _PHASES.index("archiving"):
        if archive != (None, None, None):
            raise _fail("invalid-exercise-state")
    else:
        archive_match = _ARCHIVE.fullmatch(archive[0]) if isinstance(archive[0], str) else None
        if archive_match is None or int(archive_match.group(1)) != attempt:
            raise _fail("invalid-exercise-state")
        if not isinstance(archive[1], str) or oid.fullmatch(archive[1]) is None:
            raise _fail("invalid-exercise-state")
        if archive[2] != "reset" and (not isinstance(archive[2], str) or re.fullmatch(r"[FPU][0-9]{2}-[a-z0-9]+(?:-[a-z0-9]+)*", archive[2]) is None):
            raise _fail("invalid-exercise-state")
    topology = _exact_keys(data["original_topology"], frozenset({"config", "effective_routes"}))
    config = _exact_keys(topology["config"], frozenset(_CONFIG_KEYS))
    for key in _CONFIG_KEYS:
        values = config[key]
        if values is None:
            continue
        parsed = _string_list(values, empty=True)
        if key in _URL_KEYS:
            if not parsed:
                raise _fail("invalid-exercise-state")
            for item in parsed:
                _validate_original_url(key, item)
    if config["remote.upstream.pushurl"] != ["DISABLED"]:
        raise _fail("invalid-exercise-state")
    routes = _exact_keys(topology["effective_routes"], frozenset({"origin", "upstream"}))
    for remote in ("origin", "upstream"):
        route = _exact_keys(routes[remote], frozenset({"fetch", "push"}))
        for kind in ("fetch", "push"):
            for item in _string_list(route[kind], empty=False):
                _validate_original_url(f"remote.{remote}.{'pushurl' if kind == 'push' else 'url'}", item)
    if routes["upstream"]["push"] != ["DISABLED"]:
        raise _fail("invalid-exercise-state")
    origin, upstream = data["origin_repository"], data["upstream_repository"]
    if phase_index == 0:
        if origin is not None or upstream is not None:
            raise _fail("invalid-exercise-state")
    else:
        if origin is None:
            raise _fail("invalid-exercise-state")
        _decode_repository(origin, role="learner", attempt=attempt, base_head=base_head, object_format=object_format)
        if phase_index < _PHASES.index("bares-ready"):
            if upstream is not None:
                raise _fail("invalid-exercise-state")
        else:
            _decode_repository(upstream, role="official", attempt=attempt, base_head=base_head, object_format=object_format)
    return data


def _decode_p08_record(
    value: object, *, object_format: str, repository_id: str
) -> dict[str, Any]:
    """Validate P08's top-level immutable state envelope before a transition."""
    data = _exact_keys(value, _P08_RECORD_KEYS)
    if not isinstance(data["phase"], str):
        raise _fail("invalid-exercise-state")
    oid = _oid_pattern(object_format)
    attempt = data["attempt"]
    generation = data["generation"]
    if (
        type(data["schema_version"]) is not int
        or data["schema_version"] != 1
        or type(generation) is not int
        or generation < 1
        or type(attempt) is not int
        or not 1 <= attempt <= 32
        or data["lab_id"] != "P08-repository-hygiene"
        or data["phase"] not in _P08_PHASES
        or data["namespace"] != f"refs/heads/academy-fixtures/p08/{attempt}/"
        or data["base_ref"] != "refs/heads/main"
        or not isinstance(data["base_oid"], str)
        or oid.fullmatch(data["base_oid"]) is None
        or data["attempt_ref"] != f"refs/heads/academy/P08-repository-hygiene/{attempt}"
        or (data["prepared_oid"] is not None and (
            not isinstance(data["prepared_oid"], str)
            or oid.fullmatch(data["prepared_oid"]) is None
        ))
        or (data["phase"] == "creating-attempt" and data["prepared_oid"] is not None)
        or not isinstance(data["refs"], list)
        or not isinstance(data["worktrees"], list)
    ):
        raise _fail("invalid-exercise-state")
    refs = data["refs"]
    worktrees = data["worktrees"]
    assert isinstance(refs, list)
    assert isinstance(worktrees, list)
    ref_roles = (
        "selected-base", "current-attempt", "merged-clean", "dirty-unmerged",
        "unique-unmerged",
    )
    worktree_roles = ("current-attempt", "merged-clean", "dirty-unmerged")
    namespace = str(data["namespace"])
    base = str(data["base_oid"])
    attempt_ref = str(data["attempt_ref"])
    prepared = data["prepared_oid"]
    expected_ref_names = (
        "refs/heads/main", attempt_ref, f"{namespace}merged-clean",
        f"{namespace}dirty-unmerged", f"{namespace}unique-unmerged",
    )
    expected_bindings = (
        "fixed", "learner-descendant", "fixed", "fixed", "fixed",
    )
    if len(refs) != len(ref_roles) or len(worktrees) != len(worktree_roles):
        raise _fail("invalid-exercise-state")
    if data["phase"] == "creating-attempt":
        expected_ref_oids: tuple[str | None, ...] = (base, None, base, None, None)
        expected_heads: tuple[str | None, ...] = (None, base, None)
    else:
        if not isinstance(prepared, str):
            raise _fail("invalid-exercise-state")
        expected_ref_oids = (base, prepared, base, prepared, prepared)
        expected_heads = (prepared, base, prepared)
    for item, role, ref_name, binding, expected_oid in zip(
        refs, ref_roles, expected_ref_names, expected_bindings, expected_ref_oids,
        strict=True,
    ):
        try:
            ref = _exact_keys(item, frozenset({"ref_name", "object_id", "role", "binding"}))
        except ExerciseStateError:
            raise
        if (
            ref["role"] != role
            or ref["ref_name"] != ref_name
            or ref["binding"] != binding
            or ref["object_id"] != expected_oid
        ):
            raise _fail("invalid-exercise-state")
    if not isinstance(repository_id, str) or re.fullmatch(r"[0-9a-f]{32}", repository_id) is None:
        raise _fail("invalid-exercise-state")
    observed_worktree_ids: set[str] = set()
    for index, (item, role, branch_ref, expected_head) in enumerate(zip(
        worktrees,
        worktree_roles,
        (attempt_ref, f"{namespace}merged-clean", f"{namespace}dirty-unmerged"),
        expected_heads,
        strict=True,
    )):
        worktree = _exact_keys(
            item,
            frozenset({
                "worktree_id", "path_sha256", "git_admin_id", "branch_ref", "head_oid",
                "expected_presence", "role", "dirty_status_sha256",
            }),
        )
        worktree_id = worktree["worktree_id"]
        if (
            not isinstance(worktree_id, str)
            or _HEX64.fullmatch(worktree_id) is None
            or worktree["role"] != role
            or worktree["branch_ref"] != branch_ref
            or worktree["head_oid"] != expected_head
            or worktree["expected_presence"] is not True
            or worktree_id in observed_worktree_ids
            or worktree_id != _p08_worktree_id(repository_id, int(attempt), role)
        ):
            raise _fail("invalid-exercise-state")
        observed_worktree_ids.add(worktree_id)
        is_primary = index == 0
        path_sha256 = worktree["path_sha256"]
        git_admin_id = worktree["git_admin_id"]
        dirty_status_sha256 = worktree["dirty_status_sha256"]
        linked_bound = data["phase"] in {
            "creating-worktrees", "active", "superseding", "superseded",
        }
        if (
            (is_primary and (_HEX64.fullmatch(path_sha256) is None if isinstance(path_sha256, str) else True))
            or (is_primary and git_admin_id is not None)
            or (not is_primary and git_admin_id != worktree_id)
            or (not is_primary and linked_bound and (
                not isinstance(path_sha256, str) or _HEX64.fullmatch(path_sha256) is None
            ))
            or (not is_primary and not linked_bound and path_sha256 is not None)
            or (role == "dirty-unmerged" and linked_bound and (
                not isinstance(dirty_status_sha256, str) or _HEX64.fullmatch(dirty_status_sha256) is None
            ))
            or (role != "dirty-unmerged" and dirty_status_sha256 is not None)
            or (role == "dirty-unmerged" and not linked_bound and dirty_status_sha256 is not None)
        ):
            raise _fail("invalid-exercise-state")
    return data


def _parse_p02_receipt(value: object, *, object_format: str) -> dict[str, Any]:
    expected = frozenset({"schema_version", "mode", "lab_id", "attempt", "branch", "prepared_commit", "work_head", "pushed_tip", "commits", "review", "repositories", "pr_reference"})
    try:
        data = _exact_keys(value, expected)
        oid = _oid_pattern(object_format)
        attempt = data["attempt"]
        if type(data["schema_version"]) is not int or data["schema_version"] != 1 or data["mode"] != "offline-local" or data["lab_id"] != _LAB or type(attempt) is not int or not 1 <= attempt <= 32:
            raise ValueError
        if data["branch"] != f"academy/{_LAB}/{attempt}":
            raise ValueError
        for key in ("prepared_commit", "work_head", "pushed_tip"):
            if not isinstance(data[key], str) or oid.fullmatch(data[key]) is None:
                raise ValueError
        commits = data["commits"]
        if not isinstance(commits, list) or not commits or any(not isinstance(item, str) or oid.fullmatch(item) is None for item in commits):
            raise ValueError
        if _exact_keys(data["review"], frozenset({"status"}))["status"] != "cleared":
            raise ValueError
        repositories = _exact_keys(data["repositories"], frozenset({"origin", "upstream"}))
        for name, role in (("origin", "learner"), ("upstream", "official")):
            repo = _exact_keys(repositories[name], frozenset({"repository_id", "role"}))
            if not isinstance(repo["repository_id"], str) or _HEX64.fullmatch(repo["repository_id"]) is None or repo["role"] != role:
                raise ValueError
        if data["pr_reference"] != f"local-pr:{data['work_head'][:12]}":
            raise ValueError
        return data
    except (ExerciseStateError, KeyError, TypeError, ValueError) as error:
        raise _fail("exercise-evidence-mismatch", error)


def _parse_p02_receipt_bytes(raw: bytes, *, object_format: str) -> dict[str, Any]:
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate key")
            result[key] = value
        return result

    try:
        if not isinstance(raw, bytes) or not 1 <= len(raw) <= 65_536:
            raise ValueError("receipt size")
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=unique,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError("constant")),
        )
    except (UnicodeError, json.JSONDecodeError, TypeError, ValueError) as error:
        raise _fail("exercise-evidence-mismatch", error)
    return _parse_p02_receipt(value, object_format=object_format)


def _config_values(repository: Path, key: str) -> list[str] | None:
    try:
        result = run_git(repository, ["config", "--null", "--get-all", key], check=False)
    except (GitCommandError, OSError) as error:
        raise _fail("transition-incomplete", error)
    if result.returncode == 1:
        return None
    if result.returncode:
        raise _fail("transition-incomplete")
    values = result.stdout.split("\0")
    if values and values[-1] == "":
        values.pop()
    return values


def _effective(repository: Path, remote: str, *, push: bool) -> list[str]:
    args = ["remote", "get-url"]
    if push:
        args.append("--push")
    args.extend(["--all", remote])
    output = _git(repository, args, code="remote-topology-mismatch")
    values = output.splitlines()
    if not values:
        raise _fail("remote-topology-mismatch")
    return values


def _capture_topology(repository: Path) -> dict[str, Any]:
    try:
        validate_training_remotes(repository, require_push_safe=True)
    except (RemoteSafetyError, GitCommandError) as error:
        raise _fail("remote-topology-mismatch", error)
    config = {key: _config_values(repository, key) for key in _CONFIG_KEYS}
    if config["remote.upstream.pushurl"] != ["DISABLED"]:
        raise _fail("remote-topology-mismatch")
    for key in _URL_KEYS:
        values = config[key]
        if values is not None:
            for value in values:
                _validate_original_url(key, value)
    return {
        "config": config,
        "effective_routes": {
            name: {"fetch": _effective(repository, name, push=False), "push": _effective(repository, name, push=True)}
            for name in ("origin", "upstream")
        },
    }


def _installed_root() -> Path:
    root = Path(sysconfig.get_path("data")) / "share" / "arbiter-academy" / "academy"
    try:
        details = root.lstat()
        resolved = root.resolve(strict=True)
    except OSError as error:
        raise _fail("installed-authority-required", error)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    if (
        not stat.S_ISDIR(details.st_mode)
        or stat.S_ISLNK(details.st_mode)
        or bool(getattr(details, "st_file_attributes", 0) & reparse_flag)
        or not resolved.is_dir()
    ):
        raise _fail("installed-authority-required")
    return resolved


def _installed_path(installed: Path, canonical: str) -> Path:
    relative = Path(canonical).relative_to("academy")
    try:
        candidate = installed
        reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
        for part in relative.parts:
            candidate = candidate / part
            details = candidate.lstat()
            if stat.S_ISLNK(details.st_mode) or bool(
                getattr(details, "st_file_attributes", 0) & reparse_flag
            ):
                raise _fail("installed-authority-required")
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(installed)
    except ExerciseStateError:
        raise
    except (OSError, ValueError) as error:
        raise _fail("installed-authority-required", error)
    if not stat.S_ISREG(details.st_mode) or not resolved.is_file():
        raise _fail("installed-authority-required")
    return resolved


def _verified_epoch(repository: Path, base: str) -> _VerifiedAuthority:
    installed = _installed_root()
    oid = _oid_pattern(_object_format(repository))
    if oid.fullmatch(base) is None:
        raise _fail("installed-authority-required")
    profile_entry = _git(
        repository,
        ["ls-tree", base, "--", _PROFILE_PATH],
        code="installed-authority-required",
    ).strip()
    if re.fullmatch(
        rf"100644 blob [0-9a-f]+\t{re.escape(_PROFILE_PATH)}",
        profile_entry,
    ) is None:
        raise _fail("installed-authority-required")
    profile = _git(
        repository,
        ["show", f"{base}:{_PROFILE_PATH}"],
        code="installed-authority-required",
    ).encode("utf-8", "surrogateescape")
    if hashlib.sha256(profile).hexdigest() != _BASE_PROFILE_SHA256:
        raise _fail("installed-authority-required")
    for arguments in (
        [
            "diff",
            "--cached",
            "--no-ext-diff",
            "--quiet",
            base,
            "--",
            *_CONSUMED,
        ],
        ["diff", "--no-ext-diff", "--quiet", "--", *_CONSUMED],
    ):
        result = _git_result(
            repository,
            arguments,
            code="installed-authority-required",
        )
        if result.returncode not in {0, 1}:
            raise _fail("installed-authority-required")
        if result.returncode == 1:
            raise _fail("installed-authority-required")
    untracked = _git(
        repository,
        ["ls-files", "--others", "--exclude-standard", "--", *_CONSUMED],
        code="installed-authority-required",
    )
    if untracked:
        raise _fail("installed-authority-required")
    packaged_sources: dict[str, bytes] = {}
    for canonical in _CONSUMED:
        entry = _git(repository, ["ls-tree", base, "--", canonical], code="installed-authority-required").strip()
        match = re.fullmatch(r"100644 blob [0-9a-f]+\t(.+)", entry)
        if match is None or match.group(1) != canonical:
            raise _fail("installed-authority-required")
        tracked = _git(repository, ["show", f"{base}:{canonical}"], code="installed-authority-required").encode("utf-8", "surrogateescape")
        try:
            packaged = _installed_path(installed, canonical).read_bytes()
        except OSError as error:
            raise _fail("installed-authority-required", error)
        if tracked != packaged:
            raise _fail("installed-authority-required")
        packaged_sources[canonical] = packaged
    try:
        with TemporaryDirectory(prefix="arbiter-academy-authority-") as temporary:
            captured = Path(temporary)
            catalog_path = captured / "catalog.json"
            manifest_path = captured / "manifest.json"
            catalog_path.write_bytes(packaged_sources["academy/catalog.json"])
            manifest_path.write_bytes(
                packaged_sources[f"academy/scenarios/{_LAB}/manifest.json"]
            )
            captured_catalog = Catalog.load(catalog_path)
            load_manifest_file(manifest_path)
    except Exception as error:
        raise _fail("installed-authority-required", error)
    catalog = packaged_sources["academy/catalog.json"]
    return _VerifiedAuthority(
        installed,
        hashlib.sha256(catalog).hexdigest(),
        MappingProxyType(dict(packaged_sources)),
        captured_catalog,
    )


def _verified_p08_epoch(repository: Path, base: str) -> _VerifiedAuthority:
    """Capture the six immutable installed P08 resources against base before state access."""
    installed = _installed_root()
    oid = _oid_pattern(_object_format(repository))
    if oid.fullmatch(base) is None:
        raise _fail("installed-authority-required")
    for arguments in (
        [
            "diff",
            "--cached",
            "--no-ext-diff",
            "--quiet",
            base,
            "--",
            *_P08_CONSUMED,
        ],
        ["diff", "--no-ext-diff", "--quiet", "--", *_P08_CONSUMED],
    ):
        result = _git_result(repository, arguments, code="installed-authority-required")
        if result.returncode not in {0, 1}:
            raise _fail("installed-authority-required")
        if result.returncode == 1:
            raise _fail("installed-authority-required")
    untracked = _git(
        repository,
        ["ls-files", "--others", "--exclude-standard", "--", *_P08_CONSUMED],
        code="installed-authority-required",
    )
    if untracked:
        raise _fail("installed-authority-required")
    packaged_sources: dict[str, bytes] = {}
    for canonical in _P08_CONSUMED:
        entry = _git(
            repository, ["ls-tree", base, "--", canonical], code="installed-authority-required"
        ).strip()
        match = re.fullmatch(r"100644 blob [0-9a-f]+\t(.+)", entry)
        if match is None or match.group(1) != canonical:
            raise _fail("installed-authority-required")
        tracked = _git(
            repository, ["show", f"{base}:{canonical}"], code="installed-authority-required"
        ).encode("utf-8", "surrogateescape")
        try:
            packaged = _installed_path(installed, canonical).read_bytes()
        except OSError as error:
            raise _fail("installed-authority-required", error)
        if tracked != packaged:
            raise _fail("installed-authority-required")
        packaged_sources[canonical] = packaged
    try:
        with TemporaryDirectory(prefix="arbiter-academy-p08-authority-") as temporary:
            captured = Path(temporary)
            catalog_path = captured / "catalog.json"
            manifest_path = captured / "manifest.json"
            catalog_path.write_bytes(packaged_sources["academy/catalog.json"])
            manifest_path.write_bytes(
                packaged_sources[f"academy/scenarios/{_P08_LAB}/manifest.json"]
            )
            captured_catalog = Catalog.load(catalog_path)
            load_manifest_file(manifest_path)
    except Exception as error:
        raise _fail("installed-authority-required", error)
    catalog = packaged_sources["academy/catalog.json"]
    return _VerifiedAuthority(
        installed,
        hashlib.sha256(catalog).hexdigest(),
        MappingProxyType(dict(packaged_sources)),
        captured_catalog,
    )


def open_p02_store(repository: Path, *, base: str, test_root: Path | None = None) -> ExternalStateStore:
    authority = _verified_epoch(repository, base)
    try:
        return ExternalStateStore.open(repository, academy_base_commit=base, catalog_sha256=authority.catalog_sha256, test_root=test_root)
    except ExternalStateError as error:
        raise _fail("installed-authority-required", error)


def open_p08_store(
    repository: Path,
    *,
    base: str,
    authority: _VerifiedAuthority,
    test_root: Path | None = None,
) -> ExternalStateStore:
    """Open P08 state only from the previously captured installed authority."""
    try:
        return ExternalStateStore.open(
            repository,
            academy_base_commit=base,
            catalog_sha256=authority.catalog_sha256,
            test_root=test_root,
        )
    except ExternalStateError as error:
        raise _fail("installed-authority-required", error)


def open_existing_p02_store(
    repository: Path, *, base: str, test_root: Path | None = None
) -> ExternalStateStore | None:
    authority = _verified_epoch(repository, base)
    try:
        store = ExternalStateStore.open_existing(
            repository,
            academy_base_commit=base,
            catalog_sha256=authority.catalog_sha256,
            test_root=test_root,
        )
    except ExternalStateError as error:
        raise _fail("invalid-exercise-state", error)
    if store is None:
        return None
    object_format = _object_format(repository)
    with _locked_store(store) as locked:
        if _latest(locked, object_format) is None:
            return None
    return store


def _reachable(directory: Path) -> tuple[int, str]:
    return _reachable_from(directory, ("--all",))


def _parse_oid_lines(
    output: str,
    *,
    object_format: str,
    paths_allowed: bool,
) -> list[str]:
    pattern = _oid_pattern(object_format)
    parsed: list[str] = []
    for line in output.splitlines():
        oid = line.split(" ", 1)[0] if paths_allowed else line
        if pattern.fullmatch(oid) is None or oid in parsed:
            raise _fail("transition-incomplete")
        parsed.append(oid)
    return sorted(parsed)


def _reachable_ids(
    directory: Path,
    revisions: Sequence[str],
    *,
    object_format: str | None = None,
) -> list[str]:
    selected_format = _bare_object_format(directory) if object_format is None else object_format
    return _parse_oid_lines(
        _bare(directory, ["rev-list", "--objects", *revisions]),
        object_format=selected_format,
        paths_allowed=True,
    )


def _reachable_from(
    directory: Path,
    revisions: Sequence[str],
    *,
    object_format: str | None = None,
) -> tuple[int, str]:
    objects = _reachable_ids(directory, revisions, object_format=object_format)
    payload = b"arbiter-academy/p02-reachable/v1\0" + b"".join((item + "\n").encode("ascii") for item in objects)
    return len(objects), hashlib.sha256(payload).hexdigest()


def _require_complete_object_set(
    directory: Path,
    *,
    object_format: str | None = None,
) -> None:
    selected_format = _bare_object_format(directory) if object_format is None else object_format
    all_objects = _parse_oid_lines(
        _bare(
            directory,
            [
                "cat-file",
                "--batch-all-objects",
                "--batch-check=%(objectname)",
            ],
        ),
        object_format=selected_format,
        paths_allowed=False,
    )
    if all_objects != _reachable_ids(
        directory,
        ("--all",),
        object_format=selected_format,
    ):
        raise _fail("transition-incomplete")


def _bare_refs(
    directory: Path,
    *,
    object_format: str | None = None,
) -> list[dict[str, str]]:
    selected_format = _bare_object_format(directory) if object_format is None else object_format
    oid_pattern = _oid_pattern(selected_format)
    refs: list[dict[str, str]] = []
    for line in _bare(directory, ["for-each-ref", "--format=%(refname)%00%(objectname)"]).splitlines():
        parts = line.split("\0")
        if len(parts) != 2 or oid_pattern.fullmatch(parts[1]) is None:
            raise _fail("transition-incomplete")
        refs.append({"ref": parts[0], "object_id": parts[1]})
    refs.sort(key=lambda item: item["ref"])
    return refs


def _repository_snapshot(directory: Path, repository_id: str, role: str, base: str, object_format: str) -> dict[str, Any]:
    if _bare(directory, ["rev-parse", "--is-bare-repository"]).strip() != "true":
        raise _fail("transition-incomplete")
    if _bare(directory, ["rev-parse", "--show-object-format"]).strip() != object_format:
        raise _fail("transition-incomplete")
    refs = _bare_refs(directory, object_format=object_format)
    if refs != [{"ref": "refs/heads/main", "object_id": base}]:
        raise _fail("transition-incomplete")
    _require_complete_object_set(directory, object_format=object_format)
    count, digest = _reachable_from(
        directory,
        ("--all",),
        object_format=object_format,
    )
    return {"repository_id": repository_id, "role": role, "relative_directory": f"remotes/{directory.name}", "object_format": object_format, "initial_refs": refs, "reachable_object_count": count, "reachable_objects_sha256": digest}


def _require_recorded_snapshot(
    directory: Path,
    recorded: object,
    repository_id: str,
    role: str,
    base: str,
    object_format: str,
) -> None:
    if not isinstance(recorded, Mapping) or _repository_snapshot(
        directory,
        repository_id,
        role,
        base,
        object_format,
    ) != dict(recorded):
        raise _fail("transition-incomplete")


def _prepare_bare(locked: LockedExternalState, repository: Path, attempt: int, role: str, base: str, object_format: str) -> tuple[Path, dict[str, Any]]:
    repository_id = _p02_repository_id(locked.repository_id, attempt, role)
    directory, created = locked.owned_repository_directory(
        "p02", attempt, repository_id, create=True
    )
    marker = directory / "HEAD"
    if created:
        try:
            result = run_git_unbound(
                directory.parent,
                ["init", "--bare", "--template=", f"--object-format={object_format}", str(directory)],
                check=False,
            )
            if result.returncode:
                raise _fail("transition-incomplete")
            _bare(directory, ["fetch", "--no-tags", str(repository), f"{base}:refs/heads/main"])
        except (GitCommandError, OSError) as error:
            raise _fail("transition-incomplete", error)
    return directory, _repository_snapshot(directory, repository_id, role, base, object_format)


def _write(locked: LockedExternalState, record: dict[str, Any], phase: str, **changes: object) -> dict[str, Any]:
    updated = dict(record)
    updated.update(changes)
    updated["phase"] = phase
    updated["generation"] = record["generation"] + 1
    try:
        locked.write_record("p02", int(record["attempt"]), updated, expected_generation=int(record["generation"]))
    except ExternalStateError as error:
        raise _fail("transition-incomplete", error)
    return updated


def _new_record(attempt: int, base: str, topology: dict[str, Any]) -> dict[str, Any]:
    return {"schema_version": 1, "generation": 1, "lab": _LAB, "attempt": attempt, "phase": "captured", "base_branch": "main", "base_head": base, "attempt_branch": f"academy/{_LAB}/{attempt}", "prepared_commit": None, "archive_ref": None, "archive_target": None, "transition_target": None, "original_topology": topology, "origin_repository": None, "upstream_repository": None}


def _latest(locked: LockedExternalState, object_format: str) -> dict[str, Any] | None:
    found = None
    try:
        attempts = locked.record_attempts("p02")
    except ExternalStateError as error:
        raise _fail("invalid-exercise-state", error)
    if attempts and attempts != tuple(range(1, attempts[-1] + 1)):
        raise _fail("invalid-exercise-state")
    for attempt in attempts:
        try:
            raw = locked.read_record("p02", attempt)
        except ExternalStateError as error:
            raise _fail("invalid-exercise-state", error)
        if raw is None:
            raise _fail("invalid-exercise-state")
        if raw is not None:
            if found is None and attempt != 1:
                raise _fail("invalid-exercise-state")
            if found is not None and found["phase"] != "restored":
                raise _fail("invalid-exercise-state")
            found = _decode_p02_record(raw, object_format=object_format)
            if found["attempt"] != attempt:
                raise _fail("invalid-exercise-state")
            for key in ("origin_repository", "upstream_repository"):
                repository = found[key]
                if repository is None:
                    continue
                role = "learner" if key == "origin_repository" else "official"
                if repository["repository_id"] != _p02_repository_id(
                    locked.repository_id, attempt, role
                ):
                    raise _fail("invalid-exercise-state")
                directory, _ = locked.owned_repository_directory(
                    "p02", attempt, str(repository["repository_id"])
                )
                if repository["relative_directory"] != f"remotes/{directory.name}":
                    raise _fail("invalid-exercise-state")
    return found


def _set_values(repository: Path, key: str, values: list[str] | None) -> None:
    try:
        cleared = run_git(repository, ["config", "--unset-all", key], check=False)
        if cleared.returncode not in {0, 5}:
            raise _fail("transition-incomplete")
        if values is not None:
            for value in values:
                result = run_git(repository, ["config", "--add", key, value], check=False)
                if result.returncode:
                    raise _fail("transition-incomplete")
    except (GitCommandError, OSError) as error:
        raise _fail("transition-incomplete", error)


def _local_values(origin: Path, upstream: Path) -> dict[str, list[str]]:
    origin_url = origin.as_uri()
    upstream_url = upstream.as_uri()
    return {"remote.origin.url": [origin_url], "remote.origin.pushurl": [origin_url], "remote.upstream.url": [upstream_url], "remote.upstream.pushurl": ["DISABLED"]}


def _verify_values(repository: Path, expected: Mapping[str, list[str] | None], keys: Sequence[str]) -> None:
    if any(_config_values(repository, key) != expected[key] for key in keys):
        raise _fail("remote-topology-mismatch")


def _verify_exact_topology(
    repository: Path,
    topology: Mapping[str, Any],
    local: Mapping[str, list[str]],
) -> None:
    original = topology["config"]
    for key in _CONFIG_KEYS[4:]:
        if _config_values(repository, key) != original[key]:
            raise _fail("transition-incomplete")
    for remote in ("origin", "upstream"):
        url_key = f"remote.{remote}.url"
        push_key = f"remote.{remote}.pushurl"
        observed_url = _config_values(repository, url_key)
        observed_push = _config_values(repository, push_key)
        if observed_url == local[url_key]:
            expected_fetch = local[url_key]
        elif observed_url == original[url_key]:
            expected_fetch = topology["effective_routes"][remote]["fetch"]
        else:
            raise _fail("transition-incomplete")
        if observed_push is None and original[push_key] is None:
            expected_push = (
                local[url_key]
                if observed_url == local[url_key]
                else topology["effective_routes"][remote]["push"]
            )
        elif observed_push == local[push_key]:
            expected_push = local[push_key]
        elif observed_push == original[push_key]:
            expected_push = topology["effective_routes"][remote]["push"]
        else:
            raise _fail("transition-incomplete")
        if (
            _effective(repository, remote, push=False) != expected_fetch
            or _effective(repository, remote, push=True) != expected_push
        ):
            raise _fail("transition-incomplete")


def _verify_unowned_config(
    repository: Path, original: Mapping[str, list[str] | None]
) -> None:
    if any(
        _config_values(repository, key) != original[key]
        for key in _CONFIG_KEYS[4:]
    ):
        raise _fail("transition-incomplete")


def _is_journaled_progress(
    observed: list[str] | None,
    source: list[str] | None,
    target: list[str] | None,
) -> bool:
    if observed == source or observed == target:
        return True
    if observed is None:
        return target is not None
    return bool(
        target is not None
        and len(observed) < len(target)
        and observed == target[: len(observed)]
    )


def _verify_original_topology(repository: Path, topology: Mapping[str, Any]) -> None:
    original = topology["config"]
    if any(_config_values(repository, key) != original[key] for key in _CONFIG_KEYS):
        raise _fail("transition-incomplete")
    for remote in ("origin", "upstream"):
        if (
            _effective(repository, remote, push=False)
            != topology["effective_routes"][remote]["fetch"]
            or _effective(repository, remote, push=True)
            != topology["effective_routes"][remote]["push"]
        ):
            raise _fail("transition-incomplete")


def _verify_activation_boundary(
    repository: Path,
    original: Mapping[str, list[str] | None],
    local: Mapping[str, list[str]],
    keys: Sequence[str],
    index: int,
    *,
    current_may_be_complete: bool,
) -> None:
    for position, key in enumerate(keys):
        observed = _config_values(repository, key)
        if position < index:
            expected: tuple[list[str] | None, ...] = (local[key],)
        elif position > index or not current_may_be_complete:
            expected = (original[key],)
        else:
            if _is_journaled_progress(observed, original[key], local[key]):
                continue
            expected = ()
        if not any(observed == candidate for candidate in expected):
            raise _fail("transition-incomplete")


def _verify_restoration_boundary(
    repository: Path,
    original: Mapping[str, list[str] | None],
    local: Mapping[str, list[str]],
    keys: Sequence[str],
    index: int,
    *,
    current_may_be_complete: bool,
) -> None:
    for position, key in enumerate(keys):
        observed = _config_values(repository, key)
        if position < index:
            expected: tuple[list[str] | None, ...] = (original[key],)
        elif position > index or not current_may_be_complete:
            expected = (local[key],)
        else:
            if _is_journaled_progress(observed, local[key], original[key]):
                continue
            expected = ()
        if not any(observed == candidate for candidate in expected):
            raise _fail("transition-incomplete")


def _derived_attempt_profile(
    repository: Path,
    base: str,
    authority: _VerifiedAuthority,
) -> bytes:
    """Apply only the captured tech-stack hunk to the canonical base profile."""
    _require_canonical_blob(
        repository,
        base,
        _PROFILE_PATH,
        code="transition-incomplete",
    )
    base_profile = _git(
        repository, ["show", f"{base}:{_PROFILE_PATH}"]
    ).encode("utf-8", "surrogateescape")
    patch_bytes = authority.read(
        f"academy/scenarios/{_LAB}/files/P02-worktree.patch"
    )
    try:
        with TemporaryDirectory(prefix="arbiter-academy-p02-profile-") as temporary:
            root = Path(temporary)
            profile = root / _PROFILE_PATH
            profile.parent.mkdir(parents=True)
            profile.write_bytes(base_profile)
            patch_path = root / "P02-worktree.patch"
            patch_path.write_bytes(patch_bytes)
            applied = run_git_unbound(
                root,
                [
                    "apply",
                    "--no-index",
                    f"--include={_PROFILE_PATH}",
                    str(patch_path),
                ],
                check=False,
            )
            if applied.returncode:
                raise _fail("transition-incomplete")
            # The process boundary uses Windows checkout conversion. Preparation commits
            # the canonical Git blob form, so bind the clean-filter newline form here.
            return profile.read_bytes().replace(b"\r\n", b"\n")
    except OSError as error:
        raise _fail("transition-incomplete", error)


def _canonical_profile_target(repository: Path, base: str) -> Path:
    try:
        target = ensure_within(repository, repository / _PROFILE_PATH)
        details = target.lstat()
        expected = _git(repository, ["show", f"{base}:{_PROFILE_PATH}"]).encode(
            "utf-8", "surrogateescape"
        )
        if (
            not stat.S_ISREG(details.st_mode)
            or stat.S_ISLNK(details.st_mode)
            or details.st_nlink != 1
            or target.read_bytes() != expected
        ):
            raise PathBoundaryError("learner profile source is not canonical")
        return target
    except (OSError, PathBoundaryError) as error:
        raise _fail("transition-incomplete", error)


def _create_prepared_commit(
    repository: Path, record: dict[str, Any], authority: _VerifiedAuthority
) -> str:
    branch = str(record["attempt_branch"])
    base = str(record["base_head"])
    scenario_bytes = authority.read(
        f"academy/scenarios/{_LAB}/files/scenario.json"
    )
    profile_bytes = _derived_attempt_profile(repository, base, authority)
    existing = _git_result(repository, ["show-ref", "--verify", "--quiet", f"refs/heads/{branch}"])
    if existing.returncode == 1:
        _canonical_profile_target(repository, base)
        _git(repository, ["switch", "-c", branch, base])
        try:
            target = ensure_within(
                repository,
                repository / "training_scenarios" / f"{_LAB}.json",
            )
            target.parent.mkdir(parents=True, exist_ok=True)
            target = ensure_within(repository, target)
            if os.path.lexists(target):
                raise PathBoundaryError("scenario target must not already exist")
            target.write_bytes(scenario_bytes)
            profile_target = _canonical_profile_target(repository, base)
            profile_target.write_bytes(profile_bytes)
        except (OSError, PathBoundaryError) as error:
            raise _fail("transition-incomplete", error)
        _git(
            repository,
            [
                "add",
                "--",
                profile_target.relative_to(repository).as_posix(),
                target.relative_to(repository).as_posix(),
            ],
        )
        _git(repository, ["commit", "-m", f"academy: prepare {_LAB} attempt {record['attempt']}"])
        commit = _git(repository, ["rev-parse", "HEAD"]).strip()
    elif existing.returncode:
        raise _fail("transition-incomplete")
    else:
        commit = _git(repository, ["rev-parse", f"refs/heads/{branch}"]).strip()
    _verify_prepared_commit(
        repository,
        record,
        authority,
        commit,
        scenario_bytes=scenario_bytes,
        profile_bytes=profile_bytes,
    )
    current = _git(repository, ["symbolic-ref", "--quiet", "--short", "HEAD"]).strip()
    if current != branch:
        _git(repository, ["switch", branch])
    return commit


def _verify_prepared_commit(
    repository: Path,
    record: Mapping[str, Any],
    authority: _VerifiedAuthority,
    commit: str,
    *,
    scenario_bytes: bytes | None = None,
    profile_bytes: bytes | None = None,
) -> None:
    base = str(record["base_head"])
    parent = _git(repository, ["rev-parse", f"{commit}^"]).strip()
    subject = _git(repository, ["show", "-s", "--format=%s", commit]).strip()
    paths = _git(repository, ["diff-tree", "--no-commit-id", "--name-only", "-r", commit]).splitlines()
    if (
        parent != base
        or subject != f"academy: prepare {_LAB} attempt {record['attempt']}"
        or paths != [_PROFILE_PATH, f"training_scenarios/{_LAB}.json"]
    ):
        raise _fail("transition-incomplete")
    _require_canonical_blob(
        repository,
        commit,
        f"training_scenarios/{_LAB}.json",
        code="transition-incomplete",
    )
    tracked = _git(repository, ["show", f"{commit}:training_scenarios/{_LAB}.json"]).encode("utf-8", "surrogateescape")
    if scenario_bytes is None:
        scenario_bytes = authority.read(
            f"academy/scenarios/{_LAB}/files/scenario.json"
        )
    if tracked != scenario_bytes:
        raise _fail("transition-incomplete")
    _require_canonical_blob(
        repository,
        commit,
        _PROFILE_PATH,
        code="transition-incomplete",
    )
    if profile_bytes is None:
        profile_bytes = _derived_attempt_profile(repository, base, authority)
    tracked_profile = _git(
        repository, ["show", f"{commit}:{_PROFILE_PATH}"]
    ).encode("utf-8", "surrogateescape")
    if tracked_profile != profile_bytes:
        raise _fail("transition-incomplete")


def validate_p02_prepared_commit(
    repository: Path,
    *,
    base_commit: str,
    prepared_commit: str,
    branch: str,
    attempt_number: int,
) -> bool:
    """Validate the exact P02 preparation commit against installed authority."""
    try:
        resolved = Path(repository).resolve()
        authority = _verified_epoch(resolved, base_commit)
        _verify_prepared_commit(
            resolved,
            {
                "base_head": base_commit,
                "attempt_branch": branch,
                "attempt": attempt_number,
            },
            authority,
            prepared_commit,
        )
        return True
    except (ExerciseStateError, GitCommandError, OSError, TypeError):
        return False


def _require_canonical_blob(
    repository: Path, revision: str, path: str, *, code: str
) -> None:
    entry = _git(
        repository, ["ls-tree", revision, "--", path], code=code
    ).strip()
    if re.fullmatch(rf"100644 blob [0-9a-f]+\t{re.escape(path)}", entry) is None:
        raise _fail(code)


def _verify_exact_worktree_patch(
    repository: Path, authority: _VerifiedAuthority, prepared_commit: str
) -> None:
    _validate_patch_targets(repository)
    expected_status = {f" M {path}" for path in _PATCH_PATHS}
    status = set(
        _git(repository, ["status", "--porcelain", "--untracked-files=all"]).splitlines()
    )
    if status != expected_status:
        raise _fail("transition-incomplete")
    if _git_result(repository, ["diff", "--cached", "--quiet"]).returncode != 0:
        raise _fail("transition-incomplete")
    if _git(repository, ["diff", "--summary"]):
        raise _fail("transition-incomplete")
    patch_bytes = authority.read(
        f"academy/scenarios/{_LAB}/files/P02-worktree.patch"
    )
    for path in _PATCH_PATHS:
        _require_canonical_blob(
            repository, prepared_commit, path, code="transition-incomplete"
        )
        staged = _git(repository, ["ls-files", "--stage", "--", path]).strip()
        if re.fullmatch(rf"100644 [0-9a-f]+ 0\t{re.escape(path)}", staged) is None:
            raise _fail("transition-incomplete")
    try:
        with TemporaryDirectory(prefix="arbiter-academy-p02-worktree-") as temporary:
            root = Path(temporary)
            patch_path = root / "P02-worktree.patch"
            patch_path.write_bytes(patch_bytes)
            for path in _PATCH_PATHS:
                destination = root / path
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(
                    _git(repository, ["show", f"{prepared_commit}:{path}"]).encode(
                        "utf-8", "surrogateescape"
                    )
                )
            applied = run_git_unbound(
                root,
                ["apply", "--no-index", *_WORK_PATCH_INCLUDES, str(patch_path)],
                check=False,
            )
            if applied.returncode:
                raise _fail("transition-incomplete")
            for path in _PATCH_PATHS:
                observed = repository / path
                if (
                    not observed.is_file()
                    or observed.is_symlink()
                    or observed.read_bytes() != (root / path).read_bytes()
                ):
                    raise _fail("transition-incomplete")
    except OSError as error:
        raise _fail("transition-incomplete", error)


def _validate_patch_targets(repository: Path) -> None:
    try:
        for path in _PATCH_PATHS:
            ensure_within(repository, Path(path))
    except (OSError, PathBoundaryError) as error:
        raise _fail("transition-incomplete", error)


def _apply_patch(repository: Path, authority: _VerifiedAuthority) -> None:
    patch_bytes = authority.read(
        f"academy/scenarios/{_LAB}/files/P02-worktree.patch"
    )
    _validate_patch_targets(repository)
    status = _git(repository, ["status", "--porcelain", "--untracked-files=all"])
    if not status:
        try:
            with TemporaryDirectory(prefix="arbiter-academy-p02-apply-") as temporary:
                patch_path = Path(temporary) / "P02-worktree.patch"
                patch_path.write_bytes(patch_bytes)
                _validate_patch_targets(repository)
                _git(
                    repository,
                    ["apply", "--check", *_WORK_PATCH_INCLUDES, str(patch_path)],
                )
                _validate_patch_targets(repository)
                _git(repository, ["apply", *_WORK_PATCH_INCLUDES, str(patch_path)])
        except OSError as error:
            raise _fail("transition-incomplete", error)
    _verify_exact_worktree_patch(
        repository, authority, _git(repository, ["rev-parse", "HEAD"]).strip()
    )


def preflight_p02(repository: Path, lab: Lab) -> str:
    """Prove a fresh P02 attempt is safe before external state is created."""
    if lab.id != _LAB:
        raise _fail("invalid-exercise-state")
    repository = Path(repository).resolve()
    try:
        validate_repository_git_config(repository)
    except GitCommandError as error:
        raise _fail("invalid-exercise-state", error)
    base = _git(repository, ["rev-parse", "main"]).strip()
    _verified_epoch(repository, base)
    if (
        _git(repository, ["symbolic-ref", "--quiet", "--short", "HEAD"]).strip()
        != "main"
        or _git(repository, ["status", "--porcelain", "--untracked-files=all"])
    ):
        raise _fail("transition-incomplete")
    _capture_topology(repository)
    return base


def preflight_p08(repository: Path) -> tuple[str, Lab, _VerifiedAuthority]:
    """Capture P08's installed authority before any sidecar or Git mutation seam."""
    resolved = Path(repository).resolve()
    try:
        validate_repository_git_config(resolved)
    except GitCommandError as error:
        raise _fail("invalid-exercise-state", error)
    base = _git(resolved, ["rev-parse", "main"], code="installed-authority-required").strip()
    authority = _verified_p08_epoch(resolved, base)
    try:
        lab = authority.catalog.lab(_P08_LAB)
    except CatalogError as error:
        raise _fail("installed-authority-required", error)
    return base, lab, authority


def _p08_path_hash(path: Path) -> str:
    try:
        value = os.path.normcase(str(path.resolve(strict=False))).replace("\\", "/")
    except OSError as error:
        raise _fail("p08-transition-incomplete", error)
    return hashlib.sha256(
        f"arbiter-academy/p08-worktree-path/v1\0{value}\n".encode("utf-8")
    ).hexdigest()


def _p08_dirty_digest() -> str:
    return _p08_status_digest(b"?? .arbiter-academy-p08-dirty\0")


def _p08_status_digest(raw: bytes) -> str:
    return hashlib.sha256(b"arbiter-academy/p08-dirty-status/v1\0" + raw).hexdigest()


def _p08_raw_porcelain(repository: Path) -> bytes:
    raw = _git(
        repository,
        ["status", "--porcelain=v1", "-z", "--untracked-files=all"],
        code="p08-transition-incomplete",
    ).encode("utf-8", "surrogateescape")
    if len(raw) > 65_536:
        raise _fail("p08-transition-incomplete")
    return raw


def _p08_redirect(details: os.stat_result) -> bool:
    return bool(
        stat.S_ISLNK(details.st_mode)
        or getattr(details, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    )


def _p08_plain_directory(path: Path) -> Path:
    try:
        details = path.lstat()
    except OSError as error:
        raise _fail("p08-transition-incomplete", error)
    if _p08_redirect(details) or not stat.S_ISDIR(details.st_mode):
        raise _fail("p08-transition-incomplete")
    try:
        return path.resolve(strict=True)
    except OSError as error:
        raise _fail("p08-transition-incomplete", error)


def _p08_git_directory(root: Path, value: str) -> Path:
    candidate = Path(value.strip())
    if not candidate.is_absolute():
        candidate = root / candidate
    return _p08_plain_directory(candidate)


def _p08_linked_git_administration_is_exact(
    repository: Path, target: Path, item: Mapping[str, Any]
) -> None:
    common = _p08_git_directory(
        repository,
        _git(repository, ["rev-parse", "--git-common-dir"], code="p08-transition-incomplete"),
    )
    target_common = _p08_git_directory(
        target,
        _git(target, ["rev-parse", "--git-common-dir"], code="p08-transition-incomplete"),
    )
    administration_root = _p08_plain_directory(common / "worktrees")
    admin_id = item["git_admin_id"]
    if not isinstance(admin_id, str):
        raise _fail("p08-transition-incomplete")
    expected = _p08_plain_directory(administration_root / admin_id)
    actual = _p08_git_directory(
        target,
        _git(target, ["rev-parse", "--git-dir"], code="p08-transition-incomplete"),
    )
    if (
        target_common != common
        or expected.parent != administration_root
        or expected.name != admin_id
        or actual != expected
    ):
        raise _fail("p08-transition-incomplete")


def _p08_existing_linked_worktree_is_exact(
    repository: Path, target: Path, item: Mapping[str, Any]
) -> bool:
    """Return whether an already-present linked worktree is the exact resumable prefix."""
    try:
        details = target.lstat()
    except FileNotFoundError:
        return False
    except OSError as error:
        raise _fail("p08-transition-incomplete", error)
    if _p08_redirect(details) or not stat.S_ISDIR(details.st_mode):
        raise _fail("p08-transition-incomplete")
    git_file = target / ".git"
    try:
        git_details = git_file.lstat()
    except OSError as error:
        raise _fail("p08-transition-incomplete", error)
    if _p08_redirect(git_details) or not stat.S_ISREG(git_details.st_mode):
        raise _fail("p08-transition-incomplete")
    _p08_linked_git_administration_is_exact(repository, target, item)
    branch = _git(
        target, ["symbolic-ref", "--quiet", "--short", "HEAD"], code="p08-transition-incomplete"
    ).strip()
    expected_branch = str(item["branch_ref"]).removeprefix("refs/heads/")
    if branch != expected_branch:
        raise _fail("p08-transition-incomplete")
    if _git(target, ["rev-parse", "HEAD"], code="p08-transition-incomplete").strip() != item["head_oid"]:
        raise _fail("p08-transition-incomplete")
    status = _p08_raw_porcelain(target)
    if item["role"] == "dirty-unmerged":
        marker = target / ".arbiter-academy-p08-dirty"
        try:
            marker_details = marker.lstat()
            marker_bytes = marker.read_bytes()
        except OSError as error:
            raise _fail("p08-transition-incomplete", error)
        if (
            _p08_redirect(marker_details)
            or not stat.S_ISREG(marker_details.st_mode)
            or marker_bytes != b"Arbiter Academy P08 preserved dirty fixture.\n"
            or status != b"?? .arbiter-academy-p08-dirty\0"
            or item["dirty_status_sha256"] != _p08_status_digest(status)
        ):
            raise _fail("p08-transition-incomplete")
    elif status:
        raise _fail("p08-transition-incomplete")
    return True


def _p08_planned_linked_worktree_is_exact_or_available(
    repository: Path, target: Path, item: Mapping[str, Any]
) -> bool:
    """Accept an exact linked worktree, or prove its Git-admin slot is absent."""
    if _p08_existing_linked_worktree_is_exact(repository, target, item):
        return True
    common = _p08_git_directory(
        repository,
        _git(repository, ["rev-parse", "--git-common-dir"], code="p08-transition-incomplete"),
    )
    administration_root = common / "worktrees"
    if os.path.lexists(administration_root):
        administration_root = _p08_plain_directory(administration_root)
        admin_id = item["git_admin_id"]
        if not isinstance(admin_id, str) or os.path.lexists(administration_root / admin_id):
            raise _fail("p08-transition-incomplete")
    return False


def _p08_closed_worktree_inventory(
    repository: Path,
    locked: LockedExternalState,
    record: Mapping[str, Any],
    attempt_head: str,
    *,
    primary_released: bool,
) -> None:
    """Require the three recorded P08 worktrees while ignoring unrelated ones."""
    raw = _git(
        repository,
        ["worktree", "list", "--porcelain", "-z"],
        code="p08-transition-incomplete",
    )
    if not raw.endswith("\0\0"):
        raise _fail("p08-transition-incomplete")
    entries = raw[:-2].split("\0\0")
    if any(not entry for entry in entries):
        raise _fail("p08-transition-incomplete")
    observed: dict[Path, tuple[str, str]] = {}
    parsed_entries: list[dict[str, str]] = []
    oid = _oid_pattern(_object_format(repository))
    for entry in entries:
        fields = entry.split("\0")
        values: dict[str, str] = {}
        for field in fields:
            key, separator, value = field.partition(" ")
            if not key or key in values:
                raise _fail("p08-transition-incomplete")
            if separator:
                values[key] = value
            elif key in {"bare", "detached"}:
                values[key] = ""
            else:
                raise _fail("p08-transition-incomplete")
        if "worktree" not in values:
            raise _fail("p08-transition-incomplete")
        parsed_entries.append(values)

    primary = record["worktrees"][0]
    if primary_released:
        primary_expected = (str(record["base_oid"]), "refs/heads/main")
    else:
        primary_expected = (attempt_head, str(primary["branch_ref"]))
    expected: dict[Path, tuple[str, str]] = {
        _p08_plain_directory(repository): primary_expected
    }
    p08_worktree_root: Path | None = None
    for item in record["worktrees"][1:]:
        parent = locked.owned_p08_worktree_parent(
            int(record["attempt"]), str(item["worktree_id"])
        )
        target = _p08_plain_directory(parent / str(item["worktree_id"]))
        if p08_worktree_root is None:
            p08_worktree_root = parent.parent
        expected[target] = (str(item["head_oid"]), str(item["branch_ref"]))
    for values in parsed_entries:
        path_value = values.get("worktree")
        if not isinstance(path_value, str):
            raise _fail("p08-transition-incomplete")
        candidate = Path(path_value)
        try:
            target = candidate.resolve(strict=False)
        except OSError:
            raise _fail("p08-transition-incomplete")
        if target in expected:
            if (
                set(values) != {"worktree", "HEAD", "branch"}
                or oid.fullmatch(values["HEAD"]) is None
                or target in observed
            ):
                raise _fail("p08-transition-incomplete")
            observed[target] = (values["HEAD"], values["branch"])
            continue
        branch = values.get("branch", "")
        p08_shaped = branch.startswith(f"refs/heads/academy/{_P08_LAB}/") or branch.startswith(
            str(record["namespace"])
        )
        if p08_worktree_root is not None:
            try:
                target.relative_to(p08_worktree_root)
                p08_shaped = True
            except ValueError:
                pass
        if p08_shaped:
            raise _fail("p08-transition-incomplete")
    if observed != expected:
        raise _fail("p08-transition-incomplete")


def _p08_prepared_attempt_is_exact(
    repository: Path, authority: _VerifiedAuthority, base: str, branch: str, attempt: int
) -> str:
    prepared = _git(
        repository, ["rev-parse", f"refs/heads/{branch}"], code="p08-transition-incomplete"
    ).strip()
    if (
        _git(repository, ["rev-parse", f"{prepared}^"], code="p08-transition-incomplete").strip()
        != base
        or _git(
            repository, ["log", "-1", "--format=%s", prepared], code="p08-transition-incomplete"
        ).strip()
        != f"academy: prepare {_P08_LAB} attempt {attempt}"
    ):
        raise _fail("p08-transition-incomplete")
    target = f"training_scenarios/{_P08_LAB}.json"
    changed = _git(
        repository, ["diff", "--name-status", base, prepared], code="p08-transition-incomplete"
    ).splitlines()
    if changed != [f"A\t{target}"]:
        raise _fail("p08-transition-incomplete")
    if _git(
        repository, ["show", f"{prepared}:{target}"], code="p08-transition-incomplete"
    ).encode("utf-8", "surrogateescape") != authority.read(
        f"academy/scenarios/{_P08_LAB}/files/scenario.json"
    ):
        raise _fail("p08-transition-incomplete")
    return prepared


def _p08_scenario_target(repository: Path) -> Path:
    try:
        return ensure_within(
            repository, Path("training_scenarios") / f"{_P08_LAB}.json"
        )
    except PathBoundaryError as error:
        raise _fail("p08-transition-incomplete", error)


def _p08_fixture_ref_prefix_is_exact(
    repository: Path, record: Mapping[str, Any], *, require_complete: bool
) -> list[bool]:
    fixtures = list(record["refs"][2:])
    expected = [str(item["ref_name"]) for item in fixtures]
    observed = _git(
        repository,
        ["for-each-ref", "--format=%(refname)", str(record["namespace"])],
        code="p08-transition-incomplete",
    ).splitlines()
    if set(observed) - set(expected):
        raise _fail("p08-transition-incomplete")
    present: list[bool] = []
    for item in fixtures:
        ref_name = str(item["ref_name"])
        exists = _git_result(
            repository, ["show-ref", "--verify", "--quiet", ref_name], code="p08-transition-incomplete"
        )
        if exists.returncode not in {0, 1}:
            raise _fail("p08-transition-incomplete")
        present.append(exists.returncode == 0)
        if exists.returncode == 0 and _git(
            repository, ["rev-parse", ref_name], code="p08-transition-incomplete"
        ).strip() != item["object_id"]:
            raise _fail("p08-transition-incomplete")
    if any(present[index] for index in range(1, len(present)) if not present[index - 1]):
        raise _fail("p08-transition-incomplete")
    if require_complete and present != [True] * len(fixtures):
        raise _fail("p08-transition-incomplete")
    return present


def _new_p08_record(
    locked: LockedExternalState, attempt: int, base: str, repository: Path
) -> dict[str, Any]:
    namespace = f"refs/heads/academy-fixtures/p08/{attempt}/"
    attempt_ref = f"refs/heads/academy/{_P08_LAB}/{attempt}"
    ids = {
        role: _p08_worktree_id(locked.repository_id, attempt, role)
        for role in ("current-attempt", "merged-clean", "dirty-unmerged")
    }
    return {
        "schema_version": 1, "generation": 1, "lab_id": _P08_LAB,
        "attempt": attempt, "phase": "creating-attempt", "namespace": namespace,
        "base_ref": "refs/heads/main", "base_oid": base, "attempt_ref": attempt_ref,
        "prepared_oid": None,
        "refs": [
            {"ref_name": "refs/heads/main", "object_id": base, "role": "selected-base", "binding": "fixed"},
            {"ref_name": attempt_ref, "object_id": None, "role": "current-attempt", "binding": "learner-descendant"},
            {"ref_name": namespace + "merged-clean", "object_id": base, "role": "merged-clean", "binding": "fixed"},
            {"ref_name": namespace + "dirty-unmerged", "object_id": None, "role": "dirty-unmerged", "binding": "fixed"},
            {"ref_name": namespace + "unique-unmerged", "object_id": None, "role": "unique-unmerged", "binding": "fixed"},
        ],
        "worktrees": [
            {"worktree_id": ids["current-attempt"], "path_sha256": _p08_path_hash(repository), "git_admin_id": None, "branch_ref": attempt_ref, "head_oid": None, "expected_presence": True, "role": "current-attempt", "dirty_status_sha256": None},
            {"worktree_id": ids["merged-clean"], "path_sha256": None, "git_admin_id": ids["merged-clean"], "branch_ref": namespace + "merged-clean", "head_oid": base, "expected_presence": True, "role": "merged-clean", "dirty_status_sha256": None},
            {"worktree_id": ids["dirty-unmerged"], "path_sha256": None, "git_admin_id": ids["dirty-unmerged"], "branch_ref": namespace + "dirty-unmerged", "head_oid": None, "expected_presence": True, "role": "dirty-unmerged", "dirty_status_sha256": None},
        ],
    }


def _write_p08(
    locked: LockedExternalState,
    record: dict[str, Any],
    phase: str,
    *,
    object_format: str,
    **changes: object,
) -> dict[str, Any]:
    next_record = dict(record)
    next_record.update(changes)
    next_record["phase"] = phase
    next_record["generation"] = int(record["generation"]) + 1
    _decode_p08_record(next_record, object_format=object_format, repository_id=locked.repository_id)
    try:
        locked.write_record("p08", int(next_record["attempt"]), next_record, expected_generation=int(record["generation"]))
    except ExternalStateError as error:
        raise _fail("p08-transition-incomplete", error)
    return next_record


def _p08_attempt_resources_are_exact(
    repository: Path,
    locked: LockedExternalState,
    record: Mapping[str, Any],
    *,
    primary_released: bool,
) -> str:
    """Verify the retained P08 attempt without modifying its resources."""
    if (
        _git(repository, ["rev-parse", "refs/heads/main"], code="p08-transition-incomplete").strip()
        != record["base_oid"]
    ):
        raise _fail("p08-transition-incomplete")
    _p08_fixture_ref_prefix_is_exact(repository, record, require_complete=True)
    attempt_head = _git(
        repository,
        ["rev-parse", "--verify", str(record["attempt_ref"])],
        code="p08-transition-incomplete",
    ).strip()
    if _git_result(
        repository,
        ["merge-base", "--is-ancestor", str(record["prepared_oid"]), attempt_head],
        code="p08-transition-incomplete",
    ).returncode:
        raise _fail("p08-transition-incomplete")
    primary = record["worktrees"][0]
    if _p08_path_hash(repository) != primary["path_sha256"]:
        raise _fail("p08-transition-incomplete")
    branch = _git(
        repository,
        ["symbolic-ref", "--quiet", "--short", "HEAD"],
        code="p08-transition-incomplete",
    ).strip()
    head = _git(repository, ["rev-parse", "HEAD"], code="p08-transition-incomplete").strip()
    if primary_released:
        if branch != "main" or head != record["base_oid"]:
            raise _fail("p08-transition-incomplete")
    elif branch != str(record["attempt_ref"]).removeprefix("refs/heads/") or head != attempt_head:
        raise _fail("p08-transition-incomplete")
    if _p08_raw_porcelain(repository):
        raise _fail("p08-transition-incomplete")
    for item in record["worktrees"][1:]:
        parent = locked.owned_p08_worktree_parent(
            int(record["attempt"]), str(item["worktree_id"])
        )
        target = parent / str(item["worktree_id"])
        if (
            _p08_path_hash(target) != item["path_sha256"]
            or not _p08_existing_linked_worktree_is_exact(repository, target, item)
        ):
            raise _fail("p08-transition-incomplete")
    _p08_closed_worktree_inventory(
        repository,
        locked,
        record,
        attempt_head,
        primary_released=primary_released,
    )
    return attempt_head


def verify_p08(
    repository: Path, store: ExternalStateStore, attempt: P08AttemptIdentity
) -> P08LiveState:
    """Return the path-free canonical live P08 observation for one report attempt."""
    repository = Path(repository).resolve()
    base = _git(repository, ["rev-parse", "main"], code="p08-report-mismatch").strip()
    _verified_p08_epoch(repository, base)
    object_format = _object_format(repository)
    with _locked_store(store) as locked:
        record = locked.read_record("p08", int(attempt.attempt))
        if record is None:
            raise _fail("p08-state-mismatch")
        record = _decode_p08_record(
            record, object_format=object_format, repository_id=locked.repository_id
        )
        if (
            record["phase"] != "active"
            or record["base_oid"] != base
            or attempt.branch != str(record["attempt_ref"]).removeprefix("refs/heads/")
            or attempt.prepared_commit != record["prepared_oid"]
            or _git(
                repository,
                ["rev-parse", str(record["attempt_ref"])],
                code="p08-report-mismatch",
            ).strip()
            != attempt.head_commit
        ):
            raise _fail("p08-state-mismatch")
        live_head = _p08_attempt_resources_are_exact(
            repository, locked, record, primary_released=False
        )
        parents = _git(
            repository,
            ["rev-list", "--parents", "-n", "1", attempt.head_commit],
            code="p08-report-mismatch",
        ).split()
        if parents != [attempt.head_commit, attempt.prepared_commit]:
            raise _fail("p08-report-mismatch")
        paths = _git(
            repository,
            ["diff-tree", "--no-commit-id", "--name-only", "-r", attempt.head_commit],
            code="p08-report-mismatch",
        ).splitlines()
        if paths != [_P08_REPORT_PATH]:
            raise _fail("p08-report-mismatch")
        ref_facts = (
            ("clean", "base", "preserve"),
            ("clean", "current-attempt", "preserve"),
            ("clean", "merged-clean", "eligible-for-explicit-review"),
            ("dirty", "unmerged-dirty", "preserve"),
            ("none", "unmerged-unique", "preserve"),
        )
        refs: list[P08LiveRef] = []
        for item, (worktree_state, classification, recommendation) in zip(
            record["refs"], ref_facts, strict=True
        ):
            observation = str(item["object_id"])
            live = live_head if item["role"] == "current-attempt" else observation
            merged = _git_result(
                repository,
                ["merge-base", "--is-ancestor", live, base],
                code="p08-report-mismatch",
            ).returncode == 0
            count = _git(
                repository,
                ["rev-list", "--count", f"{base}..{live}"],
                code="p08-report-mismatch",
            ).strip()
            if not count.isdecimal():
                raise _fail("p08-report-mismatch")
            refs.append(
                P08LiveRef(
                    str(item["ref_name"]), str(item["role"]), observation, live,
                    worktree_state, merged, int(count), classification, recommendation,
                )
            )
        worktree_facts = (
            (False, "current-attempt", "preserve"),
            (False, "merged-clean", "eligible-for-explicit-review"),
            (True, "unmerged-dirty", "preserve"),
        )
        worktrees = tuple(
            P08LiveWorktree(
                str(item["worktree_id"]), str(item["role"]), str(item["branch_ref"]),
                str(item["head_oid"]),
                live_head if item["role"] == "current-attempt" else str(item["head_oid"]),
                dirty, classification, recommendation,
            )
            for item, (dirty, classification, recommendation) in zip(
                record["worktrees"], worktree_facts, strict=True
            )
        )
        provisional = P08LiveState(
            locked.repository_id, "refs/heads/main", base, str(record["attempt_ref"]),
            str(record["prepared_oid"]), attempt.head_commit, live_head,
            tuple(refs), worktrees, "",
        )
        return P08LiveState(
            provisional.repository_id, provisional.base_ref, provisional.base_oid,
            provisional.attempt_ref, provisional.prepared_oid, provisional.observation_oid,
            provisional.live_head_oid, provisional.refs, provisional.worktrees,
            _p08_live_state_digest(provisional),
        )


def reset_p08(repository: Path, store: ExternalStateStore) -> "PreparedLab":
    """Supersede one exact P08 attempt, retaining all learner-visible resources."""
    repository = Path(repository).resolve()
    base = _git(repository, ["rev-parse", "main"], code="p08-transition-incomplete").strip()
    authority = _verified_p08_epoch(repository, base)
    try:
        lab = authority.catalog.lab(_P08_LAB)
    except CatalogError as error:
        raise _fail("installed-authority-required", error)
    object_format = _object_format(repository)
    with _locked_store(store) as locked:
        attempts = locked.record_attempts("p08")
        if not attempts:
            raise _fail("p08-state-mismatch")
        record = locked.read_record("p08", max(attempts))
        if record is None:
            raise _fail("p08-state-mismatch")
        record = _decode_p08_record(
            record, object_format=object_format, repository_id=locked.repository_id
        )
        if record["base_oid"] != base:
            raise _fail("p08-state-mismatch")
        if record["phase"] == "active":
            _p08_attempt_resources_are_exact(
                repository, locked, record, primary_released=False
            )
            record = _write_p08(locked, record, "superseding", object_format=object_format)
        if record["phase"] == "superseding":
            current = _git(
                repository,
                ["symbolic-ref", "--quiet", "--short", "HEAD"],
                code="p08-transition-incomplete",
            ).strip()
            if current == str(record["attempt_ref"]).removeprefix("refs/heads/"):
                _p08_attempt_resources_are_exact(
                    repository, locked, record, primary_released=False
                )
                _git(repository, ["switch", "main"], code="p08-transition-incomplete")
            elif current != "main":
                raise _fail("p08-transition-incomplete")
            _p08_attempt_resources_are_exact(
                repository, locked, record, primary_released=True
            )
            record = _write_p08(locked, record, "superseded", object_format=object_format)
        if record["phase"] != "superseded":
            raise _fail("p08-transition-incomplete")
        _p08_attempt_resources_are_exact(
            repository, locked, record, primary_released=True
        )
    return prepare_p08(repository, store, lab)


def _p08_expected_report(
    repository: Path, record: Mapping[str, Any], base: str
) -> dict[str, object]:
    ref_facts = (
        ("clean", "base", "preserve"),
        ("clean", "current-attempt", "preserve"),
        ("clean", "merged-clean", "eligible-for-explicit-review"),
        ("dirty", "unmerged-dirty", "preserve"),
        ("none", "unmerged-unique", "preserve"),
    )
    refs: list[dict[str, object]] = []
    for item, (worktree_state, classification, recommendation) in zip(
        record["refs"], ref_facts, strict=True
    ):
        observation = str(item["object_id"])
        merged = _git_result(
            repository,
            ["merge-base", "--is-ancestor", observation, base],
            code="p08-report-mismatch",
        ).returncode == 0
        count = _git(
            repository,
            ["rev-list", "--count", f"{base}..{observation}"],
            code="p08-report-mismatch",
        ).strip()
        if not count.isdecimal():
            raise _fail("p08-report-mismatch")
        refs.append(
            {
                "ref": item["ref_name"],
                "object_id": observation,
                "worktree_state": worktree_state,
                "merged_into_base": merged,
                "unique_commits": int(count),
                "classification": classification,
                "recommendation": recommendation,
            }
        )
    worktree_facts = (
        (False, "current-attempt", "preserve"),
        (False, "merged-clean", "eligible-for-explicit-review"),
        (True, "unmerged-dirty", "preserve"),
    )
    worktrees = [
        {
            "worktree_id": item["worktree_id"],
            "branch_ref": item["branch_ref"],
            "head": item["head_oid"],
            "present": True,
            "dirty": dirty,
            "classification": classification,
            "recommendation": recommendation,
        }
        for item, (dirty, classification, recommendation) in zip(
            record["worktrees"], worktree_facts, strict=True
        )
    ]
    return {
        "schema_version": 1,
        "base": {"ref": "refs/heads/main", "object_id": base},
        "refs": refs,
        "worktrees": worktrees,
    }


def validate_p08_checkpoint(
    repository: Path, store: ExternalStateStore, attempt: P08AttemptIdentity
) -> bool:
    """Accept only the exact canonical P08 report blob on its sole evidence commit."""
    try:
        repository = Path(repository).resolve()
        state = verify_p08(repository, store, attempt)
        base = state.base_oid
        object_format = _object_format(repository)
        with _locked_store(store) as locked:
            record = locked.read_record("p08", int(attempt.attempt))
            if record is None:
                return False
            record = _decode_p08_record(
                record, object_format=object_format, repository_id=locked.repository_id
            )
            entry = _git(
                repository,
                ["ls-tree", "-z", attempt.head_commit, "--", _P08_REPORT_PATH],
                code="p08-report-mismatch",
            )
            metadata, separator, path = entry.removesuffix("\0").partition("\t")
            mode, kind, blob_oid = metadata.split() if separator else ("", "", "")
            if (
                not entry.endswith("\0")
                or path != _P08_REPORT_PATH
                or mode != "100644"
                or kind != "blob"
                or _oid_pattern(object_format).fullmatch(blob_oid) is None
            ):
                return False
            raw = _git(
                repository,
                ["show", f"{attempt.head_commit}:{_P08_REPORT_PATH}"],
                code="p08-report-mismatch",
            ).encode("utf-8", "surrogateescape")
            if raw.startswith(b"\xef\xbb\xbf"):
                return False
            decoded = raw.decode("utf-8")
            report = json.loads(decoded)
            expected = _p08_expected_report(repository, record, base)
            canonical = json.dumps(
                expected, sort_keys=True, separators=(",", ":"), ensure_ascii=False
            ).encode("utf-8") + b"\n"
            return raw == canonical and report == expected
    except (ExerciseStateError, ExternalStateError, GitCommandError, OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
        return False


def prepare_p08(repository: Path, store: ExternalStateStore, lab: Lab) -> "PreparedLab":
    """Create P08's append-only prepared fixture; reset/report semantics are deferred."""
    if lab.id != _P08_LAB:
        raise _fail("p08-state-mismatch")
    repository = Path(repository).resolve()
    scenario_target = _p08_scenario_target(repository)
    base = _git(repository, ["rev-parse", "main"], code="p08-transition-incomplete").strip()
    authority = _verified_p08_epoch(repository, base)
    object_format = _object_format(repository)
    with _locked_store(store) as locked:
        attempts = locked.record_attempts("p08")
        if attempts:
            record = locked.read_record("p08", max(attempts))
            if record is None:
                raise _fail("p08-state-mismatch")
            record = _decode_p08_record(record, object_format=object_format, repository_id=locked.repository_id)
        else:
            if _git(repository, ["symbolic-ref", "--quiet", "--short", "HEAD"], code="p08-transition-incomplete").strip() != "main" or _git(repository, ["status", "--porcelain", "--untracked-files=all"], code="p08-transition-incomplete"):
                raise _fail("p08-transition-incomplete")
            record = _new_p08_record(locked, 1, base, repository)
            try:
                locked.write_record("p08", 1, record, expected_generation=0)
            except ExternalStateError as error:
                raise _fail("p08-transition-incomplete", error)
        if record["base_oid"] != base:
            raise _fail("p08-state-mismatch")
        if record["phase"] == "superseding":
            raise _fail("p08-transition-incomplete")
        if record["phase"] == "superseded":
            _p08_attempt_resources_are_exact(
                repository, locked, record, primary_released=True
            )
            next_attempt = int(record["attempt"]) + 1
            if next_attempt > 32:
                raise _fail("p08-state-mismatch")
            record = _new_p08_record(locked, next_attempt, base, repository)
            try:
                locked.write_record("p08", next_attempt, record, expected_generation=0)
            except ExternalStateError as error:
                raise _fail("p08-transition-incomplete", error)
        attempt = int(record["attempt"])
        branch = f"academy/{_P08_LAB}/{attempt}"
        if record["phase"] == "creating-attempt":
            exists = _git_result(repository, ["show-ref", "--verify", "--quiet", f"refs/heads/{branch}"], code="p08-transition-incomplete")
            if exists.returncode == 1:
                _git(repository, ["switch", "-c", branch, base], code="p08-transition-incomplete")
                scenario_target.parent.mkdir(parents=True, exist_ok=True)
                scenario_target.write_bytes(authority.read(f"academy/scenarios/{_P08_LAB}/files/scenario.json"))
                _git(repository, ["add", "--", scenario_target.relative_to(repository).as_posix()], code="p08-transition-incomplete")
                _git(repository, ["commit", "-m", f"academy: prepare {_P08_LAB} attempt {attempt}"], code="p08-transition-incomplete")
            elif exists.returncode:
                raise _fail("p08-transition-incomplete")
            prepared = _p08_prepared_attempt_is_exact(
                repository, authority, base, branch, attempt
            )
            refs = [dict(item) for item in record["refs"]]
            for item in refs:
                if item["role"] != "selected-base":
                    item["object_id"] = prepared
            refs[2]["object_id"] = base
            worktrees = [dict(item) for item in record["worktrees"]]
            worktrees[0]["head_oid"] = prepared
            worktrees[1]["head_oid"] = base
            worktrees[2]["head_oid"] = prepared
            record = _write_p08(locked, record, "creating-refs", object_format=object_format, prepared_oid=prepared, refs=refs, worktrees=worktrees)
        prepared = str(record["prepared_oid"])
        if record["phase"] == "creating-refs":
            present = _p08_fixture_ref_prefix_is_exact(
                repository, record, require_complete=False
            )
            for item, exists in zip(record["refs"][2:], present, strict=True):
                if not exists:
                    _git(repository, ["update-ref", str(item["ref_name"]), str(item["object_id"])], code="p08-transition-incomplete")
            _p08_fixture_ref_prefix_is_exact(repository, record, require_complete=True)
            record = _write_p08(locked, record, "planning-worktrees", object_format=object_format)
        if record["phase"] in {"planning-worktrees", "creating-worktrees", "active"}:
            _p08_fixture_ref_prefix_is_exact(repository, record, require_complete=True)
        if record["phase"] == "active":
            _p08_attempt_resources_are_exact(
                repository, locked, record, primary_released=False
            )
        if record["phase"] == "planning-worktrees":
            worktrees = [dict(item) for item in record["worktrees"]]
            for item in worktrees[1:]:
                parent = locked.owned_p08_worktree_parent(
                    attempt, str(item["worktree_id"])
                )
                item["path_sha256"] = _p08_path_hash(parent / str(item["worktree_id"]))
            worktrees[2]["dirty_status_sha256"] = _p08_dirty_digest()
            record = _write_p08(locked, record, "creating-worktrees", object_format=object_format, worktrees=worktrees)
        if record["phase"] == "creating-worktrees":
            linked = record["worktrees"][1:]
            completed: list[bool] = []
            targets: list[Path] = []
            for item in linked:
                parent = locked.owned_p08_worktree_parent(
                    attempt, str(item["worktree_id"])
                )
                target = parent / str(item["worktree_id"])
                targets.append(target)
                completed.append(
                    _p08_planned_linked_worktree_is_exact_or_available(
                        repository, target, item
                    )
                )
            if completed == [False, True]:
                raise _fail("p08-transition-incomplete")
            for item, target, exists in zip(linked, targets, completed, strict=True):
                if exists:
                    continue
                _git(
                    repository,
                    ["worktree", "add", str(target), str(item["branch_ref"]).removeprefix("refs/heads/")],
                    code="p08-transition-incomplete",
                )
                if item["role"] == "dirty-unmerged":
                    marker = target / ".arbiter-academy-p08-dirty"
                    marker.write_bytes(b"Arbiter Academy P08 preserved dirty fixture.\n")
            for item, target in zip(linked, targets, strict=True):
                if not _p08_existing_linked_worktree_is_exact(repository, target, item):
                    raise _fail("p08-transition-incomplete")
            record = _write_p08(locked, record, "active", object_format=object_format)
    from academy_engine.scenario import PreparedLab
    return PreparedLab(_P08_LAB, attempt, branch, base, prepared)


def prepare_p02(
    repository: Path, store: ExternalStateStore, lab: Lab
) -> "PreparedLab":
    if lab.id != _LAB:
        raise _fail("invalid-exercise-state")
    repository = Path(repository).resolve()
    try:
        validate_repository_git_config(repository)
    except GitCommandError as error:
        raise _fail("invalid-exercise-state", error)
    object_format = _object_format(repository)
    base = _git(repository, ["rev-parse", "main"]).strip()
    authority = _verified_epoch(repository, base)
    with _locked_store(store) as locked:
        record = _latest(locked, object_format)
        if record is None or record["phase"] == "restored":
            _canonical_profile_target(repository, base)
            if _git(repository, ["symbolic-ref", "--quiet", "--short", "HEAD"]).strip() != "main" or _git(repository, ["status", "--porcelain", "--untracked-files=all"]):
                raise _fail("transition-incomplete")
            attempt = 1 if record is None else int(record["attempt"]) + 1
            if attempt > 32:
                raise _fail("invalid-exercise-state")
            record = _new_record(attempt, base, _capture_topology(repository))
            try:
                locked.write_record("p02", attempt, record, expected_generation=0)
            except ExternalStateError as error:
                raise _fail("transition-incomplete", error)
        if record["base_head"] != base and record["phase"] != "restored":
            raise _fail("transition-incomplete")
        if record["phase"] in {"captured", "origin-ready", "bares-ready"}:
            current = _git(
                repository, ["symbolic-ref", "--quiet", "--short", "HEAD"]
            ).strip()
            allowed_branches = (
                {"main", str(record["attempt_branch"])}
                if record["phase"] == "bares-ready"
                else {"main"}
            )
            if current not in allowed_branches or _git(
                repository, ["status", "--porcelain", "--untracked-files=all"]
            ):
                raise _fail("transition-incomplete")
            _verify_original_topology(repository, record["original_topology"])
        attempt = int(record["attempt"])
        origin_id = _p02_repository_id(locked.repository_id, attempt, "learner")
        upstream_id = _p02_repository_id(locked.repository_id, attempt, "official")
        if record["phase"] == "captured":
            origin, snapshot = _prepare_bare(locked, repository, attempt, "learner", base, object_format)
            record = _write(locked, record, "origin-ready", origin_repository=snapshot)
        else:
            origin, _ = locked.owned_repository_directory("p02", attempt, origin_id)
        if record["phase"] == "origin-ready":
            _require_recorded_snapshot(
                origin,
                record["origin_repository"],
                origin_id,
                "learner",
                base,
                object_format,
            )
            upstream, snapshot = _prepare_bare(locked, repository, attempt, "official", base, object_format)
            record = _write(locked, record, "bares-ready", upstream_repository=snapshot)
        else:
            upstream, _ = locked.owned_repository_directory("p02", attempt, upstream_id)
        if record["phase"] in {
            "bares-ready",
            "attempt-ready",
            "worktree-ready",
            "activating-origin-url",
            "activating-origin-pushurl",
            "activating-upstream-url",
            "activating-upstream-pushurl",
        }:
            _require_recorded_snapshot(
                origin,
                record["origin_repository"],
                origin_id,
                "learner",
                base,
                object_format,
            )
            _require_recorded_snapshot(
                upstream,
                record["upstream_repository"],
                upstream_id,
                "official",
                base,
                object_format,
            )
        if record["phase"] == "bares-ready":
            prepared = _create_prepared_commit(repository, record, authority)
            record = _write(locked, record, "attempt-ready", prepared_commit=prepared)
        if record["phase"] == "attempt-ready":
            current_branch = _git(
                repository, ["symbolic-ref", "--quiet", "--short", "HEAD"]
            ).strip()
            if (
                current_branch != record["attempt_branch"]
                or _git(repository, ["rev-parse", "HEAD"]).strip()
                != record["prepared_commit"]
            ):
                raise _fail("transition-incomplete")
            _apply_patch(repository, authority)
            record = _write(locked, record, "worktree-ready")
        if record["phase"] in {
            "worktree-ready",
            "activating-origin-url",
            "activating-origin-pushurl",
            "activating-upstream-url",
            "activating-upstream-pushurl",
        }:
            current_branch = _git(
                repository, ["symbolic-ref", "--quiet", "--short", "HEAD"]
            ).strip()
            current_head = _git(repository, ["rev-parse", "HEAD"]).strip()
            if (
                current_branch != record["attempt_branch"]
                or current_head != record["prepared_commit"]
            ):
                raise _fail("transition-incomplete")
            _verify_prepared_commit(repository, record, authority, current_head)
            _verify_exact_worktree_patch(repository, authority, current_head)
        local = _local_values(origin, upstream)
        topology = record["original_topology"]
        original = topology["config"]
        activation_keys = (
            "remote.origin.url",
            "remote.origin.pushurl",
            "remote.upstream.url",
            "remote.upstream.pushurl",
        )
        sequence = (
            ("worktree-ready", "activating-origin-url", "remote.origin.url"),
            ("activating-origin-url", "activating-origin-pushurl", "remote.origin.pushurl"),
            ("activating-origin-pushurl", "activating-upstream-url", "remote.upstream.url"),
            ("activating-upstream-url", "activating-upstream-pushurl", "remote.upstream.pushurl"),
        )
        for index, (before, intent, key) in enumerate(sequence):
            if record["phase"] == before:
                _verify_activation_boundary(
                    repository,
                    original,
                    local,
                    activation_keys,
                    index,
                    current_may_be_complete=False,
                )
                _verify_exact_topology(repository, topology, local)
                record = _write(locked, record, intent)
            if record["phase"] == intent:
                _verify_activation_boundary(
                    repository,
                    original,
                    local,
                    activation_keys,
                    index,
                    current_may_be_complete=True,
                )
                current = _config_values(repository, key)
                if current in (original[key], local[key]):
                    _verify_exact_topology(repository, topology, local)
                else:
                    _verify_unowned_config(repository, original)
                if current != local[key]:
                    _set_values(repository, key, local[key])
                _verify_activation_boundary(
                    repository,
                    original,
                    local,
                    activation_keys,
                    index + 1,
                    current_may_be_complete=False,
                )
                _verify_exact_topology(repository, topology, local)
                record = _write(
                    locked,
                    record,
                    sequence[index + 1][0] if index + 1 < len(sequence) else "active",
                )
        if record["phase"] != "active":
            raise _fail("transition-incomplete")
        _verify_values(repository, local, tuple(local))
        _verify_exact_topology(repository, topology, local)
        _verify_active_sidecars(locked, record, object_format)
        from academy_engine.scenario import PreparedLab
        return PreparedLab(
            _LAB,
            attempt,
            str(record["attempt_branch"]),
            base,
            str(record["prepared_commit"]),
            str(record["origin_repository"]["repository_id"]),
            str(record["upstream_repository"]["repository_id"]),
        )


def has_active_p02(repository: Path, store: ExternalStateStore) -> bool:
    object_format = _object_format(repository)
    with _locked_store(store) as locked:
        record = _latest(locked, object_format)
        return record is not None and record["phase"] != "restored"


def _record_bare(locked: LockedExternalState, record: dict[str, Any], which: str) -> Path:
    repo = record[f"{which}_repository"]
    role = "learner" if which == "origin" else "official"
    if repo["repository_id"] != _p02_repository_id(
        locked.repository_id, int(record["attempt"]), role
    ):
        raise _fail("invalid-exercise-state")
    directory, _ = locked.owned_repository_directory(
        "p02", int(record["attempt"]), str(repo["repository_id"])
    )
    if repo["relative_directory"] != f"remotes/{directory.name}":
        raise _fail("invalid-exercise-state")
    return directory


def _verify_active_sidecars(
    locked: LockedExternalState,
    record: dict[str, Any],
    object_format: str,
) -> tuple[Path, Path]:
    """Recompute owned sidecars while allowing only the learner attempt ref to evolve."""
    base = str(record["base_head"])
    prepared = str(record["prepared_commit"])
    origin_record = record["origin_repository"]
    upstream_record = record["upstream_repository"]
    origin = _record_bare(locked, record, "origin")
    upstream = _record_bare(locked, record, "upstream")
    _require_recorded_snapshot(
        upstream,
        upstream_record,
        str(upstream_record["repository_id"]),
        "official",
        base,
        object_format,
    )
    if _bare_object_format(origin) != object_format:
        raise _fail("transition-incomplete")
    main_ref = {"ref": "refs/heads/main", "object_id": base}
    attempt_ref = f"refs/heads/{record['attempt_branch']}"
    refs = _bare_refs(origin, object_format=object_format)
    if not refs or len(refs) > 2:
        raise _fail("transition-incomplete")
    attempt_tip: str | None = None
    expected_refs = [main_ref]
    if len(refs) == 2:
        candidates = [item for item in refs if item["ref"] == attempt_ref]
        if len(candidates) != 1:
            raise _fail("transition-incomplete")
        attempt_tip = candidates[0]["object_id"]
        expected_refs.append(candidates[0])
    if refs != sorted(expected_refs, key=lambda item: item["ref"]):
        raise _fail("transition-incomplete")
    _require_complete_object_set(origin, object_format=object_format)
    initial_count, initial_digest = _reachable_from(
        origin,
        ("refs/heads/main",),
        object_format=object_format,
    )
    if (
        origin_record["initial_refs"] != [main_ref]
        or origin_record["object_format"] != object_format
        or initial_count != origin_record["reachable_object_count"]
        or initial_digest != origin_record["reachable_objects_sha256"]
    ):
        raise _fail("transition-incomplete")
    if attempt_tip is not None:
        _bare(origin, ["merge-base", "--is-ancestor", prepared, attempt_tip])
    return origin, upstream


def _validate_transition_target(
    transition_to: str, *, catalog: Catalog | None = None
) -> None:
    if transition_to == "reset":
        return
    if transition_to not in _LATER_LABS:
        raise _fail("invalid-exercise-state")
    if catalog is None:
        return
    try:
        target_index = catalog.labs.index(catalog.lab(transition_to))
        source_index = catalog.labs.index(catalog.lab(_LAB))
    except (CatalogError, ValueError) as error:
        raise _fail("invalid-exercise-state", error)
    if target_index <= source_index:
        raise _fail("invalid-exercise-state")


def _verify_transition_refs(
    repository: Path, record: Mapping[str, Any], *, branches: Sequence[str]
) -> None:
    archive_result = _git_result(
        repository,
        ["rev-parse", "--verify", "--quiet", str(record["archive_ref"])],
    )
    attempt_result = _git_result(
        repository,
        [
            "rev-parse",
            "--verify",
            "--quiet",
            f"refs/heads/{record['attempt_branch']}",
        ],
    )
    main_result = _git_result(
        repository,
        ["rev-parse", "--verify", "--quiet", "refs/heads/main"],
    )
    current = _git(
        repository, ["symbolic-ref", "--quiet", "--short", "HEAD"]
    ).strip()
    head = _git(repository, ["rev-parse", "HEAD"]).strip()
    expected_head = (
        record["base_head"] if current == "main" else record["archive_target"]
    )
    if (
        archive_result.returncode
        or attempt_result.returncode
        or main_result.returncode
        or archive_result.stdout.strip() != record["archive_target"]
        or attempt_result.stdout.strip() != record["archive_target"]
        or main_result.stdout.strip() != record["base_head"]
        or current not in branches
        or head != expected_head
    ):
        raise _fail("transition-incomplete")


def _verify_archiving_boundary(
    repository: Path,
    record: Mapping[str, Any],
) -> None:
    target = str(record["archive_target"])
    archive = str(record["archive_ref"])
    attempt = f"refs/heads/{record['attempt_branch']}"
    current = _git(
        repository,
        ["symbolic-ref", "--quiet", "--short", "HEAD"],
    ).strip()
    head = _git(repository, ["rev-parse", "HEAD"]).strip()
    attempt_tip = _git_result(
        repository,
        ["rev-parse", "--verify", "--quiet", attempt],
    )
    main_tip = _git_result(
        repository,
        ["rev-parse", "--verify", "--quiet", "refs/heads/main"],
    )
    archive_tip = _git_result(
        repository,
        ["rev-parse", "--verify", "--quiet", archive],
    )
    if (
        current != record["attempt_branch"]
        or head != target
        or attempt_tip.returncode
        or attempt_tip.stdout.strip() != target
        or main_tip.returncode
        or main_tip.stdout.strip() != record["base_head"]
        or archive_tip.returncode not in {0, 1}
        or (archive_tip.returncode == 0 and archive_tip.stdout.strip() != target)
    ):
        raise _fail("transition-incomplete")


def verify_p02(repository: Path, store: ExternalStateStore, attempt: P02AttemptIdentity) -> P02LiveState:
    object_format = _object_format(repository)
    with _locked_store(store) as locked:
        record = _latest(locked, object_format)
        if record is None:
            raise _fail("exercise-evidence-mismatch")
        if (
            record["attempt"] != attempt.attempt
            or record["phase"] != "active"
            or record["attempt_branch"] != attempt.branch
            or record["prepared_commit"] != attempt.prepared_commit
        ):
            raise _fail("exercise-evidence-mismatch")
        origin, upstream = _verify_active_sidecars(locked, record, object_format)
        local = _local_values(origin, upstream)
        _verify_values(repository, local, _PATCH_PATHS[:0] + tuple(_URL_KEYS))
        _verify_exact_topology(repository, record["original_topology"], local)
        branch_ref = f"refs/heads/{attempt.branch}"
        origin_tip = _bare(origin, ["rev-parse", "--verify", branch_ref], code="exercise-evidence-mismatch").strip()
        upstream_missing = (
            _bare(
                upstream,
                ["show-ref", "--verify", "--quiet", branch_ref],
                code="exercise-evidence-mismatch",
                missing_ok=True,
            )
            is None
        )
        expected_origin_refs = sorted(
            [
                {"ref": "refs/heads/main", "object_id": str(record["base_head"])},
                {"ref": branch_ref, "object_id": origin_tip},
            ],
            key=lambda item: item["ref"],
        )
        if _bare_refs(origin) != expected_origin_refs:
            raise _fail("exercise-evidence-mismatch")
        try:
            _require_complete_object_set(origin)
        except ExerciseStateError as error:
            raise _fail("exercise-evidence-mismatch", error)
        initial_count, initial_digest = _reachable_from(origin, ("refs/heads/main",))
        if (
            initial_count != record["origin_repository"]["reachable_object_count"]
            or initial_digest != record["origin_repository"]["reachable_objects_sha256"]
            or _git_result(
                repository,
                ["merge-base", "--is-ancestor", str(record["prepared_commit"]), origin_tip],
                code="exercise-evidence-mismatch",
            ).returncode
            or _git(repository, ["rev-parse", "HEAD"]).strip() != attempt.head_commit
        ):
            raise _fail("exercise-evidence-mismatch")
        upstream_snapshot = _repository_snapshot(upstream, str(record["upstream_repository"]["repository_id"]), "official", str(record["base_head"]), object_format)
        return P02LiveState(str(record["origin_repository"]["repository_id"]), str(record["upstream_repository"]["repository_id"]), attempt.branch, str(record["prepared_commit"]), origin_tip, upstream_missing and upstream_snapshot == record["upstream_repository"])


def restore_p02(repository: Path, store: ExternalStateStore, *, transition_to: str, now: Callable[[], datetime] | None = None) -> None:
    object_format = _object_format(repository)
    base = _git(
        repository, ["rev-parse", "main"], code="installed-authority-required"
    ).strip()
    authority = _verified_epoch(repository, base)
    with _locked_store(store) as locked:
        record = _latest(locked, object_format)
        if record is None or record["phase"] == "restored":
            return
        if record["base_head"] != base:
            raise _fail("invalid-exercise-state")
        if record["phase"] == "active":
            _git(
                repository,
                [
                    "rev-parse",
                    "--verify",
                    "--quiet",
                    f"refs/heads/{record['attempt_branch']}",
                ],
            )
        if record["phase"] not in {
            "active",
            "archiving",
            "switching-base",
            "restoring-origin-url",
            "restoring-origin-pushurl",
            "restoring-upstream-url",
            "restoring-upstream-pushurl",
        } or _git(
            repository, ["status", "--porcelain", "--untracked-files=all"]
        ):
            raise _fail("transition-incomplete")
        origin, upstream = _record_bare(locked, record, "origin"), _record_bare(locked, record, "upstream")
        local = _local_values(origin, upstream)
        topology = record["original_topology"]
        original = topology["config"]
        owned_keys = (
            "remote.origin.url",
            "remote.origin.pushurl",
            "remote.upstream.url",
            "remote.upstream.pushurl",
        )
        expected_transition = (
            transition_to if record["phase"] == "active" else record["transition_target"]
        )
        if expected_transition != transition_to:
            raise _fail("transition-incomplete")
        if record["phase"] == "active":
            _validate_transition_target(transition_to, catalog=authority.catalog)
        else:
            _validate_transition_target(transition_to)
        if record["phase"] == "active":
            _verify_active_sidecars(locked, record, object_format)
            _verify_values(repository, local, owned_keys)
            _verify_exact_topology(repository, topology, local)
            target = _git(repository, ["rev-parse", "HEAD"]).strip()
            current = _git(
                repository, ["symbolic-ref", "--quiet", "--short", "HEAD"]
            ).strip()
            attempt_tip = _git(
                repository,
                ["rev-parse", "--verify", f"refs/heads/{record['attempt_branch']}"],
            ).strip()
            main_tip = _git(
                repository,
                ["rev-parse", "--verify", "refs/heads/main"],
            ).strip()
            if (
                current != record["attempt_branch"]
                or attempt_tip != target
                or main_tip != record["base_head"]
            ):
                raise _fail("transition-incomplete")
            instant = (now or (lambda: datetime.now(timezone.utc)))().astimezone(timezone.utc)
            archive = f"refs/heads/academy/archive/{_LAB}/{record['attempt']}/{instant.strftime('%Y%m%dT%H%M%SZ')}"
            collision = _git_result(
                repository, ["rev-parse", "--verify", "--quiet", archive]
            )
            if collision.returncode != 1:
                raise _fail("transition-incomplete")
            record = _write(locked, record, "archiving", archive_ref=archive, archive_target=target, transition_target=transition_to)
        if record["phase"] == "archiving":
            _verify_active_sidecars(locked, record, object_format)
            _verify_values(repository, local, owned_keys)
            _verify_exact_topology(repository, topology, local)
            _verify_archiving_boundary(repository, record)
            existing = _git_result(
                repository,
                ["rev-parse", "--verify", "--quiet", str(record["archive_ref"])],
            )
            if existing.returncode == 1:
                _git(
                    repository,
                    [
                        "update-ref",
                        str(record["archive_ref"]),
                        str(record["archive_target"]),
                        "0" * len(str(record["archive_target"])),
                    ],
                    code="transition-incomplete",
                )
            elif existing.returncode or existing.stdout.strip() != record["archive_target"]:
                raise _fail("transition-incomplete")
            _verify_archiving_boundary(repository, record)
            record = _write(locked, record, "switching-base")
        if record["phase"] == "switching-base":
            _verify_active_sidecars(locked, record, object_format)
            _verify_values(repository, local, owned_keys)
            _verify_transition_refs(
                repository, record, branches=(str(record["attempt_branch"]), "main")
            )
            current = _git(repository, ["symbolic-ref", "--quiet", "--short", "HEAD"]).strip()
            if current == record["attempt_branch"]:
                _git(repository, ["switch", "main"])
            elif current != "main":
                raise _fail("transition-incomplete")
            _verify_transition_refs(repository, record, branches=("main",))
            record = _write(locked, record, "restoring-origin-url")
        if record["phase"].startswith("restoring-"):
            _verify_transition_refs(repository, record, branches=("main",))
        restore = (
            ("restoring-origin-url", "remote.origin.url", "restoring-origin-pushurl"),
            ("restoring-origin-pushurl", "remote.origin.pushurl", "restoring-upstream-url"),
            ("restoring-upstream-url", "remote.upstream.url", "restoring-upstream-pushurl"),
            ("restoring-upstream-pushurl", "remote.upstream.pushurl", "restored"),
        )
        for index, (phase, key, after) in enumerate(restore):
            if record["phase"] == phase:
                _verify_active_sidecars(locked, record, object_format)
                _verify_restoration_boundary(
                    repository,
                    original,
                    local,
                    owned_keys,
                    index,
                    current_may_be_complete=True,
                )
                current = _config_values(repository, key)
                if current in (local[key], original[key]):
                    _verify_exact_topology(repository, topology, local)
                else:
                    _verify_unowned_config(repository, original)
                if current != original[key]:
                    _set_values(repository, key, original[key])
                _verify_restoration_boundary(
                    repository,
                    original,
                    local,
                    owned_keys,
                    index + 1,
                    current_may_be_complete=False,
                )
                _verify_exact_topology(repository, topology, local)
                if after == "restored":
                    try:
                        validate_training_remotes(repository, require_push_safe=True)
                    except (RemoteSafetyError, GitCommandError) as error:
                        raise _fail("remote-topology-mismatch", error)
                record = _write(locked, record, after)


def validate_p02_checkpoint(repository: Path, store: ExternalStateStore, attempt: P02AttemptIdentity, receipt: object) -> bool:
    try:
        object_format = _object_format(repository)
        data = _parse_p02_receipt(receipt, object_format=object_format)
        live = verify_p02(repository, store, attempt)
        if data["attempt"] != attempt.attempt or data["branch"] != attempt.branch or data["prepared_commit"] != attempt.prepared_commit:
            return False
        if data["repositories"]["origin"]["repository_id"] != live.origin_repository_id or data["repositories"]["upstream"]["repository_id"] != live.upstream_repository_id or not live.upstream_unchanged:
            return False
        work = data["work_head"]
        if data["pushed_tip"] != live.origin_tip or work != live.origin_tip:
            return False
        commits = _git(repository, ["rev-list", "--reverse", f"{attempt.prepared_commit}..{work}"], code="exercise-evidence-mismatch").splitlines()
        if commits != data["commits"] or not commits:
            return False
        for commit in commits:
            parents = _git(repository, ["show", "-s", "--format=%P", commit]).split()
            paths = _git(repository, ["diff-tree", "--no-commit-id", "--name-only", "-r", commit]).splitlines()
            if len(parents) != 1 or any(path not in _PATCH_PATHS for path in paths):
                return False
        changed = _git(repository, ["diff", "--name-only", attempt.prepared_commit, work]).splitlines()
        if sorted(changed) != sorted(_PATCH_PATHS) or not _exact_patch_result(
            repository, attempt.prepared_commit, work
        ):
            return False
        receipt_commit = attempt.head_commit
        if _git(repository, ["rev-parse", f"{receipt_commit}^"], code="exercise-evidence-mismatch").strip() != work:
            return False
        receipt_path = ".codearbiter/reports/academy/P02-pr-receipt.json"
        if _git(repository, ["diff-tree", "--no-commit-id", "--name-only", "-r", receipt_commit]).splitlines() != [receipt_path]:
            return False
        _require_canonical_blob(
            repository,
            receipt_commit,
            receipt_path,
            code="exercise-evidence-mismatch",
        )
        committed = _parse_p02_receipt_bytes(
            _git(
                repository,
                ["show", f"{receipt_commit}:{receipt_path}"],
                code="exercise-evidence-mismatch",
            ).encode("utf-8", "surrogateescape"),
            object_format=object_format,
        )
        return committed == data
    except (ExerciseStateError, GitCommandError, OSError, KeyError, TypeError, ValueError):
        return False


def _exact_patch_result(repository: Path, prepared: str, work: str) -> bool:
    try:
        base = _git(
            repository,
            ["rev-parse", f"{prepared}^"],
            code="exercise-evidence-mismatch",
        ).strip()
        authority = _verified_epoch(repository, base)
        patch_bytes = authority.read(
            f"academy/scenarios/{_LAB}/files/P02-worktree.patch"
        )
        for path in _PATCH_PATHS:
            _require_canonical_blob(
                repository, prepared, path, code="exercise-evidence-mismatch"
            )
            _require_canonical_blob(
                repository, work, path, code="exercise-evidence-mismatch"
            )
        with TemporaryDirectory(prefix="arbiter-academy-p02-check-") as temporary:
            root = Path(temporary)
            patch_path = root / "P02-worktree.patch"
            patch_path.write_bytes(patch_bytes)
            for path in _PATCH_PATHS:
                destination = root / path
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(
                    _git(repository, ["show", f"{prepared}:{path}"], code="exercise-evidence-mismatch").encode(
                        "utf-8", "surrogateescape"
                    )
                )
            applied = run_git_unbound(
                root,
                ["apply", "--no-index", *_WORK_PATCH_INCLUDES, str(patch_path)],
                check=False,
            )
            if applied.returncode:
                return False
            for path in _PATCH_PATHS:
                expected = (root / path).read_bytes()
                observed = _git(
                    repository, ["show", f"{work}:{path}"], code="exercise-evidence-mismatch"
                ).encode("utf-8", "surrogateescape")
                if observed != expected:
                    return False
        return True
    except (ExerciseStateError, GitCommandError, OSError):
        return False
