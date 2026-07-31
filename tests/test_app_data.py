from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from workshop_queue.app_data import initialize_ticket_store, resolve_data_root
from workshop_queue.store import StoreWriteError


class DataRootTests(unittest.TestCase):
    def test_source_checkout_prefers_repository_data(self) -> None:
        repository = Path(__file__).resolve().parents[1]

        resolved = resolve_data_root(
            None,
            package_directory=repository / "workshop_queue",
            environ={},
            platform_name="nt",
            home=repository,
        )

        self.assertEqual(resolved, (repository / "data").resolve())

    def test_source_checkout_still_targets_repository_data_when_store_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project = Path(temporary_directory) / "academy"
            package = project / "workshop_queue"
            package.mkdir(parents=True)
            (project / "pyproject.toml").write_text("[project]\nname='workshop-queue'\n", encoding="utf-8")

            resolved = resolve_data_root(
                None,
                package_directory=package,
                environ={"LOCALAPPDATA": str(project / "user-data")},
                platform_name="nt",
                home=project / "home",
            )

        self.assertEqual(resolved, (project / "data").resolve())

    def test_explicit_override_is_the_trusted_root_even_in_a_checkout(self) -> None:
        repository = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temporary_directory:
            override = Path(temporary_directory) / "isolated"

            resolved = resolve_data_root(
                override,
                package_directory=repository / "workshop_queue",
                environ={},
                platform_name="nt",
                home=repository,
            )

        self.assertEqual(resolved, override.resolve())

    def test_windows_user_data_is_app_specific_under_localappdata(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            base = Path(temporary_directory)

            resolved = resolve_data_root(
                None,
                package_directory=base / "installed-package",
                environ={"LOCALAPPDATA": str(base / "LocalAppData")},
                platform_name="nt",
                home=base / "home",
            )

        self.assertEqual(resolved, (base / "LocalAppData" / "ArbiterAcademy" / "WorkshopQueue").resolve())

    def test_posix_user_data_honors_xdg_data_home(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            base = Path(temporary_directory)

            resolved = resolve_data_root(
                None,
                package_directory=base / "installed-package",
                environ={"XDG_DATA_HOME": str(base / "xdg")},
                platform_name="posix",
                home=base / "home",
            )

        self.assertEqual(resolved, (base / "xdg" / "arbiter-academy" / "workshop-queue").resolve())

    def test_posix_user_data_falls_back_beneath_home(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            home = Path(temporary_directory) / "home"

            resolved = resolve_data_root(
                None,
                package_directory=home / "installed-package",
                environ={},
                platform_name="posix",
                home=home,
            )

        self.assertEqual(
            resolved,
            (home / ".local" / "share" / "arbiter-academy" / "workshop-queue").resolve(),
        )


class SeedInitializationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.path = self.root / "tickets.json"

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_first_use_initializes_from_bundled_seed(self) -> None:
        initialize_ticket_store(self.path)

        self.assertIn(b'"id": "RQ-101"', self.path.read_bytes())
        self.assertEqual(list(self.root.glob("*.tmp")), [])

    def test_existing_learner_store_is_not_overwritten(self) -> None:
        learner_data = b'[{"id": "LEARNER-1"}]\n'
        self.path.write_bytes(learner_data)

        initialize_ticket_store(self.path, seed=b"replacement")

        self.assertEqual(self.path.read_bytes(), learner_data)

    def test_concurrent_initializer_wins_without_being_overwritten(self) -> None:
        learner_data = b'[{"id": "OTHER-PROCESS"}]\n'

        def competing_link(source: Path, destination: Path) -> None:
            destination.write_bytes(learner_data)
            raise FileExistsError("injected race")

        initialize_ticket_store(self.path, seed=b"bundled seed", link=competing_link)

        self.assertEqual(self.path.read_bytes(), learner_data)
        self.assertEqual(list(self.root.glob("*.tmp")), [])

    def test_initialization_failure_is_stable_and_cleans_temporary_file(self) -> None:
        def reject_link(source: Path, destination: Path) -> None:
            raise PermissionError("injected initialization failure")

        with self.assertRaisesRegex(StoreWriteError, "could not initialize ticket store"):
            initialize_ticket_store(self.path, seed=b"bundled seed", link=reject_link)

        self.assertFalse(self.path.exists())
        self.assertEqual(list(self.root.glob("*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
