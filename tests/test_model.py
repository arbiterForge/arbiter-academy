from __future__ import annotations

import unittest
from datetime import datetime, timezone

from workshop_queue.model import Ticket, TicketStatus, ValidationError


class TicketModelTests(unittest.TestCase):
    def test_from_mapping_parses_a_valid_open_ticket(self) -> None:
        ticket = Ticket.from_mapping(
            {
                "id": "RQ-104",
                "title": "Set up projector",
                "description": "Room A",
                "status": "open",
                "created_at": "2026-07-30T10:00:00Z",
                "claimed_by": None,
                "claimed_at": None,
                "completed_at": None,
                "resolution": None,
            }
        )

        self.assertEqual(ticket.ticket_id, "RQ-104")
        self.assertEqual(ticket.status, TicketStatus.OPEN)
        self.assertEqual(ticket.created_at, datetime(2026, 7, 30, 10, 0, tzinfo=timezone.utc))

    def test_from_mapping_rejects_non_utc_timestamps(self) -> None:
        with self.assertRaisesRegex(ValidationError, "UTC"):
            Ticket.from_mapping(
                {
                    "id": "RQ-104",
                    "title": "Set up projector",
                    "description": "Room A",
                    "status": "open",
                    "created_at": "2026-07-30T10:00:00+01:00",
                    "claimed_by": None,
                    "claimed_at": None,
                    "completed_at": None,
                    "resolution": None,
                }
            )

    def test_from_mapping_rejects_a_non_string_description(self) -> None:
        with self.assertRaisesRegex(ValidationError, "description"):
            Ticket.from_mapping(
                {
                    "id": "RQ-104",
                    "title": "Set up projector",
                    "description": 42,
                    "status": "open",
                    "created_at": "2026-07-30T10:00:00Z",
                    "claimed_by": None,
                    "claimed_at": None,
                    "completed_at": None,
                    "resolution": None,
                }
            )

    def test_ticket_is_immutable(self) -> None:
        ticket = Ticket.from_mapping(
            {
                "id": "RQ-104",
                "title": "Set up projector",
                "description": "Room A",
                "status": "open",
                "created_at": "2026-07-30T10:00:00Z",
                "claimed_by": None,
                "claimed_at": None,
                "completed_at": None,
                "resolution": None,
            }
        )

        with self.assertRaisesRegex(AttributeError, "cannot assign"):
            ticket.status = TicketStatus.CLAIMED  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()
