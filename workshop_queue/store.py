"""JSON persistence with a bounded, atomic file target."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Sequence

from .model import Ticket, ValidationError


class PathBoundaryError(ValueError):
    """Raised when a store file falls outside its approved data root."""


class MalformedStoreError(ValueError):
    """Raised when a ticket store cannot be interpreted as ticket JSON."""


class JsonTicketStore:
    def __init__(self, path: Path | str, *, allowed_root: Path | str | None = None) -> None:
        self.path = Path(path).resolve()
        root = Path(allowed_root) if allowed_root is not None else self.path.parent
        self.allowed_root = root.resolve()
        try:
            self.path.relative_to(self.allowed_root)
        except ValueError as exc:
            raise PathBoundaryError(f"store path must remain under {self.allowed_root}") from exc

    def load(self) -> list[Ticket]:
        if not self.path.exists():
            return []
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise MalformedStoreError(f"could not read ticket store {self.path}") from exc
        if not isinstance(value, list):
            raise MalformedStoreError("ticket store document must be a list")
        if not all(isinstance(item, dict) for item in value):
            raise MalformedStoreError("ticket store entries must be objects")
        try:
            return [Ticket.from_mapping(item) for item in value]
        except ValidationError as exc:
            raise MalformedStoreError(f"ticket store contains an invalid ticket: {exc}") from exc

    def save(self, tickets: Sequence[Ticket]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.path.with_suffix(self.path.suffix + ".tmp")
        payload = json.dumps(
            [ticket.to_mapping() for ticket in tickets],
            indent=2,
            sort_keys=True,
        ) + "\n"
        try:
            with temporary_path.open("w", encoding="utf-8", newline="\n") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, self.path)
        except OSError:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise
