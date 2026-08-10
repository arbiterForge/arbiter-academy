"""Display-safe, repository-derived learner attribution for P03."""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from academy_engine.command import GitCommandError, run_git


class AttributionError(ValueError):
    """A Git author name cannot be used as display-safe Academy attribution."""


_SAFE_INTERIOR = frozenset(" ._'-")
_SHA40 = re.compile(r"[0-9a-f]{40}")
_PREPARATION_ERROR = "P03 preparation requires a display-safe Git author name."


def _letter_or_number(character: str) -> bool:
    return unicodedata.category(character)[0] in {"L", "N"}


def validate_display_name(value: str) -> str:
    """Return the exact, unnormalised display-safe author value or reject it."""
    if not isinstance(value, str) or not (1 <= len(value) <= 80):
        raise AttributionError("invalid display-safe Git author name.")
    if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
        raise AttributionError("invalid display-safe Git author name.")
    if not _letter_or_number(value[0]) or not _letter_or_number(value[-1]):
        raise AttributionError("invalid display-safe Git author name.")
    if any(not (_letter_or_number(character) or character in _SAFE_INTERIOR) for character in value[1:-1]):
        raise AttributionError("invalid display-safe Git author name.")
    return value


def prospective_author_name(repository: Path, *, trust_local_config: bool) -> str:
    """Read a prospective Git author name without retaining identity tail data."""
    try:
        result = run_git(
            repository,
            ["var", "GIT_AUTHOR_IDENT"],
            trust_local_config=trust_local_config,
        )
        value = result.stdout
        if not value.endswith("\n") or "\n" in value[:-1]:
            raise AttributionError("malformed")
        identity = value[:-1]
        marker = identity.rfind(" <")
        if marker <= 0 or "> " not in identity[marker + 2 :]:
            raise AttributionError("malformed")
        name = identity[:marker]
        return validate_display_name(name)
    except (AttributionError, GitCommandError, OSError, UnicodeError):
        raise AttributionError(_PREPARATION_ERROR) from None


def commit_author_name(repository: Path, commit: str) -> str:
    """Read the exact non-mailmapped author name stored by a commit."""
    try:
        if _SHA40.fullmatch(commit) is None:
            raise AttributionError("invalid")
        result = run_git(repository, ["show", "-s", "--format=%an%x00", commit])
        value = result.stdout
        if value.count("\x00") != 1 or not value.endswith("\x00\n"):
            raise AttributionError("malformed")
        name = value[:-2]
        if "\n" in name or "\r" in name:
            raise AttributionError("malformed")
        return validate_display_name(name)
    except (AttributionError, GitCommandError, OSError, UnicodeError):
        raise AttributionError("P03 committed attribution is invalid.") from None
