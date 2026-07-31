"""A narrow, argument-safe subprocess boundary for local Git commands."""

from __future__ import annotations

import subprocess
import os
from pathlib import Path
from typing import Sequence


class GitCommandError(RuntimeError):
    """A local Git invocation could not be completed."""


def _run(command: Sequence[str], *, cwd: Path, check: bool) -> subprocess.CompletedProcess[str]:
    # Preserve only runtime variables Git needs; credentials, tokens, and arbitrary
    # caller variables are deliberately omitted.
    environment = {key: os.environ[key] for key in ("SystemRoot", "WINDIR", "PATH", "PATHEXT", "COMSPEC", "HOME", "USERPROFILE", "TMP", "TEMP") if key in os.environ}
    environment["GIT_TERMINAL_PROMPT"] = "0"
    try:
        result = subprocess.run(
            list(command),
            cwd=cwd,
            text=True,
            encoding="utf-8",
            errors="surrogateescape",
            capture_output=True,
            shell=False,
            check=False,
            timeout=10,
            env=environment,
        )
    except subprocess.TimeoutExpired as error:
        raise GitCommandError("Git command exceeded its bounded timeout.") from error
    except FileNotFoundError as error:
        raise GitCommandError("Git executable was not found on PATH.") from error
    if check and result.returncode:
        detail = result.stderr.strip() or result.stdout.strip() or "Git command failed."
        raise GitCommandError(detail)
    return result


def repository_root(root: Path) -> Path:
    """Resolve *root* to its Git working-tree root without changing repository state."""
    candidate = Path(root).expanduser().resolve()
    result = _run(["git", "rev-parse", "--show-toplevel"], cwd=candidate, check=True)
    return Path(result.stdout.strip()).resolve()


def git_version(directory: Path | None = None) -> str:
    """Return the locally installed Git version without requiring a repository."""
    cwd = Path.cwd() if directory is None else Path(directory).expanduser().resolve()
    return _run(["git", "--version"], cwd=cwd, check=True).stdout.strip()


def run_git(root: Path, args: Sequence[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    """Run Git argument-by-argument from the resolved working-tree root."""
    if isinstance(args, str) or not all(isinstance(argument, str) for argument in args):
        raise TypeError("Git arguments must be a sequence of strings.")
    return _run(["git", *args], cwd=repository_root(root), check=check)
