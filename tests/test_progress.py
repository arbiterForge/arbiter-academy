import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from academy_engine.checkpoints import CheckpointResult
from academy_engine.evidence import record_checkpoint


def _passing_result() -> CheckpointResult:
    return CheckpointResult(
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


class ProgressTests(unittest.TestCase):
    def test_progress_rejects_a_redirected_academy_parent_before_external_write(self):
        """Catches progress writes escaping through a symlink or Windows junction parent."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            outside = root / "outside"
            outside.mkdir()
            redirected = root / "learner" / ".academy"
            redirected.parent.mkdir()
            if os.name == "nt":
                command = Path(os.environ["SystemRoot"]) / "System32" / "cmd.exe"
                created = subprocess.run(
                    [str(command), "/d", "/v:off", "/c", "mklink", "/J", str(redirected), str(outside)],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(created.returncode, 0, created.stdout + created.stderr)
            else:
                redirected.symlink_to(outside, target_is_directory=True)
            result = CheckpointResult(
                "F02-orient-to-state", True, "a" * 64, "b" * 64, ("semantic",), (),
                "c" * 64, "d" * 64, "e" * 64, "f" * 64,
                "academy/F02-orient-to-state/2", "1" * 40, "2" * 40, "3" * 40,
            )
            try:
                with patch("academy_engine.evidence.evaluate_checkpoint", return_value=result):
                    with self.assertRaisesRegex(ValueError, "unsafe progress path"):
                        record_checkpoint(redirected / "progress.json", result)
                self.assertFalse((outside / "progress.json").exists())
            finally:
                if os.path.lexists(redirected):
                    if os.name == "nt":
                        os.rmdir(redirected)
                    else:
                        redirected.unlink()

    def test_progress_rejects_an_existing_hardlinked_leaf_without_replacing_outside(self):
        """Catches atomic replacement being attempted through a shared progress leaf."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            academy = root / "learner" / ".academy"
            academy.mkdir(parents=True)
            outside = root / "outside-progress.json"
            outside.write_bytes(b"outside sentinel")
            progress = academy / "progress.json"
            os.link(outside, progress)
            self.assertGreater(progress.stat().st_nlink, 1)

            result = _passing_result()
            with patch("academy_engine.evidence.evaluate_checkpoint", return_value=result):
                with self.assertRaisesRegex(ValueError, "unsafe progress path"):
                    record_checkpoint(progress, result)

            self.assertEqual(outside.read_bytes(), b"outside sentinel")
            self.assertEqual(progress.read_bytes(), b"outside sentinel")

    def test_progress_rejects_a_directory_leaf_without_replacing_its_sentinel(self):
        """Catches a directory or other nonregular progress leaf reaching replacement."""
        with tempfile.TemporaryDirectory() as directory:
            progress = Path(directory) / "learner" / ".academy" / "progress.json"
            progress.mkdir(parents=True)
            sentinel = progress / "sentinel.txt"
            sentinel.write_bytes(b"directory sentinel")

            result = _passing_result()
            with patch("academy_engine.evidence.evaluate_checkpoint", return_value=result):
                with self.assertRaisesRegex(ValueError, "unsafe progress path"):
                    record_checkpoint(progress, result)

            self.assertTrue(progress.is_dir())
            self.assertEqual(sentinel.read_bytes(), b"directory sentinel")

    def test_progress_rejects_a_non_directory_academy_parent(self):
        """Catches mkdir or replacement proceeding when .academy is a regular file."""
        with tempfile.TemporaryDirectory() as directory:
            academy = Path(directory) / "learner" / ".academy"
            academy.parent.mkdir()
            academy.write_bytes(b"parent sentinel")

            result = _passing_result()
            with patch("academy_engine.evidence.evaluate_checkpoint", return_value=result):
                with self.assertRaisesRegex(ValueError, "unsafe progress path"):
                    record_checkpoint(academy / "progress.json", result)

            self.assertEqual(academy.read_bytes(), b"parent sentinel")

    def test_progress_rejects_lexical_parent_escape_before_outside_write(self):
        """Catches a canonical-looking suffix whose lexical parents escape the learner root."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            learner_academy = root / "learner" / ".academy"
            learner_academy.mkdir(parents=True)
            outside_academy = root / "outside" / ".academy"
            outside_academy.mkdir(parents=True)
            sentinel = outside_academy / "sentinel.txt"
            sentinel.write_bytes(b"outside sentinel")
            escaped = (
                learner_academy
                / ".."
                / ".."
                / "outside"
                / ".academy"
                / "progress.json"
            )

            result = _passing_result()
            with patch("academy_engine.evidence.evaluate_checkpoint", return_value=result):
                with self.assertRaisesRegex(ValueError, "unsafe progress path"):
                    record_checkpoint(escaped, result)

            self.assertEqual(sentinel.read_bytes(), b"outside sentinel")
            self.assertFalse((outside_academy / "progress.json").exists())

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
            github_token = "gh" + "p_abcdefghijklmnopqrstuvwxyz012345"
            path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "checkpoints": [
                            {"id": "UNKNOWN", "digest": "0"},
                            {"id": "F01-proof", "digest": "C:/Users/a"},
                        ],
                        "token": github_token,
                    },
                    separators=(",", ":"),
                ),
                encoding="utf-8",
            )
            result = CheckpointResult("F01-fork-clone-doctor", True, "a" * 64, "b" * 64, ("artifact",), (), "c" * 64, "d" * 64, "e" * 64)
            with self.assertRaises(ValueError): record_checkpoint(path, result)
