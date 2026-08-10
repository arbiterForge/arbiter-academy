from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from workshop_queue.model import Ticket, TicketStatus
from workshop_queue.store import JsonTicketStore, MalformedStoreError, PathBoundaryError, StoreWriteError


def open_ticket(ticket_id: str) -> Ticket:
    return Ticket(
        ticket_id=ticket_id,
        title="Set up projector",
        description="Room A",
        status=TicketStatus.OPEN,
        created_at=datetime(2026, 7, 30, 10, 0, tzinfo=timezone.utc),
    )


class JsonTicketStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary_directory.name)
        self.data_root = self.base / "data"
        self.data_root.mkdir()
        self.path = self.data_root / "tickets.json"
        self.outside_path = self.base / "outside.json"

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_save_replaces_json_atomically(self) -> None:
        store = JsonTicketStore(self.path, allowed_root=self.data_root)

        store.save([open_ticket("RQ-104")])

        self.assertEqual(JsonTicketStore(self.path, allowed_root=self.data_root).load()[0].ticket_id, "RQ-104")
        self.assertFalse(self.path.with_suffix(".json.tmp").exists())

    def test_save_wraps_replace_failure_and_preserves_the_original(self) -> None:
        original = b'{"original": true}\n'
        self.path.write_bytes(original)

        def reject_replace(source: Path, destination: Path) -> None:
            raise PermissionError("injected replacement failure")

        store = JsonTicketStore(self.path, allowed_root=self.data_root, replace=reject_replace)

        with self.assertRaisesRegex(StoreWriteError, "could not save ticket store"):
            store.save([open_ticket("RQ-104")])

        self.assertEqual(self.path.read_bytes(), original)
        self.assertFalse(self.path.with_suffix(".json.tmp").exists())

    def test_store_rejects_a_path_outside_the_project_data_root(self) -> None:
        with self.assertRaises(PathBoundaryError):
            JsonTicketStore(self.outside_path, allowed_root=self.data_root)

    def test_malformed_input_raises_without_rewriting_the_source(self) -> None:
        malformed = '{"tickets": [not valid json]}'
        self.path.write_text(malformed, encoding="utf-8")

        with self.assertRaises(MalformedStoreError):
            JsonTicketStore(self.path, allowed_root=self.data_root).load()

        self.assertEqual(self.path.read_text(encoding="utf-8"), malformed)

    def test_invalid_utf8_is_reported_as_a_malformed_store(self) -> None:
        self.path.write_bytes(b"\xff\xfe")

        with self.assertRaisesRegex(MalformedStoreError, "could not read"):
            JsonTicketStore(self.path, allowed_root=self.data_root).load()

        self.assertEqual(self.path.read_bytes(), b"\xff\xfe")

    def test_load_rejects_a_non_list_document(self) -> None:
        self.path.write_text(json.dumps({"id": "RQ-104"}), encoding="utf-8")

        with self.assertRaisesRegex(MalformedStoreError, "list"):
            JsonTicketStore(self.path, allowed_root=self.data_root).load()

    def test_load_rejects_non_object_entries(self) -> None:
        self.path.write_text(json.dumps(["not a ticket"]), encoding="utf-8")

        with self.assertRaisesRegex(MalformedStoreError, "objects"):
            JsonTicketStore(self.path, allowed_root=self.data_root).load()


if __name__ == "__main__":
    unittest.main()
