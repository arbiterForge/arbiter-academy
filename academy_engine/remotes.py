"""Offline validation of the fork-first GitHub remote contract."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from academy_engine.command import GitCommandError, run_git


OFFICIAL_OWNER = "arbiterForge"
OFFICIAL_REPOSITORY = "arbiter-academy"
PUSH_DISABLED = "DISABLED"
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
    origin_push_targets: tuple[GitHubRemote, ...] = ()
    upstream_push_disabled: bool = False
    effective_push_remote: str | None = None
    lineage_verified_offline: bool = False
    origin_fork_compatible: bool = False


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
    if (
        not isinstance(url, str)
        or not url
        or url != url.strip()
        or any(ord(character) < 0x20 or ord(character) == 0x7F for character in url)
    ):
        raise _invalid()
    scp = _SCP_REMOTE.fullmatch(url)
    if scp is not None:
        if scp.group("user") != "git" or scp.group("host").casefold() != "github.com":
            raise _invalid()
        return _parse_path("/" + scp.group("path"))

    try:
        parsed = urlsplit(url)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError as error:
        raise _invalid() from error
    if parsed.scheme not in {"https", "ssh"} or hostname is None:
        raise _invalid()
    if (
        hostname.casefold() != "github.com"
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


def _remote_urls(root: Path, name: str, *, push: bool = False) -> tuple[tuple[str, ...], str | None]:
    args = ["remote", "get-url"]
    if push:
        args.append("--push")
    args.extend(["--all", name])
    result = run_git(root, args, check=False)
    if result.returncode:
        kind = "push target" if push else "remote"
        return (), f"{name} {kind} is missing."
    urls = tuple(line for line in result.stdout.splitlines() if line)
    if not urls:
        kind = "push target" if push else "remote"
        return (), f"{name} {kind} is missing."
    return urls, None


def _normalized_remotes(
    urls: tuple[str, ...],
    *,
    name: str,
    kind: str,
) -> tuple[tuple[GitHubRemote, ...], tuple[str, ...]]:
    remotes: list[GitHubRemote] = []
    issues: list[str] = []
    for url in urls:
        try:
            remotes.append(normalize_github_remote(url))
        except RemoteSafetyError as error:
            issues.append(f"{name} {kind} is invalid: {error}")
    return tuple(remotes), tuple(issues)


def _config_values(root: Path, key: str) -> tuple[str, ...]:
    result = run_git(root, ["config", "--get-all", key], check=False)
    if result.returncode:
        return ()
    return tuple(line for line in result.stdout.splitlines() if line)


def _effective_push_remote(root: Path) -> tuple[str | None, str | None]:
    branch_result = run_git(
        root,
        ["symbolic-ref", "--quiet", "--short", "HEAD"],
        check=False,
    )
    if branch_result.returncode:
        return None, "push routing is unknown because HEAD is detached."
    branch = branch_result.stdout.strip()
    routing_keys = (
        f"branch.{branch}.pushRemote",
        "remote.pushDefault",
        f"branch.{branch}.remote",
    )
    for key in routing_keys:
        values = _config_values(root, key)
        if len(values) > 1:
            return None, f"push routing is ambiguous because {key} has multiple values."
        if values:
            return values[0], None
    return "origin", None


def validate_training_remotes(root: Path, *, require_push_safe: bool) -> RemoteReport:
    """Assess configured remotes; only raise when a push-safe exercise demands it."""
    issues: list[str] = []
    try:
        origin_urls, origin_error = _remote_urls(root, "origin")
        upstream_urls, upstream_error = _remote_urls(root, "upstream")
        origin_push_urls, origin_push_error = _remote_urls(root, "origin", push=True)
        upstream_push_urls, upstream_push_error = _remote_urls(root, "upstream", push=True)
        effective_push_remote, routing_error = _effective_push_remote(root)
    except GitCommandError as error:
        if require_push_safe:
            raise RemoteSafetyError(str(error)) from error
        return RemoteReport(None, None, (str(error),), False)

    origin_remotes, origin_parse_issues = _normalized_remotes(
        origin_urls,
        name="origin",
        kind="remote",
    )
    upstream_remotes, upstream_parse_issues = _normalized_remotes(
        upstream_urls,
        name="upstream",
        kind="remote",
    )
    origin_push_targets, origin_push_issues = _normalized_remotes(
        origin_push_urls,
        name="origin",
        kind="push target",
    )
    origin = origin_remotes[0] if origin_remotes else None
    upstream = upstream_remotes[0] if upstream_remotes else None
    origin_fork_compatible = bool(
        origin is not None
        and len(origin_remotes) == len(origin_urls)
        and not origin.is_official
        and origin.matches(origin.owner, OFFICIAL_REPOSITORY)
        and all(remote.matches(origin.owner, origin.repository) for remote in origin_remotes)
    )

    if origin_error:
        issues.append(origin_error)
    issues.extend(origin_parse_issues)
    if origin is not None and not origin_parse_issues:
        if origin.is_official:
            issues.append(
                "origin must be a non-official same-name GitHub repository; "
                "offline validation cannot prove fork lineage."
            )
        elif not origin.matches(origin.owner, OFFICIAL_REPOSITORY):
            issues.append(
                "origin must be a non-official same-name GitHub repository "
                "for fork-compatible training."
            )
        elif any(not remote.matches(origin.owner, origin.repository) for remote in origin_remotes):
            issues.append("every origin fetch URL must identify the same GitHub owner/repository.")

    if origin_push_error:
        issues.append(origin_push_error)
    issues.extend(origin_push_issues)
    if (
        origin is not None
        and not origin_parse_issues
        and not origin_push_issues
        and any(not target.matches(origin.owner, origin.repository) for target in origin_push_targets)
    ):
        issues.append(
            "every origin push target must match origin's non-official GitHub owner/repository."
        )

    if upstream_error:
        issues.append(upstream_error)
    issues.extend(upstream_parse_issues)
    if (
        upstream is not None
        and not upstream_parse_issues
        and any(not remote.is_official for remote in upstream_remotes)
    ):
        issues.append("every upstream fetch URL must resolve to arbiterForge/arbiter-academy.")

    upstream_push_disabled = (
        not upstream_push_error
        and bool(upstream_push_urls)
        and all(url == PUSH_DISABLED for url in upstream_push_urls)
    )
    if not upstream_push_disabled:
        issues.append(
            "upstream push targets must be explicitly disabled with "
            "`git remote set-url --push upstream DISABLED`."
        )

    if routing_error:
        issues.append(routing_error)
    elif effective_push_remote != "origin":
        issues.append(
            f"current branch push routing must resolve to origin, not "
            f"{effective_push_remote or 'an unknown remote'}."
        )

    report = RemoteReport(
        origin,
        upstream,
        tuple(issues),
        not issues,
        origin_push_targets,
        upstream_push_disabled,
        effective_push_remote,
        False,
        origin_fork_compatible,
    )
    if require_push_safe and not report.push_safe:
        raise RemoteSafetyError(" ".join(report.issues))
    return report
