"""Path containment checks for learner-supplied overlay destinations."""

from __future__ import annotations

import os
from pathlib import Path


class PathBoundaryError(ValueError):
    """A path lies outside the allowed Academy repository root."""


def ensure_within(root: Path, candidate: Path) -> Path:
    """Return a resolved contained path, rejecting lexical and reparse-point escapes."""
    resolved_root = Path(root).expanduser().resolve()
    supplied = Path(candidate).expanduser()
    resolved_candidate = (supplied if supplied.is_absolute() else resolved_root / supplied).resolve()
    try:
        common = os.path.commonpath(
            [os.path.normcase(str(resolved_root)), os.path.normcase(str(resolved_candidate))]
        )
    except ValueError as error:
        raise PathBoundaryError("Path is on a different drive from the repository root.") from error
    if common != os.path.normcase(str(resolved_root)):
        raise PathBoundaryError("Path must remain within the repository root.")
    return resolved_candidate
