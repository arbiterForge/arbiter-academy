from __future__ import annotations

import ast
import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from academy_engine.checkpoints import Predicate, _Attempt, _SemanticContext, _semantic


SOURCE = Path(__file__).resolve().parents[1]
P06_CLI_OBJECT = "5b41fb168a8b258cfae7eebc46e8b9ea7696ba56"
P06_PRIOR_CLI_OBJECT = "042746e43698e5d2a6de4c536f1024f893aef805"
P06_CONTEXT_BYTES = b"""---
arbiter: enabled
stage: 2
---
<!--INITIALIZED-->

# Project: Workshop Queue

Workshop Queue is a local-first Python application used in Arbiter Academy labs.
It records, assigns, and moves teaching tickets through a small explicit lifecycle.
This directory is a pre-staged Academy fixture: learners inspect, reset, mutate,
review, and audit it during later labs.

## Fixture identity

- Product steward: Academy Facilitator (fictional Academy role).
- Historical records: all dates, events, findings, and names in this state are
  fictional Academy fixtures, not evidence about a live service or person.
- Runtime: Python 3 with the standard library only; the root license is AGPL-3.0-only.

## Scope and boundaries

- Durable ticket data is local JSON under an operator-selected application-data root.
- Assignment behavior is defined by the [ticket-assignment specification](specs/ticket-assignment.md)
  and [implementation plan](plans/ticket-assignment.md).
- The JSON boundary is recorded by [ADR-0001](decisions/0001-json-storage-boundary.md);
  lifecycle rules are recorded by [ADR-0002](decisions/0002-explicit-ticket-state-machine.md).
- Workshop Queue report output is JSON-only.

## Not this project

Workshop Queue is not a hosted ticketing service, identity system, payment system,
or team chat. Academy exercises use only fabricated ticket content and need no
network connection or credential.

## Governing artifacts

- [Coding standards](coding-standards.md)
- [Technology and verification commands](tech-stack.md)
- [Security controls](security-controls.md)
- [Open task board](open-tasks.md)
- [Academy training questions](open-questions.md)
"""
P06_CONTEXT_AFTER_BYTES = P06_CONTEXT_BYTES.replace(
    b"[ADR-0002](decisions/0002-explicit-ticket-state-machine.md)",
    b"[ADR-0005](decisions/0005-terminal-blocked-ticket-lifecycle.md)",
).replace(
    b"- Workshop Queue report output is JSON-only.",
    b"- Workshop Queue report output defaults to stable text and supports structured JSON with --format json.",
)
P06_NOTE_BYTES = (
    b"# Unrelated learner note\n\n"
    b"Keep this note unchanged while recovering the interrupted summary-format context.\n"
)
P06_SCENARIO_BYTES = (
    b'{"interrupted_lane":"P05-checkpoint-remediation",'
    b'"lab_id":"P06-context-drift-recovery",'
    b'"operation":"provenance_recovery",'
    b'"preserved_path":"docs/preserved-note.md",'
    b'"provenance_path":".codearbiter/.provenance/CONTEXT.json",'
    b'"stale_claim":"Workshop Queue report output is JSON-only.",'
    b'"starting_condition":"interrupted-lane-context-stale",'
    b'"target":".codearbiter/CONTEXT.md"}\n'
)
P06_PROVENANCE_BYTES = b"""{
  "created": "2026-07-30",
  "doc": "CONTEXT",
  "entries": [
    {
      "claims": [
        {
          "claim": "Workshop Queue report output is JSON-only.",
          "confidence": "strong",
          "lines": "60-67"
        }
      ],
      "drift_trigger": true,
      "hash": "042746e43698e5d2a6de4c536f1024f893aef805",
      "path": "workshop_queue/cli.py"
    }
  ],
  "interview_derived": false,
  "schema": 1
}
"""
P06_PROVENANCE_AFTER_BYTES = P06_PROVENANCE_BYTES.replace(
    P06_PRIOR_CLI_OBJECT.encode("ascii"), P06_CLI_OBJECT.encode("ascii")
)
P06_CONTEXT_SHA256 = "3c496fe68bfc6042663c9b1d697c6b7f314e1f814533acbb30fd5169c39752f4"
P06_CONTEXT_AFTER_SHA256 = "f6840aedb9f55ae370f1b3b3e4d69235e82a3733e52148f93e2a6af32fe9e9b1"
P06_PROVENANCE_SHA256 = "4831a0db68f47f7f63fd6d0925942184488ce65231fb3acb747b753aae38a915"
P06_PROVENANCE_AFTER_SHA256 = "c48d6b8d06de435e52f74d17a33ae17636276c43c361b6ab4acbf0ac0e4b2e7b"
P06_NOTE_SHA256 = "d4b7663f8bb21a4e312772cab1b8870e7f1132122eef972b9f8c300766f14871"


