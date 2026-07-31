"""Path containment checks for learner-supplied overlay destinations."""

from __future__ import annotations

import os
import stat
from pathlib import Path


class PathBoundaryError(ValueError):
    """A path lies outside the allowed Academy repository root."""


def ensure_within(root: Path, candidate: Path) -> Path:
    """Return a contained path after rejecting every existing reparse-point ancestor."""
    resolved_root = Path(root).expanduser().resolve()
    supplied = Path(candidate).expanduser()
    lexical_candidate = supplied if supplied.is_absolute() else resolved_root / supplied
    try:
        common = os.path.commonpath(
            [os.path.normcase(os.path.abspath(str(resolved_root))), os.path.normcase(os.path.abspath(str(lexical_candidate)))]
        )
    except ValueError as error:
        raise PathBoundaryError("Path is on a different drive from the repository root.") from error
    if common != os.path.normcase(str(resolved_root)):
        raise PathBoundaryError("Path must remain within the repository root.")
    relative = os.path.relpath(os.path.abspath(str(lexical_candidate)), str(resolved_root))
    if relative == os.pardir or relative.startswith(os.pardir + os.sep):
        raise PathBoundaryError("Path must remain within the repository root.")
    current = resolved_root
    for component in Path(relative).parts:
        if component in {"", "."}:
            continue
        current /= component
        try:
            details = os.lstat(current)
        except FileNotFoundError:
            continue
        attributes = getattr(details, "st_file_attributes", 0)
        if stat.S_ISLNK(details.st_mode) or attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400):
            raise PathBoundaryError("Path must not traverse a symlink or reparse point.")
    return lexical_candidate.resolve()
