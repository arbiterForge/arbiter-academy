from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


SETUPTOOLS_WHEEL_NAME = "setuptools-83.0.0-py3-none-any.whl"
SETUPTOOLS_SHA256 = "29b23c360f22f414dc7336bb39178cc7bcbf6021ed2733cde173f09dba19abb3"


def verified_wheelhouse(value: str | None) -> Path:
    if not value:
        raise unittest.SkipTest(
            "WORKSHOP_QUEUE_TEST_WHEELHOUSE is required with the verified setuptools==83.0.0 wheel"
        )
    wheelhouse = Path(value).expanduser().resolve()
    wheel = wheelhouse / SETUPTOOLS_WHEEL_NAME
    if not wheel.is_file():
        raise AssertionError(f"verified wheelhouse must contain {SETUPTOOLS_WHEEL_NAME}")
    observed = hashlib.sha256(wheel.read_bytes()).hexdigest()
    if observed != SETUPTOOLS_SHA256:
        raise AssertionError(
            f"setuptools wheel SHA-256 mismatch: expected {SETUPTOOLS_SHA256}, observed {observed}"
        )
    return wheelhouse


def copy_indexed_source(repository: Path, destination: Path) -> None:
    destination.mkdir(parents=True)
    tracked = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=repository,
        capture_output=True,
        check=True,
    ).stdout.decode("utf-8").split("\0")
    for relative_path in (path for path in tracked if path):
        target = destination / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(
            subprocess.run(
                ["git", "show", f":{relative_path}"],
                cwd=repository,
                capture_output=True,
                check=True,
            ).stdout
        )


def snapshot_files(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*")
        if path.is_file()
    }


def snapshot_checkout(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*")
        if path.is_file() and ".git" not in path.relative_to(root).parts
    }


