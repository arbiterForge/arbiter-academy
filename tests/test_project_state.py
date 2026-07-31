"""Integrity checks for Arbiter Academy's pre-staged governance fixture."""

from __future__ import annotations

import re
import unittest
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from workshop_queue.model import Ticket, TicketStatus
from workshop_queue.service import claim_ticket


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
    "decisions/decision-log.md",
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


def frontmatter_fields(document: Path) -> dict[str, str]:
    text = document.read_text(encoding="utf-8")
    frontmatter = re.match(r"^---\n(?P<body>.*?)\n---", text, re.DOTALL)
    if not frontmatter:
        raise ValueError(f"{document} has no closed frontmatter")
    return dict(
        line.split(": ", 1)
        for line in frontmatter.group("body").splitlines()
        if ": " in line
    )


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
            r"(?s)- \[~\] academy\.fixture\.0002 .*?"
            r"  - Scenario: deliberate Academy hygiene fixture; stale by design for the hygiene lab\.",
        )
        self.assertNotIn("academy.hygiene.0002", board)
        self.assertNotIn("[CONFIRM-", (STATE_ROOT / "open-questions.md").read_text(encoding="utf-8"))

    def test_accepted_decisions_and_log_are_sequential_and_user_attributed(self):
        decisions = sorted((STATE_ROOT / "decisions").glob("[0-9][0-9][0-9][0-9]-*.md"))
        self.assertEqual([path.name[:4] for path in decisions], ["0001", "0002"])
        for path in decisions:
            fields = frontmatter_fields(path)
            self.assertEqual(fields.get("status"), "accepted", path)
            self.assertEqual(fields.get("decided-by"), "SUaDtL", path)
            self.assertIn("## Status\nAccepted", path.read_text(encoding="utf-8"), path)

        decision_log = (STATE_ROOT / "decisions/decision-log.md").read_text(encoding="utf-8")
        entries = re.findall(r"(?ms)^## DECISION-(\d{4}) .*?(?=^---$|\Z)", decision_log)
        self.assertEqual(entries, ["0001", "0002"])
        self.assertEqual(decision_log.count("**Decided by:** SUaDtL"), 2)

    def test_completed_plan_item_exercises_real_claim_lifecycle(self):
        plan = (STATE_ROOT / "plans/ticket-assignment.md").read_text(encoding="utf-8")
        self.assertRegex(plan, r"\| A-01 \|.*claim_ticket.*\|.*done fixture \|")

        original = Ticket(
            ticket_id="academy-claim-1",
            title="Claim contract",
            description="Fixture proof",
            status=TicketStatus.OPEN,
            created_at=datetime(2026, 7, 30, tzinfo=timezone.utc),
        )
        claimed = claim_ticket(
            [original],
            "academy-claim-1",
            "Academy Volunteer",
            datetime(2026, 7, 30, 12, 0, tzinfo=timezone.utc),
        )[0]

        self.assertIs(original.status, TicketStatus.OPEN)
        self.assertIs(claimed.status, TicketStatus.CLAIMED)
        self.assertEqual(claimed.claimed_by, "Academy Volunteer")
        self.assertIsNotNone(claimed.claimed_at)

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

    def test_append_only_fixture_logs_end_with_lf_and_can_accept_a_new_record(self):
        for relative in (
            "gate-events.log",
            "overrides.log",
            "sprint-log.md",
            "decisions/decision-log.md",
        ):
            raw = (STATE_ROOT / relative).read_bytes()
            self.assertTrue(raw.endswith(b"\n"), relative)
            simulated_append = raw + b"[fixture next-record]\n"
            self.assertEqual(simulated_append.splitlines()[-2], raw.splitlines()[-1], relative)
            self.assertEqual(simulated_append.splitlines()[-1], b"[fixture next-record]", relative)

    def test_no_marker_files_are_present(self):
        markers = STATE_ROOT / ".markers"
        if markers.exists():
            self.assertEqual([path for path in markers.rglob("*") if path.is_file()], [])


if __name__ == "__main__":
    unittest.main()
