import json
import tempfile
import unittest
from pathlib import Path

from academy_engine.checkpoints import CheckpointResult
from academy_engine.evidence import record_checkpoint


class ProgressTests(unittest.TestCase):
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
