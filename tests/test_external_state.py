from __future__ import annotations

import hashlib
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
        candidates.append(("file", file_root, "invalid-state-root"))

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
            repository_locator(self.fixture.root)
        self.assertGreaterEqual(len(calls), 2)
        self.assertTrue(all(call.get("trust_local_config", False) is False for call in calls))

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
