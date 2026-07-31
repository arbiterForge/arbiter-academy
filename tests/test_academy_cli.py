from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path


REPOSITORY = Path(__file__).resolve().parents[1]


class AcademyCliTrustTests(unittest.TestCase):
    def test_project_packages_engine_and_registers_console_entrypoint(self) -> None:
        text = (REPOSITORY / "pyproject.toml").read_text(encoding="utf-8")

        self.assertIn('arbiter-academy = "academy_engine.cli:main"', text)
        self.assertIn('"academy_engine"', text)

    def test_authoritative_command_requires_explicit_repository(self) -> None:
        result = subprocess.run(
            [sys.executable, str(REPOSITORY / "scripts" / "academy.py"), "check", "F01-fork-clone-doctor"],
            cwd=REPOSITORY,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--repository", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_in_checkout_authoritative_command_refuses_circular_trust(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(REPOSITORY / "scripts" / "academy.py"),
                "--repository",
                str(REPOSITORY),
                "check",
                "F01-fork-clone-doctor",
            ],
            cwd=REPOSITORY,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("outside the target repository", result.stderr)
        self.assertNotIn(str(REPOSITORY), result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_nested_target_canonicalizes_before_circular_trust_check(self) -> None:
        nested = REPOSITORY / "tests"
        result = subprocess.run(
            [
                sys.executable,
                str(REPOSITORY / "scripts" / "academy.py"),
                "--repository",
                str(nested),
                "check",
                "F01-fork-clone-doctor",
            ],
            cwd=nested,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("outside the target repository", result.stderr)
        self.assertNotIn(str(REPOSITORY), result.stderr)
        self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
