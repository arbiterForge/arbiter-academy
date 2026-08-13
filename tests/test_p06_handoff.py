from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path

from academy_engine.p06_handoff import P06HandoffError, write_p06_handoff
from tests.test_p06_context_recovery import (
    P06_CONTEXT_AFTER_SHA256,
    P06_CONTEXT_AFTER_BYTES,
    P06_CONTEXT_BYTES,
    P06_NOTE_SHA256,
    P06_NOTE_BYTES,
    P06_PROVENANCE_AFTER_SHA256,
    P06_PROVENANCE_AFTER_BYTES,
    P06_PROVENANCE_BYTES,
    P06_PROVENANCE_SHA256,
    P06_CONTEXT_SHA256,
    SOURCE,
    _git,
    _write,
)
from tests._temporary import RetryingTemporaryDirectory


P06_LAB_ID = "P06-context-drift-recovery"
P06_HANDOFF_PATH = ".codearbiter/reports/academy/P06-recovery.json"


class P06HandoffTests(unittest.TestCase):
    def _attempt(self, *, extra_correction_path: bool = False) -> tuple[RetryingTemporaryDirectory, Path, str, str]:
        temporary = RetryingTemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        _git(root, "init", "-b", "main")
        _git(root, "config", "core.autocrlf", "false")
        _git(root, "config", "core.eol", "lf")
        _git(root, "config", "user.name", "Academy Learner")
        _git(root, "config", "user.email", "learner@example.test")
        _write(root, "README.md", b"P06 handoff fixture\n")
        _git(root, "add", "README.md")
        _git(root, "commit", "-m", "base")
        _git(root, "switch", "-c", f"academy/{P06_LAB_ID}/1")

        source = subprocess.run(
            ["git", "show", "HEAD:workshop_queue/cli.py"],
            cwd=SOURCE,
            check=True,
            capture_output=True,
        ).stdout
        _write(root, ".codearbiter/CONTEXT.md", P06_CONTEXT_BYTES)
        _write(root, ".codearbiter/.provenance/CONTEXT.json", P06_PROVENANCE_BYTES)
        _write(root, "docs/preserved-note.md", P06_NOTE_BYTES)
        _write(root, "workshop_queue/cli.py", source)
        _git(root, "add", ".")
        _git(root, "commit", "-m", f"academy: prepare {P06_LAB_ID} attempt 1")
        prepared = _git(root, "rev-parse", "HEAD")

        _write(root, ".codearbiter/CONTEXT.md", P06_CONTEXT_AFTER_BYTES)
        _write(root, ".codearbiter/.provenance/CONTEXT.json", P06_PROVENANCE_AFTER_BYTES)
        if extra_correction_path:
            _write(root, "unexpected.txt", b"must not join the recovery\n")
        _git(root, "add", ".codearbiter/CONTEXT.md", ".codearbiter/.provenance/CONTEXT.json")
        if extra_correction_path:
            _git(root, "add", "unexpected.txt")
        _git(root, "commit", "-m", "recover context")
        recovery = _git(root, "rev-parse", "HEAD")
        return temporary, root, prepared, recovery

    def test_writes_one_unstaged_canonical_handoff_from_committed_objects(self) -> None:
        _temporary, root, prepared, recovery = self._attempt()

        destination = write_p06_handoff(root)

        self.assertEqual(destination, root / P06_HANDOFF_PATH)
        raw = destination.read_bytes()
        payload = json.loads(raw)
        self.assertEqual(
            payload,
            {
                "context_after_sha256": P06_CONTEXT_AFTER_SHA256,
                "context_before_sha256": P06_CONTEXT_SHA256,
                "context_path": ".codearbiter/CONTEXT.md",
                "prepared_commit": prepared,
                "preserved_after_sha256": P06_NOTE_SHA256,
                "preserved_before_sha256": P06_NOTE_SHA256,
                "preserved_path": "docs/preserved-note.md",
                "provenance_after_sha256": P06_PROVENANCE_AFTER_SHA256,
                "provenance_before_sha256": P06_PROVENANCE_SHA256,
                "provenance_path": ".codearbiter/.provenance/CONTEXT.json",
                "recovery_commit": recovery,
                "recovery_route": "re-scout",
                "schema_version": 2,
                "source_path": "workshop_queue/cli.py",
                "stale_claim": "Workshop Queue report output is JSON-only.",
            },
        )
        self.assertEqual(
            raw,
            (json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode("utf-8"),
        )
        self.assertEqual(_git(root, "rev-parse", "HEAD"), recovery)
        self.assertNotIn(P06_HANDOFF_PATH, _git(root, "ls-tree", "-r", "--name-only", recovery))
        self.assertEqual(_git(root, "diff", "--cached", "--name-only"), "")
        self.assertEqual(_git(root, "diff", "--name-only"), "")
        self.assertIn(".codearbiter/reports/", _git(root, "status", "--short"))

    def test_refuses_dirty_or_noncanonical_recovery_before_writing(self) -> None:
        for label, extra_correction_path, dirty in (
            ("extra correction path", True, False),
            ("dirty worktree", False, True),
        ):
            with self.subTest(label=label):
                _temporary, root, _prepared, _recovery = self._attempt(
                    extra_correction_path=extra_correction_path
                )
                if dirty:
                    _write(root, "learner-note.txt", b"not part of P06\n")

                with self.assertRaises(P06HandoffError):
                    write_p06_handoff(root)

                self.assertFalse((root / P06_HANDOFF_PATH).exists())

    def test_refuses_to_overwrite_an_existing_candidate(self) -> None:
        _temporary, root, _prepared, _recovery = self._attempt()
        destination = root / P06_HANDOFF_PATH
        _write(destination.parent, destination.name, b"existing candidate\n")

        with self.assertRaises(P06HandoffError):
            write_p06_handoff(root)

        self.assertEqual(destination.read_bytes(), b"existing candidate\n")
