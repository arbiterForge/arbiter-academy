"""Current producer contracts, exercised in disposable repositories only."""
import copy
import hashlib
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

from academy_engine import checkpoints as c


class P06ProvenanceShapeTests(unittest.TestCase):
    def record(self):
        return {"schema": 2, "doc": "CONTEXT", "created": "2026-10-21",
                "document": {"path": ".codearbiter/CONTEXT.md", "digest_method": "sha256-raw",
                             "digest": hashlib.sha256(c._P06_NATIVE_CONTEXT_AFTER).hexdigest()},
                "fields": [{"id": "FIELD-DOCUMENT", "owner_ref": "document", "claims": [
                    {"id": "CLAIM-DOCUMENT", "semantic_review": {"state": "unreviewed", "reference": None},
                     "effective_authority_refs": [], "evidence": [
                         {"kind": "content", "path": "workshop_queue/cli.py", "digest_method": "sha256-raw",
                          "digest": hashlib.sha256(b"source").hexdigest()}]}]}]}

    def malformed_records(self):
        for key in ("id", "owner_ref"):
            record = self.record()
            del record["fields"][0][key]
            yield "missing-field-" + key, record
        record = self.record()
        del record["fields"][0]["claims"][0]["id"]
        yield "missing-claim-id", record
        for level in ("record", "document", "field", "claim", "review", "evidence"):
            record = self.record()
            claim = record["fields"][0]["claims"][0]
            target = {"record": record, "document": record["document"], "field": record["fields"][0],
                      "claim": claim, "review": claim["semantic_review"], "evidence": claim["evidence"][0]}[level]
            target["unexpected"] = "untrusted"
            yield "unexpected-" + level, record
        for kind in ("field", "claim"):
            record = self.record()
            items = record["fields"] if kind == "field" else record["fields"][0]["claims"]
            items.append(copy.deepcopy(items[0]))
            yield "duplicate-" + kind, record
        for owner in ("", "x" * 257, "bad\nowner", None):
            record = self.record()
            record["fields"][0]["owner_ref"] = owner
            yield "owner-" + repr(owner), record
        for kind in ("field", "claim"):
            record = self.record()
            target = record["fields"][0] if kind == "field" else record["fields"][0]["claims"][0]
            target["id"] = "invalid identity"
            yield "invalid-" + kind + "-id", record
        for kind in ("fields", "claims", "evidence"):
            record = self.record()
            target = record if kind == "fields" else record["fields"][0] if kind == "claims" else record["fields"][0]["claims"][0]
            target[kind] *= 129
            yield "oversized-" + kind, record
        record = self.record()
        record["fields"][0]["claims"][0]["effective_authority_refs"] = {}
        yield "wrong-authority-type", record

    def test_rejects_malformed_v2_records(self):
        self.assertTrue(c._p06_provenance_transition(c._P06_PROVENANCE, json.dumps(self.record()).encode(), b"source"))
        for name, record in self.malformed_records():
            with self.subTest(mutation=name):
                self.assertFalse(c._p06_provenance_transition(c._P06_PROVENANCE, json.dumps(record).encode(), b"source"))

    def test_context_must_match_the_single_supported_claim_change(self):
        raw = json.dumps(self.record()).encode()
        self.assertTrue(c._p06_provenance_transition(c._P06_PROVENANCE, raw, b"source", c._P06_NATIVE_CONTEXT_AFTER))
        self.assertFalse(c._p06_provenance_transition(c._P06_PROVENANCE, raw, b"source", c._P06_CONTEXT_AFTER))
        self.assertFalse(c._p06_provenance_transition(c._P06_PROVENANCE, b" " * (1024 * 1024) + raw, b"source"))


