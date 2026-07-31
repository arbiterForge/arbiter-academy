"""Deterministic, recoverable local scenario preparation."""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Sequence

from academy_engine.catalog import Catalog, CatalogError, Lab, ScenarioManifest, load_manifest_file
from academy_engine.command import GitCommandError, repository_root, run_git as _run_git
from academy_engine.paths import PathBoundaryError, ensure_within
from academy_engine.remotes import RemoteSafetyError, validate_training_remotes


BASE_BRANCH = "main"


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


@dataclass(frozen=True)
class _Snapshot:
    target: Path
    backup: Path | None
    is_directory: bool


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
    if manifest.requires_push_safe_setup:
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
    return lab, manifest, manifest_path


def _validate_overlay(root: Path, manifest: ScenarioManifest, manifest_path: Path) -> tuple[tuple[Path, Path], ...]:
    try:
        files_root = ensure_within(root, manifest_path.parent.relative_to(root) / "files")
    except (PathBoundaryError, ValueError) as error:
        raise _fail(error) from error
    operations: list[tuple[Path, Path]] = []
    for overlay in manifest.files:
        try:
            source = ensure_within(root, files_root.relative_to(root) / overlay.source)
            destination = ensure_within(root, Path(overlay.destination))
        except PathBoundaryError as error:
            raise _fail(error) from error
        if not source.is_file():
            raise PreparationError(f"scenario overlay source is missing or unsafe: {overlay.source}.")
        operations.append((source, destination))
    for removal in manifest.removals:
        try:
            target = ensure_within(root, Path(removal))
        except PathBoundaryError as error:
            raise _fail(error) from error
        if target.is_symlink():
            raise PreparationError(f"scenario removal target must not be a symlink: {removal}.")
    return tuple(operations)


def _snapshots(root: Path, manifest: ScenarioManifest, operations: tuple[tuple[Path, Path], ...], backup_root: Path) -> tuple[_Snapshot, ...]:
    targets: list[Path] = [ensure_within(root, Path(removal)) for removal in manifest.removals]
    targets.extend(ensure_within(root, destination.relative_to(root)) for _, destination in operations)
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


def _prepare_inputs(root: Path, lab_id: str) -> tuple[Path, Lab, ScenarioManifest, tuple[tuple[Path, Path], ...], int, str]:
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


def prepare_lab(root: Path, lab_id: str) -> PreparedLab:
    """Prepare one catalog-sourced attempt from the clean immutable base branch."""
    repository, lab, manifest, operations, attempt, base_sha = _prepare_inputs(root, lab_id)
    branch = f"academy/{lab.id}/{attempt}"
    original_branch = _branch(repository)
    with tempfile.TemporaryDirectory(prefix="academy-scenario-") as temporary:
        snapshots = _snapshots(repository, manifest, operations, Path(temporary))
        branch_created = False
        try:
            run_git(repository, ["switch", "-c", branch, base_sha])
            branch_created = True
            targets: list[str] = []
            for removal in manifest.removals:
                target = ensure_within(repository, Path(removal))
                _remove_target(target)
                targets.append(removal)
            for source, destination in operations:
                ensure_within(repository, destination.relative_to(repository))
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, destination)
                targets.append(destination.relative_to(repository).as_posix())
            if targets:
                run_git(repository, ["add", "-A", "--", *targets])
            run_git(repository, ["commit", "--allow-empty", "-m", f"academy: prepare {lab.id} attempt {attempt}"])
            commit_sha = run_git(repository, ["rev-parse", "HEAD"]).stdout.strip()
        except (GitCommandError, OSError, PathBoundaryError) as error:
            try:
                run_git(repository, ["reset"])
                _restore_snapshots(repository, snapshots)
                if _branch(repository) != original_branch:
                    run_git(repository, ["switch", original_branch])
                if branch_created:
                    run_git(repository, ["update-ref", "-d", f"refs/heads/{branch}", base_sha])
            except (GitCommandError, OSError, PathBoundaryError) as rollback_error:
                raise PreparationError(f"{error} (rollback failed: {rollback_error})") from rollback_error
            raise _fail(error) from error
    return PreparedLab(lab.id, attempt, branch, base_sha, commit_sha)


def reset_lab(root: Path, lab_id: str, *, now: Callable[[], datetime] | None = None) -> PreparedLab:
    """Archive the current clean attempt and prepare an independent retry."""
    try:
        repository = repository_root(root)
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
        return prepare_lab(repository, lab_id)
    except PreparationError as error:
        try:
            if _branch(repository) != current:
                run_git(repository, ["switch", current])
            run_git(repository, ["update-ref", "-d", f"refs/heads/{archive}", current_head])
        except GitCommandError as rollback_error:
            raise PreparationError(f"{error} (reset rollback failed: {rollback_error})") from rollback_error
        raise
