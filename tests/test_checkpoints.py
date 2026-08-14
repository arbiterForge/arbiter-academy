import json
import hashlib
import errno
import os
import shutil
import tempfile
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

from academy_engine.checkpoints import (
    CheckpointError,
    LabContract,
    Predicate,
    _Attempt,
    _SemanticContext,
    _git_blob,
    _json,
    _raw_digest,
    _p01_spec_and_plan,
    _p01_criterion,
    _p01_board_transition,
    _p01_exact_repair,
    _p01_fixture_models,
    _p01_prepared_defect,
    _p01_source_identity,
    _p05_finding_is_exact,
    _p05_red_regression_is_exact,
    _p07_native_conversation,
    _p07_report_history,
    _p07_sections,
    _p07_target_binding,
    _p07_target_object,
    _semantic,
    _validate_prepare,
    evaluate_checkpoint,
    load_checkpoint,
    load_contracts,
)
from academy_engine.exercise_state import P08AttemptIdentity
from academy_engine.p05_fixture import stage_p05_fixture
from tests._temporary import RetryingTemporaryDirectory
from tests.test_p07_threat_model import P07_INTENDED_REPORT, REPORT_PATH, TARGET_PATH

_P05_TEST_NAME = (
    "tests.test_cli.WorkshopQueueCliTests."
    "test_report_json_counts_blocked_ticket_as_unresolved"
)
_P05_PREPARED_TEST_NAME = (
    "tests.test_cli.WorkshopQueueCliTests."
    "test_p05_prepared_blocked_ticket_persists_before_summary_defect"
)
_P05_RED_METHOD = (
    "\n    def test_report_json_counts_blocked_ticket_as_unresolved(self) -> None:\n"
    "        tickets = json.loads(self.fixture.read_text(encoding=\"utf-8\"))\n"
    "        tickets[0][\"id\"] = \"RQ-105\"\n"
    "        self.fixture.write_text(json.dumps(tickets), encoding=\"utf-8\")\n"
    "        claim_result = self.run_cli(\"claim\", \"RQ-105\", \"--volunteer\", \"Sam\")\n"
    "        block_result = self.run_cli(\"block\", \"RQ-105\", \"--reason\", \"Venue access is awaiting facilities clearance\")\n"
    "        report = self.run_cli(\"report\", \"--format\", \"json\")\n"
    "        self.assertEqual(claim_result.returncode, 0, claim_result.stderr)\n"
    "        self.assertEqual(block_result.returncode, 0, block_result.stderr)\n"
    "        self.assertEqual(report.returncode, 0, report.stderr)\n"
    "        parsed = json.loads(report.stdout)\n"
    "        self.assertEqual(parsed[\"blocked\"], 1)\n"
    "        self.assertEqual(parsed[\"unresolved\"], 1)\n\n"
).encode("utf-8")
_P05_FINDING = (
    "# P05 Finding: blocked tickets omitted from unresolved summary\n\n"
    "Ticket `RQ-105` is blocked: `Venue access is awaiting facilities clearance`.\n"
    "Affected paths: `tests/test_cli.py`, `workshop_queue/cli.py`.\n"
).encode("utf-8")
_P05_ROLE_PATHS = (
    (
        ".codearbiter/checkpoints/2026-08-02.md",
        ".codearbiter/last-checkpoint",
        ".codearbiter/reports/academy/P05-finding.md",
    ),
    ("tests/test_cli.py",),
    ("workshop_queue/cli.py",),
    (".codearbiter/checkpoints/P05-academy.json",),
)


class CheckpointFixtureCleanupTests(unittest.TestCase):
    def test_real_git_checkpoint_fixtures_retry_transient_git_cleanup_races(self) -> None:
        """Catches transient Git pack-file teardown races escaping these fixtures."""
        fixtures = (
            (CheckpointTests, "test_p07_direct_target_object_rejects_wrong_blob_and_bytes"),
            (P03NativeEvidenceTests, "test_p03_accepts_the_equivalent_ordered_two_commit_history"),
            (P04NativeDependencyReviewTests, "test_accepts_real_reject_and_two_commit_acceptance_paths"),
        )
        for fixture, test_name in fixtures:
            with self.subTest(fixture=fixture.__name__):
                case = fixture(test_name)
                case.setUp()
                base_cleanup = tempfile.TemporaryDirectory.cleanup
                transient = OSError(errno.ENOTEMPTY, "directory not empty")
                try:
                    with mock.patch.object(
                        tempfile.TemporaryDirectory,
                        "cleanup",
                        side_effect=(transient, None),
                    ) as cleanup:
                        case.temp.cleanup()
                    self.assertEqual(cleanup.call_count, 2)
                finally:
                    base_cleanup(case.temp)

