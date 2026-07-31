from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


def snapshot_files(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*")
        if path.is_file()
    }


class InstalledWheelTests(unittest.TestCase):
    def test_installed_cli_seeds_writable_app_data_without_changing_site_packages(self) -> None:
        repository = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temporary_directory:
            scratch = Path(temporary_directory)
            wheel_directory = scratch / "wheel"
            wheel_directory.mkdir()
            build_command = [
                sys.executable,
                "-m",
                "pip",
                "wheel",
                "--no-deps",
                "--wheel-dir",
                str(wheel_directory),
            ]
            wheelhouse = os.environ.get("WORKSHOP_QUEUE_TEST_WHEELHOUSE")
            if wheelhouse:
                build_command.extend(["--no-index", "--find-links", wheelhouse])
            build_command.append(str(repository))
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
                [str(venv_python), "-m", "pip", "install", "--no-index", "--no-deps", str(wheel)],
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


if __name__ == "__main__":
    unittest.main()
