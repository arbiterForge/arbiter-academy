from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path


SETUPTOOLS_WHEEL_NAME = "setuptools-83.0.0-py3-none-any.whl"
SETUPTOOLS_SHA256 = "29b23c360f22f414dc7336bb39178cc7bcbf6021ed2733cde173f09dba19abb3"
P04_CANDIDATE_DIRECTORY = "academy/candidates/P04-review-a-dependency"
P04_CANDIDATE_FILES = (
    "candidate-set.json",
    "python_dateutil-2.9.0.post0-py2.py3-none-any.whl",
    "six-1.17.0-py2.py3-none-any.whl",
    "python_dateutil-2.9.0.post0.LICENSE",
    "six-1.17.0.LICENSE",
    "Apache-2.0.txt",
)


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
    snapshot: dict[str, str] = {}
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if (
            not path.is_file()
            or ".git" in relative.parts
            or relative.parts[:1] == (".superpowers",)
        ):
            continue
        snapshot[relative.as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return snapshot


class InstallerHarnessTests(unittest.TestCase):
    def test_checkout_snapshot_ignores_only_root_superpowers_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            repository = Path(temporary_directory)
            evidence = repository / ".superpowers/shard.stderr.log"
            ordinary_untracked = repository / "ordinary-untracked.log"
            evidence.parent.mkdir()
            evidence.write_bytes(b"evidence-before")
            ordinary_untracked.write_bytes(b"ordinary-before")
            before = snapshot_checkout(repository)

            evidence.write_bytes(b"evidence-after")
            self.assertEqual(snapshot_checkout(repository), before)

            ordinary_untracked.write_bytes(b"ordinary-after")
            self.assertNotEqual(snapshot_checkout(repository), before)

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
    def test_p04_candidate_bytes_survive_source_sdist_wheel_and_install_without_runtime_dependency(self) -> None:
        """Catches opaque P04 evidence being omitted, transformed, or promoted to an Academy dependency."""
        wheelhouse = verified_wheelhouse(os.environ.get("WORKSHOP_QUEUE_TEST_WHEELHOUSE"))
        repository = Path(__file__).resolve().parents[1]
        expected = {
            name: (repository / P04_CANDIDATE_DIRECTORY / name).read_bytes()
            for name in P04_CANDIDATE_FILES
        }
        self.assertEqual(
            {path.name for path in (repository / P04_CANDIDATE_DIRECTORY).iterdir() if path.is_file()},
            set(P04_CANDIDATE_FILES),
        )

        with tempfile.TemporaryDirectory() as temporary_directory:
            scratch = Path(temporary_directory)
            source = scratch / "source"
            shutil.copytree(repository, source, ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"))
            build_venv = scratch / "build-venv"
            subprocess.run([sys.executable, "-m", "venv", str(build_venv)], check=True, capture_output=True, text=True)
            build_python = build_venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            bootstrap = subprocess.run(
                [str(build_python), "-m", "pip", "install", "--no-index", "--find-links", str(wheelhouse), "--no-deps", "setuptools==83.0.0"],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(bootstrap.returncode, 0, bootstrap.stdout + bootstrap.stderr)
            dist = scratch / "dist"
            dist.mkdir()
            sdist = subprocess.run(
                [str(build_python), "-c", "from setuptools.build_meta import build_sdist; print(build_sdist(r'" + str(dist) + "'))"],
                cwd=source,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(sdist.returncode, 0, sdist.stdout + sdist.stderr)
            archive = next(dist.glob("workshop_queue-*.tar.gz"))
            with tarfile.open(archive, "r:gz") as contents:
                names = set(contents.getnames())
                prefix = next(name.split("/", 1)[0] for name in names if name.endswith("/pyproject.toml"))
                self.assertEqual(
                    {name.rsplit("/", 1)[-1] for name in names if f"/{P04_CANDIDATE_DIRECTORY}/" in name},
                    set(P04_CANDIDATE_FILES),
                )
                for name, raw in expected.items():
                    member = contents.extractfile(f"{prefix}/{P04_CANDIDATE_DIRECTORY}/{name}")
                    self.assertIsNotNone(member, name)
                    assert member is not None
                    self.assertEqual(member.read(), raw, name)

            wheel_directory = scratch / "wheel"
            wheel_directory.mkdir()
            build = subprocess.run(
                [str(build_python), "-m", "pip", "wheel", "--no-index", "--find-links", str(wheelhouse), "--no-deps", "--wheel-dir", str(wheel_directory), str(source)],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
            wheel = next(wheel_directory.glob("workshop_queue-*.whl"))
            with zipfile.ZipFile(wheel) as contents:
                names = set(contents.namelist())
                resource_prefix = "workshop_queue-0.1.0.data/data/share/arbiter-academy/academy/candidates/P04-review-a-dependency/"
                self.assertEqual({name.removeprefix(resource_prefix) for name in names if name.startswith(resource_prefix)}, set(P04_CANDIDATE_FILES))
                for name, raw in expected.items():
                    self.assertEqual(contents.read(resource_prefix + name), raw, name)
                metadata = contents.read("workshop_queue-0.1.0.dist-info/METADATA").decode("utf-8")
                self.assertNotIn("Requires-Dist:", metadata)

            installed_venv = scratch / "installed-venv"
            subprocess.run([sys.executable, "-m", "venv", str(installed_venv)], check=True, capture_output=True, text=True)
            installed_python = installed_venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            install = subprocess.run(
                [str(installed_python), "-m", "pip", "install", "--no-index", "--find-links", str(wheelhouse), "--no-deps", str(wheel)],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(install.returncode, 0, install.stdout + install.stderr)
            data_root = Path(subprocess.run(
                [str(installed_python), "-c", "import sysconfig; print(sysconfig.get_paths()['data'])"],
                text=True,
                capture_output=True,
                check=True,
            ).stdout.strip())
            installed_root = data_root / "share/arbiter-academy/academy/candidates/P04-review-a-dependency"
            self.assertEqual({path.name for path in installed_root.iterdir() if path.is_file()}, set(P04_CANDIDATE_FILES))
            for name, raw in expected.items():
                self.assertEqual((installed_root / name).read_bytes(), raw, name)
            imports = subprocess.run(
                [str(installed_python), "-c", "import academy_engine, sys; print(sorted(set(sys.modules).intersection({'dateutil', 'six'})))"],
                text=True,
                capture_output=True,
                check=True,
            )
            self.assertEqual(imports.stdout.strip(), "[]")

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
            self.assertTrue(
                any(
                    name.endswith(
                        "share/arbiter-academy/academy/publication/preview-0.8.json"
                    )
                    for name in names
                ),
                "preview-0.8.json",
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
            foundations_sources = {
                name.rsplit("/", 1)[-1]
                for name in names
                if "/share/arbiter-academy/academy/tracks/foundations/" in name
                and name.endswith(".md")
            }
            self.assertEqual(
                foundations_sources,
                {
                    "index.md",
                    "F01-fork-clone-doctor.md",
                    "F02-orient-to-state.md",
                    "F03-work-the-board.md",
                    "F04-fix-with-evidence.md",
                },
            )
            practitioner_sources = {
                name.rsplit("/", 1)[-1]
                for name in names
                if "/share/arbiter-academy/academy/tracks/practitioner/" in name
                and name.endswith(".md")
            }
            self.assertEqual(
                practitioner_sources,
                {
                    "index.md",
                    "P01-feature-through-plan.md",
                    "P02-commit-review-pr.md",
                    "P03-record-an-adr.md",
                    "P04-review-a-dependency.md",
                    "P05-checkpoint-remediation.md",
                    "P06-context-drift-recovery.md",
                    "P07-threat-model.md",
                    "P08-repository-hygiene.md",
                },
            )
            power_user_sources = {
                name.rsplit("/", 1)[-1]
                for name in names
                if "/share/arbiter-academy/academy/tracks/power-user/" in name
                and name.endswith(".md")
            }
            self.assertEqual(power_user_sources, set())

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

            p08_learner = scratch / "p08-learner"
            shutil.copytree(
                source,
                p08_learner,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
            )
            subprocess.run(
                ["git", "init", "-b", "main"],
                cwd=p08_learner,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Fixture"],
                cwd=p08_learner,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "config", "user.email", "fixture@example.invalid"],
                cwd=p08_learner,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(["git", "add", "."], cwd=p08_learner, check=True, capture_output=True, text=True)
            subprocess.run(
                ["git", "commit", "-m", "academy base"],
                cwd=p08_learner,
                check=True,
                capture_output=True,
                text=True,
            )
            for name, url in (
                ("origin", "https://github.com/learner/arbiter-academy.git"),
                ("upstream", "https://github.com/arbiterForge/arbiter-academy.git"),
            ):
                subprocess.run(
                    ["git", "remote", "add", name, url],
                    cwd=p08_learner,
                    check=True,
                    capture_output=True,
                    text=True,
                )
            subprocess.run(
                ["git", "remote", "set-url", "--push", "upstream", "DISABLED"],
                cwd=p08_learner,
                check=True,
                capture_output=True,
                text=True,
            )
            isolated_environment = os.environ.copy()
            isolated_environment["PYTHONDONTWRITEBYTECODE"] = "1"
            if os.name == "nt":
                short_data_root = tempfile.TemporaryDirectory(
                    prefix="aa-", dir=Path(tempfile.gettempdir()).anchor
                )
                self.addCleanup(short_data_root.cleanup)
                isolated_environment["LOCALAPPDATA"] = short_data_root.name
            else:
                isolated_environment["XDG_DATA_HOME"] = str(scratch / "academy-data")
            p08_prepare_script = (
                "import sys\n"
                "from pathlib import Path\n"
                "from academy_engine.scenario import prepare_lab\n"
                "prepare_lab(Path(sys.argv[1]), 'P08-repository-hygiene', installed_authority=True)\n"
            )
            p08_checkpoint_script = (
                "import sys\n"
                "from pathlib import Path\n"
                "from academy_engine.checkpoints import evaluate_checkpoint\n"
                "from academy_engine.evidence import record_checkpoint\n"
                "root = Path(sys.argv[1])\n"
                "result = evaluate_checkpoint(root, 'P08-repository-hygiene')\n"
                "if result.passed:\n"
                "    record_checkpoint(root / '.academy/progress.json', result)\n"
                "    print('checkpoint P08-repository-hygiene: passed; progress: .academy/progress.json')\n"
                "    raise SystemExit(0)\n"
                "print('checkpoint P08-repository-hygiene: failed (' + ', '.join(result.failed_predicates) + ')', file=sys.stderr)\n"
                "raise SystemExit(1)\n"
            )
            p08_prepare = subprocess.run(
                [str(venv_python), "-c", p08_prepare_script, str(p08_learner)],
                cwd=outside,
                env=isolated_environment,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(p08_prepare.returncode, 0, p08_prepare.stdout + p08_prepare.stderr)
            before_report = subprocess.run(
                [str(venv_python), "-c", p08_checkpoint_script, str(p08_learner)],
                cwd=outside,
                env=isolated_environment,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(before_report.returncode, 0)
            self.assertTrue(
                before_report.stderr.startswith("checkpoint P08-repository-hygiene: failed ("),
                before_report.stderr,
            )
            self.assertNotIn(str(p08_learner), before_report.stderr)
            self.assertNotIn(str(outside), before_report.stderr)
            self.assertNotIn("p08-worktrees", before_report.stderr)
            self.assertNotIn("VerifierState", before_report.stderr)
            self.assertNotIn("git_admin_id", before_report.stderr)
            self.assertIsNone(re.search(r"[0-9a-f]{64}", before_report.stderr))
            self.assertNotIn("Traceback", before_report.stderr)
            report_writer = (
                "import json, sys\n"
                "from pathlib import Path\n"
                "from academy_engine.exercise_state import _p08_expected_report, open_p08_store, preflight_p08\n"
                "root = Path(sys.argv[1])\n"
                "base, _lab, authority = preflight_p08(root)\n"
                "store = open_p08_store(root, base=base, authority=authority)\n"
                "with store.locked() as locked:\n"
                "    record = locked.read_record('p08', 1)\n"
                "if record is None:\n"
                "    raise SystemExit('missing P08 record')\n"
                "target = root / '.codearbiter/reports/academy/P08-hygiene.json'\n"
                "target.parent.mkdir(parents=True, exist_ok=True)\n"
                "target.write_bytes(json.dumps(_p08_expected_report(root, record, base), sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8') + b'\\n')\n"
            )
            rendered = subprocess.run(
                [str(venv_python), "-c", report_writer, str(p08_learner)],
                cwd=outside,
                env=isolated_environment,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(rendered.returncode, 0, rendered.stdout + rendered.stderr)
            subprocess.run(
                ["git", "add", ".codearbiter/reports/academy/P08-hygiene.json"],
                cwd=p08_learner,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "commit", "-m", "academy: report P08 hygiene"],
                cwd=p08_learner,
                check=True,
                capture_output=True,
                text=True,
            )
            p08_check = subprocess.run(
                [str(venv_python), "-c", p08_checkpoint_script, str(p08_learner)],
                cwd=outside,
                env=isolated_environment,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(p08_check.returncode, 0, p08_check.stdout + p08_check.stderr)
            self.assertEqual(
                p08_check.stdout,
                "checkpoint P08-repository-hygiene: passed; progress: .academy/progress.json\n",
            )
            self.assertEqual(p08_check.stderr, "")


if __name__ == "__main__":
    unittest.main()
