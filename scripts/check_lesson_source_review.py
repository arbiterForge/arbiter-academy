"""Identify lessons whose reviewed codeArbiter source dependencies changed.

Hashes detect a need for review; they never establish semantic correctness or
live host qualification. No producer code is imported or executed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from academy_engine.catalog import _EXACT_LABS


def compare(manifest: object, read_source) -> dict[str, list[str]]:
    if (not isinstance(manifest, dict) or set(manifest) != {"schema_version", "source_commit", "lessons"}
            or manifest["schema_version"] != 1 or not re.fullmatch(r"[0-9a-f]{40}", str(manifest["source_commit"]))
            or not isinstance(manifest["lessons"], list)):
        raise ValueError("invalid lesson source review manifest")
    expected = {lab for lab, _, _ in _EXACT_LABS}
    seen = set()
    for lesson in manifest["lessons"]:
        if (not isinstance(lesson, dict) or set(lesson) != {"id", "sources"}
                or not isinstance(lesson["id"], str) or lesson["id"] not in expected or lesson["id"] in seen
                or not isinstance(lesson["sources"], dict) or not lesson["sources"] or len(lesson["sources"]) > 64):
            raise ValueError("lesson source review must cover each lesson exactly once")
        seen.add(lesson["id"])
        for path, digest in lesson["sources"].items():
            if (not re.fullmatch(r"core/(?:surface|pysrc|artifacts)/[A-Za-z0-9_./-]+", path)
                    or any(part in {"", ".", ".."} for part in path.split("/"))
                    or not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest)):
                raise ValueError("unsafe or invalid reviewed source binding")
    if seen != expected:
        raise ValueError("lesson source review is incomplete")
    cache = {}
    drift = {}
    for lesson in manifest["lessons"]:
        for path, expected_digest in lesson["sources"].items():
            if path not in cache:
                raw = read_source(path)
                cache[path] = hashlib.sha256(raw).hexdigest() if raw is not None else None
            if cache[path] != expected_digest:
                drift.setdefault(lesson["id"], []).append(path)
    return drift


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path(__file__).resolve().parents[1] / "academy/lesson-source-review.json")
    parser.add_argument("--codearbiter-root", type=Path, required=True)
    parser.add_argument("--ref", default="origin/main", help="producer ref to compare; defaults to current upstream main")
    args = parser.parse_args(argv)
    try:
        if args.manifest.stat().st_size > (1 << 20):
            raise ValueError("review manifest exceeds size bound")
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        resolved = subprocess.run(["git", "-C", str(args.codearbiter_root), "rev-parse", "--verify", "--end-of-options", args.ref + "^{commit}"], capture_output=True, timeout=20, check=True)
        commit = resolved.stdout.decode("ascii").strip()
        if not re.fullmatch(r"[0-9a-f]{40}", commit):
            raise ValueError("producer ref did not resolve to a commit")
        def read_source(path):
            result = subprocess.run(["git", "-C", str(args.codearbiter_root), "show", commit + ":" + path], capture_output=True, timeout=20, check=False)
            if result.returncode:
                return None
            if len(result.stdout) > (8 << 20):
                raise ValueError("producer source exceeds size bound")
            return result.stdout
        drift = compare(manifest, read_source)
        if drift:
            for lesson, paths in drift.items():
                print(f"REVIEW REQUIRED {lesson}: {', '.join(paths)}")
            return 1
        print(f"All 19 lessons match their declared source dependencies at {commit}; this is a drift check, not semantic or host qualification.")
        return 0
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f"lesson source review could not complete: {type(error).__name__}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
