import json
import tempfile
import subprocess
import unittest
from pathlib import Path

from academy_engine.checkpoints import CheckpointError, evaluate_checkpoint, load_checkpoint


class CheckpointTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "academy" / "checkpoints").mkdir(parents=True)
        (self.root / "academy" / "catalog.json").write_text('{"schema_version":1,"labs":[]}', encoding="utf-8")
        self.path = self.root / "academy" / "checkpoints" / "F01-proof.json"
        self.write({"schema_version": 1, "id": "F01-proof", "predicates": [{"id": "artifact", "type": "file_contains", "path": ".codearbiter/specs/proof.md", "text": "approved"}]})

    def tearDown(self): self.temp.cleanup()

    def write(self, value): self.path.write_text(json.dumps(value), encoding="utf-8")

    def test_untouched_partial_and_wrong_value_fail_closed(self):
        for label, contents in (("untouched", None), ("partial", ""), ("wrong", "wrong")):
            with self.subTest(label=label):
                target = self.root / ".codearbiter" / "specs" / "proof.md"
                if contents is not None:
                    target.parent.mkdir(parents=True, exist_ok=True); target.write_text(contents, encoding="utf-8")
                result = evaluate_checkpoint(self.root, "F01-proof")
                self.assertFalse(result.passed)

    def test_passing_command_does_not_replace_missing_governed_artifact(self):
        self.write({"schema_version": 1, "id": "F01-proof", "predicates": [{"id": "tests", "type": "command_success", "argv": ["python", "-c", "pass"], "timeout_seconds": 2}, {"id": "artifact", "type": "file_exists", "path": ".codearbiter/specs/proof.md"}]})
        self.assertFalse(evaluate_checkpoint(self.root, "F01-proof").passed)

    def test_definition_rejects_unknown_unsafe_and_unbounded_values(self):
        for predicate in ({"id":"x","type":"unknown"}, {"id":"x","type":"file_exists","path":"../private"}, {"id":"x","type":"command_success","argv":["x"],"timeout_seconds":999}):
            with self.subTest(predicate=predicate):
                self.write({"schema_version":1,"id":"F01-proof","predicates":[predicate]})
                with self.assertRaises(CheckpointError): load_checkpoint(self.path)

    def test_wrong_branch_fails_recomputed_git_evidence(self):
        subprocess.run(["git", "init"], cwd=self.root, check=True, capture_output=True, text=True)
        subprocess.run(["git", "switch", "-c", "wrong-branch"], cwd=self.root, check=True, capture_output=True, text=True)
        self.write({"schema_version":1,"id":"F01-proof","predicates":[{"id":"branch","type":"git_branch","branch":"academy/F01-proof/1"}]})
        self.assertFalse(evaluate_checkpoint(self.root, "F01-proof").passed)
