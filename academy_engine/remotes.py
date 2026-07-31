"""Offline validation of the fork-first GitHub remote contract."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from academy_engine.command import GitCommandError, run_git


OFFICIAL_OWNER = "arbiterForge"
OFFICIAL_REPOSITORY = "arbiter-academy"
_GITHUB_NAME = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")
_SCP_REMOTE = re.compile(r"^(?P<user>[^@:/]+)@(?P<host>[^:/]+):(?P<path>[^:]+)$")


class RemoteSafetyError(ValueError):
    """A remote is malformed or unsuitable for a training exercise."""


@dataclass(frozen=True)
class GitHubRemote:
    owner: str
    repository: str

    def matches(self, owner: str, repository: str) -> bool:
        return self.owner.casefold() == owner.casefold() and self.repository.casefold() == repository.casefold()

    @property
    def is_official(self) -> bool:
        return self.matches(OFFICIAL_OWNER, OFFICIAL_REPOSITORY)


@dataclass(frozen=True)
class RemoteReport:
    origin: GitHubRemote | None
    upstream: GitHubRemote | None
    issues: tuple[str, ...]
    push_safe: bool


def _invalid() -> RemoteSafetyError:
    return RemoteSafetyError("GitHub remote must use a canonical GitHub HTTPS, SSH, or SCP-style URL.")


def _parse_path(path: str) -> GitHubRemote:
    if not path.startswith("/") or "%" in path or "\\" in path:
        raise _invalid()
    components = path[1:].split("/")
    if len(components) != 2 or any(component in {"", ".", ".."} for component in components):
        raise _invalid()
    owner, repository = components
    if repository.casefold().endswith(".git.git"):
        raise _invalid()
    if repository.casefold().endswith(".git"):
        repository = repository[:-4]
    if not _GITHUB_NAME.fullmatch(owner) or not _GITHUB_NAME.fullmatch(repository):
        raise _invalid()
    return GitHubRemote(owner=owner, repository=repository)


def normalize_github_remote(url: str) -> GitHubRemote:
    """Parse one canonical GitHub remote URL without doing network I/O."""
    if not isinstance(url, str) or not url or url != url.strip():
        raise _invalid()
    scp = _SCP_REMOTE.fullmatch(url)
    if scp is not None:
        if scp.group("user") != "git" or scp.group("host").casefold() != "github.com":
            raise _invalid()
        return _parse_path("/" + scp.group("path"))

    parsed = urlsplit(url)
    if parsed.scheme not in {"https", "ssh"} or parsed.hostname is None:
        raise _invalid()
    try:
        port = parsed.port
    except ValueError as error:
        raise _invalid() from error
    if (
        parsed.hostname.casefold() != "github.com"
        or parsed.query
        or parsed.fragment
        or port is not None
        or parsed.password is not None
    ):
        raise _invalid()
    if parsed.scheme == "https" and parsed.username is not None:
        raise _invalid()
    if parsed.scheme == "ssh" and parsed.username != "git":
        raise _invalid()
    return _parse_path(parsed.path)


def _remote(root: Path, name: str) -> tuple[GitHubRemote | None, str | None]:
    result = run_git(root, ["remote", "get-url", name], check=False)
    if result.returncode:
        return None, f"{name} remote is missing."
    try:
        return normalize_github_remote(result.stdout.strip()), None
    except RemoteSafetyError as error:
        return None, f"{name} remote is invalid: {error}"


def validate_training_remotes(root: Path, *, require_push_safe: bool) -> RemoteReport:
    """Assess configured remotes; only raise when a push-safe exercise demands it."""
    issues: list[str] = []
    try:
        origin, origin_error = _remote(root, "origin")
        upstream, upstream_error = _remote(root, "upstream")
    except GitCommandError as error:
        if require_push_safe:
            raise RemoteSafetyError(str(error)) from error
        return RemoteReport(None, None, (str(error),), False)
    if origin_error:
        issues.append(origin_error)
    elif origin is not None:
        if origin.is_official:
            issues.append("origin is the official repository; configure a learner-owned fork as origin.")
        elif not origin.matches(origin.owner, OFFICIAL_REPOSITORY):
            issues.append("origin must be a GitHub fork of arbiterForge/arbiter-academy.")
    if upstream_error:
        issues.append(upstream_error)
    elif upstream is not None and not upstream.is_official:
        issues.append("upstream must resolve to arbiterForge/arbiter-academy.")
    report = RemoteReport(origin, upstream, tuple(issues), not issues)
    if require_push_safe and not report.push_safe:
        raise RemoteSafetyError(" ".join(report.issues))
    return report
