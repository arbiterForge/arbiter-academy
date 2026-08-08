from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


SOURCE = Path(__file__).resolve().parents[1]


def git(root: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments], cwd=root, check=True, capture_output=True, text=True, encoding="utf-8"
    )
    return result.stdout.strip()


def baseline_blob(path: str) -> bytes:
    return subprocess.run(
        ["git", "show", f"b0dc9e5:{path}"],
        cwd=SOURCE,
        check=True,
        capture_output=True,
    ).stdout


class P05FixtureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "learner"
        self.root.mkdir()
        shutil.copyfile(SOURCE / "pyproject.toml", self.root / "pyproject.toml")
        for relative in ("workshop_queue", "tests", "academy"):
            shutil.copytree(
                SOURCE / relative,
                self.root / relative,
                ignore=shutil.ignore_patterns("__pycache__"),
            )
        for relative in (
            "workshop_queue/model.py",
            "workshop_queue/service.py",
            "workshop_queue/cli.py",
            "tests/test_cli.py",
        ):
            (self.root / relative).write_bytes(baseline_blob(relative))
        git(self.root, "init", "-b", "main")
        git(self.root, "config", "user.name", "P05 Fixture")
        git(self.root, "config", "user.email", "p05-fixture@example.invalid")
        git(self.root, "add", ".")
        git(self.root, "commit", "-m", "base")
        self.base = git(self.root, "rev-parse", "HEAD")

    def test_stage_creates_the_exact_prepared_defect_and_validates_committed_blobs(self) -> None:
        specification = importlib.util.find_spec("academy_engine.p05_fixture")
        self.assertIsNotNone(specification, "P05 requires its trusted prepared-fixture module")
        from academy_engine.p05_fixture import (
            P05_BLOCKED_TICKET_ID,
            P05_BLOCKED_TICKET_REASON,
            stage_p05_fixture,
            validate_p05_fixture,
        )

        git(self.root, "switch", "-c", "academy/P05-checkpoint-remediation/1", self.base)
        staged = stage_p05_fixture(self.root, base=self.base)
        self.assertEqual(
            staged,
            (
                "tests/test_cli.py",
                "workshop_queue/cli.py",
                "workshop_queue/model.py",
                "workshop_queue/service.py",
            ),
        )
        scenario = self.root / "training_scenarios/P05-checkpoint-remediation.json"
        scenario.parent.mkdir(parents=True)
        source = self.root / "academy/scenarios/P05-checkpoint-remediation/files/scenario.json"
        shutil.copyfile(source, scenario)
        git(self.root, "add", "training_scenarios/P05-checkpoint-remediation.json", *staged)
        git(self.root, "commit", "-m", "academy: prepare P05-checkpoint-remediation attempt 1")
        prepared = git(self.root, "rev-parse", "HEAD")

        self.assertEqual(
            tuple(git(self.root, "diff-tree", "--no-commit-id", "--name-only", "-r", prepared).splitlines()),
            (
                "tests/test_cli.py",
                "training_scenarios/P05-checkpoint-remediation.json",
                "workshop_queue/cli.py",
                "workshop_queue/model.py",
                "workshop_queue/service.py",
            ),
        )
        self.assertTrue(validate_p05_fixture(self.root, prepared))

        fixture = self.root / "data" / "p05-tickets.json"
        fixture.parent.mkdir()
        test = subprocess.run(
            [
                "python",
                "-m",
                "unittest",
                "tests.test_cli.WorkshopQueueCliTests.test_p05_prepared_blocked_ticket_persists_before_summary_defect",
                "-v",
            ],
            cwd=self.root,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )
        self.assertEqual(test.returncode, 0, test.stderr)
        self.assertIn(P05_BLOCKED_TICKET_REASON, (self.root / "tests/test_cli.py").read_text(encoding="utf-8"))

    def test_validator_rejects_a_correct_unresolved_summary(self) -> None:
        specification = importlib.util.find_spec("academy_engine.p05_fixture")
        self.assertIsNotNone(specification, "P05 requires its trusted prepared-fixture module")
        from academy_engine.p05_fixture import stage_p05_fixture, validate_p05_fixture

        git(self.root, "switch", "-c", "academy/P05-checkpoint-remediation/1", self.base)
        staged = stage_p05_fixture(self.root, base=self.base)
        cli = self.root / "workshop_queue/cli.py"
        cli.write_text(
            cli.read_text(encoding="utf-8").replace(
                "sum(ticket.status in {TicketStatus.OPEN, TicketStatus.CLAIMED} for ticket in tickets)",
                "sum(ticket.status is not TicketStatus.COMPLETED for ticket in tickets)",
            ),
            encoding="utf-8",
        )
        scenario = self.root / "training_scenarios/P05-checkpoint-remediation.json"
        scenario.parent.mkdir(parents=True)
        shutil.copyfile(
            self.root / "academy/scenarios/P05-checkpoint-remediation/files/scenario.json", scenario
        )
        git(self.root, "add", "training_scenarios/P05-checkpoint-remediation.json", *staged)
        git(self.root, "commit", "-m", "academy: prepare P05-checkpoint-remediation attempt 1")

        self.assertFalse(validate_p05_fixture(self.root, git(self.root, "rev-parse", "HEAD")))

    def test_validator_rejects_ast_valid_comment_and_noop_lookalikes(self) -> None:
        """The prepared fixture must contain executable contracts, not token bait."""
        from academy_engine.p05_fixture import stage_p05_fixture, validate_p05_fixture

        git(self.root, "switch", "-c", "academy/P05-checkpoint-remediation/1", self.base)
        staged = stage_p05_fixture(self.root, base=self.base)
        test_path = self.root / "tests/test_cli.py"
        text = test_path.read_text(encoding="utf-8")
        start = text.index("    def test_p05_prepared_blocked_ticket_persists_before_summary_defect")
        end = text.index("\n\nif __name__", start)
        impostor = '''    def test_p05_prepared_blocked_ticket_persists_before_summary_defect(self) -> None:
        """RQ-105 Venue access is awaiting facilities clearance.
        self.run_cli(\"claim\", \"RQ-105\")
        self.run_cli(\"block\", \"RQ-105\")
        self.run_cli(\"report\", \"--format\", \"json\")
        [\"blocked\"], 1; [\"unresolved\"], 0
        """
        pass'''
        test_path.write_text(text[:start] + impostor + text[end:], encoding="utf-8")
        model_path = self.root / "workshop_queue/model.py"
        model = model_path.read_text(encoding="utf-8")
        model_path.write_text(
            model.replace('    BLOCKED = "blocked"', '    # BLOCKED = "blocked"'),
            encoding="utf-8",
        )
        scenario = self.root / "training_scenarios/P05-checkpoint-remediation.json"
        scenario.parent.mkdir(parents=True)
        shutil.copyfile(self.root / "academy/scenarios/P05-checkpoint-remediation/files/scenario.json", scenario)
        git(self.root, "add", "training_scenarios/P05-checkpoint-remediation.json", *staged)
        git(self.root, "commit", "-m", "academy: forge P05 fixture lookalike")

        self.assertFalse(validate_p05_fixture(self.root, git(self.root, "rev-parse", "HEAD")))

    def test_validator_rejects_noop_lifecycle_calls_and_constant_assertions(self) -> None:
        from academy_engine.p05_fixture import stage_p05_fixture, validate_p05_fixture

        git(self.root, "switch", "-c", "academy/P05-checkpoint-remediation/1", self.base)
        staged = stage_p05_fixture(self.root, base=self.base)
        test_path = self.root / "tests/test_cli.py"
        text = test_path.read_text(encoding="utf-8")
        start = text.index("    def test_p05_prepared_blocked_ticket_persists_before_summary_defect")
        end = text.index("\n\nif __name__", start)
        impostor = '''    def test_p05_prepared_blocked_ticket_persists_before_summary_defect(self) -> None:
        claim_result = self.run_cli("claim", "RQ-105", "--volunteer", "Sam")
        block_result = self.run_cli("block", "RQ-105", "--reason", "Venue access is awaiting facilities clearance")
        report_result = self.run_cli("report", "--format", "json")
        list_result = self.run_cli("list", "--format", "json")
        ("blocked", "unresolved", "blocked_at", "blocked_reason", "RQ-105", "Venue access is awaiting facilities clearance")
        self.assertEqual(1, 1)
        self.assertEqual(0, 0)'''
        test_path.write_text(text[:start] + impostor + text[end:], encoding="utf-8")
        scenario = self.root / "training_scenarios/P05-checkpoint-remediation.json"
        scenario.parent.mkdir(parents=True)
        shutil.copyfile(self.root / "academy/scenarios/P05-checkpoint-remediation/files/scenario.json", scenario)
        git(self.root, "add", "training_scenarios/P05-checkpoint-remediation.json", *staged)
        git(self.root, "commit", "-m", "academy: forge P05 noop lifecycle")

        self.assertFalse(validate_p05_fixture(self.root, git(self.root, "rev-parse", "HEAD")))

    def test_validator_rejects_noop_service_with_blocked_tokens(self) -> None:
        """A service function must transition and persist; names and keywords are insufficient."""
        from academy_engine.p05_fixture import stage_p05_fixture, validate_p05_fixture

        git(self.root, "switch", "-c", "academy/P05-checkpoint-remediation/1", self.base)
        staged = stage_p05_fixture(self.root, base=self.base)
        service_path = self.root / "workshop_queue/service.py"
        service = service_path.read_text(encoding="utf-8")
        start = service.index("def block_ticket(")
        service_path.write_text(
            service[:start]
            + '''def block_ticket(tickets: Sequence[Ticket], ticket_id: str, reason: str, now: datetime) -> list[Ticket]:
    ticket = tickets[0]
    TicketStatus.BLOCKED
    dict(status=ticket.status, blocked_at=now, blocked_reason=reason)
    return tickets
''',
            encoding="utf-8",
        )
        scenario = self.root / "training_scenarios/P05-checkpoint-remediation.json"
        scenario.parent.mkdir(parents=True)
        shutil.copyfile(self.root / "academy/scenarios/P05-checkpoint-remediation/files/scenario.json", scenario)
        git(self.root, "add", "training_scenarios/P05-checkpoint-remediation.json", *staged)
        git(self.root, "commit", "-m", "academy: forge P05 noop service")

        self.assertFalse(validate_p05_fixture(self.root, git(self.root, "rev-parse", "HEAD")))

    def test_validator_rejects_missing_fixture_setup_before_lifecycle_calls(self) -> None:
        from academy_engine.p05_fixture import stage_p05_fixture, validate_p05_fixture

        git(self.root, "switch", "-c", "academy/P05-checkpoint-remediation/1", self.base)
        staged = stage_p05_fixture(self.root, base=self.base)
        test_path = self.root / "tests/test_cli.py"
        text = test_path.read_text(encoding="utf-8")
        setup = (
            '        tickets = json.loads(self.fixture.read_text(encoding="utf-8"))\n'
            '        tickets[0]["id"] = "RQ-105"\n'
            '        tickets[0]["title"] = "Confirm venue access"\n'
            '        self.fixture.write_text(json.dumps(tickets), encoding="utf-8")\n'
        )
        self.assertIn(setup, text)
        test_path.write_text(text.replace(setup, ""), encoding="utf-8")
        scenario = self.root / "training_scenarios/P05-checkpoint-remediation.json"
        scenario.parent.mkdir(parents=True)
        shutil.copyfile(self.root / "academy/scenarios/P05-checkpoint-remediation/files/scenario.json", scenario)
        git(self.root, "add", "training_scenarios/P05-checkpoint-remediation.json", *staged)
        git(self.root, "commit", "-m", "academy: forge P05 missing setup")

        self.assertFalse(validate_p05_fixture(self.root, git(self.root, "rev-parse", "HEAD")))

    def test_validator_rejects_rebound_tickets_after_unrelated_fixture_read(self) -> None:
        from academy_engine.p05_fixture import stage_p05_fixture, validate_p05_fixture

        git(self.root, "switch", "-c", "academy/P05-checkpoint-remediation/1", self.base)
        staged = stage_p05_fixture(self.root, base=self.base)
        test_path = self.root / "tests/test_cli.py"
        text = test_path.read_text(encoding="utf-8")
        source = '        tickets = json.loads(self.fixture.read_text(encoding="utf-8"))\n'
        forged = (
            '        source = json.loads(self.fixture.read_text(encoding="utf-8"))\n'
            '        tickets = []\n'
        )
        self.assertIn(source, text)
        test_path.write_text(text.replace(source, forged), encoding="utf-8")
        scenario = self.root / "training_scenarios/P05-checkpoint-remediation.json"
        scenario.parent.mkdir(parents=True)
        shutil.copyfile(self.root / "academy/scenarios/P05-checkpoint-remediation/files/scenario.json", scenario)
        git(self.root, "add", "training_scenarios/P05-checkpoint-remediation.json", *staged)
        git(self.root, "commit", "-m", "academy: forge P05 rebound setup")

        self.assertFalse(validate_p05_fixture(self.root, git(self.root, "rev-parse", "HEAD")))


if __name__ == "__main__":
    unittest.main()
