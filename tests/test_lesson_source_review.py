"""Declared producer changes must identify the lessons needing human review."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from academy_engine.catalog import _EXACT_LABS
from scripts import check_lesson_source_review as review


class LessonSourceReviewTests(unittest.TestCase):
    def test_actual_behavior_owners_are_tracked_beyond_command_wrappers(self):
        manifest = json.loads((Path(__file__).parents[1] / "academy/lesson-source-review.json").read_text())
        lessons = {lesson["id"]: lesson["sources"] for lesson in manifest["lessons"]}
        for lab, owner in (
            ("U02-override-audit-metrics", "core/pysrc/_bashguardlib.py"),
            ("U02-override-audit-metrics", "core/pysrc/pre-bash.py"),
            ("P03-record-an-adr", "core/surface/skills/decision-lifecycle/references/authoring.md"),
            ("P07-threat-model", "core/surface/skills/security-architecture/SKILL.md"),
            ("U04-initialize-projects", "core/surface/skills/decision-variance/SKILL.md"),
        ):
            self.assertIn(owner, lessons[lab])
            # A changed owner must mark the lesson even when its wrapper is unchanged.
            data = json.loads(json.dumps(manifest))
            for lesson in data["lessons"]:
                lesson["sources"] = {path: hashlib.sha256(path.encode()).hexdigest() for path in lesson["sources"]}
            drift = review.compare(data, lambda path: b"changed" if path == owner else path.encode())
            self.assertIn(owner, drift[lab])

    def fixture(self):
        digest = hashlib.sha256(b"reviewed command\n").hexdigest()
        return {"schema_version": 1, "source_commit": "a" * 40,
                "lessons": [{"id": lab, "sources": {"core/surface/commands/feature.md": digest}}
                            for lab, _, _ in _EXACT_LABS]}

    def test_changed_source_names_every_affected_lesson(self):
        manifest = self.fixture()
        self.assertEqual(review.compare(manifest, lambda path: b"reviewed command\n"), {})
        drift = review.compare(manifest, lambda path: b"changed command\n")
        self.assertEqual(set(drift), {lab for lab, _, _ in _EXACT_LABS})
        self.assertTrue(all(paths == ["core/surface/commands/feature.md"] for paths in drift.values()))

    def test_missing_source_is_drift_and_unmapped_sources_are_not_read(self):
        seen = []
        def read(path):
            seen.append(path)
            return None
        self.assertEqual(len(review.compare(self.fixture(), read)), 19)
        self.assertEqual(set(seen), {"core/surface/commands/feature.md"})

    def test_incomplete_duplicate_or_unsafe_review_records_are_rejected(self):
        for change in ("missing", "duplicate", "unsafe", "bad-hash", "empty"):
            manifest = self.fixture()
            if change == "missing":
                manifest["lessons"].pop()
            elif change == "duplicate":
                manifest["lessons"][-1] = manifest["lessons"][0]
            else:
                manifest["lessons"][0]["sources"] = ({"../outside": "a" * 64} if change == "unsafe" else
                                                      {"core/surface/commands/feature.md": "invalid"} if change == "bad-hash" else {})
            with self.subTest(change=change), self.assertRaises(ValueError):
                review.compare(manifest, lambda path: b"x")
