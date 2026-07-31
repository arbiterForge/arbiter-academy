"""Ticket lifecycle transitions."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from typing import Sequence

from .model import Ticket, TicketStatus


class TicketNotFound(ValueError):
    """Raised when a transition targets an unknown ticket."""


class InvalidTransition(ValueError):
    """Raised when a ticket cannot make the requested lifecycle change."""


def _validate_now(now: datetime) -> None:
    if now.tzinfo is None or now.utcoffset() != timedelta(0):
        raise ValueError("transition time must be UTC")


def _replace_ticket(tickets: Sequence[Ticket], ticket_id: str, replacement: Ticket) -> list[Ticket]:
    return [replacement if ticket.ticket_id == ticket_id else ticket for ticket in tickets]


def claim_ticket(tickets: Sequence[Ticket], ticket_id: str, volunteer: str, now: datetime) -> list[Ticket]:
    _validate_now(now)
    for ticket in tickets:
        if ticket.ticket_id == ticket_id:
            if ticket.status is not TicketStatus.OPEN:
                raise InvalidTransition(f"ticket {ticket_id} is {ticket.status.value} and cannot be claimed")
            if not volunteer.strip():
                raise ValueError("volunteer must be non-empty")
            return _replace_ticket(
                tickets,
                ticket_id,
                replace(ticket, status=TicketStatus.CLAIMED, claimed_by=volunteer, claimed_at=now),
            )
    raise TicketNotFound(f"ticket {ticket_id} was not found")


def complete_ticket(tickets: Sequence[Ticket], ticket_id: str, resolution: str, now: datetime) -> list[Ticket]:
    _validate_now(now)
    for ticket in tickets:
        if ticket.ticket_id == ticket_id:
            if ticket.status is not TicketStatus.CLAIMED:
                raise InvalidTransition(f"ticket {ticket_id} is {ticket.status.value} and cannot be completed")
            if not resolution.strip():
                raise ValueError("resolution must be non-empty")
            return _replace_ticket(
                tickets,
                ticket_id,
                replace(ticket, status=TicketStatus.COMPLETED, completed_at=now, resolution=resolution),
            )
    raise TicketNotFound(f"ticket {ticket_id} was not found")
