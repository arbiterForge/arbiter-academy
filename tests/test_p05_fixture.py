from __future__ import annotations

import importlib.util
import json
import errno
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests._temporary import RetryingTemporaryDirectory


SOURCE = Path(__file__).resolve().parents[1]
P05_ADR_PATH = ".codearbiter/decisions/0005-terminal-blocked-ticket-lifecycle.md"
P05_DECISION_LOG_PATH = ".codearbiter/decisions/decision-log.md"
P05_ADR_TITLE = "Extend the immutable ticket state machine with terminal blocked tickets"


class P05FixtureCleanupTests(unittest.TestCase):
    def test_real_git_p05_fixture_retries_transient_git_cleanup_races(self) -> None:
        """Catches transient Git pack-file teardown races escaping the P05 fixture."""
        case = P05FixtureTests("test_stage_authors_accepted_adr_0005_and_appends_decision_0005")
        case.setUp()
        base_cleanup = tempfile.TemporaryDirectory.cleanup
        transient = OSError(errno.ENOTEMPTY, "directory not empty")
        try:
            with patch.object(
                tempfile.TemporaryDirectory,
                "cleanup",
                side_effect=(transient, None),
            ) as cleanup:
                case.temporary.cleanup()
            self.assertEqual(cleanup.call_count, 2)
        finally:
            base_cleanup(case.temporary)


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
        self.temporary = RetryingTemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "learner"
        self.root.mkdir()
        shutil.copyfile(SOURCE / "pyproject.toml", self.root / "pyproject.toml")
        for relative in ("workshop_queue", "tests", "academy", ".codearbiter"):
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
        p03_adr = self.root / ".codearbiter/decisions/0004-academy-lab.md"
        p03_adr.write_text(
            "---\nstatus: accepted\ndate: 2026-08-01\n"
            "title: Choose the Workshop Queue summary-format boundary\n"
            "decided-by: Academy Learner\nsupersedes: none\n---\n\n"
            "# ADR-0004 — Choose the Workshop Queue summary-format boundary\n",
            encoding="utf-8",
            newline="\n",
        )
        p03_log = self.root / P05_DECISION_LOG_PATH
        p03_log.write_text(
            p03_log.read_text(encoding="utf-8")
            + "\n## DECISION-0004 — ADR-0004 — Choose the Workshop Queue summary-format boundary\n\n"
            "**Date:** 2026-08-01\n**Status:** accepted\n**Supersedes:** none\n"
            "**Decided by:** Academy Learner\n**Decision category:** architecture\n"
            "**Artifact-section-hash:** n/a\n\n---\n",
            encoding="utf-8",
            newline="\n",
        )
        git(self.root, "init", "-b", "main")
        git(self.root, "config", "user.name", "P05 Fixture")
        git(self.root, "config", "user.email", "p05-fixture@example.invalid")
        git(self.root, "add", ".")
        git(self.root, "commit", "-m", "base")
        self.base = git(self.root, "rev-parse", "HEAD")

    def test_stage_replaces_a_hardlinked_target_without_mutating_its_external_inode(self) -> None:
        """Direct fixture writes must not escape through a learner-supplied hardlink."""
        from academy_engine.p05_fixture import stage_p05_fixture

        git(self.root, "switch", "-c", "academy/P05-checkpoint-remediation/1", self.base)
        target = self.root / "workshop_queue/model.py"
        baseline = target.read_bytes()
        sentinel = Path(self.temporary.name) / "external-model.py"
        sentinel.write_bytes(baseline)
        target.unlink()
        os.link(sentinel, target)
        self.assertEqual(git(self.root, "status", "--porcelain"), "")

        stage_p05_fixture(self.root, base=self.base)

        self.assertEqual(sentinel.read_bytes(), baseline)
        self.assertNotEqual(target.read_bytes(), baseline)

    def test_stage_rejects_a_learner_forged_baseline_helper(self) -> None:
        """Preparation must bind source inputs to verifier-owned canonical bytes."""
        from academy_engine.p05_fixture import P05FixtureError, stage_p05_fixture

        model = self.root / "workshop_queue/model.py"
        model.write_bytes(
            model.read_bytes()
            + b'\n\ndef learner_supplied_bypass() -> str:\n    return "trusted by parent"\n'
        )
        git(self.root, "add", "workshop_queue/model.py")
        git(self.root, "commit", "-m", "forge P05 baseline helper")
        forged_base = git(self.root, "rev-parse", "HEAD")
        git(
            self.root,
            "switch",
            "-c",
            "academy/P05-checkpoint-remediation/1",
            forged_base,
        )

        with self.assertRaises(P05FixtureError):
            stage_p05_fixture(self.root, base=forged_base)

    def test_validator_rejects_a_self_consistent_fixture_from_a_forged_parent(self) -> None:
        """A matching forged parent and child cannot become their own trust anchor."""
        from academy_engine.p05_fixture import stage_p05_fixture, validate_p05_fixture

        canonical = Path(self.temporary.name) / "canonical"
        subprocess.run(
            ["git", "clone", "--no-hardlinks", str(self.root), str(canonical)],
            check=True,
            capture_output=True,
            text=True,
        )
        git(canonical, "config", "user.name", "P05 Canonical Fixture")
        git(canonical, "config", "user.email", "p05-canonical@example.invalid")
        git(
            canonical,
            "switch",
            "-c",
            "academy/P05-checkpoint-remediation/canonical",
            self.base,
        )
        staged = stage_p05_fixture(canonical, base=self.base)
        canonical_prepared = {
            path: (canonical / path).read_bytes()
            for path in staged
        }

        helper = b'\n\ndef learner_supplied_bypass() -> str:\n    return "trusted by parent"\n'
        model = self.root / "workshop_queue/model.py"
        model.write_bytes(model.read_bytes() + helper)
        git(self.root, "add", "workshop_queue/model.py")
        git(self.root, "commit", "-m", "forge P05 baseline helper")
        forged_base = git(self.root, "rev-parse", "HEAD")
        git(
            self.root,
            "switch",
            "-c",
            "academy/P05-checkpoint-remediation/forged",
            forged_base,
        )
        for path, raw in canonical_prepared.items():
            target = self.root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw + helper if path == "workshop_queue/model.py" else raw)
        scenario = self.root / "training_scenarios/P05-checkpoint-remediation.json"
        scenario.parent.mkdir(parents=True)
        shutil.copyfile(
            self.root / "academy/scenarios/P05-checkpoint-remediation/files/scenario.json",
            scenario,
        )
        git(self.root, "add", "training_scenarios/P05-checkpoint-remediation.json", *staged)
        git(self.root, "commit", "-m", "forge self-consistent P05 fixture")

        self.assertFalse(validate_p05_fixture(self.root, git(self.root, "rev-parse", "HEAD")))

    def test_stage_authors_accepted_adr_0005_and_appends_decision_0005(self) -> None:
        from academy_engine.p05_fixture import stage_p05_fixture, validate_p05_fixture

        prior_adr = git(
            self.root,
            "show",
            f"{self.base}:.codearbiter/decisions/0002-explicit-ticket-state-machine.md",
        )
        decision_log_prefix = (self.root / P05_DECISION_LOG_PATH).read_bytes()
        git(self.root, "switch", "-c", "academy/P05-checkpoint-remediation/1", self.base)

        staged = stage_p05_fixture(self.root, base=self.base)

        self.assertEqual(
            staged,
            (
                P05_ADR_PATH,
                P05_DECISION_LOG_PATH,
                "tests/test_cli.py",
                "workshop_queue/cli.py",
                "workshop_queue/model.py",
                "workshop_queue/service.py",
            ),
        )
        adr = (self.root / P05_ADR_PATH).read_text(encoding="utf-8")
        for expected in (
            "status: accepted",
            "date: 2026-08-08",
            f"title: {P05_ADR_TITLE}",
            "decided-by: SUaDtL",
            "supersedes: 0002-explicit-ticket-state-machine",
            "`open` to `claimed`",
            "`claimed` to `completed`",
            "`claimed` to terminal `blocked`",
            "immutable block metadata",
            "blocked tickets cannot carry completion metadata",
            "status is not `completed`",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, adr)
        log = (self.root / P05_DECISION_LOG_PATH).read_bytes()
        self.assertTrue(log.startswith(decision_log_prefix))
        self.assertEqual(log.count(b"## DECISION-0005 "), 1)
        self.assertIn(b"**Status:** accepted", log[len(decision_log_prefix) :])
        self.assertIn(b"**Supersedes:** DECISION-0002", log[len(decision_log_prefix) :])
        self.assertIn(b"**Decided by:** SUaDtL", log[len(decision_log_prefix) :])
        self.assertIn(
            b"**Artifact-section-hash:** 24d9aef09ecf1b5de995c31d3bf3317c59408305470dc4d1ae21b5b48eb36019",
            log[len(decision_log_prefix) :],
        )
        self.assertIn(
            b"- **Status type:** same-level-conflict-resolution",
            log[len(decision_log_prefix) :],
        )
        self.assertEqual(
            git(
                self.root,
                "show",
                f"{self.base}:.codearbiter/decisions/0002-explicit-ticket-state-machine.md",
            ),
            prior_adr,
        )

        scenario = self.root / "training_scenarios/P05-checkpoint-remediation.json"
        scenario.parent.mkdir(parents=True)
        shutil.copyfile(
            self.root / "academy/scenarios/P05-checkpoint-remediation/files/scenario.json",
            scenario,
        )
        git(self.root, "add", "training_scenarios/P05-checkpoint-remediation.json", *staged)
        git(self.root, "commit", "-m", "academy: prepare P05-checkpoint-remediation attempt 1")
        prepared = git(self.root, "rev-parse", "HEAD")
        self.assertTrue(validate_p05_fixture(self.root, prepared))

    def test_validator_rejects_governance_and_terminal_graph_mutations(self) -> None:
        from academy_engine.p05_fixture import stage_p05_fixture, validate_p05_fixture

        mutations = (
            "adr-attribution",
            "adr-supersession",
            "rewritten-log-prefix",
            "mutable-model",
            "blocked-can-complete",
            "blocked-completion-metadata",
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                clone = Path(self.temporary.name) / mutation
                subprocess.run(
                    ["git", "clone", "--no-hardlinks", str(self.root), str(clone)],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                git(clone, "config", "user.name", "P05 Mutation")
                git(clone, "config", "user.email", "p05-mutation@example.invalid")
                base = git(clone, "rev-parse", "HEAD")
                git(clone, "switch", "-c", "academy/P05-checkpoint-remediation/1", base)
                staged = stage_p05_fixture(clone, base=base)
                if mutation == "adr-attribution":
                    path = clone / P05_ADR_PATH
                    path.write_text(
                        path.read_text(encoding="utf-8").replace(
                            "decided-by: SUaDtL", "decided-by: Academy Learner"
                        ),
                        encoding="utf-8",
                        newline="\n",
                    )
                elif mutation == "adr-supersession":
                    path = clone / P05_ADR_PATH
                    path.write_text(
                        path.read_text(encoding="utf-8").replace(
                            "supersedes: 0002-explicit-ticket-state-machine",
                            "supersedes: none",
                        ),
                        encoding="utf-8",
                        newline="\n",
                    )
                elif mutation == "rewritten-log-prefix":
                    path = clone / P05_DECISION_LOG_PATH
                    path.write_text(
                        path.read_text(encoding="utf-8").replace(
                            "## DECISION-0004 —", "## DECISION-0004 rewritten —"
                        ),
                        encoding="utf-8",
                        newline="\n",
                    )
                elif mutation == "mutable-model":
                    path = clone / "workshop_queue/model.py"
                    path.write_text(
                        path.read_text(encoding="utf-8").replace(
                            "@dataclass(frozen=True, slots=True)",
                            "@dataclass(slots=True)",
                        ),
                        encoding="utf-8",
                        newline="\n",
                    )
                elif mutation == "blocked-can-complete":
                    path = clone / "workshop_queue/service.py"
                    text = path.read_text(encoding="utf-8")
                    complete = text.index("def complete_ticket(")
                    before, body = text[:complete], text[complete:]
                    body = body.replace(
                        "if ticket.status is not TicketStatus.CLAIMED:",
                        "if ticket.status not in {TicketStatus.CLAIMED, TicketStatus.BLOCKED}:",
                        1,
                    ).replace(
                        "replace(ticket, status=TicketStatus.COMPLETED, completed_at=now, resolution=resolution)",
                        "replace(ticket, status=TicketStatus.COMPLETED, completed_at=now, resolution=resolution, blocked_at=None, blocked_reason=None)",
                        1,
                    )
                    path.write_text(before + body, encoding="utf-8", newline="\n")
                else:
                    path = clone / "workshop_queue/model.py"
                    text = path.read_text(encoding="utf-8")
                    clause = (
                        "        if self.status is TicketStatus.BLOCKED and any(value is not None for value in (self.completed_at, self.resolution)):\n"
                        "            raise ValidationError(\"blocked tickets cannot have completion metadata\")\n"
                    )
                    self.assertIn(clause, text)
                    path.write_text(text.replace(clause, ""), encoding="utf-8", newline="\n")

                scenario = clone / "training_scenarios/P05-checkpoint-remediation.json"
                scenario.parent.mkdir(parents=True)
                shutil.copyfile(
                    clone / "academy/scenarios/P05-checkpoint-remediation/files/scenario.json",
                    scenario,
                )
                git(clone, "add", "training_scenarios/P05-checkpoint-remediation.json", *staged)
                git(clone, "commit", "-m", f"academy: forge {mutation}")
                self.assertFalse(validate_p05_fixture(clone, git(clone, "rev-parse", "HEAD")))

    def test_validator_rejects_reclaiming_a_blocked_ticket(self) -> None:
        """Blocked is terminal; a forged claim path cannot clear block metadata."""
        from academy_engine.p05_fixture import stage_p05_fixture, validate_p05_fixture

        git(self.root, "switch", "-c", "academy/P05-checkpoint-remediation/1", self.base)
        staged = stage_p05_fixture(self.root, base=self.base)
        service_path = self.root / "workshop_queue/service.py"
        service = service_path.read_text(encoding="utf-8")
        claim_start = service.index("def claim_ticket(")
        complete_start = service.index("def complete_ticket(", claim_start)
        before, claim, after = (
            service[:claim_start],
            service[claim_start:complete_start],
            service[complete_start:],
        )
        claimed_guard = "if ticket.status is not TicketStatus.OPEN:"
        claimed_replacement = (
            "replace(ticket, status=TicketStatus.CLAIMED, "
            "claimed_by=volunteer, claimed_at=now)"
        )
        self.assertEqual(claim.count(claimed_guard), 1)
        self.assertEqual(claim.count(claimed_replacement), 1)
        claim = claim.replace(
            claimed_guard,
            "if ticket.status not in {TicketStatus.OPEN, TicketStatus.BLOCKED}:",
        ).replace(
            claimed_replacement,
            "replace(ticket, status=TicketStatus.CLAIMED, "
            "claimed_by=volunteer, claimed_at=now, blocked_at=None, blocked_reason=None)",
        )
        service_path.write_text(before + claim + after, encoding="utf-8", newline="\n")
        scenario = self.root / "training_scenarios/P05-checkpoint-remediation.json"
        scenario.parent.mkdir(parents=True)
        shutil.copyfile(
            self.root / "academy/scenarios/P05-checkpoint-remediation/files/scenario.json",
            scenario,
        )
        git(self.root, "add", "training_scenarios/P05-checkpoint-remediation.json", *staged)
        git(self.root, "commit", "-m", "academy: forge blocked ticket reclaim")

        self.assertFalse(validate_p05_fixture(self.root, git(self.root, "rev-parse", "HEAD")))

    def test_stage_refuses_a_nonsequential_p03_decision_history(self) -> None:
        from academy_engine.p05_fixture import P05FixtureError, stage_p05_fixture

        for mutation in ("missing-adr-0004", "missing-decision-0004"):
            with self.subTest(mutation=mutation):
                clone = Path(self.temporary.name) / mutation
                subprocess.run(
                    ["git", "clone", "--no-hardlinks", str(self.root), str(clone)],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                git(clone, "config", "user.name", "P05 History Mutation")
                git(clone, "config", "user.email", "p05-history@example.invalid")
                if mutation == "missing-adr-0004":
                    (clone / ".codearbiter/decisions/0004-academy-lab.md").unlink()
                else:
                    path = clone / P05_DECISION_LOG_PATH
                    text = path.read_text(encoding="utf-8")
                    start = text.index("\n## DECISION-0004 ")
                    path.write_text(text[:start] + "\n", encoding="utf-8", newline="\n")
                git(clone, "add", "-A")
                git(clone, "commit", "-m", mutation)
                base = git(clone, "rev-parse", "HEAD")
                git(clone, "switch", "-c", "academy/P05-checkpoint-remediation/1", base)

                with self.assertRaises(P05FixtureError):
                    stage_p05_fixture(clone, base=base)

    def test_stage_preserves_context_as_a_genuine_adr_0002_stale_reference(self) -> None:
        from academy_engine.p05_fixture import P05FixtureError, stage_p05_fixture

        clone = Path(self.temporary.name) / "current-context"
        subprocess.run(
            ["git", "clone", "--no-hardlinks", str(self.root), str(clone)],
            check=True,
            capture_output=True,
            text=True,
        )
        git(clone, "config", "user.name", "P05 Context Mutation")
        git(clone, "config", "user.email", "p05-context@example.invalid")
        context = clone / ".codearbiter/CONTEXT.md"
        text = context.read_text(encoding="utf-8")
        context.write_text(
            text.replace(
                "[ADR-0002](decisions/0002-explicit-ticket-state-machine.md)",
                "[ADR-0005](decisions/0005-terminal-blocked-ticket-lifecycle.md)",
            ),
            encoding="utf-8",
            newline="\n",
        )
        git(clone, "add", ".codearbiter/CONTEXT.md")
        git(clone, "commit", "-m", "make context current too early")
        base = git(clone, "rev-parse", "HEAD")
        git(clone, "switch", "-c", "academy/P05-checkpoint-remediation/1", base)

        with self.assertRaises(P05FixtureError):
            stage_p05_fixture(clone, base=base)

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
                ".codearbiter/decisions/0005-terminal-blocked-ticket-lifecycle.md",
                ".codearbiter/decisions/decision-log.md",
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
                ".codearbiter/decisions/0005-terminal-blocked-ticket-lifecycle.md",
                ".codearbiter/decisions/decision-log.md",
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
