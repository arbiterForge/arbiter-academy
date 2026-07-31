"""Immutable Workshop Queue domain objects."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Mapping


class ValidationError(ValueError):
    """Raised when a ticket mapping does not meet the domain contract."""


class TicketStatus(str, Enum):
    OPEN = "open"
    CLAIMED = "claimed"
    COMPLETED = "completed"


def _parse_utc_timestamp(value: object, field_name: str) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValidationError(f"{field_name} must be a UTC ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValidationError(f"{field_name} must be a UTC ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ValidationError(f"{field_name} must be a UTC ISO-8601 timestamp")
    return parsed.astimezone(timezone.utc)


def _required_string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{field_name} must be a non-empty string")
    return value


@dataclass(frozen=True, slots=True)
class Ticket:
    ticket_id: str
    title: str
    description: str
    status: TicketStatus
    created_at: datetime
    claimed_by: str | None = None
    claimed_at: datetime | None = None
    completed_at: datetime | None = None
    resolution: str | None = None

    def __post_init__(self) -> None:
        _required_string(self.ticket_id, "id")
        _required_string(self.title, "title")
        if not isinstance(self.description, str):
            raise ValidationError("description must be a string")
        if not isinstance(self.status, TicketStatus):
            raise ValidationError("status must be a known ticket status")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() != timedelta(0):
            raise ValidationError("created_at must be a UTC ISO-8601 timestamp")
        for field_name in ("claimed_at", "completed_at"):
            value = getattr(self, field_name)
            if value is not None and (value.tzinfo is None or value.utcoffset() != timedelta(0)):
                raise ValidationError(f"{field_name} must be a UTC ISO-8601 timestamp")
        if self.claimed_by is not None:
            _required_string(self.claimed_by, "claimed_by")
        if self.resolution is not None:
            _required_string(self.resolution, "resolution")
        if self.status is TicketStatus.OPEN and any(
            value is not None for value in (self.claimed_by, self.claimed_at, self.completed_at, self.resolution)
        ):
            raise ValidationError("open tickets cannot have lifecycle metadata")
        if self.status is TicketStatus.CLAIMED and (self.claimed_by is None or self.claimed_at is None):
            raise ValidationError("claimed tickets require attribution and timestamp")
        if self.status is TicketStatus.CLAIMED and any(value is not None for value in (self.completed_at, self.resolution)):
            raise ValidationError("claimed tickets cannot have completion metadata")
        if self.status is TicketStatus.COMPLETED and any(
            value is None for value in (self.claimed_by, self.claimed_at, self.completed_at, self.resolution)
        ):
            raise ValidationError("completed tickets require claim and resolution metadata")

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> "Ticket":
        try:
            status = TicketStatus(value["status"])
        except (KeyError, ValueError) as exc:
            raise ValidationError("status must be a known ticket status") from exc
        created_at = _parse_utc_timestamp(value.get("created_at"), "created_at")
        if created_at is None:
            raise ValidationError("created_at must be a UTC ISO-8601 timestamp")
        return cls(
            ticket_id=_required_string(value.get("id"), "id"),
            title=_required_string(value.get("title"), "title"),
            description=value.get("description", ""),
            status=status,
            created_at=created_at,
            claimed_by=value.get("claimed_by"),
            claimed_at=_parse_utc_timestamp(value.get("claimed_at"), "claimed_at"),
            completed_at=_parse_utc_timestamp(value.get("completed_at"), "completed_at"),
            resolution=value.get("resolution"),
        )

    def to_mapping(self) -> dict[str, object]:
        result = asdict(self)
        result["id"] = result.pop("ticket_id")
        result["status"] = self.status.value
        for field_name in ("created_at", "claimed_at", "completed_at"):
            value = getattr(self, field_name)
            result[field_name] = value.isoformat().replace("+00:00", "Z") if value else None
        return result