class InstallerHarnessTests(unittest.TestCase):
    def test_missing_wheelhouse_has_a_precise_skip_prerequisite(self) -> None:
        with self.assertRaisesRegex(
            unittest.SkipTest,
            "WORKSHOP_QUEUE_TEST_WHEELHOUSE.*verified setuptools==83.0.0 wheel",
        ):
            verified_wheelhouse(None)

    def test_supplied_wheelhouse_with_wrong_hash_fails_deterministically(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            wheelhouse = Path(temporary_directory)
            (wheelhouse / SETUPTOOLS_WHEEL_NAME).write_bytes(b"not the reviewed wheel")

            with self.assertRaisesRegex(AssertionError, "SHA-256 mismatch"):
                verified_wheelhouse(str(wheelhouse))

    def test_supplied_wheelhouse_missing_exact_wheel_fails_deterministically(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            with self.assertRaisesRegex(AssertionError, SETUPTOOLS_WHEEL_NAME):
                verified_wheelhouse(temporary_directory)

    def test_scratch_source_contains_exactly_indexed_files_without_touching_checkout(self) -> None:
        repository = Path(__file__).resolve().parents[1]
        before = snapshot_checkout(repository)
        tracked = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=repository,
            capture_output=True,
            check=True,
        ).stdout.decode("utf-8").split("\0")
        expected = {path for path in tracked if path}

        with tempfile.TemporaryDirectory() as temporary_directory:
            source = Path(temporary_directory) / "source"
            copy_indexed_source(repository, source)
            actual = {
                path.relative_to(source).as_posix()
                for path in source.rglob("*")
                if path.is_file()
            }

            self.assertEqual(actual, expected)
            indexed_pyproject = subprocess.run(
                ["git", "show", ":pyproject.toml"],
                cwd=repository,
                capture_output=True,
                check=True,
            ).stdout
            self.assertEqual((source / "pyproject.toml").read_bytes(), indexed_pyproject)

        self.assertEqual(snapshot_checkout(repository), before)


class InstalledWheelTests(unittest.TestCase):
    def test_installed_cli_seeds_writable_app_data_without_changing_site_packages(self) -> None:
        wheelhouse = verified_wheelhouse(os.environ.get("WORKSHOP_QUEUE_TEST_WHEELHOUSE"))
        repository = Path(__file__).resolve().parents[1]
        checkout_before = snapshot_checkout(repository)
        with tempfile.TemporaryDirectory() as temporary_directory:
            scratch = Path(temporary_directory)
            source = scratch / "source"
            copy_indexed_source(repository, source)
            wheel_directory = scratch / "wheel"
            wheel_directory.mkdir()
            build_command = [
                sys.executable,
                "-m",
                "pip",
                "wheel",
                "--no-index",
                "--find-links",
                str(wheelhouse),
                "--no-deps",
                "--wheel-dir",
                str(wheel_directory),
                str(source),
            ]
            build = subprocess.run(build_command, text=True, capture_output=True, check=False)
            self.assertEqual(build.returncode, 0, build.stdout + build.stderr)

            venv = scratch / "venv"
            create_venv = subprocess.run(
                [sys.executable, "-m", "venv", str(venv)],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(create_venv.returncode, 0, create_venv.stdout + create_venv.stderr)
            venv_python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            executable = venv / ("Scripts/workshop-queue.exe" if os.name == "nt" else "bin/workshop-queue")
            wheel = next(wheel_directory.glob("workshop_queue-*.whl"))
            install = subprocess.run(
                [
                    str(venv_python),
                    "-m",
                    "pip",
                    "install",
                    "--no-index",
                    "--find-links",
                    str(wheelhouse),
                    "--no-deps",
                    str(wheel),
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(install.returncode, 0, install.stdout + install.stderr)
            purelib_result = subprocess.run(
                [str(venv_python), "-c", "import sysconfig; print(sysconfig.get_paths()['purelib'])"],
                text=True,
                capture_output=True,
                check=True,
            )
            site_packages = Path(purelib_result.stdout.strip())
            before = snapshot_files(site_packages)

            outside_checkout = scratch / "outside"
            user_data = scratch / "user-data"
            outside_checkout.mkdir()
            command_environment = os.environ.copy()
            command_environment["PYTHONDONTWRITEBYTECODE"] = "1"
            platform_base = scratch / "platform-data"
            if os.name == "nt":
                command_environment["LOCALAPPDATA"] = str(platform_base)
                platform_store = platform_base / "ArbiterAcademy" / "WorkshopQueue" / "tickets.json"
            else:
                command_environment["XDG_DATA_HOME"] = str(platform_base)
                platform_store = platform_base / "arbiter-academy" / "workshop-queue" / "tickets.json"

            def run_installed(*arguments: str) -> subprocess.CompletedProcess[str]:
                return subprocess.run(
                    [str(executable), "--data-root", str(user_data), *arguments],
                    cwd=outside_checkout,
                    env=command_environment,
                    text=True,
                    capture_output=True,
                    check=False,
                )

            default_list = subprocess.run(
                [str(executable), "list", "--format", "json"],
                cwd=outside_checkout,
                env=command_environment,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(default_list.returncode, 0, default_list.stderr)
            self.assertEqual(json.loads(default_list.stdout)[0]["id"], "RQ-101")
            self.assertTrue(platform_store.is_file())

            listed = run_installed("list", "--format", "json")
            self.assertEqual(listed.returncode, 0, listed.stderr)
            self.assertEqual(json.loads(listed.stdout)[0]["id"], "RQ-101")
            claimed = run_installed("claim", "RQ-101", "--volunteer", "Sam")
            self.assertEqual(claimed.returncode, 0, claimed.stderr)
            completed = run_installed("complete", "RQ-101", "--resolution", "Projector ready")
            self.assertEqual(completed.returncode, 0, completed.stderr)
            saved = json.loads((user_data / "tickets.json").read_text(encoding="utf-8"))[0]
            self.assertEqual(saved["status"], "completed")
            self.assertEqual(saved["resolution"], "Projector ready")
            self.assertEqual(snapshot_files(site_packages), before)
        self.assertEqual(snapshot_checkout(repository), checkout_before)
        for artifact in ("build", "dist", "workshop_queue.egg-info"):
            self.assertFalse((repository / artifact).exists(), artifact)

    def test_installed_academy_verifier_targets_a_separate_learner_repository(self) -> None:
        wheelhouse = verified_wheelhouse(os.environ.get("WORKSHOP_QUEUE_TEST_WHEELHOUSE"))
        repository = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temporary_directory:
            scratch = Path(temporary_directory)
            source = scratch / "source"
            shutil.copytree(
                repository,
                source,
                ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"),
            )
            wheel_directory = scratch / "wheel"
            wheel_directory.mkdir()
            build = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "wheel",
                    "--no-index",
                    "--find-links",
                    str(wheelhouse),
                    "--no-deps",
                    "--wheel-dir",
                    str(wheel_directory),
                    str(source),
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
            wheel = next(wheel_directory.glob("workshop_queue-*.whl"))
            with zipfile.ZipFile(wheel) as archive:
                names = set(archive.namelist())
            for artifact in (
                "catalog.json",
                "catalog.schema.json",
                "contracts.json",
                "checkpoint.schema.json",
                "receipt.schema.json",
                "scenario.schema.json",
            ):
                self.assertTrue(
                    any(
                        name.endswith(f"share/arbiter-academy/academy/{artifact}")
                        for name in names
                    ),
                    artifact,
                )
            self.assertEqual(
                sum(
                    name.endswith(".json")
                    and "/share/arbiter-academy/academy/checkpoints/" in name
                    for name in names
                ),
                19,
            )
            self.assertEqual(
                sum(
                    name.endswith("/manifest.json")
                    and "/share/arbiter-academy/academy/scenarios/" in name
                    for name in names
                ),
                19,
            )
            self.assertEqual(
                sum(
                    name.endswith("/scenario.json")
                    and "/share/arbiter-academy/academy/scenarios/" in name
                    for name in names
                ),
                19,
            )

            venv = scratch / "venv"
            subprocess.run(
                [sys.executable, "-m", "venv", str(venv)],
                text=True,
                capture_output=True,
                check=True,
            )
            venv_python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            executable = venv / ("Scripts/arbiter-academy.exe" if os.name == "nt" else "bin/arbiter-academy")
            install = subprocess.run(
                [
                    str(venv_python),
                    "-m",
                    "pip",
                    "install",
                    "--no-index",
                    "--find-links",
                    str(wheelhouse),
                    "--no-deps",
                    str(wheel),
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(install.returncode, 0, install.stdout + install.stderr)
            learner = scratch / "learner"
            learner.mkdir()
            subprocess.run(["git", "init", "-b", "main"], cwd=learner, check=True, capture_output=True, text=True)
            (learner / "README.md").write_text("learner\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=learner, check=True, capture_output=True, text=True)
            subprocess.run(
                ["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-m", "learner"],
                cwd=learner,
                check=True,
                capture_output=True,
                text=True,
            )
            outside = scratch / "outside"
            outside.mkdir()
            command = subprocess.run(
                [
                    str(executable),
                    "--repository",
                    str(learner),
                    "check",
                    "F01-fork-clone-doctor",
                ],
                cwd=outside,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(command.returncode, 0)
            self.assertIn("checkpoint F01-fork-clone-doctor: failed", command.stderr)
            self.assertNotIn("outside the target repository", command.stderr)
            self.assertNotIn(str(learner), command.stderr)
            self.assertNotIn("Traceback", command.stderr)
            location = subprocess.run(
                [
                    str(venv_python),
                    "-c",
                    "import academy_engine; print(academy_engine.__file__)",
                ],
                cwd=outside,
                text=True,
                capture_output=True,
                check=True,
            ).stdout.strip()
            self.assertNotIn(str(learner), location)


if __name__ == "__main__":
    unittest.main()