@unittest.skipUnless(os.environ.get("ARBITER_ACADEMY_TEST_PLUGIN_ROOT"), "requires reviewed installed producer")
class CurrentGovernanceRecords(unittest.TestCase):
    def test_p06_shape_negatives_match_installed_producer(self):
        plugin = Path(os.environ["ARBITER_ACADEMY_TEST_PLUGIN_ROOT"])
        sys.path.insert(0, str(plugin / "hooks"))
        from _provenancelib import valid_provenance_record
        fixture = P06ProvenanceShapeTests()
        self.assertTrue(valid_provenance_record(fixture.record()))
        for name, record in fixture.malformed_records():
            with self.subTest(mutation=name):
                self.assertFalse(valid_provenance_record(record))
                self.assertFalse(c._p06_provenance_transition(c._P06_PROVENANCE, json.dumps(record).encode(), b"source"))

    def test_p06_real_native_adoption_and_source_change_refusal(self):
        from tests.test_p06_handoff import P06HandoffTests
        from tests.test_p06_context_recovery import _git
        from academy_engine.p06_handoff import write_p06_handoff
        plugin = Path(os.environ["ARBITER_ACADEMY_TEST_PLUGIN_ROOT"])
        sys.path.insert(0, str(plugin / "hooks"))
        from _artifactlib import ArtifactClient, ArtifactError
        from _contextwriterlib import prepare_document_preview
        helper = P06HandoffTests()
        self.addCleanup(helper.doCleanups)
        _, root, prepared, _ = helper._attempt()
        _git(root, "reset", "--hard", prepared)  # disposable synthetic fixture
        draft = root / "draft.md"
        draft.write_bytes(c._P06_NATIVE_CONTEXT_AFTER)
        engine = ArtifactClient(root, plugin / "helpers/artifacts")
        request = prepare_document_preview(root, "CONTEXT", "draft.md", ["workshop_queue/cli.py"])
        preview = engine.call("context-preview", request)
        source = root / "workshop_queue/cli.py"
        original = source.read_bytes()
        source.write_bytes(original + b"\n# changed input\n")
        with self.assertRaises(ArtifactError):
            engine.call("context-apply", {"preview_ref": preview["preview_ref"], "preview_sha256": preview["preview_sha256"]})
        self.assertEqual((root / ".codearbiter/CONTEXT.md").read_bytes(), c._P06_CONTEXT)
        source.write_bytes(original)
        engine.call("context-apply", {"preview_ref": preview["preview_ref"], "preview_sha256": preview["preview_sha256"]})
        draft.unlink()
        with (root / ".git/info/exclude").open("a", encoding="utf-8") as f:
            f.write("\n.codearbiter/.artifacts/\n")
        after = (root / ".codearbiter/.provenance/CONTEXT.json").read_bytes()
        self.assertTrue(c._p06_provenance_transition(c._P06_PROVENANCE, after, original))
        record = json.loads(after)
        for mutation in ("source", "document", "semantic"):
            damaged = copy.deepcopy(record)
            if mutation == "source":
                damaged["fields"][0]["claims"][0]["evidence"][0]["digest"] = "0" * 64
            elif mutation == "document":
                damaged["document"]["digest"] = "0" * 64
            else:
                damaged["fields"][0]["claims"][0]["semantic_review"] = {"state": "verified", "reference": "invented"}
            self.assertFalse(c._p06_provenance_transition(c._P06_PROVENANCE, json.dumps(damaged).encode(), original))
        _git(root, "add", ".codearbiter/CONTEXT.md", ".codearbiter/.provenance/CONTEXT.json")
        _git(root, "commit", "-m", "recover through native writer")
        self.assertEqual(_git(root, "status", "--porcelain", "--untracked-files=all"), "")
        report = write_p06_handoff(root)
        self.assertEqual(json.loads(report.read_bytes())["provenance_after_sha256"], hashlib.sha256(after).hexdigest())
        _git(root, "add", str(report.relative_to(root)))
        _git(root, "commit", "-m", "record recovery")
        attempt = c._Attempt("academy/P06-context-drift-recovery/1", 1, prepared, "0" * 40, _git(root, "rev-parse", "HEAD"))
        definition = c.load_checkpoint(Path(__file__).parents[1] / "academy/checkpoints/P06-context-drift-recovery.json")
        self.assertTrue(c._semantic(c._SemanticContext(root, attempt, definition.predicates[0])))

    def test_p03_acceptance_matches_installed_schema_and_rejects_corrupt_bindings(self):
        from tests.test_checkpoints import P03NativeEvidenceTests
        plugin = Path(os.environ["ARBITER_ACADEMY_TEST_PLUGIN_ROOT"])
        spec = importlib.util.spec_from_file_location("producer_adr_fixture", plugin / "hooks/_adrlifecycle.py")
        owner = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(owner)
        helper = P03NativeEvidenceTests()
        helper.setUp()
        self.addCleanup(helper.tearDown)
        root = helper.root
        adr_path = ".codearbiter/decisions/0004-academy-lab.md"
        blob = c._git_blob(root, helper.head, adr_path)
        text = "Use stable text for Workshop Queue summaries."
        obligations = [{"id": "0004-academy-lab.01", "section": "Decision", "text": text, "text_sha256": hashlib.sha256(text.encode()).hexdigest()}]
        event = {"schema": "adr-lifecycle/v1", "event": "acceptance", "adr": "0004-academy-lab", "recorded_at": "2026-10-21T12:00:00Z", "source_commit": helper.head,
                 "blob_sha256": hashlib.sha256(blob).hexdigest(), "body_sha256": hashlib.sha256(owner.immutable_body(blob)).hexdigest(), "obligations": obligations,
                 "obligations_sha256": owner.obligation_set_digest(obligations), "obligations_sealed": True}
        self.assertEqual(owner.validate_events([event], {event["adr"]: blob}), [])
        self.assertTrue(c._p03_lifecycle_binding(event, blob, helper.head))
        for key, value in (("source_commit", "0" * 40), ("body_sha256", "0" * 64), ("obligations_sealed", False), ("obligations", [])):
            self.assertFalse(c._p03_lifecycle_binding({**event, key: value}, blob, helper.head))
        ledger = root / ".codearbiter/decisions/adr-lifecycle.jsonl"
        ledger.write_text(json.dumps(event) + "\n", encoding="utf-8")
        helper._commit("bind accepted planned decision")
        attempt = c._Attempt("academy/P03-record-an-adr/1", 1, helper.prepared, "0" * 40, helper._head())
        self.assertTrue(c._p03_accepted_adr(root, attempt, adr_path, ".codearbiter/decisions/decision-log.md", require_lifecycle=True))
        ledger.write_text(json.dumps(event) + "\n" + json.dumps(event) + "\n", encoding="utf-8")
        helper._commit("invalid duplicate")
        attempt = c._Attempt(attempt.branch, 1, helper.prepared, "0" * 40, helper._head())
        self.assertFalse(c._p03_accepted_adr(root, attempt, adr_path, ".codearbiter/decisions/decision-log.md", require_lifecycle=True))
