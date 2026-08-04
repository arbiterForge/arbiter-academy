from __future__ import annotations

import hashlib
import inspect
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from academy_engine import external_state
from academy_engine.external_state import (
    ExternalStateError,
    ExternalStateStore,
    LockedExternalState,
    repository_locator,
    resolve_state_root,
)


BASE_COMMIT = "a" * 40
CATALOG_SHA256 = "b" * 64


def git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    if result.returncode:
        raise AssertionError(result.stderr or result.stdout)
    return result.stdout.strip()


class RepositoryFixture:
    def __init__(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name).resolve()
        self.root = self.base / "learner-private-repository"
        self.root.mkdir()
        git(self.root, "init", "--object-format=sha1", "--initial-branch=main")
        (self.root / "README.md").write_text("academy\n", encoding="utf-8")
        git(self.root, "add", "README.md")
        git(
            self.root,
            "-c",
            "user.name=Academy Test",
            "-c",
            "user.email=academy@example.invalid",
            "commit",
            "-m",
            "initial",
        )
        self.state_root = self.base / "installed-state"

    def store(
        self,
        *,
        base_commit: str = BASE_COMMIT,
        catalog_sha256: str = CATALOG_SHA256,
        state_root: Path | None = None,
    ) -> ExternalStateStore:
        return ExternalStateStore.open(
            self.root,
            academy_base_commit=base_commit,
            catalog_sha256=catalog_sha256,
            test_root=self.state_root if state_root is None else state_root,
        )

    def close(self) -> None:
        self.temporary.cleanup()


class ExistingStateProbeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = RepositoryFixture()
        self.addCleanup(self.fixture.close)

    def test_absent_probe_and_open_existing_are_non_mutating(self) -> None:
        self.assertFalse(
            ExternalStateStore.has_records(
                self.fixture.root,
                lab="p02",
                test_root=self.fixture.state_root,
            )
        )
        self.assertIsNone(
            ExternalStateStore.open_existing(
                self.fixture.root,
                academy_base_commit=BASE_COMMIT,
                catalog_sha256=CATALOG_SHA256,
                test_root=self.fixture.state_root,
            )
        )
        self.assertFalse(self.fixture.state_root.exists())

    def test_installed_state_open_paths_keep_authoritative_config_validation(self) -> None:
        """Catches extending the read-only absence exception into state open paths."""
        git(self.fixture.root, "config", "pull.rebase", "false")

        for operation in (
            lambda: self.fixture.store(),
            lambda: ExternalStateStore.open_existing(
                self.fixture.root,
                academy_base_commit=BASE_COMMIT,
                catalog_sha256=CATALOG_SHA256,
                test_root=self.fixture.state_root,
            ),
        ):
            with self.subTest(operation=operation):
                with self.assertRaises(ExternalStateError) as raised:
                    operation()
                self.assertEqual(raised.exception.code, "repository-identity")
                self.assertFalse(self.fixture.state_root.exists())

    def test_probe_finds_records_and_open_existing_binds_exact_epoch(self) -> None:
        store = self.fixture.store()
        with store.locked() as locked:
            locked.write_record(
                "p02", 1, {"generation": 1}, expected_generation=0
            )

        self.assertTrue(
            ExternalStateStore.has_records(
                self.fixture.root,
                lab="p02",
                test_root=self.fixture.state_root,
            )
        )
        opened = ExternalStateStore.open_existing(
            self.fixture.root,
            academy_base_commit=BASE_COMMIT,
            catalog_sha256=CATALOG_SHA256,
            test_root=self.fixture.state_root,
        )
        self.assertIsNotNone(opened)
        self.assertEqual(opened.repository_id, store.repository_id)
        self.assertIsNone(
            ExternalStateStore.open_existing(
                self.fixture.root,
                academy_base_commit="c" * 40,
                catalog_sha256=CATALOG_SHA256,
                test_root=self.fixture.state_root,
            )
        )

    def test_probe_rejects_noncanonical_epoch_structure_without_reading_records(self) -> None:
        store = self.fixture.store()
        with store.locked() as locked:
            locked.write_record(
                "p02", 1, {"generation": 1}, expected_generation=0
            )
        epochs = store._epoch_dir.parent
        (epochs / "not-a-canonical-epoch").mkdir()

        with self.assertRaisesRegex(ExternalStateError, "identity"):
            ExternalStateStore.has_records(
                self.fixture.root,
                lab="p02",
                test_root=self.fixture.state_root,
            )

    def test_open_existing_does_not_repair_or_rewrite_existing_state(self) -> None:
        store = self.fixture.store()
        with store.locked() as locked:
            locked.write_record(
                "p02", 1, {"generation": 1}, expected_generation=0
            )
        identity_before = store._identity_path.read_bytes()
        lock_before = store._lock_path.read_bytes()
        identity_mtime = store._identity_path.stat().st_mtime_ns
        lock_mtime = store._lock_path.stat().st_mtime_ns

        opened = ExternalStateStore.open_existing(
            self.fixture.root,
            academy_base_commit=BASE_COMMIT,
            catalog_sha256=CATALOG_SHA256,
            test_root=self.fixture.state_root,
        )

        self.assertIsNotNone(opened)
        self.assertEqual(store._identity_path.read_bytes(), identity_before)
        self.assertEqual(store._lock_path.read_bytes(), lock_before)
        self.assertEqual(store._identity_path.stat().st_mtime_ns, identity_mtime)
        self.assertEqual(store._lock_path.stat().st_mtime_ns, lock_mtime)

    def test_probe_rejects_empty_and_noncanonical_attempt_directories(self) -> None:
        store = self.fixture.store()
        lab_directory = store._epoch_dir / "p02"
        lab_directory.mkdir()
        if os.name != "nt":
            os.chmod(lab_directory, 0o700)

        before = self._snapshot(self.fixture.state_root)
        with self.assertRaises(ExternalStateError) as empty:
            ExternalStateStore.has_records(
                self.fixture.root,
                lab="p02",
                test_root=self.fixture.state_root,
            )
        self.assertEqual(empty.exception.code, "state-corrupt")
        self.assertEqual(self._snapshot(self.fixture.state_root), before)

        for name in ("01", "+1", "\u0661", "0", "33"):
            with self.subTest(name=name):
                attempt = lab_directory / name
                attempt.mkdir()
                before = self._snapshot(self.fixture.state_root)
                with self.assertRaises(ExternalStateError) as invalid:
                    ExternalStateStore.has_records(
                        self.fixture.root,
                        lab="p02",
                        test_root=self.fixture.state_root,
                    )
                self.assertEqual(invalid.exception.code, "state-corrupt")
                self.assertEqual(self._snapshot(self.fixture.state_root), before)
                attempt.rmdir()

    def test_open_existing_validates_locator_lock_before_absent_epoch(self) -> None:
        store = self.fixture.store()
        store._lock_path.unlink()
        before = self._snapshot(self.fixture.state_root)

        with self.assertRaises(ExternalStateError) as raised:
            ExternalStateStore.open_existing(
                self.fixture.root,
                academy_base_commit="c" * 40,
                catalog_sha256=CATALOG_SHA256,
                test_root=self.fixture.state_root,
            )

        self.assertEqual(raised.exception.code, "state-identity-mismatch")
        self.assertEqual(self._snapshot(self.fixture.state_root), before)

    def test_open_existing_rejects_empty_or_malformed_epochs_before_absent_epoch(self) -> None:
        for shape in ("empty", "malformed-sibling"):
            with self.subTest(shape=shape):
                fixture = RepositoryFixture()
                self.addCleanup(fixture.close)
                store = fixture.store()
                epochs = store._epoch_dir.parent
                shutil.rmtree(store._epoch_dir)
                if shape == "malformed-sibling":
                    (epochs / "not-a-canonical-epoch").mkdir()
                before = self._snapshot(fixture.state_root)

                with self.assertRaises(ExternalStateError) as raised:
                    ExternalStateStore.open_existing(
                        fixture.root,
                        academy_base_commit="c" * 40,
                        catalog_sha256=CATALOG_SHA256,
                        test_root=fixture.state_root,
                    )

                self.assertEqual(raised.exception.code, "state-identity-mismatch")
                self.assertEqual(self._snapshot(fixture.state_root), before)

    def test_open_existing_validates_p02_records_in_valid_sibling_epochs_before_absence(self) -> None:
        """Catches corrupt sibling P02 state hidden by an absent requested epoch."""
        for shape in ("empty", "noncanonical", "partial", "extra"):
            with self.subTest(shape=shape):
                fixture = RepositoryFixture()
                self.addCleanup(fixture.close)
                store = fixture.store()
                lab_directory = store._epoch_dir / "p02"
                if shape == "extra":
                    with store.locked() as locked:
                        locked.write_record(
                            "p02", 1, {"generation": 1}, expected_generation=0
                        )
                    (lab_directory / "1/unexpected").write_text(
                        "corrupt\n", encoding="utf-8"
                    )
                else:
                    lab_directory.mkdir()
                    if os.name != "nt":
                        os.chmod(lab_directory, 0o700)
                    if shape == "noncanonical":
                        attempt = lab_directory / "01"
                        attempt.mkdir()
                    elif shape == "partial":
                        attempt = lab_directory / "1"
                        attempt.mkdir()
                    if shape in {"noncanonical", "partial"} and os.name != "nt":
                        os.chmod(attempt, 0o700)
                before = self._snapshot(fixture.state_root)

                with self.assertRaises(ExternalStateError) as raised:
                    ExternalStateStore.open_existing(
                        fixture.root,
                        academy_base_commit="c" * 40,
                        catalog_sha256=CATALOG_SHA256,
                        test_root=fixture.state_root,
                    )

                self.assertEqual(raised.exception.code, "state-corrupt")
                self.assertEqual(self._snapshot(fixture.state_root), before)

    @staticmethod
    def _snapshot(root: Path) -> dict[str, tuple[str, bytes | None]]:
        if not root.exists():
            return {}
        return {
            path.relative_to(root).as_posix(): (
                "directory" if path.is_dir() else "file",
                None if path.is_dir() else path.read_bytes(),
            )
            for path in root.rglob("*")
        }

    def test_probe_rejects_partial_locator_epochs_and_identity_without_mutation(self) -> None:
        cases = (
            "missing-lock",
            "directory-lock",
            "empty-epochs",
            "missing-identity",
            "corrupt-identity",
        )
        for kind in cases:
            with self.subTest(kind=kind):
                fixture = RepositoryFixture()
                self.addCleanup(fixture.close)
                store = fixture.store()
                if kind == "missing-lock":
                    store._lock_path.unlink()
                elif kind == "directory-lock":
                    store._lock_path.unlink()
                    store._lock_path.mkdir()
                elif kind == "empty-epochs":
                    shutil.rmtree(store._epoch_dir)
                elif kind == "missing-identity":
                    store._identity_path.unlink()
                else:
                    store._identity_path.write_bytes(b'{"corrupt":true}\n')
                before = self._snapshot(fixture.state_root)

                with self.assertRaises(ExternalStateError):
                    ExternalStateStore.has_records(
                        fixture.root,
                        lab="p02",
                        test_root=fixture.state_root,
                    )

                self.assertEqual(self._snapshot(fixture.state_root), before)


