"""Deterministic, recoverable local scenario preparation."""

from __future__ import annotations

import hashlib
import shutil
import tempfile
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Sequence

from academy_engine.catalog import (
    Catalog,
    CatalogError,
    Lab,
    ScenarioManifest,
    _CONTROL_STATE_SEED_TARGETS,
    load_manifest_file,
)
from academy_engine.attribution import (
    AttributionError,
    commit_author_name,
    prospective_author_name,
)
from academy_engine.command import GitCommandError, repository_root, run_git as _run_git
from academy_engine.exercise_state import (
    ExerciseStateError,
    has_active_p02,
    open_existing_p02_store,
    open_p02_store,
    open_p08_store,
    preflight_p08,
    preflight_p02,
    prepare_p08,
    prepare_p02,
    reset_p08,
    restore_p02,
)
from academy_engine.external_state import ExternalStateError, ExternalStateStore
from academy_engine.paths import PathBoundaryError, ensure_within
from academy_engine.p05_fixture import P05FixtureError, stage_p05_fixture
from academy_engine.remotes import RemoteSafetyError, validate_training_remotes


BASE_BRANCH = "main"
_TRUSTED_PROTECTED_OVERLAY_SHA256 = {
    (
        "P06-context-drift-recovery",
        "CONTEXT.md",
        ".codearbiter/CONTEXT.md",
    ): "3c496fe68bfc6042663c9b1d697c6b7f314e1f814533acbb30fd5169c39752f4",
    (
        "P06-context-drift-recovery",
        "CONTEXT.provenance.json",
        ".codearbiter/.provenance/CONTEXT.json",
    ): "4831a0db68f47f7f63fd6d0925942184488ce65231fb3acb747b753aae38a915",
}
_P02_STATE_REACHABLE_LABS = frozenset(
    {
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
    }
)
_P02_AUTHORITY_REQUIRED = (
    "P02 exercise records require installed Academy authority."
)
_P05_FIXTURE_TARGETS = (
    ".codearbiter/decisions/0005-terminal-blocked-ticket-lifecycle.md",
    ".codearbiter/decisions/decision-log.md",
    "tests/test_cli.py",
    "workshop_queue/cli.py",
    "workshop_queue/model.py",
    "workshop_queue/service.py",
)


def p02_state_reachable(lab_id: str | None) -> bool:
    """Return whether scenario dispatch can inspect or mutate verifier-owned P02 state."""
    return lab_id in _P02_STATE_REACHABLE_LABS


def run_git(
    root: Path, args: Sequence[str], *, check: bool = True
):
    return _run_git(root, args, check=check, trust_local_config=True)


class PreparationError(RuntimeError):
    """The learner repository is not safe for a scenario state transition."""


@dataclass(frozen=True)
class PreparedLab:
    lab_id: str
    attempt: int
    branch: str
    base_sha: str
    commit_sha: str
    origin_repository_id: str | None = None
    upstream_repository_id: str | None = None

    def __post_init__(self) -> None:
        identities = (self.origin_repository_id, self.upstream_repository_id)
        if (identities[0] is None) != (identities[1] is None) or any(
            value is not None and re.fullmatch(r"[0-9a-f]{64}", value) is None
            for value in identities
        ):
            raise ValueError("prepared lab repository identity is invalid.")


@dataclass(frozen=True)
class _Snapshot:
    target: Path
    backup: Path | None
    is_directory: bool


@dataclass(frozen=True)
class _OverlayOperation:
    source: Path
    destination: Path
    payload: bytes


def _fail(error: Exception) -> PreparationError:
    return PreparationError(str(error))


def _clean(root: Path) -> None:
    status = run_git(root, ["status", "--porcelain", "--untracked-files=all"]).stdout
    if status:
        raise PreparationError("worktree must be clean, including untracked files.")


def _branch(root: Path) -> str:
    result = run_git(root, ["symbolic-ref", "--quiet", "--short", "HEAD"], check=False)
    if result.returncode:
        raise PreparationError("HEAD is detached; check out the Academy base branch first.")
    return result.stdout.strip()