def assert_p06_report_source_contract(test: unittest.TestCase, source: bytes) -> None:
    """Assert the shared CLI behavior that makes the prepared provenance claim stale."""
    tree = ast.parse(source.decode("utf-8"))
    report_format_calls: list[ast.Call] = []
    write_report: ast.FunctionDef | None = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_write_report":
            write_report = node
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        owner = node.func.value
        if (
            node.func.attr == "add_argument"
            and isinstance(owner, ast.Name)
            and owner.id == "report_parser"
            and len(node.args) == 1
            and isinstance(node.args[0], ast.Constant)
            and node.args[0].value == "--format"
        ):
            report_format_calls.append(node)

    test.assertEqual(len(report_format_calls), 1)
    keywords = {keyword.arg: keyword.value for keyword in report_format_calls[0].keywords}
    test.assertEqual(
        tuple(element.value for element in keywords["choices"].elts),
        ("text", "json"),
    )
    test.assertEqual(keywords["default"].value, "text")
    test.assertIsNotNone(write_report)
    json_branch = [
        node
        for node in ast.walk(write_report)
        if isinstance(node, ast.If)
        and isinstance(node.test, ast.Compare)
        and isinstance(node.test.left, ast.Name)
        and node.test.left.id == "output_format"
        and len(node.test.ops) == 1
        and isinstance(node.test.ops[0], ast.Eq)
        and len(node.test.comparators) == 1
        and isinstance(node.test.comparators[0], ast.Constant)
        and node.test.comparators[0].value == "json"
    ]
    test.assertEqual(len(json_branch), 1)
    test.assertTrue(
        any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "json"
            and node.func.attr == "dumps"
            for node in ast.walk(json_branch[0])
        )
    )
    test.assertTrue(any(isinstance(node, ast.For) for node in write_report.body))


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True,
        text=True, encoding="utf-8",
    ).stdout.strip()


def _write(root: Path, relative: str, raw: bytes) -> None:
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)