class RootResolutionTests(unittest.TestCase):
    def test_platform_roots_are_exact(self) -> None:
        if os.name == "nt":
            windows_home = Path("C:/Users/Academy")
            local = Path("C:/Users/Academy/AppData/Local")
        else:
            windows_home = Path("/Users/Academy")
            local = Path("/var/academy/local")

        self.assertEqual(
            resolve_state_root(
                platform_name="win32",
                environ={"LOCALAPPDATA": str(local)},
                home=windows_home,
            ),
            local / "ArbiterAcademy/VerifierState",
        )
        self.assertEqual(
            resolve_state_root(platform_name="win32", environ={}, home=windows_home),
            windows_home / "AppData/Local/ArbiterAcademy/VerifierState",
        )
        host_anchor = Path(Path.cwd().anchor)
        posix_home = host_anchor / "Users/academy"
        self.assertEqual(
            resolve_state_root(platform_name="darwin", environ={}, home=posix_home),
            posix_home / "Library/Application Support/ArbiterAcademy/VerifierState",
        )
        self.assertEqual(
            resolve_state_root(
                platform_name="linux",
                environ={"XDG_STATE_HOME": str(host_anchor / "srv/state")},
                home=host_anchor / "home/academy",
            ),
            host_anchor / "srv/state/arbiter-academy",
        )
        self.assertEqual(
            resolve_state_root(
                platform_name="linux",
                environ={"XDG_STATE_HOME": "relative"},
                home=host_anchor / "home/academy",
            ),
            host_anchor / "home/academy/.local/state/arbiter-academy",
        )

    def test_invalid_windows_roots_are_rejected_path_free(self) -> None:
        for supplied in ("relative", r"\\server\share"):
            with self.subTest(supplied=supplied):
                with self.assertRaises(ExternalStateError) as raised:
                    resolve_state_root(
                        platform_name="win32",
                        environ={"LOCALAPPDATA": supplied},
                        home=Path("C:/Users/Academy"),
                    )
                self.assertEqual(raised.exception.code, "invalid-state-root")
                self.assertNotIn(supplied, str(raised.exception))

    def test_store_rejects_inside_file_and_redirected_roots(self) -> None:
        fixture = RepositoryFixture()
        self.addCleanup(fixture.close)
        candidates: list[tuple[str, Path, str]] = []
        candidates.append(("inside", fixture.root / "state", "state-root-inside-repository"))
        file_root = fixture.base / "state-file"
        file_root.write_text("not a directory", encoding="utf-8")
        candidates.append(("file", file_root, "unsafe-state-path"))

        outside = fixture.base / "redirect-target"
        outside.mkdir()
        redirected = fixture.base / "redirected-state"
        if sys.platform == "win32":
            command = Path(os.environ["SystemRoot"]) / "System32/cmd.exe"
            created = subprocess.run(
                [str(command), "/d", "/v:off", "/c", "mklink", "/J", redirected.name, outside.name],
                cwd=fixture.base,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                check=False,
                timeout=10,
            )
            self.assertEqual(created.returncode, 0, (created.stdout + created.stderr)[:2048])
        else:
            os.symlink(outside, redirected, target_is_directory=True)
        self.addCleanup(self._remove_redirect, redirected)
        candidates.append(("redirect", redirected, "unsafe-state-path"))

        for name, candidate, code in candidates:
            with self.subTest(name=name):
                with self.assertRaises(ExternalStateError) as raised:
                    fixture.store(state_root=candidate)
                self.assertEqual(raised.exception.code, code)
                self.assertNotIn(str(candidate), str(raised.exception))

    @staticmethod
    def _remove_redirect(path: Path) -> None:
        if os.path.lexists(path):
            if sys.platform == "win32":
                os.rmdir(path)
            else:
                os.unlink(path)

    def test_reparse_ancestor_in_created_descendants_is_rejected(self) -> None:
        fixture = RepositoryFixture()
        self.addCleanup(fixture.close)
        fixture.state_root.mkdir()
        outside = fixture.base / "outside-repositories"
        outside.mkdir()
        redirected = fixture.state_root / "repositories"
        if sys.platform == "win32":
            command = Path(os.environ["SystemRoot"]) / "System32/cmd.exe"
            created = subprocess.run(
                [
                    str(command),
                    "/d",
                    "/v:off",
                    "/c",
                    "mklink",
                    "/J",
                    "installed-state\\repositories",
                    "outside-repositories",
                ],
                cwd=fixture.base,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                check=False,
                timeout=10,
            )
            self.assertEqual(created.returncode, 0, (created.stdout + created.stderr)[:2048])
        else:
            os.symlink(outside, redirected, target_is_directory=True)
        self.addCleanup(self._remove_redirect, redirected)

        with self.assertRaises(ExternalStateError) as raised:
            fixture.store()
        self.assertEqual(raised.exception.code, "unsafe-state-path")
        self.assertEqual(list(outside.iterdir()), [])

    def test_redirected_ancestor_above_absent_state_root_is_rejected_before_creation(self) -> None:
        fixture = RepositoryFixture()
        self.addCleanup(fixture.close)
        outside = fixture.base / "outside-parent"
        outside.mkdir()
        redirected = fixture.base / "redirected-parent"
        if sys.platform == "win32":
            command = Path(os.environ["SystemRoot"]) / "System32/cmd.exe"
            created = subprocess.run(
                [str(command), "/d", "/v:off", "/c", "mklink", "/J", redirected.name, outside.name],
                cwd=fixture.base,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                check=False,
                timeout=10,
            )
            self.assertEqual(created.returncode, 0, (created.stdout + created.stderr)[:2048])
        else:
            os.symlink(outside, redirected, target_is_directory=True)
        self.addCleanup(self._remove_redirect, redirected)
        candidate = redirected / "VerifierState"

        with self.assertRaises(ExternalStateError) as raised:
            fixture.store(state_root=candidate)

        self.assertEqual(raised.exception.code, "unsafe-state-path")
        self.assertFalse((outside / "VerifierState").exists())
        self.assertNotIn(str(candidate), str(raised.exception))

    def test_read_only_lookup_rejects_a_redirected_ancestor_without_mutation(self) -> None:
        """Catches read-only traversal through a symlink or junction above the state root."""
        fixture = RepositoryFixture()
        self.addCleanup(fixture.close)
        outside = fixture.base / "outside-read-only"
        candidate_target = outside / "VerifierState"
        candidate_target.mkdir(parents=True)
        sentinel = candidate_target / "sentinel.txt"
        sentinel.write_text("preserve\n", encoding="utf-8")
        redirected = fixture.base / "redirected-read-only"
        if sys.platform == "win32":
            command = Path(os.environ["SystemRoot"]) / "System32/cmd.exe"
            created = subprocess.run(
                [
                    str(command),
                    "/d",
                    "/v:off",
                    "/c",
                    "mklink",
                    "/J",
                    redirected.name,
                    outside.name,
                ],
                cwd=fixture.base,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                check=False,
                timeout=10,
            )
            self.assertEqual(
                created.returncode, 0, (created.stdout + created.stderr)[:2048]
            )
        else:
            os.symlink(outside, redirected, target_is_directory=True)
        self.addCleanup(self._remove_redirect, redirected)
        candidate = redirected / "VerifierState"
        before = sentinel.read_bytes()

        for operation in ("has-records", "open-existing"):
            with self.subTest(operation=operation):
                with self.assertRaises(ExternalStateError) as raised:
                    if operation == "has-records":
                        ExternalStateStore.has_records(
                            fixture.root, lab="p02", test_root=candidate
                        )
                    else:
                        ExternalStateStore.open_existing(
                            fixture.root,
                            academy_base_commit=BASE_COMMIT,
                            catalog_sha256=CATALOG_SHA256,
                            test_root=candidate,
                        )
                self.assertEqual(raised.exception.code, "unsafe-state-path")
                self.assertNotIn(str(candidate), str(raised.exception))
                self.assertEqual(sentinel.read_bytes(), before)
                self.assertEqual(tuple(candidate_target.iterdir()), (sentinel,))


class LocatorAndIdentityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = RepositoryFixture()
        self.addCleanup(self.fixture.close)

    def test_linked_worktrees_share_exact_filesystem_locator(self) -> None:
        linked = self.fixture.base / "linked-worktree"
        git(self.fixture.root, "worktree", "add", "-b", "linked", str(linked), "main")
        first = repository_locator(self.fixture.root)
        second = repository_locator(linked)
        self.assertEqual(first, second)
        self.assertEqual(first.source_kind, "filesystem-id")
        common = Path(git(self.fixture.root, "rev-parse", "--git-common-dir"))
        if not common.is_absolute():
            common = self.fixture.root / common
        details = common.resolve(strict=True).stat()
        preimage = (
            "arbiter-academy/repository-locator/v1\0filesystem-id\0sha1\0"
            f"{details.st_dev}\0{details.st_ino}\n"
        ).encode("ascii")
        self.assertEqual(first.digest, hashlib.sha256(preimage).hexdigest())

    def test_forced_fallback_uses_normalized_resolved_common_directory(self) -> None:
        common = Path(git(self.fixture.root, "rev-parse", "--git-common-dir"))
        if not common.is_absolute():
            common = self.fixture.root / common
        normalized = os.path.normcase(str(common.resolve(strict=True))).replace("\\", "/")
        expected = hashlib.sha256(
            (
                "arbiter-academy/repository-locator/v1\0resolved-path-fallback\0"
                f"sha1\0{normalized}\n"
            ).encode("utf-8")
        ).hexdigest()
        with mock.patch.object(external_state, "_filesystem_identity", return_value=None):
            locator = repository_locator(self.fixture.root)
        self.assertEqual(locator.source_kind, "resolved-path-fallback")
        self.assertEqual(locator.digest, expected)

    def test_git_boundary_is_called_without_trusted_local_config(self) -> None:
        calls: list[dict[str, object]] = []
        real = external_state.run_git

        def observed(*args: object, **kwargs: object):
            calls.append(dict(kwargs))
            return real(*args, **kwargs)

        with mock.patch.object(external_state, "run_git", side_effect=observed):
            found = ExternalStateStore.has_records(
                self.fixture.root,
                lab="p02",
                test_root=self.fixture.state_root,
            )
        self.assertFalse(found)
        self.assertFalse(self.fixture.state_root.exists())
        self.assertGreaterEqual(len(calls), 2)
        self.assertTrue(all(call.get("trust_local_config", False) is False for call in calls))
        self.assertTrue(
            all(call.get("validate_local_config", True) is False for call in calls)
        )

    def test_identity_is_exact_opaque_and_epoch_separated(self) -> None:
        first = self.fixture.store()
        identity = json.loads(first._identity_path.read_text(encoding="utf-8"))
        locator = repository_locator(self.fixture.root)
        self.assertEqual(
            set(identity),
            {
                "schema_version",
                "repository_id",
                "locator",
                "locator_source",
                "object_format",
                "academy_base_commit",
                "catalog_sha256",
            },
        )
        self.assertRegex(first.repository_id, r"^[0-9a-f]{32}$")
        self.assertEqual(identity["locator"], locator.digest)
        rendered = json.dumps(identity, sort_keys=True)
        self.assertNotIn(str(self.fixture.root), rendered)
        self.assertNotIn(str(self.fixture.state_root), rendered)
        with first.locked() as locked:
            locked.write_record("p02", 1, {"generation": 1, "value": "old"}, expected_generation=0)
        old_bytes = (first._epoch_dir / "p02/1/state.json").read_bytes()

        second = self.fixture.store(base_commit="c" * 40)
        self.assertNotEqual(first._epoch_dir, second._epoch_dir)
        self.assertEqual((first._epoch_dir / "p02/1/state.json").read_bytes(), old_bytes)
        self.assertFalse((second._epoch_dir / "p02/1/state.json").exists())

    def test_identity_corruption_unknown_keys_duplicates_and_oversize_fail_closed(self) -> None:
        store = self.fixture.store()
        original = store._identity_path.read_bytes()
        corruptions = {
            "truncated": b'{"schema_version":1',
            "duplicate": original.replace(b'"schema_version":1', b'"schema_version":1,"schema_version":1'),
            "unknown": original.replace(b"{", b'{"unknown":true,', 1),
            "oversize": b"{" + b" " * 65536 + b"}",
        }
        for name, payload in corruptions.items():
            with self.subTest(name=name):
                store._identity_path.write_bytes(payload)
                with self.assertRaises(ExternalStateError) as raised:
                    self.fixture.store()
                self.assertEqual(
                    raised.exception.code,
                    "state-too-large" if name == "oversize" else "state-corrupt",
                )
                self.assertNotIn(str(self.fixture.state_root), str(raised.exception))
                store._identity_path.write_bytes(original)

    def test_identity_immutable_binding_mismatch_fails_closed(self) -> None:
        store = self.fixture.store()
        identity = json.loads(store._identity_path.read_text(encoding="utf-8"))
        identity["catalog_sha256"] = "c" * 64
        store._identity_path.write_text(json.dumps(identity), encoding="utf-8")
        with self.assertRaises(ExternalStateError) as raised:
            self.fixture.store()
        self.assertEqual(raised.exception.code, "state-identity-mismatch")

    def test_nonempty_epoch_without_identity_fails_closed_and_is_byte_unchanged(self) -> None:
        store = self.fixture.store()
        store._identity_path.unlink()
        orphan = store._epoch_dir / "p02/1/state.json"
        orphan.parent.mkdir(parents=True)
        orphan.write_bytes(b'{"generation":1,"orphan":"preserve"}\n')
        before = {
            path.relative_to(store._epoch_dir).as_posix(): path.read_bytes()
            for path in store._epoch_dir.rglob("*")
            if path.is_file()
        }

        with self.assertRaises(ExternalStateError) as raised:
            self.fixture.store()

        self.assertEqual(raised.exception.code, "state-identity-mismatch")
        after = {
            path.relative_to(store._epoch_dir).as_posix(): path.read_bytes()
            for path in store._epoch_dir.rglob("*")
            if path.is_file()
        }
        self.assertEqual(after, before)
        self.assertFalse(store._identity_path.exists())


class ShallowRepositoryDirectoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = RepositoryFixture()
        self.addCleanup(self.fixture.close)
        self.store = self.fixture.store()
        self.repository_id = "c" * 64

    def _storage_id(self, attempt: int = 1) -> str:
        return hashlib.sha256(
            (
                "arbiter-academy/shallow-repository/v1\0"
                f"{self.store._locator_digest}\0{self.store._epoch_digest}\0"
                f"p02\0{attempt}\0{self.repository_id}\n"
            ).encode("ascii")
        ).hexdigest()

    def test_exact_storage_preimage_path_and_private_mode(self) -> None:
        expected_id = hashlib.sha256(
            b"arbiter-academy/shallow-repository/v1\0"
            + self.store._locator_digest.encode("ascii")
            + b"\0"
            + self.store._epoch_digest.encode("ascii")
            + b"\0p02\0"
            + b"1"
            + b"\0"
            + self.repository_id.encode("ascii")
            + b"\n"
        ).hexdigest()

        with self.store.locked() as locked:
            directory, created = locked.owned_repository_directory(
                "p02", 1, self.repository_id, create=True
            )

        self.assertTrue(created)
        self.assertEqual(directory, (self.store._state_root / "remotes" / expected_id).resolve())
        self.assertTrue(directory.is_dir())
        self.assertFalse(directory.is_symlink())
        if os.name != "nt":
            self.assertEqual(stat.S_IMODE(directory.stat().st_mode), 0o700)

    def test_locator_epoch_and_attempt_separate_storage(self) -> None:
        second_epoch = self.fixture.store(base_commit="d" * 40)
        with self.store.locked() as first_locked:
            first, _ = first_locked.owned_repository_directory("p02", 1, self.repository_id, create=True)
            next_attempt, _ = first_locked.owned_repository_directory("p02", 2, self.repository_id, create=True)
        with second_epoch.locked() as second_locked:
            second, _ = second_locked.owned_repository_directory("p02", 1, self.repository_id, create=True)
        self.assertNotEqual(first, second)
        self.assertNotEqual(first, next_attempt)

    def test_active_lock_lab_attempt_and_id_grammar_are_enforced(self) -> None:
        with self.store.locked() as locked:
            for lab, attempt, repository_id, code in (
                ("p08", 1, self.repository_id, "unsafe-state-path"),
                ("p02", 0, self.repository_id, "attempt-limit"),
                ("p02", 33, self.repository_id, "attempt-limit"),
                ("p02", True, self.repository_id, "attempt-limit"),
                ("p02", 1, "C" * 64, "unsafe-state-path"),
                ("p02", 1, "c" * 63, "unsafe-state-path"),
            ):
                with self.subTest(lab=lab, attempt=attempt, repository_id=repository_id):
                    with self.assertRaises(ExternalStateError) as raised:
                        locked.owned_repository_directory(lab, attempt, repository_id)
                    self.assertEqual(raised.exception.code, code)
        with self.assertRaises(ExternalStateError) as raised:
            locked.owned_repository_directory("p02", 1, self.repository_id)
        self.assertEqual(raised.exception.code, "state-busy")

    def test_missing_lookup_is_nonmutating_and_create_reports_atomic_ownership(self) -> None:
        remotes = self.store._state_root / "remotes"
        with self.store.locked() as locked:
            with self.assertRaises(ExternalStateError) as raised:
                locked.owned_repository_directory("p02", 1, self.repository_id)
            self.assertEqual(raised.exception.code, "state-missing")
            self.assertFalse(os.path.lexists(remotes))

            directory, created = locked.owned_repository_directory(
                "p02", 1, self.repository_id, create=True
            )
            same, created_again = locked.owned_repository_directory(
                "p02", 1, self.repository_id, create=True
            )

        self.assertTrue(created)
        self.assertFalse(created_again)
        self.assertEqual(directory, same)

    def test_existing_directory_is_not_chmod_normalized(self) -> None:
        with self.store.locked() as locked:
            directory, created = locked.owned_repository_directory(
                "p02", 1, self.repository_id, create=True
            )
            self.assertTrue(created)
            with mock.patch.object(external_state, "_set_private_mode") as normalized:
                same, created_again = locked.owned_repository_directory(
                    "p02", 1, self.repository_id, create=True
                )
        self.assertEqual(same, directory)
        self.assertFalse(created_again)
        normalized.assert_not_called()

    def test_redirected_remotes_ancestor_is_rejected_without_outside_mutation(self) -> None:
        outside = self.fixture.base / "outside-remotes"
        outside.mkdir()
        redirected = self.store._state_root / "remotes"
        if sys.platform == "win32":
            command = Path(os.environ["SystemRoot"]) / "System32/cmd.exe"
            created = subprocess.run(
                [str(command), "/d", "/v:off", "/c", "mklink", "/J", redirected.name, outside.name],
                cwd=self.store._state_root,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                check=False,
                timeout=10,
            )
            self.assertEqual(created.returncode, 0, (created.stdout + created.stderr)[:2048])
        else:
            os.symlink(outside, redirected, target_is_directory=True)
        self.addCleanup(RootResolutionTests._remove_redirect, redirected)

        with self.store.locked() as locked, self.assertRaises(ExternalStateError) as raised:
            locked.owned_repository_directory("p02", 1, self.repository_id, create=True)

        self.assertEqual(raised.exception.code, "unsafe-state-path")
        self.assertEqual(list(outside.iterdir()), [])

    def test_redirected_or_regular_file_final_entry_is_rejected_unchanged(self) -> None:
        remotes = self.store._state_root / "remotes"
        remotes.mkdir()
        final = remotes / self._storage_id()
        outside = self.fixture.base / "outside-final"
        outside.mkdir()
        if sys.platform == "win32":
            command = Path(os.environ["SystemRoot"]) / "System32/cmd.exe"
            created = subprocess.run(
                [str(command), "/d", "/v:off", "/c", "mklink", "/J", str(final.relative_to(self.fixture.base)), outside.name],
                cwd=self.fixture.base,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                check=False,
                timeout=10,
            )
            self.assertEqual(created.returncode, 0, (created.stdout + created.stderr)[:2048])
        else:
            os.symlink(outside, final, target_is_directory=True)
        with self.store.locked() as locked, self.assertRaises(ExternalStateError) as raised:
            locked.owned_repository_directory("p02", 1, self.repository_id, create=True)
        self.assertEqual(raised.exception.code, "unsafe-state-path")
        self.assertEqual(list(outside.iterdir()), [])
        RootResolutionTests._remove_redirect(final)

        final.write_bytes(b"preserve-final-file")
        before = final.read_bytes()
        with self.store.locked() as locked, self.assertRaises(ExternalStateError) as raised:
            locked.owned_repository_directory("p02", 1, self.repository_id, create=True)
        self.assertEqual(raised.exception.code, "unsafe-state-path")
        self.assertEqual(final.read_bytes(), before)

    def test_windows_length_failure_creates_no_remotes_ancestor(self) -> None:
        original_root = self.store._state_root
        original_entries = tuple(original_root.iterdir())
        overlong_root = Path("C:/" + "x" * 230)
        self.store._state_root = overlong_root
        try:
            with mock.patch.object(external_state.os, "name", "nt"):
                with self.store.locked() as locked, self.assertRaises(ExternalStateError) as raised:
                    locked.owned_repository_directory("p02", 1, self.repository_id, create=True)
            self.assertEqual(raised.exception.code, "unsafe-state-path")
            self.assertFalse(os.path.lexists(overlong_root))
            self.assertFalse(os.path.lexists(overlong_root / "remotes"))
            self.assertFalse((original_root / "remotes").exists())
            self.assertEqual(tuple(original_root.iterdir()), original_entries)
        finally:
            self.store._state_root = original_root

    def test_windows_length_budget_counts_utf16_astral_code_units(self) -> None:
        original_root = self.store._state_root
        astral_root = Path("C:/" + "\U0001f680" * 90)
        candidate = astral_root / "remotes" / self._storage_id()
        self.assertLessEqual(len(str(candidate)), 240)
        self.assertGreater(len(os.fspath(candidate).encode("utf-16-le")) // 2, 240)
        self.store._state_root = astral_root
        try:
            with mock.patch.object(external_state.os, "name", "nt"):
                with self.store.locked() as locked, self.assertRaises(ExternalStateError) as raised:
                    locked.owned_repository_directory("p02", 1, self.repository_id, create=True)
            self.assertEqual(raised.exception.code, "unsafe-state-path")
            self.assertFalse(os.path.lexists(astral_root))
            self.assertFalse(os.path.lexists(astral_root / "remotes"))
        finally:
            self.store._state_root = original_root

    @unittest.skipUnless(os.name == "nt", "Git for Windows shallow-path push coverage")
    def test_real_bare_repository_accepts_push_through_shallow_path(self) -> None:
        with self.store.locked() as locked:
            directory, _ = locked.owned_repository_directory(
                "p02", 1, self.repository_id, create=True
            )
        git(self.fixture.base, "init", "--bare", "--template=", str(directory))
        branch = "academy/P02-commit-review-pr/1"
        git(self.fixture.root, "push", directory.as_uri(), f"HEAD:refs/heads/{branch}")
        self.assertEqual(
            git(self.fixture.base, f"--git-dir={directory}", "rev-parse", f"refs/heads/{branch}"),
            git(self.fixture.root, "rev-parse", "HEAD"),
        )


class P08WorktreeParentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = RepositoryFixture()
        self.addCleanup(self.fixture.close)
        self.store = self.fixture.store()
        self.worktree_id = "d" * 64

    def _storage_id(self, *, store=None, attempt: int = 1, worktree_id: str | None = None) -> str:
        active_store = self.store if store is None else store
        identifier = self.worktree_id if worktree_id is None else worktree_id
        return hashlib.sha256(
            (
                "arbiter-academy/p08-worktree-parent/v1\0"
                f"{active_store._locator_digest}\0{active_store._epoch_digest}\0"
                f"p08\0{attempt}\0{identifier}\n"
            ).encode("ascii")
        ).hexdigest()[:32]

    def _set_windows_state_root_for_target_units(self, units: int) -> tuple[Path, Path]:
        suffix = Path("p08-worktrees") / self._storage_id() / self.worktree_id / ".git"
        prefix = self.fixture.base / "p08-units-"
        padding = units - len(os.fspath(prefix / suffix).encode("utf-16-le")) // 2
        self.assertGreaterEqual(padding, 1)
        root = Path(os.fspath(prefix) + "x" * padding)
        self.assertEqual(len(os.fspath(root / suffix).encode("utf-16-le")) // 2, units)
        root.mkdir(parents=True)
        original_root = self.store._state_root
        self.store._state_root = root
        self.addCleanup(setattr, self.store, "_state_root", original_root)
        return root, root / "p08-worktrees"

    def test_exact_preimage_determinism_leaf_and_internal_epoch_binding(self) -> None:
        expected_id = self._storage_id()
        with self.store.locked() as locked:
            parent = locked.owned_p08_worktree_parent(1, self.worktree_id)
            repeated = locked.owned_p08_worktree_parent(1, self.worktree_id)
            next_attempt = locked.owned_p08_worktree_parent(2, self.worktree_id)
            next_worktree = locked.owned_p08_worktree_parent(1, "e" * 64)

        self.assertEqual(parent, (self.store._state_root / "p08-worktrees" / expected_id).resolve())
        self.assertEqual(parent, repeated)
        self.assertEqual(len(parent.name), 32)
        self.assertNotEqual(parent, next_attempt)
        self.assertNotEqual(parent, next_worktree)
        self.assertTrue(parent.is_dir())
        self.assertFalse((parent / self.worktree_id).exists())
        self.assertEqual(
            tuple(inspect.signature(locked.owned_p08_worktree_parent).parameters),
            ("attempt", "worktree_id"),
        )

        later_epoch = self.fixture.store(base_commit="d" * 40)
        with later_epoch.locked() as locked:
            later_parent = locked.owned_p08_worktree_parent(1, self.worktree_id)
        self.assertNotEqual(parent, later_parent)

        other = RepositoryFixture()
        self.addCleanup(other.close)
        with other.store().locked() as locked:
            other_parent = locked.owned_p08_worktree_parent(1, self.worktree_id)
        self.assertNotEqual(parent, other_parent)

    def test_exact_240_utf16_target_plus_git_is_accepted_before_leaf_creation(self) -> None:
        _, p08_root = self._set_windows_state_root_for_target_units(240)
        with mock.patch.object(external_state.os, "name", "nt"):
            with self.store.locked() as locked:
                parent = locked.owned_p08_worktree_parent(1, self.worktree_id)
        self.assertTrue(parent.is_dir())
        self.assertFalse((parent / self.worktree_id).exists())
        self.assertTrue(p08_root.is_dir())

    def test_241_utf16_target_plus_git_fails_before_shallow_root_mutation(self) -> None:
        root, p08_root = self._set_windows_state_root_for_target_units(241)
        before = tuple(root.iterdir())
        with mock.patch.object(external_state.os, "name", "nt"):
            with self.store.locked() as locked, self.assertRaises(ExternalStateError) as raised:
                locked.owned_p08_worktree_parent(1, self.worktree_id)
        self.assertEqual(raised.exception.code, "unsafe-state-path")
        self.assertFalse(os.path.lexists(p08_root))
        self.assertEqual(tuple(root.iterdir()), before)

    def test_astral_utf16_overlength_fails_before_shallow_root_mutation(self) -> None:
        original_root = self.store._state_root
        astral_root = Path("C:/" + "\U0001f680" * 80)
        candidate = astral_root / "p08-worktrees" / self._storage_id() / self.worktree_id / ".git"
        self.assertLessEqual(len(os.fspath(candidate)), 240)
        self.assertGreater(len(os.fspath(candidate).encode("utf-16-le")) // 2, 240)
        self.store._state_root = astral_root
        try:
            with mock.patch.object(external_state.os, "name", "nt"):
                with self.store.locked() as locked, self.assertRaises(ExternalStateError) as raised:
                    locked.owned_p08_worktree_parent(1, self.worktree_id)
            self.assertEqual(raised.exception.code, "unsafe-state-path")
            self.assertFalse(os.path.lexists(astral_root))
            self.assertFalse(os.path.lexists(astral_root / "p08-worktrees"))
        finally:
            self.store._state_root = original_root

    def test_redirected_shallow_root_is_rejected_without_outside_mutation(self) -> None:
        outside = self.fixture.base / "outside-p08-worktrees"
        outside.mkdir()
        redirected = self.store._state_root / "p08-worktrees"
        if sys.platform == "win32":
            command = Path(os.environ["SystemRoot"]) / "System32/cmd.exe"
            created = subprocess.run(
                [str(command), "/d", "/v:off", "/c", "mklink", "/J", redirected.name, outside.name],
                cwd=self.store._state_root,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                check=False,
                timeout=10,
            )
            self.assertEqual(created.returncode, 0, (created.stdout + created.stderr)[:2048])
        else:
            os.symlink(outside, redirected, target_is_directory=True)
        self.addCleanup(RootResolutionTests._remove_redirect, redirected)

        with self.store.locked() as locked, self.assertRaises(ExternalStateError) as raised:
            locked.owned_p08_worktree_parent(1, self.worktree_id)
        self.assertEqual(raised.exception.code, "unsafe-state-path")
        self.assertEqual(tuple(outside.iterdir()), ())

    def test_deep_record_and_p02_storage_are_preserved(self) -> None:
        with self.store.locked() as locked:
            locked.write_record("p08", 1, {"generation": 1, "value": "deep-record"}, expected_generation=0)
            p02, created = locked.owned_repository_directory("p02", 1, "c" * 64, create=True)
            before = (self.store._epoch_dir / "p08/1/state.json").read_bytes()
            parent = locked.owned_p08_worktree_parent(1, self.worktree_id)
            after = (self.store._epoch_dir / "p08/1/state.json").read_bytes()
            repeated_p02, created_again = locked.owned_repository_directory("p02", 1, "c" * 64, create=True)
        self.assertEqual(before, after)
        self.assertEqual(p02, repeated_p02)
        self.assertTrue(created)
        self.assertFalse(created_again)
        self.assertEqual(parent.parent.parent, self.store._state_root)
        self.assertFalse(str(parent).startswith(str(self.store._epoch_dir)))


class RecordAndAtomicityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = RepositoryFixture()
        self.addCleanup(self.fixture.close)
        self.store = self.fixture.store()

    def test_create_update_read_and_generation_mismatch(self) -> None:
        with self.store.locked() as locked:
            self.assertIsNone(locked.read_record("p02", 1))
            locked.write_record("p02", 1, {"value": "created", "generation": 1}, expected_generation=0)
            self.assertEqual(locked.read_record("p02", 1), {"generation": 1, "value": "created"})
            before = (self.store._epoch_dir / "p02/1/state.json").read_bytes()
            with self.assertRaises(ExternalStateError) as raised:
                locked.write_record("p02", 1, {"generation": 3}, expected_generation=1)
            self.assertEqual(raised.exception.code, "generation-mismatch")
            self.assertEqual((self.store._epoch_dir / "p02/1/state.json").read_bytes(), before)
            locked.write_record("p02", 1, {"generation": 2, "value": "updated"}, expected_generation=1)
            self.assertEqual(locked.read_record("p02", 1)["value"], "updated")

        expected = b'{"generation":2,"value":"updated"}\n'
        self.assertEqual((self.store._epoch_dir / "p02/1/state.json").read_bytes(), expected)

    def test_invalid_lab_attempt_control_and_size_are_rejected_before_mutation(self) -> None:
        before = sorted(str(path.relative_to(self.store._epoch_dir)) for path in self.store._epoch_dir.rglob("*"))
        cases = (
            ("../p02", 1, {"generation": 1}, 0, "unsafe-state-path"),
            ("p03", 1, {"generation": 1}, 0, "unsafe-state-path"),
            ("p02", 0, {"generation": 1}, 0, "attempt-limit"),
            ("p02", 33, {"generation": 1}, 0, "attempt-limit"),
            ("p02", True, {"generation": 1}, 0, "attempt-limit"),
            ("p02", 1, {"generation": 1, "bad": "line\nfeed"}, 0, "state-corrupt"),
        )
        with self.store.locked() as locked:
            for lab, attempt, record, expected_generation, code in cases:
                with self.subTest(lab=lab, attempt=attempt, code=code):
                    with self.assertRaises(ExternalStateError) as raised:
                        locked.write_record(lab, attempt, record, expected_generation=expected_generation)
                    self.assertEqual(raised.exception.code, code)
            for ceiling in (0, 65537, True, 1.5):
                with self.subTest(ceiling=ceiling):
                    with self.assertRaises(ExternalStateError) as raised:
                        locked.read_record("p02", 1, max_bytes=ceiling)  # type: ignore[arg-type]
                    self.assertEqual(raised.exception.code, "state-too-large")
            with self.assertRaises(ExternalStateError) as raised:
                locked.write_record(
                    "p02", 1, {"generation": 1, "payload": "x" * 80}, expected_generation=0, max_bytes=64
                )
            self.assertEqual(raised.exception.code, "state-too-large")
        after = sorted(str(path.relative_to(self.store._epoch_dir)) for path in self.store._epoch_dir.rglob("*"))
        self.assertEqual(after, before)

    def test_corrupt_duplicate_nonobject_and_oversize_records_are_rejected(self) -> None:
        path = self.store._epoch_dir / "p08/1/state.json"
        path.parent.mkdir(parents=True)
        payloads = (
            b'{"generation":1',
            b'{"generation":1,"generation":1}\n',
            b"[]\n",
            b'{"generation":1.0}\n',
            b'{"generation":1,"text":"\\u0000"}\n',
            b"{" + b" " * 65536 + b"}",
        )
        with self.store.locked() as locked:
            for payload in payloads:
                with self.subTest(payload=payload[:30]):
                    path.write_bytes(payload)
                    with self.assertRaises(ExternalStateError) as raised:
                        locked.read_record("p08", 1)
                    self.assertIn(raised.exception.code, {"state-corrupt", "state-too-large"})

    def test_atomic_failure_preserves_bytes_and_cleans_only_owned_temp(self) -> None:
        with self.store.locked() as locked:
            locked.write_record("p02", 1, {"generation": 1, "value": "before"}, expected_generation=0)
            record_path = self.store._epoch_dir / "p02/1/state.json"
            before = record_path.read_bytes()
            unrelated = record_path.parent / ".state.json.unrelated.tmp"
            unrelated.write_bytes(b"keep")
            with mock.patch.object(external_state.os, "replace", side_effect=OSError("private path")):
                with self.assertRaises(ExternalStateError) as raised:
                    locked.write_record(
                        "p02", 1, {"generation": 2, "value": "after"}, expected_generation=1
                    )
            self.assertEqual(raised.exception.code, "state-corrupt")
            self.assertNotIn("private path", str(raised.exception))
            self.assertEqual(record_path.read_bytes(), before)
            self.assertEqual(unrelated.read_bytes(), b"keep")
            owned = [path for path in record_path.parent.iterdir() if path.name.startswith(".state.json.")]
            self.assertEqual(owned, [unrelated])

    def test_every_post_replace_failure_restores_old_bytes_and_cleans_owned_temps(self) -> None:
        real_set_private_mode = external_state._set_private_mode

        for attempt, failure_point in ((1, "mode-verification"), (2, "parent-fsync")):
            with self.subTest(failure_point=failure_point):
                with self.store.locked() as locked:
                    locked.write_record(
                        "p08", attempt, {"generation": 1, "value": "before"}, expected_generation=0
                    )
                    record_path = self.store._epoch_dir / f"p08/{attempt}/state.json"
                    before = record_path.read_bytes()
                    unrelated = record_path.parent / ".state.json.unrelated.tmp"
                    unrelated.write_bytes(b"keep")

                    if failure_point == "mode-verification":
                        def fail_record_mode(path: Path, *, directory: bool) -> None:
                            if path == record_path:
                                raise OSError("private post-replace mode failure")
                            real_set_private_mode(path, directory=directory)

                        injection = mock.patch.object(
                            external_state, "_set_private_mode", side_effect=fail_record_mode
                        )
                    else:
                        injection = mock.patch.object(
                            external_state,
                            "_fsync_parent",
                            side_effect=OSError("private post-replace fsync failure"),
                            create=True,
                        )
                    with injection:
                        with self.assertRaises(ExternalStateError) as raised:
                            locked.write_record(
                                "p08",
                                attempt,
                                {"generation": 2, "value": "after"},
                                expected_generation=1,
                            )
                    self.assertEqual(raised.exception.code, "state-corrupt")
                    self.assertNotIn("private", str(raised.exception))
                    self.assertEqual(record_path.read_bytes(), before)
                    self.assertEqual(unrelated.read_bytes(), b"keep")
                    owned = [
                        path
                        for path in record_path.parent.iterdir()
                        if path.name.startswith(".state.json.")
                    ]
                    self.assertEqual(owned, [unrelated])

    def test_read_rejects_a_redirected_record_ancestor(self) -> None:
        outside = self.store._epoch_dir / "outside-attempts"
        record = outside / "1/state.json"
        record.parent.mkdir(parents=True)
        record.write_bytes(b'{"generation":1}\n')
        redirected = self.store._epoch_dir / "p02"
        if sys.platform == "win32":
            command = Path(os.environ["SystemRoot"]) / "System32/cmd.exe"
            created = subprocess.run(
                [str(command), "/d", "/v:off", "/c", "mklink", "/J", "p02", "outside-attempts"],
                cwd=self.store._epoch_dir,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                check=False,
                timeout=10,
            )
            self.assertEqual(created.returncode, 0, (created.stdout + created.stderr)[:2048])
        else:
            os.symlink(outside, redirected, target_is_directory=True)
        self.addCleanup(RootResolutionTests._remove_redirect, redirected)

        with self.store.locked() as locked:
            with self.assertRaises(ExternalStateError) as raised:
                locked.read_record("p02", 1)
        self.assertEqual(raised.exception.code, "unsafe-state-path")

    @unittest.skipIf(os.name == "nt", "POSIX mode proof")
    def test_posix_directories_and_files_are_private(self) -> None:
        with self.store.locked() as locked:
            locked.write_record("p02", 1, {"generation": 1}, expected_generation=0)
        for path in self.fixture.state_root.rglob("*"):
            mode = stat.S_IMODE(path.stat().st_mode)
            self.assertEqual(mode & 0o077, 0, path)
            self.assertEqual(mode, 0o700 if path.is_dir() else 0o600, path)
        record = self.store._epoch_dir / "p02/1/state.json"
        os.chmod(record, 0o644)
        with self.store.locked() as locked:
            with self.assertRaises(ExternalStateError) as raised:
                locked.read_record("p02", 1)
        self.assertEqual(raised.exception.code, "unsafe-state-path")


class LockingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = RepositoryFixture()
        self.addCleanup(self.fixture.close)
        self.store = self.fixture.store()

    def test_same_process_contention_is_bounded(self) -> None:
        second = self.fixture.store()
        with self.store.locked():
            started = time.monotonic()
            with self.assertRaises(ExternalStateError) as raised:
                with second.locked(timeout_seconds=0.05):
                    self.fail("contended lock acquired")
            elapsed = time.monotonic() - started
        self.assertEqual(raised.exception.code, "state-busy")
        self.assertGreaterEqual(elapsed, 0.04)
        self.assertLess(elapsed, 1.0)

    @unittest.skipUnless(os.name == "nt", "Windows byte-range lock semantics")
    def test_windows_lock_initializes_only_new_storage_and_rejects_existing_malformed_bytes_unchanged(self) -> None:
        new_lock = self.fixture.base / "new-private-lock"
        with external_state._AdvisoryLock(new_lock, 0.1):
            pass
        self.assertEqual(new_lock.read_bytes(), b"\0")

        valid_before = self.store._lock_path.read_bytes()
        valid_mtime = self.store._lock_path.stat().st_mtime_ns
        with self.store.locked(timeout_seconds=0.1):
            pass
        self.assertEqual(self.store._lock_path.read_bytes(), valid_before)
        self.assertEqual(self.store._lock_path.stat().st_mtime_ns, valid_mtime)

        for malformed in (b"", b"\0\0", b"partial"):
            with self.subTest(malformed=malformed):
                self.store._lock_path.write_bytes(malformed)
                before = self.store._lock_path.read_bytes()
                before_mtime = self.store._lock_path.stat().st_mtime_ns
                with self.assertRaises(ExternalStateError) as raised:
                    with self.store.locked(timeout_seconds=0.1):
                        self.fail("malformed existing lock acquired")
                self.assertEqual(raised.exception.code, "state-busy")
                self.assertNotIn(str(self.fixture.state_root), str(raised.exception))
                self.assertEqual(self.store._lock_path.read_bytes(), before)
                self.assertEqual(self.store._lock_path.stat().st_mtime_ns, before_mtime)

    def test_nonfinite_and_overflowing_timeouts_fail_promptly_with_stable_code(self) -> None:
        second = self.fixture.store()
        values = (("nan", float("nan")), ("positive-infinity", float("inf")), ("overflow", 10**10_000))
        for label, value in values:
            with self.subTest(value=label):
                outcomes: list[object] = []

                def contend() -> None:
                    try:
                        with second.locked(timeout_seconds=value):  # type: ignore[arg-type]
                            outcomes.append("acquired")
                    except BaseException as error:
                        outcomes.append(error)

                with self.store.locked():
                    thread = threading.Thread(target=contend, daemon=True)
                    started = time.monotonic()
                    thread.start()
                    thread.join(timeout=0.2)
                    completed_while_contended = not thread.is_alive()
                    elapsed = time.monotonic() - started
                thread.join(timeout=1.0)

                self.assertTrue(completed_while_contended, "invalid timeout did not fail while contended")
                self.assertLess(elapsed, 0.75)
                self.assertEqual(len(outcomes), 1)
                self.assertIsInstance(outcomes[0], ExternalStateError)
                error = outcomes[0]
                assert isinstance(error, ExternalStateError)
                self.assertEqual(error.code, "state-busy")
                self.assertNotIn(str(self.fixture.state_root), str(error))

    def test_retained_locked_state_cannot_read_or_write_after_context_exit(self) -> None:
        with self.store.locked() as locked:
            locked.write_record("p02", 1, {"generation": 1}, expected_generation=0)
            retained = locked
        record_path = self.store._epoch_dir / "p02/1/state.json"
        before = record_path.read_bytes()

        with self.assertRaises(ExternalStateError) as read_error:
            retained.read_record("p02", 1)
        with self.assertRaises(ExternalStateError) as write_error:
            retained.write_record("p02", 1, {"generation": 2}, expected_generation=1)
        with self.assertRaises(ExternalStateError) as directory_error:
            retained.owned_directory("p02", 1, "bare")

        self.assertEqual(read_error.exception.code, "state-busy")
        self.assertEqual(write_error.exception.code, "state-busy")
        self.assertEqual(directory_error.exception.code, "state-busy")
        self.assertEqual(record_path.read_bytes(), before)

    def test_locked_state_cannot_be_constructed_without_lock_capability(self) -> None:
        with self.assertRaises(ExternalStateError) as raised:
            LockedExternalState(self.store)
        self.assertEqual(raised.exception.code, "state-busy")
        self.assertNotIn(str(self.fixture.state_root), str(raised.exception))

    def test_locked_owned_directory_creates_exact_contained_p02_and_p08_paths(self) -> None:
        with self.store.locked() as locked:
            p02 = locked.owned_directory("p02", 1, "bare", "origin-0123.git")
            p08 = locked.owned_directory("p08", 32, "worktrees", "worktree-4567")

        self.assertEqual(
            p02,
            (self.store._epoch_dir / "p02/1/bare/origin-0123.git").resolve(strict=True),
        )
        self.assertEqual(
            p08,
            (self.store._epoch_dir / "p08/32/worktrees/worktree-4567").resolve(strict=True),
        )
        self.assertTrue(p02.is_absolute())
        self.assertTrue(p08.is_absolute())
        self.assertTrue(p02.is_dir())
        self.assertTrue(p08.is_dir())
        if os.name != "nt":
            for directory in (p02, *p02.parents[:3], p08, *p08.parents[:3]):
                self.assertEqual(stat.S_IMODE(directory.stat().st_mode), 0o700)

    def test_owned_directory_rejects_invalid_reserved_and_separator_components_before_mutation(self) -> None:
        invalid_components = (
            (),
            (".",),
            ("..",),
            ("slash/name",),
            ("back\\name",),
            ("c:",),
            ("control\x00",),
            ("Upper",),
            ("con",),
            ("con.txt",),
            ("name.",),
            ("name ",),
            ("x" * 65,),
            ("one", "two", "three", "four", "five"),
        )
        with self.store.locked() as locked:
            before = sorted(path.relative_to(self.store._epoch_dir).as_posix() for path in self.store._epoch_dir.rglob("*"))
            for components in invalid_components:
                with self.subTest(components=components):
                    with self.assertRaises(ExternalStateError) as raised:
                        locked.owned_directory("p02", 2, *components)
                    self.assertEqual(raised.exception.code, "unsafe-state-path")
                    after = sorted(
                        path.relative_to(self.store._epoch_dir).as_posix()
                        for path in self.store._epoch_dir.rglob("*")
                    )
                    self.assertEqual(after, before)

    def test_owned_directory_rejects_redirected_ancestor_and_final_file_before_target_mutation(self) -> None:
        attempt = self.store._epoch_dir / "p02/3"
        attempt.mkdir(parents=True)
        outside = self.store._epoch_dir / "outside-owned"
        outside.mkdir()
        redirected = attempt / "redirected"
        if sys.platform == "win32":
            command = Path(os.environ["SystemRoot"]) / "System32/cmd.exe"
            created = subprocess.run(
                [
                    str(command),
                    "/d",
                    "/v:off",
                    "/c",
                    "mklink",
                    "/J",
                    "p02\\3\\redirected",
                    "outside-owned",
                ],
                cwd=self.store._epoch_dir,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                check=False,
                timeout=10,
            )
            self.assertEqual(created.returncode, 0, (created.stdout + created.stderr)[:2048])
        else:
            os.symlink(outside, redirected, target_is_directory=True)
        self.addCleanup(RootResolutionTests._remove_redirect, redirected)
        final_file = self.store._epoch_dir / "p08/4/worktrees"
        final_file.parent.mkdir(parents=True)
        final_file.write_bytes(b"preserve")

        with self.store.locked() as locked:
            with self.assertRaises(ExternalStateError) as redirect_error:
                locked.owned_directory("p02", 3, "redirected", "child")
            with self.assertRaises(ExternalStateError) as file_error:
                locked.owned_directory("p08", 4, "worktrees")

        self.assertEqual(redirect_error.exception.code, "unsafe-state-path")
        self.assertEqual(file_error.exception.code, "unsafe-state-path")
        self.assertEqual(list(outside.iterdir()), [])
        self.assertEqual(final_file.read_bytes(), b"preserve")

    def test_independent_process_contention_and_process_death_release(self) -> None:
        code = (
            "import sys\n"
            "from pathlib import Path\n"
            "from academy_engine.external_state import ExternalStateStore\n"
            "s=ExternalStateStore.open(Path(sys.argv[1]),academy_base_commit=sys.argv[3],"
            "catalog_sha256=sys.argv[4],test_root=Path(sys.argv[2]))\n"
            "with s.locked():\n"
            " print('READY',flush=True)\n"
            " sys.stdin.buffer.read()\n"
        )
        process = subprocess.Popen(
            [
                sys.executable,
                "-c",
                code,
                str(self.fixture.root),
                str(self.fixture.state_root),
                BASE_COMMIT,
                CATALOG_SHA256,
            ],
            cwd=Path(__file__).resolve().parents[1],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.addCleanup(self._terminate, process)
        assert process.stdout is not None
        self.assertEqual(process.stdout.readline().strip(), "READY")
        with self.assertRaises(ExternalStateError) as raised:
            with self.store.locked(timeout_seconds=0.05):
                self.fail("independent-process lock acquired")
        self.assertEqual(raised.exception.code, "state-busy")

        process.kill()
        process.wait(timeout=5)
        with self.store.locked(timeout_seconds=0.5) as locked:
            self.assertEqual(locked.repository_id, self.store.repository_id)

    @staticmethod
    def _terminate(process: subprocess.Popen[str]) -> None:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        for stream in (process.stdin, process.stdout, process.stderr):
            if stream is not None:
                stream.close()


if __name__ == "__main__":
    unittest.main()
