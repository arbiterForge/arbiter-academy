from __future__ import annotations

import hashlib
import inspect
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import academy_engine.exercise_state as exercise_module
from academy_engine.checkpoints import (
    Predicate,
    _Attempt,
    _SemanticContext,
    _valid_offline_p02_receipt,
)
from academy_engine.catalog import Catalog
from academy_engine.exercise_state import (
    ExerciseStateError,
    P08LiveRef,
    P08LiveState,
    P08LiveWorktree,
    _bare,
    _decode_p02_record,
    _decode_p08_record,
    _exact_patch_result,
    _object_format,
    _p02_repository_id,
    _p08_worktree_id,
    _p08_live_state_digest,
    _parse_p02_receipt,
    _parse_p02_receipt_bytes,
    _prepare_bare,
    _reachable_ids,
    _require_complete_object_set,
    _verified_epoch,
    _verified_p08_epoch,
    preflight_p08,
    prepare_p08,
    has_active_p02,
    open_existing_p02_store,
    open_p02_store,
    open_p08_store,
    prepare_p02,
    restore_p02,
    validate_p02_checkpoint,
    verify_p02,
    P02AttemptIdentity,
)
from academy_engine.external_state import ExternalStateError
from academy_engine.scenario import PreparationError, prepare_lab


SOURCE = Path(__file__).resolve().parents[1]


def git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=root, text=True, encoding="utf-8",
        capture_output=True, check=check,
    )


class P02StateContractTests(unittest.TestCase):
    def test_repository_ids_use_the_frozen_domain_separated_preimage(self) -> None:
        repository_id = "0123456789abcdef0123456789abcdef"
        expected = hashlib.sha256(
            b"arbiter-academy/p02-repository-id/v1\0"
            + repository_id.encode("ascii")
            + b"\0P02-commit-review-pr\0"
            + b"1"
            + b"\0learner\n"
        ).hexdigest()

        self.assertEqual(_p02_repository_id(repository_id, 1, "learner"), expected)

    def test_record_schema_rejects_unknown_keys_and_boolean_attempts(self) -> None:
        minimal = {
            "schema_version": 1,
            "generation": 1,
            "lab": "P02-commit-review-pr",
            "attempt": True,
            "phase": "captured",
            "base_branch": "main",
            "base_head": "a" * 40,
            "attempt_branch": "academy/P02-commit-review-pr/1",
            "prepared_commit": None,
            "archive_ref": None,
            "archive_target": None,
            "transition_target": None,
            "original_topology": {
                "config": {
                    "remote.origin.url": ["https://github.com/learner/arbiter-academy.git"],
                    "remote.origin.pushurl": None,
                    "remote.upstream.url": ["https://github.com/arbiterForge/arbiter-academy.git"],
                    "remote.upstream.pushurl": ["DISABLED"],
                    "remote.pushDefault": None,
                    "push.default": None,
                    "branch.main.remote": None,
                    "branch.main.pushRemote": None,
                },
                "effective_routes": {
                    "origin": {"fetch": ["https://github.com/learner/arbiter-academy.git"], "push": ["https://github.com/learner/arbiter-academy.git"]},
                    "upstream": {"fetch": ["https://github.com/arbiterForge/arbiter-academy.git"], "push": ["DISABLED"]},
                },
            },
            "origin_repository": None,
            "upstream_repository": None,
        }

        with self.assertRaisesRegex(ExerciseStateError, "invalid"):
            _decode_p02_record(minimal, object_format="sha1")
        minimal["attempt"] = 1
        minimal["schema_version"] = True
        with self.assertRaisesRegex(ExerciseStateError, "invalid"):
            _decode_p02_record(minimal, object_format="sha1")
        minimal["schema_version"] = 1
        minimal["unexpected"] = "value"
        with self.assertRaisesRegex(ExerciseStateError, "invalid"):
            _decode_p02_record(minimal, object_format="sha1")

    def test_offline_receipt_rejects_hosted_mode_and_unknown_keys(self) -> None:
        receipt = {
            "schema_version": 1,
            "mode": "github",
            "lab_id": "P02-commit-review-pr",
            "attempt": 1,
            "branch": "academy/P02-commit-review-pr/1",
            "prepared_commit": "a" * 40,
            "work_head": "b" * 40,
            "pushed_tip": "b" * 40,
            "commits": ["b" * 40],
            "review": {"status": "cleared"},
            "repositories": {
                "origin": {"repository_id": "c" * 64, "role": "learner"},
                "upstream": {"repository_id": "d" * 64, "role": "official"},
            },
            "pr_reference": "local-pr:" + "b" * 12,
        }

        with self.assertRaisesRegex(ExerciseStateError, "evidence"):
            _parse_p02_receipt(receipt, object_format="sha1")
        receipt["mode"] = "offline-local"
        receipt["hosted_check"] = True
        with self.assertRaisesRegex(ExerciseStateError, "evidence"):
            _parse_p02_receipt(receipt, object_format="sha1")

    def test_receipt_bytes_reject_duplicate_keys(self) -> None:
        raw = b'{"schema_version":1,"schema_version":1}'
        with self.assertRaisesRegex(ExerciseStateError, "evidence"):
            _parse_p02_receipt_bytes(raw, object_format="sha1")

    def test_receipt_rejects_each_frozen_semantic_mismatch(self) -> None:
        valid = {
            "schema_version": 1,
            "mode": "offline-local",
            "lab_id": "P02-commit-review-pr",
            "attempt": 1,
            "branch": "academy/P02-commit-review-pr/1",
            "prepared_commit": "a" * 40,
            "work_head": "b" * 40,
            "pushed_tip": "b" * 40,
            "commits": ["b" * 40],
            "review": {"status": "cleared"},
            "repositories": {
                "origin": {"repository_id": "c" * 64, "role": "learner"},
                "upstream": {"repository_id": "d" * 64, "role": "official"},
            },
            "pr_reference": "local-pr:" + "b" * 12,
        }
        mutations = (
            ("boolean schema", lambda value: value.update(schema_version=True)),
            ("wrong branch", lambda value: value.update(branch="academy/P02-commit-review-pr/2")),
            ("uncleared review", lambda value: value.update(review={"status": "pending"})),
            (
                "wrong origin role",
                lambda value: value["repositories"]["origin"].update(role="official"),
            ),
            (
                "wrong upstream role",
                lambda value: value["repositories"]["upstream"].update(role="learner"),
            ),
            ("wrong receipt reference", lambda value: value.update(pr_reference="local-pr:000000000000")),
        )

        for label, mutate in mutations:
            with self.subTest(label=label):
                candidate = json.loads(json.dumps(valid))
                mutate(candidate)
                with self.assertRaisesRegex(ExerciseStateError, "evidence"):
                    _parse_p02_receipt(candidate, object_format="sha1")


class P08StateContractTests(unittest.TestCase):
    REPOSITORY_ID = "0" * 32

    @staticmethod
    def _record() -> dict[str, object]:
        base = "a" * 40
        attempt_ref = "refs/heads/academy/P08-repository-hygiene/1"
        namespace = "refs/heads/academy-fixtures/p08/1/"
        current_id = _p08_worktree_id(P08StateContractTests.REPOSITORY_ID, 1, "current-attempt")
        merged_id = _p08_worktree_id(P08StateContractTests.REPOSITORY_ID, 1, "merged-clean")
        dirty_id = _p08_worktree_id(P08StateContractTests.REPOSITORY_ID, 1, "dirty-unmerged")
        return {
            "schema_version": 1,
            "generation": 1,
            "lab_id": "P08-repository-hygiene",
            "attempt": 1,
            "phase": "creating-attempt",
            "namespace": namespace,
            "base_ref": "refs/heads/main",
            "base_oid": base,
            "attempt_ref": attempt_ref,
            "prepared_oid": None,
            "refs": [
                {"ref_name": "refs/heads/main", "object_id": base, "role": "selected-base", "binding": "fixed"},
                {"ref_name": attempt_ref, "object_id": None, "role": "current-attempt", "binding": "learner-descendant"},
                {"ref_name": namespace + "merged-clean", "object_id": base, "role": "merged-clean", "binding": "fixed"},
                {"ref_name": namespace + "dirty-unmerged", "object_id": None, "role": "dirty-unmerged", "binding": "fixed"},
                {"ref_name": namespace + "unique-unmerged", "object_id": None, "role": "unique-unmerged", "binding": "fixed"},
            ],
            "worktrees": [
                {"worktree_id": current_id, "path_sha256": "b" * 64, "git_admin_id": None, "branch_ref": attempt_ref, "head_oid": None, "expected_presence": True, "role": "current-attempt", "dirty_status_sha256": None},
                {"worktree_id": merged_id, "path_sha256": None, "git_admin_id": merged_id, "branch_ref": namespace + "merged-clean", "head_oid": base, "expected_presence": True, "role": "merged-clean", "dirty_status_sha256": None},
                {"worktree_id": dirty_id, "path_sha256": None, "git_admin_id": dirty_id, "branch_ref": namespace + "dirty-unmerged", "head_oid": None, "expected_presence": True, "role": "dirty-unmerged", "dirty_status_sha256": None},
            ],
        }

    def test_worktree_ids_use_the_frozen_domain_separated_preimage(self) -> None:
        repository_id = "0123456789abcdef0123456789abcdef"
        expected = hashlib.sha256(
            b"arbiter-academy/p08-worktree-id/v1\0"
            + repository_id.encode("ascii")
            + b"\0P08-repository-hygiene\0"
            + b"1\0merged-clean\n"
        ).hexdigest()

        self.assertEqual(
            _p08_worktree_id(repository_id, 1, "merged-clean"),
            expected,
        )
        ref = P08LiveRef(
            ref_name="refs/heads/main",
            role="selected-base",
            observation_oid="a" * 40,
            live_oid="a" * 40,
            worktree_state="clean",
            merged_into_base=True,
            unique_commits=0,
            classification="base",
            recommendation="preserve",
        )
        worktree = P08LiveWorktree(
            worktree_id="b" * 64,
            role="current-attempt",
            branch_ref="refs/heads/academy/P08-repository-hygiene/1",
            observation_oid="a" * 40,
            live_oid="a" * 40,
            dirty=False,
            classification="current-attempt",
            recommendation="preserve",
        )
        state = P08LiveState(
            repository_id=repository_id,
            base_ref="refs/heads/main",
            base_oid="a" * 40,
            attempt_ref="refs/heads/academy/P08-repository-hygiene/1",
            prepared_oid="a" * 40,
            observation_oid="a" * 40,
            live_head_oid="a" * 40,
            refs=(ref,),
            worktrees=(worktree,),
            state_digest="c" * 64,
        )
        self.assertEqual(state.refs[0].role, "selected-base")
        self.assertFalse(state.worktrees[0].dirty)
        self.assertEqual(
            _p08_live_state_digest(state),
            "012c38e5e09024c1c4a10a6b982b1fd7faca07affdf1fa19c2623b411430aa92",
        )

    def test_record_schema_rejects_unknown_keys_and_boolean_attempts(self) -> None:
        record = {
            "schema_version": 1,
            "generation": 1,
            "lab_id": "P08-repository-hygiene",
            "attempt": True,
            "phase": "creating-attempt",
            "namespace": "refs/heads/academy-fixtures/p08/1/",
            "base_ref": "refs/heads/main",
            "base_oid": "a" * 40,
            "attempt_ref": "refs/heads/academy/P08-repository-hygiene/1",
            "prepared_oid": None,
            "refs": [],
            "worktrees": [],
        }

        with self.assertRaisesRegex(ExerciseStateError, "invalid"):
            _decode_p08_record(record, object_format="sha1", repository_id=self.REPOSITORY_ID)

    def test_record_requires_exact_role_order_and_nested_keys(self) -> None:
        record = self._record()
        self.assertEqual(
            _decode_p08_record(record, object_format="sha1", repository_id=self.REPOSITORY_ID)["refs"][0]["role"],
            "selected-base",
        )
        truncated = self._record()
        truncated["refs"] = truncated["refs"][:-1]
        with self.assertRaisesRegex(ExerciseStateError, "invalid"):
            _decode_p08_record(truncated, object_format="sha1", repository_id=self.REPOSITORY_ID)
        malformed = self._record()
        malformed["worktrees"][1]["extra"] = "not-allowed"
        with self.assertRaisesRegex(ExerciseStateError, "invalid"):
            _decode_p08_record(malformed, object_format="sha1", repository_id=self.REPOSITORY_ID)
        record["attempt"] = 1
        record["unexpected"] = "value"
        with self.assertRaisesRegex(ExerciseStateError, "invalid"):
            _decode_p08_record(record, object_format="sha1", repository_id=self.REPOSITORY_ID)

    def test_record_rejects_boolean_schema_and_worktree_identity_rebinding(self) -> None:
        boolean_schema = self._record()
        boolean_schema["schema_version"] = True
        with self.assertRaisesRegex(ExerciseStateError, "invalid"):
            _decode_p08_record(
                boolean_schema, object_format="sha1", repository_id=self.REPOSITORY_ID
            )
        duplicate = self._record()
        duplicate["worktrees"][2]["worktree_id"] = duplicate["worktrees"][1]["worktree_id"]
        duplicate["worktrees"][2]["git_admin_id"] = duplicate["worktrees"][1]["git_admin_id"]
        with self.assertRaisesRegex(ExerciseStateError, "invalid"):
            _decode_p08_record(
                duplicate, object_format="sha1", repository_id=self.REPOSITORY_ID
            )
        rebound = self._record()
        rebound_id = _p08_worktree_id(self.REPOSITORY_ID, 1, "dirty-unmerged")
        rebound["worktrees"][1]["worktree_id"] = rebound_id
        rebound["worktrees"][1]["git_admin_id"] = rebound_id
        with self.assertRaisesRegex(ExerciseStateError, "invalid"):
            _decode_p08_record(
                rebound, object_format="sha1", repository_id=self.REPOSITORY_ID
            )

    def test_creating_attempt_rejects_a_prepared_commit_identity(self) -> None:
        record = self._record()
        record["prepared_oid"] = "a" * 40
        with self.assertRaisesRegex(ExerciseStateError, "invalid"):
            _decode_p08_record(
                record, object_format="sha1", repository_id=self.REPOSITORY_ID
            )

    def test_record_translates_unhashable_phase_to_stable_error(self) -> None:
        for malformed_phase in ([], {}):
            with self.subTest(malformed_phase=type(malformed_phase).__name__):
                record = self._record()
                record["phase"] = malformed_phase
                with self.assertRaisesRegex(ExerciseStateError, "invalid"):
                    _decode_p08_record(
                        record, object_format="sha1", repository_id=self.REPOSITORY_ID
                    )

    def test_record_translates_non_string_repository_identity_to_stable_error(self) -> None:
        for malformed_repository_id in (None, True, 0, []):
            with self.subTest(repository_id=repr(malformed_repository_id)):
                with self.assertRaisesRegex(ExerciseStateError, "invalid"):
                    _decode_p08_record(
                        self._record(),
                        object_format="sha1",
                        repository_id=malformed_repository_id,
                    )

    def test_worktree_id_translates_non_string_repository_identity_to_stable_error(self) -> None:
        with self.assertRaisesRegex(ExerciseStateError, "invalid"):
            _p08_worktree_id(None, 1, "current-attempt")

    def test_public_digest_canonicalizes_supplied_role_order(self) -> None:
        selected = P08LiveRef(
            ref_name="refs/heads/main", role="selected-base", observation_oid="a" * 40,
            live_oid="a" * 40, worktree_state="clean", merged_into_base=True,
            unique_commits=0, classification="base", recommendation="preserve",
        )
        current = P08LiveRef(
            ref_name="refs/heads/academy/P08-repository-hygiene/1", role="current-attempt",
            observation_oid="b" * 40, live_oid="c" * 40, worktree_state="clean",
            merged_into_base=False, unique_commits=1, classification="current-attempt",
            recommendation="preserve",
        )
        worktree = P08LiveWorktree(
            worktree_id="d" * 64, role="current-attempt",
            branch_ref="refs/heads/academy/P08-repository-hygiene/1",
            observation_oid="b" * 40, live_oid="c" * 40, dirty=False,
            classification="current-attempt", recommendation="preserve",
        )
        common = {
            "repository_id": self.REPOSITORY_ID,
            "base_ref": "refs/heads/main",
            "base_oid": "a" * 40,
            "attempt_ref": "refs/heads/academy/P08-repository-hygiene/1",
            "prepared_oid": "b" * 40,
            "observation_oid": "b" * 40,
            "live_head_oid": "c" * 40,
            "worktrees": (worktree,),
            "state_digest": "e" * 64,
        }
        first = P08LiveState(refs=(selected, current), **common)
        second = P08LiveState(refs=(current, selected), **common)
        self.assertEqual(_p08_live_state_digest(first), _p08_live_state_digest(second))


