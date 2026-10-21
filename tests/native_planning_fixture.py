"""Generate synthetic drafts with the real installed writer, never hand-edit HTML."""
import importlib.util
import sys
from pathlib import Path


def client(plugin: Path, root: Path):
    sys.path.insert(0, str(plugin / "hooks"))
    spec = importlib.util.spec_from_file_location("academy_fixture_artifact_bridge", plugin / "hooks/_artifactlib.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.ArtifactClient(root.resolve(), plugin / "helpers/artifacts")


def create_pair(plugin: Path, root: Path, slug: str = "academy-feature") -> tuple[bytes, bytes]:
    engine = client(plugin, root)
    sprint = slug == "academy-sprint"
    paths = ["docs/academy-sprint-summary.md"] if sprint else ["tests/test_cli.py", "workshop_queue/cli.py"]
    statement = ("Explain the approval boundary, SMARTS decision trail, and hard-gate stop."
                 if sprint else "The unresolved JSON summary is open plus claimed; completed tickets are excluded.")
    spec_normative = {
        "title": "Academy native planning fixture", "summary": statement,
        "baseline": {"repository": None, "commit": None, "observed_date": "2026-10-21"},
        "sections": [], "sources": [], "retired_symbols": [],
        "intent": {"id": "INTENT-01", "problem": "The requested outcome is missing.", "caller": "Academy learner", "outcome": statement, "source_refs": []},
        "approach": {"id": "APPROACH-01", "choice": "Make the bounded change and inspect its result.", "tradeoff": "This practice does not extend other product behavior.", "binding_decision_refs": []},
        "constraints": [], "scope": [{"id": "SCOPE-01", "statement": statement}],
        "non_goals": [{"id": "NON-GOAL-01", "statement": "Unrelated changes, merge, or publication."}],
        "decisions": [], "governs": paths, "open_decisions": [],
        "criteria": [{
            "id": "AC-01", "title": "Deliver the bounded outcome", "kind": "behavior", "obligation": "must",
            "intent_refs": ["SCOPE-01"], "statement": statement, "preconditions": ["Prepared Academy fixture"],
            "trigger": "Inspect the completed exercise", "guarantees": [statement],
            "scenarios": [{"id": "SCN-01", "given": "One open, one claimed, and one completed ticket", "when": "Inspect the requested output", "then": statement}],
            "verification": {"id": "VER-01", "method": "automated", "planned_target": "Academy focused check", "oracle": statement, "negative_control": "The unchanged prepared fixture does not meet the criterion.", "evidence_state": "planned"},
            "source_refs": [], "constraint_refs": [], "applicability": {"mode": "conditional", "rationale": "This exercise's prepared fixture."},
        }],
    }
    spec_id, plan_id = "SPEC-ACADEMY-FIXTURE", "PLAN-ACADEMY-FIXTURE"
    created = engine.call("create", {"operation_id": "academy-test-spec", "artifact_id": spec_id, "kind": "spec", "slug": slug, "title": spec_normative["title"], "summary": statement, "normative": spec_normative})
    plan_normative = {
        "title": "Academy native plan fixture", "summary": statement,
        "baseline": spec_normative["baseline"], "sections": [], "sources": [], "retired_symbols": [],
        "spec_ref": {"artifact_id": spec_id, "normative_sha256": created["normative_sha256"], "binding_mode": "draft_preview"},
        "tasks": [{"id": "T-01", "title": "Implement and inspect the outcome", "checkpoint": "CP-01", "execution_scope": "CP-01", "depends_on": [],
                   "paths": [{"path": path, "action": "modify"} for path in paths], "criterion_refs": [spec_id + "#AC-01"],
                   "steps": ["Check the missing behavior.", "Implement the bounded change.", "Run focused verification."],
                   "verification": [{"availability": "proposed", "cwd": ".", "argv": ["python", "-m", "unittest"], "expected_exit": 0, "assertion": statement, "required_tests": ["tests.test_cli.WorkshopQueueCliTests.test_report_json_counts_open_and_claimed_as_unresolved"]}],
                   "done_when": [statement], "rollback": "Revert the change.", "source_refs": []}],
        "checkpoints": [{"id": "CP-01", "title": "Bounded delivery", "tasks": ["T-01"], "exit": statement, "depends_on": []}],
        "prerequisites": [], "criterion_dispositions": [],
    }
    engine.call("create", {"operation_id": "academy-test-plan", "artifact_id": plan_id, "kind": "plan", "slug": slug, "title": plan_normative["title"], "summary": statement, "spec_id": spec_id, "normative": plan_normative})
    return tuple((root / f".codearbiter/{kind}s/{slug}.html").read_bytes() for kind in ("spec", "plan"))