class CheckpointTests(unittest.TestCase):
    def setUp(self):
        self.temp = RetryingTemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "academy" / "checkpoints").mkdir(parents=True)
        (self.root / "academy" / "catalog.json").write_text('{"schema_version":1,"labs":[]}', encoding="utf-8")
        self.path = self.root / "academy" / "checkpoints" / "F01-fork-clone-doctor.json"
        self.write({"schema_version": 2, "id": "F01-fork-clone-doctor", "predicates": [{"id": "remote_and_doctor", "type": "lab_semantics", "profile": "remote_doctor", "artifact": ".codearbiter/reports/academy/F01-doctor.json"}]})

    def tearDown(self): self.temp.cleanup()

    def _p07_direct_repository(self) -> tuple[Path, str]:
        source = Path(__file__).resolve().parents[1]
        root = self.root / f"p07-direct-{len(tuple(self.root.glob('p07-direct-*')))}"
        target = root / TARGET_PATH
        target.parent.mkdir(parents=True)
        shutil.copyfile(source / TARGET_PATH, target)
        subprocess.run(["git", "init", "-b", "main"], cwd=root, check=True, capture_output=True, text=True)
        subprocess.run(["git", "config", "user.name", "P07 Direct"], cwd=root, check=True)
        subprocess.run(["git", "config", "user.email", "p07-direct@example.invalid"], cwd=root, check=True)
        subprocess.run(["git", "add", TARGET_PATH], cwd=root, check=True, capture_output=True, text=True)
        subprocess.run(["git", "commit", "-m", "prepared"], cwd=root, check=True, capture_output=True, text=True)
        return root, subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True
        ).stdout.strip()

    def test_p07_direct_target_object_rejects_wrong_blob_and_bytes(self) -> None:
        root, prepared = self._p07_direct_repository()
        self.assertIsNotNone(_p07_target_object(root, prepared, TARGET_PATH))
        target = root / TARGET_PATH
        target.write_bytes(target.read_bytes() + b"\n# changed target\n")
        subprocess.run(["git", "add", TARGET_PATH], cwd=root, check=True, capture_output=True, text=True)
        subprocess.run(["git", "commit", "-m", "wrong target"], cwd=root, check=True, capture_output=True, text=True)
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True
        ).stdout.strip()
        self.assertIsNone(_p07_target_object(root, head, TARGET_PATH))

    def test_p07_direct_parser_rejects_duplicate_academy_label(self) -> None:
        report = P07_INTENDED_REPORT.replace(
            b"The boundary must prove containment before a destination write.\n",
            b"The boundary must prove containment before a destination write.\nAcademy-Target-Path: academy_engine/paths.py\n",
        )
        sections = _p07_sections(report)
        self.assertIsNotNone(sections)
        self.assertFalse(_p07_native_conversation(sections or {}))

    def test_p07_direct_parser_rejects_crlf_and_missing_final_lf(self) -> None:
        self.assertIsNone(_p07_sections(P07_INTENDED_REPORT.replace(b"\n", b"\r\n")))
        self.assertIsNone(_p07_sections(P07_INTENDED_REPORT[:-1]))
        self.assertIsNone(
            _p07_sections(
                P07_INTENDED_REPORT.replace(b"destination write.", b"destination write.\x00", 1)
            )
        )

    def test_p07_direct_parser_rejects_stride_table_reordering(self) -> None:
        report = P07_INTENDED_REPORT.replace(b"| S | L | M |", b"| T | L | M |", 1)
        sections = _p07_sections(report)
        self.assertIsNotNone(sections)
        self.assertFalse(_p07_native_conversation(sections or {}))
        valid = _p07_sections(P07_INTENDED_REPORT)
        self.assertIsNotNone(valid)
        self.assertTrue(_p07_target_binding(valid or {}))

    def test_p07_direct_history_rejects_report_plus_target_cocommit(self) -> None:
        root, prepared = self._p07_direct_repository()
        report = root / REPORT_PATH
        report.parent.mkdir(parents=True)
        report.write_bytes(P07_INTENDED_REPORT)
        target = root / TARGET_PATH
        target.write_bytes(target.read_bytes() + b"\n# co-commit\n")
        subprocess.run(
            ["git", "-c", "core.autocrlf=false", "add", REPORT_PATH, TARGET_PATH],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(["git", "commit", "-m", "report plus target"], cwd=root, check=True, capture_output=True, text=True)
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True
        ).stdout.strip()
        attempt = _Attempt("academy/P07-threat-model/1", 1, prepared, prepared, head)
        self.assertIsNone(_p07_report_history(root, attempt, REPORT_PATH))

    def _p05_git(
        self,
        root: Path,
        *arguments: str,
        check: bool = True,
        environment: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *arguments],
            cwd=root,
            check=check,
            capture_output=True,
            text=True,
            env=environment,
        )

    def _p05_commit(
        self,
        root: Path,
        paths: tuple[str, ...],
        subject: str,
        *,
        name: str,
        email: str,
        timestamp: str,
    ) -> str:
        self._p05_git(root, "add", "--", *paths)
        environment = os.environ.copy()
        environment.update(
            {
                "GIT_AUTHOR_NAME": name,
                "GIT_AUTHOR_EMAIL": email,
                "GIT_AUTHOR_DATE": timestamp,
                "GIT_COMMITTER_NAME": name,
                "GIT_COMMITTER_EMAIL": email,
                "GIT_COMMITTER_DATE": timestamp,
            }
        )
        self._p05_git(root, "commit", "-m", subject, environment=environment)
        return self._p05_git(root, "rev-parse", "HEAD").stdout.strip()

    def _p05_prepared_repository(self, *, object_format: str = "sha1") -> tuple[Path, str, str]:
        source = Path(__file__).resolve().parents[1]
        root = self.root / "p05-prepared"
        root.mkdir()
        for relative in ("academy", "data", "workshop_queue", "tests", ".codearbiter"):
            shutil.copytree(
                source / relative,
                root / relative,
                ignore=shutil.ignore_patterns("__pycache__"),
            )
        shutil.copy2(source / "pyproject.toml", root / "pyproject.toml")
        for relative in (
            "workshop_queue/model.py",
            "workshop_queue/service.py",
            "workshop_queue/cli.py",
            "tests/test_cli.py",
        ):
            (root / relative).write_bytes(
                subprocess.run(
                    ["git", "show", f"b0dc9e5:{relative}"],
                    cwd=source,
                    check=True,
                    capture_output=True,
                ).stdout
            )
        p03_adr = root / ".codearbiter/decisions/0004-academy-lab.md"
        p03_adr.write_text(
            "---\nstatus: accepted\ndate: 2026-08-01\n"
            "title: Choose the Workshop Queue summary-format boundary\n"
            "decided-by: Academy Learner\nsupersedes: none\n---\n\n"
            "# ADR-0004 — Choose the Workshop Queue summary-format boundary\n",
            encoding="utf-8",
            newline="\n",
        )
        p03_log = root / ".codearbiter/decisions/decision-log.md"
        p03_log.write_text(
            p03_log.read_text(encoding="utf-8")
            + "\n## DECISION-0004 — ADR-0004 — Choose the Workshop Queue summary-format boundary\n\n"
            "**Date:** 2026-08-01\n**Status:** accepted\n**Supersedes:** none\n"
            "**Decided by:** Academy Learner\n**Decision category:** architecture\n"
            "**Artifact-section-hash:** n/a\n\n---\n",
            encoding="utf-8",
            newline="\n",
        )
        (root / "training_scenarios").mkdir()
        self._p05_git(root, "init", "-b", "main", f"--object-format={object_format}")
        base = self._p05_commit(
            root,
            (".codearbiter", "academy", "data", "pyproject.toml", "workshop_queue", "tests"),
            "base",
            name="P05 Prepared Fixture",
            email="p05-prepared@example.invalid",
            timestamp="2026-08-02T11:58:00+00:00",
        )
        self._p05_git(root, "switch", "-c", "academy/P05-checkpoint-remediation/1")
        staged = stage_p05_fixture(root, base=base)
        shutil.copyfile(
            root / "academy/scenarios/P05-checkpoint-remediation/files/scenario.json",
            root / "training_scenarios/P05-checkpoint-remediation.json",
        )
        prepared = self._p05_commit(
            root,
            ("training_scenarios/P05-checkpoint-remediation.json", *staged),
            "academy: prepare P05-checkpoint-remediation attempt 1",
            name="P05 Prepared Fixture",
            email="p05-prepared@example.invalid",
            timestamp="2026-08-02T11:59:00+00:00",
        )
        return root, base, prepared

    def test_p05_prepare_validation_accepts_the_seven_path_governed_fixture(self) -> None:
        root, base, prepared = self._p05_prepared_repository()
        attempt = _Attempt(
            "academy/P05-checkpoint-remediation/1",
            1,
            prepared,
            base,
            prepared,
        )
        contract = LabContract(
            "P05-checkpoint-remediation",
            "Remediate a checkpoint finding",
            "academy/tracks/practitioner/P05-checkpoint-remediation.md",
            "academy/checkpoints/P05-checkpoint-remediation.json",
            "training_scenarios/P05-checkpoint-remediation.json",
        )

        self.assertTrue(_validate_prepare(root, contract, attempt))

    def test_p05_checkpoint_accepts_an_otherwise_valid_sha256_history(self) -> None:
        prepared_root, _, prepared = self._p05_prepared_repository(object_format="sha256")
        history = self._p05_history(
            prepared_root,
            prepared,
            "sha256",
            name="P05 SHA-256 Fixture",
            email="p05-sha256@example.invalid",
            timestamps=tuple(f"2026-08-02T12:1{minute}:00+00:00" for minute in range(4)),
        )

        self.assertEqual(len(prepared), 64)
        self.assertTrue(self._p05_semantic(history))

    def _p05_mutated_red(self, raw: bytes, mutation: str | None) -> bytes:
        if mutation is None:
            return raw
        encoding_prefixes = {
            "unknown-encoding-cookie": b"# coding: unknown-p05-codec\n",
            "non-utf8-cookie": b"# coding: latin-1\n",
        }
        if mutation in encoding_prefixes:
            return encoding_prefixes[mutation] + raw
        replacements = {
            "run-cli": (
                b"    def run_cli(self, *arguments: str) -> subprocess.CompletedProcess[str]:\n"
                b"        return self.run_cli_for(self.fixture, *arguments)\n",
                b"    def run_cli(self, *arguments: str) -> subprocess.CompletedProcess[str]:\n"
                b"        marker = None\n"
                b"        return self.run_cli_for(self.fixture, *arguments)\n",
            ),
            "helper": (
                b"    def tearDown(self) -> None:\n"
                b"        self.temporary_directory.cleanup()\n",
                b"    def tearDown(self) -> None:\n"
                b"        marker = None\n"
                b"        self.temporary_directory.cleanup()\n",
            ),
            "other-test": (
                b"    def test_list_json_is_machine_readable(self) -> None:\n"
                b"        result = self.run_cli(\"list\", \"--format\", \"json\")\n",
                b"    def test_list_json_is_machine_readable(self) -> None:\n"
                b"        self.assertTrue(True)\n"
                b"        result = self.run_cli(\"list\", \"--format\", \"json\")\n",
            ),
            "skip-decorator": (
                b"    def test_report_json_counts_blocked_ticket_as_unresolved(self) -> None:\n",
                b"    @unittest.skip(\"disabled regression\")\n"
                b"    def test_report_json_counts_blocked_ticket_as_unresolved(self) -> None:\n",
            ),
            "skip-call": (
                b"    def test_report_json_counts_blocked_ticket_as_unresolved(self) -> None:\n",
                b"    def test_report_json_counts_blocked_ticket_as_unresolved(self) -> None:\n"
                b"        self.skipTest(\"disabled regression\")\n",
            ),
            "early-return": (
                b"    def test_report_json_counts_blocked_ticket_as_unresolved(self) -> None:\n",
                b"    def test_report_json_counts_blocked_ticket_as_unresolved(self) -> None:\n"
                b"        return\n",
            ),
            "report-before-state": (
                b"        claim_result = self.run_cli(\"claim\", \"RQ-105\", \"--volunteer\", \"Sam\")\n"
                b"        block_result = self.run_cli(\"block\", \"RQ-105\", \"--reason\", \"Venue access is awaiting facilities clearance\")\n"
                b"        report = self.run_cli(\"report\", \"--format\", \"json\")\n",
                b"        report = self.run_cli(\"report\", \"--format\", \"json\")\n"
                b"        claim_result = self.run_cli(\"claim\", \"RQ-105\", \"--volunteer\", \"Sam\")\n"
                b"        block_result = self.run_cli(\"block\", \"RQ-105\", \"--reason\", \"Venue access is awaiting facilities clearance\")\n",
            ),
            "extra-required-arg": (
                b"    def test_report_json_counts_blocked_ticket_as_unresolved(self) -> None:\n",
                b"    def test_report_json_counts_blocked_ticket_as_unresolved(self, required) -> None:\n",
            ),
            "no-self": (
                b"    def test_report_json_counts_blocked_ticket_as_unresolved(self) -> None:\n",
                b"    def test_report_json_counts_blocked_ticket_as_unresolved() -> None:\n",
            ),
            "fixture-load-keyword": (
                b"    def test_report_json_counts_blocked_ticket_as_unresolved(self) -> None:\n"
                b"        tickets = json.loads(self.fixture.read_text(encoding=\"utf-8\"))\n",
                b"    def test_report_json_counts_blocked_ticket_as_unresolved(self) -> None:\n"
                b"        tickets = json.loads(self.fixture.read_text(encoding=\"utf-8\"), object_hook=missing_hook)\n",
            ),
            "rebind-self": (
                b"        parsed = json.loads(report.stdout)\n"
                b"        self.assertEqual(parsed[\"blocked\"], 1)\n"
                b"        self.assertEqual(parsed[\"unresolved\"], 1)\n",
                b"        self = json.loads(report.stdout)\n"
                b"        self.assertEqual(self[\"blocked\"], 1)\n"
                b"        self.assertEqual(self[\"unresolved\"], 1)\n",
            ),
        }
        old, new = replacements[mutation]
        self.assertEqual(raw.count(old), 1, mutation)
        return raw.replace(old, new)

    def _p05_history(
        self,
        prepared_root: Path,
        prepared: str,
        label: str,
        *,
        name: str,
        email: str,
        timestamps: tuple[str, str, str, str],
        red_mutation: str | None = None,
    ) -> dict[str, object]:
        root = self.root / f"p05-{label}"
        subprocess.run(
            ["git", "clone", "--no-hardlinks", str(prepared_root), str(root)],
            cwd=self.root,
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual(self._p05_git(root, "rev-parse", "HEAD").stdout.strip(), prepared)

        finding_path = root / ".codearbiter/reports/academy/P05-finding.md"
        finding_path.parent.mkdir(parents=True)
        finding_path.write_bytes(_P05_FINDING)
        checkpoint_path = root / ".codearbiter/checkpoints/2026-08-02.md"
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        checkpoint_path.write_text(
            "# CodeArbiter Checkpoint - 2026-08-02\n\n"
            "ACADEMY-P05-BLOCKED-UNRESOLVED: blocked tickets omitted from unresolved summary.\n",
            encoding="utf-8",
        )
        (root / ".codearbiter/last-checkpoint").write_text("0\n", encoding="utf-8")
        finding = self._p05_commit(
            root,
            _P05_ROLE_PATHS[0],
            "record P05 finding",
            name=name,
            email=email,
            timestamp=timestamps[0],
        )

        test_path = root / "tests/test_cli.py"
        prepared_test = _git_blob(root, prepared, "tests/test_cli.py")
        self.assertIsNotNone(prepared_test)
        assert prepared_test is not None
        marker = b'\n\nif __name__ == "__main__":'
        self.assertEqual(prepared_test.count(marker), 1)
        red_test = prepared_test.replace(marker, _P05_RED_METHOD + b'if __name__ == "__main__":')
        test_path.write_bytes(self._p05_mutated_red(red_test, red_mutation))
        red = self._p05_commit(
            root,
            _P05_ROLE_PATHS[1],
            "add P05 regression",
            name=name,
            email=email,
            timestamp=timestamps[1],
        )

        cli_path = root / "workshop_queue/cli.py"
        defect = b"sum(ticket.status in {TicketStatus.OPEN, TicketStatus.CLAIMED} for ticket in tickets)"
        correct = b"sum(ticket.status is not TicketStatus.COMPLETED for ticket in tickets)"
        cli = _git_blob(root, red, "workshop_queue/cli.py")
        self.assertIsNotNone(cli)
        assert cli is not None
        self.assertEqual(cli.count(defect), 1)
        cli_path.write_bytes(cli.replace(defect, correct))
        remediation = self._p05_commit(
            root,
            _P05_ROLE_PATHS[2],
            "repair P05 unresolved summary",
            name=name,
            email=email,
            timestamp=timestamps[2],
        )

        receipt_data = {
            "affected_paths": ["tests/test_cli.py", "workshop_queue/cli.py"],
            "finding_commit": finding,
            "finding_id": "ACADEMY-P05-BLOCKED-UNRESOLVED",
            "red_commit": red,
            "remediation_commit": remediation,
            "schema_version": 2,
            "status": "remediated",
        }
        receipt = root / ".codearbiter/checkpoints/P05-academy.json"
        receipt.parent.mkdir(parents=True, exist_ok=True)
        receipt.write_bytes(
            json.dumps(receipt_data, sort_keys=True, separators=(",", ":")).encode("ascii")
            + b"\n"
        )
        head = self._p05_commit(
            root,
            _P05_ROLE_PATHS[3],
            "record P05 receipt",
            name=name,
            email=email,
            timestamp=timestamps[3],
        )
        base = self._p05_git(root, "rev-parse", f"{prepared}^").stdout.strip()
        return {
            "root": root,
            "base": base,
            "prepared": prepared,
            "finding": finding,
            "red": red,
            "remediation": remediation,
            "head": head,
            "name": name,
            "email": email,
            "timestamps": timestamps,
            "receipt_data": receipt_data,
        }

    def _p05_semantic(self, history: dict[str, object]) -> bool:
        attempt = _Attempt(
            "academy/P05-checkpoint-remediation/1",
            1,
            str(history["prepared"]),
            str(history["base"]),
            str(history["head"]),
        )
        predicate = Predicate(
            "finding_remediation_link",
            "lab_semantics",
            {
                "profile": "checkpoint_remediation",
                "report": ".codearbiter/checkpoints/P05-academy.json",
            },
        )
        return _semantic(_SemanticContext(Path(history["root"]), attempt, predicate))

    def _p05_run_committed_tests(self, history: dict[str, object], label: str) -> None:
        root = Path(history["root"])
        checkout = self.root / f"p05-execute-{label}"
        subprocess.run(
            ["git", "clone", "--no-hardlinks", str(root), str(checkout)],
            cwd=self.root,
            check=True,
            capture_output=True,
            text=True,
        )
        observations = (
            ("prepared", _P05_PREPARED_TEST_NAME, 0),
            ("red", _P05_TEST_NAME, 1),
            ("remediation", _P05_TEST_NAME, 0),
            ("head", _P05_TEST_NAME, 0),
        )
        for role, test_name, expected_returncode in observations:
            self._p05_git(checkout, "checkout", "--detach", "--force", str(history[role]))
            result = subprocess.run(
                [sys.executable, "-m", "unittest", test_name, "-v"],
                cwd=checkout,
                check=False,
                capture_output=True,
                text=True,
            )
            with self.subTest(history=label, role=role):
                self.assertEqual(result.returncode, expected_returncode, result.stdout + result.stderr)
                if role == "red":
                    self.assertIn("0 != 1", result.stdout + result.stderr)

    def test_p05_accepts_deterministic_intended_and_equivalent_histories(self) -> None:
        prepared_root, _, prepared = self._p05_prepared_repository()
        intended = self._p05_history(
            prepared_root,
            prepared,
            "intended",
            name="P05 Intended Fixture",
            email="p05-intended@example.invalid",
            timestamps=tuple(f"2026-08-02T12:0{minute}:00+00:00" for minute in range(4)),
        )
        equivalent = self._p05_history(
            prepared_root,
            prepared,
            "equivalent",
            name="P05 Equivalent Fixture",
            email="p05-equivalent@example.invalid",
            timestamps=tuple(f"2026-08-02T13:0{minute}:00+00:00" for minute in range(4)),
        )

        for label, history in (("intended", intended), ("equivalent", equivalent)):
            self.assertTrue(self._p05_semantic(history), label)
            parent = prepared
            for index, role in enumerate(("finding", "red", "remediation", "head")):
                commit = str(history[role])
                self.assertRegex(commit, r"^[0-9a-f]{40}$")
                self.assertEqual(
                    self._p05_git(Path(history["root"]), "rev-list", "--parents", "-n", "1", commit).stdout.split(),
                    [commit, parent],
                )
                self.assertEqual(
                    tuple(
                        self._p05_git(
                            Path(history["root"]),
                            "diff-tree",
                            "--no-commit-id",
                            "--name-only",
                            "-r",
                            commit,
                        ).stdout.splitlines()
                    ),
                    _P05_ROLE_PATHS[index],
                )
                metadata = self._p05_git(
                    Path(history["root"]),
                    "show",
                    "-s",
                    "--format=%an%x00%ae%x00%aI%x00%cn%x00%ce%x00%cI",
                    commit,
                ).stdout.rstrip("\n").split("\x00")
                rendered_timestamp = str(history["timestamps"][index]).replace(
                    "+00:00", "Z"
                )
                self.assertEqual(
                    metadata,
                    [
                        history["name"],
                        history["email"],
                        rendered_timestamp,
                        history["name"],
                        history["email"],
                        rendered_timestamp,
                    ],
                )
                parent = commit
            self.assertEqual(
                _git_blob(Path(history["root"]), str(history["red"]), "tests/test_cli.py"),
                _git_blob(Path(history["root"]), str(history["head"]), "tests/test_cli.py"),
            )
            self._p05_run_committed_tests(history, label)

        for role in ("finding", "red", "remediation", "head"):
            self.assertNotEqual(intended[role], equivalent[role], role)
        for role, path in (
            ("finding", _P05_ROLE_PATHS[0][0]),
            ("red", _P05_ROLE_PATHS[1][0]),
            ("remediation", _P05_ROLE_PATHS[2][0]),
        ):
            self.assertEqual(
                _git_blob(Path(intended["root"]), str(intended[role]), path),
                _git_blob(Path(equivalent["root"]), str(equivalent[role]), path),
            )

        normalized_receipts = []
        for history in (intended, equivalent):
            raw_receipt = _git_blob(
                Path(history["root"]),
                str(history["head"]),
                _P05_ROLE_PATHS[3][0],
            )
            self.assertIsNotNone(raw_receipt)
            assert raw_receipt is not None
            normalized = json.loads(raw_receipt)
            for field, role in (
                ("finding_commit", "finding"),
                ("red_commit", "red"),
                ("remediation_commit", "remediation"),
            ):
                self.assertEqual(normalized[field], history[role])
                normalized[field] = f"<{role}>"
            normalized_receipts.append(normalized)
        self.assertEqual(normalized_receipts[0], normalized_receipts[1])

        receipt_data = dict(intended["receipt_data"])
        receipt_mutations = {
            "extra-field": {**receipt_data, "proof": "synthetic"},
            "missing-red": {
                key: value for key, value in receipt_data.items() if key != "red_commit"
            },
            "wrong-status": {**receipt_data, "status": "open"},
            "same-role-commit": {**receipt_data, "red_commit": intended["finding"]},
            "disjoint-paths": {
                **receipt_data,
                "affected_paths": ["README.md", "docs/proof.md"],
            },
        }
        intended_root = Path(intended["root"])
        receipt = intended_root / ".codearbiter/checkpoints/P05-academy.json"
        for label, forged_receipt in receipt_mutations.items():
            with self.subTest(receipt_mutation=label):
                self._p05_git(
                    intended_root,
                    "reset",
                    "--hard",
                    str(intended["remediation"]),
                )
                receipt.parent.mkdir(parents=True, exist_ok=True)
                receipt.write_bytes(
                    json.dumps(
                        forged_receipt,
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode("ascii")
                    + b"\n"
                )
                forged_head = self._p05_commit(
                    intended_root,
                    _P05_ROLE_PATHS[3],
                    f"forge {label}",
                    name=str(intended["name"]),
                    email=str(intended["email"]),
                    timestamp="2026-08-02T12:04:00+00:00",
                )
                forged_history = {**intended, "head": forged_head}
                self.assertFalse(self._p05_semantic(forged_history))

    def test_p05_rejects_red_commits_with_other_executable_test_ast_changes(self) -> None:
        prepared_root, _, prepared = self._p05_prepared_repository()
        for index, mutation in enumerate(
            (
                "run-cli",
                "helper",
                "other-test",
                "skip-decorator",
                "skip-call",
                "early-return",
                "report-before-state",
                "extra-required-arg",
                "no-self",
                "fixture-load-keyword",
                "rebind-self",
                "unknown-encoding-cookie",
                "non-utf8-cookie",
            )
        ):
            with self.subTest(mutation=mutation):
                history = self._p05_history(
                    prepared_root,
                    prepared,
                    f"mutated-{mutation}",
                    name="P05 Adversarial Fixture",
                    email="p05-adversarial@example.invalid",
                    timestamps=tuple(
                        f"2026-08-02T14:{index * 4 + minute:02d}:00+00:00"
                        for minute in range(4)
                    ),
                    red_mutation=mutation,
                )
                self.assertFalse(self._p05_semantic(history))
                if mutation == "unknown-encoding-cookie":
                    red_source = _git_blob(
                        Path(history["root"]),
                        str(history["red"]),
                        "tests/test_cli.py",
                    )
                    self.assertIsNotNone(red_source)
                    assert red_source is not None
                    with self.assertRaisesRegex(SyntaxError, "unknown encoding"):
                        compile(red_source, "tests/test_cli.py", "exec")

    def test_p05_finding_parser_rejects_terminal_claims_and_private_data(self):
        """A P05 finding is reviewed evidence, never a captured host session."""
        valid = (
            "# P05 Finding: blocked tickets omitted from unresolved summary\n\n"
            "Ticket `RQ-105` is blocked: `Venue access is awaiting facilities clearance`.\n"
            "Affected paths: `tests/test_cli.py`, `workshop_queue/cli.py`.\n"
        )
        self.assertTrue(_p05_finding_is_exact(valid))
        for label, forged in {
            "host-command": valid + "$ca-checkpoint\n",
            "terminal-output": valid + "PS C:\\repo> arbiter-academy check P05\n",
            "email": valid + "owner@example.com\n",
            "absolute-path": valid + "C:\\Users\\learner\\secret.txt\n",
            "token": valid + ("gh" + "p_" + "abcdefghijklmnopqrstuvwxyz1234567890\n"),
            "extra-section": valid + "## Raw output\nnot evidence\n",
        }.items():
            with self.subTest(label=label):
                self.assertFalse(_p05_finding_is_exact(forged))

    def test_p05_red_parser_rejects_comment_only_regression_bypass(self):
        text = '''import json
class WorkshopQueueCliTests:
    def test_report_json_counts_blocked_ticket_as_unresolved(self) -> None:
        tickets = json.loads(self.fixture.read_text(encoding="utf-8"))
        tickets[0]["id"] = "RQ-105"
        self.fixture.write_text(json.dumps(tickets), encoding="utf-8")
        claim_result = self.run_cli("claim", "RQ-105", "--volunteer", "Sam")
        block_result = self.run_cli("block", "RQ-105", "--reason", "Venue access is awaiting facilities clearance")
        report = self.run_cli("report", "--format", "json")
        self.assertEqual(claim_result.returncode, 0, claim_result.stderr)
        self.assertEqual(block_result.returncode, 0, block_result.stderr)
        self.assertEqual(report.returncode, 0, report.stderr)
        parsed = json.loads(report.stdout)
        self.assertEqual(parsed["blocked"], 1)
        self.assertEqual(parsed["unresolved"], 1)

if __name__ == "__main__":
    pass
'''
        source = text.encode("utf-8")
        self.assertTrue(_p05_red_regression_is_exact(source))
        start = text.index("    def test_report_json_counts_blocked_ticket_as_unresolved")
        end = text.index("\n\nif __name__", start)
        forged = '''    def test_report_json_counts_blocked_ticket_as_unresolved(self) -> None:
        """self.run_cli(\"claim\", \"RQ-105\", \"--volunteer\", \"Sam\")
        self.run_cli(\"block\", \"RQ-105\", \"--reason\", \"Venue access is awaiting facilities clearance\")
        self.run_cli(\"report\", \"--format\", \"json\")
        [\"blocked\"], 1; [\"unresolved\"], 1
        """
        pass'''
        self.assertFalse(_p05_red_regression_is_exact((text[:start] + forged + text[end:]).encode("utf-8")))

    def test_p05_red_parser_rejects_missing_fixture_setup(self):
        text = '''import json
class WorkshopQueueCliTests:
    def test_report_json_counts_blocked_ticket_as_unresolved(self) -> None:
        tickets = json.loads(self.fixture.read_text(encoding="utf-8"))
        tickets[0]["id"] = "RQ-105"
        self.fixture.write_text(json.dumps(tickets), encoding="utf-8")
        claim_result = self.run_cli("claim", "RQ-105", "--volunteer", "Sam")
        block_result = self.run_cli("block", "RQ-105", "--reason", "Venue access is awaiting facilities clearance")
        report = self.run_cli("report", "--format", "json")
        self.assertEqual(claim_result.returncode, 0, claim_result.stderr)
        self.assertEqual(block_result.returncode, 0, block_result.stderr)
        self.assertEqual(report.returncode, 0, report.stderr)
        parsed = json.loads(report.stdout)
        self.assertEqual(parsed["blocked"], 1)
        self.assertEqual(parsed["unresolved"], 1)
'''
        self.assertTrue(_p05_red_regression_is_exact(text.encode("utf-8")))
        missing_setup = text.replace(
            '        tickets = json.loads(self.fixture.read_text(encoding="utf-8"))\n'
            '        tickets[0]["id"] = "RQ-105"\n'
            '        self.fixture.write_text(json.dumps(tickets), encoding="utf-8")\n',
            "",
        )
        self.assertFalse(_p05_red_regression_is_exact(missing_setup.encode("utf-8")))

    def test_p05_red_parser_rejects_noop_commands_and_constant_assertions(self):
        """Calls alone are not evidence unless report data reaches both assertions."""
        text = '''class WorkshopQueueCliTests:
    def test_report_json_counts_blocked_ticket_as_unresolved(self) -> None:
        self.run_cli("claim", "RQ-105", "--volunteer", "Sam")
        self.run_cli("block", "RQ-105", "--reason", "Venue access is awaiting facilities clearance")
        self.run_cli("report", "--format", "json")
        ("blocked", "unresolved")
        self.assertEqual(1, 1)
        self.assertEqual(1, 1)
'''
        self.assertFalse(_p05_red_regression_is_exact(text.encode("utf-8")))


    def test_p01_spec_and_plan_reject_ambiguous_approval_and_scope_creep_variants(self):
        """Catches a P01 verifier that merely token-matches native feature artifacts."""
        spec = (
            "# Unresolved ticket report\n\n"
            "## Problem\nThe Workshop Queue JSON report lacks an unresolved count.\n\n"
            "## Scope\nJSON report behavior in workshop_queue/cli.py and verification in tests/test_cli.py only; "
            "exclude text-output changes, lifecycle changes, storage changes, dependencies, network behavior, credentials, and real personal data.\n\n"
            "## Acceptance criteria\n"
            "1. The JSON report adds integer unresolved equal to open + claimed.\n"
            "2. Existing integer open, claimed, and completed counts remain exact, and completed tickets do not contribute to unresolved.\n\n"
            "## Open questions\nNone.\n"
        )
        plan = (
            "# Academy feature plan\n\n"
            "## Acceptance criteria ledger\n"
            "- AC-01: The JSON report adds integer unresolved equal to open + claimed.\n"
            "- AC-02: Existing integer open, claimed, and completed counts remain exact, and completed tickets do not contribute to unresolved.\n\n"
            "## Tasks\n"
            "| ID | Path(s) | Verification | Maps to | Covers | Depends on | Status |\n"
            "| --- | --- | --- | --- | --- | --- | --- |\n"
            "| T-01 | tests/test_cli.py | focused unresolved-summary test | AC-01, AC-02 | AC-01, AC-02 | none | ACCEPTED |\n"
            "| T-02 | workshop_queue/cli.py | focused unresolved-summary test; python -m unittest discover -v; python -m compileall workshop_queue tests | AC-01, AC-02 | AC-01, AC-02 | T-01 | ACCEPTED |\n\n"
            "## MVP slice\nT-01 through T-02\n"
        )
        self.assertTrue(_p01_spec_and_plan(spec.encode(), plan.encode()))
        bad_specs = (
            spec.replace("open + claimed.", "open + claimed or open + completed."),
            spec.replace("open + claimed.", "open and claimed."),
            spec.replace("do not contribute to unresolved", "contribute to unresolved"),
            spec.replace("None.\n", "None.\nApproved by system at 2026-08-04.\n"),
            spec.replace(
                "The Workshop Queue JSON report lacks an unresolved count.",
                "The Workshop Queue JSON report lacks an unresolved count.\nStatus: approved 2026-08-04.",
            ),
            spec.replace(
                "The Workshop Queue JSON report lacks an unresolved count.",
                "The Workshop Queue JSON report lacks an unresolved count.\nApproval: granted by a system.",
            ),
            spec.replace(
                "The Workshop Queue JSON report lacks an unresolved count.",
                "The Workshop Queue JSON report lacks an unresolved count for learner@example.com.",
            ),
            spec.replace("2. Existing", "3. Existing"),
        )
        private_markers = (
            " https://learner:token@example.invalid/",
            " gh" + "p_aaaaaaaaaaaaaaaaaaaa",
            " -----BEGIN " + "PRIVATE KEY-----",
            " secret = 'academy-only'",
            r" C:\\Users\\learner\\private.txt",
            r" \\server\\share\\private.txt",
            " /private/path",
            " path=/private/data",
            " see (/private/data)",
            "\x01",
        )
        bad_specs += tuple(
            spec.replace(
                "The Workshop Queue JSON report lacks an unresolved count.",
                "The Workshop Queue JSON report lacks an unresolved count." + marker,
            )
            for marker in private_markers
        )
        bad_plans = (
            plan.replace(
                "## MVP slice\n",
                "| T-03 | README.md | python -m unittest discover -v | AC-01 | AC-01 | T-02 | ACCEPTED |\n\n## MVP slice\n",
            ),
            plan.replace("T-01 | tests/test_cli.py", "T-01 | tests/test_cli.py, README.md"),
            plan.replace("T-01 through T-02", "T-02 through T-01"),
            plan.replace(
                "| T-02 | workshop_queue/cli.py | focused unresolved-summary test; python -m unittest discover -v",
                "| T-02 | workshop_queue/cli.py | python -m unittest discover -v",
            ),
            plan.replace(
                "; python -m compileall workshop_queue tests",
                "; whoami; python -m compileall workshop_queue tests",
            ),
        )
        for bad_spec in bad_specs:
            with self.subTest(kind="spec"):
                self.assertFalse(_p01_spec_and_plan(bad_spec.encode(), plan.encode()))
        for bad_plan in bad_plans:
            with self.subTest(kind="plan"):
                self.assertFalse(_p01_spec_and_plan(spec.encode(), bad_plan.encode()))

    def test_p01_frozen_model_requires_the_prepared_no_unresolved_defect(self):
        """Catches a P01 proof that accepts a regression already green before the repair."""
        source = Path(__file__).resolve().parents[1]
        fixture = (source / "academy/scenarios/P01-feature-through-plan/files/p01-unresolved-tickets.json").read_bytes()
        cli = (source / "workshop_queue/cli.py").read_bytes()
        prepared, intended = _p01_fixture_models(fixture)
        expected = {"open": 1, "claimed": 1, "completed": 1, "unresolved": 2}
        self.assertEqual(prepared, {"open": 1, "claimed": 1, "completed": 1})
        self.assertNotEqual(prepared, expected)
        self.assertEqual(intended, expected)
        self.assertTrue(_p01_prepared_defect(cli))

        redundant = cli.replace(
            b"    if output_format == \"json\":\n",
            b"    counts['unresolved'] = counts[TicketStatus.OPEN.value] + counts[TicketStatus.CLAIMED.value]\n    if output_format == \"json\":\n",
        )
        duplicate_status = fixture.replace(b'"status":"claimed"', b'"status":"open"')
        invalid_lifecycle = fixture.replace(b'"claimed_by":"Academy Volunteer"', b'"claimed_by":null')
        private_description = fixture.replace(
            b'"description":"Fictional Academy ticket."',
            b'"description":"Contact learner@example.com for this fictional ticket."',
            1,
        )
        invalid_chronology = fixture.replace(
            b'"completed_at":"2026-08-01T09:25:00Z"',
            b'"completed_at":"2026-08-01T09:00:00Z"',
        )
        invalid_calendar_time = fixture.replace(
            b'"created_at":"2026-08-01T09:00:00Z"',
            b'"created_at":"2026-02-30T09:00:00Z"',
        )
        private_fixtures = tuple(
            fixture.replace(
                b'"description":"Fictional Academy ticket."',
                f'"description":"{marker}"'.encode("utf-8"),
                1,
            )
            for marker in (
                "gh" + "p_aaaaaaaaaaaaaaaaaaaa",
                "secret = academy-only",
                r"C:\\private\\ticket.txt",
            )
        )
        self.assertFalse(_p01_prepared_defect(redundant))
        for candidate in (
            duplicate_status,
            invalid_lifecycle,
            private_description,
            invalid_chronology,
            invalid_calendar_time,
            *private_fixtures,
        ):
            with self.subTest(fixture=candidate):
                self.assertIsNone(_p01_fixture_models(candidate))

    def test_p01_source_identity_is_typed_private_and_exact(self):
        """Catches source identity comparisons where Python bools satisfy integer fields."""
        source = Path(__file__).resolve().parents[1]
        identity = json.loads(
            (source / "academy/scenarios/P01-feature-through-plan/files/codearbiter-source.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertTrue(_p01_source_identity(identity))
        for mutation in (
            {**identity, "schema_version": True},
            {**identity, "repository": "learner@example.com"},
        ):
            with self.subTest(mutation=mutation):
                self.assertFalse(_p01_source_identity(mutation))

    def test_p01_board_transition_returns_false_when_line_counts_differ(self):
        """Catches a strict zip exception escaping a malformed board comparison."""
        attempt = _Attempt("academy/P01-feature-through-plan/1", 1, "prepared", "base", "head")
        with mock.patch(
            "academy_engine.checkpoints._p01_regular_blob",
            side_effect=(
                b"- [ ] academy.feature.0002 - Show unresolved tickets in the summary\n",
                b"- [~] academy.feature.0002 - Show unresolved tickets in the summary  (started 2026-08-04)\nextra\n",
            ),
        ):
            self.assertFalse(
                _p01_board_transition(
                    self.root,
                    attempt,
                    ".codearbiter/open-tasks.md",
                    "academy.feature.0002",
                )
            )

    def test_p01_criteria_require_the_actual_formula_and_completed_exclusion(self):
        """Catches a criterion parser that accepts a semantic inversion by token presence."""
        self.assertTrue(
            _p01_criterion(
                "The JSON report adds integer unresolved equal to open + claimed.",
                first=True,
            )
        )
        self.assertTrue(
            _p01_criterion(
                "Existing integer open, claimed, and completed counts remain exact, and completed tickets do not contribute to unresolved.",
                first=False,
            )
        )
        self.assertFalse(
            _p01_criterion(
                "The JSON report adds integer unresolved equal to open and claimed.",
                first=True,
            )
        )
        self.assertFalse(
            _p01_criterion(
                "Existing integer open, claimed, and completed counts remain exact, and completed tickets contribute to unresolved.",
                first=False,
            )
        )

    def test_p01_repair_must_follow_the_status_count_comprehension(self):
        """Catches a syntactically exact assignment placed after JSON output or return."""
        source = Path(__file__).resolve().parents[1]
        prepared = (source / "workshop_queue/cli.py").read_bytes()
        assignment = (
            b"    counts['unresolved'] = (\n"
            b"        counts[TicketStatus.OPEN.value]\n"
            b"        + counts[TicketStatus.CLAIMED.value]\n"
            b"    )\n"
        )
        count_to_json = (
            b"    counts = {status.value: sum(ticket.status is status for ticket in tickets) for status in TicketStatus}\n"
            b'    if output_format == "json":\n'
        )
        correct = prepared.replace(
            count_to_json,
            count_to_json.removesuffix(b'    if output_format == "json":\n')
            + assignment
            + b'    if output_format == "json":\n',
        )
        after_json = prepared.replace(
            b"    for status in TicketStatus:\n",
            assignment + b"    for status in TicketStatus:\n",
        )
        self.assertTrue(_p01_exact_repair(prepared, correct))
        self.assertFalse(_p01_exact_repair(prepared, after_json))

    def test_p08_authenticated_profile_proves_authority_before_external_checkpoint(self):
        attempt = _Attempt(
            "academy/P08-repository-hygiene/1", 1, "a" * 40, "b" * 40, "c" * 40
        )
        predicate = Predicate("live_ref_hygiene", "lab_semantics", {"profile": "p08_authenticated"})
        context = _SemanticContext(self.root, attempt, predicate)
        store, authority = mock.Mock(), mock.Mock()

        sequence = mock.Mock()
        with mock.patch(
            "academy_engine.checkpoints.preflight_p08",
            return_value=("b" * 40, mock.Mock(), authority),
        ) as preflight, mock.patch(
            "academy_engine.checkpoints.open_p08_store", return_value=store
        ) as opened, mock.patch(
            "academy_engine.checkpoints.validate_p08_checkpoint", return_value=True
        ) as verified:
            sequence.attach_mock(preflight, "preflight")
            sequence.attach_mock(opened, "opened")
            sequence.attach_mock(verified, "verified")
            self.assertTrue(_semantic(context))

        preflight.assert_called_once_with(self.root)
        opened.assert_called_once_with(self.root, base="b" * 40, authority=authority)
        identity = P08AttemptIdentity(1, attempt.branch, attempt.prepared, attempt.head)
        verified.assert_called_once_with(self.root, store, identity)
        self.assertEqual(
            sequence.mock_calls,
            [
                mock.call.preflight(self.root),
                mock.call.opened(self.root, base="b" * 40, authority=authority),
                mock.call.verified(self.root, store, identity),
            ],
        )

    def write(self, value): self.path.write_text(json.dumps(value), encoding="utf-8")

    def test_p02_prepare_requires_the_exact_patch_derived_learner_profile(self):
        source = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            installed_data = root / "installed-data"
            installed = installed_data / "share/arbiter-academy/academy"
            installed.parent.mkdir(parents=True)
            shutil.copytree(source / "academy", installed)
            shutil.copytree(source / "academy", root / "academy")
            scenario_root = root / "academy/scenarios/P02-commit-review-pr"
            profile = root / ".codearbiter/tech-stack.md"
            profile.parent.mkdir(parents=True)
            shutil.copy2(source / ".codearbiter/tech-stack.md", profile)
            subprocess.run(["git", "init", "-b", "main"], cwd=root, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.name", "Fixture"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.email", "fixture@example.invalid"], cwd=root, check=True)
            subprocess.run(["git", "add", "."], cwd=root, check=True)
            subprocess.run(["git", "commit", "-m", "base"], cwd=root, check=True, capture_output=True)
            base = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True).stdout.strip()
            contract = LabContract(
                "P02-commit-review-pr",
                "Commit, review, and PR",
                "academy/tracks/practitioner/P02-commit-review-pr.md",
                "academy/checkpoints/P02-commit-review-pr.json",
                "training_scenarios/P02-commit-review-pr.json",
            )

            def prepare(kind: str) -> _Attempt:
                subprocess.run(["git", "switch", "--detach", base], cwd=root, check=True, capture_output=True)
                destination = root / contract.scenario_path
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(scenario_root / "files/scenario.json", destination)
                if kind != "missing":
                    subprocess.run(
                        [
                            "git",
                            "apply",
                            "--include=.codearbiter/tech-stack.md",
                            "--",
                            "academy/scenarios/P02-commit-review-pr/files/P02-worktree.patch",
                        ],
                        cwd=root,
                        check=True,
                        capture_output=True,
                    )
                if kind == "wrong":
                    profile.write_text("# unverified learner profile\n", encoding="utf-8")
                if kind == "extra":
                    (root / "unexpected.txt").write_text("extra\n", encoding="utf-8")
                subprocess.run(["git", "add", "."], cwd=root, check=True)
                subprocess.run(
                    ["git", "commit", "-m", "academy: prepare P02-commit-review-pr attempt 1"],
                    cwd=root,
                    check=True,
                    capture_output=True,
                )
                prepared = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True).stdout.strip()
                return _Attempt("academy/P02-commit-review-pr/1", 1, prepared, base, prepared)

            with mock.patch(
                "academy_engine.exercise_state.sysconfig.get_path",
                return_value=str(installed_data),
            ):
                self.assertTrue(_validate_prepare(root, contract, prepare("exact")))
                for kind in ("missing", "wrong", "extra"):
                    with self.subTest(kind=kind):
                        self.assertFalse(_validate_prepare(root, contract, prepare(kind)))

    def test_non_p02_prepare_remains_manifest_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            files = root / "academy/scenarios/F99-control/files"
            files.mkdir(parents=True)
            (files / "scenario.json").write_text('{"control":true}\n', encoding="utf-8")
            (files.parent / "manifest.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "id": "F99-control",
                        "files": [
                            {
                                "source": "scenario.json",
                                "destination": "training_scenarios/F99-control.json",
                            }
                        ],
                        "removals": [],
                        "starting_task": "F99",
                        "checkpoint": "academy/checkpoints/F99-control.json",
                        "requires_push_safe_setup": False,
                    }
                ),
                encoding="utf-8",
            )
            subprocess.run(["git", "init", "-b", "main"], cwd=root, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.name", "Fixture"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.email", "fixture@example.invalid"], cwd=root, check=True)
            subprocess.run(["git", "add", "."], cwd=root, check=True)
            subprocess.run(["git", "commit", "-m", "base"], cwd=root, check=True, capture_output=True)
            base = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True).stdout.strip()
            destination = root / "training_scenarios/F99-control.json"
            destination.parent.mkdir()
            shutil.copy2(files / "scenario.json", destination)
            subprocess.run(["git", "add", "."], cwd=root, check=True)
            subprocess.run(["git", "commit", "-m", "prepare"], cwd=root, check=True, capture_output=True)
            prepared = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True).stdout.strip()
            contract = LabContract("F99-control", "Control", "guide.md", "checkpoint.json", "training_scenarios/F99-control.json")
            attempt = _Attempt("academy/F99-control/1", 1, prepared, base, prepared)

            self.assertTrue(_validate_prepare(root, contract, attempt))

    def test_p02_semantics_use_external_state_and_strict_offline_receipt(self):
        attempt = _Attempt(
            "academy/P02-commit-review-pr/1",
            1,
            "b" * 40,
            "a" * 40,
            "c" * 40,
        )
        predicate = Predicate(
            "review_pr_commit_range",
            "lab_semantics",
            {
                "profile": "pr_receipt",
                "receipt": ".codearbiter/reports/academy/P02-pr-receipt.json",
            },
        )
        context = _SemanticContext(self.root, attempt, predicate)
        receipt = {"strict": "offline"}
        store = object()

        with mock.patch(
            "academy_engine.checkpoints._git_blob", return_value=b"receipt-bytes"
        ), mock.patch(
            "academy_engine.checkpoints.open_existing_p02_store", return_value=store
        ) as opened, mock.patch(
            "academy_engine.checkpoints._parse_p02_receipt_bytes", return_value=receipt
        ) as parsed, mock.patch(
            "academy_engine.checkpoints.validate_p02_checkpoint", return_value=True
        ) as validated:
            self.assertTrue(_semantic(context))

        opened.assert_called_once_with(self.root, base=attempt.base)
        parsed.assert_called_once_with(b"receipt-bytes", object_format="sha1")
        validated.assert_called_once()

    def test_untouched_partial_and_wrong_value_fail_closed(self):
        for label, contents in (("untouched", None), ("partial", ""), ("wrong", "wrong")):
            with self.subTest(label=label):
                target = self.root / ".codearbiter" / "specs" / "proof.md"
                if contents is not None:
                    target.parent.mkdir(parents=True, exist_ok=True); target.write_text(contents, encoding="utf-8")
                result = evaluate_checkpoint(self.root, "F01-fork-clone-doctor")
                self.assertFalse(result.passed)

    def test_passing_command_does_not_replace_missing_governed_artifact(self):
        self.write({"schema_version": 2, "id": "F01-fork-clone-doctor", "predicates": [{"id": "remote_and_doctor", "type": "lab_semantics", "profile": "remote_doctor", "artifact": ".codearbiter/reports/academy/F01-doctor.json"}]})
        self.assertFalse(evaluate_checkpoint(self.root, "F01-fork-clone-doctor").passed)

    def test_definition_rejects_unknown_unsafe_and_unbounded_values(self):
        for predicate in (
            {"id":"x","type":"unknown"},
            {"id":"x","type":"lab_semantics","profile":"remote_doctor","artifact":"../private"},
            {"id":"x","type":"lab_semantics","profile":"remote_doctor","artifact":".codearbiter/report.json","timeout_seconds":999},
        ):
            with self.subTest(predicate=predicate):
                self.write({"schema_version":2,"id":"F01-fork-clone-doctor","predicates":[predicate]})
                with self.assertRaises(CheckpointError): load_checkpoint(self.path)
        self.write({"schema_version":1,"id":"F01-fork-clone-doctor","predicates":[{"id":"x","type":"file_exists","path":"proof"}]})
        with self.assertRaises(CheckpointError):
            load_checkpoint(self.path)

    def test_definition_runtime_matches_the_single_predicate_schema(self):
        """Catches runtime accepting multiple predicates forbidden by checkpoint.schema.json."""
        predicate = {
            "id": "remote_and_doctor",
            "type": "lab_semantics",
            "profile": "remote_doctor",
            "artifact": ".codearbiter/reports/academy/F01-doctor.json",
        }
        self.write(
            {
                "schema_version": 2,
                "id": "F01-fork-clone-doctor",
                "predicates": [predicate, {**predicate, "id": "second"}],
            }
        )
        with self.assertRaisesRegex(CheckpointError, "exactly one"):
            load_checkpoint(self.path)

    def test_definition_accepts_the_u04_two_project_binding_fields(self):
        self.write(
            {
                "schema_version": 2,
                "id": "U04-initialize-projects",
                "predicates": [
                    {
                        "id": "initialized_projects",
                        "type": "lab_semantics",
                        "profile": "initialized_projects",
                        "greenfield": ".academy/workspaces/U04-greenfield",
                        "brownfield": ".academy/workspaces/U04-brownfield",
                        "report": ".codearbiter/reports/academy/U04-initialization.md",
                    }
                ],
            }
        )
        checkpoint = load_checkpoint(self.path)
        self.assertEqual(checkpoint.predicates[0].data["greenfield"], ".academy/workspaces/U04-greenfield")
        self.assertEqual(checkpoint.predicates[0].data["brownfield"], ".academy/workspaces/U04-brownfield")

    def test_definition_accepts_u03_real_release_target_fields(self):
        self.write(
            {
                "schema_version": 2,
                "id": "U03-refactor-chore-release",
                "predicates": [
                    {
                        "id": "refactor_chore_release",
                        "type": "lab_semantics",
                        "profile": "refactor_chore_release",
                        "scenario": "training_scenarios/U03-refactor-chore-release.json",
                        "code": "workshop_queue/store.py",
                        "test": "tests/test_store.py",
                        "chore": "README.md",
                        "release_target": "academy-private-training",
                        "release_version": "0.0.1",
                        "release_tag": "academy-v0.0.1",
                        "release_changelog": "CHANGELOG.md",
                        "release_targets": ".codearbiter/release-targets.md",
                    }
                ],
            }
        )
        checkpoint = load_checkpoint(self.path)
        self.assertEqual(checkpoint.predicates[0].data["release_tag"], "academy-v0.0.1")

    def test_u03_real_release_fields_are_declared_by_the_checkpoint_schema(self):
        """Catches public schema drift from the real ca-release target contract."""
        schema = json.loads(
            (Path(__file__).parents[1] / "academy/checkpoint.schema.json").read_text(
                encoding="utf-8"
            )
        )
        properties = schema["properties"]["predicates"]["items"]["properties"]
        self.assertIn("release_changelog", properties)
        self.assertIn("release_targets", properties)
        self.assertNotIn("release_message", properties)

    def test_wrong_branch_fails_recomputed_git_evidence(self):
        subprocess.run(["git", "init"], cwd=self.root, check=True, capture_output=True, text=True)
        subprocess.run(["git", "switch", "-c", "wrong-branch"], cwd=self.root, check=True, capture_output=True, text=True)
        self.write({"schema_version":2,"id":"F01-fork-clone-doctor","predicates":[{"id":"remote_and_doctor","type":"lab_semantics","profile":"remote_doctor","artifact":".codearbiter/reports/academy/F01-doctor.json"}]})
        self.assertFalse(evaluate_checkpoint(self.root, "F01-fork-clone-doctor").passed)

    def test_p06_provenance_recovery_requires_exact_context_provenance_history_and_preserved_blob(self):
        from tests.test_p06_context_recovery import _p06_semantic_fixture

        _root, intended = _p06_semantic_fixture(self)
        self.assertTrue(_semantic(intended))
        _root, wrong_route = _p06_semantic_fixture(self, route="re-baseline")
        self.assertFalse(_semantic(wrong_route))
        _root, changed_note = _p06_semantic_fixture(self, alter_note=True)
        self.assertFalse(_semantic(changed_note))
        _root, extra_path = _p06_semantic_fixture(self, extra_correction_path=True)
        self.assertFalse(_semantic(extra_path))

    def test_p05_rejects_finding_and_remediation_commits_before_prepare(self):
        subprocess.run(["git", "init", "-b", "main"], cwd=self.root, check=True, capture_output=True, text=True)
        subprocess.run(["git", "config", "user.name", "Fixture"], cwd=self.root, check=True, capture_output=True, text=True)
        subprocess.run(["git", "config", "user.email", "fixture@example.invalid"], cwd=self.root, check=True, capture_output=True, text=True)
        paths = ("workshop_queue/service.py", "tests/test_service.py")
        seed = self.root / "README.md"
        seed.write_text("seed\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=self.root, check=True, capture_output=True, text=True)
        subprocess.run(["git", "commit", "-m", "seed"], cwd=self.root, check=True, capture_output=True, text=True)
        for path in paths:
            target = self.root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("finding\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=self.root, check=True, capture_output=True, text=True)
        subprocess.run(["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-m", "historical finding"], cwd=self.root, check=True, capture_output=True, text=True)
        finding = subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.root, check=True, capture_output=True, text=True).stdout.strip()
        for path in paths:
            (self.root / path).write_text("historical remediation\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=self.root, check=True, capture_output=True, text=True)
        subprocess.run(["git", "commit", "-m", "historical remediation"], cwd=self.root, check=True, capture_output=True, text=True)
        remediation = subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.root, check=True, capture_output=True, text=True).stdout.strip()
        subprocess.run(["git", "commit", "--allow-empty", "-m", "prepare"], cwd=self.root, check=True, capture_output=True, text=True)
        prepared = subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.root, check=True, capture_output=True, text=True).stdout.strip()
        for path in paths:
            (self.root / path).write_text("learner edit\n", encoding="utf-8")
        report = self.root / ".codearbiter" / "checkpoints" / "P05-academy.json"
        report.parent.mkdir(parents=True)
        report.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "finding_id": "ACADEMY-P05",
                    "finding_commit": finding,
                    "remediation_commit": remediation,
                    "paths": list(paths),
                    "status": "remediated",
                }
            ),
            encoding="utf-8",
        )
        subprocess.run(["git", "add", "."], cwd=self.root, check=True, capture_output=True, text=True)
        subprocess.run(["git", "commit", "-m", "claim old remediation"], cwd=self.root, check=True, capture_output=True, text=True)
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.root, check=True, capture_output=True, text=True).stdout.strip()
        predicate = Predicate(
            "finding_remediation_link",
            "lab_semantics",
            {"profile": "checkpoint_remediation", "report": ".codearbiter/checkpoints/P05-academy.json"},
        )
        attempt = _Attempt("academy/P05-checkpoint-remediation/1", 1, prepared, remediation, head)
        self.assertFalse(_semantic(_SemanticContext(self.root, attempt, predicate)))

    def test_contract_loader_rejects_duplicate_and_boolean_schema_versions(self):
        source = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copytree(source / "academy", root / "academy")
            path = root / "academy" / "contracts.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["contracts"].append(payload["contracts"][0])
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(CheckpointError):
                load_contracts(root)
            payload["contracts"].pop()
            payload["schema_version"] = True
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(CheckpointError):
                load_contracts(root)
            shutil.copyfile(source / "academy" / "contracts.json", path)
            checkpoint = root / "academy" / "checkpoints" / "F01-fork-clone-doctor.json"
            checkpoint.write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "id": "F01-fork-clone-doctor",
                        "predicates": [
                            {
                                "id": "live_context_orientation",
                                "type": "lab_semantics",
                                "profile": "orientation",
                                "artifact": ".codearbiter/reports/academy/F02-orientation.json",
                                "context": ".codearbiter/CONTEXT.md",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(CheckpointError, "noncanonical"):
                load_contracts(root)

    def test_generic_one_commit_answers_without_remotes_do_not_pass(self):
        source = Path(__file__).resolve().parents[1]
        with RetryingTemporaryDirectory() as directory:
            root = Path(directory) / "repo"
            root.mkdir()
            shutil.copytree(source / "academy", root / "academy")
            shutil.copytree(source / "academy_engine", root / "academy_engine")
            shutil.copytree(source / "scripts", root / "scripts")
            shutil.copytree(source / ".codearbiter", root / ".codearbiter")
            shutil.copytree(source / "workshop_queue", root / "workshop_queue")
            subprocess.run(["git", "init", "-b", "main"], cwd=root, check=True, capture_output=True, text=True)
            subprocess.run(
                ["git", "add", "-f", "academy", "academy_engine", "scripts", ".codearbiter"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-m", "base"], cwd=root, check=True, capture_output=True, text=True)
            lab_id = "F01-fork-clone-doctor"
            subprocess.run(["git", "switch", "-c", f"academy/{lab_id}/1"], cwd=root, check=True, capture_output=True, text=True)
            scenario = root / "training_scenarios" / f"{lab_id}.json"
            scenario.parent.mkdir(parents=True)
            shutil.copyfile(
                root / "academy" / "scenarios" / lab_id / "files" / "scenario.json",
                scenario,
            )
            subprocess.run(["git", "add", str(scenario.relative_to(root))], cwd=root, check=True, capture_output=True, text=True)
            subprocess.run(["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-m", f"academy: prepare {lab_id} attempt 1"], cwd=root, check=True, capture_output=True, text=True)
            for item in json.loads((root / "academy" / "contracts.json").read_text(encoding="utf-8"))["contracts"]:
                for name, payload in (
                    ("outcome.json", {"lab_id": item["id"], "status": "completed"}),
                    ("governed.json", {"lab_id": item["id"], "status": "governed"}),
                ):
                    path = root / ".academy" / "work" / item["id"] / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(json.dumps(payload), encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=root, check=True, capture_output=True, text=True)
            subprocess.run(["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-m", "all answers"], cwd=root, check=True, capture_output=True, text=True)
            self.assertFalse(evaluate_checkpoint(root, lab_id).passed)

    def test_current_semantic_attempt_two_is_selected_and_bound_to_its_head(self):
        source = Path(__file__).resolve().parents[1]
        lab_id = "F02-orient-to-state"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "repo"
            root.mkdir()
            shutil.copytree(source / "academy", root / "academy")
            shutil.copytree(source / "academy_engine", root / "academy_engine")
            shutil.copytree(source / "scripts", root / "scripts")
            shutil.copytree(source / ".codearbiter", root / ".codearbiter")
            track = root / "academy" / "tracks" / "foundations"
            track.mkdir(parents=True, exist_ok=True)
            (track / f"{lab_id}.md").write_text("# Orientation lab\n", encoding="utf-8")
            subprocess.run(["git", "init", "-b", "main"], cwd=root, check=True, capture_output=True, text=True)
            subprocess.run(
                ["git", "add", "-f", "academy", "academy_engine", "scripts", ".codearbiter"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-m", "base"], cwd=root, check=True, capture_output=True, text=True)
            for attempt in (1, 2):
                subprocess.run(["git", "switch", "-c", f"academy/{lab_id}/{attempt}", "main"], cwd=root, check=True, capture_output=True, text=True)
                prepared = root / "training_scenarios" / f"{lab_id}.json"
                prepared.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(
                    root / "academy" / "scenarios" / lab_id / "files" / "scenario.json",
                    prepared,
                )
                subprocess.run(["git", "add", str(prepared.relative_to(root))], cwd=root, check=True, capture_output=True, text=True)
                subprocess.run(["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-m", f"academy: prepare {lab_id} attempt {attempt}"], cwd=root, check=True, capture_output=True, text=True)
                if attempt == 1:
                    subprocess.run(["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "--allow-empty", "-m", "incomplete"], cwd=root, check=True, capture_output=True, text=True)
                    subprocess.run(["git", "switch", "main"], cwd=root, check=True, capture_output=True, text=True)
                    continue
                context = (root / ".codearbiter" / "CONTEXT.md").read_bytes()
                artifact = root / ".codearbiter" / "reports" / "academy" / "F02-orientation.json"
                artifact.parent.mkdir(parents=True, exist_ok=True)
                artifact.write_text(
                    json.dumps(
                        {
                            "schema_version": 1,
                            "context_path": ".codearbiter/CONTEXT.md",
                            "context_sha256": hashlib.sha256(context).hexdigest(),
                            "stage": 2,
                        }
                    ),
                    encoding="utf-8",
                )
                subprocess.run(["git", "add", str(artifact.relative_to(root))], cwd=root, check=True, capture_output=True, text=True)
                subprocess.run(["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-m", "record live context orientation"], cwd=root, check=True, capture_output=True, text=True)
            result = evaluate_checkpoint(root, lab_id)
            self.assertTrue(result.passed, result.failed_predicates)
            self.assertEqual(result.attempt, f"academy/{lab_id}/2")
            self.assertEqual(
                result.head_commit,
                subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True).stdout.strip(),
            )
            checked = subprocess.run(
                [
                    sys.executable,
                    str(source / "scripts" / "academy.py"),
                    "--repository",
                    str(root),
                    "check",
                    lab_id,
                ],
                cwd=root,
                capture_output=True,
                text=True,
            )
            self.assertEqual(checked.returncode, 0)
            self.assertEqual(
                checked.stdout,
                f"checkpoint {lab_id}: passed; progress: .academy/progress.json\n",
            )
            self.assertEqual(checked.stderr, "")
            progress_path = root / ".academy" / "progress.json"
            self.assertTrue(progress_path.is_file())
            # The public command owns progress; this fixture now returns to the
            # clean attempt boundary before it tests source-integrity drift.
            progress_path.unlink()
            added_verifier = root / "academy_engine" / "benign_extension.py"
            added_verifier.write_text("# benign but unreviewed verifier extension\n", encoding="utf-8")
            subprocess.run(["git", "add", str(added_verifier.relative_to(root))], cwd=root, check=True, capture_output=True, text=True)
            subprocess.run(["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-m", "add verifier extension"], cwd=root, check=True, capture_output=True, text=True)
            extended_verifier = evaluate_checkpoint(root, lab_id)
            self.assertFalse(extended_verifier.passed)
            self.assertIn("source_integrity", extended_verifier.failed_predicates)
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=Fixture",
                    "-c",
                    "user.email=fixture@example.invalid",
                    "revert",
                    "--no-edit",
                    "HEAD",
                ],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )
            restored_baseline = evaluate_checkpoint(root, lab_id)
            self.assertFalse(restored_baseline.passed)
            self.assertIn("live_context_orientation", restored_baseline.failed_predicates)
            remotes_path = root / "academy_engine" / "remotes.py"
            remotes_original = remotes_path.read_bytes()
            remotes_path.write_bytes(remotes_original + b"\n# verifier substitution\n")
            substituted_verifier = evaluate_checkpoint(root, lab_id)
            self.assertFalse(substituted_verifier.passed)
            self.assertIn("source_integrity", substituted_verifier.failed_predicates)
            remotes_path.write_bytes(remotes_original)
            restored_baseline = evaluate_checkpoint(root, lab_id)
            self.assertFalse(restored_baseline.passed)
            self.assertIn("live_context_orientation", restored_baseline.failed_predicates)
            checkpoint_path = root / "academy" / "checkpoints" / f"{lab_id}.json"
            checkpoint_original = checkpoint_path.read_bytes()
            checkpoint_path.write_text(
                checkpoint_path.read_text(encoding="utf-8") + "\n",
                encoding="utf-8",
            )
            substituted = evaluate_checkpoint(root, lab_id)
            self.assertFalse(substituted.passed)
            self.assertIn("source_integrity", substituted.failed_predicates)
            checkpoint_path.write_bytes(checkpoint_original)
            restored_baseline = evaluate_checkpoint(root, lab_id)
            self.assertFalse(restored_baseline.passed)
            self.assertIn("live_context_orientation", restored_baseline.failed_predicates)
            subprocess.run(
                ["git", "switch", "-c", "alternate-rules"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )
            checkpoint_path.write_bytes(checkpoint_original + b"\n")
            subprocess.run(
                ["git", "add", str(checkpoint_path.relative_to(root))],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=Fixture",
                    "-c",
                    "user.email=fixture@example.invalid",
                    "commit",
                    "-m",
                    "alternate checkpoint rules",
                ],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )
            clean_alternate = evaluate_checkpoint(root, lab_id)
            self.assertFalse(clean_alternate.passed)
            self.assertIn("source_integrity", clean_alternate.failed_predicates)


class P03NativeEvidenceTests(unittest.TestCase):
    """Exercise the P03 evidence predicate against immutable, real Git history."""

    def setUp(self) -> None:
        self.temp = RetryingTemporaryDirectory()
        self.root = Path(self.temp.name)
        subprocess.run(["git", "init", "-b", "main"], cwd=self.root, check=True, capture_output=True, text=True)
        subprocess.run(["git", "config", "user.name", "Ada Learner"], cwd=self.root, check=True)
        subprocess.run(["git", "config", "user.email", "p03-private-canary" + "@example.invalid"], cwd=self.root, check=True)
        log = self.root / ".codearbiter/decisions/decision-log.md"
        log.parent.mkdir(parents=True)
        log.write_text("# Decision log\n\n", encoding="utf-8")
        (self.root / ".codearbiter/decisions/0003-verifier-trust.md").write_text("# ADR-0003\n", encoding="utf-8")
        (self.root / "README.md").write_text("base\n", encoding="utf-8")
        self._commit("base")
        subprocess.run(["git", "switch", "-c", "academy/P03-record-an-adr/1"], cwd=self.root, check=True, capture_output=True, text=True)
        self._commit("academy: prepare P03-record-an-adr attempt 1", empty=True)
        self.prepared = self._head()
        self._write_valid_evidence("Ada Learner")
        self._commit("record decision")
        self.head = self._head()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _head(self) -> str:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.root, check=True, capture_output=True, text=True).stdout.strip()

    def _commit(self, message: str, *, empty: bool = False) -> None:
        subprocess.run(["git", "add", "-A"], cwd=self.root, check=True, capture_output=True, text=True)
        command = ["git", "commit", "-m", message]
        if empty:
            command.insert(2, "--allow-empty")
        environment = os.environ.copy()
        environment["GIT_AUTHOR_DATE"] = "2026-08-04T12:00:00-04:00"
        environment["GIT_COMMITTER_DATE"] = "2026-08-04T12:00:00-04:00"
        subprocess.run(command, cwd=self.root, env=environment, check=True, capture_output=True, text=True)

    def _write_valid_evidence(self, name: str) -> None:
        date = subprocess.run(["git", "show", "-s", "--format=%aI", "HEAD"], cwd=self.root, check=True, capture_output=True, text=True).stdout[:10]
        adr = self.root / ".codearbiter/decisions/0004-academy-lab.md"
        adr.write_text(
            "---\nstatus: accepted\ndate: " + date + "\ntitle: Choose the Workshop Queue summary-format boundary\n"
            + "decided-by: " + name + "\nsupersedes: none\ngoverns: workshop_queue/cli.py\n---\n\n"
            + "# ADR-0004 — Choose the Workshop Queue summary-format boundary\n\n## Status\n\nAccepted\n\n"
            + "## Context\n\nStable text supports people; structured JSON supports automation.\n\n## Decision\n\n"
            + "Use stable text for Workshop Queue summaries.\n\n## Alternatives considered\n\nStable text and structured JSON were considered.\n\n"
            + "## Consequences\n\nStable text remains readable, while the rejected structured JSON costs a versioned schema.\n\n"
            + "## Risks\n\nConsumers must parse text carefully.\n",
            encoding="utf-8",
        )
        log = self.root / ".codearbiter/decisions/decision-log.md"
        log.write_text(log.read_text(encoding="utf-8") + "## DECISION-0004 — ADR-0004 — Choose the Workshop Queue summary-format boundary\n\n"
            + "**Date:** " + date + "\n**Status:** accepted\n**Supersedes:** none\n**Decided by:** " + name + "\n"
            + "**Decision category:** architecture\n**Artifact-section-hash:** n/a\n\n## Variance summary\n\nStatus type: open-decision-closure\n\n"
            + "## Decision\n\nUse stable text for Workshop Queue summaries.\n\n## SMARTS rationale\n\nStable and measurable.\n\n"
            + "## Implementation implication\n\nKeep workshop_queue/cli.py stable.\n",
            encoding="utf-8")

    def test_p03_accepts_one_real_co_commit_with_native_artifacts(self) -> None:
        from academy_engine.checkpoints import _p03_accepted_adr

        attempt = _Attempt("academy/P03-record-an-adr/1", 1, self.prepared, "0" * 40, self.head)
        self.assertTrue(_p03_accepted_adr(self.root, attempt, ".codearbiter/decisions/0004-academy-lab.md", ".codearbiter/decisions/decision-log.md"))

    def test_p03_accepts_the_equivalent_ordered_two_commit_history(self) -> None:
        from academy_engine.checkpoints import _p03_accepted_adr

        subprocess.run(["git", "reset", "--hard", self.prepared], cwd=self.root, check=True, capture_output=True, text=True)
        self._write_valid_evidence("Ada Learner")
        log = self.root / ".codearbiter/decisions/decision-log.md"
        prepared_log = "# Decision log\n\n"
        log.write_text(prepared_log, encoding="utf-8")
        self._commit("record ADR")
        log.write_text((self.root / ".codearbiter/decisions/decision-log.md").read_text(encoding="utf-8") + "## DECISION-0004 — ADR-0004 — Choose the Workshop Queue summary-format boundary\n\n"
            + "**Date:** " + subprocess.run(["git", "show", "-s", "--format=%aI", "HEAD"], cwd=self.root, check=True, capture_output=True, text=True).stdout[:10]
            + "\n**Status:** accepted\n**Supersedes:** none\n**Decided by:** Ada Learner\n**Decision category:** architecture\n**Artifact-section-hash:** n/a\n\n## Variance summary\n\nStatus type: open-decision-closure\n\n## Decision\n\nUse stable text for Workshop Queue summaries.\n\n## SMARTS rationale\n\nStable and measurable.\n\n## Implementation implication\n\nKeep workshop_queue/cli.py stable.\n", encoding="utf-8")
        self._commit("append decision log")
        attempt = _Attempt("academy/P03-record-an-adr/1", 1, self.prepared, "0" * 40, self._head())
        self.assertTrue(_p03_accepted_adr(self.root, attempt, ".codearbiter/decisions/0004-academy-lab.md", ".codearbiter/decisions/decision-log.md"))

    def test_p03_rejects_an_attribution_mismatch_even_when_old_headings_match(self) -> None:
        from academy_engine.checkpoints import _p03_accepted_adr

        subprocess.run(["git", "reset", "--hard", self.prepared], cwd=self.root, check=True, capture_output=True, text=True)
        self._write_valid_evidence("Other Learner")
        self._commit("record mismatched attribution")
        attempt = _Attempt("academy/P03-record-an-adr/1", 1, self.prepared, "0" * 40, self._head())
        self.assertFalse(_p03_accepted_adr(self.root, attempt, ".codearbiter/decisions/0004-academy-lab.md", ".codearbiter/decisions/decision-log.md"))

    def test_p03_log_is_ordered_unique_and_has_no_trailing_content(self) -> None:
        from academy_engine.checkpoints import _git_blob, _p03_parse_log

        prefix = _git_blob(self.root, self.prepared, ".codearbiter/decisions/decision-log.md")
        head = _git_blob(self.root, self.head, ".codearbiter/decisions/decision-log.md")
        self.assertIsNotNone(prefix)
        self.assertIsNotNone(head)
        for mutation in (
            b"\n## Extra section\n",
            b"**Status:** accepted\n",
            b"## DECISION-0004 \xe2\x80\x94 ADR-0004 \xe2\x80\x94 Choose the Workshop Queue summary-format boundary\n",
            b"**Supersedes:** none\n**Date:** 2026-08-04\n",
        ):
            with self.subTest(mutation=mutation[:16]):
                candidate = head + mutation
                self.assertFalse(_p03_parse_log(candidate, prefix, "Ada Learner", "2026-08-04", "Use stable text for Workshop Queue summaries."))

    def test_p03_requires_the_prepared_log_blob_and_strict_adr_structure(self) -> None:
        from academy_engine import checkpoints
        from academy_engine.checkpoints import _p03_accepted_adr

        attempt = _Attempt("academy/P03-record-an-adr/1", 1, self.prepared, "0" * 40, self.head)
        original = checkpoints._git_blob

        def missing_prepared_log(root: Path, ref: str, path: str):
            if ref == self.prepared and path == ".codearbiter/decisions/decision-log.md":
                return None
            return original(root, ref, path)

        with mock.patch("academy_engine.checkpoints._git_blob", side_effect=missing_prepared_log):
            self.assertFalse(checkpoints._p03_accepted_adr(self.root, attempt, ".codearbiter/decisions/0004-academy-lab.md", ".codearbiter/decisions/decision-log.md"))

        adr = original(self.root, self.head, ".codearbiter/decisions/0004-academy-lab.md")
        self.assertIsNotNone(adr)
        self.assertIsNotNone(checkpoints._p03_parse_adr(adr.replace(b"\n", b"\r\n"), "Ada Learner", "2026-08-04"))
        self.assertIsNone(checkpoints._p03_parse_adr(adr + b"\n# Extra heading\n", "Ada Learner", "2026-08-04"))
        self.assertIsNone(checkpoints._p03_parse_adr(adr.replace(b"costs a versioned schema", b"is merely another available format"), "Ada Learner", "2026-08-04"))

    def test_p03_rejects_negated_cost_and_prohibited_log_markers_but_allows_multiline_narrative(self) -> None:
        from academy_engine import checkpoints

        adr = checkpoints._git_blob(self.root, self.head, ".codearbiter/decisions/0004-academy-lab.md")
        prefix = checkpoints._git_blob(self.root, self.prepared, ".codearbiter/decisions/decision-log.md")
        log = checkpoints._git_blob(self.root, self.head, ".codearbiter/decisions/decision-log.md")
        self.assertIsNotNone(adr)
        self.assertIsNotNone(prefix)
        self.assertIsNotNone(log)
        for replacement in (b"structured JSON has no cost", b"structured JSON is without risk"):
            with self.subTest(replacement=replacement):
                candidate = adr.replace(b"costs a versioned schema", replacement)
                self.assertIsNone(checkpoints._p03_parse_adr(candidate, "Ada Learner", "2026-08-04"))
        for marker in (b"Re-evaluation trigger", b"Resolves same-level conflict between"):
            with self.subTest(marker=marker):
                candidate = log.replace(b"Stable and measurable.", b"Stable and measurable. " + marker)
                self.assertFalse(checkpoints._p03_parse_log(candidate, prefix, "Ada Learner", "2026-08-04", "Use stable text for Workshop Queue summaries."))
        multiline = log.replace(b"Stable and measurable.", b"Stable and measurable.\nThis is a second bounded rationale line.")
        self.assertTrue(checkpoints._p03_parse_log(multiline, prefix, "Ada Learner", "2026-08-04", "Use stable text for Workshop Queue summaries."))
        injected_heading = log.replace(b"Stable and measurable.", b"Stable and measurable.\n# Injected heading")
        self.assertFalse(checkpoints._p03_parse_log(injected_heading, prefix, "Ada Learner", "2026-08-04", "Use stable text for Workshop Queue summaries."))

    def test_p03_native_artifact_mutation_matrix_rejects_each_schema_decoy(self) -> None:
        """Keep the brief's native-artifact adversarial cases attached to immutable Git blobs."""
        from academy_engine import checkpoints

        adr = checkpoints._git_blob(self.root, self.head, ".codearbiter/decisions/0004-academy-lab.md")
        prefix = checkpoints._git_blob(self.root, self.prepared, ".codearbiter/decisions/decision-log.md")
        log = checkpoints._git_blob(self.root, self.head, ".codearbiter/decisions/decision-log.md")
        self.assertIsNotNone(adr)
        self.assertIsNotNone(prefix)
        self.assertIsNotNone(log)
        adr_mutations = (
            adr.replace(b"ADR-0004", b"ADR-0005", 1),
            adr.replace(b"status: accepted\n", b"", 1),
            adr.replace(b"status: accepted\n", b"status: accepted\nstatus: accepted\n", 1),
            adr.replace(b"## Status", b"## State", 1),
            adr + b"\n# Duplicate ADR heading\n",
            adr.replace(b"Accepted", b"Proposed", 1),
            adr.replace(b"Use stable text for Workshop Queue summaries.", b"Use stable text for Workshop Queue summaries.\nUse structured JSON for Workshop Queue summaries.", 1),
            adr.replace(b"Use stable text for Workshop Queue summaries.", b"No choice is recorded.", 1),
            adr.replace(b"decided-by: Ada Learner", b"decided-by: 'Ada Learner'", 1),
            adr.replace(b"decided-by: Ada Learner", b"decided-by: |\n  Ada Learner", 1),
        )
        for candidate in adr_mutations:
            with self.subTest(kind="adr"):
                self.assertIsNone(checkpoints._p03_parse_adr(candidate, "Ada Learner", "2026-08-04"))
        log_mutations = (
            log.replace(b"**Date:** 2026-08-04", b"**Date:** 1999-01-01", 1),
            log.replace(b"Use stable text for Workshop Queue summaries.", b"Use structured JSON for Workshop Queue summaries.", 1),
            log.replace(b"**Decided by:** Ada Learner", b"**Decided by:** 'Ada Learner'", 1),
            log.replace(b"## Decision", b"## Decision\n\nUse stable text for Workshop Queue summaries.\n\n## Decision", 1),
        )
        for candidate in log_mutations:
            with self.subTest(kind="log"):
                self.assertFalse(checkpoints._p03_parse_log(candidate, prefix, "Ada Learner", "2026-08-04", "Use stable text for Workshop Queue summaries."))
        self.assertFalse(checkpoints._p03_parse_log(log, prefix + b"rewritten", "Ada Learner", "2026-08-04", "Use stable text for Workshop Queue summaries."))

    def test_p03_real_git_history_mutation_matrix_rejects_noncanonical_evidence(self) -> None:
        """Exercise path/order/cleanliness mutations in real commits, not mocked history."""
        from academy_engine.checkpoints import _p03_accepted_adr

        def reset_with_valid() -> None:
            subprocess.run(["git", "reset", "--hard", self.prepared], cwd=self.root, check=True, capture_output=True, text=True)
            self._write_valid_evidence("Ada Learner")

        def attempt() -> _Attempt:
            return _Attempt("academy/P03-record-an-adr/1", 1, self.prepared, "0" * 40, self._head())

        # The uncommitted lookalike is rejected without creating any learner evidence commit.
        (self.root / ".codearbiter/decisions/0004-academy-lab.md").write_text("lookalike\n", encoding="utf-8")
        self.assertFalse(_p03_accepted_adr(self.root, attempt(), ".codearbiter/decisions/0004-academy-lab.md", ".codearbiter/decisions/decision-log.md"))
        subprocess.run(["git", "reset", "--hard", "HEAD"], cwd=self.root, check=True, capture_output=True, text=True)

        reset_with_valid()
        (self.root / ".codearbiter/decisions/0004-academy-lab.md").rename(self.root / ".codearbiter/decisions/0004-alternate.md")
        self._commit("alternate ADR filename")
        self.assertFalse(_p03_accepted_adr(self.root, attempt(), ".codearbiter/decisions/0004-academy-lab.md", ".codearbiter/decisions/decision-log.md"))

        reset_with_valid()
        (self.root / "generic-governance-event.md").write_text("decoy\n", encoding="utf-8")
        self._commit("generic event decoy")
        self.assertFalse(_p03_accepted_adr(self.root, attempt(), ".codearbiter/decisions/0004-academy-lab.md", ".codearbiter/decisions/decision-log.md"))

        reset_with_valid()
        adr = self.root / ".codearbiter/decisions/0004-academy-lab.md"
        adr_bytes = adr.read_bytes()
        adr.unlink()
        self._commit("log before ADR")
        adr.write_bytes(adr_bytes)
        self._commit("late ADR")
        self.assertFalse(_p03_accepted_adr(self.root, attempt(), ".codearbiter/decisions/0004-academy-lab.md", ".codearbiter/decisions/decision-log.md"))

        reset_with_valid()
        self._commit("valid evidence")
        (self.root / "README.md").write_text("later mutation\n", encoding="utf-8")
        self._commit("extra path")
        self.assertFalse(_p03_accepted_adr(self.root, attempt(), ".codearbiter/decisions/0004-academy-lab.md", ".codearbiter/decisions/decision-log.md"))

        reset_with_valid()
        (self.root / ".codearbiter/decisions/0003-verifier-trust.md").write_text("rewritten ADR-0003\n", encoding="utf-8")
        self._commit("edit ADR-0003")
        self.assertFalse(_p03_accepted_adr(self.root, attempt(), ".codearbiter/decisions/0004-academy-lab.md", ".codearbiter/decisions/decision-log.md"))

        reset_with_valid()
        self._commit("valid evidence")
        subprocess.run(["git", "branch", "p03-merge-side", self.prepared], cwd=self.root, check=True, capture_output=True, text=True)
        subprocess.run(["git", "switch", "p03-merge-side"], cwd=self.root, check=True, capture_output=True, text=True)
        (self.root / "README.md").write_text("side history\n", encoding="utf-8")
        self._commit("side history")
        subprocess.run(["git", "switch", "academy/P03-record-an-adr/1"], cwd=self.root, check=True, capture_output=True, text=True)
        subprocess.run(["git", "merge", "--no-ff", "p03-merge-side", "-m", "merge side history"], cwd=self.root, check=True, capture_output=True, text=True)
        self.assertFalse(_p03_accepted_adr(self.root, attempt(), ".codearbiter/decisions/0004-academy-lab.md", ".codearbiter/decisions/decision-log.md"))

        reset_with_valid()
        self._commit("valid evidence")
        adr.write_text(adr.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        self._commit("later ADR mutation")
        self.assertFalse(_p03_accepted_adr(self.root, attempt(), ".codearbiter/decisions/0004-academy-lab.md", ".codearbiter/decisions/decision-log.md"))

    def test_p03_rejects_a_stale_copied_native_pair_from_a_prior_attempt(self) -> None:
        """A byte-for-byte native pair must still bind to its introducing commit's date."""
        from academy_engine import checkpoints

        adr_path = ".codearbiter/decisions/0004-academy-lab.md"
        log_path = ".codearbiter/decisions/decision-log.md"
        prior_adr = checkpoints._git_blob(self.root, self.head, adr_path)
        prior_log = checkpoints._git_blob(self.root, self.head, log_path)
        self.assertIsNotNone(prior_adr)
        self.assertIsNotNone(prior_log)
        prior_attempt = _Attempt("academy/P03-record-an-adr/1", 1, self.prepared, "0" * 40, self.head)
        self.assertTrue(checkpoints._p03_accepted_adr(self.root, prior_attempt, adr_path, log_path))

        subprocess.run(["git", "reset", "--hard", self.prepared], cwd=self.root, check=True, capture_output=True, text=True)
        (self.root / adr_path).write_bytes(prior_adr)
        (self.root / log_path).write_bytes(prior_log)
        subprocess.run(["git", "add", adr_path, log_path], cwd=self.root, check=True, capture_output=True, text=True)
        environment = os.environ.copy()
        environment["GIT_AUTHOR_DATE"] = "2030-01-02T03:04:05+00:00"
        environment["GIT_COMMITTER_DATE"] = "2030-01-02T03:04:05+00:00"
        subprocess.run(["git", "commit", "-m", "copy prior native pair"], cwd=self.root, env=environment, check=True, capture_output=True, text=True)
        copied_attempt = _Attempt("academy/P03-record-an-adr/1", 1, self.prepared, "0" * 40, self._head())
        self.assertFalse(checkpoints._p03_accepted_adr(self.root, copied_attempt, adr_path, log_path))


class U02OverrideAuditMetricTests(unittest.TestCase):
    """Adversarial direct tests for the private U02 evidence predicate."""

    def setUp(self) -> None:
        self.temp = RetryingTemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _git(self, root: Path, *arguments: str) -> str:
        result = subprocess.run(
            ["git", *arguments], cwd=root, text=True, capture_output=True, check=False
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout.strip()

    def _semantic_context(
        self,
        *,
        gate: str = "safe-training-gate",
        tamper_prefix: bool = False,
        extra_path: bool = False,
        dirty: bool = False,
        audit_packet: bool = False,
        audit_receipt: bool = True,
        metrics_receipt: bool = True,
        override_lines: int = 1,
        audit_packet_name: str = "2026-08-12.md",
        audit_packet_prose_only: bool = False,
    ) -> _SemanticContext:
        root = self.root / f"u02-{len(tuple(self.root.iterdir()))}"
        root.mkdir()
        self._git(root, "init", "-b", "main")
        self._git(root, "config", "user.name", "U02 Fixture")
        self._git(root, "config", "user.email", "u02@example.invalid")

        override_path = root / ".codearbiter" / "overrides.log"
        override_path.parent.mkdir()
        prepared_line = (
            "[2026-08-12T10:00:00+00:00] | BY: u02@example.invalid | "
            "GATE: prior-training-gate | REASON: prepared fixture\n"
        )
        override_path.write_text(prepared_line, encoding="utf-8", newline="\n")
        self._git(root, "add", ".codearbiter/overrides.log")
        self._git(root, "commit", "-m", "base override log")
        self._git(root, "switch", "-c", "academy/U02-override-audit-metrics/1")
        self._git(root, "commit", "--allow-empty", "-m", "academy: prepare U02 attempt 1")
        prepared = self._git(root, "rev-parse", "HEAD")
        base = self._git(root, "rev-parse", "HEAD^")

        self.assertGreaterEqual(override_lines, 1)
        new_lines = [
            "[2026-08-12T10:01:0"
            f"{index}+00:00] | BY: u02@example.invalid | "
            f"GATE: {gate} | REASON: scoped Academy exercise {index}\n"
            for index in range(1, override_lines + 1)
        ]
        final_lines = [prepared_line, *new_lines]
        if tamper_prefix:
            final_lines[0] = final_lines[0].replace("prepared fixture", "rewritten fixture")
        override_path.write_text("".join(final_lines), encoding="utf-8", newline="\n")

        audit_path = root / ".codearbiter" / "reports" / "academy" / "U02-audit.md"
        if audit_receipt:
            audit_path.parent.mkdir(parents=True)
            hashed_lines = final_lines if tamper_prefix else new_lines
            audit_path.write_text(
                "\n".join(hashlib.sha256(line.rstrip("\n").encode("utf-8")).hexdigest() for line in hashed_lines)
                + "\n",
                encoding="utf-8",
                newline="\n",
            )
        metrics_path = audit_path.with_name("U02-metrics.json")
        if metrics_receipt:
            metrics_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "override_count": len(new_lines),
                        "low_confidence_count": 0,
                    },
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
                newline="\n",
            )
        audit_packet_path = root / ".codearbiter" / "audits" / audit_packet_name
        if audit_packet:
            audit_packet_path.parent.mkdir(parents=True)
            audit_packet_path.write_text(
                (
                    "# Academy audit packet\n\n"
                    "## Overrides\n"
                    + "".join(new_lines)
                    if not audit_packet_prose_only
                    else "# Academy audit packet\n\n"
                    + "The override record was: "
                    + new_lines[0]
                ),
                encoding="utf-8",
                newline="\n",
            )
        paths = (".codearbiter/overrides.log",)
        if audit_receipt:
            paths = (*paths, ".codearbiter/reports/academy/U02-audit.md")
        if metrics_receipt:
            paths = (*paths, ".codearbiter/reports/academy/U02-metrics.json")
        if audit_packet:
            paths = (*paths, f".codearbiter/audits/{audit_packet_name}")
        if extra_path:
            (root / "extra.txt").write_text("decoy\n", encoding="utf-8", newline="\n")
            paths = (*paths, "extra.txt")
        self._git(root, "add", "--", *paths)
        self._git(root, "commit", "-m", "record U02 evidence")
        head = self._git(root, "rev-parse", "HEAD")
        if dirty:
            (root / "untracked.txt").write_text("dirty\n", encoding="utf-8", newline="\n")

        return _SemanticContext(
            root,
            _Attempt("academy/U02-override-audit-metrics/1", 1, prepared, base, head),
            Predicate(
                "linked_override_audit_metrics",
                "lab_semantics",
                {
                    "profile": "override_audit_metrics",
                    "overrides": ".codearbiter/overrides.log",
                    "audit": ".codearbiter/reports/academy/U02-audit.md",
                    "metrics": ".codearbiter/reports/academy/U02-metrics.json",
                    "audit_packets": ".codearbiter/audits",
                },
            ),
        )

    def test_u02_rejects_synthetic_audit_and_metrics_receipts(self) -> None:
        """A learner-written receipt must not be accepted as CodeArbiter output."""
        self.assertFalse(_semantic(self._semantic_context(audit_packet=True)))

    def test_u02_accepts_real_override_and_audit_artifacts_without_metrics_receipt(self) -> None:
        """Metrics output is read-only advice, not a fabricated committed receipt."""
        self.assertTrue(
            _semantic(
                self._semantic_context(
                    audit_packet=True, audit_receipt=False, metrics_receipt=False
                )
            )
        )

    def test_u02_checkpoint_definition_loads_the_audit_packet_directory_contract(self) -> None:
        """Catches direct predicate tests bypassing an unregistered checkpoint field."""
        checkpoint = load_checkpoint(
            Path(__file__).parents[1]
            / "academy/checkpoints/U02-override-audit-metrics.json"
        )
        self.assertEqual(
            checkpoint.predicates[0].data["audit_packets"], ".codearbiter/audits"
        )

    def test_u02_rejects_tampered_prefix_wrong_gate_extra_path_and_dirty_worktree(self) -> None:
        cases = {
            "prepared-log-prefix-tampered": {"tamper_prefix": True},
            "wrong-gate": {"gate": "other-gate"},
            "extra-commit-path": {"extra_path": True},
            "dirty-worktree": {"dirty": True},
        }
        for name, arguments in cases.items():
            with self.subTest(name=name):
                self.assertFalse(_semantic(self._semantic_context(audit_packet=True, **arguments)))

    def test_u02_rejects_multiple_otherwise_valid_safe_training_overrides(self) -> None:
        """Catches the lesson's one-override boundary becoming a permissive log batch."""
        self.assertFalse(
            _semantic(self._semantic_context(audit_packet=True, override_lines=2))
        )

    def test_u02_rejects_noncanonical_audit_packet_names_and_prose_only_quotes(self) -> None:
        """A dated CodeArbiter packet quotes the record as an Overrides entry, not prose."""
        cases = {
            "alternate-packet-name": {"audit_packet_name": "override-summary.md"},
            "prose-only-quote": {"audit_packet_prose_only": True},
        }
        for name, arguments in cases.items():
            with self.subTest(name=name):
                self.assertFalse(_semantic(self._semantic_context(audit_packet=True, **arguments)))


class P04NativeDependencyReviewTests(unittest.TestCase):
    """Exercise P04 against immutable candidate blobs and real learner Git history."""

    review_path = ".codearbiter/reports/academy/P04-dependency-review.md"
    lock_path = "requirements.lock"
    wrapper_path = ".codearbiter/reports/academy/P04-approved-dependency.lock.json"

    def setUp(self) -> None:
        self.temp = RetryingTemporaryDirectory()
        self.root = Path(self.temp.name)
        subprocess.run(["git", "init", "-b", "main"], cwd=self.root, check=True, capture_output=True, text=True)
        subprocess.run(["git", "config", "user.name", "Fixture"], cwd=self.root, check=True)
        subprocess.run(["git", "config", "user.email", "fixture@example.invalid"], cwd=self.root, check=True)
        source = Path(__file__).resolve().parents[1] / "academy/candidates/P04-review-a-dependency"
        shutil.copytree(source, self.root / "academy/candidates/P04-review-a-dependency")
        (self.root / "pyproject.toml").write_text("[project]\nname = 'fixture'\nversion = '0'\nrequires-python = '>=3.10'\n", encoding="utf-8")
        (self.root / "README.md").write_text("base\n", encoding="utf-8")
        self._commit("base")
        subprocess.run(["git", "switch", "-c", "academy/P04-review-a-dependency/1"], cwd=self.root, check=True, capture_output=True, text=True)
        self._commit("academy: prepare P04-review-a-dependency attempt 1", empty=True)
        self.prepared = self._head()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _head(self) -> str:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.root, check=True, capture_output=True, text=True).stdout.strip()

    def _commit(self, message: str, *, empty: bool = False, raw_paths: dict[str, bytes] | None = None) -> None:
        subprocess.run(["git", "add", "-A"], cwd=self.root, check=True, capture_output=True, text=True)
        for relative, raw in (raw_paths or {}).items():
            object_id = subprocess.run(
                ["git", "hash-object", "-w", "--stdin"], cwd=self.root, input=raw, check=True, capture_output=True
            ).stdout.decode("ascii").strip()
            subprocess.run(
                ["git", "update-index", "--add", "--cacheinfo", f"100644,{object_id},{relative}"],
                cwd=self.root,
                check=True,
                capture_output=True,
                text=True,
            )
        command = ["git", "commit", "-m", message]
        if empty:
            command.insert(2, "--allow-empty")
        subprocess.run(command, cwd=self.root, check=True, capture_output=True, text=True)

    def _review(self, decision: str) -> str:
        prepared = subprocess.run(
            ["git", "show", f"{self.prepared}:pyproject.toml"],
            cwd=self.root,
            check=True,
            capture_output=True,
        ).stdout
        digest = hashlib.sha256(prepared).hexdigest()
        labels = (
            "# P04 Dependency Review - python-dateutil==2.9.0.post0\nAcademy-Schema-Version: 1\n"
            f"Project-SHA256: {digest}\nCandidate: python-dateutil==2.9.0.post0\n"
            "Candidate-Artifact: python_dateutil-2.9.0.post0-py2.py3-none-any.whl\n"
            "Candidate-SHA256: a8b2bc7bffae282281c8140a97d3aa9c14da0b136dfe83f850eea9a5f7470427\n"
            "Closure-Requirement: six>=1.5\nClosure-Package: six==1.17.0\n"
            "Closure-Artifact: six-1.17.0-py2.py3-none-any.whl\n"
            "Closure-SHA256: 4721f391ed90541fddacab5acf947aa0d3dc7d27b2e1e8eda2be8970586c3274\n"
            "Install-Policy: no-install-in-p04\n\n"
        )
        sections = {
            "Candidate": "python-dateutil==2.9.0.post0 uses python_dateutil-2.9.0.post0-py2.py3-none-any.whl with complete six>=1.5 and six==1.17.0 closure in six-1.17.0-py2.py3-none-any.whl.",
            "Provenance": "PyPI distribution python-dateutil imports dateutil; dateutil/dateutil and benjaminp/six filenames and hashes bind bytes.",
            "License": "Apache-2.0 OR BSD-3-Clause and MIT; python_dateutil-2.9.0.post0.LICENSE ba00f51a0d92823b5a1cde27d8b5b9d2321e67ed8da9bc163eff96d5e17e577e; six-1.17.0.LICENSE 4375ba20e2b9c6c4e7cad2940a628fd90e95cc3d50ee92aae755715d8ba1fbd0; Apache-2.0.txt cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30.",
            "Maintenance": "Frozen 2026-07-31 review snapshot, not current truth.",
            "Known vulnerabilities": "Frozen 2026-07-31 review snapshot, not a guarantee.",
            "Supply chain": "pure-Python universal wheels, no sdist, no resolver-selected artifact, and no install during P04.",
            "Compatibility": "Academy Python 3.10+; Requires-Python !=3.0.*,!=3.1.*,!=3.2.*,>=2.7 and >=2.7, !=3.0.*, !=3.1.*, !=3.2.*.",
            "Alternatives": "Use a bounded datetime.strptime parser with finite formats, length limit, deterministic timezone/default rules, and fail-closed trailing-content behavior.",
            "SMARTS": "| Lens | Bounded stdlib | Two-wheel closure |\n| --- | --- | --- |\n| Scalable | Strong. Finite policy. | Adequate. Broader surface. |\n| Maintainable | Strong. No lifecycle. | Weak. Two packages. |\n| Available | Strong. Offline. | Adequate. Cached bytes. |\n| Reliable | Strong. Fail closed. | Adequate. Broad parser. |\n| Testable | Strong. Small matrix. | Adequate. More behavior. |\n| Securable | Strong. No acquisition. | Weak. Publisher chain. |",
            "Decision": "Bounded stdlib parser is selected.\nDecision: reject" if decision == "reject" else "Broader parsing surface is required; install is deferred.\nDecision: accept",
        }
        return labels + "".join(f"## {name}\n\n{sections[name]}\n\n" for name in sections)

    def _attempt(self) -> _Attempt:
        return _Attempt("academy/P04-review-a-dependency/1", 1, self.prepared, "0" * 40, self._head())

    def _write_review(self, decision: str, *replacements: tuple[str, str]) -> Path:
        """Write a hand-authored learner report whose mutations remain real Git content."""
        text = self._review(decision)
        for old, new in replacements:
            self.assertIn(old, text)
            text = text.replace(old, new, 1)
        review = self.root / self.review_path
        review.parent.mkdir(parents=True, exist_ok=True)
        review.write_text(text, encoding="utf-8")
        return review

    def _reset_to_prepared(self, prepared: str) -> None:
        subprocess.run(["git", "reset", "--hard", prepared], cwd=self.root, check=True, capture_output=True, text=True)
        subprocess.run(["git", "clean", "-fd"], cwd=self.root, check=True, capture_output=True, text=True)
        for relative in (self.review_path, self.lock_path, self.wrapper_path):
            path = self.root / relative
            if path.exists():
                path.unlink()
        self.prepared = prepared

    def test_rejects_any_extra_prepared_candidate_path(self) -> None:
        """Catches a checker that reads only known candidate names and ignores prepared decoys."""
        from academy_engine.checkpoints import _p04_dependency_review

        candidate_root = self.root / "academy/candidates/P04-review-a-dependency"
        for filename in ("NOTICE.txt", "PATENT", "third-wheel.whl"):
            (candidate_root / filename).write_bytes(b"decoy\n")
        self._commit("prepare candidate notice patent and payload decoys")
        self._commit("academy: prepare P04 candidate decoys", empty=True)
        self.prepared = self._head()
        self._write_review("reject")
        self._commit("record P04 rejection")
        self.assertFalse(_p04_dependency_review(self.root, self._attempt(), self.review_path, "pyproject.toml"))

    def test_rejects_report_that_omits_substantive_review_contract_terms(self) -> None:
        """Catches a headings-only parser that accepts vague licensing, snapshot, closure, or fallback claims."""
        from academy_engine.checkpoints import _p04_dependency_review

        original_prepared = self.prepared
        mutations = {
            "license-hash": (
                "ba00f51a0d92823b5a1cde27d8b5b9d2321e67ed8da9bc163eff96d5e17e577e",
                "0" * 64,
            ),
            "maintenance-disclaimer": (
                "Frozen 2026-07-31 review snapshot, not current truth.",
                "Frozen 2026-07-31 review snapshot.",
            ),
            "vulnerability-disclaimer": (
                "Frozen 2026-07-31 review snapshot, not a guarantee.",
                "Frozen 2026-07-31 review snapshot.",
            ),
            "alternative-default-and-trailing": (
                "Use a bounded datetime.strptime parser with finite formats, length limit, deterministic timezone/default rules, and fail-closed trailing-content behavior.",
                "Use a bounded datetime.strptime parser with finite formats, length limit, deterministic timezone rules, and fail-closed behavior.",
            ),
            "candidate-closure": (
                "python-dateutil==2.9.0.post0 uses python_dateutil-2.9.0.post0-py2.py3-none-any.whl with complete six>=1.5 and six==1.17.0 closure in six-1.17.0-py2.py3-none-any.whl.",
                "python-dateutil==2.9.0.post0 with six==1.17.0.",
            ),
            "provenance-filenames": (
                "PyPI distribution python-dateutil imports dateutil; dateutil/dateutil and benjaminp/six filenames and hashes bind bytes.",
                "PyPI distribution python-dateutil imports dateutil; dateutil/dateutil and benjaminp/six hashes bind bytes.",
            ),
        }
        for name, replacement in mutations.items():
            with self.subTest(name=name):
                old, new = replacement
                self._write_review("reject", (old, new))
                self._commit(f"record incomplete P04 review {name}")
                self.assertFalse(_p04_dependency_review(self.root, self._attempt(), self.review_path, "pyproject.toml"))
                self._reset_to_prepared(original_prepared)

    def test_accepts_real_reject_and_two_commit_acceptance_paths(self) -> None:
        from academy_engine.checkpoints import _p04_dependency_review

        review = self.root / self.review_path
        review.parent.mkdir(parents=True)
        review.write_text(self._review("reject"), encoding="utf-8")
        self._commit("record P04 rejection")
        self.assertTrue(_p04_dependency_review(self.root, self._attempt(), self.review_path, "pyproject.toml"))

        subprocess.run(["git", "reset", "--hard", self.prepared], cwd=self.root, check=True, capture_output=True, text=True)
        review.parent.mkdir(parents=True)
        review.write_text(self._review("accept"), encoding="utf-8")
        self._commit("record P04 acceptance")
        (self.root / "pyproject.toml").write_text("[project]\nname = 'fixture'\nversion = '0'\nrequires-python = '>=3.10'\ndependencies = ['python-dateutil==2.9.0.post0']\n", encoding="utf-8")
        (self.root / self.lock_path).write_text("python-dateutil==2.9.0.post0 --hash=sha256:a8b2bc7bffae282281c8140a97d3aa9c14da0b136dfe83f850eea9a5f7470427 # artifact=python_dateutil-2.9.0.post0-py2.py3-none-any.whl\nsix==1.17.0 --hash=sha256:4721f391ed90541fddacab5acf947aa0d3dc7d27b2e1e8eda2be8970586c3274 # artifact=six-1.17.0-py2.py3-none-any.whl\n", encoding="utf-8")
        wrapper = {"schema_version": 1, "name": "python-dateutil", "version": "2.9.0.post0", "artifact": "python_dateutil-2.9.0.post0-py2.py3-none-any.whl", "sha256": "a8b2bc7bffae282281c8140a97d3aa9c14da0b136dfe83f850eea9a5f7470427", "install_policy": "later-only-after-review"}
        target = self.root / self.wrapper_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(json.dumps(wrapper, separators=(",", ":"), ensure_ascii=True).encode("utf-8") + b"\n")
        self._commit("record accepted P04 dependency evidence")
        self.assertTrue(_p04_dependency_review(self.root, self._attempt(), self.review_path, "pyproject.toml"))

    def test_rejects_uncommitted_review_and_extra_history_path(self) -> None:
        from academy_engine.checkpoints import _p04_dependency_review

        review = self.root / self.review_path
        review.parent.mkdir(parents=True)
        review.write_text(self._review("reject"), encoding="utf-8")
        self.assertFalse(_p04_dependency_review(self.root, self._attempt(), self.review_path, "pyproject.toml"))
        self._commit("record P04 rejection")
        (self.root / "README.md").write_text("unexpected\n", encoding="utf-8")
        self._commit("unrelated path")
        self.assertFalse(_p04_dependency_review(self.root, self._attempt(), self.review_path, "pyproject.toml"))

    def test_rejects_stale_label_section_and_closure_report_mutations(self) -> None:
        """Catches committed reports that look native but break a bound header or unique section contract."""
        from academy_engine.checkpoints import _p04_dependency_review

        original_prepared = self.prepared
        prepared_digest = hashlib.sha256(
            subprocess.run(["git", "show", f"{self.prepared}:pyproject.toml"], cwd=self.root, check=True, capture_output=True).stdout
        ).hexdigest()
        mutations = {
            "stale-project-digest": (f"Project-SHA256: {prepared_digest}", "Project-SHA256: " + "0" * 64),
            "unknown-header-label": ("Candidate: python-dateutil==2.9.0.post0", "Candidate-Name: python-dateutil==2.9.0.post0"),
            "unknown-section": ("## Alternatives\n\n", "## Fallback\n\n"),
            "wrong-closure": ("Closure-Requirement: six>=1.5", "Closure-Requirement: six>=9"),
        }
        for name, (old, new) in mutations.items():
            with self.subTest(name=name):
                self._write_review("reject", (old, new))
                self._commit(f"record malformed P04 review {name}")
                self.assertFalse(_p04_dependency_review(self.root, self._attempt(), self.review_path, "pyproject.toml"))
                self._reset_to_prepared(original_prepared)

    def test_rejects_nonblank_duplicate_or_unknown_h2_heading(self) -> None:
        """Catches a heading parser that ignores malformed H2 declarations inside an otherwise valid section."""
        from academy_engine.checkpoints import _p04_dependency_review

        original_prepared = self.prepared
        mutations = {
            "duplicate": ("## Candidate\n\n", "## Candidate\n\n## Candidate\ninjected duplicate\n"),
            "unknown": ("## Candidate\n\n", "## Candidate\n\n## Unreviewed\ninjected unknown\n"),
        }
        for name, (old, new) in mutations.items():
            with self.subTest(name=name):
                self._write_review("reject", (old, new))
                self._commit(f"record malformed nonblank H2 {name}")
                self.assertFalse(_p04_dependency_review(self.root, self._attempt(), self.review_path, "pyproject.toml"))
                self._reset_to_prepared(original_prepared)

    def test_rejects_duplicate_reordered_or_semantically_contradictory_review(self) -> None:
        """Catches native-shaped reports with reordered grammar, truncated SMARTS, or an outcome that contradicts its rationale."""
        from academy_engine.checkpoints import _p04_dependency_review

        original_prepared = self.prepared
        mutations = {
            "duplicate-label": (
                "Install-Policy: no-install-in-p04\n\n",
                "Install-Policy: no-install-in-p04\nCandidate: python-dateutil==2.9.0.post0\n\n",
            ),
            "reordered-label": (
                "Candidate: python-dateutil==2.9.0.post0\nCandidate-Artifact: python_dateutil-2.9.0.post0-py2.py3-none-any.whl\n",
                "Candidate-Artifact: python_dateutil-2.9.0.post0-py2.py3-none-any.whl\nCandidate: python-dateutil==2.9.0.post0\n",
            ),
            "duplicate-section": ("## Candidate\n\n", "## Candidate\n\n## Candidate\n\nduplicate\n\n"),
            "reordered-section": ("## Candidate\n\n", "## Provenance\n\n"),
            "incomplete-smarts": ("| Securable | Strong. No acquisition. | Weak. Publisher chain. |\n", ""),
        }
        for name, (old, new) in mutations.items():
            with self.subTest(name=name):
                self._write_review("reject", (old, new))
                self._commit(f"record contradictory P04 review {name}")
                self.assertFalse(_p04_dependency_review(self.root, self._attempt(), self.review_path, "pyproject.toml"))
                self._reset_to_prepared(original_prepared)

    def test_rejects_contradictory_decision_in_an_otherwise_valid_two_commit_acceptance(self) -> None:
        """Catches an accepted topology whose review still selects the bounded stdlib alternative."""
        from academy_engine.checkpoints import _p04_dependency_review

        self._write_review(
            "accept",
            (
                "Broader parsing surface is required; install is deferred.\nDecision: accept",
                "Bounded stdlib parser is selected. Broader parsing surface is required; install is deferred.\nDecision: accept",
            ),
        )
        self._commit("record contradictory P04 acceptance")
        self._write_acceptance_artifacts()
        self._commit("record otherwise valid P04 adoption")
        self.assertFalse(_p04_dependency_review(self.root, self._attempt(), self.review_path, "pyproject.toml"))

    def test_rejects_isolated_required_report_identity_and_structure_mutations(self) -> None:
        """Catches missing, wrong, extra, filename, and order mutations in a committed otherwise-valid rejection."""
        from academy_engine.checkpoints import _p04_dependency_review

        original_prepared = self.prepared
        mutations = {
            "missing-label": ("Candidate-SHA256: a8b2bc7bffae282281c8140a97d3aa9c14da0b136dfe83f850eea9a5f7470427\n", ""),
            "missing-section": ("## Compatibility\n\n", ""),
            "wrong-candidate": ("Candidate: python-dateutil==2.9.0.post0", "Candidate: python-dateutil==0"),
            "missing-six": ("Closure-Package: six==1.17.0\n", ""),
            "wrong-six": ("Closure-Package: six==1.17.0", "Closure-Package: six==0"),
            "extra-six": ("Install-Policy: no-install-in-p04\n\n", "Install-Policy: no-install-in-p04\nClosure-Package: six==1.17.1\n\n"),
            "candidate-filename": ("python_dateutil-2.9.0.post0-py2.py3-none-any.whl", "python_dateutil-other.whl"),
            "closure-filename": ("six-1.17.0-py2.py3-none-any.whl", "six-other.whl"),
            "label-order": (
                "Candidate: python-dateutil==2.9.0.post0\nCandidate-Artifact: python_dateutil-2.9.0.post0-py2.py3-none-any.whl\n",
                "Candidate-Artifact: python_dateutil-2.9.0.post0-py2.py3-none-any.whl\nCandidate: python-dateutil==2.9.0.post0\n",
            ),
        }
        for name, (old, new) in mutations.items():
            self._reset_to_prepared(original_prepared)
            with self.subTest(name=name):
                self._write_review("reject", (old, new))
                self._commit(f"record isolated malformed P04 {name}")
                self.assertFalse(_p04_dependency_review(self.root, self._attempt(), self.review_path, "pyproject.toml"))

    def test_rejects_review_amended_after_a_valid_adoption(self) -> None:
        """Catches an actual amend that folds a later review edit into an otherwise valid adoption commit."""
        from academy_engine.checkpoints import _p04_dependency_review

        review = self._write_review("accept")
        self._commit("record P04 acceptance")
        self._write_acceptance_artifacts()
        self._commit("record valid P04 adoption")
        self.assertTrue(_p04_dependency_review(self.root, self._attempt(), self.review_path, "pyproject.toml"))
        changed = review.read_text(encoding="utf-8").replace("Strong. Finite policy.", "Strong. Bounded policy.", 1)
        review.write_text(changed, encoding="utf-8")
        subprocess.run(["git", "add", self.review_path], cwd=self.root, check=True, capture_output=True, text=True)
        subprocess.run(["git", "commit", "--amend", "--no-edit"], cwd=self.root, check=True, capture_output=True, text=True)
        self.assertFalse(_p04_dependency_review(self.root, self._attempt(), self.review_path, "pyproject.toml"))

    def _write_acceptance_artifacts(self, *, lock: bytes | None = None, wrapper: bytes | None = None) -> None:
        (self.root / "pyproject.toml").write_text(
            "[project]\nname = 'fixture'\nversion = '0'\nrequires-python = '>=3.10'\ndependencies = ['python-dateutil==2.9.0.post0']\n",
            encoding="utf-8",
        )
        (self.root / self.lock_path).write_bytes(lock or (
            b"python-dateutil==2.9.0.post0 --hash=sha256:a8b2bc7bffae282281c8140a97d3aa9c14da0b136dfe83f850eea9a5f7470427 # artifact=python_dateutil-2.9.0.post0-py2.py3-none-any.whl\n"
            b"six==1.17.0 --hash=sha256:4721f391ed90541fddacab5acf947aa0d3dc7d27b2e1e8eda2be8970586c3274 # artifact=six-1.17.0-py2.py3-none-any.whl\n"
        ))
        target = self.root / self.wrapper_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(wrapper or (
            b'{"schema_version":1,"name":"python-dateutil","version":"2.9.0.post0","artifact":"python_dateutil-2.9.0.post0-py2.py3-none-any.whl","sha256":"a8b2bc7bffae282281c8140a97d3aa9c14da0b136dfe83f850eea9a5f7470427","install_policy":"later-only-after-review"}\n'
        ))

    def test_rejects_same_commit_adoption_and_prior_touch_revert(self) -> None:
        """Catches adoption smuggled into review or a lock touched before review and later removed."""
        from academy_engine.checkpoints import _p04_dependency_review

        self._write_review("accept")
        self._write_acceptance_artifacts()
        self._commit("record review and adoption together")
        self.assertFalse(_p04_dependency_review(self.root, self._attempt(), self.review_path, "pyproject.toml"))

        self._reset_to_prepared(self.prepared)
        (self.root / self.lock_path).write_text("temporary\n", encoding="utf-8")
        self._commit("touch lock before review")
        (self.root / self.lock_path).unlink()
        self._commit("revert lock before review")
        self._write_review("reject")
        self._commit("record P04 rejection")
        self.assertFalse(_p04_dependency_review(self.root, self._attempt(), self.review_path, "pyproject.toml"))

    def test_rejects_wrong_accepted_lock_wrapper_and_rejected_project_drift(self) -> None:
        """Catches acceptance artifacts that differ by bytes and rejection that later changes project state."""
        from academy_engine.checkpoints import _p04_dependency_review

        original_prepared = self.prepared
        cases = {
            "wrong-lock": (b"python-dateutil==2.9.0.post0\n", None),
            "wrong-wrapper": (None, b'{"schema_version":2}\n'),
        }
        for name, (lock, wrapper) in cases.items():
            with self.subTest(name=name):
                self._write_review("accept")
                self._commit("record P04 acceptance")
                self._write_acceptance_artifacts(lock=lock, wrapper=wrapper)
                self._commit(f"record {name} P04 adoption")
                self.assertFalse(_p04_dependency_review(self.root, self._attempt(), self.review_path, "pyproject.toml"))
                self._reset_to_prepared(original_prepared)

        self._write_review("reject")
        self._commit("record P04 rejection")
        (self.root / "pyproject.toml").write_text(
            "[project]\nname = 'fixture'\nversion = '0'\nrequires-python = '>=3.10'\ndependencies = ['python-dateutil==2.9.0.post0']\n",
            encoding="utf-8",
        )
        self._commit("drift rejected project")
        self.assertFalse(_p04_dependency_review(self.root, self._attempt(), self.review_path, "pyproject.toml"))

    def test_rejects_manifest_touch_revert_review_after_adoption_and_merge_history(self) -> None:
        """Catches forbidden pre-review candidate changes and history that is not a linear review then adoption proof."""
        from academy_engine.checkpoints import _p04_dependency_review

        original_prepared = self.prepared
        manifest = self.root / "academy/candidates/P04-review-a-dependency/candidate-set.json"
        original_manifest = manifest.read_bytes()
        manifest.write_bytes(original_manifest + b" ")
        self._commit("touch candidate manifest before review")
        manifest.write_bytes(original_manifest)
        self._commit("revert candidate manifest before review")
        self._write_review("reject")
        self._commit("record P04 rejection")
        self.assertFalse(_p04_dependency_review(self.root, self._attempt(), self.review_path, "pyproject.toml"))
        self._reset_to_prepared(original_prepared)

        self._write_acceptance_artifacts()
        self._commit("adopt before review")
        self._write_review("accept")
        self._commit("review after adoption")
        self.assertFalse(_p04_dependency_review(self.root, self._attempt(), self.review_path, "pyproject.toml"))
        self._reset_to_prepared(original_prepared)

        subprocess.run(["git", "switch", "-c", "p04-side", original_prepared], cwd=self.root, check=True, capture_output=True, text=True)
        (self.root / "README.md").write_text("side\n", encoding="utf-8")
        self._commit("side change")
        subprocess.run(["git", "switch", "academy/P04-review-a-dependency/1"], cwd=self.root, check=True, capture_output=True, text=True)
        self._write_review("reject")
        self._commit("record P04 rejection")
        subprocess.run(["git", "merge", "--no-ff", "p04-side", "-m", "merge side"], cwd=self.root, check=True, capture_output=True, text=True)
        self.assertFalse(_p04_dependency_review(self.root, self._attempt(), self.review_path, "pyproject.toml"))

    def test_rejects_lock_variants_and_partial_or_split_acceptance(self) -> None:
        """Catches lock-file variants and acceptance evidence that is incomplete or split across commits."""
        from academy_engine.checkpoints import _p04_dependency_review

        original_prepared = self.prepared
        canonical_lock = (
            b"python-dateutil==2.9.0.post0 --hash=sha256:a8b2bc7bffae282281c8140a97d3aa9c14da0b136dfe83f850eea9a5f7470427 # artifact=python_dateutil-2.9.0.post0-py2.py3-none-any.whl\n"
            b"six==1.17.0 --hash=sha256:4721f391ed90541fddacab5acf947aa0d3dc7d27b2e1e8eda2be8970586c3274 # artifact=six-1.17.0-py2.py3-none-any.whl\n"
        )
        variants = {
            "crlf": canonical_lock.replace(b"\n", b"\r\n"),
            "no-final-lf": canonical_lock.rstrip(b"\n"),
            "index": b"--index-url https://invalid.example\n" + canonical_lock,
            "editable": b"-e .\n" + canonical_lock,
            "marker": canonical_lock.replace(b"six==1.17.0", b"six==1.17.0 ; python_version >= '3.10'"),
            "alternate-hash": canonical_lock.replace(b"a8b2bc", b"b8b2bc"),
            "extra-dependency": canonical_lock + b"example==1 --hash=sha256:" + b"0" * 64 + b"\n",
            "reordered": canonical_lock.splitlines(keepends=True)[1] + canonical_lock.splitlines(keepends=True)[0],
        }
        for name, lock in variants.items():
            self._reset_to_prepared(original_prepared)
            with self.subTest(name=name):
                self._write_review("accept")
                self._commit("record P04 acceptance")
                self._write_acceptance_artifacts(lock=lock)
                self._commit(f"record {name} lock", raw_paths={self.lock_path: lock})
                committed_lock = subprocess.run(
                    ["git", "show", f"HEAD:{self.lock_path}"], cwd=self.root, check=True, capture_output=True
                ).stdout
                self.assertEqual(committed_lock, lock)
                self.assertFalse(_p04_dependency_review(self.root, self._attempt(), self.review_path, "pyproject.toml"))

        self._reset_to_prepared(original_prepared)
        self._write_review("accept")
        self._commit("record P04 acceptance")
        (self.root / "pyproject.toml").write_text(
            "[project]\nname = 'fixture'\nversion = '0'\nrequires-python = '>=3.10'\ndependencies = ['python-dateutil==2.9.0.post0']\n",
            encoding="utf-8",
        )
        self._commit("partial adoption")
        self.assertFalse(_p04_dependency_review(self.root, self._attempt(), self.review_path, "pyproject.toml"))
        (self.root / self.lock_path).write_bytes(canonical_lock)
        target = self.root / self.wrapper_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b'{"schema_version":1,"name":"python-dateutil","version":"2.9.0.post0","artifact":"python_dateutil-2.9.0.post0-py2.py3-none-any.whl","sha256":"a8b2bc7bffae282281c8140a97d3aa9c14da0b136dfe83f850eea9a5f7470427","install_policy":"later-only-after-review"}\n')
        self._commit("split remaining adoption")
        self.assertFalse(_p04_dependency_review(self.root, self._attempt(), self.review_path, "pyproject.toml"))

    def test_rejects_wrapper_variants_alone_and_rejected_lock_drift(self) -> None:
        """Catches a direct-candidate wrapper used alone or mutated despite a native-looking JSON shape."""
        from academy_engine.checkpoints import _p04_dependency_review

        original_prepared = self.prepared
        canonical_wrapper = b'{"schema_version":1,"name":"python-dateutil","version":"2.9.0.post0","artifact":"python_dateutil-2.9.0.post0-py2.py3-none-any.whl","sha256":"a8b2bc7bffae282281c8140a97d3aa9c14da0b136dfe83f850eea9a5f7470427","install_policy":"later-only-after-review"}\n'
        variants = {
            "policy": canonical_wrapper.replace(b"later-only-after-review", b"install-now"),
            "key": canonical_wrapper.replace(b'"schema_version"', b'"schema"'),
            "order": b'{"name":"python-dateutil","schema_version":1,"version":"2.9.0.post0","artifact":"python_dateutil-2.9.0.post0-py2.py3-none-any.whl","sha256":"a8b2bc7bffae282281c8140a97d3aa9c14da0b136dfe83f850eea9a5f7470427","install_policy":"later-only-after-review"}\n',
            "newline": canonical_wrapper.rstrip(b"\n"),
        }
        for name, wrapper in variants.items():
            self._reset_to_prepared(original_prepared)
            with self.subTest(name=name):
                self._write_review("accept")
                self._commit("record P04 acceptance")
                self._write_acceptance_artifacts(wrapper=wrapper)
                self._commit(f"record {name} wrapper")
                self.assertFalse(_p04_dependency_review(self.root, self._attempt(), self.review_path, "pyproject.toml"))

        self._reset_to_prepared(original_prepared)
        self._write_review("accept")
        self._commit("record P04 acceptance")
        target = self.root / self.wrapper_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(canonical_wrapper)
        self._commit("wrapper-only adoption")
        self.assertFalse(_p04_dependency_review(self.root, self._attempt(), self.review_path, "pyproject.toml"))
        self._reset_to_prepared(original_prepared)

        self._write_review("reject")
        self._commit("record P04 rejection")
        (self.root / self.lock_path).write_text("drift\n", encoding="utf-8")
        self._commit("drift rejected lock")
        self.assertFalse(_p04_dependency_review(self.root, self._attempt(), self.review_path, "pyproject.toml"))


class U07CapstoneSemanticTests(unittest.TestCase):
    """Exercise bounded feature artifacts without claiming a hosted PR occurred."""

    spec_path = ".codearbiter/specs/capstone.md"
    plan_path = ".codearbiter/plans/capstone.md"
    code_path = "workshop_queue/service.py"
    test_path = "tests/test_service.py"

    def setUp(self) -> None:
        self.temp = RetryingTemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / ".codearbiter").mkdir()
        (self.root / ".codearbiter" / "CONTEXT.md").write_text("# Capstone fixture\n", encoding="utf-8")
        source = Path(__file__).resolve().parents[1]
        shutil.copytree(source / "workshop_queue", self.root / "workshop_queue")
        shutil.copytree(source / "tests", self.root / "tests")
        subprocess.run(["git", "init", "-b", "main"], cwd=self.root, check=True, capture_output=True, text=True)
        subprocess.run(["git", "config", "user.name", "Academy Learner"], cwd=self.root, check=True)
        subprocess.run(["git", "config", "user.email", "learner@example.invalid"], cwd=self.root, check=True)
        subprocess.run(["git", "remote", "add", "origin", "https://github.com/academy-learner/arbiter-academy.git"], cwd=self.root, check=True)
        subprocess.run(["git", "remote", "add", "upstream", "https://github.com/arbiterForge/arbiter-academy.git"], cwd=self.root, check=True)
        subprocess.run(["git", "remote", "set-url", "--push", "upstream", "DISABLED"], cwd=self.root, check=True)
        self._commit("base")
        from academy_engine.u07_fixture import stage_u07_fixture

        scenario_source = self.root / "academy" / "scenarios" / "U07-capstone" / "files" / "scenario.json"
        scenario_source.parent.mkdir(parents=True)
        scenario_source.write_text(
            '{"schema_version":1,"lab_id":"U07-capstone","operation":"capstone_terminal_state","target":"workshop_queue/service.py","starting_condition":"terminal-status-not-implemented"}\n',
            encoding="utf-8",
        )
        self._commit("add U07 scenario source")
        subprocess.run(["git", "switch", "-c", "academy/U07-capstone/1"], cwd=self.root, check=True, capture_output=True, text=True)
        base = self._head()
        scenario = self.root / "training_scenarios/U07-capstone.json"
        scenario.parent.mkdir(parents=True)
        scenario.write_bytes(scenario_source.read_bytes())
        stage_u07_fixture(self.root, base=base)
        self._commit("academy: prepare U07-capstone attempt 1")
        self.prepared = self._head()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _head(self) -> str:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.root, check=True, capture_output=True, text=True).stdout.strip()

    def _commit(self, message: str, *, empty: bool = False) -> str:
        subprocess.run(["git", "add", "-A"], cwd=self.root, check=True, capture_output=True, text=True)
        command = ["git", "commit", "-m", message]
        if empty:
            command.insert(2, "--allow-empty")
        subprocess.run(command, cwd=self.root, check=True, capture_output=True, text=True)
        return self._head()

    def _write(self, relative: str, text: str) -> None:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")

    def _context(self) -> _SemanticContext:
        return _SemanticContext(
            self.root,
            _Attempt("academy/U07-capstone/1", 1, self.prepared, self.prepared, self._head()),
            Predicate(
                "feature_capstone_range",
                "lab_semantics",
                {
                    "profile": "feature_capstone",
                    "code": self.code_path,
                    "test": self.test_path,
                },
            ),
        )

    def _write_honest_history(self, *, extra_implementation_path: bool = False) -> None:
        self._write(self.spec_path, "# Reject control characters\n\n## Problem\n\nTicket resolution accepts control characters.\n\n## Acceptance criteria\n\n- Resolution rejects newline, tab, and DEL control characters.\n")
        self._write(self.plan_path, "# Reject control characters\n\n## Plan\n\n1. Write the focused resolution regression.\n2. Change the service.\n\n## Verification\n\n`python -m unittest tests.test_service`\n")
        self._commit("record capstone scope")

        prepared_test = (self.root / self.test_path).read_text(encoding="utf-8")
        start = prepared_test.index("    def test_u07_prepared_resolution_control_is_accepted")
        end = prepared_test.index("\n\nif __name__ == \"__main__\":", start)
        self._write(self.test_path, prepared_test[:start] + "    def test_u07_rejects_control_characters_in_resolution(self) -> None:\n        claimed = claim_ticket([open_ticket(\"RQ-U07\")], \"RQ-U07\", \"Sam\", fixed_now())\n        for resolution in (\"done\\nagain\", \"done\\tagain\", \"done\\x7fagain\"):\n            with self.subTest(resolution=repr(resolution)):\n                with self.assertRaisesRegex(ValueError, \"control characters\"):\n                    complete_ticket(claimed, \"RQ-U07\", resolution, fixed_now())\n" + prepared_test[end:])
        self._commit("test capstone terminal state")

        service = (self.root / self.code_path).read_text(encoding="utf-8")
        needle = '            if not resolution.strip():\n                raise ValueError("resolution must be non-empty")\n'
        self._write(self.code_path, service.replace(needle, needle + '            if any(ord(character) < 32 or ord(character) == 127 for character in resolution):\n                raise ValueError("resolution must not contain control characters")\n', 1))
        if extra_implementation_path:
            self._write("README.md", "unrelated\n")
        candidate = self._commit("implement capstone terminal state")

    def test_accepts_feature_history_without_an_adr_or_pr_receipt(self) -> None:
        self._write_honest_history()
        self.assertTrue(_semantic(self._context()))

    def test_rejects_implementation_commit_with_an_unrelated_path(self) -> None:
        self._write_honest_history(extra_implementation_path=True)
        self.assertFalse(_semantic(self._context()))

    def test_rejects_feature_documents_with_different_slugs(self) -> None:
        self.plan_path = ".codearbiter/plans/another-feature.md"
        self._write_honest_history()
        self.assertFalse(_semantic(self._context()))

    def test_rejects_each_learner_controlled_runtime_probe_timeout(self) -> None:
        self._write_honest_history()
        original_run = subprocess.run
        for target in (("-m", "unittest"), ("-c",)):
            def timeout_target(command, *args, **kwargs):
                if tuple(command[1 : 1 + len(target)]) == target:
                    raise subprocess.TimeoutExpired(command, 1)
                return original_run(command, *args, **kwargs)

            with self.subTest(target=target), mock.patch(
                "academy_engine.checkpoints.subprocess.run", side_effect=timeout_target
            ):
                self.assertFalse(_semantic(self._context()))
