#!/usr/bin/env python3
"""Verify a Preview compatibility declaration against a local codeArbiter checkout."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Mapping, NoReturn


_COMPONENT_PREFIXES = {
    "codearbiter": "v",
    "ca-codex": "ca-codex-v",
    "ca-pi": "ca-pi-v",
}
_COMMIT = re.compile(r"[0-9a-f]{40}")
_DIGEST = re.compile(r"[0-9a-f]{64}")
_VERSION = re.compile(r"([0-9]+)\.([0-9]+)\.([0-9]+)")
_SEMVER_NUMBER = r"(?:0|[1-9][0-9]*)"
_SEMVER_PRERELEASE_IDENTIFIER = (
    r"(?:0|[1-9][0-9]*|[0-9A-Za-z-]*[A-Za-z-][0-9A-Za-z-]*)"
)
_SEMVER_PRERELEASE = re.compile(
    rf"{_SEMVER_NUMBER}\.{_SEMVER_NUMBER}\.{_SEMVER_NUMBER}"
    rf"-(?:{_SEMVER_PRERELEASE_IDENTIFIER})"
    rf"(?:\.{_SEMVER_PRERELEASE_IDENTIFIER})*"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
)
_SAFE_DIAGNOSTIC = re.compile(r"[^A-Za-z0-9 ._/@:+-]")
_MAX_MANIFEST_PATH_BYTES = 1024


class CompatibilityError(Exception):
    """A bounded compatibility rejection suitable for a maintainer diagnostic."""

    def __init__(self, component_id: str, detail: str) -> None:
        super().__init__(detail)
        self.component_id = component_id
        self.detail = detail


def _reject(component_id: object, detail: str) -> NoReturn:
    label = _sanitize(component_id, 40) or "declaration"
    raise CompatibilityError(label, detail)


def _sanitize(value: object, limit: int) -> str:
    text = _SAFE_DIAGNOSTIC.sub(
        "?", str(value).replace("\r", "?").replace("\n", "?")
    )
    return text[:limit]


def _git(repository: Path, *arguments: str) -> bytes:
    try:
        result = subprocess.run(
            ["git", "-C", str(repository), *arguments],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=10,
        )
    except (
        OSError,
        subprocess.TimeoutExpired,
        UnicodeError,
        ValueError,
    ) as error:
        raise CompatibilityError(
            "codearbiter", "Git inspection could not complete"
        ) from error
    if result.returncode != 0:
        raise CompatibilityError(
            "codearbiter", "Git inspection rejected the requested object"
        )
    return result.stdout


def _mapping(
    value: object, component_id: str, label: str
) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        _reject(component_id, f"{label} must be an object")
    return value


def _canonical_version(
    component_id: str, value: object, label: str
) -> tuple[int, int, int]:
    if not isinstance(value, str):
        _reject(component_id, f"{label} version is malformed")
    match = _VERSION.fullmatch(value)
    if match is None:
        _reject(component_id, f"{label} version is malformed")
    parts = match.groups()
    if any(str(int(part)) != part for part in parts):
        _reject(component_id, f"{label} version is ambiguous")
    return int(parts[0]), int(parts[1]), int(parts[2])


def _load_components(
    manifest_path: Path,
) -> tuple[Mapping[str, object], ...]:
    try:
        document = json.loads(manifest_path.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CompatibilityError(
            "declaration", "Preview manifest could not be read"
        ) from error
    document = _mapping(document, "declaration", "Preview manifest")
    compatibility = _mapping(
        document.get("integration_compatibility"),
        "declaration",
        "integration compatibility",
    )
    values = compatibility.get("components")
    if not isinstance(values, list) or len(values) != len(_COMPONENT_PREFIXES):
        _reject(
            "declaration",
            "compatibility components must contain exactly three records",
        )

    components = tuple(
        _mapping(value, f"component-{index}", "compatibility component")
        for index, value in enumerate(values, start=1)
    )
    component_ids = tuple(
        component.get("component_id") for component in components
    )
    if component_ids != tuple(_COMPONENT_PREFIXES):
        _reject(
            "declaration", "compatibility component IDs or order are invalid"
        )

    source_commits = tuple(
        component.get("source_commit") for component in components
    )
    if any(commit != source_commits[0] for commit in source_commits[1:]):
        _reject(
            "declaration",
            "compatibility components do not share one source commit",
        )
    return components


def _release_tags(repository: Path) -> tuple[str, ...]:
    try:
        output = _git(
            repository,
            "for-each-ref",
            "--format=%(refname:strip=2)",
            "refs/tags",
        ).decode("utf-8")
    except UnicodeDecodeError as error:
        raise CompatibilityError(
            "codearbiter", "release tag refs are not UTF-8"
        ) from error
    return tuple(line for line in output.splitlines() if line)


def _family_versions(
    component_id: str, prefix: str, tags: tuple[str, ...]
) -> dict[str, tuple[int, int, int]]:
    versions: dict[str, tuple[int, int, int]] = {}
    for tag in tags:
        if not tag.startswith(prefix):
            continue
        suffix = tag[len(prefix) :]
        match = _VERSION.fullmatch(suffix)
        if match is None:
            if _SEMVER_PRERELEASE.fullmatch(suffix):
                continue
            _reject(
                component_id,
                f"release family contains malformed tag {_sanitize(tag, 80)}",
            )
        parts = match.groups()
        if any(str(int(part)) != part for part in parts):
            _reject(
                component_id,
                f"release family contains ambiguous tag {_sanitize(tag, 80)}",
            )
        versions[tag] = int(parts[0]), int(parts[1]), int(parts[2])
    if not versions:
        _reject(component_id, "release tag family is missing")
    return versions


def _required_string(
    component: Mapping[str, object], component_id: str, key: str
) -> str:
    value = component.get(key)
    if not isinstance(value, str) or not value:
        _reject(component_id, f"declared {key} is invalid")
    return value


def _verify_component(
    repository: Path,
    component: Mapping[str, object],
    all_tags: tuple[str, ...],
) -> None:
    component_id = _required_string(
        component, "declaration", "component_id"
    )
    prefix = _COMPONENT_PREFIXES[component_id]
    declared_tag = _required_string(component, component_id, "release_tag")
    declared_version = _required_string(component, component_id, "version")
    version = _canonical_version(component_id, declared_version, "declared")
    if declared_tag != f"{prefix}{declared_version}":
        _reject(component_id, "declared tag and version do not match")

    family = _family_versions(component_id, prefix, all_tags)
    latest_tag, latest_version = max(
        family.items(), key=lambda item: item[1]
    )
    if declared_tag not in family:
        _reject(component_id, "declared release tag is missing")
    if version != latest_version:
        _reject(
            component_id,
            f"declaration is stale; newest tag is {_sanitize(latest_tag, 80)}",
        )

    source_commit = _required_string(
        component, component_id, "source_commit"
    )
    if _COMMIT.fullmatch(source_commit) is None:
        _reject(component_id, "declared source commit is invalid")
    try:
        tag_commit = _git(
            repository,
            "rev-parse",
            "--verify",
            f"refs/tags/{declared_tag}^{{commit}}",
        ).decode("ascii").strip()
    except (UnicodeDecodeError, CompatibilityError):
        _reject(component_id, "tag source commit could not be resolved")
    if tag_commit != source_commit:
        _reject(
            component_id,
            "tag does not peel to the declared source commit",
        )

    manifest_path = _required_string(
        component, component_id, "manifest_path"
    )
    try:
        encoded_manifest_path = manifest_path.encode("utf-8")
    except UnicodeError:
        _reject(component_id, "declared manifest path is invalid")
    path = PurePosixPath(manifest_path)
    raw_path_parts = manifest_path.split("/")
    if (
        not encoded_manifest_path
        or len(encoded_manifest_path) > _MAX_MANIFEST_PATH_BYTES
        or "\\" in manifest_path
        or any(
            ord(character) < 32 or ord(character) == 127
            for character in manifest_path
        )
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in raw_path_parts)
    ):
        _reject(component_id, "declared manifest path is invalid")
    try:
        raw_manifest = _git(
            repository,
            "cat-file",
            "blob",
            f"{declared_tag}:{manifest_path}",
        )
    except CompatibilityError:
        _reject(
            component_id,
            "declared manifest path is missing from the tag",
        )

    try:
        manifest = json.loads(raw_manifest)
    except (UnicodeDecodeError, json.JSONDecodeError):
        _reject(component_id, "component manifest is not valid JSON")
    manifest = _mapping(manifest, component_id, "component manifest")
    if manifest.get("version") != declared_version:
        _reject(
            component_id,
            "component manifest version does not match the declaration",
        )

    declared_digest = _required_string(
        component, component_id, "manifest_sha256"
    )
    if _DIGEST.fullmatch(declared_digest) is None:
        _reject(component_id, "declared manifest SHA-256 is invalid")
    if hashlib.sha256(raw_manifest).hexdigest() != declared_digest:
        _reject(
            component_id,
            "raw component manifest SHA-256 does not match",
        )


def check_compatibility(manifest_path: Path, repository: Path) -> None:
    components = _load_components(manifest_path)
    tags = _release_tags(repository)
    for component in components:
        _verify_component(repository, component, tags)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Verify Preview compatibility against a local codeArbiter checkout."
        )
    )
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--codearbiter-root", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    arguments = _parse_args()
    try:
        check_compatibility(
            arguments.manifest, arguments.codearbiter_root
        )
    except CompatibilityError as error:
        component = _sanitize(error.component_id, 40) or "declaration"
        detail = _sanitize(error.detail, 400) or "compatibility check failed"
        sys.stderr.write(f"ERROR: {component}: {detail}\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
