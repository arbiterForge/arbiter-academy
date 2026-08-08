"""Fail closed when an Arbiter Academy Preview artifact is not self-contained."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit


_SHA = re.compile(r"^[0-9a-f]{40}$")
_CSS_URL = re.compile(r"url\(\s*[\"']?([^\"')]+)")
_CSS_IMPORT = re.compile(
    r"@import\s+(?:url\(\s*)?(?:[\"']([^\"']+)[\"']|([^\"'()\s;]+))\s*\)?",
    re.IGNORECASE,
)
_DISCUSSION_URL = "https://github.com/arbiterForge/arbiter-academy/discussions"
_ASSET_SHA256 = {
    Path("assets/academy.css"): "495c3496ca30e6cb7913fc87fc1beca550b38bb9993f487f66eae8a246c713b1",
    Path("assets/fonts/jetbrains-mono-latin-wght-normal.woff2"): (
        "18be452724bfdc236c074ca94a249a7f41a86752c7d04ab258ce9ed5651f6a7e"
    ),
    Path("assets/fonts/manrope-latin-wght-normal.woff2"): (
        "a30ddcd349703aff7464c34bef3fffdff405ee50c113440d7c8693c02d210972"
    ),
}
_ALLOWED_HTML_ATTRIBUTES = {
    "html": {"lang"},
    "head": set(),
    "meta": {"charset", "name", "content"},
    "title": set(),
    "link": {"rel", "href"},
    "body": set(),
    "a": {"class", "href", "aria-label"},
    "header": {"class"},
    "div": {"class", "role"},
    "span": {"class", "aria-hidden"},
    "nav": {"aria-label"},
    "main": {"id", "tabindex"},
    "footer": {"class"},
    "p": {"class"},
    "h1": set(),
    "h2": set(),
    "code": set(),
    "ol": set(),
    "li": set(),
    "strong": set(),
    "ul": set(),
}
_LABS = (
    "F01-fork-clone-doctor",
    "F02-orient-to-state",
    "F03-work-the-board",
    "F04-fix-with-evidence",
    "P01-feature-through-plan",
    "P02-commit-review-pr",
    "P03-record-an-adr",
    "P04-review-a-dependency",
)
_EXPECTED_FILES = {
    Path("assets/academy.css"),
    Path("assets/fonts/jetbrains-mono-latin-wght-normal.woff2"),
    Path("assets/fonts/manrope-latin-wght-normal.woff2"),
    Path("index.html"),
    Path("recovery/index.html"),
    Path("release.json"),
    *(Path("labs") / lab_id / "index.html" for lab_id in _LABS),
}


class _LinkCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.targets: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        allowed = _ALLOWED_HTML_ATTRIBUTES.get(tag)
        if allowed is None:
            raise ValueError(f"disallowed HTML element: {tag}")
        names = [name for name, _ in attrs]
        if len(names) != len(set(names)):
            raise ValueError(f"disallowed HTML duplicate attribute on {tag}")
        for name, value in attrs:
            if name not in allowed or value is None:
                raise ValueError(f"disallowed HTML attribute on {tag}: {name}")
            if name == "href":
                self.targets.append((tag, value))
        if tag == "html" and dict(attrs) != {"lang": "en"}:
            raise ValueError("disallowed HTML attributes on html")
        if tag == "link" and dict(attrs).get("rel") != "stylesheet":
            raise ValueError("disallowed HTML link relationship")

    def handle_endtag(self, tag: str) -> None:
        if tag not in _ALLOWED_HTML_ATTRIBUTES:
            raise ValueError(f"disallowed HTML element: {tag}")

    def handle_decl(self, decl: str) -> None:
        if decl.lower() != "doctype html":
            raise ValueError(f"disallowed HTML declaration: {decl}")

    def handle_pi(self, data: str) -> None:
        raise ValueError("disallowed HTML processing instruction")


def _is_symlink_or_reparse(path: Path) -> bool:
    try:
        details = path.lstat()
    except FileNotFoundError:
        return False
    except OSError as error:
        raise ValueError(f"could not inspect artifact path {path}: {error}") from error
    attributes = getattr(details, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return stat.S_ISLNK(details.st_mode) or bool(attributes & reparse_flag)


def _reject_unsafe_lexical_components(path: Path) -> None:
    absolute = Path(os.path.abspath(path))
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        try:
            details = current.lstat()
        except FileNotFoundError:
            break
        except OSError as error:
            raise ValueError(f"could not inspect artifact path {current}: {error}") from error
        attributes = getattr(details, "st_file_attributes", 0)
        reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
        if stat.S_ISLNK(details.st_mode) or bool(attributes & reparse_flag):
            raise ValueError(
                "preview artifact root must be a real directory; "
                f"artifact path contains a symlink or reparse point: {current}"
            )


def _artifact_files(root: Path) -> set[Path]:
    found: set[Path] = set()
    for path in root.rglob("*"):
        if _is_symlink_or_reparse(path):
            raise ValueError(
                f"artifact contains a symlink or reparse point: {path.relative_to(root).as_posix()}"
            )
        if path.is_file():
            found.add(path.relative_to(root))
    return found


def _resolve_local(
    root: Path,
    source: Path,
    target: str,
    *,
    allow_discussion: bool = False,
) -> Path | None:
    parsed = urlsplit(target)
    if parsed.scheme or parsed.netloc:
        if not allow_discussion or target != _DISCUSSION_URL:
            raise ValueError(f"unapproved external URL in {source.relative_to(root).as_posix()}: {target}")
        return None
    path = unquote(parsed.path)
    if not path or path.startswith("#"):
        return None
    if path.startswith("/") or "\\" in path:
        raise ValueError(f"project-unsafe root-relative URL in {source.relative_to(root).as_posix()}: {target}")
    candidate = (source.parent / path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as error:
        raise ValueError(f"internal link escapes artifact root: {target}") from error
    if not candidate.is_file():
        raise ValueError(
            f"broken internal link in {source.relative_to(root).as_posix()}: {target}"
        )
    return candidate


def _check_release(root: Path) -> None:
    try:
        data = json.loads((root / "release.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"release.json is unreadable: {error}") from error
    if (
        not isinstance(data, dict)
        or set(data) != {"release", "commit"}
        or data.get("release") != "preview-0.1"
        or not isinstance(data.get("commit"), str)
        or not _SHA.fullmatch(data["commit"])
    ):
        raise ValueError("release.json does not contain the exact Preview 0.1 provenance contract")


def _check_asset_digests(root: Path) -> None:
    for relative, expected in _ASSET_SHA256.items():
        try:
            actual = hashlib.sha256((root / relative).read_bytes()).hexdigest()
        except OSError as error:
            raise ValueError(f"reviewed runtime asset is unreadable: {relative.as_posix()}: {error}") from error
        if actual != expected:
            raise ValueError(f"runtime asset digest mismatch: {relative.as_posix()}")


def _check_stylesheet_dependencies(root: Path, stylesheet: Path, css: str) -> None:
    for quoted, unquoted in _CSS_IMPORT.findall(css):
        _resolve_local(root, stylesheet, quoted or unquoted)
    for target in _CSS_URL.findall(css):
        _resolve_local(root, stylesheet, target)


def check_preview_site(site_root: Path) -> None:
    _reject_unsafe_lexical_components(site_root)
    root = site_root.resolve()
    if not root.is_dir():
        raise ValueError("preview artifact root must be a real directory")
    actual = _artifact_files(root)
    if actual != _EXPECTED_FILES:
        missing = sorted(path.as_posix() for path in _EXPECTED_FILES - actual)
        unexpected = sorted(path.as_posix() for path in actual - _EXPECTED_FILES)
        raise ValueError(
            "preview artifact inventory mismatch; "
            f"missing={missing or 'none'}; unexpected={unexpected or 'none'}"
        )

    _check_release(root)
    _check_asset_digests(root)
    for relative in sorted(path for path in actual if path.suffix == ".html"):
        page = root / relative
        try:
            text = page.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            raise ValueError(f"generated HTML is unreadable: {relative.as_posix()}: {error}") from error
        collector = _LinkCollector()
        collector.feed(text)
        for tag, target in collector.targets:
            resolved = _resolve_local(
                root,
                page,
                target,
                allow_discussion=tag == "a",
            )
            if tag == "link" and resolved != root / "assets" / "academy.css":
                raise ValueError(f"unapproved stylesheet URL: {target}")

    stylesheet = root / "assets/academy.css"
    try:
        css = stylesheet.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise ValueError(f"generated stylesheet is unreadable: {error}") from error
    _check_stylesheet_dependencies(root, stylesheet, css)


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("site_root", type=Path)
    options = parser.parse_args(arguments)
    try:
        check_preview_site(options.site_root)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