def _ref_exists(root: Path, name: str) -> bool:
    return run_git(root, ["show-ref", "--verify", "--quiet", f"refs/heads/{name}"], check=False).returncode == 0


def _validate_ref(root: Path, name: str) -> None:
    if run_git(root, ["check-ref-format", f"refs/heads/{name}"], check=False).returncode:
        raise PreparationError("Academy branch namespace is unsafe.")


def _attempt(root: Path, lab_id: str) -> int:
    prefix = f"academy/{lab_id}/"
    names = run_git(root, ["for-each-ref", "--format=%(refname:short)", f"refs/heads/{prefix}"]).stdout.splitlines()
    numbers: list[int] = []
    for name in names:
        suffix = name.removeprefix(prefix)
        if not suffix.isdecimal() or str(int(suffix)) != suffix or int(suffix) < 1:
            raise PreparationError("Academy attempt namespace contains an unsafe ref.")
        numbers.append(int(suffix))
    return (max(numbers) if numbers else 0) + 1


def _ensure_mutation_remote_safety(root: Path, manifest: ScenarioManifest) -> None:
    """Every mutation needs a learner fork; push labs additionally need the full contract."""
    try:
        report = validate_training_remotes(
            root, require_push_safe=False, trust_local_config=True
        )
    except RemoteSafetyError as error:
        raise _fail(error) from error
    origin = report.origin
    origin_targets_safe = bool(
        origin is not None
        and report.origin_push_targets
        and all(target.matches(origin.owner, origin.repository) for target in report.origin_push_targets)
    )
    if not report.origin_fork_compatible or report.effective_push_remote != "origin" or not origin_targets_safe:
        raise PreparationError("scenario mutation requires a fork-safe origin and origin push routing.")
    # F01 exists to finish and verify the upstream half of a real fork-shaped
    # checkout.  Its origin and effective push route must already be safe before
    # any mutation, but demanding a complete upstream contract here would make
    # the exercise vacuous.  The F01 checkpoint still requires the full contract.
    if manifest.requires_push_safe_setup and manifest.id != "F01-fork-clone-doctor":
        try:
            validate_training_remotes(
                root, require_push_safe=True, trust_local_config=True
            )
        except RemoteSafetyError as error:
            raise _fail(error) from error


def _catalog_and_manifest(root: Path, lab_id: str) -> tuple[Lab, ScenarioManifest, Path]:
    try:
        catalog = Catalog.load(root / "academy" / "catalog.json")
        lab = catalog.lab(lab_id)
        manifest_path = ensure_within(root, Path(lab.manifest))
        if manifest_path.is_symlink():
            raise PreparationError("scenario manifest path must not be a symlink.")
        manifest = load_manifest_file(manifest_path)
    except (CatalogError, PathBoundaryError) as error:
        raise _fail(error) from error
    if manifest.id != lab.id:
        raise PreparationError("catalog and scenario manifest lab IDs disagree.")
    if manifest.checkpoint != lab.checkpoint:
        raise PreparationError("catalog and scenario manifest checkpoints disagree.")
    if manifest.requires_push_safe_setup != lab.requires_push_safe_setup:
        raise PreparationError("catalog and scenario manifest remote requirements disagree.")
    if manifest.control_state_seed is not None and manifest.control_state_seed.destination not in _CONTROL_STATE_SEED_TARGETS.get(lab.id, frozenset()):
        raise PreparationError("scenario control-state seed is not allowed for this lab.")
    return lab, manifest, manifest_path


def _p02_catalog_and_manifest(
    root: Path, lab_id: str
) -> tuple[Lab, ScenarioManifest, Path]:
    try:
        return _catalog_and_manifest(root, lab_id)
    except (CatalogError, OSError, PathBoundaryError, PreparationError) as error:
        raise ExerciseStateError("invalid-exercise-state") from error