class P02RealRepositoryTests(unittest.TestCase):
    OBJECT_FORMAT = "sha1"

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.repository = root / "learner"
        self.repository.mkdir()
        self.data_root = root / "installed-data"
        self.installed = self.data_root / "share/arbiter-academy/academy"
        self.installed.parent.mkdir(parents=True)
        shutil.copytree(SOURCE / "academy", self.installed)
        shutil.copytree(SOURCE / "academy", self.repository / "academy")
        shutil.copytree(SOURCE / "workshop_queue", self.repository / "workshop_queue")
        shutil.copytree(SOURCE / "data", self.repository / "data")
        shutil.copy2(SOURCE / "pyproject.toml", self.repository / "pyproject.toml")
        shutil.copy2(SOURCE / ".gitignore", self.repository / ".gitignore")
        (self.repository / "tests").mkdir()
        shutil.copy2(SOURCE / "tests/test_cli.py", self.repository / "tests/test_cli.py")
        (self.repository / ".codearbiter").mkdir()
        shutil.copy2(
            SOURCE / ".codearbiter/tech-stack.md",
            self.repository / ".codearbiter/tech-stack.md",
        )
        (self.repository / "scripts").mkdir()
        shutil.copy2(
            SOURCE / "scripts/scan_secrets.py",
            self.repository / "scripts/scan_secrets.py",
        )
        git(
            self.repository,
            "init",
            f"--object-format={self.OBJECT_FORMAT}",
            "-b",
            "main",
        )
        git(self.repository, "config", "core.autocrlf", "false")
        git(self.repository, "config", "user.name", "Academy Fixture")
        git(self.repository, "config", "user.email", "fixture@example.invalid")
        git(self.repository, "add", ".")
        git(self.repository, "commit", "-m", "academy base")
        git(self.repository, "remote", "add", "origin", "https://github.com/learner/arbiter-academy.git")
        git(self.repository, "remote", "add", "upstream", "https://github.com/arbiterForge/arbiter-academy.git")
        git(self.repository, "remote", "set-url", "--push", "upstream", "DISABLED")
        self.state_root = root / "state"

    def _prepare(self):
        store, lab = self._store_and_lab()
        with patch("academy_engine.exercise_state.sysconfig.get_path", return_value=str(self.data_root)):
            prepared = prepare_p02(self.repository, store, lab)
        return store, prepared

    def _store_and_lab(self):
        with patch("academy_engine.exercise_state.sysconfig.get_path", return_value=str(self.data_root)):
            base = git(self.repository, "rev-parse", "main").stdout.strip()
            store = open_p02_store(
                self.repository,
                base=base,
                test_root=self.state_root,
            )
            lab = Catalog.load(self.installed / "catalog.json").lab("P02-commit-review-pr")
        return store, lab

    def _p08_attempt_one_snapshot(self, store) -> dict[str, object]:
        with store.locked() as locked:
            record = locked.read_record("p08", 1)
            self.assertIsNotNone(record)
            assert record is not None
            copied = json.loads(json.dumps(record))
            targets = [
                (
                    item,
                    locked.owned_p08_worktree_parent(1, str(item["worktree_id"]))
                    / str(item["worktree_id"]),
                )
                for item in record["worktrees"][1:]
            ]
        refs = {
            str(item["ref_name"]): git(self.repository, "rev-parse", str(item["ref_name"])).stdout.strip()
            for item in copied["refs"]
        }
        worktrees: list[dict[str, object]] = []
        for item, target in targets:
            git_dir = Path(git(target, "rev-parse", "--git-dir").stdout.strip())
            if not git_dir.is_absolute():
                git_dir = target / git_dir
            worktrees.append(
                {
                    "role": item["role"],
                    "target": target,
                    "git_file": (target / ".git").read_bytes(),
                    "git_dir": git_dir.resolve(),
                    "status": git(
                        target, "status", "--porcelain=v1", "-z", "--untracked-files=all"
                    ).stdout.encode("utf-8", "surrogateescape"),
                    "marker": (
                        (target / ".arbiter-academy-p08-dirty").read_bytes()
                        if item["role"] == "dirty-unmerged"
                        else None
                    ),
                }
            )
        return {"record": copied, "refs": refs, "worktrees": worktrees}

    def _assert_p08_attempt_one_preserved(
        self,
        before: dict[str, object],
        after: dict[str, object],
        *,
        phase: str,
    ) -> None:
        before_record = dict(before["record"])
        after_record = dict(after["record"])
        before_record.pop("phase")
        before_record.pop("generation")
        after_record.pop("phase")
        after_record.pop("generation")
        self.assertEqual(after_record, before_record)
        self.assertEqual(after["record"]["phase"], phase)
        self.assertGreater(after["record"]["generation"], before["record"]["generation"])
        self.assertEqual(after["refs"], before["refs"])
        self.assertEqual(after["worktrees"], before["worktrees"])

    def test_p08_authority_capture_reads_exact_installed_six_resource_set(self) -> None:
        base = git(self.repository, "rev-parse", "main").stdout.strip()
        expected = (
            "academy/catalog.json",
            "academy/contracts.json",
            "academy/scenarios/P08-repository-hygiene/manifest.json",
            "academy/checkpoints/P08-repository-hygiene.json",
            "academy/scenarios/P08-repository-hygiene/files/scenario.json",
            "academy/tracks/practitioner/P08-repository-hygiene.md",
        )

        with patch(
            "academy_engine.exercise_state.sysconfig.get_path",
            return_value=str(self.data_root),
        ):
            authority = _verified_p08_epoch(self.repository, base)

        self.assertEqual(authority.installed_root, self.installed)
        self.assertEqual(tuple(authority.sources), expected)
        self.assertEqual(
            authority.catalog_sha256,
            hashlib.sha256((self.installed / "catalog.json").read_bytes()).hexdigest(),
        )

    def test_p08_authority_capture_rejects_one_tampered_installed_resource(self) -> None:
        base = git(self.repository, "rev-parse", "main").stdout.strip()
        scenario = self.installed / "scenarios/P08-repository-hygiene/files/scenario.json"
        original = scenario.read_bytes()
        scenario.write_bytes(original + b"\n")

        with patch(
            "academy_engine.exercise_state.sysconfig.get_path",
            return_value=str(self.data_root),
        ):
            with self.assertRaises(ExerciseStateError) as raised:
                _verified_p08_epoch(self.repository, base)

        self.assertEqual(raised.exception.code, "installed-authority-required")
        self.assertNotIn(str(self.repository), str(raised.exception))

    def test_p08_preflight_captures_installed_authority_before_state_creation(self) -> None:
        with patch(
            "academy_engine.exercise_state.sysconfig.get_path",
            return_value=str(self.data_root),
        ):
            base, lab, authority = preflight_p08(self.repository)

        self.assertEqual(base, git(self.repository, "rev-parse", "main").stdout.strip())
        self.assertEqual(lab.id, "P08-repository-hygiene")
        self.assertEqual(authority.installed_root, self.installed)
        self.assertFalse(self.state_root.exists())

    def test_p08_prepare_creates_the_closed_non_destructive_fixture(self) -> None:
        with patch(
            "academy_engine.exercise_state.sysconfig.get_path",
            return_value=str(self.data_root),
        ):
            base, lab, authority = preflight_p08(self.repository)
            store = open_p08_store(
                self.repository, base=base, authority=authority, test_root=self.state_root
            )
            prepared = prepare_p08(self.repository, store, lab)

        self.assertEqual(prepared.branch, "academy/P08-repository-hygiene/1")
        self.assertEqual(prepared.base_sha, base)
        self.assertEqual(
            git(self.repository, "rev-parse", "refs/heads/academy-fixtures/p08/1/merged-clean").stdout.strip(),
            base,
        )
        self.assertEqual(
            git(self.repository, "rev-parse", "refs/heads/academy-fixtures/p08/1/dirty-unmerged").stdout.strip(),
            prepared.commit_sha,
        )
        self.assertTrue((self.repository / "training_scenarios/P08-repository-hygiene.json").is_file())
        with store.locked() as locked:
            record = locked.read_record("p08", 1)
            self.assertIsNotNone(record)
            for item in record["worktrees"][1:]:
                parent = locked.owned_p08_worktree_parent(1, item["worktree_id"])
                target = parent / item["worktree_id"]
                normalized = os.path.normcase(str(target.resolve(strict=False))).replace("\\", "/")
                expected_hash = hashlib.sha256(
                    f"arbiter-academy/p08-worktree-path/v1\0{normalized}\n".encode("utf-8")
                ).hexdigest()
                self.assertTrue(target.is_dir())
                self.assertTrue((target / ".git").is_file())
                self.assertEqual(item["path_sha256"], expected_hash)
                self.assertFalse(
                    os.path.lexists(
                        store._epoch_dir / "p08/1/worktrees" / item["worktree_id"]
                    )
                )

    def test_p08_prepare_rejects_dangling_worktree_leaf_before_git_or_outside_mutation(self) -> None:
        outside = self.repository.parent / "outside-dangling-worktree"
        outside.mkdir()
        parent_calls: dict[str, int] = {}
        worktree_adds: list[list[str]] = []
        original_parent = exercise_module.LockedExternalState.owned_p08_worktree_parent
        original_git = exercise_module._git

        def owned_parent(locked, attempt, worktree_id):
            parent = original_parent(locked, attempt, worktree_id)
            parent_calls[worktree_id] = parent_calls.get(worktree_id, 0) + 1
            if parent_calls[worktree_id] == 2:
                target = parent / worktree_id
                if sys.platform == "win32":
                    backing = outside / "removed-junction-target"
                    backing.mkdir()
                    command = Path(os.environ["SystemRoot"]) / "System32/cmd.exe"
                    created = subprocess.run(
                        [str(command), "/d", "/v:off", "/c", "mklink", "/J", str(target), str(backing)],
                        cwd=parent,
                        stdin=subprocess.DEVNULL,
                        capture_output=True,
                        check=False,
                        timeout=10,
                    )
                    self.assertEqual(created.returncode, 0, (created.stdout + created.stderr)[:2048])
                    backing.rmdir()
                else:
                    os.symlink(outside / "missing-target", target, target_is_directory=True)
                self.assertTrue(os.path.lexists(target))
                self.assertFalse(target.exists())
            return parent

        def guarded_git(repository, args, *, code="transition-incomplete"):
            if args[:2] == ["worktree", "add"]:
                worktree_adds.append(list(args))
                raise AssertionError("P08 must reject a dangling target before git worktree add")
            return original_git(repository, args, code=code)

        with patch("academy_engine.exercise_state.sysconfig.get_path", return_value=str(self.data_root)):
            base, lab, authority = preflight_p08(self.repository)
            store = open_p08_store(
                self.repository, base=base, authority=authority, test_root=self.state_root
            )
            with patch.object(
                exercise_module.LockedExternalState,
                "owned_p08_worktree_parent",
                autospec=True,
                side_effect=owned_parent,
            ), patch.object(exercise_module, "_git", side_effect=guarded_git):
                with self.assertRaises(ExerciseStateError) as raised:
                    prepare_p08(self.repository, store, lab)

        self.assertEqual(raised.exception.code, "p08-transition-incomplete")
        self.assertEqual(worktree_adds, [])
        self.assertEqual(tuple(outside.iterdir()), ())

    def test_p08_prepare_resumes_exact_linked_worktree_prefix_after_interruption(self) -> None:
        original_git = exercise_module._git

        def interrupted_git(repository, args, *, code="transition-incomplete"):
            if (
                args[:2] == ["worktree", "add"]
                and args[-1] == "academy-fixtures/p08/1/dirty-unmerged"
            ):
                raise ExerciseStateError("p08-transition-incomplete")
            return original_git(repository, args, code=code)

        with patch("academy_engine.exercise_state.sysconfig.get_path", return_value=str(self.data_root)):
            base, lab, authority = preflight_p08(self.repository)
            store = open_p08_store(
                self.repository, base=base, authority=authority, test_root=self.state_root
            )
            with patch.object(exercise_module, "_git", side_effect=interrupted_git):
                with self.assertRaises(ExerciseStateError) as raised:
                    prepare_p08(self.repository, store, lab)
            self.assertEqual(raised.exception.code, "p08-transition-incomplete")
            with store.locked() as locked:
                interrupted = locked.read_record("p08", 1)
            self.assertEqual(interrupted["phase"], "creating-worktrees")

            resumed = prepare_p08(self.repository, store, lab)

        self.assertEqual(resumed.branch, "academy/P08-repository-hygiene/1")
        with store.locked() as locked:
            completed = locked.read_record("p08", 1)
        self.assertEqual(completed["phase"], "active")

    def test_p08_linked_worktree_rejects_moved_git_administration_suffix(self) -> None:
        with patch("academy_engine.exercise_state.sysconfig.get_path", return_value=str(self.data_root)):
            base, lab, authority = preflight_p08(self.repository)
            store = open_p08_store(
                self.repository, base=base, authority=authority, test_root=self.state_root
            )
            prepare_p08(self.repository, store, lab)
        with store.locked() as locked:
            record = locked.read_record("p08", 1)
            item = record["worktrees"][1]
            parent = locked.owned_p08_worktree_parent(1, item["worktree_id"])
        target = parent / item["worktree_id"]
        common = Path(git(self.repository, "rev-parse", "--git-common-dir").stdout.strip())
        if not common.is_absolute():
            common = self.repository / common
        expected = common.resolve() / "worktrees" / item["git_admin_id"]
        moved = expected.with_name(expected.name + "-suffix")
        expected.rename(moved)
        git_file = target / ".git"
        if sys.platform == "win32":
            attributes = subprocess.run(
                ["attrib", "-H", "-R", str(git_file)],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                check=False,
                timeout=10,
            )
            self.assertEqual(attributes.returncode, 0, (attributes.stdout + attributes.stderr)[:2048])
        git_file.chmod(stat.S_IREAD | stat.S_IWRITE)
        git_file.write_text(f"gitdir: {moved}\n", encoding="utf-8")

        with self.assertRaises(ExerciseStateError) as raised:
            exercise_module._p08_existing_linked_worktree_is_exact(
                self.repository, target, item
            )

        self.assertEqual(raised.exception.code, "p08-transition-incomplete")

    def test_p08_prepare_rejects_wrong_stored_raw_dirty_status_digest_on_resume(self) -> None:
        original_git = exercise_module._git

        def interrupted_git(repository, args, *, code="transition-incomplete"):
            if (
                args[:2] == ["worktree", "add"]
                and args[-1] == "academy-fixtures/p08/1/dirty-unmerged"
            ):
                raise ExerciseStateError("p08-transition-incomplete")
            return original_git(repository, args, code=code)

        with patch("academy_engine.exercise_state.sysconfig.get_path", return_value=str(self.data_root)):
            base, lab, authority = preflight_p08(self.repository)
            store = open_p08_store(
                self.repository, base=base, authority=authority, test_root=self.state_root
            )
            with patch.object(exercise_module, "_git", side_effect=interrupted_git):
                with self.assertRaises(ExerciseStateError):
                    prepare_p08(self.repository, store, lab)
            with store.locked() as locked:
                record = locked.read_record("p08", 1)
                record["worktrees"][2]["dirty_status_sha256"] = "0" * 64
                record["generation"] += 1
                locked.write_record("p08", 1, record, expected_generation=record["generation"] - 1)

            with self.assertRaises(ExerciseStateError) as raised:
                prepare_p08(self.repository, store, lab)

        self.assertEqual(raised.exception.code, "p08-transition-incomplete")
        with store.locked() as locked:
            unchanged = locked.read_record("p08", 1)
        self.assertEqual(unchanged["phase"], "creating-worktrees")

    def test_p08_linked_worktree_rejects_unexpected_raw_dirty_status(self) -> None:
        with patch("academy_engine.exercise_state.sysconfig.get_path", return_value=str(self.data_root)):
            base, lab, authority = preflight_p08(self.repository)
            store = open_p08_store(
                self.repository, base=base, authority=authority, test_root=self.state_root
            )
            prepare_p08(self.repository, store, lab)
        with store.locked() as locked:
            record = locked.read_record("p08", 1)
            item = record["worktrees"][2]
            parent = locked.owned_p08_worktree_parent(1, item["worktree_id"])
        target = parent / item["worktree_id"]
        (target / "unexpected-raw-status").write_bytes(b"unexpected\n")

        with self.assertRaises(ExerciseStateError) as raised:
            exercise_module._p08_existing_linked_worktree_is_exact(
                self.repository, target, item
            )

        self.assertEqual(raised.exception.code, "p08-transition-incomplete")

    def test_p08_prepare_rejects_uncommitted_attempt_branch_on_reentry(self) -> None:
        original_git = exercise_module._git

        def interrupted_git(repository, args, *, code="transition-incomplete"):
            if args[:2] == ["commit", "-m"]:
                raise ExerciseStateError("p08-transition-incomplete")
            return original_git(repository, args, code=code)

        with patch("academy_engine.exercise_state.sysconfig.get_path", return_value=str(self.data_root)):
            base, lab, authority = preflight_p08(self.repository)
            store = open_p08_store(
                self.repository, base=base, authority=authority, test_root=self.state_root
            )
            with patch.object(exercise_module, "_git", side_effect=interrupted_git):
                with self.assertRaises(ExerciseStateError):
                    prepare_p08(self.repository, store, lab)
            with store.locked() as locked:
                interrupted = locked.read_record("p08", 1)
            self.assertEqual(interrupted["phase"], "creating-attempt")

            with self.assertRaises(ExerciseStateError) as raised:
                prepare_p08(self.repository, store, lab)

        self.assertEqual(raised.exception.code, "p08-transition-incomplete")
        with store.locked() as locked:
            unchanged = locked.read_record("p08", 1)
        self.assertEqual(unchanged["phase"], "creating-attempt")

    def test_p08_prepare_rejects_extra_fixture_ref_before_worktree_mutation(self) -> None:
        original_write = exercise_module._write_p08

        def interrupted_write(locked, record, phase, **changes):
            result = original_write(locked, record, phase, **changes)
            if phase == "planning-worktrees":
                raise ExerciseStateError("p08-transition-incomplete")
            return result

        with patch("academy_engine.exercise_state.sysconfig.get_path", return_value=str(self.data_root)):
            base, lab, authority = preflight_p08(self.repository)
            store = open_p08_store(
                self.repository, base=base, authority=authority, test_root=self.state_root
            )
            with patch.object(exercise_module, "_write_p08", side_effect=interrupted_write):
                with self.assertRaises(ExerciseStateError):
                    prepare_p08(self.repository, store, lab)
            git(
                self.repository,
                "update-ref",
                "refs/heads/academy-fixtures/p08/1/unexpected",
                base,
            )
            with self.assertRaises(ExerciseStateError) as raised:
                prepare_p08(self.repository, store, lab)

        self.assertEqual(raised.exception.code, "p08-transition-incomplete")
        with store.locked() as locked:
            unchanged = locked.read_record("p08", 1)
        self.assertEqual(unchanged["phase"], "planning-worktrees")

    def test_p08_prepare_rejects_authority_equivalent_main_drift_after_record_binding(self) -> None:
        with patch("academy_engine.exercise_state.sysconfig.get_path", return_value=str(self.data_root)):
            base, lab, authority = preflight_p08(self.repository)
            store = open_p08_store(
                self.repository, base=base, authority=authority, test_root=self.state_root
            )
            prepare_p08(self.repository, store, lab)
            tree = git(self.repository, "rev-parse", f"{base}^{{tree}}").stdout.strip()
            drift = git(
                self.repository,
                "commit-tree",
                tree,
                "-p",
                base,
                "-m",
                "authority-equivalent main drift",
            ).stdout.strip()
            git(self.repository, "update-ref", "refs/heads/main", drift)

            with self.assertRaises(ExerciseStateError) as raised:
                prepare_p08(self.repository, store, lab)

        self.assertEqual(raised.exception.code, "p08-state-mismatch")

    def test_p08_active_prepare_rejects_dirty_primary_without_mutation(self) -> None:
        with patch("academy_engine.exercise_state.sysconfig.get_path", return_value=str(self.data_root)):
            base, lab, authority = preflight_p08(self.repository)
            store = open_p08_store(
                self.repository, base=base, authority=authority, test_root=self.state_root
            )
            prepared = prepare_p08(self.repository, store, lab)
            state_path = store._epoch_dir / "p08/1/state.json"
            before_state = state_path.read_bytes()
            before_refs = git(
                self.repository, "for-each-ref", "--format=%(refname)%00%(objectname)", "refs/heads/academy-fixtures/p08/"
            ).stdout
            drift = self.repository / "active-retry-drift.txt"
            drift.write_text("dirty\n", encoding="utf-8")

            with self.assertRaises(ExerciseStateError) as raised:
                prepare_p08(self.repository, store, lab)

        self.assertEqual(raised.exception.code, "p08-transition-incomplete")
        self.assertEqual(git(self.repository, "rev-parse", "HEAD").stdout.strip(), prepared.commit_sha)
        self.assertEqual(state_path.read_bytes(), before_state)
        self.assertEqual(
            git(
                self.repository, "for-each-ref", "--format=%(refname)%00%(objectname)", "refs/heads/academy-fixtures/p08/"
            ).stdout,
            before_refs,
        )
        self.assertEqual(drift.read_text(encoding="utf-8"), "dirty\n")

    def test_p08_active_prepare_rejects_moved_linked_worktree_without_mutation(self) -> None:
        with patch("academy_engine.exercise_state.sysconfig.get_path", return_value=str(self.data_root)):
            base, lab, authority = preflight_p08(self.repository)
            store = open_p08_store(
                self.repository, base=base, authority=authority, test_root=self.state_root
            )
            prepare_p08(self.repository, store, lab)
            with store.locked() as locked:
                record = locked.read_record("p08", 1)
                self.assertIsNotNone(record)
                assert record is not None
                item = record["worktrees"][1]
                target = (
                    locked.owned_p08_worktree_parent(1, str(item["worktree_id"]))
                    / str(item["worktree_id"])
                )
            state_path = store._epoch_dir / "p08/1/state.json"
            before_state = state_path.read_bytes()
            moved = target.with_name(target.name + "-moved")
            target.rename(moved)

            with self.assertRaises(ExerciseStateError) as raised:
                prepare_p08(self.repository, store, lab)

        self.assertEqual(raised.exception.code, "p08-transition-incomplete")
        self.assertFalse(target.exists())
        self.assertTrue(moved.is_dir())
        self.assertEqual(state_path.read_bytes(), before_state)

    def test_p08_active_prepare_rejects_rebound_fixture_ref_without_mutation(self) -> None:
        with patch("academy_engine.exercise_state.sysconfig.get_path", return_value=str(self.data_root)):
            base, lab, authority = preflight_p08(self.repository)
            store = open_p08_store(
                self.repository, base=base, authority=authority, test_root=self.state_root
            )
            prepared = prepare_p08(self.repository, store, lab)
            with store.locked() as locked:
                record = locked.read_record("p08", 1)
                self.assertIsNotNone(record)
                assert record is not None
                dirty_ref = str(record["refs"][3]["ref_name"])
            state_path = store._epoch_dir / "p08/1/state.json"
            before_state = state_path.read_bytes()
            tree = git(self.repository, "rev-parse", f"{prepared.commit_sha}^{{tree}}").stdout.strip()
            rebound = git(
                self.repository,
                "commit-tree",
                tree,
                "-p",
                prepared.commit_sha,
                "-m",
                "P08 active retry rebound fixture",
            ).stdout.strip()
            git(self.repository, "update-ref", dirty_ref, rebound)

            with self.assertRaises(ExerciseStateError) as raised:
                prepare_p08(self.repository, store, lab)

        self.assertEqual(raised.exception.code, "p08-transition-incomplete")
        self.assertEqual(git(self.repository, "rev-parse", dirty_ref).stdout.strip(), rebound)
        self.assertEqual(state_path.read_bytes(), before_state)

    def test_p08_active_prepare_retries_clean_fixture_without_mutation(self) -> None:
        with patch("academy_engine.exercise_state.sysconfig.get_path", return_value=str(self.data_root)):
            base, lab, authority = preflight_p08(self.repository)
            store = open_p08_store(
                self.repository, base=base, authority=authority, test_root=self.state_root
            )
            prepared = prepare_p08(self.repository, store, lab)
            state_path = store._epoch_dir / "p08/1/state.json"
            before_state = state_path.read_bytes()

            repeated = prepare_p08(self.repository, store, lab)

        self.assertEqual(repeated, prepared)
        self.assertEqual(state_path.read_bytes(), before_state)

    def test_p08_prepare_rejects_planned_git_admin_collision_before_worktree_add(self) -> None:
        original_write = exercise_module._write_p08

        def interrupted_write(locked, record, phase, **changes):
            result = original_write(locked, record, phase, **changes)
            if phase == "creating-worktrees":
                raise ExerciseStateError("p08-transition-incomplete")
            return result

        with patch("academy_engine.exercise_state.sysconfig.get_path", return_value=str(self.data_root)):
            base, lab, authority = preflight_p08(self.repository)
            store = open_p08_store(
                self.repository, base=base, authority=authority, test_root=self.state_root
            )
            with patch.object(exercise_module, "_write_p08", side_effect=interrupted_write):
                with self.assertRaises(ExerciseStateError):
                    prepare_p08(self.repository, store, lab)
            with store.locked() as locked:
                record = locked.read_record("p08", 1)
                self.assertIsNotNone(record)
                assert record is not None
                item = record["worktrees"][1]
                target = (
                    locked.owned_p08_worktree_parent(1, str(item["worktree_id"]))
                    / str(item["worktree_id"])
                )
            common = Path(git(self.repository, "rev-parse", "--git-common-dir").stdout.strip())
            if not common.is_absolute():
                common = self.repository / common
            collision = common.resolve() / "worktrees" / str(item["git_admin_id"])
            collision.parent.mkdir()
            collision.mkdir()
            state_path = store._epoch_dir / "p08/1/state.json"
            before_state = state_path.read_bytes()
            original_git = exercise_module._git
            worktree_adds: list[tuple[str, ...]] = []

            def guarded_git(repository, args, *, code="transition-incomplete"):
                if args[:2] == ["worktree", "add"]:
                    worktree_adds.append(tuple(args))
                    raise AssertionError("P08 must reject a Git-admin collision before worktree add")
                return original_git(repository, args, code=code)

            with patch.object(exercise_module, "_git", side_effect=guarded_git):
                with self.assertRaises(ExerciseStateError) as raised:
                    prepare_p08(self.repository, store, lab)

        self.assertEqual(raised.exception.code, "p08-transition-incomplete")
        self.assertEqual(worktree_adds, [])
        self.assertFalse(target.exists())
        self.assertTrue(collision.is_dir())
        self.assertEqual(state_path.read_bytes(), before_state)

    @unittest.skipUnless(os.name == "nt", "Windows junction boundary")
    def test_p08_prepare_rejects_scenario_directory_junction_before_branch_record_or_outside_write(self) -> None:
        outside = self.repository.parent / "outside-p08-scenarios"
        outside.mkdir()
        redirected = self.repository / "training_scenarios"
        command = Path(os.environ["SystemRoot"]) / "System32/cmd.exe"
        created = subprocess.run(
            [
                str(command), "/d", "/v:off", "/c", "mklink", "/J",
                redirected.name, str(outside),
            ],
            cwd=self.repository,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(created.returncode, 0, created.stdout + created.stderr)
        self.addCleanup(lambda: os.path.lexists(redirected) and os.rmdir(redirected))
        with patch("academy_engine.exercise_state.sysconfig.get_path", return_value=str(self.data_root)):
            base, lab, authority = preflight_p08(self.repository)
            store = open_p08_store(
                self.repository, base=base, authority=authority, test_root=self.state_root
            )
            with self.assertRaises(ExerciseStateError) as raised:
                prepare_p08(self.repository, store, lab)

        self.assertEqual(raised.exception.code, "p08-transition-incomplete")
        self.assertEqual(tuple(outside.iterdir()), ())
        self.assertEqual(
            git(
                self.repository,
                "show-ref",
                "--verify",
                "--quiet",
                "refs/heads/academy/P08-repository-hygiene/1",
                check=False,
            ).returncode,
            1,
        )
        with store.locked() as locked:
            self.assertIsNone(locked.read_record("p08", 1))

    def test_p08_reset_supersedes_without_deleting_attempt_one_resources(self) -> None:
        with patch("academy_engine.exercise_state.sysconfig.get_path", return_value=str(self.data_root)):
            base, lab, authority = preflight_p08(self.repository)
            store = open_p08_store(
                self.repository, base=base, authority=authority, test_root=self.state_root
            )
            first = prepare_p08(self.repository, store, lab)
        with store.locked() as locked:
            record = locked.read_record("p08", 1)
            self.assertIsNotNone(record)
            assert record is not None
            old_refs = {
                str(item["ref_name"]): git(self.repository, "rev-parse", str(item["ref_name"])).stdout.strip()
                for item in record["refs"]
            }
            old_targets = [
                locked.owned_p08_worktree_parent(1, str(item["worktree_id"])) / str(item["worktree_id"])
                for item in record["worktrees"][1:]
            ]
        marker = old_targets[1] / ".arbiter-academy-p08-dirty"
        marker_bytes = marker.read_bytes()
        dirty_status = git(
            old_targets[1], "status", "--porcelain=v1", "-z", "--untracked-files=all"
        ).stdout.encode("utf-8", "surrogateescape")
        original_git = exercise_module._git
        commands: list[tuple[str, ...]] = []

        def observed_git(repository, args, *, code="transition-incomplete"):
            commands.append(tuple(args))
            return original_git(repository, args, code=code)

        with patch("academy_engine.exercise_state.sysconfig.get_path", return_value=str(self.data_root)), patch.object(
            exercise_module, "_git", side_effect=observed_git
        ):
            second = exercise_module.reset_p08(self.repository, store)

        self.assertEqual(first.attempt, 1)
        self.assertEqual(second.attempt, 2)
        with store.locked() as locked:
            superseded = locked.read_record("p08", 1)
            retry = locked.read_record("p08", 2)
        self.assertEqual(superseded["phase"], "superseded")
        self.assertEqual(retry["phase"], "active")
        self.assertEqual(
            {
                name: git(self.repository, "rev-parse", name).stdout.strip()
                for name in old_refs
            },
            old_refs,
        )
        self.assertTrue(all(target.is_dir() for target in old_targets))
        self.assertEqual(marker.read_bytes(), marker_bytes)
        self.assertEqual(
            git(old_targets[1], "status", "--porcelain=v1", "-z", "--untracked-files=all").stdout.encode(
                "utf-8", "surrogateescape"
            ),
            dirty_status,
        )
        self.assertFalse(any(
            args[:2] in {("worktree", "remove"), ("worktree", "prune")}
            or args[:2] in {("branch", "-d"), ("branch", "-D")}
            or args[:2] == ("update-ref", "-d")
            or args[:1] == ("reset",)
            or "--force" in args
            for args in commands
        ))
        self.assertEqual(
            git(
                self.repository,
                "for-each-ref",
                "--format=%(refname)",
                "refs/heads/academy/archive/P08-repository-hygiene/",
            ).stdout,
            "",
        )

    def test_p08_reset_resumes_exact_prefix_after_primary_switch_interruption(self) -> None:
        with patch("academy_engine.exercise_state.sysconfig.get_path", return_value=str(self.data_root)):
            base, lab, authority = preflight_p08(self.repository)
            store = open_p08_store(
                self.repository, base=base, authority=authority, test_root=self.state_root
            )
            prepare_p08(self.repository, store, lab)
        original_write = exercise_module._write_p08

        def interrupted_write(locked, record, phase, *, object_format, **changes):
            if phase == "superseded":
                raise ExerciseStateError("p08-transition-incomplete")
            return original_write(locked, record, phase, object_format=object_format, **changes)

        with patch("academy_engine.exercise_state.sysconfig.get_path", return_value=str(self.data_root)), patch.object(
            exercise_module, "_write_p08", side_effect=interrupted_write
        ):
            with self.assertRaises(ExerciseStateError) as raised:
                exercise_module.reset_p08(self.repository, store)

        self.assertEqual(raised.exception.code, "p08-transition-incomplete")
        self.assertEqual(git(self.repository, "branch", "--show-current").stdout.strip(), "main")
        with store.locked() as locked:
            interrupted = locked.read_record("p08", 1)
        self.assertEqual(interrupted["phase"], "superseding")

        with patch("academy_engine.exercise_state.sysconfig.get_path", return_value=str(self.data_root)):
            resumed = exercise_module.reset_p08(self.repository, store)

        self.assertEqual(resumed.attempt, 2)
        with store.locked() as locked:
            self.assertEqual(locked.read_record("p08", 1)["phase"], "superseded")
            self.assertEqual(locked.read_record("p08", 2)["phase"], "active")

    def test_p08_reset_resumes_superseding_prefix_before_primary_switch(self) -> None:
        with patch("academy_engine.exercise_state.sysconfig.get_path", return_value=str(self.data_root)):
            base, lab, authority = preflight_p08(self.repository)
            store = open_p08_store(
                self.repository, base=base, authority=authority, test_root=self.state_root
            )
            prepare_p08(self.repository, store, lab)
        before = self._p08_attempt_one_snapshot(store)
        original_git = exercise_module._git

        def interrupted_git(repository, args, *, code="transition-incomplete"):
            if args == ["switch", "main"]:
                raise ExerciseStateError("p08-transition-incomplete")
            return original_git(repository, args, code=code)

        with patch("academy_engine.exercise_state.sysconfig.get_path", return_value=str(self.data_root)), patch.object(
            exercise_module, "_git", side_effect=interrupted_git
        ):
            with self.assertRaises(ExerciseStateError) as raised:
                exercise_module.reset_p08(self.repository, store)

        self.assertEqual(raised.exception.code, "p08-transition-incomplete")
        self.assertEqual(
            git(self.repository, "branch", "--show-current").stdout.strip(),
            "academy/P08-repository-hygiene/1",
        )
        interrupted = self._p08_attempt_one_snapshot(store)
        self._assert_p08_attempt_one_preserved(before, interrupted, phase="superseding")
        with store.locked() as locked:
            self.assertIsNone(locked.read_record("p08", 2))

        with patch("academy_engine.exercise_state.sysconfig.get_path", return_value=str(self.data_root)):
            resumed = exercise_module.reset_p08(self.repository, store)

        self.assertEqual(resumed.attempt, 2)
        retried = self._p08_attempt_one_snapshot(store)
        self._assert_p08_attempt_one_preserved(before, retried, phase="superseded")
        with store.locked() as locked:
            self.assertEqual(locked.read_record("p08", 2)["phase"], "active")

    def test_p08_reset_resumes_after_superseded_before_attempt_two(self) -> None:
        with patch("academy_engine.exercise_state.sysconfig.get_path", return_value=str(self.data_root)):
            base, lab, authority = preflight_p08(self.repository)
            store = open_p08_store(
                self.repository, base=base, authority=authority, test_root=self.state_root
            )
            prepare_p08(self.repository, store, lab)
        before = self._p08_attempt_one_snapshot(store)

        with patch("academy_engine.exercise_state.sysconfig.get_path", return_value=str(self.data_root)), patch.object(
            exercise_module,
            "prepare_p08",
            side_effect=ExerciseStateError("p08-transition-incomplete"),
        ):
            with self.assertRaises(ExerciseStateError) as raised:
                exercise_module.reset_p08(self.repository, store)

        self.assertEqual(raised.exception.code, "p08-transition-incomplete")
        self.assertEqual(git(self.repository, "branch", "--show-current").stdout.strip(), "main")
        interrupted = self._p08_attempt_one_snapshot(store)
        self._assert_p08_attempt_one_preserved(before, interrupted, phase="superseded")
        with store.locked() as locked:
            self.assertIsNone(locked.read_record("p08", 2))

        with patch("academy_engine.exercise_state.sysconfig.get_path", return_value=str(self.data_root)):
            resumed = exercise_module.reset_p08(self.repository, store)

        self.assertEqual(resumed.attempt, 2)
        retried = self._p08_attempt_one_snapshot(store)
        self._assert_p08_attempt_one_preserved(before, retried, phase="superseded")
        with store.locked() as locked:
            self.assertEqual(locked.read_record("p08", 2)["phase"], "active")

    def test_p08_reset_rejects_mixed_primary_branch_after_superseding_journal(self) -> None:
        with patch("academy_engine.exercise_state.sysconfig.get_path", return_value=str(self.data_root)):
            base, lab, authority = preflight_p08(self.repository)
            store = open_p08_store(
                self.repository, base=base, authority=authority, test_root=self.state_root
            )
            prepare_p08(self.repository, store, lab)
        original_git = exercise_module._git

        def interrupted_git(repository, args, *, code="transition-incomplete"):
            if args == ["switch", "main"]:
                raise ExerciseStateError("p08-transition-incomplete")
            return original_git(repository, args, code=code)

        with patch("academy_engine.exercise_state.sysconfig.get_path", return_value=str(self.data_root)), patch.object(
            exercise_module, "_git", side_effect=interrupted_git
        ):
            with self.assertRaises(ExerciseStateError):
                exercise_module.reset_p08(self.repository, store)
        git(self.repository, "switch", "-c", "academy/foreign-p08-reset")

        with patch("academy_engine.exercise_state.sysconfig.get_path", return_value=str(self.data_root)):
            with self.assertRaises(ExerciseStateError) as raised:
                exercise_module.reset_p08(self.repository, store)

        self.assertEqual(raised.exception.code, "p08-transition-incomplete")
        self.assertEqual(
            git(self.repository, "branch", "--show-current").stdout.strip(),
            "academy/foreign-p08-reset",
        )
        with store.locked() as locked:
            self.assertEqual(locked.read_record("p08", 1)["phase"], "superseding")

    def test_p08_checkpoint_accepts_only_the_canonical_report_commit_blob(self) -> None:
        with patch("academy_engine.exercise_state.sysconfig.get_path", return_value=str(self.data_root)):
            base, lab, authority = preflight_p08(self.repository)
            store = open_p08_store(
                self.repository, base=base, authority=authority, test_root=self.state_root
            )
            prepared = prepare_p08(self.repository, store, lab)
        with store.locked() as locked:
            record = locked.read_record("p08", 1)
        self.assertIsNotNone(record)
        assert record is not None
        report = {
            "schema_version": 1,
            "base": {"ref": "refs/heads/main", "object_id": base},
            "refs": [
                {
                    "ref": item["ref_name"],
                    "object_id": item["object_id"],
                    "worktree_state": state,
                    "merged_into_base": merged,
                    "unique_commits": unique,
                    "classification": classification,
                    "recommendation": recommendation,
                }
                for item, state, merged, unique, classification, recommendation in zip(
                    record["refs"],
                    ("clean", "clean", "clean", "dirty", "none"),
                    (True, False, True, False, False),
                    (0, 1, 0, 1, 1),
                    (
                        "base",
                        "current-attempt",
                        "merged-clean",
                        "unmerged-dirty",
                        "unmerged-unique",
                    ),
                    (
                        "preserve",
                        "preserve",
                        "eligible-for-explicit-review",
                        "preserve",
                        "preserve",
                    ),
                    strict=True,
                )
            ],
            "worktrees": [
                {
                    "worktree_id": item["worktree_id"],
                    "branch_ref": item["branch_ref"],
                    "head": item["head_oid"],
                    "present": True,
                    "dirty": dirty,
                    "classification": classification,
                    "recommendation": recommendation,
                }
                for item, dirty, classification, recommendation in zip(
                    record["worktrees"],
                    (False, False, True),
                    ("current-attempt", "merged-clean", "unmerged-dirty"),
                    ("preserve", "eligible-for-explicit-review", "preserve"),
                    strict=True,
                )
            ],
        }
        target = self.repository / ".codearbiter/reports/academy/P08-hygiene.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(
            json.dumps(report, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
            + b"\n"
        )
        git(self.repository, "add", "--", target.relative_to(self.repository).as_posix())
        git(self.repository, "commit", "-m", "academy: report P08 hygiene")
        report_commit = git(self.repository, "rev-parse", "HEAD").stdout.strip()
        identity = exercise_module.P08AttemptIdentity(
            1, prepared.branch, prepared.commit_sha, report_commit
        )
        self.assertEqual(record["phase"], "active")
        self.assertEqual(record["base_oid"], base)
        self.assertEqual(prepared.branch, record["attempt_ref"].removeprefix("refs/heads/"))
        self.assertEqual(prepared.commit_sha, record["prepared_oid"])
        self.assertEqual(
            git(self.repository, "rev-parse", record["attempt_ref"]).stdout.strip(), report_commit
        )
        self.assertEqual(
            git(self.repository, "rev-list", "--parents", "-n", "1", report_commit).stdout.split(),
            [report_commit, prepared.commit_sha],
        )
        self.assertEqual(
            git(
                self.repository, "diff-tree", "--no-commit-id", "--name-only", "-r", report_commit
            ).stdout.splitlines(),
            [".codearbiter/reports/academy/P08-hygiene.json"],
        )
        self.assertEqual(
            git(
                self.repository,
                "show",
                f"{report_commit}:.codearbiter/reports/academy/P08-hygiene.json",
            ).stdout.encode("utf-8", "surrogateescape"),
            json.dumps(
                exercise_module._p08_expected_report(self.repository, record, base),
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
            + b"\n",
        )
        entry = exercise_module._git(
            self.repository,
            [
                "ls-tree",
                "-z",
                report_commit,
                "--",
                ".codearbiter/reports/academy/P08-hygiene.json",
            ],
            code="p08-report-mismatch",
        )
        self.assertTrue(entry.endswith("\0"), repr(entry))
        self.assertEqual(
            entry.removesuffix("\0").split("\t", 1)[0].split()[:2],
            ["100644", "blob"],
        )

        with patch("academy_engine.exercise_state.sysconfig.get_path", return_value=str(self.data_root)):
            self.assertTrue(exercise_module.validate_p08_checkpoint(self.repository, store, identity))

    def test_p08_public_verify_returns_canonical_path_free_live_state(self) -> None:
        _base, store, prepared, record, identity = self._p08_checkpoint_candidate()

        with patch("academy_engine.exercise_state.sysconfig.get_path", return_value=str(self.data_root)):
            state = exercise_module.verify_p08(self.repository, store, identity)

        self.assertEqual(state.repository_id, store.repository_id)
        self.assertEqual(state.prepared_oid, prepared.commit_sha)
        self.assertEqual(state.observation_oid, identity.head_commit)
        self.assertEqual(state.live_head_oid, identity.head_commit)
        self.assertEqual(tuple(ref.role for ref in state.refs), tuple(item["role"] for item in record["refs"]))
        current = next(ref for ref in state.refs if ref.role == "current-attempt")
        self.assertEqual(current.observation_oid, prepared.commit_sha)
        self.assertEqual(current.live_oid, identity.head_commit)
        self.assertEqual(state.state_digest, exercise_module._p08_live_state_digest(state))
        self.assertNotIn(str(self.repository), repr(state))
        self.assertNotIn(str(self.state_root), repr(state))

    def test_p08_reset_has_the_declared_two_argument_public_signature(self) -> None:
        self.assertEqual(
            tuple(inspect.signature(exercise_module.reset_p08).parameters),
            ("repository", "store"),
        )

    def _p08_checkpoint_candidate(
        self,
        *,
        canonical: bool = True,
        extra_path: str | None = None,
        executable: bool = False,
        mutate_report=None,
        mode: str | None = None,
    ):
        with patch("academy_engine.exercise_state.sysconfig.get_path", return_value=str(self.data_root)):
            base, lab, authority = preflight_p08(self.repository)
            store = open_p08_store(
                self.repository, base=base, authority=authority, test_root=self.state_root
            )
            prepared = prepare_p08(self.repository, store, lab)
        with store.locked() as locked:
            record = locked.read_record("p08", 1)
        self.assertIsNotNone(record)
        assert record is not None
        target = self.repository / ".codearbiter/reports/academy/P08-hygiene.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        report = exercise_module._p08_expected_report(self.repository, record, base)
        if mutate_report is not None:
            mutate_report(report)
        if canonical:
            rendered = json.dumps(
                report, sort_keys=True, separators=(",", ":"), ensure_ascii=False
            ).encode("utf-8") + b"\n"
        else:
            rendered = json.dumps(report, indent=2, ensure_ascii=False).encode("utf-8") + b"\n"
        target.write_bytes(rendered)
        git(self.repository, "add", "--", target.relative_to(self.repository).as_posix())
        if executable:
            git(
                self.repository,
                "update-index",
                "--chmod=+x",
                target.relative_to(self.repository).as_posix(),
            )
        if mode in {"symlink", "gitlink"}:
            object_id = base
            if mode == "symlink":
                hashed = subprocess.run(
                    ["git", "hash-object", "-w", "--stdin"],
                    cwd=self.repository,
                    input="outside-report.json\n",
                    text=True,
                    capture_output=True,
                    check=True,
                )
                object_id = hashed.stdout.strip()
            git(
                self.repository,
                "update-index",
                "--add",
                "--cacheinfo",
                f"{'120000' if mode == 'symlink' else '160000'},{object_id},{target.relative_to(self.repository).as_posix()}",
            )
        if extra_path is not None:
            extra = self.repository / extra_path
            extra.parent.mkdir(parents=True, exist_ok=True)
            extra.write_text("not P08 evidence\n", encoding="utf-8")
            git(self.repository, "add", "--", extra_path)
        git(self.repository, "commit", "-m", "academy: report P08 hygiene")
        head = git(self.repository, "rev-parse", "HEAD").stdout.strip()
        return base, store, prepared, record, exercise_module.P08AttemptIdentity(
            1, prepared.branch, prepared.commit_sha, head
        )

    def test_p08_checkpoint_rejects_noncanonical_report_bytes(self) -> None:
        _base, store, _prepared, _record, identity = self._p08_checkpoint_candidate(
            canonical=False
        )

        with patch("academy_engine.exercise_state.sysconfig.get_path", return_value=str(self.data_root)):
            self.assertFalse(exercise_module.validate_p08_checkpoint(self.repository, store, identity))

    def test_p08_checkpoint_rejects_extra_evidence_path(self) -> None:
        _base, store, _prepared, _record, identity = self._p08_checkpoint_candidate(
            extra_path="docs/not-p08-evidence.md"
        )

        with patch("academy_engine.exercise_state.sysconfig.get_path", return_value=str(self.data_root)):
            self.assertFalse(exercise_module.validate_p08_checkpoint(self.repository, store, identity))

    def test_p08_checkpoint_rejects_executable_report_blob(self) -> None:
        _base, store, _prepared, _record, identity = self._p08_checkpoint_candidate(
            executable=True
        )

        with patch("academy_engine.exercise_state.sysconfig.get_path", return_value=str(self.data_root)):
            self.assertFalse(exercise_module.validate_p08_checkpoint(self.repository, store, identity))

    def test_p08_checkpoint_rejects_symlink_report_entry(self) -> None:
        _base, store, _prepared, _record, identity = self._p08_checkpoint_candidate(
            mode="symlink"
        )
        with patch("academy_engine.exercise_state.sysconfig.get_path", return_value=str(self.data_root)):
            self.assertFalse(exercise_module.validate_p08_checkpoint(self.repository, store, identity))

    def test_p08_checkpoint_rejects_gitlink_report_entry(self) -> None:
        _base, store, _prepared, _record, identity = self._p08_checkpoint_candidate(
            mode="gitlink"
        )
        with patch("academy_engine.exercise_state.sysconfig.get_path", return_value=str(self.data_root)):
            self.assertFalse(exercise_module.validate_p08_checkpoint(self.repository, store, identity))

    def test_p08_checkpoint_rejects_canonical_but_wrong_containment_and_unique_facts(self) -> None:
        def mutate(report):
            report["refs"][3]["merged_into_base"] = True
            report["refs"][3]["unique_commits"] = 0

        _base, store, _prepared, _record, identity = self._p08_checkpoint_candidate(
            mutate_report=mutate
        )

        with patch("academy_engine.exercise_state.sysconfig.get_path", return_value=str(self.data_root)):
            self.assertFalse(exercise_module.validate_p08_checkpoint(self.repository, store, identity))

    def test_p08_checkpoint_rejects_fixture_ref_rebinding_after_report_commit(self) -> None:
        _base, store, _prepared, record, identity = self._p08_checkpoint_candidate()
        fixture = record["refs"][2]
        git(
            self.repository,
            "update-ref",
            fixture["ref_name"],
            identity.head_commit,
        )

        with patch("academy_engine.exercise_state.sysconfig.get_path", return_value=str(self.data_root)):
            self.assertFalse(exercise_module.validate_p08_checkpoint(self.repository, store, identity))

    def test_p08_checkpoint_rejects_stale_identity_and_dirty_primary_checkout(self) -> None:
        _base, store, prepared, _record, identity = self._p08_checkpoint_candidate()
        stale = exercise_module.P08AttemptIdentity(
            1, prepared.branch, prepared.commit_sha, prepared.commit_sha
        )

        with patch("academy_engine.exercise_state.sysconfig.get_path", return_value=str(self.data_root)):
            self.assertFalse(exercise_module.validate_p08_checkpoint(self.repository, store, stale))
        (self.repository / "uncommitted-p08-drift.txt").write_text("drift\n", encoding="utf-8")

        with patch("academy_engine.exercise_state.sysconfig.get_path", return_value=str(self.data_root)):
            self.assertFalse(exercise_module.validate_p08_checkpoint(self.repository, store, identity))

    def test_p08_checkpoint_rejects_unrecorded_detached_linked_worktree(self) -> None:
        _base, store, _prepared, record, identity = self._p08_checkpoint_candidate()
        with store.locked() as locked:
            owned = record["worktrees"][1]
            outside = locked.owned_p08_worktree_parent(1, owned["worktree_id"]) / "unrecorded-p08-worktree"
        git(
            self.repository,
            "worktree",
            "add",
            "--detach",
            str(outside),
            identity.head_commit,
        )

        with patch("academy_engine.exercise_state.sysconfig.get_path", return_value=str(self.data_root)):
            self.assertFalse(exercise_module.validate_p08_checkpoint(self.repository, store, identity))

    def test_p08_checkpoint_preserves_unrelated_detached_worktree(self) -> None:
        _base, store, _prepared, _record, identity = self._p08_checkpoint_candidate()
        unrelated = Path(self.temporary.name) / "unrelated-detached-worktree"
        git(
            self.repository,
            "worktree",
            "add",
            "--detach",
            str(unrelated),
            identity.head_commit,
        )

        with patch("academy_engine.exercise_state.sysconfig.get_path", return_value=str(self.data_root)):
            self.assertTrue(exercise_module.validate_p08_checkpoint(self.repository, store, identity))

    def test_p08_checkpoint_preserves_unrelated_ordinary_linked_worktree(self) -> None:
        _base, store, _prepared, _record, identity = self._p08_checkpoint_candidate()
        unrelated = Path(self.temporary.name) / "unrelated-linked-worktree"
        git(self.repository, "branch", "unrelated/ordinary", identity.head_commit)
        git(self.repository, "worktree", "add", str(unrelated), "unrelated/ordinary")

        with patch("academy_engine.exercise_state.sysconfig.get_path", return_value=str(self.data_root)):
            self.assertTrue(exercise_module.validate_p08_checkpoint(self.repository, store, identity))

    def test_p08_checkpoint_preserves_real_bare_porcelain_entry(self) -> None:
        _base, store, _prepared, _record, identity = self._p08_checkpoint_candidate()
        bare = Path(self.temporary.name) / "unrelated-bare.git"
        git(bare.parent, "init", "--bare", str(bare))
        bare_entry = git(bare, "worktree", "list", "--porcelain", "-z").stdout
        self.assertIn("\0bare\0\0", bare_entry)
        original_git = exercise_module._git

        def with_bare_entry(repository, args, *, code="transition-incomplete"):
            result = original_git(repository, args, code=code)
            if args == ["worktree", "list", "--porcelain", "-z"]:
                return result + bare_entry
            return result

        with patch("academy_engine.exercise_state.sysconfig.get_path", return_value=str(self.data_root)), patch.object(
            exercise_module, "_git", side_effect=with_bare_entry
        ):
            self.assertTrue(exercise_module.validate_p08_checkpoint(self.repository, store, identity))

    def test_p08_checkpoint_uses_committed_report_not_checkout_bytes(self) -> None:
        _base, store, _prepared, _record, identity = self._p08_checkpoint_candidate()
        target = self.repository / ".codearbiter/reports/academy/P08-hygiene.json"
        target.write_bytes(b'{"checkout":"substitution"}\n')
        git(
            self.repository,
            "update-index",
            "--assume-unchanged",
            target.relative_to(self.repository).as_posix(),
        )

        with patch("academy_engine.exercise_state.sysconfig.get_path", return_value=str(self.data_root)):
            self.assertTrue(exercise_module.validate_p08_checkpoint(self.repository, store, identity))

    def test_p08_checkpoint_rejects_linked_marker_drift(self) -> None:
        _base, store, _prepared, record, identity = self._p08_checkpoint_candidate()
        with store.locked() as locked:
            dirty = record["worktrees"][2]
            parent = locked.owned_p08_worktree_parent(1, dirty["worktree_id"])
        target = parent / dirty["worktree_id"]
        (target / ".arbiter-academy-p08-dirty").write_text("tampered\n", encoding="utf-8")

        with patch("academy_engine.exercise_state.sysconfig.get_path", return_value=str(self.data_root)):
            self.assertFalse(exercise_module.validate_p08_checkpoint(self.repository, store, identity))

    def test_p08_checkpoint_rejects_linked_admin_drift(self) -> None:
        _base, store, _prepared, record, identity = self._p08_checkpoint_candidate()
        with store.locked() as locked:
            linked = record["worktrees"][1]
            parent = locked.owned_p08_worktree_parent(1, linked["worktree_id"])
        target = parent / linked["worktree_id"]
        git_file = target / ".git"
        if sys.platform == "win32":
            subprocess.run(
                ["attrib", "-H", "-R", str(git_file)],
                check=True,
                capture_output=True,
                text=True,
            )
        git_file.chmod(stat.S_IREAD | stat.S_IWRITE)
        git_file.write_text("gitdir: invalid-admin\n", encoding="utf-8")

        with patch("academy_engine.exercise_state.sysconfig.get_path", return_value=str(self.data_root)):
            self.assertFalse(exercise_module.validate_p08_checkpoint(self.repository, store, identity))

    def test_p08_checkpoint_rejects_linked_worktree_path_drift(self) -> None:
        _base, store, _prepared, record, identity = self._p08_checkpoint_candidate()
        with store.locked() as locked:
            linked = record["worktrees"][1]
            parent = locked.owned_p08_worktree_parent(1, linked["worktree_id"])
        target = parent / linked["worktree_id"]
        target.rename(parent / "moved-linked-worktree")

        with patch("academy_engine.exercise_state.sysconfig.get_path", return_value=str(self.data_root)):
            self.assertFalse(exercise_module.validate_p08_checkpoint(self.repository, store, identity))

    def _commit_base_profile_mutation_outside_patch_hunks(self) -> str:
        profile = self.repository / ".codearbiter/tech-stack.md"
        original = profile.read_bytes()
        tampered = original.replace(
            b"- Python 3.11 or newer.",
            b"- Python 3.12 or newer.",
            1,
        )
        self.assertNotEqual(tampered, original)
        profile.write_bytes(tampered)
        git(self.repository, "add", "--", ".codearbiter/tech-stack.md")
        git(self.repository, "commit", "-m", "tamper with base learner profile")
        return hashlib.sha256(tampered).hexdigest()

    def _commit_authority_valid_main_drift(self, recorded_base: str) -> str:
        tree = git(
            self.repository,
            "rev-parse",
            f"{recorded_base}^{{tree}}",
        ).stdout.strip()
        drift = git(
            self.repository,
            "commit-tree",
            tree,
            "-p",
            recorded_base,
            "-m",
            "test: authority-valid main drift",
        ).stdout.strip()
        self.assertNotEqual(drift, recorded_base)
        self.assertEqual(
            git(self.repository, "rev-parse", f"{drift}^{{tree}}").stdout.strip(),
            tree,
        )
        self.assertEqual(
            git(self.repository, "rev-parse", f"{drift}^").stdout.strip(),
            recorded_base,
        )
        return drift

    def _origin_directory(self, store):
        with store.locked() as locked:
            record = locked.read_record("p02", 1)
            directory, _ = locked.owned_repository_directory(
                "p02", 1, record["origin_repository"]["repository_id"]
            )
        return directory

    def _upstream_directory(self, store):
        with store.locked() as locked:
            record = locked.read_record("p02", 1)
            directory, _ = locked.owned_repository_directory(
                "p02", 1, record["upstream_repository"]["repository_id"]
            )
        return directory

    @staticmethod
    def _tree_snapshot(root: Path) -> dict[str, tuple[str, bytes | None]]:
        if not root.exists():
            return {}
        return {
            path.relative_to(root).as_posix(): (
                "directory" if path.is_dir() else "file",
                None if path.is_dir() else path.read_bytes(),
            )
            for path in sorted(root.rglob("*"))
        }

    def _verifiable_attempt(self):
        store, prepared = self._prepare()
        git(self.repository, "add", "workshop_queue/cli.py", "tests/test_cli.py")
        git(self.repository, "commit", "-m", "feat(queue): include unresolved tickets")
        work = git(self.repository, "rev-parse", "HEAD").stdout.strip()
        pushed = git(
            self.repository,
            "push",
            "origin",
            f"HEAD:refs/heads/{prepared.branch}",
            check=False,
        )
        self.assertEqual(pushed.returncode, 0, pushed.stderr)
        identity = P02AttemptIdentity(
            prepared.attempt,
            prepared.branch,
            prepared.commit_sha,
            work,
        )
        return store, prepared, identity

    def _receipt_for(self, prepared, work_head: str, commits: list[str]) -> dict[str, object]:
        return {
            "schema_version": 1,
            "mode": "offline-local",
            "lab_id": "P02-commit-review-pr",
            "attempt": prepared.attempt,
            "branch": prepared.branch,
            "prepared_commit": prepared.commit_sha,
            "work_head": work_head,
            "pushed_tip": work_head,
            "commits": commits,
            "review": {"status": "cleared"},
            "repositories": {
                "origin": {
                    "repository_id": prepared.origin_repository_id,
                    "role": "learner",
                },
                "upstream": {
                    "repository_id": prepared.upstream_repository_id,
                    "role": "official",
                },
            },
            "pr_reference": f"local-pr:{work_head[:12]}",
        }

    def _commit_receipt(
        self,
        payload: object,
        *,
        raw: bytes | None = None,
        extra_path: str | None = None,
    ) -> tuple[Path, str]:
        receipt_path = self.repository / ".codearbiter/reports/academy/P02-pr-receipt.json"
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_bytes(
            raw
            if raw is not None
            else (json.dumps(payload, sort_keys=True) + "\n").encode("utf-8")
        )
        paths = [receipt_path.relative_to(self.repository).as_posix()]
        if extra_path is not None:
            extra = self.repository / extra_path
            extra.parent.mkdir(parents=True, exist_ok=True)
            extra.write_text("unexpected\n", encoding="utf-8")
            paths.append(extra_path)
        git(self.repository, "add", "--", *paths)
        git(self.repository, "commit", "-m", "docs(academy): record P02 receipt")
        return receipt_path, git(self.repository, "rev-parse", "HEAD").stdout.strip()

    def _complete_checkpoint_attempt(self, *, split: bool = True):
        store, prepared = self._prepare()
        commits: list[str] = []
        if split:
            for path in ("tests/test_cli.py", "workshop_queue/cli.py"):
                git(self.repository, "add", "--", path)
                git(self.repository, "commit", "-m", f"feat(queue): apply {path}")
                commits.append(git(self.repository, "rev-parse", "HEAD").stdout.strip())
        else:
            git(self.repository, "add", "--", "tests/test_cli.py", "workshop_queue/cli.py")
            git(self.repository, "commit", "-m", "feat(queue): include unresolved tickets")
            commits.append(git(self.repository, "rev-parse", "HEAD").stdout.strip())
        work_head = commits[-1]
        pushed = git(
            self.repository,
            "push",
            "origin",
            f"HEAD:refs/heads/{prepared.branch}",
            check=False,
        )
        self.assertEqual(pushed.returncode, 0, pushed.stderr)
        receipt = self._receipt_for(prepared, work_head, commits)
        receipt_path, receipt_head = self._commit_receipt(receipt)
        identity = P02AttemptIdentity(
            prepared.attempt,
            prepared.branch,
            prepared.commit_sha,
            receipt_head,
        )
        return {
            "store": store,
            "prepared": prepared,
            "commits": commits,
            "work_head": work_head,
            "receipt": receipt,
            "receipt_path": receipt_path,
            "receipt_head": receipt_head,
            "identity": identity,
        }

    def _write_later_attempt(self, store, *, kind: str) -> None:
        with store.locked() as locked:
            first = locked.read_record("p02", 1)
            if kind == "corrupt":
                later = {"generation": 1, "unexpected": True}
            else:
                later = json.loads(json.dumps(first))
                later.update(
                    generation=1,
                    attempt=2,
                    attempt_branch="academy/P02-commit-review-pr/2",
                )
                if kind == "captured":
                    later.update(
                        phase="captured",
                        prepared_commit=None,
                        origin_repository=None,
                        upstream_repository=None,
                    )
                elif kind == "active":
                    for key, role in (
                        ("origin_repository", "learner"),
                        ("upstream_repository", "official"),
                    ):
                        repository_id = _p02_repository_id(
                            locked.repository_id, 2, role
                        )
                        directory, _ = locked.owned_repository_directory(
                            "p02", 2, repository_id, create=True
                        )
                        later[key]["repository_id"] = repository_id
                        later[key]["relative_directory"] = f"remotes/{directory.name}"
                else:
                    raise AssertionError(kind)
            locked.write_record("p02", 2, later, expected_generation=0)

    def _persist_archiving(self):
        store, prepared = self._prepare()
        git(self.repository, "add", "workshop_queue/cli.py", "tests/test_cli.py")
        git(self.repository, "commit", "-m", "feat(queue): include unresolved tickets")
        target = git(self.repository, "rev-parse", "HEAD").stdout.strip()
        archive = "refs/heads/academy/archive/P02-commit-review-pr/1/20260731T123456Z"
        with store.locked() as locked:
            record = locked.read_record("p02", 1)
            record["generation"] += 1
            record["phase"] = "archiving"
            record["archive_ref"] = archive
            record["archive_target"] = target
            record["transition_target"] = "reset"
            locked.write_record(
                "p02",
                1,
                record,
                expected_generation=record["generation"] - 1,
            )
        return store, prepared, target, archive

    def test_empty_or_partial_existing_bare_blocks_without_reinitialization(self) -> None:
        store, _ = self._store_and_lab()
        base = git(self.repository, "rev-parse", "HEAD").stdout.strip()
        with store.locked() as locked:
            repository_id = _p02_repository_id(locked.repository_id, 1, "learner")
            directory, created = locked.owned_repository_directory(
                "p02", 1, repository_id, create=True
            )
            self.assertTrue(created)
            marker = directory / "preserve.partial"
            marker.write_bytes(b"partial")
            before = {path.name: path.read_bytes() for path in directory.iterdir()}
            with self.assertRaisesRegex(ExerciseStateError, "incomplete"):
                _prepare_bare(
                    locked,
                    self.repository,
                    1,
                    "learner",
                    base,
                    _object_format(self.repository),
                )
            after = {path.name: path.read_bytes() for path in directory.iterdir()}
        self.assertEqual(after, before)

    def test_complete_existing_bare_is_adopted_without_reinitialization(self) -> None:
        store, _ = self._store_and_lab()
        base = git(self.repository, "rev-parse", "HEAD").stdout.strip()
        with store.locked() as locked:
            repository_id = _p02_repository_id(locked.repository_id, 1, "learner")
            directory, created = locked.owned_repository_directory(
                "p02", 1, repository_id, create=True
            )
            self.assertTrue(created)
            git(directory.parent, "init", "--bare", "--template=", str(directory))
            git(
                directory.parent,
                f"--git-dir={directory}",
                "fetch",
                "--no-tags",
                str(self.repository),
                f"{base}:refs/heads/main",
            )
            head_before = (directory / "HEAD").read_bytes()
            adopted, snapshot = _prepare_bare(
                locked,
                self.repository,
                1,
                "learner",
                base,
                _object_format(self.repository),
            )
        self.assertEqual(adopted, directory)
        self.assertEqual((directory / "HEAD").read_bytes(), head_before)
        self.assertEqual(snapshot["initial_refs"], [{"ref": "refs/heads/main", "object_id": base}])

    def test_bare_config_tampering_is_rejected_path_free(self) -> None:
        store, _ = self._prepare()
        origin = self._origin_directory(store)
        git(origin.parent, f"--git-dir={origin}", "config", "extensions.partialclone", "origin")

        with self.assertRaises(ExerciseStateError) as raised:
            _bare(origin, ["rev-parse", "--is-bare-repository"])

        self.assertEqual(raised.exception.code, "transition-incomplete")
        self.assertNotIn(str(origin), str(raised.exception))

    def test_bare_allows_optional_singleton_logallrefupdates_booleans(self) -> None:
        store, _ = self._prepare()
        origin = self._origin_directory(store)

        for value in ("true", "false"):
            with self.subTest(value=value):
                git(
                    origin.parent,
                    f"--git-dir={origin}",
                    "config",
                    "--replace-all",
                    "core.logallrefupdates",
                    value,
                )
                self.assertEqual(
                    _bare(origin, ["rev-parse", "--is-bare-repository"]).strip(),
                    "true",
                )

    def test_bare_rejects_invalid_or_duplicate_logallrefupdates_path_free(self) -> None:
        store, _ = self._prepare()
        origin = self._origin_directory(store)

        git(
            origin.parent,
            f"--git-dir={origin}",
            "config",
            "--replace-all",
            "core.logallrefupdates",
            "sometimes",
        )
        with self.assertRaises(ExerciseStateError) as invalid:
            _bare(origin, ["rev-parse", "--is-bare-repository"])
        git(
            origin.parent,
            f"--git-dir={origin}",
            "config",
            "--unset-all",
            "core.logallrefupdates",
        )
        for value in ("true", "false"):
            git(
                origin.parent,
                f"--git-dir={origin}",
                "config",
                "--add",
                "core.logallrefupdates",
                value,
            )
        with self.assertRaises(ExerciseStateError) as duplicate:
            _bare(origin, ["rev-parse", "--is-bare-repository"])

        for raised in (invalid, duplicate):
            self.assertEqual(raised.exception.code, "transition-incomplete")
            self.assertNotIn(str(origin), str(raised.exception))

    def test_bare_allows_each_optional_platform_key_to_be_omitted_independently(self) -> None:
        store, _ = self._prepare()
        origin = self._origin_directory(store)
        optional = (
            "core.filemode",
            "core.symlinks",
            "core.ignorecase",
            "core.precomposeunicode",
        )
        for key in optional:
            git(
                origin.parent,
                f"--git-dir={origin}",
                "config",
                "--replace-all",
                key,
                "true",
            )
        for key in optional:
            with self.subTest(key=key):
                try:
                    git(
                        origin.parent,
                        f"--git-dir={origin}",
                        "config",
                        "--unset-all",
                        key,
                    )
                    self.assertEqual(
                        _bare(origin, ["rev-parse", "--is-bare-repository"]).strip(),
                        "true",
                    )
                finally:
                    git(
                        origin.parent,
                        f"--git-dir={origin}",
                        "config",
                        key,
                        "true",
                    )

    def test_bare_rejects_invalid_or_duplicate_optional_platform_booleans(self) -> None:
        store, _ = self._prepare()
        origin = self._origin_directory(store)
        for key in (
            "core.filemode",
            "core.symlinks",
            "core.ignorecase",
            "core.precomposeunicode",
        ):
            with self.subTest(key=key, case="invalid"):
                git(
                    origin.parent,
                    f"--git-dir={origin}",
                    "config",
                    "--replace-all",
                    key,
                    "sometimes",
                )
                with self.assertRaises(ExerciseStateError) as invalid:
                    _bare(origin, ["rev-parse", "--is-bare-repository"])
                self.assertNotIn(str(origin), str(invalid.exception))
            git(
                origin.parent,
                f"--git-dir={origin}",
                "config",
                "--unset-all",
                key,
            )
            for value in ("true", "false"):
                git(
                    origin.parent,
                    f"--git-dir={origin}",
                    "config",
                    "--add",
                    key,
                    value,
                )
            with self.subTest(key=key, case="duplicate"):
                with self.assertRaises(ExerciseStateError) as duplicate:
                    _bare(origin, ["rev-parse", "--is-bare-repository"])
                self.assertNotIn(str(origin), str(duplicate.exception))
            git(
                origin.parent,
                f"--git-dir={origin}",
                "config",
                "--unset-all",
                key,
            )

    def test_bare_alternates_and_promisor_markers_are_rejected(self) -> None:
        store, _ = self._prepare()
        origin = self._origin_directory(store)
        alternates = origin / "objects/info/alternates"
        alternates.parent.mkdir(parents=True, exist_ok=True)
        alternates.write_text(str(self.repository / ".git/objects") + "\n", encoding="utf-8")
        with self.assertRaises(ExerciseStateError):
            _bare(origin, ["rev-parse", "--is-bare-repository"])
        alternates.unlink()
        promisor = origin / "objects/pack/forged.promisor"
        promisor.parent.mkdir(parents=True, exist_ok=True)
        promisor.write_bytes(b"")
        with self.assertRaises(ExerciseStateError):
            _bare(origin, ["rev-parse", "--is-bare-repository"])

    def test_unreachable_bare_object_is_rejected(self) -> None:
        store, _ = self._prepare()
        origin = self._origin_directory(store)
        payload = self.repository / "unreachable-object.txt"
        payload.write_text("not referenced\n", encoding="utf-8")
        git(
            origin.parent,
            f"--git-dir={origin}",
            "hash-object",
            "-w",
            str(payload),
        )

        with self.assertRaisesRegex(ExerciseStateError, "incomplete"):
            _require_complete_object_set(origin)

    def test_reachable_object_output_rejects_duplicates_and_malformed_oids(self) -> None:
        oid = "a" * 40
        for label, output in (
            ("duplicate", f"{oid}\n{oid}\n"),
            ("malformed", "not-an-object-id\n"),
        ):
            with self.subTest(label=label), patch(
                "academy_engine.exercise_state._bare",
                return_value=output,
            ):
                with self.assertRaises(ExerciseStateError) as raised:
                    _reachable_ids(
                        Path("unused"),
                        ("--all",),
                        object_format="sha1",
                    )
                self.assertEqual(raised.exception.code, "transition-incomplete")

    def test_complete_object_set_rejects_duplicate_reachable_output(self) -> None:
        oid = "a" * 40
        with patch(
            "academy_engine.exercise_state._bare",
            side_effect=(f"{oid}\n", f"{oid}\n{oid}\n"),
        ):
            with self.assertRaises(ExerciseStateError) as raised:
                _require_complete_object_set(
                    Path("unused"),
                    object_format="sha1",
                )
        self.assertEqual(raised.exception.code, "transition-incomplete")

    def test_sha256_object_outputs_reject_malformed_duplicates_and_wrong_lengths(self) -> None:
        oid = "a" * 64
        cases = (
            ("duplicate-all", (f"{oid}\n{oid}\n",)),
            ("malformed-all", ("not-an-object-id\n",)),
            ("sha1-in-sha256-all", (f"{'a' * 40}\n",)),
            ("duplicate-reachable", (f"{oid}\n", f"{oid}\n{oid}\n")),
            ("malformed-reachable", (f"{oid}\n", "not-an-object-id\n")),
        )
        for label, outputs in cases:
            with self.subTest(case=label), patch(
                "academy_engine.exercise_state._bare",
                side_effect=outputs,
            ):
                with self.assertRaises(ExerciseStateError) as raised:
                    _require_complete_object_set(
                        Path("unused"),
                        object_format="sha256",
                    )
                self.assertEqual(raised.exception.code, "transition-incomplete")

    def test_checkpoint_with_absent_external_state_is_noncreating(self) -> None:
        base = git(self.repository, "rev-parse", "HEAD").stdout.strip()
        branch = "academy/P02-commit-review-pr/1"
        git(self.repository, "switch", "-c", branch)
        git(
            self.repository,
            "commit",
            "--allow-empty",
            "-m",
            "academy: prepare P02-commit-review-pr attempt 1",
        )
        prepared = git(self.repository, "rev-parse", "HEAD").stdout.strip()
        git(self.repository, "commit", "--allow-empty", "-m", "learner work")
        work = git(self.repository, "rev-parse", "HEAD").stdout.strip()
        receipt = {
            "schema_version": 1,
            "mode": "offline-local",
            "lab_id": "P02-commit-review-pr",
            "attempt": 1,
            "branch": branch,
            "prepared_commit": prepared,
            "work_head": work,
            "pushed_tip": work,
            "commits": [work],
            "review": {"status": "cleared"},
            "repositories": {
                "origin": {"repository_id": "a" * 64, "role": "learner"},
                "upstream": {"repository_id": "b" * 64, "role": "official"},
            },
            "pr_reference": f"local-pr:{work[:12]}",
        }
        _, head = self._commit_receipt(receipt)
        context = _SemanticContext(
            self.repository,
            _Attempt(branch, 1, prepared, base, head),
            Predicate(
                "review_pr_commit_range",
                "lab_semantics",
                {
                    "profile": "pr_receipt",
                    "receipt": ".codearbiter/reports/academy/P02-pr-receipt.json",
                },
            ),
        )
        self.assertFalse(self.state_root.exists())

        with patch(
            "academy_engine.exercise_state.sysconfig.get_path",
            return_value=str(self.data_root),
        ), patch(
            "academy_engine.external_state.resolve_state_root",
            return_value=self.state_root,
        ):
            self.assertFalse(
                _valid_offline_p02_receipt(
                    context,
                    ".codearbiter/reports/academy/P02-pr-receipt.json",
                )
            )

        self.assertFalse(self.state_root.exists())

    def test_installed_authority_ignores_replacement_refs(self) -> None:
        base = git(self.repository, "rev-parse", "HEAD").stdout.strip()
        catalog = self.repository / "academy/catalog.json"
        catalog.write_text('{"replacement":"must-not-bind"}\n', encoding="utf-8")
        git(self.repository, "add", "academy/catalog.json")
        git(self.repository, "commit", "-m", "test: replacement authority")
        replacement = git(self.repository, "rev-parse", "HEAD").stdout.strip()
        git(self.repository, "reset", "--hard", base)
        git(self.repository, "replace", base, replacement)

        with patch(
            "academy_engine.exercise_state.sysconfig.get_path",
            return_value=str(self.data_root),
        ):
            authority = _verified_epoch(self.repository, base)
        consumer = authority[0] if isinstance(authority, tuple) else authority

        self.assertEqual(authority.installed_root, self.installed)
        self.assertEqual(
            authority.catalog_sha256,
            hashlib.sha256((self.installed / "catalog.json").read_bytes()).hexdigest(),
        )

    def test_preparation_consumes_verified_scenario_and_patch_bytes_after_regular_file_swap(self) -> None:
        base = git(self.repository, "rev-parse", "HEAD").stdout.strip()
        scenario_path = self.installed / "scenarios/P02-commit-review-pr/files/scenario.json"
        patch_path = self.installed / "scenarios/P02-commit-review-pr/files/P02-worktree.patch"
        original_scenario = scenario_path.read_bytes()
        original_patch = patch_path.read_bytes()
        record = {
            "attempt": 1,
            "attempt_branch": "academy/P02-commit-review-pr/1",
            "base_head": base,
        }

        with patch(
            "academy_engine.exercise_state.sysconfig.get_path",
            return_value=str(self.data_root),
        ):
            authority = _verified_epoch(self.repository, base)
        consumer = authority[0] if isinstance(authority, tuple) else authority
        scenario_path.write_bytes(
            original_scenario.replace(b'"review-required"', b'"swapped-content"')
        )
        patch_path.write_bytes(
            original_patch.replace(
                b'counts["open"] + counts["claimed"]', b'counts["open"]'
            )
        )

        prepared = exercise_module._create_prepared_commit(
            self.repository, record, consumer
        )
        exercise_module._apply_patch(self.repository, consumer)

        observed = git(
            self.repository,
            "show",
            f"{prepared}:training_scenarios/P02-commit-review-pr.json",
        ).stdout.encode("utf-8", "surrogateescape")
        self.assertEqual(observed, original_scenario)
        self.assertIn(
            'counts["unresolved"] = counts["open"] + counts["claimed"]',
            (self.repository / "workshop_queue/cli.py").read_text(encoding="utf-8"),
        )

    def test_preparation_rejects_tampered_installed_patch_before_authority_capture(self) -> None:
        """Catches installed patch-byte tampering before P02 can create learner state."""
        base = git(self.repository, "rev-parse", "HEAD").stdout.strip()
        patch_path = self.installed / "scenarios/P02-commit-review-pr/files/P02-worktree.patch"
        original = patch_path.read_bytes()
        tampered = original.replace(
            b'counts["open"] + counts["claimed"]', b'counts["open"]', 1
        )
        self.assertNotEqual(tampered, original)
        profile = self.repository / ".codearbiter/tech-stack.md"
        before_profile = profile.read_bytes()
        patch_path.write_bytes(tampered)

        with patch(
            "academy_engine.exercise_state.sysconfig.get_path",
            return_value=str(self.data_root),
        ):
            with self.assertRaises(ExerciseStateError) as raised:
                open_p02_store(self.repository, base=base, test_root=self.state_root)

        self.assertEqual(raised.exception.code, "installed-authority-required")
        self.assertNotIn(str(self.repository), str(raised.exception))
        self.assertFalse(self.state_root.exists())
        self.assertEqual(
            git(self.repository, "branch", "--show-current").stdout.strip(), "main"
        )
        self.assertNotEqual(
            git(
                self.repository,
                "show-ref",
                "--verify",
                "--quiet",
                "refs/heads/academy/P02-commit-review-pr/1",
                check=False,
            ).returncode,
            0,
        )
        self.assertEqual(profile.read_bytes(), before_profile)
        self.assertFalse((self.repository / "training_scenarios").exists())

    def _assert_patch_rejects_redirected_parent(
        self, relative_path: str, *, junction: bool
    ) -> None:
        base = git(self.repository, "rev-parse", "HEAD").stdout.strip()
        with patch(
            "academy_engine.exercise_state.sysconfig.get_path",
            return_value=str(self.data_root),
        ):
            authority = _verified_epoch(self.repository, base)
        parent = self.repository / Path(relative_path).parent
        outside = self.repository.parent / f"outside-patch-{parent.name}"
        original_parent = self.repository.parent / f"original-patch-{parent.name}"
        shutil.copytree(parent, outside)
        canonical = subprocess.run(
            ["git", "show", f"HEAD:{relative_path}"],
            cwd=self.repository,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        ).stdout
        outside_target = outside / Path(relative_path).name
        outside_target.write_bytes(canonical)
        self.assertEqual(outside_target.read_bytes(), canonical)
        parent.rename(original_parent)
        try:
            if junction:
                command = Path(os.environ["SystemRoot"]) / "System32/cmd.exe"
                created = subprocess.run(
                    [
                        str(command),
                        "/d",
                        "/v:off",
                        "/c",
                        "mklink",
                        "/J",
                        str(parent),
                        str(outside),
                    ],
                    cwd=self.repository,
                    stdin=subprocess.DEVNULL,
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=10,
                )
                self.assertEqual(
                    created.returncode,
                    0,
                    (created.stdout + created.stderr)[:2048],
                )
            else:
                os.symlink(outside, parent, target_is_directory=True)
            redirected_status = git(
                self.repository,
                "status",
                "--porcelain",
                "--untracked-files=all",
            ).stdout
            if junction:
                self.assertEqual(redirected_status, "")
            else:
                self.assertNotEqual(redirected_status, "")

            caught = None
            try:
                exercise_module._apply_patch(self.repository, authority)
            except ExerciseStateError as error:
                caught = error

            self.assertEqual(outside_target.read_bytes(), canonical)
            self.assertIsNotNone(caught)
            self.assertEqual(caught.code, "transition-incomplete")
            self.assertEqual(str(caught), "P02 transition is incomplete.")
            self.assertNotIn(str(self.repository), str(caught))
            self.assertNotIn(str(outside), str(caught))
            self.assertEqual(
                git(
                    self.repository,
                    "status",
                    "--porcelain",
                    "--untracked-files=all",
                ).stdout,
                redirected_status,
            )
        finally:
            if os.path.lexists(parent):
                if junction:
                    os.rmdir(parent)
                else:
                    os.unlink(parent)
            original_parent.rename(parent)
        self.assertEqual(
            git(
                self.repository,
                "status",
                "--porcelain",
                "--untracked-files=all",
            ).stdout,
            "",
        )

    def test_apply_patch_validates_targets_before_repository_status(self) -> None:
        base = git(self.repository, "rev-parse", "HEAD").stdout.strip()
        with patch(
            "academy_engine.exercise_state.sysconfig.get_path",
            return_value=str(self.data_root),
        ):
            authority = _verified_epoch(self.repository, base)
        events = []
        real_validate = exercise_module._validate_patch_targets
        real_git = exercise_module._git

        def observe_validation(repository):
            events.append("validate")
            return real_validate(repository)

        def observe_git(repository, args, *, code="transition-incomplete"):
            if list(args) == ["status", "--porcelain", "--untracked-files=all"]:
                events.append("status")
            return real_git(repository, args, code=code)

        with patch(
            "academy_engine.exercise_state._validate_patch_targets",
            side_effect=observe_validation,
        ), patch(
            "academy_engine.exercise_state._git",
            side_effect=observe_git,
        ):
            exercise_module._apply_patch(self.repository, authority)

        self.assertEqual(events[:2], ["validate", "status"])
        self.assertGreaterEqual(events.count("validate"), 4)

    @unittest.skipUnless(os.name == "nt", "Windows junction boundary")
    def test_apply_patch_rejects_windows_directory_junction_ancestors_without_outside_write(self) -> None:
        for relative_path in exercise_module._PATCH_PATHS:
            with self.subTest(relative_path=relative_path):
                self._assert_patch_rejects_redirected_parent(
                    relative_path, junction=True
                )

    @unittest.skipIf(os.name == "nt", "POSIX symlink boundary")
    def test_apply_patch_rejects_posix_directory_symlink_ancestors_without_outside_write(self) -> None:
        for relative_path in exercise_module._PATCH_PATHS:
            with self.subTest(relative_path=relative_path):
                self._assert_patch_rejects_redirected_parent(
                    relative_path, junction=False
                )

    def test_checkpoint_consumes_verified_patch_bytes_after_regular_file_swap(self) -> None:
        base = git(self.repository, "rev-parse", "HEAD").stdout.strip()
        target = self.installed / "scenarios/P02-commit-review-pr/files/P02-worktree.patch"
        original = target.read_bytes()
        record = {
            "attempt": 1,
            "attempt_branch": "academy/P02-commit-review-pr/1",
            "base_head": base,
        }
        with patch(
            "academy_engine.exercise_state.sysconfig.get_path",
            return_value=str(self.data_root),
        ):
            authority = _verified_epoch(self.repository, base)
        consumer = authority[0] if isinstance(authority, tuple) else authority
        prepared = exercise_module._create_prepared_commit(
            self.repository, record, consumer
        )
        exercise_module._apply_patch(self.repository, consumer)
        git(self.repository, "add", "--", "tests/test_cli.py", "workshop_queue/cli.py")
        git(self.repository, "commit", "-m", "feat(queue): include unresolved tickets")
        work = git(self.repository, "rev-parse", "HEAD").stdout.strip()
        real_verified = exercise_module._verified_epoch
        swapped = False

        def verify_then_swap(repository, base):
            nonlocal swapped
            verified = real_verified(repository, base)
            target.write_bytes(
                original.replace(
                    b'counts["open"] + counts["claimed"]', b'counts["open"]'
                )
            )
            swapped = True
            return verified

        with patch(
            "academy_engine.exercise_state.sysconfig.get_path",
            return_value=str(self.data_root),
        ), patch(
            "academy_engine.exercise_state._verified_epoch",
            side_effect=verify_then_swap,
        ):
            self.assertTrue(_exact_patch_result(self.repository, prepared, work))
        self.assertTrue(swapped)

    def test_restore_consumes_the_catalog_captured_by_its_successful_verification(self) -> None:
        store, prepared = self._prepare()
        git(self.repository, "add", "--", "tests/test_cli.py", "workshop_queue/cli.py")
        git(self.repository, "commit", "-m", "feat(queue): include unresolved tickets")
        catalog = self.installed / "catalog.json"
        original = catalog.read_bytes()
        real_verified = exercise_module._verified_epoch
        verified_calls = 0

        def verify_then_swap(repository, base):
            nonlocal verified_calls
            verified_calls += 1
            if verified_calls != 1:
                raise AssertionError("restore reopened installed authority")
            authority = real_verified(repository, base)
            catalog.write_bytes(original + b"\n")
            return authority

        with patch(
            "academy_engine.exercise_state.sysconfig.get_path",
            return_value=str(self.data_root),
        ), patch(
            "academy_engine.exercise_state._verified_epoch",
            side_effect=verify_then_swap,
        ):
            restore_p02(
                self.repository,
                store,
                transition_to="P03-record-an-adr",
            )

        self.assertEqual(verified_calls, 1)
        with store.locked() as locked:
            self.assertEqual(locked.read_record("p02", 1)["phase"], "restored")

    def test_captured_record_decode_never_calls_hosted_remote_normalizer(self) -> None:
        base = git(self.repository, "rev-parse", "HEAD").stdout.strip()
        record = {
            "schema_version": 1,
            "generation": 1,
            "lab": "P02-commit-review-pr",
            "attempt": 1,
            "phase": "captured",
            "base_branch": "main",
            "base_head": base,
            "attempt_branch": "academy/P02-commit-review-pr/1",
            "prepared_commit": None,
            "archive_ref": None,
            "archive_target": None,
            "transition_target": None,
            "original_topology": {
                "config": {
                    "remote.origin.url": ["https://github.com/learner/arbiter-academy.git"],
                    "remote.origin.pushurl": None,
                    "remote.upstream.url": ["https://github.com/arbiterForge/arbiter-academy.git"],
                    "remote.upstream.pushurl": ["DISABLED"],
                    "remote.pushDefault": None,
                    "push.default": None,
                    "branch.main.remote": None,
                    "branch.main.pushRemote": None,
                },
                "effective_routes": {
                    "origin": {
                        "fetch": ["https://github.com/learner/arbiter-academy.git"],
                        "push": ["https://github.com/learner/arbiter-academy.git"],
                    },
                    "upstream": {
                        "fetch": ["https://github.com/arbiterForge/arbiter-academy.git"],
                        "push": ["DISABLED"],
                    },
                },
            },
            "origin_repository": None,
            "upstream_repository": None,
        }

        with patch(
            "academy_engine.exercise_state.normalize_github_remote",
            return_value=None,
            create=True,
        ) as hosted:
            decoded = _decode_p02_record(record, object_format=self.OBJECT_FORMAT)

        self.assertEqual(decoded["phase"], "captured")
        hosted.assert_not_called()

    def test_config_journal_resumes_after_unset_and_ordered_prefix_only(self) -> None:
        keys = (
            "remote.origin.url",
            "remote.origin.pushurl",
            "remote.upstream.url",
            "remote.upstream.pushurl",
        )

        def set_values(key: str, values: list[str] | None) -> None:
            git(self.repository, "config", "--unset-all", key, check=False)
            for value in values or ():
                git(self.repository, "config", "--add", key, value)

        cases = (
            (
                "activation",
                exercise_module._verify_activation_boundary,
                {
                    keys[0]: ["https://github.com/learner/arbiter-academy.git"],
                    keys[1]: None,
                    keys[2]: ["https://github.com/arbiterForge/arbiter-academy.git"],
                    keys[3]: ["DISABLED"],
                },
                {
                    keys[0]: ["file:///academy/origin-a", "file:///academy/origin-b"],
                    keys[1]: ["file:///academy/origin-a"],
                    keys[2]: ["file:///academy/upstream"],
                    keys[3]: ["DISABLED"],
                },
            ),
            (
                "restoration",
                exercise_module._verify_restoration_boundary,
                {
                    keys[0]: [
                        "https://github.com/learner/arbiter-academy.git",
                        "git@github.com:learner/arbiter-academy.git",
                    ],
                    keys[1]: None,
                    keys[2]: ["https://github.com/arbiterForge/arbiter-academy.git"],
                    keys[3]: ["DISABLED"],
                },
                {
                    keys[0]: ["file:///academy/origin"],
                    keys[1]: ["file:///academy/origin"],
                    keys[2]: ["file:///academy/upstream"],
                    keys[3]: ["DISABLED"],
                },
            ),
        )
        for label, verify, original, local in cases:
            source = original[keys[0]] if label == "activation" else local[keys[0]]
            target = local[keys[0]] if label == "activation" else original[keys[0]]
            for progress in (None, target[:1]):
                with self.subTest(direction=label, progress=progress):
                    baseline = original if label == "activation" else local
                    for key in keys:
                        set_values(key, baseline[key])
                    set_values(keys[0], progress)
                    verify(
                        self.repository,
                        original,
                        local,
                        keys,
                        0,
                        current_may_be_complete=True,
                    )
                    exercise_module._set_values(self.repository, keys[0], target)
                    verify(
                        self.repository,
                        original,
                        local,
                        keys,
                        1,
                        current_may_be_complete=False,
                    )
                    self.assertEqual(
                        exercise_module._config_values(self.repository, keys[0]), target
                    )
            for invalid in (
                ["file:///academy/novel"],
                list(reversed(target)),
                [*target, "file:///academy/superset"],
            ):
                with self.subTest(direction=label, invalid=invalid):
                    baseline = original if label == "activation" else local
                    for key in keys:
                        set_values(key, baseline[key])
                    set_values(keys[0], invalid)
                    before = exercise_module._config_values(self.repository, keys[0])
                    with self.assertRaises(ExerciseStateError):
                        verify(
                            self.repository,
                            original,
                            local,
                            keys,
                            0,
                            current_may_be_complete=True,
                        )
                    self.assertEqual(
                        exercise_module._config_values(self.repository, keys[0]), before
                    )

    def test_exact_topology_recomputes_effective_remote_routes(self) -> None:
        topology = exercise_module._capture_topology(self.repository)
        local = {
            "remote.origin.url": ["file:///academy/origin"],
            "remote.origin.pushurl": ["file:///academy/origin"],
            "remote.upstream.url": ["file:///academy/upstream"],
            "remote.upstream.pushurl": ["DISABLED"],
        }

        with patch(
            "academy_engine.exercise_state._effective",
            return_value=["file:///academy/forged-route"],
        ) as effective:
            with self.assertRaises(ExerciseStateError):
                exercise_module._verify_exact_topology(
                    self.repository, topology, local
                )

        effective.assert_called()

    def test_duplicate_disabled_upstream_pushurls_fail_before_first_record_write(self) -> None:
        store, lab = self._store_and_lab()
        git(
            self.repository,
            "config",
            "--add",
            "remote.upstream.pushurl",
            "DISABLED",
        )
        before = self._tree_snapshot(self.state_root)

        with patch(
            "academy_engine.exercise_state.sysconfig.get_path",
            return_value=str(self.data_root),
        ):
            with self.assertRaises(ExerciseStateError):
                prepare_p02(self.repository, store, lab)

        self.assertEqual(self._tree_snapshot(self.state_root), before)
        self.assertFalse((store._epoch_dir / "p02").exists())

    def test_p02_preflight_owns_the_singleton_disabled_pushurl_contract(self) -> None:
        """Catches relocation of the P02-only singleton rule outside its authorized boundary."""
        _, lab = self._store_and_lab()
        git(
            self.repository,
            "config",
            "--add",
            "remote.upstream.pushurl",
            "DISABLED",
        )

        with patch(
            "academy_engine.exercise_state.sysconfig.get_path",
            return_value=str(self.data_root),
        ), patch(
            "academy_engine.exercise_state.validate_training_remotes",
            return_value=None,
        ):
            with self.assertRaisesRegex(ExerciseStateError, "topology"):
                exercise_module.preflight_p02(self.repository, lab)

    def test_prepare_lab_preflights_dirty_branch_and_credentialed_remotes_before_state_creation(self) -> None:
        for condition in ("dirty", "off-branch", "credentialed"):
            with self.subTest(condition=condition):
                case = P02RealRepositoryTests(
                    "test_prepare_creates_exact_bares_patch_and_local_topology"
                )
                case.setUp()
                try:
                    if condition == "dirty":
                        (case.repository / "dirty.txt").write_text(
                            "dirty\n", encoding="utf-8"
                        )
                    elif condition == "off-branch":
                        git(case.repository, "switch", "-c", "topic")
                    else:
                        git(
                            case.repository,
                            "remote",
                            "set-url",
                            "origin",
                            "https://learner:secret@github.com/learner/arbiter-academy.git",
                        )
                    self.assertFalse(case.state_root.exists())

                    with patch(
                        "academy_engine.exercise_state.sysconfig.get_path",
                        return_value=str(case.data_root),
                    ), patch(
                        "academy_engine.external_state.resolve_state_root",
                        return_value=case.state_root,
                    ):
                        with self.assertRaises(PreparationError):
                            prepare_lab(
                                case.repository,
                                "P02-commit-review-pr",
                                installed_authority=True,
                            )

                    self.assertFalse(case.state_root.exists())
                finally:
                    case.doCleanups()

    def test_bare_boundary_rejects_redirected_internal_authority(self) -> None:
        store, _ = self._prepare()
        origin = self._origin_directory(store)
        loose_fanout = next(
            name
            for name in (f"{value:02x}" for value in range(256))
            if not (origin / "objects" / name).exists()
        )
        cases = (
            Path("refs/redirected"),
            Path("objects") / loose_fanout,
            Path("objects/pack/redirected"),
            Path("objects/info/redirected"),
            Path("logs/redirected"),
        )
        for index, relative in enumerate(cases):
            with self.subTest(relative=relative.as_posix()):
                outside = self.repository.parent / f"outside-bare-{index}"
                outside.mkdir()
                sentinel = outside / "preserve.txt"
                sentinel.write_bytes(b"preserve")
                redirected = origin / relative
                redirected.parent.mkdir(parents=True, exist_ok=True)
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
                            str(redirected),
                            str(outside),
                        ],
                        cwd=origin,
                        stdin=subprocess.DEVNULL,
                        capture_output=True,
                        check=False,
                        timeout=10,
                    )
                    self.assertEqual(
                        created.returncode,
                        0,
                        (created.stdout + created.stderr)[:2048],
                    )
                else:
                    os.symlink(outside, redirected, target_is_directory=True)
                try:
                    with self.assertRaises(ExerciseStateError) as raised:
                        _bare(origin, ["rev-parse", "--is-bare-repository"])
                    self.assertEqual(raised.exception.code, "transition-incomplete")
                    self.assertNotIn(str(outside), str(raised.exception))
                    self.assertEqual(sentinel.read_bytes(), b"preserve")
                finally:
                    if os.path.lexists(redirected):
                        if sys.platform == "win32":
                            os.rmdir(redirected)
                        else:
                            os.unlink(redirected)

    def test_bare_boundary_rejects_redirected_top_level_info(self) -> None:
        store, _ = self._prepare()
        origin = self._origin_directory(store)
        redirected = origin / "info"
        self.assertFalse(os.path.lexists(redirected))
        self.assertEqual(
            _bare(origin, ["rev-parse", "--is-bare-repository"]).strip(),
            "true",
        )
        outside = self.repository.parent / "outside-bare-info"
        outside.mkdir()
        sentinel = outside / "preserve.txt"
        sentinel.write_bytes(b"preserve")
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
                    str(redirected),
                    str(outside),
                ],
                cwd=origin,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                check=False,
                timeout=10,
            )
            self.assertEqual(
                created.returncode,
                0,
                (created.stdout + created.stderr)[:2048],
            )
        else:
            os.symlink(outside, redirected, target_is_directory=True)
        try:
            with self.assertRaises(ExerciseStateError) as raised:
                _bare(origin, ["rev-parse", "--is-bare-repository"])
            self.assertEqual(raised.exception.code, "transition-incomplete")
            self.assertNotIn(str(outside), str(raised.exception))
            self.assertEqual(sentinel.read_bytes(), b"preserve")
        finally:
            if os.path.lexists(redirected):
                if sys.platform == "win32":
                    os.rmdir(redirected)
                else:
                    os.unlink(redirected)

    def test_latest_record_rejects_noncanonical_attempt_entries(self) -> None:
        store, _ = self._prepare()
        extra = store._epoch_dir / "p02/01"
        extra.mkdir()
        before = (store._epoch_dir / "p02/1/state.json").read_bytes()

        with self.assertRaises(ExerciseStateError) as raised:
            has_active_p02(self.repository, store)

        self.assertEqual(raised.exception.code, "invalid-exercise-state")
        self.assertEqual((store._epoch_dir / "p02/1/state.json").read_bytes(), before)

    def test_retry_rejects_recorded_origin_snapshot_tamper_before_upstream_creation(self) -> None:
        store, lab = self._store_and_lab()
        real_prepare_bare = exercise_module._prepare_bare

        def stop_before_upstream(locked, repository, attempt, role, base, object_format):
            if role == "official":
                raise ExerciseStateError("transition-incomplete")
            return real_prepare_bare(
                locked, repository, attempt, role, base, object_format
            )

        with patch(
            "academy_engine.exercise_state.sysconfig.get_path",
            return_value=str(self.data_root),
        ), patch(
            "academy_engine.exercise_state._prepare_bare",
            side_effect=stop_before_upstream,
        ):
            with self.assertRaises(ExerciseStateError):
                prepare_p02(self.repository, store, lab)
        with store.locked() as locked:
            record = locked.read_record("p02", 1)
            self.assertEqual(record["phase"], "origin-ready")
            record["origin_repository"]["reachable_objects_sha256"] = "0" * 64
            record["generation"] += 1
            locked.write_record(
                "p02", 1, record, expected_generation=record["generation"] - 1
            )
        remotes_before = tuple(sorted(path.name for path in (self.state_root / "remotes").iterdir()))
        record_before = (store._epoch_dir / "p02/1/state.json").read_bytes()

        with patch(
            "academy_engine.exercise_state.sysconfig.get_path",
            return_value=str(self.data_root),
        ):
            with self.assertRaises(ExerciseStateError):
                prepare_p02(self.repository, store, lab)

        self.assertEqual(
            tuple(sorted(path.name for path in (self.state_root / "remotes").iterdir())),
            remotes_before,
        )
        self.assertEqual((store._epoch_dir / "p02/1/state.json").read_bytes(), record_before)

    def test_bares_ready_retry_rejects_upstream_ref_tamper_before_learner_mutation(self) -> None:
        store, lab = self._store_and_lab()
        with patch(
            "academy_engine.exercise_state.sysconfig.get_path",
            return_value=str(self.data_root),
        ), patch(
            "academy_engine.exercise_state._create_prepared_commit",
            side_effect=ExerciseStateError("transition-incomplete"),
        ):
            with self.assertRaises(ExerciseStateError):
                prepare_p02(self.repository, store, lab)
        with store.locked() as locked:
            record = locked.read_record("p02", 1)
            self.assertEqual(record["phase"], "bares-ready")
            upstream, _ = locked.owned_repository_directory(
                "p02", 1, record["upstream_repository"]["repository_id"]
            )
        git(upstream.parent, f"--git-dir={upstream}", "update-ref", "-d", "refs/heads/main")
        record_before = (store._epoch_dir / "p02/1/state.json").read_bytes()
        refs_before = git(self.repository, "for-each-ref", "--format=%(refname)%00%(objectname)").stdout

        with patch(
            "academy_engine.exercise_state.sysconfig.get_path",
            return_value=str(self.data_root),
        ):
            with self.assertRaises(ExerciseStateError):
                prepare_p02(self.repository, store, lab)

        self.assertEqual(
            git(self.repository, "for-each-ref", "--format=%(refname)%00%(objectname)").stdout,
            refs_before,
        )
        self.assertEqual((store._epoch_dir / "p02/1/state.json").read_bytes(), record_before)

    def test_attempt_ready_retry_rejects_origin_config_tamper_before_worktree_mutation(self) -> None:
        store, lab = self._store_and_lab()
        with patch(
            "academy_engine.exercise_state.sysconfig.get_path",
            return_value=str(self.data_root),
        ), patch(
            "academy_engine.exercise_state._apply_patch",
            side_effect=ExerciseStateError("transition-incomplete"),
        ):
            with self.assertRaises(ExerciseStateError):
                prepare_p02(self.repository, store, lab)
        with store.locked() as locked:
            record = locked.read_record("p02", 1)
            self.assertEqual(record["phase"], "attempt-ready")
            origin, _ = locked.owned_repository_directory(
                "p02", 1, record["origin_repository"]["repository_id"]
            )
        git(origin.parent, f"--git-dir={origin}", "config", "academy.tamper", "present")
        status_before = git(
            self.repository, "status", "--porcelain", "--untracked-files=all"
        ).stdout
        record_before = (store._epoch_dir / "p02/1/state.json").read_bytes()

        with patch(
            "academy_engine.exercise_state.sysconfig.get_path",
            return_value=str(self.data_root),
        ):
            with self.assertRaises(ExerciseStateError):
                prepare_p02(self.repository, store, lab)

        self.assertEqual(
            git(self.repository, "status", "--porcelain", "--untracked-files=all").stdout,
            status_before,
        )
        self.assertEqual((store._epoch_dir / "p02/1/state.json").read_bytes(), record_before)

    def test_archiving_retry_rejects_same_oid_foreign_branch_before_mutation(self) -> None:
        store, _, target, archive = self._persist_archiving()
        git(self.repository, "branch", "foreign-same-oid", target)
        git(self.repository, "switch", "foreign-same-oid")
        record_before = (store._epoch_dir / "p02/1/state.json").read_bytes()
        config_before = (self.repository / ".git/config").read_bytes()

        with self.assertRaises(ExerciseStateError):
            restore_p02(self.repository, store, transition_to="reset")

        self.assertNotEqual(
            git(self.repository, "show-ref", "--verify", "--quiet", archive, check=False).returncode,
            0,
        )
        self.assertEqual((store._epoch_dir / "p02/1/state.json").read_bytes(), record_before)
        self.assertEqual((self.repository / ".git/config").read_bytes(), config_before)

    def test_archiving_retry_rejects_main_drift_before_mutation(self) -> None:
        store, prepared, _, archive = self._persist_archiving()
        git(self.repository, "update-ref", "refs/heads/main", prepared.commit_sha)
        record_before = (store._epoch_dir / "p02/1/state.json").read_bytes()
        config_before = (self.repository / ".git/config").read_bytes()

        with self.assertRaises(ExerciseStateError):
            restore_p02(self.repository, store, transition_to="reset")

        self.assertNotEqual(
            git(self.repository, "show-ref", "--verify", "--quiet", archive, check=False).returncode,
            0,
        )
        self.assertEqual((store._epoch_dir / "p02/1/state.json").read_bytes(), record_before)
        self.assertEqual((self.repository / ".git/config").read_bytes(), config_before)

    def test_prepare_retry_binds_existing_epoch_to_main_not_head(self) -> None:
        from academy_engine.scenario import PreparationError, prepare_lab

        real_write = exercise_module._write
        tripped = False

        def crash_at_worktree(locked, record, phase, **changes):
            nonlocal tripped
            if not tripped and phase == "worktree-ready":
                tripped = True
                raise ExerciseStateError("transition-incomplete")
            return real_write(locked, record, phase, **changes)

        with patch(
            "academy_engine.exercise_state.sysconfig.get_path",
            return_value=str(self.data_root),
        ), patch(
            "academy_engine.external_state.resolve_state_root",
            return_value=self.state_root,
        ), patch(
            "academy_engine.exercise_state._write", side_effect=crash_at_worktree
        ):
            with self.assertRaises(PreparationError):
                prepare_lab(
                    self.repository,
                    "P02-commit-review-pr",
                    installed_authority=True,
                )
        self.assertTrue(tripped)
        self.assertEqual(
            git(self.repository, "branch", "--show-current").stdout.strip(),
            "academy/P02-commit-review-pr/1",
        )

        with patch(
            "academy_engine.exercise_state.sysconfig.get_path",
            return_value=str(self.data_root),
        ), patch(
            "academy_engine.external_state.resolve_state_root",
            return_value=self.state_root,
        ):
            resumed = prepare_lab(
                self.repository,
                "P02-commit-review-pr",
                installed_authority=True,
            )

        self.assertEqual(resumed.attempt, 1)
        self.assertEqual(len(tuple((self.state_root / "repositories").rglob("identity.json"))), 1)

    def test_reset_missing_state_is_noncreating(self) -> None:
        from academy_engine.scenario import PreparationError, reset_lab

        with patch(
            "academy_engine.exercise_state.sysconfig.get_path",
            return_value=str(self.data_root),
        ), patch(
            "academy_engine.external_state.resolve_state_root",
            return_value=self.state_root,
        ):
            with self.assertRaises(PreparationError):
                reset_lab(
                    self.repository,
                    "P02-commit-review-pr",
                    installed_authority=True,
                )

        self.assertFalse(self.state_root.exists())

    def test_reset_main_drift_uses_existing_preparation_epoch_without_creation(self) -> None:
        from academy_engine.scenario import PreparationError, reset_lab

        store, prepared = self._prepare()
        git(self.repository, "add", "workshop_queue/cli.py", "tests/test_cli.py")
        git(self.repository, "commit", "-m", "feat(queue): include unresolved tickets")
        git(self.repository, "update-ref", "refs/heads/main", prepared.commit_sha)
        identities_before = tuple(
            sorted(path.read_bytes() for path in self.state_root.rglob("identity.json"))
        )
        record_before = (store._epoch_dir / "p02/1/state.json").read_bytes()

        with patch(
            "academy_engine.exercise_state.sysconfig.get_path",
            return_value=str(self.data_root),
        ), patch(
            "academy_engine.external_state.resolve_state_root",
            return_value=self.state_root,
        ):
            with self.assertRaises(PreparationError):
                reset_lab(
                    self.repository,
                    "P02-commit-review-pr",
                    installed_authority=True,
                )

        self.assertEqual(
            tuple(sorted(path.read_bytes() for path in self.state_root.rglob("identity.json"))),
            identities_before,
        )
        self.assertEqual((store._epoch_dir / "p02/1/state.json").read_bytes(), record_before)

    def test_installed_source_disappearance_is_path_free(self) -> None:
        store, lab = self._store_and_lab()
        (
            self.installed
            / "scenarios/P02-commit-review-pr/files/scenario.json"
        ).unlink()

        with patch(
            "academy_engine.exercise_state.sysconfig.get_path",
            return_value=str(self.data_root),
        ):
            with self.assertRaises(ExerciseStateError) as raised:
                prepare_p02(self.repository, store, lab)

        self.assertEqual(raised.exception.code, "installed-authority-required")
        self.assertNotIn(str(self.installed), str(raised.exception))

    def test_installed_authority_cleanliness_binds_to_explicit_base_with_dangling_head(self) -> None:
        """HEAD loss cannot hide consumed drift or invalidate an unchanged explicit base."""
        for kind in (
            "unchanged",
            "unstaged-edit",
            "staged-edit",
            "staged-delete-untracked-replacement",
            "committed-drift",
        ):
            with self.subTest(kind=kind):
                case = P02RealRepositoryTests(
                    "test_prepare_creates_exact_bares_patch_and_local_topology"
                )
                case.setUp()
                try:
                    base = git(case.repository, "rev-parse", "main").stdout.strip()
                    branch = "academy/authority-dangling-head"
                    git(case.repository, "switch", "-c", branch, base)
                    target = case.repository / "academy/catalog.json"
                    original = target.read_bytes()
                    if kind in {"unstaged-edit", "staged-edit", "committed-drift"}:
                        target.write_bytes(original + b"\n")
                    if kind == "staged-edit":
                        git(case.repository, "add", "--", "academy/catalog.json")
                    elif kind == "staged-delete-untracked-replacement":
                        target.unlink()
                        git(case.repository, "add", "--", "academy/catalog.json")
                        target.write_bytes(original)
                    elif kind == "committed-drift":
                        git(case.repository, "add", "--", "academy/catalog.json")
                        git(case.repository, "commit", "-m", "tamper with consumed authority")
                    git(
                        case.repository,
                        "update-ref",
                        "-d",
                        f"refs/heads/{branch}",
                    )

                    with patch(
                        "academy_engine.exercise_state.sysconfig.get_path",
                        return_value=str(case.data_root),
                    ):
                        if kind == "unchanged":
                            authority = _verified_epoch(case.repository, base)
                            self.assertEqual(
                                authority.catalog_sha256,
                                hashlib.sha256(
                                    (case.repository / "academy/catalog.json").read_bytes()
                                ).hexdigest(),
                            )
                        else:
                            with self.assertRaises(ExerciseStateError) as raised:
                                _verified_epoch(case.repository, base)
                            self.assertEqual(
                                raised.exception.code,
                                "installed-authority-required",
                            )
                finally:
                    case.doCleanups()

    def test_prepare_creates_exact_bares_patch_and_local_topology(self) -> None:
        store, prepared = self._prepare()

        self.assertEqual(prepared.branch, "academy/P02-commit-review-pr/1")
        self.assertRegex(prepared.origin_repository_id, r"^[0-9a-f]{64}$")
        self.assertRegex(prepared.upstream_repository_id, r"^[0-9a-f]{64}$")
        self.assertEqual(
            git(self.repository, "diff", "--name-only").stdout.splitlines(),
            ["tests/test_cli.py", "workshop_queue/cli.py"],
        )

    def test_preflight_rejects_base_profile_mutation_outside_patch_hunks(self) -> None:
        """Catches removal of the full canonical base-profile digest check."""
        lab = Catalog.load(self.installed / "catalog.json").lab(
            "P02-commit-review-pr"
        )
        self._commit_base_profile_mutation_outside_patch_hunks()

        with patch(
            "academy_engine.exercise_state.sysconfig.get_path",
            return_value=str(self.data_root),
        ):
            with self.assertRaises(ExerciseStateError) as raised:
                exercise_module.preflight_p02(self.repository, lab)

        self.assertEqual(raised.exception.code, "installed-authority-required")
        self.assertFalse(self.state_root.exists())
        self.assertEqual(
            git(self.repository, "branch", "--show-current").stdout.strip(),
            "main",
        )

    def test_prepare_rejects_base_profile_mutation_outside_patch_hunks(self) -> None:
        """Catches deriving the learner gate from arbitrary base-profile bytes."""
        store, lab = self._store_and_lab()
        self._commit_base_profile_mutation_outside_patch_hunks()

        with patch(
            "academy_engine.exercise_state.sysconfig.get_path",
            return_value=str(self.data_root),
        ):
            with self.assertRaises(ExerciseStateError) as raised:
                prepare_p02(self.repository, store, lab)

        self.assertEqual(raised.exception.code, "installed-authority-required")
        self.assertFalse((store._epoch_dir / "p02").exists())
        self.assertEqual(
            git(self.repository, "branch", "--show-current").stdout.strip(),
            "main",
        )

    def test_checkpoint_rejects_base_profile_mutation_outside_patch_hunks(self) -> None:
        """Catches checkpoint acceptance of work rooted in an unapproved base profile."""
        tampered_digest = self._commit_base_profile_mutation_outside_patch_hunks()
        with patch.object(
            exercise_module,
            "_BASE_PROFILE_SHA256",
            tampered_digest,
            create=True,
        ):
            completed = self._complete_checkpoint_attempt(split=True)

        with patch(
            "academy_engine.exercise_state.sysconfig.get_path",
            return_value=str(self.data_root),
        ):
            accepted = validate_p02_checkpoint(
                self.repository,
                completed["store"],
                completed["identity"],
                completed["receipt"],
            )

        self.assertFalse(accepted)

    def test_p02_prepares_a_verified_attempt_local_gate_without_weakening_main(self) -> None:
        """Catches an unbounded or unpinned learner commit gate in the prepared attempt."""
        release_profile = git(
            self.repository, "show", "main:.codearbiter/tech-stack.md"
        ).stdout
        self.assertIn("python -m unittest discover -v", release_profile)

        _, prepared = self._prepare()
        changed = git(
            self.repository,
            "diff-tree",
            "--no-commit-id",
            "--name-only",
            "-r",
            prepared.commit_sha,
        ).stdout.splitlines()
        self.assertEqual(
            changed,
            [
                ".codearbiter/tech-stack.md",
                "training_scenarios/P02-commit-review-pr.json",
            ],
        )
        learner_profile = git(
            self.repository,
            "show",
            f"{prepared.commit_sha}:.codearbiter/tech-stack.md",
        ).stdout
        for command in (
            "python -m unittest tests.test_cli -v",
            "python -m compileall -q workshop_queue tests/test_cli.py",
            "python scripts/scan_secrets.py --staged",
        ):
            self.assertIn(command, learner_profile)
        self.assertIn("P02 learner commit gate", learner_profile)
        self.assertNotIn("python -m unittest discover -v", learner_profile)
        self.assertEqual(
            git(self.repository, "show", "main:.codearbiter/tech-stack.md").stdout,
            release_profile,
        )
        self.assertEqual(
            git(self.repository, "diff", "--name-only").stdout.splitlines(),
            ["tests/test_cli.py", "workshop_queue/cli.py"],
        )

    def test_p02_real_two_commit_gate_checkpoint_and_reset_profile_lifecycle(self) -> None:
        """Proves both learner commits use the bounded profile and reset restores release policy."""
        store, prepared = self._prepare()
        learner_profile = (self.repository / ".codearbiter/tech-stack.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("P02 learner commit gate", learner_profile)
        release_profile = git(
            self.repository, "show", "main:.codearbiter/tech-stack.md"
        ).stdout
        gate_commands = (
            [sys.executable, "-m", "unittest", "tests.test_cli", "-v"],
            [
                sys.executable,
                "-m",
                "compileall",
                "-q",
                "workshop_queue",
                "tests/test_cli.py",
            ],
            [sys.executable, "scripts/scan_secrets.py", "--staged"],
        )

        def run_gate() -> float:
            started = time.monotonic()
            for command in gate_commands:
                completed = subprocess.run(
                    command,
                    cwd=self.repository,
                    stdin=subprocess.DEVNULL,
                    text=True,
                    capture_output=True,
                    check=False,
                    timeout=60,
                )
                self.assertEqual(
                    completed.returncode,
                    0,
                    f"{command!r}\n{completed.stdout}\n{completed.stderr}",
                )
            return time.monotonic() - started

        git(self.repository, "add", "--", "tests/test_cli.py", "workshop_queue/cli.py")
        first_duration = run_gate()
        git(self.repository, "commit", "-m", "feat(queue): include unresolved tickets")
        work = git(self.repository, "rev-parse", "HEAD").stdout.strip()
        commits = [work]
        pushed = git(
            self.repository,
            "push",
            "origin",
            f"HEAD:refs/heads/{prepared.branch}",
            check=False,
        )
        self.assertEqual(pushed.returncode, 0, pushed.stderr)
        receipt = self._receipt_for(prepared, work, commits)
        receipt_path = self.repository / ".codearbiter/reports/academy/P02-pr-receipt.json"
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(
            json.dumps(receipt, sort_keys=True) + "\n", encoding="utf-8"
        )
        git(
            self.repository,
            "add",
            "--",
            ".codearbiter/reports/academy/P02-pr-receipt.json",
        )
        second_duration = run_gate()
        self.p02_gate_durations = (first_duration, second_duration)
        git(self.repository, "commit", "-m", "docs(academy): record P02 receipt")
        receipt_head = git(self.repository, "rev-parse", "HEAD").stdout.strip()
        identity = P02AttemptIdentity(
            prepared.attempt,
            prepared.branch,
            prepared.commit_sha,
            receipt_head,
        )
        with patch(
            "academy_engine.exercise_state.sysconfig.get_path",
            return_value=str(self.data_root),
        ):
            self.assertTrue(validate_p02_checkpoint(self.repository, store, identity, receipt))
        self.assertLess(first_duration, 30.0)
        self.assertLess(second_duration, 30.0)

        with patch(
            "academy_engine.exercise_state.sysconfig.get_path",
            return_value=str(self.data_root),
        ):
            restore_p02(
                self.repository,
                store,
                transition_to="reset",
                now=lambda: __import__("datetime").datetime(
                    2026,
                    8,
                    1,
                    12,
                    0,
                    0,
                    tzinfo=__import__("datetime").timezone.utc,
                ),
            )
        self.assertEqual(
            (self.repository / ".codearbiter/tech-stack.md").read_text(
                encoding="utf-8"
            ),
            release_profile,
        )
        archive = (
            "refs/heads/academy/archive/P02-commit-review-pr/1/"
            "20260801T120000Z"
        )
        self.assertIn(
            "P02 learner commit gate",
            git(
                self.repository,
                "show",
                f"{archive}:.codearbiter/tech-stack.md",
            ).stdout,
        )

    def test_bares_ready_retry_rejects_same_parent_and_subject_with_wrong_profile(self) -> None:
        """A pre-created preparation branch cannot substitute an unverified learner gate."""
        store, lab = self._store_and_lab()
        with patch(
            "academy_engine.exercise_state.sysconfig.get_path",
            return_value=str(self.data_root),
        ), patch(
            "academy_engine.exercise_state._create_prepared_commit",
            side_effect=ExerciseStateError("transition-incomplete"),
        ):
            with self.assertRaises(ExerciseStateError):
                prepare_p02(self.repository, store, lab)
        with store.locked() as locked:
            record = locked.read_record("p02", 1)
        self.assertEqual(record["phase"], "bares-ready")
        branch = str(record["attempt_branch"])
        git(self.repository, "switch", "-c", branch, str(record["base_head"]))
        scenario = self.repository / "training_scenarios/P02-commit-review-pr.json"
        scenario.parent.mkdir(parents=True)
        shutil.copy2(
            self.installed / "scenarios/P02-commit-review-pr/files/scenario.json",
            scenario,
        )
        (self.repository / ".codearbiter/tech-stack.md").write_text(
            "# substituted learner gate\n", encoding="utf-8"
        )
        git(
            self.repository,
            "add",
            "--",
            ".codearbiter/tech-stack.md",
            "training_scenarios/P02-commit-review-pr.json",
        )
        git(
            self.repository,
            "commit",
            "-m",
            "academy: prepare P02-commit-review-pr attempt 1",
        )
        forged = git(self.repository, "rev-parse", "HEAD").stdout.strip()
        git(self.repository, "switch", "main")
        record_before = (store._epoch_dir / "p02/1/state.json").read_bytes()

        with patch(
            "academy_engine.exercise_state.sysconfig.get_path",
            return_value=str(self.data_root),
        ):
            with self.assertRaisesRegex(ExerciseStateError, "incomplete"):
                prepare_p02(self.repository, store, lab)

        self.assertEqual((store._epoch_dir / "p02/1/state.json").read_bytes(), record_before)
        self.assertEqual(
            git(self.repository, "rev-parse", f"refs/heads/{branch}").stdout.strip(),
            forged,
        )

    def test_active_resume_rejects_upstream_config_ref_and_object_drift(self) -> None:
        """Catches official-sidecar drift after P02 reaches active."""
        store, prepared = self._prepare()
        upstream = self._upstream_directory(store)
        lab = Catalog.load(self.installed / "catalog.json").lab("P02-commit-review-pr")
        mutations = (
            (
                "config",
                lambda: git(
                    upstream.parent,
                    f"--git-dir={upstream}",
                    "config",
                    "academy.tamper",
                    "present",
                ),
                lambda: git(
                    upstream.parent,
                    f"--git-dir={upstream}",
                    "config",
                    "--unset-all",
                    "academy.tamper",
                    check=False,
                ),
            ),
            (
                "ref",
                lambda: git(
                    upstream.parent,
                    f"--git-dir={upstream}",
                    "update-ref",
                    "refs/heads/foreign",
                    prepared.base_sha,
                ),
                lambda: git(
                    upstream.parent,
                    f"--git-dir={upstream}",
                    "update-ref",
                    "-d",
                    "refs/heads/foreign",
                ),
            ),
            (
                "unreachable-object",
                lambda: subprocess.run(
                    [
                        "git",
                        f"--git-dir={upstream}",
                        "hash-object",
                        "-w",
                        "--stdin",
                    ],
                    cwd=upstream.parent,
                    input="unreachable official object\n",
                    text=True,
                    capture_output=True,
                    check=True,
                ),
                lambda: None,
            ),
        )
        for label, mutate, restore in mutations:
            with self.subTest(label=label):
                mutate()
                before_record = (store._epoch_dir / "p02/1/state.json").read_bytes()
                before_config = (self.repository / ".git/config").read_bytes()
                try:
                    with patch(
                        "academy_engine.exercise_state.sysconfig.get_path",
                        return_value=str(self.data_root),
                    ):
                        with self.assertRaisesRegex(ExerciseStateError, "incomplete"):
                            prepare_p02(self.repository, store, lab)
                finally:
                    restore()
                self.assertEqual(
                    (store._epoch_dir / "p02/1/state.json").read_bytes(),
                    before_record,
                )
                self.assertEqual((self.repository / ".git/config").read_bytes(), before_config)

    def test_active_resume_accepts_the_owned_origin_attempt_tip(self) -> None:
        """Protects legitimate learner-origin evolution while official state stays exact."""
        store, prepared = self._prepare()
        git(self.repository, "add", "--", "tests/test_cli.py", "workshop_queue/cli.py")
        git(self.repository, "commit", "-m", "feat(queue): include unresolved tickets")
        pushed = git(
            self.repository,
            "push",
            "origin",
            f"HEAD:refs/heads/{prepared.branch}",
            check=False,
        )
        self.assertEqual(pushed.returncode, 0, pushed.stderr)
        lab = Catalog.load(self.installed / "catalog.json").lab("P02-commit-review-pr")

        with patch(
            "academy_engine.exercise_state.sysconfig.get_path",
            return_value=str(self.data_root),
        ):
            resumed = prepare_p02(self.repository, store, lab)

        self.assertEqual(resumed.attempt, prepared.attempt)
        self.assertEqual(resumed.commit_sha, prepared.commit_sha)
        origin = git(self.repository, "remote", "get-url", "--all", "origin").stdout.strip()
        upstream = git(self.repository, "remote", "get-url", "--all", "upstream").stdout.strip()
        self.assertTrue(origin.startswith("file:///"))
        self.assertTrue(upstream.startswith("file:///"))
        self.assertEqual(
            git(self.repository, "remote", "get-url", "--push", "--all", "upstream").stdout.strip(),
            "DISABLED",
        )
        with store.locked() as locked:
            record = locked.read_record("p02", 1)
        self.assertEqual(record["phase"], "active")
        self.assertEqual(
            prepared.origin_repository_id,
            record["origin_repository"]["repository_id"],
        )
        self.assertEqual(
            prepared.upstream_repository_id,
            record["upstream_repository"]["repository_id"],
        )
        self.assertEqual(record["original_topology"]["config"]["remote.upstream.pushurl"], ["DISABLED"])
        self.assertRegex(record["origin_repository"]["relative_directory"], r"^remotes/[0-9a-f]{64}$")
        rendered = json.dumps(record, sort_keys=True)
        self.assertNotIn("file:", rendered)
        self.assertNotIn(str(self.state_root), rendered)

    def test_existing_foreign_attempt_branch_blocks_without_switching_head(self) -> None:
        git(self.repository, "switch", "-c", "academy/P02-commit-review-pr/1")
        (self.repository / "foreign.txt").write_text("foreign\n", encoding="utf-8")
        git(self.repository, "add", "foreign.txt")
        git(self.repository, "commit", "-m", "foreign attempt")
        git(self.repository, "switch", "main")
        store, lab = self._store_and_lab()

        with patch("academy_engine.exercise_state.sysconfig.get_path", return_value=str(self.data_root)):
            with self.assertRaisesRegex(ExerciseStateError, "incomplete"):
                prepare_p02(self.repository, store, lab)

        self.assertEqual(git(self.repository, "branch", "--show-current").stdout.strip(), "main")

    def test_existing_exact_preparation_commit_with_executable_scenario_is_rejected(self) -> None:
        branch = "academy/P02-commit-review-pr/1"
        git(self.repository, "switch", "-c", branch)
        target = self.repository / "training_scenarios/P02-commit-review-pr.json"
        target.parent.mkdir()
        target.write_bytes(
            (self.installed / "scenarios/P02-commit-review-pr/files/scenario.json").read_bytes()
        )
        git(self.repository, "add", target.relative_to(self.repository).as_posix())
        git(
            self.repository,
            "update-index",
            "--chmod=+x",
            target.relative_to(self.repository).as_posix(),
        )
        if os.name != "nt":
            target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        git(self.repository, "commit", "-m", "academy: prepare P02-commit-review-pr attempt 1")
        self.assertEqual(git(self.repository, "status", "--porcelain").stdout, "")
        git(self.repository, "switch", "main")
        store, lab = self._store_and_lab()

        with patch(
            "academy_engine.exercise_state.sysconfig.get_path",
            return_value=str(self.data_root),
        ):
            with self.assertRaisesRegex(ExerciseStateError, "incomplete"):
                prepare_p02(self.repository, store, lab)

        self.assertEqual(git(self.repository, "branch", "--show-current").stdout.strip(), "main")

    @unittest.skipIf(os.name == "nt", "POSIX symlink boundary")
    def test_preparation_rejects_a_tracked_scenario_directory_symlink_without_outside_write(self) -> None:
        outside = self.repository.parent / "outside-scenarios"
        outside.mkdir()
        redirected = self.repository / "training_scenarios"
        os.symlink(outside, redirected, target_is_directory=True)
        git(self.repository, "add", "training_scenarios")
        git(self.repository, "commit", "-m", "test: tracked scenario redirect")
        store, lab = self._store_and_lab()

        with patch(
            "academy_engine.exercise_state.sysconfig.get_path",
            return_value=str(self.data_root),
        ):
            with self.assertRaises(ExerciseStateError) as raised:
                prepare_p02(self.repository, store, lab)

        self.assertEqual(raised.exception.code, "transition-incomplete")
        self.assertEqual(tuple(outside.iterdir()), ())
        self.assertNotIn(str(outside), str(raised.exception))

    @unittest.skipUnless(os.name == "nt", "Windows junction boundary")
    def test_preparation_rejects_a_scenario_directory_junction_without_outside_write(self) -> None:
        outside = self.repository.parent / "outside-scenarios"
        outside.mkdir()
        redirected = self.repository / "training_scenarios"
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
                str(outside),
            ],
            cwd=self.repository,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(created.returncode, 0, created.stdout + created.stderr)
        self.addCleanup(lambda: os.path.lexists(redirected) and os.rmdir(redirected))
        store, lab = self._store_and_lab()

        with patch(
            "academy_engine.exercise_state.sysconfig.get_path",
            return_value=str(self.data_root),
        ):
            with self.assertRaises(ExerciseStateError) as raised:
                prepare_p02(self.repository, store, lab)

        self.assertEqual(raised.exception.code, "transition-incomplete")
        self.assertEqual(tuple(outside.iterdir()), ())
        self.assertNotIn(str(outside), str(raised.exception))

    @unittest.skipUnless(hasattr(os, "link"), "hardlink boundary unavailable")
    def test_preparation_rejects_a_hardlinked_existing_scenario_without_outside_write(self) -> None:
        outside = self.repository.parent / "outside-scenario.json"
        original = b'{"preserve":"outside"}\n'
        outside.write_bytes(original)
        target = self.repository / "training_scenarios/P02-commit-review-pr.json"
        target.parent.mkdir()
        os.link(outside, target)
        git(self.repository, "add", target.relative_to(self.repository).as_posix())
        git(self.repository, "commit", "-m", "test: tracked scenario hardlink")
        store, lab = self._store_and_lab()

        with patch(
            "academy_engine.exercise_state.sysconfig.get_path",
            return_value=str(self.data_root),
        ):
            with self.assertRaises(ExerciseStateError) as raised:
                prepare_p02(self.repository, store, lab)

        self.assertEqual(raised.exception.code, "transition-incomplete")
        self.assertEqual(outside.read_bytes(), original)
        self.assertNotIn(str(outside), str(raised.exception))

    @unittest.skipUnless(hasattr(os, "link"), "hardlink boundary unavailable")
    def test_preparation_rejects_a_hardlinked_profile_before_any_mutation(self) -> None:
        outside = self.repository.parent / "outside-profile.md"
        profile = self.repository / ".codearbiter/tech-stack.md"
        original = profile.read_bytes()
        outside.write_bytes(original)
        profile.unlink()
        os.link(outside, profile)
        self.assertEqual(profile.stat().st_nlink, 2)
        store, lab = self._store_and_lab()
        state_before = self._tree_snapshot(self.state_root)
        config_before = (self.repository / ".git/config").read_bytes()
        refs_before = git(
            self.repository,
            "for-each-ref",
            "--format=%(refname) %(objectname)",
        ).stdout
        head_before = git(self.repository, "rev-parse", "HEAD").stdout

        with patch(
            "academy_engine.exercise_state.sysconfig.get_path",
            return_value=str(self.data_root),
        ):
            with self.assertRaises(ExerciseStateError) as raised:
                prepare_p02(self.repository, store, lab)

        self.assertEqual(raised.exception.code, "transition-incomplete")
        self.assertEqual(outside.read_bytes(), original)
        self.assertEqual(outside.stat().st_nlink, 2)
        self.assertEqual(self._tree_snapshot(self.state_root), state_before)
        self.assertEqual((self.repository / ".git/config").read_bytes(), config_before)
        self.assertEqual(
            git(
                self.repository,
                "for-each-ref",
                "--format=%(refname) %(objectname)",
            ).stdout,
            refs_before,
        )
        self.assertEqual(git(self.repository, "rev-parse", "HEAD").stdout, head_before)
        self.assertEqual(
            git(self.repository, "branch", "--show-current").stdout.strip(),
            "main",
        )
        self.assertEqual(
            git(
                self.repository,
                "status",
                "--porcelain",
                "--untracked-files=all",
            ).stdout,
            "",
        )
        self.assertNotIn(str(outside), str(raised.exception))

    @unittest.skipUnless(hasattr(os, "link"), "hardlink boundary unavailable")
    def test_bares_ready_retry_rejects_a_hardlinked_profile_before_learner_mutation(self) -> None:
        store, lab = self._store_and_lab()
        with patch(
            "academy_engine.exercise_state.sysconfig.get_path",
            return_value=str(self.data_root),
        ), patch(
            "academy_engine.exercise_state._create_prepared_commit",
            side_effect=ExerciseStateError("transition-incomplete"),
        ):
            with self.assertRaises(ExerciseStateError):
                prepare_p02(self.repository, store, lab)
        with store.locked() as locked:
            self.assertEqual(locked.read_record("p02", 1)["phase"], "bares-ready")
        outside = self.repository.parent / "outside-resumed-profile.md"
        profile = self.repository / ".codearbiter/tech-stack.md"
        original = profile.read_bytes()
        outside.write_bytes(original)
        profile.unlink()
        os.link(outside, profile)
        self.assertEqual(profile.stat().st_nlink, 2)
        state_before = self._tree_snapshot(self.state_root)
        config_before = (self.repository / ".git/config").read_bytes()
        refs_before = git(
            self.repository,
            "for-each-ref",
            "--format=%(refname) %(objectname)",
        ).stdout
        head_before = git(self.repository, "rev-parse", "HEAD").stdout
        branch_before = git(
            self.repository, "branch", "--show-current"
        ).stdout
        status_before = git(
            self.repository,
            "status",
            "--porcelain",
            "--untracked-files=all",
        ).stdout

        with patch(
            "academy_engine.exercise_state.sysconfig.get_path",
            return_value=str(self.data_root),
        ):
            with self.assertRaises(ExerciseStateError) as raised:
                prepare_p02(self.repository, store, lab)

        self.assertEqual(raised.exception.code, "transition-incomplete")
        self.assertEqual(outside.read_bytes(), original)
        self.assertEqual(outside.stat().st_nlink, 2)
        self.assertEqual(self._tree_snapshot(self.state_root), state_before)
        self.assertEqual((self.repository / ".git/config").read_bytes(), config_before)
        self.assertEqual(
            git(
                self.repository,
                "for-each-ref",
                "--format=%(refname) %(objectname)",
            ).stdout,
            refs_before,
        )
        self.assertEqual(git(self.repository, "rev-parse", "HEAD").stdout, head_before)
        self.assertEqual(
            git(self.repository, "branch", "--show-current").stdout,
            branch_before,
        )
        self.assertEqual(
            git(
                self.repository,
                "status",
                "--porcelain",
                "--untracked-files=all",
            ).stdout,
            status_before,
        )
        self.assertNotIn(str(outside), str(raised.exception))

    def test_retry_rejects_wrong_allowed_path_contents_before_remote_mutation(self) -> None:
        store, _ = self._prepare()
        with store.locked() as locked:
            record = locked.read_record("p02", 1)
            original = record["original_topology"]["config"]
            record["generation"] += 1
            record["phase"] = "worktree-ready"
            locked.write_record("p02", 1, record, expected_generation=record["generation"] - 1)
        for key in (
            "remote.origin.url",
            "remote.origin.pushurl",
            "remote.upstream.url",
            "remote.upstream.pushurl",
        ):
            git(self.repository, "config", "--unset-all", key, check=False)
            if original[key] is not None:
                for value in original[key]:
                    git(self.repository, "config", "--add", key, value)
        (self.repository / "workshop_queue/cli.py").write_text("wrong but allowed path\n", encoding="utf-8")
        before = git(self.repository, "config", "--null", "--get-all", "remote.origin.url")

        with patch("academy_engine.exercise_state.sysconfig.get_path", return_value=str(self.data_root)):
            lab = Catalog.load(self.installed / "catalog.json").lab("P02-commit-review-pr")
            with self.assertRaisesRegex(ExerciseStateError, "incomplete"):
                prepare_p02(self.repository, store, lab)

        after = git(self.repository, "config", "--null", "--get-all", "remote.origin.url")
        self.assertEqual((after.returncode, after.stdout), (before.returncode, before.stdout))

    def test_attempt_ready_retry_rejects_same_oid_on_foreign_branch_before_mutation(self) -> None:
        store, prepared = self._prepare()
        git(
            self.repository,
            "restore",
            "--source=HEAD",
            "--",
            "workshop_queue/cli.py",
            "tests/test_cli.py",
        )
        with store.locked() as locked:
            record = locked.read_record("p02", 1)
            original = record["original_topology"]["config"]
            record["generation"] += 1
            record["phase"] = "attempt-ready"
            locked.write_record(
                "p02", 1, record, expected_generation=record["generation"] - 1
            )
            before_record = locked.read_record("p02", 1)
        for key in (
            "remote.origin.url",
            "remote.origin.pushurl",
            "remote.upstream.url",
            "remote.upstream.pushurl",
        ):
            git(self.repository, "config", "--unset-all", key, check=False)
            if original[key] is not None:
                for value in original[key]:
                    git(self.repository, "config", "--add", key, value)
        git(self.repository, "switch", "-c", "foreign-retry", prepared.commit_sha)
        status_before = git(
            self.repository, "status", "--porcelain", "--untracked-files=all"
        ).stdout
        config_before = (self.repository / ".git/config").read_bytes()

        with patch(
            "academy_engine.exercise_state.sysconfig.get_path",
            return_value=str(self.data_root),
        ):
            lab = Catalog.load(self.installed / "catalog.json").lab(
                "P02-commit-review-pr"
            )
            with self.assertRaisesRegex(ExerciseStateError, "incomplete"):
                prepare_p02(self.repository, store, lab)

        self.assertEqual(
            git(self.repository, "status", "--porcelain", "--untracked-files=all").stdout,
            status_before,
        )
        self.assertEqual((self.repository / ".git/config").read_bytes(), config_before)
        self.assertEqual(git(self.repository, "branch", "--show-current").stdout.strip(), "foreign-retry")
        with store.locked() as locked:
            self.assertEqual(locked.read_record("p02", 1), before_record)

    def test_reset_archives_attempt_and_restores_exact_original_topology(self) -> None:
        store, prepared = self._prepare()
        git(self.repository, "add", "workshop_queue/cli.py", "tests/test_cli.py")
        git(self.repository, "commit", "-m", "feat(queue): include unresolved tickets")
        pushed = git(
            self.repository,
            "push",
            "origin",
            f"HEAD:refs/heads/{prepared.branch}",
            check=False,
        )
        self.assertEqual(pushed.returncode, 0, pushed.stderr)

        with patch("academy_engine.exercise_state.sysconfig.get_path", return_value=str(self.data_root)):
            restore_p02(
                self.repository,
                store,
                transition_to="reset",
                now=lambda: __import__("datetime").datetime(2026, 7, 31, 12, 34, 56, tzinfo=__import__("datetime").timezone.utc),
            )

        self.assertEqual(git(self.repository, "branch", "--show-current").stdout.strip(), "main")
        self.assertEqual(
            git(self.repository, "remote", "get-url", "--all", "origin").stdout.strip(),
            "https://github.com/learner/arbiter-academy.git",
        )
        self.assertEqual(
            git(self.repository, "remote", "get-url", "--all", "upstream").stdout.strip(),
            "https://github.com/arbiterForge/arbiter-academy.git",
        )
        self.assertNotIn(
            "file:",
            git(self.repository, "config", "--local", "--get-regexp", r"^remote\.", check=False).stdout,
        )
        self.assertEqual(
            git(self.repository, "show-ref", "--verify", "--hash", "refs/heads/academy/archive/P02-commit-review-pr/1/20260731T123456Z").stdout.strip(),
            git(self.repository, "rev-parse", prepared.branch).stdout.strip(),
        )
        with store.locked() as locked:
            self.assertEqual(locked.read_record("p02", 1)["phase"], "restored")

    def test_transition_accepts_any_canonical_catalog_lab_after_p02(self) -> None:
        store, _ = self._prepare()
        git(self.repository, "add", "workshop_queue/cli.py", "tests/test_cli.py")
        git(self.repository, "commit", "-m", "feat(queue): include unresolved tickets")

        with patch("academy_engine.exercise_state.sysconfig.get_path", return_value=str(self.data_root)):
            restore_p02(
                self.repository,
                store,
                transition_to="U01-autonomous-sprint",
                now=lambda: __import__("datetime").datetime(2026, 7, 31, 12, 34, 56, tzinfo=__import__("datetime").timezone.utc),
            )

        with store.locked() as locked:
            record = locked.read_record("p02", 1)
        self.assertEqual(record["phase"], "restored")
        self.assertEqual(record["transition_target"], "U01-autonomous-sprint")

    def test_new_archive_collision_blocks_before_journaling(self) -> None:
        store, prepared = self._prepare()
        git(self.repository, "add", "workshop_queue/cli.py", "tests/test_cli.py")
        git(self.repository, "commit", "-m", "feat(queue): include unresolved tickets")
        target = git(self.repository, "rev-parse", "HEAD").stdout.strip()
        archive = "refs/heads/academy/archive/P02-commit-review-pr/1/20260731T123456Z"
        git(self.repository, "update-ref", archive, target)

        with patch("academy_engine.exercise_state.sysconfig.get_path", return_value=str(self.data_root)):
            with self.assertRaisesRegex(ExerciseStateError, "incomplete"):
                restore_p02(
                    self.repository,
                    store,
                    transition_to="reset",
                    now=lambda: __import__("datetime").datetime(2026, 7, 31, 12, 34, 56, tzinfo=__import__("datetime").timezone.utc),
                )

        with store.locked() as locked:
            self.assertEqual(locked.read_record("p02", 1)["phase"], "active")

    def test_routing_drift_blocks_restoration_before_journaling(self) -> None:
        store, _ = self._prepare()
        git(self.repository, "add", "workshop_queue/cli.py", "tests/test_cli.py")
        git(self.repository, "commit", "-m", "feat(queue): include unresolved tickets")
        git(self.repository, "config", "remote.pushDefault", "upstream")

        with patch("academy_engine.exercise_state.sysconfig.get_path", return_value=str(self.data_root)):
            with self.assertRaisesRegex(ExerciseStateError, "incomplete"):
                restore_p02(self.repository, store, transition_to="reset")

        with store.locked() as locked:
            self.assertEqual(locked.read_record("p02", 1)["phase"], "active")

    def test_dirty_interrupted_restoration_blocks_before_ref_mutation(self) -> None:
        store, prepared = self._prepare()
        git(self.repository, "add", "workshop_queue/cli.py", "tests/test_cli.py")
        git(self.repository, "commit", "-m", "feat(queue): include unresolved tickets")
        target = git(self.repository, "rev-parse", "HEAD").stdout.strip()
        archive = "refs/heads/academy/archive/P02-commit-review-pr/1/20260731T123456Z"
        with store.locked() as locked:
            record = locked.read_record("p02", 1)
            record["generation"] += 1
            record["phase"] = "archiving"
            record["archive_ref"] = archive
            record["archive_target"] = target
            record["transition_target"] = "reset"
            locked.write_record(
                "p02", 1, record, expected_generation=record["generation"] - 1
            )
        (self.repository / "dirty-recovery.txt").write_text("preserve\n", encoding="utf-8")

        with patch(
            "academy_engine.exercise_state.sysconfig.get_path",
            return_value=str(self.data_root),
        ):
            with self.assertRaisesRegex(ExerciseStateError, "incomplete"):
                restore_p02(self.repository, store, transition_to="reset")

        self.assertNotEqual(
            git(self.repository, "show-ref", "--verify", "--quiet", archive, check=False).returncode,
            0,
        )
        with store.locked() as locked:
            self.assertEqual(locked.read_record("p02", 1)["phase"], "archiving")

    def test_restore_rejects_main_ref_drift_before_archive_or_journal_mutation(self) -> None:
        store, prepared = self._prepare()
        git(self.repository, "add", "workshop_queue/cli.py", "tests/test_cli.py")
        git(self.repository, "commit", "-m", "feat(queue): include unresolved tickets")
        drift = self._commit_authority_valid_main_drift(prepared.base_sha)
        git(self.repository, "branch", "-f", "main", drift)
        with store.locked() as locked:
            before_record = locked.read_record("p02", 1)
        config_before = (self.repository / ".git/config").read_bytes()

        with patch(
            "academy_engine.exercise_state.sysconfig.get_path",
            return_value=str(self.data_root),
        ):
            with self.assertRaises(ExerciseStateError) as raised:
                restore_p02(self.repository, store, transition_to="reset")
        self.assertEqual(raised.exception.code, "invalid-exercise-state")

        self.assertEqual((self.repository / ".git/config").read_bytes(), config_before)
        self.assertEqual(
            git(
                self.repository,
                "for-each-ref",
                "--format=%(refname)",
                "refs/heads/academy/archive/",
            ).stdout,
            "",
        )
        with store.locked() as locked:
            self.assertEqual(locked.read_record("p02", 1), before_record)

    def test_interrupted_restore_rejects_main_ref_drift_before_further_mutation(self) -> None:
        store, prepared = self._prepare()
        git(self.repository, "add", "workshop_queue/cli.py", "tests/test_cli.py")
        git(self.repository, "commit", "-m", "feat(queue): include unresolved tickets")
        real_write = exercise_module._write

        def crash_before_restoring(locked, record, next_phase, **changes):
            if next_phase == "restoring-origin-url":
                raise ExerciseStateError("transition-incomplete")
            return real_write(locked, record, next_phase, **changes)

        with patch(
            "academy_engine.exercise_state.sysconfig.get_path",
            return_value=str(self.data_root),
        ), patch(
            "academy_engine.exercise_state._write",
            side_effect=crash_before_restoring,
        ):
            with self.assertRaisesRegex(ExerciseStateError, "incomplete"):
                restore_p02(self.repository, store, transition_to="reset")
        drift = self._commit_authority_valid_main_drift(prepared.base_sha)
        git(self.repository, "update-ref", "refs/heads/main", drift)
        git(self.repository, "reset", "--hard", drift)
        with store.locked() as locked:
            before_record = locked.read_record("p02", 1)
        config_before = (self.repository / ".git/config").read_bytes()
        archive_before = git(
            self.repository,
            "for-each-ref",
            "--format=%(refname)%00%(objectname)",
            "refs/heads/academy/archive/",
        ).stdout

        with patch(
            "academy_engine.exercise_state.sysconfig.get_path",
            return_value=str(self.data_root),
        ):
            with self.assertRaises(ExerciseStateError) as raised:
                restore_p02(self.repository, store, transition_to="reset")
        self.assertEqual(raised.exception.code, "invalid-exercise-state")

        self.assertEqual((self.repository / ".git/config").read_bytes(), config_before)
        self.assertEqual(
            git(
                self.repository,
                "for-each-ref",
                "--format=%(refname)%00%(objectname)",
                "refs/heads/academy/archive/",
            ).stdout,
            archive_before,
        )
        with store.locked() as locked:
            self.assertEqual(locked.read_record("p02", 1), before_record)

    def test_exact_patch_result_rejects_executable_mode_forgery(self) -> None:
        _, prepared = self._prepare()
        git(self.repository, "add", "workshop_queue/cli.py", "tests/test_cli.py")
        git(self.repository, "update-index", "--chmod=+x", "workshop_queue/cli.py")
        git(self.repository, "commit", "-m", "feat(queue): include unresolved tickets")
        work = git(self.repository, "rev-parse", "HEAD").stdout.strip()

        with patch("academy_engine.exercise_state.sysconfig.get_path", return_value=str(self.data_root)):
            self.assertFalse(
                _exact_patch_result(self.repository, prepared.commit_sha, work)
            )

    def test_active_restore_rejects_a_missing_attempt_ref_without_state_or_topology_mutation(self) -> None:
        store, prepared = self._prepare()
        before_config = (self.repository / ".git" / "config").read_bytes()
        git(
            self.repository,
            "update-ref",
            "-d",
            f"refs/heads/{prepared.branch}",
        )

        with patch(
            "academy_engine.exercise_state.sysconfig.get_path",
            return_value=str(self.data_root),
        ):
            with self.assertRaisesRegex(ExerciseStateError, "incomplete"):
                restore_p02(self.repository, store, transition_to="reset")

        self.assertEqual((self.repository / ".git" / "config").read_bytes(), before_config)
        with store.locked() as locked:
            self.assertEqual(locked.read_record("p02", 1)["phase"], "active")

    def test_active_restore_rejects_upstream_config_ref_and_object_drift_before_mutation(self) -> None:
        """Catches official-sidecar drift at the active restoration boundary."""
        for mutation in ("config", "ref", "unreachable-object"):
            with self.subTest(mutation=mutation):
                case = P02RealRepositoryTests(
                    "test_prepare_creates_exact_bares_patch_and_local_topology"
                )
                case.setUp()
                try:
                    store, prepared = case._prepare()
                    git(
                        case.repository,
                        "add",
                        "--",
                        "tests/test_cli.py",
                        "workshop_queue/cli.py",
                    )
                    git(
                        case.repository,
                        "commit",
                        "-m",
                        "feat(queue): include unresolved tickets",
                    )
                    upstream = case._upstream_directory(store)
                    if mutation == "config":
                        git(
                            upstream.parent,
                            f"--git-dir={upstream}",
                            "config",
                            "academy.tamper",
                            "present",
                        )
                    elif mutation == "ref":
                        git(
                            upstream.parent,
                            f"--git-dir={upstream}",
                            "update-ref",
                            "refs/heads/foreign",
                            prepared.base_sha,
                        )
                    else:
                        subprocess.run(
                            [
                                "git",
                                f"--git-dir={upstream}",
                                "hash-object",
                                "-w",
                                "--stdin",
                            ],
                            cwd=upstream.parent,
                            input="unreachable official object\n",
                            text=True,
                            capture_output=True,
                            check=True,
                        )
                    record_path = store._epoch_dir / "p02/1/state.json"
                    before_record = record_path.read_bytes()
                    before_config = (case.repository / ".git/config").read_bytes()
                    before_refs = git(
                        case.repository,
                        "for-each-ref",
                        "--format=%(refname)%00%(objectname)",
                    ).stdout

                    with patch(
                        "academy_engine.exercise_state.sysconfig.get_path",
                        return_value=str(case.data_root),
                    ):
                        with case.assertRaisesRegex(ExerciseStateError, "incomplete"):
                            restore_p02(
                                case.repository, store, transition_to="reset"
                            )

                    self.assertEqual(record_path.read_bytes(), before_record)
                    self.assertEqual(
                        (case.repository / ".git/config").read_bytes(), before_config
                    )
                    self.assertEqual(
                        git(
                            case.repository,
                            "for-each-ref",
                            "--format=%(refname)%00%(objectname)",
                        ).stdout,
                        before_refs,
                    )
                finally:
                    case.doCleanups()

    def test_interrupted_restoration_revalidates_upstream_sidecar_before_retry(self) -> None:
        """Catches a retry that trusts a stale official snapshot after an earlier mutation."""
        store, _ = self._prepare()
        git(self.repository, "add", "--", "tests/test_cli.py", "workshop_queue/cli.py")
        git(self.repository, "commit", "-m", "feat(queue): include unresolved tickets")
        real_write = exercise_module._write
        tripped = False

        def crash_before_config_restore(locked, record, next_phase, **changes):
            nonlocal tripped
            if not tripped and next_phase == "restoring-origin-url":
                tripped = True
                raise ExerciseStateError("transition-incomplete")
            return real_write(locked, record, next_phase, **changes)

        with patch(
            "academy_engine.exercise_state.sysconfig.get_path",
            return_value=str(self.data_root),
        ), patch(
            "academy_engine.exercise_state._write",
            side_effect=crash_before_config_restore,
        ):
            with self.assertRaisesRegex(ExerciseStateError, "incomplete"):
                restore_p02(self.repository, store, transition_to="reset")
        self.assertTrue(tripped)
        upstream = self._upstream_directory(store)
        git(
            upstream.parent,
            f"--git-dir={upstream}",
            "config",
            "academy.retry-tamper",
            "present",
        )
        record_path = store._epoch_dir / "p02/1/state.json"
        before_record = record_path.read_bytes()
        before_config = (self.repository / ".git/config").read_bytes()

        with patch(
            "academy_engine.exercise_state.sysconfig.get_path",
            return_value=str(self.data_root),
        ):
            with self.assertRaisesRegex(ExerciseStateError, "incomplete"):
                restore_p02(self.repository, store, transition_to="reset")

        self.assertEqual(record_path.read_bytes(), before_record)
        self.assertEqual((self.repository / ".git/config").read_bytes(), before_config)

    def test_stale_p02_is_not_bypassed_by_an_empty_current_epoch(self) -> None:
        stale_store, prepared = self._prepare()
        git(self.repository, "add", "workshop_queue/cli.py", "tests/test_cli.py")
        git(self.repository, "commit", "-m", "feat(queue): include unresolved tickets")
        with patch(
            "academy_engine.exercise_state.sysconfig.get_path",
            return_value=str(self.data_root),
        ):
            restore_p02(self.repository, stale_store, transition_to="reset")
        marker = self.repository / "epoch-marker.txt"
        marker.write_text("current epoch\n", encoding="utf-8")
        git(self.repository, "add", "epoch-marker.txt")
        git(self.repository, "commit", "-m", "docs: advance Academy epoch")
        current_base = git(self.repository, "rev-parse", "HEAD").stdout.strip()
        with patch(
            "academy_engine.exercise_state.sysconfig.get_path",
            return_value=str(self.data_root),
        ):
            open_p02_store(
                self.repository,
                base=current_base,
                test_root=self.state_root,
            )
            self.assertTrue(
                exercise_module.ExternalStateStore.has_records(
                    self.repository,
                    lab="p02",
                    test_root=self.state_root,
                )
            )
            current = open_existing_p02_store(
                self.repository,
                base=current_base,
                test_root=self.state_root,
            )

        self.assertIsNone(current)
        with stale_store.locked() as locked:
            self.assertEqual(locked.read_record("p02", prepared.attempt)["phase"], "restored")

    def test_current_restored_p02_state_is_opened_and_true_absence_stays_nonmutating(self) -> None:
        empty_root = self.repository.parent / "absent-state"
        base = git(self.repository, "rev-parse", "HEAD").stdout.strip()
        with patch(
            "academy_engine.exercise_state.sysconfig.get_path",
            return_value=str(self.data_root),
        ):
            self.assertIsNone(
                open_existing_p02_store(
                    self.repository,
                    base=base,
                    test_root=empty_root,
                )
            )
        self.assertFalse(empty_root.exists())

        store, prepared = self._prepare()
        git(self.repository, "add", "workshop_queue/cli.py", "tests/test_cli.py")
        git(self.repository, "commit", "-m", "feat(queue): include unresolved tickets")
        with patch(
            "academy_engine.exercise_state.sysconfig.get_path",
            return_value=str(self.data_root),
        ):
            restore_p02(self.repository, store, transition_to="reset")
        with patch(
            "academy_engine.exercise_state.sysconfig.get_path",
            return_value=str(self.data_root),
        ):
            opened = open_existing_p02_store(
                self.repository,
                base=prepared.base_sha,
                test_root=self.state_root,
            )

        self.assertIsNotNone(opened)
        self.assertEqual(opened.repository_id, store.repository_id)

    def test_every_preparation_journal_boundary_resumes_exactly(self) -> None:
        phases = (
            "origin-ready",
            "bares-ready",
            "attempt-ready",
            "worktree-ready",
            "activating-origin-url",
            "activating-origin-pushurl",
            "activating-upstream-url",
            "activating-upstream-pushurl",
            "active",
        )
        for phase in phases:
            with self.subTest(phase=phase):
                case = P02RealRepositoryTests(
                    "test_prepare_creates_exact_bares_patch_and_local_topology"
                )
                case.setUp()
                try:
                    store, lab = case._store_and_lab()
                    real_write = exercise_module._write
                    tripped = False

                    def crash_once(locked, record, next_phase, **changes):
                        nonlocal tripped
                        if not tripped and next_phase == phase:
                            tripped = True
                            raise ExerciseStateError("transition-incomplete")
                        return real_write(locked, record, next_phase, **changes)

                    with patch(
                        "academy_engine.exercise_state.sysconfig.get_path",
                        return_value=str(case.data_root),
                    ), patch(
                        "academy_engine.exercise_state._write",
                        side_effect=crash_once,
                    ):
                        with case.assertRaises(ExerciseStateError):
                            prepare_p02(case.repository, store, lab)
                    self.assertTrue(tripped)
                    with patch(
                        "academy_engine.exercise_state.sysconfig.get_path",
                        return_value=str(case.data_root),
                    ):
                        resumed = prepare_p02(case.repository, store, lab)
                    self.assertEqual(resumed.attempt, 1)
                    with store.locked() as locked:
                        self.assertEqual(locked.read_record("p02", 1)["phase"], "active")
                finally:
                    case.doCleanups()

    def test_verified_base_profile_accepts_reviewed_bytes_and_rejects_one_byte_tamper_before_preparation(self) -> None:
        """The reviewed base binds before P02 can create learner state or refs."""
        try:
            store, _ = self._store_and_lab()
        except ExerciseStateError as error:
            self.assertEqual(error.code, "installed-authority-required")
            self.fail("the reviewed base profile must bind installed authority")
        self.assertFalse((store._epoch_dir / "p02").exists())
        self.assertFalse(
            git(
                self.repository,
                "show-ref",
                "--verify",
                "--quiet",
                "refs/heads/academy/P02-commit-review-pr/1",
                check=False,
            ).returncode
            == 0
        )

        case = P02RealRepositoryTests(
            "test_prepare_creates_exact_bares_patch_and_local_topology"
        )
        case.setUp()
        try:
            profile = case.repository / ".codearbiter/tech-stack.md"
            original = profile.read_bytes()
            tampered = original.replace(b"Python 3.11", b"Python 3.12", 1)
            case.assertNotEqual(tampered, original)
            profile.write_bytes(tampered)
            git(case.repository, "add", "--", ".codearbiter/tech-stack.md")
            git(case.repository, "commit", "-m", "test: one-byte profile tamper")
            before_head = git(case.repository, "rev-parse", "HEAD").stdout.strip()
            before_profile = profile.read_bytes()

            with case.assertRaises(ExerciseStateError) as raised:
                case._store_and_lab()

            case.assertEqual(raised.exception.code, "installed-authority-required")
            case.assertNotIn(str(case.repository), str(raised.exception))
            case.assertFalse(case.state_root.exists())
            case.assertEqual(
                git(case.repository, "branch", "--show-current").stdout.strip(), "main"
            )
            case.assertEqual(git(case.repository, "rev-parse", "HEAD").stdout.strip(), before_head)
            case.assertEqual(profile.read_bytes(), before_profile)
            case.assertNotEqual(
                git(
                    case.repository,
                    "show-ref",
                    "--verify",
                    "--quiet",
                    "refs/heads/academy/P02-commit-review-pr/1",
                    check=False,
                ).returncode,
                0,
            )
            case.assertFalse((case.repository / "training_scenarios").exists())
        finally:
            case.doCleanups()

    def test_attempt_ready_resume_accepts_only_exact_prepared_commit(self) -> None:
        """An attempt-ready resume accepts only its authenticated preparation commit."""
        def crash_boundary(case):
            store, lab = case._store_and_lab()
            real_write = exercise_module._write
            tripped = False

            def stop_at_attempt_ready(locked, record, phase, **changes):
                nonlocal tripped
                if not tripped and phase == "attempt-ready":
                    tripped = True
                    raise ExerciseStateError("transition-incomplete")
                return real_write(locked, record, phase, **changes)

            with patch(
                "academy_engine.exercise_state.sysconfig.get_path",
                return_value=str(case.data_root),
            ), patch(
                "academy_engine.exercise_state._write",
                side_effect=stop_at_attempt_ready,
            ):
                with case.assertRaisesRegex(ExerciseStateError, "incomplete"):
                    prepare_p02(case.repository, store, lab)
            case.assertTrue(tripped)
            with store.locked() as locked:
                record = locked.read_record("p02", 1)
            case.assertEqual(record["phase"], "bares-ready")
            branch = str(record["attempt_branch"])
            commit = git(
                case.repository, "rev-parse", f"refs/heads/{branch}"
            ).stdout.strip()
            return store, lab, record, commit

        def plumbing(case, *args):
            return subprocess.run(
                ["git", *args],
                cwd=case.repository,
                text=True,
                encoding="utf-8",
                capture_output=True,
                check=True,
                env={**os.environ, "GIT_INDEX_FILE": str(case.repository.parent / "mutant.index")},
            )

        def mutant_commit(case, exact, record, label):
            parent = git(case.repository, "rev-parse", f"{exact}^").stdout.strip()
            subject = git(
                case.repository, "show", "-s", "--format=%s", exact
            ).stdout.strip()
            tree = git(case.repository, "rev-parse", f"{exact}^{{tree}}").stdout.strip()
            scenario_path = "training_scenarios/P02-commit-review-pr.json"
            profile_path = ".codearbiter/tech-stack.md"

            def altered_tree(*index_commands):
                index = case.repository.parent / "mutant.index"
                if index.exists():
                    index.unlink()
                plumbing(case, "read-tree", tree)
                for command in index_commands:
                    plumbing(case, *command)
                return plumbing(case, "write-tree").stdout.strip()

            if label == "wrong parent":
                synthetic_parent = git(
                    case.repository,
                    "commit-tree",
                    f"{parent}^{{tree}}",
                    "-p",
                    parent,
                    "-m",
                    "test: synthetic alternate parent",
                ).stdout.strip()
                return git(
                    case.repository, "commit-tree", tree, "-p", synthetic_parent, "-m", subject
                ).stdout.strip()
            if label == "wrong subject":
                return git(
                    case.repository, "commit-tree", tree, "-p", parent, "-m", subject + " x"
                ).stdout.strip()
            if label == "extra path":
                blob = subprocess.run(
                    ["git", "hash-object", "-w", "--stdin"],
                    cwd=case.repository,
                    text=True,
                    encoding="utf-8",
                    input="foreign fixture\n",
                    capture_output=True,
                    check=True,
                ).stdout.strip()
                tree = altered_tree(
                    ("update-index", "--add", "--cacheinfo", f"100644,{blob},foreign.txt")
                )
            elif label == "missing path":
                tree = altered_tree(("update-index", "--force-remove", "--", scenario_path))
            elif label == "executable scenario":
                entry = git(case.repository, "ls-tree", exact, "--", scenario_path).stdout.split()[2]
                tree = altered_tree(
                    ("update-index", "--add", "--cacheinfo", f"100755,{entry},{scenario_path}")
                )
            elif label == "wrong scenario bytes":
                blob = subprocess.run(
                    ["git", "hash-object", "-w", "--stdin"],
                    cwd=case.repository,
                    text=True,
                    encoding="utf-8",
                    input="{\"wrong\":true}\n",
                    capture_output=True,
                    check=True,
                ).stdout.strip()
                tree = altered_tree(
                    ("update-index", "--add", "--cacheinfo", f"100644,{blob},{scenario_path}")
                )
            elif label == "wrong derived profile":
                blob = subprocess.run(
                    ["git", "hash-object", "-w", "--stdin"],
                    cwd=case.repository,
                    text=True,
                    encoding="utf-8",
                    input="# wrong profile fixture\n",
                    capture_output=True,
                    check=True,
                ).stdout.strip()
                tree = altered_tree(
                    ("update-index", "--add", "--cacheinfo", f"100644,{blob},{profile_path}")
                )
            else:
                raise AssertionError(label)
            return git(case.repository, "commit-tree", tree, "-p", parent, "-m", subject).stdout.strip()

        store, lab, record, exact = crash_boundary(self)
        branch = str(record["attempt_branch"])
        journal_path = store._epoch_dir / "p02/1/state.json"
        journal_before = journal_path.read_bytes()
        identity_before = json.loads(journal_before.decode("utf-8"))
        with patch(
            "academy_engine.exercise_state.sysconfig.get_path",
            return_value=str(self.data_root),
        ):
            resumed = prepare_p02(self.repository, store, lab)
        self.assertEqual(resumed.attempt, 1)
        self.assertEqual(resumed.branch, branch)
        self.assertEqual(resumed.commit_sha, exact)
        self.assertEqual(git(self.repository, "rev-parse", f"refs/heads/{branch}").stdout.strip(), exact)
        with store.locked() as locked:
            active = locked.read_record("p02", 1)
        self.assertEqual(active["phase"], "active")
        for key in ("attempt", "attempt_branch", "base_head"):
            self.assertEqual(active[key], identity_before[key])

        for label in (
            "wrong parent",
            "wrong subject",
            "extra path",
            "missing path",
            "executable scenario",
            "wrong scenario bytes",
            "wrong derived profile",
        ):
            with self.subTest(label=label):
                case = P02RealRepositoryTests(
                    "test_prepare_creates_exact_bares_patch_and_local_topology"
                )
                case.setUp()
                try:
                    store, lab, record, exact = crash_boundary(case)
                    branch = str(record["attempt_branch"])
                    git(case.repository, "switch", "main")
                    mutant = mutant_commit(case, exact, record, label)
                    case.assertNotEqual(mutant, exact)
                    scenario_path = "training_scenarios/P02-commit-review-pr.json"
                    paths = git(
                        case.repository,
                        "diff-tree",
                        "--no-commit-id",
                        "--name-only",
                        "-r",
                        mutant,
                    ).stdout.splitlines()
                    if label == "extra path":
                        case.assertEqual(
                            paths,
                            [
                                ".codearbiter/tech-stack.md",
                                "foreign.txt",
                                scenario_path,
                            ],
                        )
                    elif label == "missing path":
                        case.assertEqual(paths, [".codearbiter/tech-stack.md"])
                    else:
                        case.assertEqual(paths, [".codearbiter/tech-stack.md", scenario_path])
                    if label == "executable scenario":
                        case.assertTrue(
                            git(case.repository, "ls-tree", mutant, "--", scenario_path).stdout.startswith(
                                "100755 blob "
                            )
                        )
                    elif label == "wrong scenario bytes":
                        case.assertEqual(
                            git(case.repository, "show", f"{mutant}:{scenario_path}").stdout,
                            '{"wrong":true}\n',
                        )
                    elif label == "wrong derived profile":
                        case.assertEqual(
                            git(
                                case.repository,
                                "show",
                                f"{mutant}:.codearbiter/tech-stack.md",
                            ).stdout,
                            "# wrong profile fixture\n",
                        )
                    git(
                        case.repository,
                        "update-ref",
                        f"refs/heads/{branch}",
                        mutant,
                        exact,
                    )
                    journal_path = store._epoch_dir / "p02/1/state.json"
                    before_journal = journal_path.read_bytes()
                    before_identity = json.loads(before_journal.decode("utf-8"))
                    before_branch = git(case.repository, "branch", "--show-current").stdout.strip()
                    before_head = git(case.repository, "rev-parse", "HEAD").stdout.strip()
                    before_ref = git(
                        case.repository, "rev-parse", f"refs/heads/{branch}"
                    ).stdout.strip()
                    before_repository_id = store.repository_id
                    with patch(
                        "academy_engine.exercise_state.sysconfig.get_path",
                        return_value=str(case.data_root),
                    ):
                        with case.assertRaisesRegex(ExerciseStateError, "incomplete") as raised:
                            prepare_p02(case.repository, store, lab)
                    case.assertEqual(raised.exception.code, "transition-incomplete")
                    case.assertNotIn(str(case.repository), str(raised.exception))
                    case.assertEqual(
                        git(case.repository, "branch", "--show-current").stdout.strip(), before_branch
                    )
                    case.assertEqual(git(case.repository, "rev-parse", "HEAD").stdout.strip(), before_head)
                    case.assertEqual(
                        git(case.repository, "rev-parse", f"refs/heads/{branch}").stdout.strip(), before_ref
                    )
                    case.assertEqual(journal_path.read_bytes(), before_journal)
                    case.assertEqual(
                        json.loads(journal_path.read_bytes().decode("utf-8")), before_identity
                    )
                    case.assertEqual(store.repository_id, before_repository_id)
                finally:
                    case.doCleanups()

    def test_every_restoration_journal_boundary_resumes_exactly(self) -> None:
        phases = (
            "archiving",
            "switching-base",
            "restoring-origin-url",
            "restoring-origin-pushurl",
            "restoring-upstream-url",
            "restoring-upstream-pushurl",
            "restored",
        )
        fixed_now = lambda: __import__("datetime").datetime(
            2026,
            7,
            31,
            12,
            34,
            56,
            tzinfo=__import__("datetime").timezone.utc,
        )
        for phase in phases:
            with self.subTest(phase=phase):
                case = P02RealRepositoryTests(
                    "test_prepare_creates_exact_bares_patch_and_local_topology"
                )
                case.setUp()
                try:
                    store, _ = case._prepare()
                    git(case.repository, "add", "workshop_queue/cli.py", "tests/test_cli.py")
                    git(case.repository, "commit", "-m", "feat(queue): include unresolved tickets")
                    real_write = exercise_module._write
                    tripped = False

                    def crash_once(locked, record, next_phase, **changes):
                        nonlocal tripped
                        if not tripped and next_phase == phase:
                            tripped = True
                            raise ExerciseStateError("transition-incomplete")
                        return real_write(locked, record, next_phase, **changes)

                    with patch(
                        "academy_engine.exercise_state.sysconfig.get_path",
                        return_value=str(case.data_root),
                    ), patch(
                        "academy_engine.exercise_state._write",
                        side_effect=crash_once,
                    ):
                        with case.assertRaises(ExerciseStateError):
                            restore_p02(
                                case.repository,
                                store,
                                transition_to="reset",
                                now=fixed_now,
                            )
                    self.assertTrue(tripped)
                    with patch(
                        "academy_engine.exercise_state.sysconfig.get_path",
                        return_value=str(case.data_root),
                    ):
                        restore_p02(
                            case.repository,
                            store,
                            transition_to="reset",
                            now=fixed_now,
                        )
                    with store.locked() as locked:
                        self.assertEqual(locked.read_record("p02", 1)["phase"], "restored")
                finally:
                    case.doCleanups()


    def test_public_state_query_translates_external_state_failures(self) -> None:
        class FailingStore:
            @contextmanager
            def locked(self):
                raise ExternalStateError("unsafe-state-path")
                yield

        with self.assertRaises(ExerciseStateError) as raised:
            has_active_p02(self.repository, FailingStore())

        self.assertEqual(raised.exception.code, "invalid-exercise-state")
        self.assertNotIn(str(self.state_root), str(raised.exception))

    def test_checkpoint_accepts_only_the_exact_origin_pushed_range_and_receipt_commit(self) -> None:
        store, prepared = self._prepare()
        git(self.repository, "add", "workshop_queue/cli.py", "tests/test_cli.py")
        git(self.repository, "commit", "-m", "feat(queue): include unresolved tickets")
        work_head = git(self.repository, "rev-parse", "HEAD").stdout.strip()
        pushed = git(
            self.repository,
            "push",
            "origin",
            f"HEAD:refs/heads/{prepared.branch}",
            check=False,
        )
        self.assertEqual(pushed.returncode, 0, pushed.stderr)
        with store.locked() as locked:
            record = locked.read_record("p02", 1)
        receipt = {
            "schema_version": 1,
            "mode": "offline-local",
            "lab_id": "P02-commit-review-pr",
            "attempt": 1,
            "branch": prepared.branch,
            "prepared_commit": prepared.commit_sha,
            "work_head": work_head,
            "pushed_tip": work_head,
            "commits": [work_head],
            "review": {"status": "cleared"},
            "repositories": {
                "origin": {"repository_id": prepared.origin_repository_id, "role": "learner"},
                "upstream": {"repository_id": prepared.upstream_repository_id, "role": "official"},
            },
            "pr_reference": f"local-pr:{work_head[:12]}",
        }
        receipt_path = self.repository / ".codearbiter/reports/academy/P02-pr-receipt.json"
        receipt_path.parent.mkdir(parents=True)
        receipt_path.write_text(json.dumps(receipt, sort_keys=True) + "\n", encoding="utf-8")
        git(self.repository, "add", receipt_path.relative_to(self.repository).as_posix())
        git(self.repository, "commit", "-m", "docs(academy): record P02 receipt")
        receipt_head = git(self.repository, "rev-parse", "HEAD").stdout.strip()
        identity = P02AttemptIdentity(1, prepared.branch, prepared.commit_sha, receipt_head)

        with patch("academy_engine.exercise_state.sysconfig.get_path", return_value=str(self.data_root)):
            self.assertTrue(validate_p02_checkpoint(self.repository, store, identity, receipt))
            forged = dict(receipt)
            forged["pushed_tip"] = prepared.commit_sha
            self.assertFalse(validate_p02_checkpoint(self.repository, store, identity, forged))
            receipt_path.write_text("{}\n", encoding="utf-8")
            git(self.repository, "add", receipt_path.relative_to(self.repository).as_posix())
            git(self.repository, "commit", "--amend", "--no-edit")
            mismatched_identity = P02AttemptIdentity(
                1,
                prepared.branch,
                prepared.commit_sha,
                git(self.repository, "rev-parse", "HEAD").stdout.strip(),
            )
            self.assertFalse(
                validate_p02_checkpoint(
                    self.repository, store, mismatched_identity, receipt
                )
            )

    def test_checkpoint_rejects_an_executable_receipt_tree_entry(self) -> None:
        completed = self._complete_checkpoint_attempt(split=True)
        receipt_path = completed["receipt_path"].relative_to(self.repository).as_posix()
        git(self.repository, "update-index", "--chmod=+x", "--", receipt_path)
        git(self.repository, "commit", "--amend", "--no-edit")
        receipt_head = git(self.repository, "rev-parse", "HEAD").stdout.strip()
        identity = P02AttemptIdentity(
            completed["prepared"].attempt,
            completed["prepared"].branch,
            completed["prepared"].commit_sha,
            receipt_head,
        )

        entry = git(self.repository, "ls-tree", receipt_head, "--", receipt_path).stdout
        self.assertRegex(entry, rf"^100755 blob [0-9a-f]+\t{re.escape(receipt_path)}\n$")
        with patch(
            "academy_engine.exercise_state.sysconfig.get_path",
            return_value=str(self.data_root),
        ):
            self.assertFalse(
                validate_p02_checkpoint(
                    self.repository,
                    completed["store"],
                    identity,
                    completed["receipt"],
                )
            )

    def test_checkpoint_rejects_a_symlink_mode_receipt_tree_entry(self) -> None:
        completed = self._complete_checkpoint_attempt(split=True)
        receipt_path = completed["receipt_path"].relative_to(self.repository).as_posix()
        receipt_blob = git(
            self.repository, "rev-parse", f"HEAD:{receipt_path}"
        ).stdout.strip()
        git(
            self.repository,
            "update-index",
            "--add",
            "--cacheinfo",
            f"120000,{receipt_blob},{receipt_path}",
        )
        git(self.repository, "commit", "--amend", "--no-edit")
        receipt_head = git(self.repository, "rev-parse", "HEAD").stdout.strip()
        identity = P02AttemptIdentity(
            completed["prepared"].attempt,
            completed["prepared"].branch,
            completed["prepared"].commit_sha,
            receipt_head,
        )

        entry = git(self.repository, "ls-tree", receipt_head, "--", receipt_path).stdout
        self.assertRegex(entry, rf"^120000 blob [0-9a-f]+\t{re.escape(receipt_path)}\n$")
        with patch(
            "academy_engine.exercise_state.sysconfig.get_path",
            return_value=str(self.data_root),
        ):
            self.assertFalse(
                validate_p02_checkpoint(
                    self.repository,
                    completed["store"],
                    identity,
                    completed["receipt"],
                )
            )

    def test_checkpoint_real_repository_acceptance_and_negative_matrix(self) -> None:
        completed = self._complete_checkpoint_attempt(split=True)
        store = completed["store"]
        prepared = completed["prepared"]
        canonical_receipt = completed["receipt"]
        canonical_receipt_head = completed["receipt_head"]
        canonical_work = completed["work_head"]
        canonical_commits = completed["commits"]
        branch_ref = f"refs/heads/{prepared.branch}"
        origin = self._origin_directory(store)
        with store.locked() as locked:
            record = locked.read_record("p02", 1)
            upstream, _ = locked.owned_repository_directory(
                "p02", 1, record["upstream_repository"]["repository_id"]
            )

        self.enterContext(
            patch(
                "academy_engine.exercise_state.sysconfig.get_path",
                return_value=str(self.data_root),
            )
        )
        self.assertTrue(
            validate_p02_checkpoint(
                self.repository,
                store,
                completed["identity"],
                canonical_receipt,
            )
        )

        def current_identity() -> P02AttemptIdentity:
            return P02AttemptIdentity(
                prepared.attempt,
                prepared.branch,
                prepared.commit_sha,
                git(self.repository, "rev-parse", "HEAD").stdout.strip(),
            )

        receipt_cases: list[tuple[str, dict[str, object], bool]] = []
        reversed_range = json.loads(json.dumps(canonical_receipt))
        reversed_range["commits"] = list(reversed(canonical_commits))
        receipt_cases.append(("wrong-range-reversed", reversed_range, False))
        omitted_range = json.loads(json.dumps(canonical_receipt))
        omitted_range["commits"] = [canonical_commits[-1]]
        receipt_cases.append(("wrong-range-omitted", omitted_range, False))
        wrong_origin_id = json.loads(json.dumps(canonical_receipt))
        wrong_origin_id["repositories"]["origin"]["repository_id"] = "0" * 64
        receipt_cases.append(("wrong-origin-id", wrong_origin_id, False))
        wrong_upstream_id = json.loads(json.dumps(canonical_receipt))
        wrong_upstream_id["repositories"]["upstream"]["repository_id"] = "f" * 64
        receipt_cases.append(("wrong-upstream-id", wrong_upstream_id, False))
        wrong_roles = json.loads(json.dumps(canonical_receipt))
        wrong_roles["repositories"]["origin"]["role"] = "official"
        wrong_roles["repositories"]["upstream"]["role"] = "learner"
        receipt_cases.append(("wrong-roles", wrong_roles, False))
        wrong_work = json.loads(json.dumps(canonical_receipt))
        wrong_work["work_head"] = prepared.commit_sha
        receipt_cases.append(("wrong-work-tip", wrong_work, False))
        wrong_pushed = json.loads(json.dumps(canonical_receipt))
        wrong_pushed["pushed_tip"] = prepared.commit_sha
        receipt_cases.append(("wrong-pushed-tip", wrong_pushed, False))
        wrong_status = json.loads(json.dumps(canonical_receipt))
        wrong_status["review"]["status"] = "pending"
        receipt_cases.append(("wrong-review-status", wrong_status, True))
        wrong_reference = json.loads(json.dumps(canonical_receipt))
        wrong_reference["pr_reference"] = "local-pr:" + "0" * 12
        receipt_cases.append(("wrong-reference", wrong_reference, False))
        copied = json.loads(json.dumps(canonical_receipt))
        copied["attempt"] = 2
        copied["branch"] = "academy/P02-commit-review-pr/2"
        receipt_cases.append(("copied-attempt", copied, False))
        stale = json.loads(json.dumps(canonical_receipt))
        stale["work_head"] = canonical_commits[0]
        stale["pushed_tip"] = canonical_commits[0]
        stale["commits"] = [canonical_commits[0]]
        stale["pr_reference"] = f"local-pr:{canonical_commits[0][:12]}"
        receipt_cases.append(("stale-receipt", stale, False))
        for label, key, value in (
            ("url-injection", "url", "file:///private/path"),
            ("path-injection", "path", "C:/private/path"),
            ("hosted-injection", "hosted_check", "success"),
        ):
            injected = json.loads(json.dumps(canonical_receipt))
            injected[key] = value
            receipt_cases.append((label, injected, True))
        github_mode = json.loads(json.dumps(canonical_receipt))
        github_mode["mode"] = "github"
        receipt_cases.append(("hosted-mode", github_mode, True))

        for label, candidate, committed_parse_only in receipt_cases:
            with self.subTest(boundary="receipt", case=label):
                git(self.repository, "reset", "--hard", canonical_work)
                self._commit_receipt(candidate)
                argument = canonical_receipt if committed_parse_only else candidate
                with patch(
                    "academy_engine.exercise_state.sysconfig.get_path",
                    return_value=str(self.data_root),
                ):
                    self.assertFalse(
                        validate_p02_checkpoint(
                            self.repository,
                            store,
                            current_identity(),
                            argument,
                        )
                    )
                git(self.repository, "reset", "--hard", canonical_receipt_head)

        with self.subTest(boundary="committed-receipt", case="extra-receipt-path"):
            git(self.repository, "reset", "--hard", canonical_work)
            self._commit_receipt(
                canonical_receipt,
                extra_path=".codearbiter/reports/academy/unexpected.txt",
            )
            self.assertFalse(
                validate_p02_checkpoint(
                    self.repository, store, current_identity(), canonical_receipt
                )
            )
            git(self.repository, "reset", "--hard", canonical_receipt_head)

        with self.subTest(boundary="graph", case="extra-commit-before-receipt"):
            git(self.repository, "reset", "--hard", canonical_work)
            git(self.repository, "commit", "--allow-empty", "-m", "unexpected extra commit")
            self._commit_receipt(canonical_receipt)
            self.assertFalse(
                validate_p02_checkpoint(
                    self.repository, store, current_identity(), canonical_receipt
                )
            )
            git(self.repository, "reset", "--hard", canonical_receipt_head)

        with self.subTest(boundary="graph", case="wrong-receipt-parent"):
            git(self.repository, "reset", "--hard", prepared.commit_sha)
            self._commit_receipt(canonical_receipt)
            self.assertFalse(
                validate_p02_checkpoint(
                    self.repository, store, current_identity(), canonical_receipt
                )
            )
            git(self.repository, "reset", "--hard", canonical_receipt_head)

        origin_backup = self.repository.parent / "canonical-origin-backup"
        shutil.copytree(origin, origin_backup)

        def restore_origin_fixture() -> None:
            def remove_readonly(function, path, _error):
                os.chmod(path, stat.S_IWRITE)
                function(path)

            shutil.rmtree(origin, onerror=remove_readonly)
            shutil.copytree(origin_backup, origin)

        for kind in ("untouched", "partial", "wrong-patch"):
            with self.subTest(boundary="patch-graph", case=kind):
                restore_origin_fixture()
                git(self.repository, "reset", "--hard", prepared.commit_sha)
                if kind == "untouched":
                    git(self.repository, "commit", "--allow-empty", "-m", "untouched")
                elif kind == "partial":
                    git(self.repository, "checkout", canonical_work, "--", "tests/test_cli.py")
                    git(self.repository, "commit", "-m", "partial patch")
                else:
                    (self.repository / "tests/test_cli.py").write_text(
                        "wrong patch\n", encoding="utf-8"
                    )
                    git(self.repository, "add", "--", "tests/test_cli.py")
                    git(self.repository, "commit", "-m", "wrong patch")
                candidate_work = git(self.repository, "rev-parse", "HEAD").stdout.strip()
                candidate_commits = git(
                    self.repository,
                    "rev-list",
                    "--reverse",
                    f"{prepared.commit_sha}..{candidate_work}",
                ).stdout.splitlines()
                candidate_receipt = self._receipt_for(
                    prepared, candidate_work, candidate_commits
                )
                git(
                    origin.parent,
                    f"--git-dir={origin}",
                    "fetch",
                    "--no-tags",
                    str(self.repository),
                    f"+{candidate_work}:{branch_ref}",
                )
                self._commit_receipt(candidate_receipt)
                self.assertFalse(
                    validate_p02_checkpoint(
                        self.repository,
                        store,
                        current_identity(),
                        candidate_receipt,
                    )
                )
                git(self.repository, "reset", "--hard", canonical_receipt_head)
                git(
                    origin.parent,
                    f"--git-dir={origin}",
                    "update-ref",
                    branch_ref,
                    canonical_work,
                )
        restore_origin_fixture()

        with self.subTest(boundary="origin-ref", case="wrong-origin-tip"):
            git(
                origin.parent,
                f"--git-dir={origin}",
                "update-ref",
                branch_ref,
                prepared.commit_sha,
            )
            self.assertFalse(
                validate_p02_checkpoint(
                    self.repository,
                    store,
                    completed["identity"],
                    canonical_receipt,
                )
            )
            git(
                origin.parent,
                f"--git-dir={origin}",
                "update-ref",
                branch_ref,
                canonical_work,
            )

        with self.subTest(boundary="upstream-ref", case="unexpected-attempt-ref"):
            git(
                upstream.parent,
                f"--git-dir={upstream}",
                "update-ref",
                branch_ref,
                prepared.base_sha,
            )
            self.assertFalse(
                validate_p02_checkpoint(
                    self.repository,
                    store,
                    completed["identity"],
                    canonical_receipt,
                )
            )
            git(upstream.parent, f"--git-dir={upstream}", "update-ref", "-d", branch_ref)

        with self.subTest(boundary="upstream-state", case="recorded-digest-tamper"):
            with store.locked() as locked:
                record = locked.read_record("p02", 1)
                original_upstream = json.loads(json.dumps(record["upstream_repository"]))
                record["upstream_repository"]["reachable_objects_sha256"] = "0" * 64
                record["generation"] += 1
                locked.write_record(
                    "p02", 1, record, expected_generation=record["generation"] - 1
                )
            self.assertFalse(
                validate_p02_checkpoint(
                    self.repository,
                    store,
                    completed["identity"],
                    canonical_receipt,
                )
            )
            with store.locked() as locked:
                record = locked.read_record("p02", 1)
                record["upstream_repository"] = original_upstream
                record["generation"] += 1
                locked.write_record(
                    "p02", 1, record, expected_generation=record["generation"] - 1
                )

        with self.subTest(boundary="locator", case="noncanonical-extra-attempt"):
            extra = store._epoch_dir / "p02/01"
            extra.mkdir()
            self.assertFalse(
                validate_p02_checkpoint(
                    self.repository,
                    store,
                    completed["identity"],
                    canonical_receipt,
                )
            )
            extra.rmdir()

        self.assertEqual(
            git(self.repository, "rev-parse", "HEAD").stdout.strip(),
            canonical_receipt_head,
            "the negative matrix did not restore the canonical learner HEAD",
        )
        with store.locked() as locked:
            final_record = locked.read_record("p02", 1)
        self.assertEqual(final_record["phase"], "active")
        self.assertEqual(final_record["upstream_repository"], original_upstream)
        final_live = verify_p02(self.repository, store, completed["identity"])
        self.assertTrue(
            final_live.upstream_unchanged,
            "the negative matrix did not restore the canonical upstream snapshot",
        )
        final_data = _parse_p02_receipt(
            canonical_receipt, object_format=_object_format(self.repository)
        )
        self.assertEqual(final_live.origin_tip, canonical_work)
        final_commits = git(
            self.repository,
            "rev-list",
            "--reverse",
            f"{prepared.commit_sha}..{canonical_work}",
        ).stdout.splitlines()
        self.assertEqual(final_commits, canonical_commits)
        self.assertTrue(
            _exact_patch_result(self.repository, prepared.commit_sha, canonical_work),
            "the negative matrix did not restore the canonical patch graph",
        )
        self.assertEqual(
            git(self.repository, "rev-parse", f"{canonical_receipt_head}^").stdout.strip(),
            canonical_work,
        )
        receipt_path = ".codearbiter/reports/academy/P02-pr-receipt.json"
        self.assertEqual(
            git(
                self.repository,
                "diff-tree",
                "--no-commit-id",
                "--name-only",
                "-r",
                canonical_receipt_head,
            ).stdout.splitlines(),
            [receipt_path],
        )
        committed_receipt = _parse_p02_receipt_bytes(
            git(
                self.repository, "show", f"{canonical_receipt_head}:{receipt_path}"
            ).stdout.encode("utf-8", "surrogateescape"),
            object_format=_object_format(self.repository),
        )
        self.assertEqual(committed_receipt, final_data)
        self.assertTrue(
            validate_p02_checkpoint(
                self.repository,
                store,
                completed["identity"],
                canonical_receipt,
            )
        )

    def test_verify_rejects_a_later_captured_record_after_the_selected_active_attempt(self) -> None:
        store, _, identity = self._verifiable_attempt()
        self._write_later_attempt(store, kind="captured")

        with self.assertRaisesRegex(ExerciseStateError, "state|evidence"):
            verify_p02(self.repository, store, identity)

    def test_verify_rejects_a_corrupt_later_record_after_the_selected_active_attempt(self) -> None:
        store, _, identity = self._verifiable_attempt()
        self._write_later_attempt(store, kind="corrupt")

        with self.assertRaisesRegex(ExerciseStateError, "state|evidence"):
            verify_p02(self.repository, store, identity)

    def test_verify_rejects_a_second_active_record_after_the_selected_attempt(self) -> None:
        store, _, identity = self._verifiable_attempt()
        self._write_later_attempt(store, kind="active")

        with self.assertRaisesRegex(ExerciseStateError, "state|evidence"):
            verify_p02(self.repository, store, identity)

    def test_upstream_missing_ref_check_routes_through_validated_bare_boundary(self) -> None:
        store, _, identity = self._verifiable_attempt()
        with store.locked() as locked:
            record = locked.read_record("p02", 1)
            upstream, _ = locked.owned_repository_directory(
                "p02",
                1,
                record["upstream_repository"]["repository_id"],
            )
            snapshot = record["upstream_repository"]
        git(
            upstream.parent,
            f"--git-dir={upstream}",
            "config",
            "extensions.partialclone",
            "forbidden",
        )
        real_bare = exercise_module._bare
        observed: list[tuple[Path, tuple[str, ...]]] = []

        def bare_spy(directory, args, **kwargs):
            observed.append((directory, tuple(args)))
            return real_bare(directory, args, **kwargs)

        with patch(
            "academy_engine.exercise_state._bare", side_effect=bare_spy
        ), patch(
            "academy_engine.exercise_state._repository_snapshot",
            return_value=snapshot,
        ):
            with self.assertRaises(ExerciseStateError) as raised:
                verify_p02(self.repository, store, identity)

        self.assertTrue(
            any(
                directory == upstream and args[:3] == ("show-ref", "--verify", "--quiet")
                for directory, args in observed
            )
        )
        self.assertNotIn(str(upstream), str(raised.exception))

    def test_activation_retry_preserves_a_novel_mixed_topology_without_further_mutation(self) -> None:
        store, _ = self._prepare()
        with store.locked() as locked:
            record = locked.read_record("p02", 1)
            record["generation"] += 1
            record["phase"] = "activating-origin-pushurl"
            locked.write_record(
                "p02", 1, record, expected_generation=record["generation"] - 1
            )
        git(self.repository, "config", "--unset-all", "remote.origin.pushurl", check=False)
        git(
            self.repository,
            "config",
            "--replace-all",
            "remote.upstream.url",
            "https://github.com/other/arbiter-academy.git",
        )
        before = git(
            self.repository,
            "config",
            "--null",
            "--get-all",
            "remote.origin.pushurl",
            check=False,
        )

        with patch("academy_engine.exercise_state.sysconfig.get_path", return_value=str(self.data_root)):
            lab = Catalog.load(self.installed / "catalog.json").lab("P02-commit-review-pr")
            with self.assertRaisesRegex(ExerciseStateError, "incomplete"):
                prepare_p02(self.repository, store, lab)

        after = git(
            self.repository,
            "config",
            "--null",
            "--get-all",
            "remote.origin.pushurl",
            check=False,
        )
        self.assertEqual((after.returncode, after.stdout), (before.returncode, before.stdout))
        with store.locked() as locked:
            self.assertEqual(locked.read_record("p02", 1)["phase"], "activating-origin-pushurl")

    def test_restoration_retry_preserves_a_novel_mixed_topology_without_further_mutation(self) -> None:
        store, prepared = self._prepare()
        git(self.repository, "add", "workshop_queue/cli.py", "tests/test_cli.py")
        git(self.repository, "commit", "-m", "feat(queue): include unresolved tickets")
        target = git(self.repository, "rev-parse", "HEAD").stdout.strip()
        archive = "refs/heads/academy/archive/P02-commit-review-pr/1/20260731T123456Z"
        git(self.repository, "update-ref", archive, target)
        git(self.repository, "switch", "main")
        with store.locked() as locked:
            record = locked.read_record("p02", 1)
            local_origin_push = git(
                self.repository, "config", "--null", "--get-all", "remote.origin.pushurl"
            ).stdout
            original = record["original_topology"]["config"]
            record["generation"] += 1
            record["phase"] = "restoring-origin-pushurl"
            record["archive_ref"] = archive
            record["archive_target"] = target
            record["transition_target"] = "reset"
            locked.write_record(
                "p02", 1, record, expected_generation=record["generation"] - 1
            )
        git(
            self.repository,
            "config",
            "--replace-all",
            "remote.origin.url",
            original["remote.origin.url"][0],
        )
        git(
            self.repository,
            "config",
            "--replace-all",
            "remote.upstream.url",
            "https://github.com/other/arbiter-academy.git",
        )

        with patch(
            "academy_engine.exercise_state.sysconfig.get_path",
            return_value=str(self.data_root),
        ):
            with self.assertRaisesRegex(ExerciseStateError, "incomplete"):
                restore_p02(self.repository, store, transition_to="reset")

        after = git(
            self.repository, "config", "--null", "--get-all", "remote.origin.pushurl"
        ).stdout
        self.assertEqual(after, local_origin_push)
        with store.locked() as locked:
            self.assertEqual(locked.read_record("p02", 1)["phase"], "restoring-origin-pushurl")


