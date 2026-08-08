"""Build the fail-closed static public surface for Academy Preview 0.1."""

from __future__ import annotations

import json
import os
import re
from html import escape
from pathlib import Path
from string import Template

from academy_engine.preview import PreviewManifest, load_preview_manifest


_SHA = re.compile(r"^[0-9a-f]{40}$")
_FRONTMATTER_FIELDS = ("title", "outcome", "next_lab")


def build_preview_site(root: Path, out: Path, *, release_sha: str | None = None) -> None:
    """Render only the reviewed Preview 0.1 pages into *out*.

    All inputs are validated before any page is written so a missing lesson
    cannot leave a partial public site behind.
    """
    manifest = load_preview_manifest(root)
    commit = _validate_release_sha(release_sha)
    templates = _load_templates(root)
    expected_files = _expected_files(manifest)
    expected_paths = _expected_paths(manifest)
    _reject_unexpected_generated_paths(out, expected_paths)

    lessons = {
        lab_id: _read_public_lesson(root, lab_id)
        for lab_id in manifest.available_labs
    }
    rendered_pages = _render_pages(manifest, lessons, templates, commit)
    _validate_rendered_inventory(rendered_pages, expected_files)

    for relative_path, content in rendered_pages.items():
        destination = out / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")


def _validate_release_sha(release_sha: str | None) -> str:
    if not isinstance(release_sha, str) or not _SHA.fullmatch(release_sha):
        raise ValueError("ACADEMY_RELEASE_SHA must be a lowercase 40-character Git commit SHA")
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


def _expected_files(manifest: PreviewManifest) -> set[Path]:
    paths = {Path("index.html"), Path("release.json"), Path("recovery/index.html")}
    for lab_id in manifest.available_labs:
        paths.add(Path("labs") / lab_id / "index.html")
    return paths


def _expected_paths(manifest: PreviewManifest) -> set[Path]:
    return _expected_files(manifest) | {
        Path("labs"),
        Path("recovery"),
        *(Path("labs") / lab_id for lab_id in manifest.available_labs),
    }


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


def _read_public_lesson(root: Path, lab_id: str) -> dict[str, str]:
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
            continue
        metadata[key.strip()] = value.strip()
    missing = [field for field in _FRONTMATTER_FIELDS if not metadata.get(field)]
    if missing:
        raise ValueError(f"eligible lesson {lab_id} is missing public field(s): {', '.join(missing)}")

    heading = next((line[2:].strip() for line in lines[end + 1 :] if line.startswith("# ")), "")
    if not heading:
        raise ValueError(f"eligible lesson {lab_id} is missing a public title heading")
    return {"heading": heading, **{field: metadata[field] for field in _FRONTMATTER_FIELDS}}


def _render_pages(
    manifest: PreviewManifest,
    lessons: dict[str, dict[str, str]],
    templates: dict[str, Template],
    commit: str,
) -> dict[Path, str]:
    available_labs = "\n".join(
        '<li><a href="labs/{id}/index.html">{heading}</a><p>{outcome}</p></li>'.format(
            id=escape(lab_id, quote=True),
            heading=escape(lessons[lab_id]["heading"]),
            outcome=escape(lessons[lab_id]["outcome"]),
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
            ),
        ),
        Path("recovery/index.html"): _page(
            templates,
            "Recovery | Arbiter Academy Preview 0.1",
            templates["recovery"].substitute(),
        ),
        Path("release.json"): json.dumps(
            {"release": manifest.release, "commit": commit},
            indent=2,
        ) + "\n",
    }
    available = set(manifest.available_labs)
    for lab_id, lesson in lessons.items():
        next_lab = lesson["next_lab"]
        if next_lab in available:
            next_step = 'Continue with <a href="../{id}/index.html">{id}</a>.'.format(
                id=escape(next_lab, quote=True)
            )
        else:
            next_step = f"Continue with {escape(_lab_code(next_lab))} when it enters verification."
        pages[Path("labs") / lab_id / "index.html"] = _page(
            templates,
            f"{lesson['title']} | Arbiter Academy Preview 0.1",
            templates["lab"].substitute(
                heading=escape(lesson["heading"]),
                outcome=escape(lesson["outcome"]),
                next_step=next_step,
            ),
        )
    return pages


def _page(templates: dict[str, Template], title: str, body: str) -> str:
    return templates["base"].substitute(title=escape(title), body=body)


def _lab_code(lab_id: str) -> str:
    return lab_id.partition("-")[0]


def main() -> None:
    root = Path(__file__).parents[1]
    build_preview_site(root, root / "site" / "generated", release_sha=os.environ.get("ACADEMY_RELEASE_SHA"))


if __name__ == "__main__":
    main()