def _p02_git(repository: Path, args: Sequence[str]):
    try:
        result = _run_git(repository, args, check=False)
    except (GitCommandError, OSError) as error:
        raise ExerciseStateError("invalid-exercise-state") from error
    if result.returncode:
        raise ExerciseStateError("invalid-exercise-state")
    return result


def _validate_overlay(
    root: Path,
    manifest: ScenarioManifest,
    manifest_path: Path,
) -> tuple[_OverlayOperation, ...]:
    try:
        files_root = ensure_within(root, manifest_path.parent.relative_to(root) / "files")
    except (PathBoundaryError, ValueError) as error:
        raise _fail(error) from error
    operations: list[_OverlayOperation] = []
    for overlay in manifest.files:
        try:
            source = ensure_within(root, files_root.relative_to(root) / overlay.source)
            destination = ensure_within(root, Path(overlay.destination))
        except PathBoundaryError as error:
            raise _fail(error) from error
        if not source.is_file():
            raise PreparationError(f"scenario overlay source is missing or unsafe: {overlay.source}.")
        try:
            payload = source.read_bytes()
        except OSError as error:
            raise PreparationError(
                f"scenario overlay source could not be read: {overlay.source}."
            ) from error
        binding = (manifest.id, overlay.source, overlay.destination)
        trusted_digest = _TRUSTED_PROTECTED_OVERLAY_SHA256.get(binding)
        if trusted_digest is not None:
            observed_digest = hashlib.sha256(payload).hexdigest()
            if observed_digest != trusted_digest:
                raise PreparationError(
                    f"scenario trusted protected overlay bytes do not match the reviewed fixture: {overlay.source}."
                )
        operations.append(_OverlayOperation(source, destination, payload))
    if manifest.control_state_seed is not None:
        seed = manifest.control_state_seed
        try:
            source = ensure_within(root, files_root.relative_to(root) / seed.source)
            destination = ensure_within(root, Path(seed.destination))
        except PathBoundaryError as error:
            raise _fail(error) from error
        if not source.is_file():
            raise PreparationError(
                f"scenario control-state seed source is missing or unsafe: {seed.source}."
            )
        try:
            payload = source.read_bytes()
        except OSError as error:
            raise PreparationError(
                f"scenario control-state seed source could not be read: {seed.source}."
            ) from error
        operations.append(_OverlayOperation(source, destination, payload))
    for removal in manifest.removals:
        try:
            target = ensure_within(root, Path(removal))
        except PathBoundaryError as error:
            raise _fail(error) from error
        if target.is_symlink():
            raise PreparationError(f"scenario removal target must not be a symlink: {removal}.")
    return tuple(operations)


def _snapshots(
    root: Path,
    manifest: ScenarioManifest,
    operations: tuple[_OverlayOperation, ...],
    backup_root: Path,
    *,
    extra_targets: tuple[str, ...] = (),
) -> tuple[_Snapshot, ...]:
    targets: list[Path] = [ensure_within(root, Path(removal)) for removal in manifest.removals]
    targets.extend(
        ensure_within(root, operation.destination.relative_to(root))
        for operation in operations
    )
    targets.extend(ensure_within(root, Path(target)) for target in extra_targets)
    snapshots: list[_Snapshot] = []
    for index, target in enumerate(targets):
        backup = backup_root / str(index)
        if target.exists():
            if target.is_dir():
                shutil.copytree(target, backup)
                snapshots.append(_Snapshot(target, backup, True))
            else:
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, backup)
                snapshots.append(_Snapshot(target, backup, False))
        else:
            snapshots.append(_Snapshot(target, None, False))
    return tuple(snapshots)


def _remove_target(target: Path) -> None:
    if target.exists():
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()


