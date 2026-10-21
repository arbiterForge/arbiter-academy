"""Current plugin workflows must not require red commits or invented state writes."""

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from academy_engine.checkpoints import _Attempt, _SemanticContext, _semantic, evaluate_checkpoint
from tests import test_foundations_labs as foundations
from tests import test_checkpoints as checkpoints
from tests import test_power_user_u05 as u05
from academy_engine.scenario import prepare_lab


class CurrentPluginWorkflows(unittest.TestCase):
    def test_planning_labs_start_fresh_for_the_native_authoring_route(self):
        for lab, slug in [('P01-feature-through-plan', 'academy-feature'), ('U01-autonomous-sprint', 'academy-sprint')]:
            with self.subTest(lab=lab):
                fixture = foundations.AcademyRepository()
                self.addCleanup(fixture.close)
                fixture.add_safe_upstream()
                prepare_lab(fixture.root, lab)
                for kind in ('specs', 'plans'):
                    self.assertFalse((fixture.root / f'.codearbiter/{kind}/{slug}.md').exists())
                    self.assertFalse((fixture.root / f'.codearbiter/{kind}/{slug}.html').exists())

    def test_f04_accepts_one_green_commit_without_claiming_red_chronology(self):
        helper = foundations.FoundationsCheckpointMatrixTests()
        fixture = helper._prepared('F04-fix-with-evidence')
        self.addCleanup(fixture.close)
        test = fixture.root / 'tests/test_service.py'
        text = test.read_text(encoding='utf-8')
        method = '''    def test_claim_rejects_control_characters_in_volunteer_label(self) -> None:
        for volunteer in ("Sam\\nAdmin", "Sam\\tAdmin", "Sam\\x7fAdmin"):
            with self.subTest(volunteer=repr(volunteer)):
                with self.assertRaisesRegex(ValueError, "control characters"):
                    claim_ticket([open_ticket("RQ-104")], "RQ-104", volunteer, fixed_now())
        claimed = claim_ticket([open_ticket("RQ-104")], "RQ-104", "Sam Allen", fixed_now())
        self.assertEqual(claimed[0].claimed_by, "Sam Allen")

'''
        marker = '    def test_complete_requires_a_claimed_ticket_and_records_resolution(self) -> None:\n'
        self.assertIn(marker, text)
        test.write_text(text.replace(marker, method + marker), encoding='utf-8', newline='\n')
        result = subprocess.run(['python', '-m', 'unittest', 'tests.test_service.TicketTransitionTests.test_claim_rejects_control_characters_in_volunteer_label'], cwd=fixture.root, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('ValueError not raised', result.stderr)
        code = fixture.root / 'workshop_queue/service.py'
        before = code.read_text(encoding='utf-8')
        needle = '            if not volunteer.strip():\n                raise ValueError("volunteer must be non-empty")\n'
        guard = '            if any(ord(character) < 32 or ord(character) == 127 for character in volunteer):\n                raise ValueError("volunteer must not contain control characters")\n'
        self.assertIn(needle, before)
        code.write_text(before.replace(needle, needle + guard), encoding='utf-8', newline='\n')
        result = subprocess.run(['python', '-m', 'unittest', 'tests.test_service'], cwd=fixture.root, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        fixture.commit('fix: validate claimant labels with regression', 'tests/test_service.py', 'workshop_queue/service.py')
        self.assertTrue(evaluate_checkpoint(fixture.root, 'F04-fix-with-evidence').passed)
        (fixture.root / 'unrelated.txt').write_text('unrelated', encoding='utf-8')
        self.assertFalse(evaluate_checkpoint(fixture.root, 'F04-fix-with-evidence').passed)

    def test_p05_accepts_finding_green_repair_and_honest_receipt(self):
        helper = checkpoints.CheckpointTests()
        helper.setUp()
        self.addCleanup(helper.tearDown)
        prepared_root, _, prepared = helper._p05_prepared_repository()
        history = helper._p05_history(prepared_root, prepared, 'current', name='Academy Fixture', email='fixture@example.invalid', timestamps=tuple(f'2026-08-02T12:0{i}:00+00:00' for i in range(4)))
        root = history['root']
        # Rebuild only this disposable fixture into the current green-only topology.
        helper._p05_git(root, 'reset', '--soft', str(history['finding']))
        helper._p05_git(root, 'restore', '--staged', '.codearbiter/checkpoints/P05-academy.json')
        (root / '.codearbiter/checkpoints/P05-academy.json').unlink()
        repair = helper._p05_commit(root, ('tests/test_cli.py', 'workshop_queue/cli.py'), 'fix: regression and repair', name='Academy Fixture', email='fixture@example.invalid', timestamp='2026-08-02T12:02:00+00:00')
        report = dict(history['receipt_data'])
        report.pop('red_commit')
        report.update(schema_version=3, remediation_commit=repair)
        receipt = root / '.codearbiter/checkpoints/P05-academy.json'
        receipt.write_bytes(json.dumps(report, sort_keys=True, separators=(',', ':')).encode() + b'\n')
        history['head'] = helper._p05_commit(root, ('.codearbiter/checkpoints/P05-academy.json',), 'docs: record repair', name='Academy Fixture', email='fixture@example.invalid', timestamp='2026-08-02T12:03:00+00:00')
        self.assertTrue(helper._p05_semantic(history))
        report['red_commit'] = repair
        receipt.write_bytes(json.dumps(report, sort_keys=True, separators=(',', ':')).encode() + b'\n')
        helper._p05_git(root, 'add', '.codearbiter/checkpoints/P05-academy.json')
        helper._p05_git(root, '-c', 'user.name=Academy Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '--amend', '--no-edit')
        history['head'] = helper._p05_git(root, 'rev-parse', 'HEAD').stdout.strip()
        self.assertEqual(helper._p05_git(root, 'status', '--porcelain').stdout.strip(), '')
        self.assertFalse(helper._p05_semantic(history))

    def test_u05_accepts_read_only_no_action_and_findings_only_transfer(self):
        helper = u05.U05PluginContractTests()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            context = helper.context(root)
            # Construct a fresh fixture history with no invented debug board event.
            helper.git(root, 'reset', '--soft', context.attempt.prepared)
            helper.git(root, 'restore', '--source', context.attempt.prepared, '--staged', '--worktree', '.codearbiter/open-tasks.md')
            helper.git(root, 'commit', '-m', 'docs: retain spike findings')
            head = helper.git(root, 'rev-parse', 'HEAD')
            current = _SemanticContext(root, _Attempt(context.attempt.branch, 1, context.attempt.prepared, context.attempt.base, head), context.predicate)
            self.assertTrue(_semantic(current))
            helper.git(root, 'branch', 'spike/u05-cache-key', head)
            self.assertFalse(_semantic(current))

    def test_u07_accepts_bug_fix_without_feature_classification(self):
        helper = checkpoints.U07CapstoneSemanticTests()
        helper.setUp()
        self.addCleanup(helper.tearDown)
        helper._write_honest_history()
        subprocess.run(['git', 'reset', '--soft', helper.prepared], cwd=helper.root, check=True, capture_output=True)
        for path in (helper.spec_path, helper.plan_path):
            subprocess.run(['git', 'restore', '--staged', path], cwd=helper.root, check=True, capture_output=True)
            (helper.root / path).unlink()
        helper._commit('fix: reject resolution control characters')
        self.assertTrue(_semantic(helper._context()))
        helper._write('unrelated.md', 'unrelated\n')
        helper._commit('unrelated')
        self.assertFalse(_semantic(helper._context()))
