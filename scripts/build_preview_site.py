"""Build the fail-closed static public surface for Academy Preview 0.1."""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import sys
from html import escape
from pathlib import Path
from string import Template

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(_REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPOSITORY_ROOT))

from academy_engine.preview import PreviewManifest, load_preview_manifest


_SHA = re.compile(r"^[0-9a-f]{40}$")
_FRONTMATTER_FIELDS = ("title", "outcome", "estimated_minutes", "next_lab")
_FENCE_LANGUAGES = {"powershell", "text", "sh", "json"}
_HEADING = re.compile(r"^(#{1,3}) ([^#].*)$")
_TABLE_DIVIDER = re.compile(r"^\|\s*:?-{3,}:?\s*\|\s*:?-{3,}:?\s*\|$")
_UNSUPPORTED_BLOCK = re.compile(r"^(?:[-+*]\s|\d+[.)]\s|>|#{4,}\s|<)")
_RAW_HTML = re.compile(r"(?:</?[A-Za-z][^>]*>|<!--.*?-->)")
_LINK_OR_IMAGE = re.compile(r"!?\[[^\]]*\]\([^)]*\)")
_UNSUPPORTED_INLINE_MARKERS = ("*", "_", "[", "]", "\\", "~")
_PUBLIC_ASSET_FILES = (
    Path("assets/academy.css"),
    Path("assets/favicon.svg"),
    Path("assets/fonts/jetbrains-mono-latin-wght-normal.woff2"),
    Path("assets/fonts/manrope-latin-wght-normal.woff2"),
    Path("assets/gate-mark.svg"),
    Path("assets/hero-gates.webp"),
    Path("assets/logo.svg"),
)


def build_preview_site(root: Path, out: Path, *, release_sha: str | None = None) -> None:
    """Render only the reviewed Preview 0.1 pages into *out*.

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

    lessons = {
        lab_id: _read_public_lesson(root, lab_id)
        for lab_id in manifest.available_labs
    }
    rendered_pages = _render_pages(manifest, lessons, templates, commit)
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


def _read_public_lesson(root: Path, lab_id: str) -> dict[str, object]:
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

    content, headings = _render_markdown(lab_id, lines[end + 1 :])
    h1 = [title for level, _slug, title in headings if level == 1]
    if len(h1) != 1:
        raise ValueError(f"eligible lesson {lab_id} must contain exactly one public title heading")
    return {
        "heading": h1[0],
        "content": content,
        "headings": headings,
        **metadata,
        "estimated_minutes": int(metadata["estimated_minutes"]),
    }


def _render_inline(lab_id: str, value: str) -> str:
    if _RAW_HTML.search(value) or _LINK_OR_IMAGE.search(value):
        raise ValueError(f"eligible lesson {lab_id} contains unsupported Markdown syntax")
    parts: list[str] = []
    position = 0
    while position < len(value):
        if value.startswith("**", position):
            end = value.find("**", position + 2)
            if end < 0 or end == position + 2:
                raise ValueError(f"eligible lesson {lab_id} contains unsupported Markdown syntax")
            strong = value[position + 2 : end]
            if "`" in strong or any(marker in strong for marker in _UNSUPPORTED_INLINE_MARKERS):
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
        next_markers = [index for index in (value.find("**", position), value.find("`", position)) if index >= 0]
        end = min(next_markers) if next_markers else len(value)
        plain = value[position:end]
        if "`" in plain or any(marker in plain for marker in _UNSUPPORTED_INLINE_MARKERS):
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


def _table_cells(lab_id: str, line: str) -> tuple[str, str]:
    if not line.startswith("|") or not line.endswith("|"):
        raise ValueError(f"eligible lesson {lab_id} contains unsupported Markdown syntax")
    cells = tuple(cell.strip() for cell in line[1:-1].split("|"))
    if len(cells) != 2 or not all(cells):
        raise ValueError(f"eligible lesson {lab_id} contains unsupported Markdown syntax")
    return cells[0], cells[1]


def _render_markdown(
    lab_id: str, lines: list[str]
) -> tuple[str, tuple[tuple[int, str, str], ...]]:
    rendered: list[str] = []
    headings: list[tuple[int, str, str]] = []
    used_slugs: set[str] = set()
    paragraph: list[str] = []
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
        if line.startswith("```"):
            flush_paragraph()
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
        if (
            _UNSUPPORTED_BLOCK.match(line)
            or line.startswith(("---", "~~~", "#"))
            or re.fullmatch(r"(?:=+|-+|\*+|_+)", line)
        ):
            raise ValueError(f"eligible lesson {lab_id} contains unsupported Markdown syntax")
        paragraph.append(line.strip())
        index += 1
    flush_paragraph()
    return "\n".join(rendered), tuple(headings)


def _render_pages(
    manifest: PreviewManifest,
    lessons: dict[str, dict[str, object]],
    templates: dict[str, Template],
    commit: str,
) -> dict[Path, str]:
    durations = [int(lessons[lab_id]["estimated_minutes"]) for lab_id in manifest.available_labs]
    available_labs = "\n".join(
        '<li><a href="labs/{id}/index.html">{heading}</a><p>{outcome}</p></li>'.format(
            id=escape(lab_id, quote=True),
            heading=escape(str(lessons[lab_id]["heading"])),
            outcome=escape(str(lessons[lab_id]["outcome"])),
        )
        for lab_id in manifest.available_labs
    )
    coming_next = "\n".join(
        f"<li>{escape(_lab_code(lab_id))} \u2014 in verification</li>" for lab_id in manifest.coming_next
    )
    pages: dict[Path, str] = {
        Path("index.html"): _page(
            templates,
            "Arbiter Academy Preview 0.1",
            templates["index"].substitute(
                available_labs=available_labs,
                coming_next=coming_next,
                discussion_url=escape(manifest.discussion_url, quote=True),
                minimum_minutes=min(durations),
                maximum_minutes=max(durations),
            ),
            root_prefix="",
        ),
        Path("recovery/index.html"): _page(
            templates,
            "Recovery | Arbiter Academy Preview 0.1",
            templates["recovery"].substitute(),
            root_prefix="../",
        ),
        Path("release.json"): json.dumps(
            {"release": manifest.release, "commit": commit},
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
            next_step = f"Continue with {escape(_lab_code(next_lab))} when it enters verification."
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
            f"{lesson['title']} | Arbiter Academy Preview 0.1",
            templates["lab"].substitute(
                lab_id=escape(lab_id),
                track=track_label,
                minutes=escape(str(lesson.get("estimated_minutes", ""))),
                outcome=escape(str(lesson["outcome"])),
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
