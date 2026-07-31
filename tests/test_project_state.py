"""Integrity checks for Arbiter Academy's pre-staged governance fixture."""

from __future__ import annotations

import re
import unittest
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
STATE_ROOT = REPO_ROOT / ".codearbiter"


REQUIRED_FILES = {
    "CONTEXT.md",
    "coding-standards.md",
    "tech-stack.md",
    "security-controls.md",
    "open-tasks.md",
    "open-questions.md",
    "sprint-log.md",
    "overrides.log",
    "gate-events.log",
    "decisions/0001-json-storage-boundary.md",
    "decisions/0002-explicit-ticket-state-machine.md",
    "specs/ticket-assignment.md",
    "plans/ticket-assignment.md",
    "checkpoints/2026-07-20-baseline.md",
    "reports/2026-07-20-baseline/summary.md",
}


@dataclass(frozen=True)
class AcademyState:
    """Parsed, learner-facing facts from the Academy fixture."""

    stage: int
    initialized: bool
    root: Path

    @classmethod
    def load(cls, root: Path) -> "AcademyState":
        context = (root / "CONTEXT.md").read_text(encoding="utf-8")
        frontmatter = re.match(r"^---\n(?P<body>.*?)\n---", context, re.DOTALL)
        if not frontmatter:
            raise ValueError("CONTEXT.md has no closed frontmatter")
        fields = dict(
            line.split(": ", 1)
            for line in frontmatter.group("body").splitlines()
            if ": " in line
        )
        if fields.get("arbiter") != "enabled":
            raise ValueError("arbiter is not enabled")
        return cls(
            stage=int(fields["stage"]),
            initialized="<!--INITIALIZED-->" in context,
            root=root,
        )

    def unresolved_references(self) -> list[str]:
        unresolved: list[str] = []
        for document in self.root.rglob("*.md"):
            text = document.read_text(encoding="utf-8")
            for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", text):
                if target.startswith(("#", "http://", "https://")):
                    continue
                candidate = (document.parent / target).resolve()
                try:
                    candidate.relative_to(self.root.resolve())
                except ValueError:
                    unresolved.append(f"{document.relative_to(self.root)} -> {target}")
                    continue
                if not candidate.is_file():
                    unresolved.append(f"{document.relative_to(self.root)} -> {target}")
        return unresolved


def load_training_lane_labels() -> list[str]:
    board = (STATE_ROOT / "open-tasks.md").read_text(encoding="utf-8")
    return re.findall(r"^  - Curriculum lane: ([a-z]+)$", board, re.MULTILINE)


class ProjectStateTests(unittest.TestCase):
    def test_project_state_is_initialized_and_cross_references_are_resolvable(self):
        state = AcademyState.load(STATE_ROOT)

        self.assertEqual(state.stage, 2)
        self.assertTrue(state.initialized)
        self.assertEqual(state.unresolved_references(), [])
        self.assertEqual(
            {path.relative_to(STATE_ROOT).as_posix() for path in STATE_ROOT.rglob("*") if path.is_file()}
            & REQUIRED_FILES,
            REQUIRED_FILES,
        )

    def test_task_board_contains_each_curriculum_lane(self):
        required = {"feature", "fix", "decision", "dependency", "security", "release"}
        self.assertTrue(required <= set(load_training_lane_labels()))

    def test_task_board_models_lifecycle_and_hygiene_fixture(self):
        board = (STATE_ROOT / "open-tasks.md").read_text(encoding="utf-8")

        self.assertEqual(set(re.findall(r"^- \[([ ~x])\] ", board, re.MULTILINE)), {" ", "~", "x"})
        self.assertRegex(
            board,
            r"(?s)- \[~\] academy\.hygiene\.0002 .*?"
            r"  - Scenario: deliberate Academy hygiene fixture; stale by design for the hygiene lab\.",
        )
        self.assertNotIn("[CONFIRM-", (STATE_ROOT / "open-questions.md").read_text(encoding="utf-8"))

    def test_fixture_evidence_chain_uses_the_recorded_decision_date(self):
        for path in (
            "specs/ticket-assignment.md",
            "plans/ticket-assignment.md",
            "checkpoints/2026-07-20-baseline.md",
            "reports/2026-07-20-baseline/summary.md",
        ):
            self.assertRegex(
                (STATE_ROOT / path).read_text(encoding="utf-8"),
                r"Recorded:\s+2026-07-30 \(fictional Academy fixture\)",
                path,
            )

        board = (STATE_ROOT / "open-tasks.md").read_text(encoding="utf-8")
        self.assertIn("academy.decision.0005 - Record explicit assignment lifecycle (done 2026-07-30)", board)
        self.assertIn("status: accepted", (STATE_ROOT / "decisions/0001-json-storage-boundary.md").read_text(encoding="utf-8"))
        self.assertIn("decided-by: SUaDtL", (STATE_ROOT / "decisions/0002-explicit-ticket-state-machine.md").read_text(encoding="utf-8"))

    def test_historical_records_are_explicit_fixtures_and_utf8_without_bom(self):
        for path in STATE_ROOT.rglob("*"):
            if not path.is_file():
                continue
            raw = path.read_bytes()
            self.assertFalse(raw.startswith(b"\xef\xbb\xbf"), path)
            raw.decode("utf-8")

        logs = {
            name: (STATE_ROOT / name).read_text(encoding="utf-8")
            for name in ("sprint-log.md", "overrides.log", "gate-events.log")
        }
        for name, text in logs.items():
            self.assertIn("Historical records below are fictional Academy fixtures.", text, name)
        self.assertRegex(logs["sprint-log.md"], r"## SD-01 .* confidence: high")
        self.assertRegex(
            logs["overrides.log"],
            r"(?m)^\[2026-07-20T09:15:00Z\] \| BY: Academy Facilitator \| GATE: H-05",
        )
        self.assertRegex(
            logs["gate-events.log"],
            r"(?m)^\[2026-07-20T09:20:00Z\] REMIND \[H-12\] host=academy hook=fixture.py \|",
        )


if __name__ == "__main__":
    unittest.main()
