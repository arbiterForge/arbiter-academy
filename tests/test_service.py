from __future__ import annotations

import unittest
from datetime import datetime, timezone

from workshop_queue.model import Ticket, TicketStatus
from workshop_queue.service import InvalidTransition, TicketNotFound, claim_ticket, complete_ticket


def fixed_now() -> datetime:
    return datetime(2026, 7, 30, 12, 0, tzinfo=timezone.utc)


def open_ticket(ticket_id: str) -> Ticket:
    return Ticket(
        ticket_id=ticket_id,
        title="Set up projector",
        description="Room A",
        status=TicketStatus.OPEN,
        created_at=datetime(2026, 7, 30, 10, 0, tzinfo=timezone.utc),
    )


def completed_ticket(ticket_id: str) -> Ticket:
    return Ticket(
        ticket_id=ticket_id,
        title="Set up projector",
        description="Room A",
        status=TicketStatus.COMPLETED,
        created_at=datetime(2026, 7, 30, 10, 0, tzinfo=timezone.utc),
        claimed_by="Pat",
        claimed_at=datetime(2026, 7, 30, 11, 0, tzinfo=timezone.utc),
        completed_at=datetime(2026, 7, 30, 11, 30, tzinfo=timezone.utc),
        resolution="Done",
    )


class TicketTransitionTests(unittest.TestCase):
    def test_claim_moves_an_open_ticket_to_claimed_with_attribution(self) -> None:
        original = open_ticket("RQ-104")
        updated = claim_ticket([original], "RQ-104", "Sam", fixed_now())

        self.assertEqual(updated[0].status, TicketStatus.CLAIMED)
        self.assertEqual(updated[0].claimed_by, "Sam")
        self.assertEqual(updated[0].claimed_at, fixed_now())
        self.assertEqual(original.status, TicketStatus.OPEN)
        self.assertIsNot(updated[0], original)

    def test_completed_ticket_cannot_be_claimed_again(self) -> None:
        with self.assertRaisesRegex(InvalidTransition, "completed"):
            claim_ticket([completed_ticket("RQ-104")], "RQ-104", "Sam", fixed_now())

    def test_claim_rejects_control_characters_in_volunteer_label(self) -> None:
        for volunteer in ("Sam\nAdmin", "Sam\tAdmin", "Sam\x7fAdmin"):
            with self.subTest(volunteer=repr(volunteer)):
                with self.assertRaisesRegex(ValueError, "control characters"):
                    claim_ticket([open_ticket("RQ-104")], "RQ-104", volunteer, fixed_now())

        claimed = claim_ticket([open_ticket("RQ-104")], "RQ-104", "Sam Allen", fixed_now())
        self.assertEqual(claimed[0].claimed_by, "Sam Allen")

    def test_complete_requires_a_claimed_ticket_and_records_resolution(self) -> None:
        claimed = claim_ticket([open_ticket("RQ-104")], "RQ-104", "Sam", fixed_now())
        completed_at = datetime(2026, 7, 30, 12, 5, tzinfo=timezone.utc)

        updated = complete_ticket(claimed, "RQ-104", "Projector is ready", completed_at)

        self.assertEqual(updated[0].status, TicketStatus.COMPLETED)
        self.assertEqual(updated[0].resolution, "Projector is ready")
        self.assertEqual(updated[0].completed_at, completed_at)
        self.assertEqual(claimed[0].status, TicketStatus.CLAIMED)

    def test_transition_rejects_unknown_ticket(self) -> None:
        with self.assertRaisesRegex(TicketNotFound, "RQ-999"):
            claim_ticket([open_ticket("RQ-104")], "RQ-999", "Sam", fixed_now())


if __name__ == "__main__":
    unittest.main()