def _restore_snapshots(root: Path, snapshots: tuple[_Snapshot, ...]) -> None:
    for snapshot in snapshots:
        ensure_within(root, snapshot.target.relative_to(root))
        _remove_target(snapshot.target)
        if snapshot.backup is None:
            continue
        snapshot.target.parent.mkdir(parents=True, exist_ok=True)
        if snapshot.is_directory:
            shutil.copytree(snapshot.backup, snapshot.target)
        else:
            shutil.copy2(snapshot.backup, snapshot.target)


def _prepare_inputs(
    root: Path,
    lab_id: str,
) -> tuple[Path, Lab, ScenarioManifest, tuple[_OverlayOperation, ...], int, str]:
    try:
        repository = repository_root(root)
        _clean(repository)
        current = _branch(repository)
    except GitCommandError as error:
        raise _fail(error) from error
    if current != BASE_BRANCH:
        raise PreparationError(f"prepare must start on Academy base branch {BASE_BRANCH}.")
    lab, manifest, manifest_path = _catalog_and_manifest(repository, lab_id)
    operations = _validate_overlay(repository, manifest, manifest_path)
    _ensure_mutation_remote_safety(repository, manifest)
    attempt = _attempt(repository, lab.id)
    branch = f"academy/{lab.id}/{attempt}"
    _validate_ref(repository, branch)
    if _ref_exists(repository, branch):
        raise PreparationError("Academy attempt branch already exists.")
    return repository, lab, manifest, operations, attempt, run_git(repository, ["rev-parse", "HEAD"]).stdout.strip()


def _restore_p02_before_later_lab(
    repository: Path,
    lab_id: str,
    *,
    installed_authority: bool,
) -> None:
    if not p02_state_reachable(lab_id) or lab_id == "P02-commit-review-pr":
        return
    try:
        if not ExternalStateStore.has_records(repository, lab="p02"):
            return
        if not installed_authority:
            raise PreparationError(_P02_AUTHORITY_REQUIRED)
        store = open_existing_p02_store(
            repository,
            base=_p02_git(repository, ["rev-parse", "main"]).stdout.strip(),
        )
        if store is None:
            raise ExternalStateError("state-identity-mismatch")
        if has_active_p02(repository, store):
            restore_p02(repository, store, transition_to=lab_id)
    except (ExerciseStateError, ExternalStateError) as error:
        raise PreparationError(str(error)) from error


