"""Command-line interface for the Workshop Queue."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from .model import Ticket, TicketStatus
from .service import InvalidTransition, TicketNotFound, claim_ticket, complete_ticket
from .store import JsonTicketStore, MalformedStoreError, PathBoundaryError, StoreWriteError


def _default_data_file() -> Path:
    return Path(__file__).resolve().parent.parent / "data" / "tickets.json"


def _project_data_root() -> Path:
    return Path(__file__).resolve().parent.parent / "data"


def _resolve_data_file(value: Path, data_root: Path) -> Path:
    return value if value.is_absolute() else data_root / value


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="workshop-queue")
    parser.add_argument("--data-file", type=Path, default=_default_data_file())
    commands = parser.add_subparsers(dest="command", required=True)

    list_parser = commands.add_parser("list", help="list tickets")
    list_parser.add_argument("--format", choices=("text", "json"), default="text")

    claim_parser = commands.add_parser("claim", help="claim an open ticket")
    claim_parser.add_argument("ticket_id")
    claim_parser.add_argument("--volunteer", required=True)

    complete_parser = commands.add_parser("complete", help="complete a claimed ticket")
    complete_parser.add_argument("ticket_id")
    complete_parser.add_argument("--resolution", required=True)

    report_parser = commands.add_parser("report", help="summarize tickets by status")
    report_parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def _write_tickets(tickets: Sequence[Ticket], output_format: str) -> None:
    if output_format == "json":
        print(json.dumps([ticket.to_mapping() for ticket in tickets], indent=2, sort_keys=True))
        return
    for ticket in tickets:
        print(f"{ticket.ticket_id} [{ticket.status.value}] {ticket.title}")


def _write_report(tickets: Sequence[Ticket], output_format: str) -> None:
    counts = {status.value: sum(ticket.status is status for ticket in tickets) for status in TicketStatus}
    if output_format == "json":
        print(json.dumps(counts, sort_keys=True))
        return
    for status in TicketStatus:
        print(f"{status.value}: {counts[status.value]}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    try:
        arguments = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code)

    try:
        data_root = _project_data_root()
        data_file = _resolve_data_file(arguments.data_file, data_root)
        store = JsonTicketStore(data_file, allowed_root=data_root)
        tickets = store.load()
        if arguments.command == "list":
            _write_tickets(tickets, arguments.format)
        elif arguments.command == "claim":
            store.save(claim_ticket(tickets, arguments.ticket_id, arguments.volunteer, datetime.now(timezone.utc)))
        elif arguments.command == "complete":
            store.save(complete_ticket(tickets, arguments.ticket_id, arguments.resolution, datetime.now(timezone.utc)))
        elif arguments.command == "report":
            _write_report(tickets, arguments.format)
        return 0
    except (InvalidTransition, TicketNotFound, MalformedStoreError, PathBoundaryError, StoreWriteError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
