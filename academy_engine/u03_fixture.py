"""Trusted U03 release-target fixture construction."""

from __future__ import annotations

from pathlib import Path

from academy_engine.command import GitCommandError, run_git


class U03FixtureError(ValueError):
    """The U03 release-target fixture cannot be staged exactly."""


U03_RELEASE_TARGETS_PATH = ".codearbiter/release-targets.md"
U03_RELEASE_TARGETS_SOURCE = "academy/scenarios/U03-refactor-chore-release/files/release-targets.md"
_EXPECTED_TARGETS = (
    b"<!-- release-targets -->\n"
    b"[academy-private-training]\n"
    b"prefix: academy-v\n"
    b"changelog: CHANGELOG.md\n"
    b"payload: .\n"
    b"<!-- /release-targets -->\n"
)


def stage_u03_fixture(repository: Path, *, base: str) -> tuple[str, ...]:
    """Stage the reviewed target declaration from the immutable scenario source."""
    try:
        if run_git(repository, ["rev-parse", "HEAD"], trust_local_config=True).stdout.strip() != base:
            raise U03FixtureError("U03 fixture must be staged from its declared base.")
        source = repository / U03_RELEASE_TARGETS_SOURCE
        target = repository / U03_RELEASE_TARGETS_PATH
        raw = source.read_bytes()
        if raw != _EXPECTED_TARGETS:
            raise U03FixtureError("U03 release target declaration is not canonical.")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        run_git(repository, ["add", "--", U03_RELEASE_TARGETS_PATH], trust_local_config=True)
    except (GitCommandError, OSError) as error:
        raise U03FixtureError("U03 release target fixture could not be staged.") from error
    return (U03_RELEASE_TARGETS_PATH,)
