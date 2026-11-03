"""Lesson mechanism sections stay short and point to their canonical codeArbiter page.

The codeArbiter site explains each mechanism once, on a guide or concept page. A lesson's
"Understand the mechanism" section (required by ``academy_engine.curriculum``) is therefore a
short summary plus a link, not a second copy of that page.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
TRACKS = ROOT / "academy" / "tracks"

SECTION = "Understand the mechanism"
MAX_WORDS = 80
SITE = "https://codearbiter.dev/"
DASH_SEPARATORS = (chr(0x2013), chr(0x2014))  # en dash, em dash

# Which codeArbiter page each lesson practices, as the site publishes it.
#
# Source: ``site/src/data/topic-map.json`` on arbiterForge/codeArbiter ``main`` (added by
# efc586d2, #1075), the topic map that the site generator uses to render "Read alongside this
# lesson" links. It is copied here verbatim: page slug -> the lesson IDs that practice it.
# The order of the keys is part of the data. A lesson's canonical page is the first page that
# lists it, and an optional second link may point to the second. When the site's topic map
# changes, paste the new JSON here and the tests below name every lesson that has to follow.
TOPIC_MAP: dict[str, list[str]] = {
    "guides/troubleshooting": ["F01-fork-clone-doctor"],
    "guides/return-to-a-project": ["F02-orient-to-state", "F03-work-the-board", "U05-debug-spike-conflict"],
    "guides/investigate-and-fix": ["F04-fix-with-evidence", "U05-debug-spike-conflict"],
    "guides/feature-lane": ["P01-feature-through-plan", "U07-capstone"],
    "guides/review-artifacts": ["P01-feature-through-plan"],
    "guides/review-and-ship": [
        "P02-commit-review-pr",
        "P07-threat-model",
        "P08-repository-hygiene",
        "U06-preview-and-advanced-surfaces",
    ],
    "guides/recording-adrs": ["P03-record-an-adr"],
    "guides/adding-a-dependency": ["P04-review-a-dependency"],
    "guides/understand-an-existing-project": ["P06-context-drift-recovery", "U04-initialize-projects"],
    "guides/plan-a-new-project": ["U04-initialize-projects"],
    "guides/autonomous-sprints": ["U01-autonomous-sprint"],
    "guides/overriding-a-gate": ["U02-override-audit-metrics"],
    "guides/releasing-a-version": ["U03-refactor-chore-release"],
    "concepts/gated-lanes": ["F03-work-the-board", "U03-refactor-chore-release"],
    "concepts/test-first": ["F04-fix-with-evidence", "P05-checkpoint-remediation"],
    "concepts/checkpoints": ["P05-checkpoint-remediation"],
    "concepts/adrs": ["P03-record-an-adr"],
    "concepts/provenance-drift": ["P06-context-drift-recovery"],
    "concepts/auditability": ["U02-override-audit-metrics"],
}

# A lesson with no mechanism section, and why. U06 is a bounded preview lesson whose eight
# headings are pinned by ``tests.test_lesson_actions.U06_HEADINGS`` and which never had one.
# ``test_exempt_lessons_still_have_no_section`` fails once U06 gains the section, so the
# lesson is then held to every check below instead of staying exempt by accident.
LESSONS_WITHOUT_SECTION = frozenset({"U06-preview-and-advanced-surfaces"})

_HEADING = re.compile(r"(?m)^## ([^\n]+)\n")
_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_INLINE_LINK = re.compile(r"\[([^\]]*)\]\(([^)]*)\)")
_BARE_URL = re.compile(r"https?://\S+")


def canonical_pages() -> dict[str, tuple[str, ...]]:
    """Invert the topic map: lesson ID -> its pages, in the order the map lists them."""
    pages: dict[str, list[str]] = {}
    for slug, lesson_ids in TOPIC_MAP.items():
        for lesson_id in lesson_ids:
            pages.setdefault(lesson_id, []).append(slug)
    return {lesson_id: tuple(slugs) for lesson_id, slugs in pages.items()}


def page_url(slug: str) -> str:
    return f"{SITE}{slug}/"


def lesson_files() -> dict[str, Path]:
    """Every lesson under academy/tracks, keyed by lesson ID. Track index pages are not lessons."""
    return {
        path.stem: path
        for path in sorted(TRACKS.glob("*/*.md"))
        if path.name != "index.md"
    }


def mechanism_section(text: str) -> str | None:
    """The body under the level-two heading, or None when absent.

    Uses the same ``## `` heading rule as ``academy_engine.curriculum._sections``: the body runs
    to the next level-two heading or the end of the file.
    """
    matches = list(_HEADING.finditer(text))
    for index, match in enumerate(matches):
        if match.group(1).strip() != SECTION:
            continue
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        return text[match.end() : end].strip()
    return None


def word_count(section: str) -> int:
    """Count the words a learner reads in a section.

    Counting rules, which the limit below is measured with:
    1. HTML comments are not counted; curriculum.py treats them as not learner-visible.
    2. Each Markdown link ``[text](url)`` counts as its link text. The URL is not counted.
    3. Any other bare http(s) URL is not counted.
    4. What remains is split on whitespace and every piece is one word. Words inside code spans
       count, and emphasis markers stay attached to the word they wrap.
    """
    visible = _COMMENT.sub("", section)
    visible = _INLINE_LINK.sub(lambda match: match.group(1), visible)
    visible = _BARE_URL.sub("", visible)
    return len(visible.split())


def link_targets(section: str) -> list[str]:
    visible = _COMMENT.sub("", section)
    return [match.group(2).strip() for match in _INLINE_LINK.finditer(visible)]


class WordCountRuleTests(unittest.TestCase):
    def test_link_text_counts_and_its_url_does_not(self) -> None:
        """Catches a counter that charges a learner for a URL or ignores link text."""
        section = "Read [the full guide](https://codearbiter.dev/guides/feature-lane/) today."
        self.assertEqual(word_count(section), 5)

    def test_bare_urls_and_comments_are_not_counted(self) -> None:
        """Catches words hidden in comments or bare URLs inflating the count."""
        section = "One two <!-- three four --> https://codearbiter.dev/concepts/checkpoints/ five"
        self.assertEqual(word_count(section), 3)

    def test_code_spans_and_emphasis_count_as_words(self) -> None:
        """Catches a counter that drops inline code or bold text from the total."""
        self.assertEqual(word_count("**Use this.** Run `init --greenfield` now."), 6)

    def test_section_runs_to_the_next_level_two_heading_only(self) -> None:
        """Catches a section that swallows the next heading or stops at a level-three one."""
        text = (
            "## Check\n\nbefore\n\n"
            f"## {SECTION}\n\nfirst\n\n### Detail\n\nsecond\n\n"
            "## Next lab\n\nafter\n"
        )
        self.assertEqual(mechanism_section(text), "first\n\n### Detail\n\nsecond")
        self.assertIsNone(mechanism_section("## Check\n\nonly\n"))


class MechanismLinkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.pages = canonical_pages()
        cls.files = lesson_files()
        cls.sections = {
            lesson_id: mechanism_section(path.read_text(encoding="utf-8"))
            for lesson_id, path in cls.files.items()
        }

    def _linked_lessons(self) -> list[str]:
        return sorted(lesson_id for lesson_id in self.files if lesson_id not in LESSONS_WITHOUT_SECTION)

    def test_topic_map_and_lesson_files_name_the_same_lessons(self) -> None:
        """Catches a lesson with no canonical page, or a mapped lesson that has no file."""
        self.assertEqual(sorted(self.files), sorted(self.pages))

    def test_exempt_lessons_still_have_no_section(self) -> None:
        """Catches an exemption that outlived its reason and now hides a section from the checks."""
        self.assertLessEqual(LESSONS_WITHOUT_SECTION, set(self.files))
        for lesson_id in sorted(LESSONS_WITHOUT_SECTION):
            with self.subTest(lesson=lesson_id):
                self.assertIsNone(
                    self.sections[lesson_id],
                    f"{lesson_id} now has '{SECTION}'; remove it from LESSONS_WITHOUT_SECTION",
                )

    def test_every_lesson_has_the_mechanism_section(self) -> None:
        """Catches a lesson that lost the section academy_engine/curriculum.py requires."""
        for lesson_id in self._linked_lessons():
            with self.subTest(lesson=lesson_id):
                section = self.sections[lesson_id]
                self.assertIsNotNone(section, f"{lesson_id} has no '## {SECTION}' section")
                self.assertTrue(_COMMENT.sub("", section).strip(), f"{lesson_id} section is empty")

    def test_every_section_is_at_most_eighty_words(self) -> None:
        """Catches a mechanism section that grew back into a second copy of the guide."""
        for lesson_id in self._linked_lessons():
            with self.subTest(lesson=lesson_id):
                section = self.sections[lesson_id]
                self.assertIsNotNone(section)
                count = word_count(section)
                self.assertLessEqual(
                    count, MAX_WORDS, f"{lesson_id} has {count} words; the limit is {MAX_WORDS}"
                )

    def test_every_section_links_to_its_canonical_page(self) -> None:
        """Catches a section with no link, a link to the wrong page, or a link that is not a page URL."""
        for lesson_id in self._linked_lessons():
            with self.subTest(lesson=lesson_id):
                section = self.sections[lesson_id]
                self.assertIsNotNone(section)
                slugs = self.pages[lesson_id]
                canonical = page_url(slugs[0])
                allowed = [page_url(slug) for slug in slugs[:2]]
                targets = link_targets(section)
                self.assertIn(canonical, targets, f"{lesson_id} must link to {canonical}")
                self.assertEqual(
                    targets[0], canonical, f"{lesson_id} must link its canonical page first"
                )
                self.assertLessEqual(len(targets), 2, f"{lesson_id} links more than two pages")
                for target in targets:
                    self.assertIn(target, allowed, f"{lesson_id} links {target}, which it does not practice")
                self.assertEqual(len(targets), len(set(targets)), f"{lesson_id} repeats a link")

    def test_sections_use_no_dash_separators(self) -> None:
        """Catches an em or en dash used as a separator in the summary."""
        for lesson_id in self._linked_lessons():
            with self.subTest(lesson=lesson_id):
                section = self.sections[lesson_id]
                self.assertIsNotNone(section)
                for dash in DASH_SEPARATORS:
                    self.assertNotIn(dash, section)


if __name__ == "__main__":
    unittest.main()