def prepare_lab(
    root: Path,
    lab_id: str,
    *,
    installed_authority: bool = False,
) -> PreparedLab:
    """Prepare one catalog-sourced attempt from the clean immutable base branch."""
    try:
        repository = repository_root(root)
        if lab_id == "P02-commit-review-pr":
            if not installed_authority:
                raise PreparationError(_P02_AUTHORITY_REQUIRED)
            lab, _, _ = _p02_catalog_and_manifest(repository, lab_id)
            base = _p02_git(
                repository,
                ["rev-parse", "main"],
            ).stdout.strip()
            if ExternalStateStore.has_records(repository, lab="p02"):
                store = open_existing_p02_store(repository, base=base)
                if store is None:
                    raise ExternalStateError("state-identity-mismatch")
            else:
                base = preflight_p02(repository, lab)
                store = open_p02_store(repository, base=base)
            return prepare_p02(repository, store, lab)
        if lab_id == "P08-repository-hygiene":
            if not installed_authority:
                raise PreparationError("P08 requires installed Academy authority.")
            base, lab, authority = preflight_p08(repository)
            _restore_p02_before_later_lab(
                repository,
                lab_id,
                installed_authority=installed_authority,
            )
            store = open_p08_store(repository, base=base, authority=authority)
            return prepare_p08(repository, store, lab)
        _restore_p02_before_later_lab(
            repository,
            lab_id,
            installed_authority=installed_authority,
        )
        prospective_name = (
            prospective_author_name(repository, trust_local_config=True)
            if lab_id == "P03-record-an-adr"
            else None
        )
    except (ExerciseStateError, ExternalStateError, AttributionError) as error:
        raise PreparationError(str(error)) from error
    repository, lab, manifest, operations, attempt, base_sha = _prepare_inputs(root, lab_id)
    branch = f"academy/{lab.id}/{attempt}"
    original_branch = _branch(repository)
    with tempfile.TemporaryDirectory(prefix="academy-scenario-") as temporary:
        fixture_targets = _P05_FIXTURE_TARGETS if lab.id == "P05-checkpoint-remediation" else ()
        snapshots = _snapshots(
            repository,
            manifest,
            operations,
            Path(temporary),
            extra_targets=fixture_targets,
        )
        branch_created = False
        try:
            run_git(repository, ["switch", "-c", branch, base_sha])
            branch_created = True
            targets: list[str] = []
            for removal in manifest.removals:
                target = ensure_within(repository, Path(removal))
                _remove_target(target)
                targets.append(removal)
            for operation in operations:
                ensure_within(repository, operation.destination.relative_to(repository))
                try:
                    current_payload = operation.source.read_bytes()
                except OSError as error:
                    raise PreparationError(
                        "scenario overlay source could not be reread after validation: "
                        f"{operation.source.name}."
                    ) from error
                if current_payload != operation.payload:
                    raise PreparationError(
                        "scenario overlay source changed after validation: "
                        f"{operation.source.name}."
                    )
                operation.destination.parent.mkdir(parents=True, exist_ok=True)
                operation.destination.write_bytes(operation.payload)
                targets.append(operation.destination.relative_to(repository).as_posix())
            if lab.id == "P05-checkpoint-remediation":
                targets.extend(stage_p05_fixture(repository, base=base_sha))
            if targets:
                run_git(repository, ["add", "-A", "--", *targets])
            run_git(repository, ["commit", "--allow-empty", "-m", f"academy: prepare {lab.id} attempt {attempt}"])
            commit_sha = run_git(repository, ["rev-parse", "HEAD"]).stdout.strip()
            if prospective_name is not None and commit_author_name(repository, commit_sha) != prospective_name:
                raise AttributionError("P03 committed attribution is invalid.")
        except (
            GitCommandError,
            OSError,
            PathBoundaryError,
            AttributionError,
            P05FixtureError,
            PreparationError,
        ) as error:
            try:
                run_git(repository, ["reset"])
                _restore_snapshots(repository, snapshots)
                if _branch(repository) != original_branch:
                    run_git(repository, ["switch", original_branch])
                if branch_created:
                    run_git(repository, ["update-ref", "-d", f"refs/heads/{branch}"])
            except (GitCommandError, OSError, PathBoundaryError) as rollback_error:
                raise PreparationError(f"{error} (rollback failed: {rollback_error})") from rollback_error
            raise _fail(error) from error
    return PreparedLab(lab.id, attempt, branch, base_sha, commit_sha)


def _p02_preparation_base(repository: Path) -> str:
    prefix = "refs/heads/academy/P02-commit-review-pr/"
    result = _p02_git(
        repository,
        ["for-each-ref", "--format=%(refname:short)", prefix],
    )
    attempts: dict[int, str] = {}
    for branch in result.stdout.splitlines():
        match = re.fullmatch(r"academy/P02-commit-review-pr/([1-9]|[12][0-9]|3[0-2])", branch)
        if match is None:
            raise ExerciseStateError("invalid-exercise-state")
        attempt = int(match.group(1))
        if attempt in attempts:
            raise ExerciseStateError("invalid-exercise-state")
        attempts[attempt] = branch
    if not attempts:
        raise ExerciseStateError("invalid-exercise-state")
    latest = max(attempts)
    if tuple(sorted(attempts)) != tuple(range(1, latest + 1)):
        raise ExerciseStateError("invalid-exercise-state")
    subject = f"academy: prepare P02-commit-review-pr attempt {latest}"
    history = _p02_git(
        repository,
        ["log", "--format=%H%x00%s", attempts[latest]],
    ).stdout.splitlines()
    matches = [line.split("\0", 1)[0] for line in history if line.endswith("\0" + subject)]
    if len(matches) != 1:
        raise ExerciseStateError("invalid-exercise-state")
    parents = _p02_git(
        repository,
        ["rev-list", "--parents", "-n", "1", matches[0]],
    ).stdout.split()
    if len(parents) != 2:
        raise ExerciseStateError("invalid-exercise-state")
    return parents[1]


