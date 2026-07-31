import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from academy_engine.checkpoints import CheckpointResult
from academy_engine.evidence import record_checkpoint


class ProgressTests(unittest.TestCase):
    def test_valid_fresh_result_is_written_canonically(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / ".academy" / "progress.json"
            result = CheckpointResult(
                "F02-orient-to-state",
                True,
                "a" * 64,
                "b" * 64,
                ("semantic",),
                (),
                "c" * 64,
                "d" * 64,
                "e" * 64,
                "f" * 64,
                "academy/F02-orient-to-state/2",
                "1" * 40,
                "2" * 40,
                "3" * 40,
            )
            with patch("academy_engine.evidence.evaluate_checkpoint", return_value=result):
                record_checkpoint(path, result)
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema_version"], 2)
            self.assertEqual(payload["checkpoints"][0]["attempt_head"], "3" * 40)
            self.assertNotIn(str(root), path.read_text(encoding="utf-8"))

    def test_canonical_path_rejects_poisoned_caller_and_malformed_existing_entry(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / ".academy" / "progress.json"
            fresh = CheckpointResult(
                "F02-orient-to-state", True, "a" * 64, "b" * 64, ("semantic",), (),
                "c" * 64, "d" * 64, "e" * 64, "f" * 64,
                "academy/F02-orient-to-state/2", "1" * 40, "2" * 40, "3" * 40,
            )
            poisoned = CheckpointResult(
                "F02-orient-to-state", True, "a" * 64, "0" * 64, ("semantic",), (),
                "c" * 64, "d" * 64, "e" * 64, "f" * 64,
                "academy/F02-orient-to-state/2", "1" * 40, "2" * 40, "3" * 40,
            )
            with patch("academy_engine.evidence.evaluate_checkpoint", return_value=fresh):
                with self.assertRaisesRegex(ValueError, "not fresh"):
                    record_checkpoint(path, poisoned)
            path.parent.mkdir(parents=True)
            path.write_text(
                '{"schema_version":2,"checkpoints":[{"id":"F02-orient-to-state","result_sha256":"0"}]}',
                encoding="utf-8",
            )
            with patch("academy_engine.evidence.evaluate_checkpoint", return_value=fresh):
                with self.assertRaisesRegex(ValueError, "existing progress"):
                    record_checkpoint(path, fresh)

    def test_progress_is_canonical_digest_only_and_replaces_fabrication(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "progress.json"
            path.write_text('{"claims":["passed at C:\\\\Users\\\\learner"]}', encoding="utf-8")
            result = CheckpointResult("F01-fork-clone-doctor", True, "a" * 64, "b" * 64, ("artifact",), (), "c" * 64, "d" * 64, "e" * 64)
            with self.assertRaises(ValueError): record_checkpoint(path, result)

    def test_progress_drops_unknown_malformed_and_private_preexisting_entries(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "progress.json"
            path.write_text('{"schema_version":1,"checkpoints":[{"id":"UNKNOWN","digest":"0"},{"id":"F01-proof","digest":"C:/Users/a"}],"token":"ghp_abcdefghijklmnopqrstuvwxyz012345"}', encoding="utf-8")
            result = CheckpointResult("F01-fork-clone-doctor", True, "a" * 64, "b" * 64, ("artifact",), (), "c" * 64, "d" * 64, "e" * 64)
            with self.assertRaises(ValueError): record_checkpoint(path, result)
