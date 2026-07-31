"""Read-only learner setup diagnostics for Arbiter Academy."""

from __future__ import annotations

import platform
from dataclasses import dataclass
from pathlib import Path

from academy_engine.command import GitCommandError, git_version, repository_root, run_git
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
        lines = [
            "Arbiter Academy doctor",
            f"Python: {self.python_version}",
            f"Git: {self.git.version or 'unavailable'}",
            f"Repository root: {root}",
            f"Worktree clean: {cleanliness}",
            f"Branch: {branch}",
            f"Origin: {origin}",
            f"Upstream: {upstream}",
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
    guidance = "Run `python scripts/academy.py doctor` from the repository root."
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
        status = run_git(repository, ["status", "--porcelain"]).stdout
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