def reset_lab(
    root: Path,
    lab_id: str,
    *,
    now: Callable[[], datetime] | None = None,
    installed_authority: bool = False,
) -> PreparedLab:
    """Archive the current clean attempt and prepare an independent retry."""
    if lab_id == "P02-commit-review-pr":
        if not installed_authority:
            raise PreparationError(_P02_AUTHORITY_REQUIRED)
        try:
            repository = repository_root(root)
            lab, _, _ = _p02_catalog_and_manifest(repository, lab_id)
            base = _p02_preparation_base(repository)
            store = open_existing_p02_store(repository, base=base)
            if store is None:
                raise ExternalStateError("state-identity-mismatch")
            restore_p02(
                repository, store, transition_to="reset", now=now
            )
            return prepare_p02(repository, store, lab)
        except (ExerciseStateError, ExternalStateError, GitCommandError, OSError) as error:
            raise PreparationError(str(error)) from error
    if lab_id == "P08-repository-hygiene":
        if not installed_authority:
            raise PreparationError("P08 requires installed Academy authority.")
        try:
            repository = repository_root(root)
            base, lab, authority = preflight_p08(repository)
            _restore_p02_before_later_lab(
                repository,
                lab_id,
                installed_authority=installed_authority,
            )
            store = open_p08_store(repository, base=base, authority=authority)
            return reset_p08(repository, store)
        except (ExerciseStateError, ExternalStateError, GitCommandError, OSError) as error:
            raise PreparationError(str(error)) from error
    try:
        repository = repository_root(root)
        _restore_p02_before_later_lab(
            repository,
            lab_id,
            installed_authority=installed_authority,
        )
        _clean(repository)
        current = _branch(repository)
    except GitCommandError as error:
        raise _fail(error) from error
    expected_prefix = f"academy/{lab_id}/"
    suffix = current.removeprefix(expected_prefix)
    if not current.startswith(expected_prefix) or not suffix.isdecimal() or str(int(suffix)) != suffix or int(suffix) < 1:
        raise PreparationError("reset requires the matching attempt branch for this Academy lab.")
    lab, manifest, manifest_path = _catalog_and_manifest(repository, lab_id)
    _validate_overlay(repository, manifest, manifest_path)
    _ensure_mutation_remote_safety(repository, manifest)
    _attempt(repository, lab.id)
    timestamp = (now or (lambda: datetime.now(timezone.utc)))().astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive = f"academy/archive/{lab_id}/{timestamp}"
    _validate_ref(repository, archive)
    if _ref_exists(repository, archive):
        raise PreparationError("Academy archive branch already exists for this timestamp.")
    current_head = run_git(repository, ["rev-parse", "HEAD"]).stdout.strip()
    archive_created = False
    try:
        run_git(repository, ["branch", archive, current_head])
        archive_created = True
        run_git(repository, ["switch", BASE_BRANCH])
    except GitCommandError as error:
        if archive_created:
            try:
                run_git(repository, ["update-ref", "-d", f"refs/heads/{archive}", current_head])
            except GitCommandError as rollback_error:
                raise PreparationError(f"{error} (archive rollback failed: {rollback_error})") from rollback_error
        raise _fail(error) from error
    try:
        return prepare_lab(
            repository,
            lab_id,
            installed_authority=installed_authority,
        )
    except PreparationError as error:
        try:
            if _branch(repository) != current:
                run_git(repository, ["switch", current])
            run_git(repository, ["update-ref", "-d", f"refs/heads/{archive}", current_head])
        except GitCommandError as rollback_error:
            raise PreparationError(f"{error} (reset rollback failed: {rollback_error})") from rollback_error
        raise
