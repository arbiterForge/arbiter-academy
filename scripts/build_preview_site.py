"""Build the fail-closed static public surface for Academy Preview 0.6."""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import sys
from collections.abc import Mapping
from html import escape
from pathlib import Path
from string import Template

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(_REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPOSITORY_ROOT))

from academy_engine.lesson_actions import LessonAction, load_action_manifest
from academy_engine.paths import ensure_within
from academy_engine.preview import PreviewManifest, load_preview_manifest


_SHA = re.compile(r"^[0-9a-f]{40}$")
_FRONTMATTER_FIELDS = ("title", "outcome", "estimated_minutes", "next_lab")
_FENCE_LANGUAGES = {"powershell", "text", "sh", "json"}
_HEADING = re.compile(r"^(#{1,3}) ([^#].*)$")
_TABLE_DIVIDER = re.compile(r"^\|\s*:?-{3,}:?\s*\|\s*:?-{3,}:?\s*\|$")
_ORDERED_ITEM = re.compile(r"^(?P<number>[1-9][0-9]*)\. (?P<body>\S.*)$")
_UNSUPPORTED_BLOCK = re.compile(r"^(?:[-+*]\s|\d+[.)]\s|>|#{4,}\s|<)")
_RAW_HTML = re.compile(r"(?:</?[A-Za-z][^>]*>|<!--.*?-->)")
_LINK_OR_IMAGE = re.compile(r"!?\[[^\]]*\]\([^)]*\)")
_INLINE_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_GUIDE_LINK_TARGETS = frozenset(
    {
        "../../index.html",
        "https://arbiterforge.github.io/codeArbiter/getting-started/choose-your-host/",
    }
)
_ACTION_REFERENCE = re.compile(r"\{\{action:([A-Za-z0-9][A-Za-z0-9-]{0,95})\}\}")
_UNSUPPORTED_INLINE_MARKERS = ("*", "_", "[", "]", "\\", "~")
_PUBLIC_ASSET_FILES = (
    Path("assets/academy.css"),
    Path("assets/academy.js"),
    Path("assets/favicon.svg"),
    Path("assets/fonts/jetbrains-mono-latin-wght-normal.woff2"),
    Path("assets/fonts/manrope-latin-wght-normal.woff2"),
    Path("assets/gate-mark.svg"),
    Path("assets/hero-gates.webp"),
    Path("assets/logo.svg"),
)


def build_preview_site(root: Path, out: Path, *, release_sha: str | None = None) -> None:
    """Render only the reviewed Preview 0.6 pages into *out*.

    All inputs are validated before any page is written so a missing lesson
    cannot leave a partial public site behind.
    """
    _reject_unsafe_lexical_components(out)
    manifest = load_preview_manifest(root)
    commit = _validate_release_sha(release_sha)
    templates = _load_templates(root)
    expected_files = _expected_files(manifest)
    expected_paths = _expected_paths(manifest)
    _reject_unsafe_generated_paths(out, expected_paths, expected_files)
    _reject_unexpected_generated_paths(out, expected_paths)
    assets = _load_public_assets(root)
    guides = {
        document_id: _read_optional_guide(root, document_id)
        for document_id in ("home", "recovery")
    }

    lessons = {
        lab_id: _read_public_lesson(root, lab_id, guided=lab_id in manifest.guided_labs)
        for lab_id in manifest.available_labs
    }
    rendered_pages = _render_pages(manifest, lessons, guides, templates, commit)
    _validate_rendered_inventory(rendered_pages, _expected_rendered_files(manifest))

    for relative_path, content in rendered_pages.items():
        destination = out / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")
    for relative_path, content in assets.items():
        destination = out / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)

    actual_files = {
        path.relative_to(out)
        for path in out.rglob("*")
        if path.is_file()
    }
    if actual_files != expected_files:
        raise ValueError("generated file inventory does not match the reviewed Preview artifact")


def _validate_release_sha(release_sha: str | None) -> str:
    if not isinstance(release_sha, str) or not _SHA.fullmatch(release_sha):
        raise ValueError("release SHA must be a lowercase 40-character Git commit SHA")
    return release_sha


def _load_templates(root: Path) -> dict[str, Template]:
    templates: dict[str, Template] = {}
    for name in ("base", "index", "lab", "recovery"):
        path = root / "site" / "templates" / f"{name}.html"
        try:
            templates[name] = Template(path.read_text(encoding="utf-8"))
        except OSError as error:
            raise ValueError(f"could not read site template {name}: {error}") from error
    return templates


