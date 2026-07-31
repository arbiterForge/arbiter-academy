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
            result = CheckpointResult("F01-proof", True, "a" * 64, "b" * 64, ("artifact",), ())
            record_checkpoint(path, result)
            value = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(value, {"schema_version": 1, "checkpoints": [{"id":"F01-proof", "digest":"b" * 64}]})
            self.assertNotIn("Users", path.read_text(encoding="utf-8"))
