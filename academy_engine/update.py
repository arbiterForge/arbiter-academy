"""Non-destructive fast-forward updates from the official Academy upstream."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from academy_engine.command import GitCommandError, repository_root, run_git
from academy_engine.remotes import RemoteSafetyError, validate_training_remotes
from academy_engine.scenario import BASE_BRANCH


class UpdateError(RuntimeError):
    """An Academy update would be unsafe or non-fast-forward."""


@dataclass(frozen=True)
class UpdateReport:
    before_sha: str
    after_sha: str
    advanced: bool

    def render(self) -> str:
        if self.advanced:
            return f"Academy updated: {self.before_sha} -> {self.after_sha}"
        return f"Academy already current: {self.after_sha}"


def update_academy(root: Path) -> UpdateReport:
    """Fetch only upstream and fast-forward the clean main branch when safe."""
    try:
        repository = repository_root(root)
        if run_git(repository, ["status", "--porcelain", "--untracked-files=all"]).stdout:
            raise UpdateError("update requires a clean worktree, including untracked files.")
        branch = run_git(repository, ["symbolic-ref", "--quiet", "--short", "HEAD"], check=False)
        if branch.returncode or branch.stdout.strip() != BASE_BRANCH:
            raise UpdateError(f"update requires Academy base branch {BASE_BRANCH}.")
        validate_training_remotes(repository, require_push_safe=True)
        before = run_git(repository, ["rev-parse", "HEAD"]).stdout.strip()
        run_git(repository, ["fetch", "--no-tags", "upstream"])
        target = run_git(repository, ["rev-parse", f"upstream/{BASE_BRANCH}"]).stdout.strip()
        if before == target:
            return UpdateReport(before, before, False)
        if run_git(repository, ["merge-base", "--is-ancestor", before, target], check=False).returncode:
            raise UpdateError("upstream is not a fast-forward of the Academy base branch.")
        run_git(repository, ["merge", "--ff-only", f"upstream/{BASE_BRANCH}"])
        after = run_git(repository, ["rev-parse", "HEAD"]).stdout.strip()
        return UpdateReport(before, after, True)
    except (GitCommandError, RemoteSafetyError) as error:
        raise UpdateError(str(error)) from error
