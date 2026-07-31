"""Read-only learner setup diagnostics for Arbiter Academy."""

from __future__ import annotations

import platform
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from academy_engine.command import GitCommandError, git_version, repository_root, run_git
from academy_engine.paths import ensure_within
from academy_engine.remotes import RemoteReport, validate_training_remotes


@dataclass(frozen=True)
class GitStatus:
    available: bool
    version: str | None


@dataclass(frozen=True)
class WorktreeStatus:
    root: Path | None
    clean: bool | None
    branch: str | None
    detached: bool | None


@dataclass(frozen=True)
class DoctorReport:
    python_version: str
    git: GitStatus
    worktree: WorktreeStatus
    remotes: RemoteReport
    codearbiter_active: bool
    codearbiter_initialized: bool
    host_guidance: str
    issues: tuple[str, ...]
    safe_for_push_labs: bool

    def render(self) -> str:
        root = str(self.worktree.root) if self.worktree.root else "unavailable"
        origin = _remote_label(self.remotes.origin)
        upstream = _remote_label(self.remotes.upstream)
        branch = self.worktree.branch or ("detached" if self.worktree.detached else "unavailable")
        cleanliness = _yes_no(self.worktree.clean)
        origin_classification = (
            "fork-compatible"
            if self.remotes.origin_fork_compatible
            else "not fork-compatible"
        )
        lines = [
            "Arbiter Academy doctor",
            f"Python: {self.python_version}",
            f"Git: {self.git.version or 'unavailable'}",
            f"Repository root: {root}",
            f"Worktree clean: {cleanliness}",
            f"Branch: {branch}",
            f"Origin: {origin}",
            f"Upstream: {upstream}",
            f"Effective push remote: {self.remotes.effective_push_remote or 'unavailable'}",
            f"Official upstream push disabled: {_yes_no(self.remotes.upstream_push_disabled)}",
            f"Origin identity is {origin_classification}; "
            "GitHub lineage is not verified offline.",
            f"codeArbiter active: {_yes_no(self.codearbiter_active)}",
            f"codeArbiter initialized: {_yes_no(self.codearbiter_initialized)}",
            f"Host guidance: {self.host_guidance}",
        ]
        if self.issues:
            lines.extend(["UNSAFE for learner push labs:", *(f"- {issue}" for issue in self.issues)])
        else:
            lines.append("SAFE for learner push labs.")
        return "\n".join(lines)


def _yes_no(value: bool | None) -> str:
    return "yes" if value else "no" if value is False else "unavailable"


def _remote_label(remote: object) -> str:
    if remote is None:
        return "unavailable"
    return f"{remote.owner}/{remote.repository}"  # type: ignore[attr-defined]


def inspect_doctor(root: Path | None = None) -> DoctorReport:
    """Collect a complete, non-mutating local readiness report."""
    requested_root = Path.cwd() if root is None else Path(root)
    guidance = (
        "Run `python scripts/academy.py doctor` from the repository root. "
        "Make the official upstream read-only with "
        "`git remote set-url --push upstream DISABLED`."
    )
    try:
        version = git_version(requested_root)
    except GitCommandError as error:
        issue = f"Git executable check failed: {error}"
        unavailable_remotes = RemoteReport(None, None, (issue,), False)
        return DoctorReport(
            platform.python_version(),
            GitStatus(False, None),
            WorktreeStatus(None, None, None, None),
            unavailable_remotes,
            False,
            False,
            guidance,
            (issue,),
            False,
        )
    try:
        repository = repository_root(requested_root)
        status = run_git(
            repository,
            ["status", "--porcelain", "--untracked-files=all"],
        ).stdout
        branch_result = run_git(repository, ["symbolic-ref", "--quiet", "--short", "HEAD"], check=False)
    except GitCommandError as error:
        issue = f"Git repository check failed: {error}"
        unavailable_remotes = RemoteReport(None, None, (issue,), False)
        return DoctorReport(
            platform.python_version(),
            GitStatus(True, version),
            WorktreeStatus(None, None, None, None),
            unavailable_remotes,
            False,
            False,
            guidance,
            (issue,),
            False,
        )
    detached = branch_result.returncode != 0
    branch = None if detached else branch_result.stdout.strip()
    remotes = validate_training_remotes(repository, require_push_safe=False)
    codearbiter = repository / ".codearbiter"
    active = codearbiter.is_dir()
    initialized = active and (codearbiter / "CONTEXT.md").is_file()
    issues = list(remotes.issues)
    if status:
        issues.append("worktree has uncommitted changes.")
    if detached:
        issues.append("HEAD is detached; check out a learner branch before a push lab.")
    if not active:
        issues.append("codeArbiter is not activated in this repository.")
    elif not initialized:
        issues.append("codeArbiter is not initialized in this repository.")
    return DoctorReport(
        platform.python_version(),
        GitStatus(True, version),
        WorktreeStatus(repository, not bool(status), branch, detached),
        remotes,
        active,
        initialized,
        guidance,
        tuple(issues),
        not issues,
    )


def record_foundations_doctor(root: Path, report: DoctorReport) -> Path:
    """Write the bounded F01 observation after a fully safe live inspection."""
    if not report.safe_for_push_labs or report.remotes.effective_push_remote != "origin":
        raise ValueError("F01 doctor evidence is recorded only after all safety checks pass.")
    repository = repository_root(root)
    destination = ensure_within(
        repository, Path(".codearbiter/reports/academy/F01-doctor.json")
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination = ensure_within(
        repository, Path(".codearbiter/reports/academy/F01-doctor.json")
    )
    payload = {
        "schema_version": 1,
        "safe_for_push_labs": True,
        "effective_push_remote": "origin",
    }
    descriptor, temporary_name = tempfile.mkstemp(
        dir=destination.parent, prefix="F01-doctor.", suffix=".tmp"
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, destination)
    except Exception:
        try:
            os.unlink(temporary_name)
        except OSError:
            pass
        raise
    return destination