class P02Sha256RepositoryTests(unittest.TestCase):
    def test_sha256_end_to_end_checkpoint_tamper_and_restoration(self) -> None:
        case = P02RealRepositoryTests(
            "test_prepare_creates_exact_bares_patch_and_local_topology"
        )
        case.OBJECT_FORMAT = "sha256"
        case.setUp()
        self.enterContext(
            patch(
                "academy_engine.exercise_state.sysconfig.get_path",
                return_value=str(case.data_root),
            )
        )
        try:
            completed = case._complete_checkpoint_attempt(split=True)
            store = completed["store"]
            prepared = completed["prepared"]
            self.assertEqual(len(prepared.base_sha), 64)
            self.assertEqual(len(prepared.commit_sha), 64)
            self.assertTrue(all(len(oid) == 64 for oid in completed["commits"]))
            self.assertEqual(len(completed["work_head"]), 64)
            self.assertEqual(len(completed["receipt_head"]), 64)
            self.assertRegex(prepared.origin_repository_id, r"^[0-9a-f]{64}$")
            self.assertRegex(prepared.upstream_repository_id, r"^[0-9a-f]{64}$")
            self.assertTrue(
                validate_p02_checkpoint(
                    case.repository,
                    store,
                    completed["identity"],
                    completed["receipt"],
                )
            )
            origin = case._origin_directory(store)
            branch_ref = f"refs/heads/{prepared.branch}"
            git(
                origin.parent,
                f"--git-dir={origin}",
                "update-ref",
                branch_ref,
                prepared.base_sha,
            )
            self.assertFalse(
                validate_p02_checkpoint(
                    case.repository,
                    store,
                    completed["identity"],
                    completed["receipt"],
                )
            )
            git(
                origin.parent,
                f"--git-dir={origin}",
                "update-ref",
                branch_ref,
                completed["work_head"],
            )
            self.assertTrue(
                validate_p02_checkpoint(
                    case.repository,
                    store,
                    completed["identity"],
                    completed["receipt"],
                )
            )
            fixed_now = lambda: __import__("datetime").datetime(
                2026,
                7,
                31,
                12,
                34,
                56,
                tzinfo=__import__("datetime").timezone.utc,
            )
            restore_p02(
                case.repository,
                store,
                transition_to="reset",
                now=fixed_now,
            )
            with store.locked() as locked:
                self.assertEqual(locked.read_record("p02", 1)["phase"], "restored")
            self.assertEqual(
                git(case.repository, "branch", "--show-current").stdout.strip(),
                "main",
            )
            self.assertEqual(
                git(case.repository, "rev-parse", "HEAD").stdout.strip(),
                prepared.base_sha,
            )
            self.assertTrue(
                git(case.repository, "remote", "get-url", "origin").stdout.strip().startswith(
                    "https://github.com/"
                )
            )
            self.assertTrue(
                git(case.repository, "remote", "get-url", "upstream").stdout.strip().startswith(
                    "https://github.com/"
                )
            )
            self.assertEqual(
                git(
                    case.repository,
                    "remote",
                    "get-url",
                    "--push",
                    "upstream",
                ).stdout.strip(),
                "DISABLED",
            )
            self.assertNotIn(
                "file:",
                git(case.repository, "remote", "-v").stdout,
            )
        finally:
            case.doCleanups()


if __name__ == "__main__":
    unittest.main()