def _load_public_assets(root: Path) -> dict[Path, bytes]:
    assets: dict[Path, bytes] = {}
    for relative in _PUBLIC_ASSET_FILES:
        source = root / "site" / relative
        if source.is_symlink() or not source.is_file():
            raise ValueError(f"reviewed public asset is missing or unsafe: {relative.as_posix()}")
        try:
            assets[relative] = source.read_bytes()
        except OSError as error:
            raise ValueError(f"could not read reviewed public asset {relative.as_posix()}: {error}") from error
    return assets


def _expected_rendered_files(manifest: PreviewManifest) -> set[Path]:
    paths = {Path("index.html"), Path("release.json"), Path("recovery/index.html")}
    for lab_id in manifest.available_labs:
        paths.add(Path("labs") / lab_id / "index.html")
    return paths


def _expected_files(manifest: PreviewManifest) -> set[Path]:
    return _expected_rendered_files(manifest) | set(_PUBLIC_ASSET_FILES)


def _expected_paths(manifest: PreviewManifest) -> set[Path]:
    paths = set(_expected_files(manifest))
    for file_path in tuple(paths):
        parent = file_path.parent
        while parent != Path("."):
            paths.add(parent)
            parent = parent.parent
    return paths


def _is_symlink_or_reparse(details: os.stat_result) -> bool:
    attributes = getattr(details, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return stat.S_ISLNK(details.st_mode) or bool(attributes & reparse_flag)


def _reject_unsafe_lexical_components(out: Path) -> None:
    absolute = Path(os.path.abspath(out))
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        try:
            details = current.lstat()
        except FileNotFoundError:
            break
        except OSError as error:
            raise ValueError(f"could not inspect generated output path {current}: {error}") from error
        if _is_symlink_or_reparse(details):
            raise ValueError(f"generated output path is a symlink or reparse point: {current}")


def _reject_unsafe_generated_paths(
    out: Path,
    expected_paths: set[Path],
    expected_files: set[Path],
) -> None:
    candidates = (Path("."), *sorted(expected_paths, key=lambda path: (len(path.parts), str(path))))
    for relative in candidates:
        candidate = out if relative == Path(".") else out / relative
        try:
            details = candidate.lstat()
        except FileNotFoundError:
            continue
        except OSError as error:
            raise ValueError(f"could not inspect generated output path {candidate}: {error}") from error
        if _is_symlink_or_reparse(details):
            raise ValueError(f"generated output path is a symlink or reparse point: {candidate}")
        if relative in expected_files:
            if not stat.S_ISREG(details.st_mode) or details.st_nlink != 1:
                raise ValueError(
                    f"generated output leaf must be an unshared regular file: {candidate}"
                )
        elif not stat.S_ISDIR(details.st_mode):
            raise ValueError(f"generated output path is not a directory: {candidate}")


def _reject_unexpected_generated_paths(out: Path, expected_paths: set[Path]) -> None:
    if not out.exists():
        return
    if not out.is_dir():
        raise ValueError(f"generated output path is not a directory: {out}")
    found_paths = {path.relative_to(out) for path in out.rglob("*")}
    unexpected = sorted(str(path) for path in found_paths - expected_paths)
    if unexpected:
        raise ValueError(f"unexpected generated path(s): {', '.join(unexpected)}")


def _validate_rendered_inventory(rendered_pages: dict[Path, str], approved_files: set[Path]) -> None:
    rendered_paths = set(rendered_pages)
    invalid = sorted(
        str(path)
        for path in rendered_paths
        if path.is_absolute() or ".." in path.parts or path not in approved_files
    )
    if invalid:
        raise ValueError(f"rendered destination(s) are not approved: {', '.join(invalid)}")
    if rendered_paths != approved_files:
        missing = sorted(str(path) for path in approved_files - rendered_paths)
        raise ValueError(f"rendered inventory is incomplete: {', '.join(missing)}")


def _read_public_lesson(root: Path, lab_id: str, *, guided: bool = False) -> dict[str, object]:
    track = "foundations" if lab_id.startswith("F") else "practitioner" if lab_id.startswith("P") else ""
    if not track:
        raise ValueError(f"eligible lesson has unsupported lab ID: {lab_id}")
    path = root / "academy" / "tracks" / track / f"{lab_id}.md"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise ValueError(f"could not read eligible lesson {lab_id}: {error}") from error

    lines = text.splitlines()
    if not lines or lines[0] != "---":
        raise ValueError(f"eligible lesson {lab_id} has no frontmatter")
    try:
        end = lines.index("---", 1)
    except ValueError as error:
        raise ValueError(f"eligible lesson {lab_id} has unterminated frontmatter") from error

    metadata: dict[str, str] = {}
    for line in lines[1:end]:
        key, separator, value = line.partition(":")
        if not separator:
            raise ValueError(f"eligible lesson {lab_id} has invalid frontmatter")
        key = key.strip()
        if not key or key in metadata:
            raise ValueError(f"eligible lesson {lab_id} has invalid frontmatter")
        metadata[key] = value.strip()
    missing = [field for field in _FRONTMATTER_FIELDS if not metadata.get(field)]
    if missing:
        raise ValueError(f"eligible lesson {lab_id} is missing public field(s): {', '.join(missing)}")
    if not re.fullmatch(r"[1-9][0-9]{0,2}", metadata["estimated_minutes"]):
        raise ValueError(f"eligible lesson {lab_id} has invalid estimated_minutes")

    action_path = root / "academy" / "actions" / f"{lab_id}.json"
    if guided and action_path.is_file():
        document = _read_markdown_document(
            root,
            path.relative_to(root),
            lab_id,
            require_h1=True,
        )
        content = str(document["content"])
        headings = document["headings"]
        assert isinstance(headings, tuple)
        referenced_actions = document["referenced_actions"]
        assert isinstance(referenced_actions, tuple)
    else:
        content, headings = _render_markdown(lab_id, lines[end + 1 :])
        referenced_actions = ()
    h1 = [title for level, _slug, title in headings if level == 1]
    if len(h1) != 1:
        raise ValueError(f"eligible lesson {lab_id} must contain exactly one public title heading")
    return {
        "heading": h1[0],
        "content": content,
        "headings": headings,
        "referenced_actions": referenced_actions,
        "guided": bool(guided and action_path.is_file()),
        **metadata,
        "estimated_minutes": int(metadata["estimated_minutes"]),
    }


def _read_markdown_document(
    root: Path,
    relative_path: Path,
    document_id: str,
    *,
    require_h1: bool,
) -> dict[str, object]:
    """Read one guided Markdown document and bind every declared action exactly once."""
    if relative_path.is_absolute():
        raise ValueError("guided document path must be relative to the Academy root")
    path = ensure_within(root, root / relative_path)
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as error:
        raise ValueError(f"could not read guided document {document_id}: {error}") from error

    metadata: dict[str, str] = {}
    content_start = 0
    if lines and lines[0] == "---":
        try:
            end = lines.index("---", 1)
        except ValueError as error:
            raise ValueError(f"guided document {document_id} has unterminated frontmatter") from error
        for line in lines[1:end]:
            key, separator, value = line.partition(":")
            key = key.strip()
            if not separator or not key or key in metadata:
                raise ValueError(f"guided document {document_id} has invalid frontmatter")
            metadata[key] = value.strip()
        content_start = end + 1

    manifest = load_action_manifest(root, document_id)
    actions = {action.id: action for action in manifest.actions}
    content, headings, referenced_actions = _render_markdown(
        document_id, lines[content_start:], actions
    )
    h1 = [title for level, _slug, title in headings if level == 1]
    if require_h1 and len(h1) != 1:
        raise ValueError(f"guided document {document_id} must contain exactly one public title heading")
    if not require_h1 and len(h1) > 1:
        raise ValueError(f"guided document {document_id} must not contain multiple public title headings")
    return {
        **metadata,
        "heading": h1[0] if h1 else "",
        "content": content,
        "headings": headings,
        "referenced_actions": referenced_actions,
    }


def _read_optional_guide(root: Path, document_id: str) -> dict[str, object] | None:
    """Activate a guide only when its Markdown and action manifest are both present."""
    guide_path = root / "academy" / "guides" / f"{document_id}.md"
    action_path = root / "academy" / "actions" / f"{document_id}.json"

    def present(path: Path) -> bool:
        try:
            path.lstat()
        except FileNotFoundError:
            return False
        except OSError as error:
            raise ValueError(f"could not inspect guided {document_id} asset: {error}") from error
        return True

    guide_present = present(guide_path)
    action_present = present(action_path)
    if not guide_present and not action_present:
        return None
    if guide_present != action_present:
        raise ValueError(
            f"guided {document_id} guide/action pair must be either both present or both absent"
        )
    return _read_markdown_document(
        root,
        guide_path.relative_to(root),
        document_id,
        require_h1=True,
    )


def _render_inline(lab_id: str, value: str) -> str:
    parts: list[str] = []
    position = 0
    while position < len(value):
        if value.startswith("**", position):
            end = value.find("**", position + 2)
            if end < 0 or end == position + 2:
                raise ValueError(f"eligible lesson {lab_id} contains unsupported Markdown syntax")
            strong = value[position + 2 : end]
            if (
                "`" in strong
                or _RAW_HTML.search(strong)
                or _LINK_OR_IMAGE.search(strong)
                or any(marker in strong for marker in _UNSUPPORTED_INLINE_MARKERS)
            ):
                raise ValueError(f"eligible lesson {lab_id} contains unsupported Markdown syntax")
            parts.append(f"<strong>{escape(strong)}</strong>")
            position = end + 2
            continue
        if value[position] == "`":
            end = value.find("`", position + 1)
            if end < 0 or end == position + 1:
                raise ValueError(f"eligible lesson {lab_id} contains unsupported Markdown syntax")
            parts.append(f"<code>{escape(value[position + 1:end])}</code>")
            position = end + 1
            continue
        if value[position] == "[":
            match = _INLINE_LINK.match(value, position)
            if match is None:
                raise ValueError(f"eligible lesson {lab_id} contains unsupported Markdown syntax")
            label, target = match.groups()
            if (
                target not in _GUIDE_LINK_TARGETS
                or not label.strip()
                or _RAW_HTML.search(label)
                or any(marker in label for marker in _UNSUPPORTED_INLINE_MARKERS)
            ):
                raise ValueError(f"eligible lesson {lab_id} contains unsupported Markdown syntax")
            parts.append(f'<a href="{target}">{escape(label)}</a>')
            position = match.end()
            continue
        next_markers = [
            index
            for index in (value.find("**", position), value.find("`", position), value.find("[", position))
            if index >= 0
        ]
        end = min(next_markers) if next_markers else len(value)
        plain = value[position:end]
        if (
            "`" in plain
            or _RAW_HTML.search(plain)
            or _LINK_OR_IMAGE.search(plain)
            or any(marker in plain for marker in _UNSUPPORTED_INLINE_MARKERS)
        ):
            raise ValueError(f"eligible lesson {lab_id} contains unsupported Markdown syntax")
        parts.append(escape(plain))
        position = end
    return "".join(parts)


def _heading_slug(value: str, used: set[str]) -> str:
    plain = re.sub(r"(?:\*\*|`)", "", value).casefold()
    slug = re.sub(r"[^a-z0-9]+", "-", plain).strip("-") or "section"
    candidate = slug
    counter = 2
    while candidate in used:
        candidate = f"{slug}-{counter}"
        counter += 1
    used.add(candidate)
    return candidate


def _starts_markdown_block(line: str) -> bool:
    return bool(
        _HEADING.fullmatch(line)
        or _ORDERED_ITEM.fullmatch(line)
        or _UNSUPPORTED_BLOCK.match(line)
        or line.startswith(("```", "|", "---", "~~~", "#"))
        or re.fullmatch(r"(?:=+|-+|\*+|_+)", line)
    )


def _table_cells(lab_id: str, line: str) -> tuple[str, str]:
    if not line.startswith("|") or not line.endswith("|"):
        raise ValueError(f"eligible lesson {lab_id} contains unsupported Markdown syntax")
    cells = tuple(cell.strip() for cell in line[1:-1].split("|"))
    if len(cells) != 2 or not all(cells):
        raise ValueError(f"eligible lesson {lab_id} contains unsupported Markdown syntax")
    return cells[0], cells[1]


def _execution_label(action: LessonAction, *, surface: str, host: str, operating_system: str) -> str:
    actor = {"learner": "You", "academy": "Academy", "agent": "Your agent"}[action.actor]
    if surface == "harness":
        surface_label = {
            "claude-code": "Claude Code harness",
            "codex": "Codex harness",
            "pi": "Pi harness",
        }[host]
    else:
        surface_label = {
            "browser": "Browser",
            "native-terminal": "Native terminal",
            "academy-console": "Academy console",
            "active-harness": "Active CodeArbiter harness",
        }[surface]
    os_label = {
        "all": "All operating systems",
        "windows": "Windows",
        "macos": "macOS",
        "linux": "Linux",
    }[operating_system]
    return f"{actor} \u00b7 {surface_label} \u00b7 {os_label}"


def _render_action(action: LessonAction) -> str:
    """Render one validated action without interpreting any manifest prose as markup."""
    action_id = escape(action.id, quote=True)
    blocks = [
        f'<section class="lesson-action" data-action-id="{action_id}" '
        f'aria-labelledby="action-heading-{action_id}">',
        '<header class="lesson-action__header">',
        f'<h2 id="action-heading-{action_id}">{escape(action.title)}</h2>',
        "</header>",
    ]
    if not action.variants:
        assert action.surface is not None
        blocks.append(
            f'<p class="action-role">{escape(_execution_label(action, surface=action.surface, host="none", operating_system="all"))}</p>'
        )
    blocks.append(f'<p class="action-instruction">{escape(action.instruction)}</p>')
    if action.rationale is not None:
        blocks.append(
            f'<div class="action-rationale"><strong>Why</strong><p>{escape(action.rationale)}</p></div>'
        )
    if action.resources:
        links = "".join(
            f'<li><a href="{escape(resource.href, quote=True)}">{escape(resource.label)}</a></li>'
            for resource in action.resources
        )
        blocks.append(
            '<div class="action-resources">'
            f"<p><strong>Reviewed resources for {escape(action.title)}</strong></p>"
            f"<ul>{links}</ul></div>"
        )
    for variant in action.variants:
        variant_id = escape(variant.id, quote=True)
        command_id = f"command-{action_id}-{variant_id}"
        status_id = f"copy-status-{action_id}-{variant_id}"
        blocks.extend(
            (
                f'<div class="command-variant" data-os="{escape(variant.operating_system, quote=True)}" '
                f'data-host="{escape(variant.host, quote=True)}" data-surface="{escape(variant.surface, quote=True)}">',
                f'<p class="action-role">{escape(_execution_label(action, surface=variant.surface, host=variant.host, operating_system=variant.operating_system))}</p>',
                '<div class="command-shell">',
                f'<pre><code id="{command_id}" tabindex="0" class="language-{escape(variant.language, quote=True)}">{escape(variant.command)}</code></pre>',
            )
        )
        if variant.copy:
            blocks.extend(
                (
                    f'<button type="button" class="command-copy" data-copy-target="{command_id}" aria-describedby="{status_id}">Copy</button>',
                    "</div>",
                    f'<p id="{status_id}" class="copy-status" role="status" aria-live="polite"></p>',
                )
            )
        else:
            blocks.append("</div>")
        blocks.append("</div>")
    blocks.extend(
        (
            f'<div class="action-expected"><strong>Expected result</strong><p>{escape(action.expected_result)}</p></div>',
            f'<div class="action-recovery"><strong>If that does not happen</strong><p>{escape(action.recovery)}</p></div>',
        )
    )
    if action.evidence is not None:
        blocks.append(
            f'<div class="action-evidence"><strong>Evidence</strong><p>{escape(action.evidence)}</p></div>'
        )
    blocks.append("</section>")
    return "\n".join(blocks)


def _render_command_preferences(actions: Mapping[str, LessonAction]) -> str:
    variants = tuple(variant for action in actions.values() for variant in action.variants)
    present_os = {variant.operating_system for variant in variants if variant.operating_system != "all"}
    present_hosts = {variant.host for variant in variants if variant.host != "none"}
    groups: list[str] = []
    if present_os:
        os_controls = "".join(
            f'<button type="button" class="academy-os-choice" data-os="{value}" aria-pressed="false">{label}</button>'
            for value, label in (("windows", "Windows"), ("macos", "macOS"), ("linux", "Linux"))
            if value in present_os
        )
        groups.append(
            '<div class="academy-command-preference" role="group" aria-labelledby="academy-os-heading">'
            f'<p id="academy-os-heading">Operating system</p>{os_controls}</div>'
        )
    if present_hosts:
        host_controls = "".join(
            f'<button type="button" class="academy-host-choice" data-host="{value}" aria-pressed="false">{label}</button>'
            for value, label in (("claude-code", "Claude Code"), ("codex", "Codex"), ("pi", "Pi"))
            if value in present_hosts
        )
        groups.append(
            '<div class="academy-command-preference" role="group" aria-labelledby="academy-host-heading">'
            f'<p id="academy-host-heading">CodeArbiter host</p>{host_controls}</div>'
        )
    if not groups:
        return ""
    return (
        '<div class="academy-command-preferences" hidden '
        'aria-labelledby="academy-command-preferences-heading">'
        '<p id="academy-command-preferences-heading"><strong>Choose the commands you use</strong></p>'
        f'{"".join(groups)}</div>'
    )


def _render_markdown(
    lab_id: str,
    lines: list[str],
    actions: Mapping[str, LessonAction] | None = None,
) -> tuple[str, tuple[tuple[int, str, str], ...]] | tuple[
    str, tuple[tuple[int, str, str], ...], tuple[str, ...]
]:
    guided = actions is not None
    action_map = actions or {}
    rendered: list[str] = []
    headings: list[tuple[int, str, str]] = []
    used_slugs: set[str] = set()
    paragraph: list[str] = []
    referenced_actions: list[str] = []
    index = 0

    def flush_paragraph() -> None:
        if paragraph:
            rendered.append(f"<p>{_render_inline(lab_id, ' '.join(paragraph))}</p>")
            paragraph.clear()

    while index < len(lines):
        line = lines[index]
        if not line.strip():
            flush_paragraph()
            index += 1
            continue
        if line != line.lstrip() or line.endswith("  "):
            raise ValueError(f"eligible lesson {lab_id} contains unsupported Markdown syntax")
        action_reference = _ACTION_REFERENCE.fullmatch(line)
        if action_reference:
            flush_paragraph()
            action_id = action_reference.group(1)
            if not guided:
                raise ValueError(f"eligible lesson {lab_id} contains an action reference outside a guided document")
            if action_id not in action_map:
                raise ValueError(f"guided document {lab_id} references unknown action {action_id}")
            if action_id in referenced_actions:
                raise ValueError(f"guided document {lab_id} contains duplicate action reference {action_id}")
            rendered.append(_render_action(action_map[action_id]))
            referenced_actions.append(action_id)
            index += 1
            continue
        if "{{action:" in line:
            raise ValueError(f"guided document {lab_id} action references must be standalone")
        if line.startswith("```"):
            flush_paragraph()
            if guided:
                raise ValueError(f"guided document {lab_id} contains a raw command fence")
            language = line[3:]
            if language not in _FENCE_LANGUAGES:
                raise ValueError(f"eligible lesson {lab_id} contains unsupported Markdown syntax")
            index += 1
            code_lines: list[str] = []
            while index < len(lines) and lines[index] != "```":
                code_lines.append(lines[index])
                index += 1
            if index >= len(lines):
                raise ValueError(f"eligible lesson {lab_id} contains unsupported Markdown syntax")
            rendered.append(
                f'<pre><code class="language-{language}">{escape(chr(10).join(code_lines))}</code></pre>'
            )
            index += 1
            continue
        ordered_item = _ORDERED_ITEM.fullmatch(line)
        if ordered_item:
            flush_paragraph()
            items: list[str] = []
            expected_number = 1
            while index < len(lines):
                item = _ORDERED_ITEM.fullmatch(lines[index])
                if item is None:
                    break
                if int(item.group("number")) != expected_number:
                    raise ValueError(f"eligible lesson {lab_id} contains unsupported Markdown syntax")
                parts = [item.group("body")]
                index += 1
                while index < len(lines) and lines[index].startswith("   "):
                    continuation = lines[index][3:]
                    if (
                        not continuation
                        or continuation.startswith(" ")
                        or _starts_markdown_block(continuation)
                    ):
                        raise ValueError(f"eligible lesson {lab_id} contains unsupported Markdown syntax")
                    parts.append(continuation)
                    index += 1
                items.append(f"<li>{_render_inline(lab_id, ' '.join(parts))}</li>")
                expected_number += 1
            rendered.append(f"<ol>{''.join(items)}</ol>")
            continue
        heading = _HEADING.fullmatch(line)
        if heading:
            flush_paragraph()
            level = len(heading.group(1))
            title = heading.group(2).strip()
            if re.search(r"\s#+$", title):
                raise ValueError(f"eligible lesson {lab_id} contains unsupported Markdown syntax")
            slug = _heading_slug(title, used_slugs)
            rendered.append(f'<h{level} id="{slug}">{_render_inline(lab_id, title)}</h{level}>')
            headings.append((level, slug, re.sub(r"(?:\*\*|`)", "", title)))
            index += 1
            continue
        if line.startswith("|"):
            flush_paragraph()
            if index + 2 >= len(lines) or not _TABLE_DIVIDER.fullmatch(lines[index + 1]):
                raise ValueError(f"eligible lesson {lab_id} contains unsupported Markdown syntax")
            headers = _table_cells(lab_id, line)
            index += 2
            rows: list[tuple[str, str]] = []
            while index < len(lines) and lines[index].startswith("|"):
                rows.append(_table_cells(lab_id, lines[index]))
                index += 1
            if not rows:
                raise ValueError(f"eligible lesson {lab_id} contains unsupported Markdown syntax")
            body = "".join(
                f"<tr><td>{_render_inline(lab_id, left)}</td><td>{_render_inline(lab_id, right)}</td></tr>"
                for left, right in rows
            )
            rendered.append(
                '<div class="table-shell"><table><thead><tr>'
                f"<th>{_render_inline(lab_id, headers[0])}</th><th>{_render_inline(lab_id, headers[1])}</th>"
                f"</tr></thead><tbody>{body}</tbody></table></div>"
            )
            continue
        if _starts_markdown_block(line):
            raise ValueError(f"eligible lesson {lab_id} contains unsupported Markdown syntax")
        paragraph.append(line.strip())
        index += 1
    flush_paragraph()
    if guided:
        expected_actions = tuple(
            action.id for action in sorted(action_map.values(), key=lambda item: item.sequence)
        )
        if tuple(referenced_actions) != expected_actions:
            missing = tuple(action_id for action_id in expected_actions if action_id not in referenced_actions)
            if missing:
                raise ValueError(
                    f"guided document {lab_id} has unreferenced action(s): {', '.join(missing)}"
                )
            raise ValueError(f"guided document {lab_id} action references are out of sequence")
        preferences = _render_command_preferences(action_map)
        if preferences:
            h1_index = next(
                (position for position, block in enumerate(rendered) if block.startswith("<h1")),
                0,
            )
            rendered.insert(h1_index + 1, preferences)
        return "\n".join(rendered), tuple(headings), tuple(referenced_actions)
    return "\n".join(rendered), tuple(headings)


def _render_pages(
    manifest: PreviewManifest,
    lessons: dict[str, dict[str, object]],
    guides: dict[str, dict[str, object] | None],
    templates: dict[str, Template],
    commit: str,
) -> dict[Path, str]:
    available_labs = "\n".join(
        '<li><a href="labs/{id}/index.html">{heading}</a><p>{outcome}</p></li>'.format(
            id=escape(lab_id, quote=True),
            heading=escape(str(lessons[lab_id]["heading"])),
            outcome=escape(str(lessons[lab_id]["outcome"])),
        )
        for lab_id in manifest.available_labs
    )
    coming_next_section = ""
    if manifest.coming_next:
        foundations = tuple(_lab_code(lab_id) for lab_id in manifest.coming_next if lab_id.startswith("F"))
        practitioner = tuple(_lab_code(lab_id) for lab_id in manifest.coming_next if lab_id.startswith("P"))
        groups = []
        if foundations:
            if len(foundations) == 1:
                foundation_sequence = foundations[0]
            elif len(foundations) == 2:
                foundation_sequence = " and ".join(foundations)
            else:
                foundation_sequence = ", ".join(foundations[:-1]) + f", and {foundations[-1]}"
            groups.append(
                "<li><strong>Foundations</strong>: "
                + escape(foundation_sequence)
                + ". Guided rewrites are in progress.</li>"
            )
        if practitioner:
            groups.append(
                "<li><strong>Practitioner</strong>: "
                + escape(f"{practitioner[0]} through {practitioner[-1]}")
                + ". Guided rewrites are in progress.</li>"
            )
        coming_next = "\n".join(groups)
        coming_next_section = (
            "<h2>Coming next</h2>\n"
            "<p>These lessons are not public routes until their guided rewrites and acceptance evidence are complete.</p>\n"
            f'<ul class="coming-next">\n{coming_next}\n</ul>'
        )
    pages: dict[Path, str] = {
        Path("index.html"): _page(
            templates,
            "Arbiter Academy Preview 0.6",
            templates["index"].substitute(
                guide_content=(
                    "" if guides["home"] is None else str(guides["home"]["content"])
                ),
                available_labs=available_labs,
                coming_next_section=coming_next_section,
                discussion_url=escape(manifest.discussion_url, quote=True),
            ),
            root_prefix="",
        ),
        Path("recovery/index.html"): _page(
            templates,
            "Recovery | Arbiter Academy Preview 0.6",
            templates["recovery"].substitute(
                guide_content=(
                    ""
                    if guides["recovery"] is None
                    else str(guides["recovery"]["content"])
                )
            ),
            root_prefix="../",
        ),
        Path("release.json"): json.dumps(
            {
                "release": manifest.release,
                "commit": commit,
                "lesson_contract_version": manifest.lesson_contract_version,
                "catalog_sha256": manifest.catalog_sha256,
                "available_labs": manifest.available_labs,
                "runnable_labs": manifest.runnable_labs,
                "guided_labs": manifest.guided_labs,
                "coming_next": manifest.coming_next,
                "prerequisites": manifest.prerequisites,
                "known_limits": manifest.known_limits,
                "discussion_url": manifest.discussion_url,
            },
            indent=2,
        ) + "\n",
    }
    available = set(manifest.available_labs)
    lab_order = tuple(manifest.available_labs)
    for position, (lab_id, lesson) in enumerate(lessons.items()):
        next_lab = str(lesson["next_lab"])
        if next_lab in available:
            next_step = 'Continue with <a href="../{id}/index.html">{id}</a>.'.format(
                id=escape(next_lab, quote=True)
            )
        else:
            next_step = f"{escape(_lab_code(next_lab))} is not available in Academy Preview 0.6."
        previous_link = ""
        if position:
            previous = lab_order[position - 1]
            previous_link = f'<a rel="prev" href="../{escape(previous, quote=True)}/index.html">\u2190 {escape(_lab_code(previous))}</a>'
        next_link = ""
        if position + 1 < len(lab_order):
            following = lab_order[position + 1]
            next_link = f'<a rel="next" href="../{escape(following, quote=True)}/index.html">{escape(_lab_code(following))} \u2192</a>'
        headings = lesson["headings"]
        assert isinstance(headings, tuple)
        toc = "\n".join(
            f'<li class="lab-toc__level-{level}"><a href="#{escape(slug, quote=True)}">{escape(title)}</a></li>'
            for level, slug, title in headings
            if level in {2, 3}
        )
        track_label = "Foundations" if lab_id.startswith("F") else "Practitioner"
        pages[Path("labs") / lab_id / "index.html"] = _page(
            templates,
            f"{lesson['title']} | Arbiter Academy Preview 0.6",
            templates["lab"].substitute(
                lab_id=escape(lab_id),
                track=track_label,
                minutes=escape(str(lesson.get("estimated_minutes", ""))),
                outcome=escape(str(lesson["outcome"])),
                lesson_status=(
                    "Guided lesson"
                    if lesson["guided"]
                    else "Guided lesson \u00b7 structured rewrite pending"
                    if lab_id in manifest.guided_labs
                    else "Reference lesson \u00b7 guided rewrite pending"
                ),
                lesson_content=str(lesson["content"]),
                toc=toc,
                next_step=next_step,
                previous_link=previous_link,
                next_link=next_link,
            ),
            root_prefix="../../",
        )
    return pages


def _page(
    templates: dict[str, Template],
    title: str,
    body: str,
    *,
    root_prefix: str,
) -> str:
    return templates["base"].substitute(
        title=escape(title),
        body=body,
        home_url=f"{root_prefix}index.html",
        recovery_url=f"{root_prefix}recovery/index.html",
        stylesheet_url=f"{root_prefix}assets/academy.css",
        script_url=f"{root_prefix}assets/academy.js",
        favicon_url=f"{root_prefix}assets/favicon.svg",
        logo_url=f"{root_prefix}assets/logo.svg",
    )


def _lab_code(lab_id: str) -> str:
    return lab_id.partition("-")[0]


def main(arguments: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--release-sha", required=True)
    options = parser.parse_args(arguments)
    build_preview_site(
        _REPOSITORY_ROOT,
        options.output,
        release_sha=options.release_sha,
    )


if __name__ == "__main__":
    main()
