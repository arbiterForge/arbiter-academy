"""Deterministic private U04 child-project fixture construction."""

from __future__ import annotations

import os
from pathlib import Path

from academy_engine.command import GitCommandError, initialize_empty_training_repository, run_git
from academy_engine.paths import PathBoundaryError, ensure_within


class U04FixtureError(ValueError):
    """The isolated U04 project fixtures cannot be prepared safely."""


U04_CHILD_PATHS = {
    "greenfield": ".academy/workspaces/U04-greenfield",
    "brownfield": ".academy/workspaces/U04-brownfield",
}
U04_SEED_CONTENT = {
    "greenfield": {"README.md": b"# Greenfield fixture\n"},
    "brownfield": {
        "workshop_queue/legacy_queue.py": (
            b"def summarize(items: list[str]) -> str:\n    return \",\".join(items)\n"
        )
    },
}


def _stage_child(repository: Path, relative: str, kind: str) -> None:
    child = ensure_within(repository, Path(relative))
    if os.path.lexists(child):
        raise U04FixtureError("U04 fixture target is already occupied.")
    try:
        child.parent.mkdir(parents=True, exist_ok=True)
        child.mkdir()
        child = ensure_within(repository, Path(relative))
        initialize_empty_training_repository(child)
        run_git(child, ["config", "user.name", "Academy Fixture"], trust_local_config=True)
        run_git(
            child,
            ["config", "user.email", "academy-fixture@arbiterforge.invalid"],
            trust_local_config=True,
        )
        for relative_document, contents in U04_SEED_CONTENT[kind].items():
            document = ensure_within(child, Path(relative_document))
            document.parent.mkdir(parents=True, exist_ok=True)
            document.write_bytes(contents)
        run_git(child, ["add", "--all"], trust_local_config=True)
        run_git(
            child,
            ["commit", "-m", f"academy: initialize U04 {kind} fixture"],
            trust_local_config=True,
        )
        status = run_git(
            child,
            ["status", "--porcelain", "--untracked-files=all"],
            trust_local_config=True,
        )
    except (GitCommandError, OSError, PathBoundaryError) as error:
        raise U04FixtureError("U04 child fixture could not be staged.") from error
    if status.stdout:
        raise U04FixtureError("U04 child fixture is not clean after staging.")


def stage_u04_fixture(repository: Path, *, base: str) -> None:
    """Create the two private repositories that U04 asks the learner to inspect."""
    try:
        head = run_git(repository, ["rev-parse", "HEAD"], trust_local_config=True).stdout.strip()
    except GitCommandError as error:
        raise U04FixtureError("U04 fixture base could not be read.") from error
    if head != base:
        raise U04FixtureError("U04 fixture must be staged from its declared base.")
    for kind, relative in U04_CHILD_PATHS.items():
        _stage_child(repository, relative, kind)