def _p06_semantic_fixture(
    test: unittest.TestCase,
    *,
    correction_subject: str = "recover context",
    handoff_subject: str = "record handoff",
    route: str = "re-scout",
    alter_note: bool = False,
    extra_correction_path: bool = False,
    extra_handoff_path: bool = False,
    wrong_context: bool = False,
    wrong_provenance: bool = False,
) -> tuple[Path, _SemanticContext]:
    temporary = tempfile.TemporaryDirectory()
    test.addCleanup(temporary.cleanup)
    root = Path(temporary.name)
    _git(root, "init", "-b", "main")
    _git(root, "config", "core.autocrlf", "false")
    _git(root, "config", "core.eol", "lf")
    _git(root, "config", "user.name", "Academy Learner")
    _git(root, "config", "user.email", "learner@example.test")
    source = subprocess.run(
        ["git", "show", "HEAD:workshop_queue/cli.py"],
        cwd=SOURCE, check=True, capture_output=True,
    ).stdout
    _write(root, ".codearbiter/CONTEXT.md", P06_CONTEXT_BYTES)
    _write(root, ".codearbiter/.provenance/CONTEXT.json", P06_PROVENANCE_BYTES)
    _write(root, "docs/preserved-note.md", P06_NOTE_BYTES)
    _write(root, "workshop_queue/cli.py", source)
    _git(root, "add", ".")
    _git(root, "commit", "-m", "prepared P06")
    prepared = _git(root, "rev-parse", "HEAD")

    _write(
        root,
        ".codearbiter/CONTEXT.md",
        P06_CONTEXT_AFTER_BYTES + (b"unexpected\n" if wrong_context else b""),
    )
    _write(
        root,
        ".codearbiter/.provenance/CONTEXT.json",
        P06_PROVENANCE_BYTES if wrong_provenance else P06_PROVENANCE_AFTER_BYTES,
    )
    if alter_note:
        _write(root, "docs/preserved-note.md", P06_NOTE_BYTES + b"changed\n")
    if extra_correction_path:
        _write(root, "unrelated.txt", b"not allowed\n")
    _git(root, "add", ".")
    _git(root, "commit", "-m", correction_subject)
    recovery = _git(root, "rev-parse", "HEAD")

    handoff = {
        "context_after_sha256": P06_CONTEXT_AFTER_SHA256,
        "context_before_sha256": P06_CONTEXT_SHA256,
        "context_path": ".codearbiter/CONTEXT.md",
        "prepared_commit": prepared,
        "preserved_after_sha256": P06_NOTE_SHA256,
        "preserved_before_sha256": P06_NOTE_SHA256,
        "preserved_path": "docs/preserved-note.md",
        "provenance_after_sha256": P06_PROVENANCE_AFTER_SHA256,
        "provenance_before_sha256": P06_PROVENANCE_SHA256,
        "provenance_path": ".codearbiter/.provenance/CONTEXT.json",
        "recovery_commit": recovery,
        "recovery_route": route,
        "schema_version": 2,
        "source_path": "workshop_queue/cli.py",
        "stale_claim": "Workshop Queue report output is JSON-only.",
    }
    _write(
        root,
        ".codearbiter/reports/academy/P06-recovery.json",
        (json.dumps(handoff, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode("utf-8"),
    )
    if extra_handoff_path:
        _write(root, "handoff-extra.txt", b"not allowed\n")
    _git(root, "add", ".codearbiter/reports/academy/P06-recovery.json")
    if extra_handoff_path:
        _git(root, "add", "handoff-extra.txt")
    _git(root, "commit", "-m", handoff_subject)
    head = _git(root, "rev-parse", "HEAD")
    predicate = Predicate(
        "provenance_drift_recovery",
        "lab_semantics",
        {
            "profile": "provenance_recovery",
            "context": ".codearbiter/CONTEXT.md",
            "handoff": ".codearbiter/reports/academy/P06-recovery.json",
            "source": "workshop_queue/cli.py",
            "preserved_path": "docs/preserved-note.md",
            "provenance": ".codearbiter/.provenance/CONTEXT.json",
        },
    )
    attempt = _Attempt("academy/P06-context-drift-recovery/1", 1, prepared, prepared, head)
    return root, _SemanticContext(root, attempt, predicate)


def _context_at_head(context: _SemanticContext, head: str) -> _SemanticContext:
    attempt = context.attempt
    return _SemanticContext(
        context.root,
        _Attempt(attempt.branch, attempt.number, attempt.prepared, attempt.base, head),
        context.predicate,
    )


class P06ContextRecoveryContractTests(unittest.TestCase):
    def test_p06_fixture_pins_exact_byte_git_normalization(self) -> None:
        """Catches ambient Git line-ending policy changing the frozen fixture history."""
        root, _intended = _p06_semantic_fixture(self)

        self.assertEqual(
            _git(root, "config", "--local", "--get", "core.autocrlf"),
            "false",
        )
        self.assertEqual(_git(root, "config", "--local", "--get", "core.eol"), "lf")

    def test_p06_context_transition_bytes_and_hashes_are_exact(self) -> None:
        self.assertEqual(len(P06_CONTEXT_BYTES), 1664)
        self.assertEqual(hashlib.sha256(P06_CONTEXT_BYTES).hexdigest(), P06_CONTEXT_SHA256)
        self.assertEqual(len(P06_CONTEXT_AFTER_BYTES), 1727)
        self.assertEqual(
            hashlib.sha256(P06_CONTEXT_AFTER_BYTES).hexdigest(),
            P06_CONTEXT_AFTER_SHA256,
        )
        self.assertNotIn(b"ADR-0002", P06_CONTEXT_AFTER_BYTES)
        self.assertEqual(P06_CONTEXT_AFTER_BYTES.count(b"ADR-0005"), 1)
        self.assertNotIn(b"report output is JSON-only", P06_CONTEXT_AFTER_BYTES)

    def test_p06_safe_fixture_bytes_bind_provenance_note_and_scenario(self) -> None:
        """Catches drift in the non-ADR-dependent prepared provenance and preservation evidence."""
        files = SOURCE / "academy/scenarios/P06-context-drift-recovery/files"
        expected = {
            "CONTEXT.provenance.json": (
                P06_PROVENANCE_BYTES,
                "4831a0db68f47f7f63fd6d0925942184488ce65231fb3acb747b753aae38a915",
            ),
            "preserved-note.md": (
                P06_NOTE_BYTES,
                "d4b7663f8bb21a4e312772cab1b8870e7f1132122eef972b9f8c300766f14871",
            ),
            "scenario.json": (P06_SCENARIO_BYTES, None),
        }
        for name, (raw, digest) in expected.items():
            with self.subTest(name=name):
                path = files / name
                self.assertTrue(path.is_file(), f"missing P06 fixture: {name}")
                self.assertEqual(path.read_bytes(), raw)
                if digest is not None:
                    self.assertEqual(hashlib.sha256(raw).hexdigest(), digest)

    def test_p06_shared_cli_object_contradicts_the_recorded_json_only_claim(self) -> None:
        """Catches P06 pointing at source that no longer has text-default/JSON-optional reports."""
        object_id = subprocess.run(
            ["git", "rev-parse", "HEAD:workshop_queue/cli.py"],
            cwd=SOURCE,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=True,
        ).stdout.strip()
        source = subprocess.run(
            ["git", "show", "HEAD:workshop_queue/cli.py"],
            cwd=SOURCE,
            capture_output=True,
            check=True,
        ).stdout

        self.assertEqual(object_id, P06_CLI_OBJECT)
        self.assertNotEqual(object_id, P06_PRIOR_CLI_OBJECT)
        assert_p06_report_source_contract(self, source)

    def test_p06_intended_rescout_recovery_passes(self) -> None:
        _root, context = _p06_semantic_fixture(self)
        self.assertTrue(_semantic(context))

    def test_p06_equivalent_rescout_recovery_with_different_commit_subjects_passes(self) -> None:
        _root, context = _p06_semantic_fixture(
            self,
            correction_subject="docs: reconcile two proven claims",
            handoff_subject="evidence: bind recovered objects",
        )
        self.assertTrue(_semantic(context))

    def test_p06_correction_commit_allows_only_context_and_provenance(self) -> None:
        _root, context = _p06_semantic_fixture(self, extra_correction_path=True)
        self.assertFalse(_semantic(context))

    def test_p06_rejects_changed_or_recreated_preserved_note(self) -> None:
        _root, context = _p06_semantic_fixture(self, alter_note=True)
        self.assertFalse(_semantic(context))

    def test_p06_rejects_wrong_route(self) -> None:
        _root, context = _p06_semantic_fixture(self, route="re-baseline")
        self.assertFalse(_semantic(context))

    def test_p06_rejects_stale_or_noncontradictory_context_claim(self) -> None:
        _root, context = _p06_semantic_fixture(self, wrong_context=True)
        self.assertFalse(_semantic(context))

    def test_p06_rejects_provenance_hash_not_updated_to_prepared_source(self) -> None:
        _root, context = _p06_semantic_fixture(self, wrong_provenance=True)
        self.assertFalse(_semantic(context))

    def test_p06_handoff_commit_allows_only_the_recovery_record(self) -> None:
        _root, context = _p06_semantic_fixture(self, extra_handoff_path=True)
        self.assertFalse(_semantic(context))

    def test_p06_rejects_noncanonical_handoff_bytes_and_digests(self) -> None:
        root, context = _p06_semantic_fixture(self)
        path = root / ".codearbiter/reports/academy/P06-recovery.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8", newline="\n")
        _git(root, "add", ".codearbiter/reports/academy/P06-recovery.json")
        _git(root, "commit", "--amend", "--no-edit")
        self.assertFalse(_semantic(_context_at_head(context, _git(root, "rev-parse", "HEAD"))))

    def test_p06_untouched_partial_and_wrong_evidence_fail(self) -> None:
        for label, raw in (
            ("partial", b'{"schema_version":2}\n'),
            ("malformed", b"{\n"),
            ("invalid-utf8", b"\xff\n"),
        ):
            with self.subTest(label=label):
                root, context = _p06_semantic_fixture(self)
                path = root / ".codearbiter/reports/academy/P06-recovery.json"
                path.write_bytes(raw)
                _git(root, "add", ".codearbiter/reports/academy/P06-recovery.json")
                _git(root, "commit", "--amend", "--no-edit")
                self.assertFalse(_semantic(_context_at_head(context, _git(root, "rev-parse", "HEAD"))))

        root, context = _p06_semantic_fixture(self)
        path = root / ".codearbiter/reports/academy/P06-recovery.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["context_after_sha256"] = "0" * 64
        path.write_text(
            json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8", newline="\n",
        )
        _git(root, "add", ".codearbiter/reports/academy/P06-recovery.json")
        _git(root, "commit", "--amend", "--no-edit")
        self.assertFalse(_semantic(_context_at_head(context, _git(root, "rev-parse", "HEAD"))))

    def test_p06_rejects_unsafe_or_absolute_handoff_paths(self) -> None:
        for unsafe in ("../CONTEXT.md", "C:/private/CONTEXT.md", "docs\\note.md"):
            with self.subTest(unsafe=unsafe):
                root, context = _p06_semantic_fixture(self)
                path = root / ".codearbiter/reports/academy/P06-recovery.json"
                payload = json.loads(path.read_text(encoding="utf-8"))
                payload["context_path"] = unsafe
                path.write_text(
                    json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n",
                    encoding="utf-8", newline="\n",
                )
                _git(root, "add", ".codearbiter/reports/academy/P06-recovery.json")
                _git(root, "commit", "--amend", "--no-edit")
                self.assertFalse(_semantic(_context_at_head(context, _git(root, "rev-parse", "HEAD"))))

    def test_p06_rejects_uncommitted_or_extra_commit_history(self) -> None:
        root, context = _p06_semantic_fixture(self)
        _write(root, "untracked.txt", b"dirty\n")
        self.assertFalse(_semantic(context))
        (root / "untracked.txt").unlink()
        _git(root, "commit", "--allow-empty", "-m", "extra")
        self.assertFalse(_semantic(_context_at_head(context, _git(root, "rev-parse", "HEAD"))))


if __name__ == "__main__":
    unittest.main()
