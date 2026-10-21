"""Native lesson validation must use the trusted installed engine."""
import tempfile
import unittest
import os
from pathlib import Path


class NativePlanningTests(unittest.TestCase):
    def test_native_inspector_is_available_without_importing_learner_code(self):
        from academy_engine import native_planning
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            # A checkout-local fake bridge must not execute.
            plugin = root / "plugin"
            (plugin / "hooks").mkdir(parents=True)
            marker = root / "executed"
            (plugin / "hooks/_artifactlib.py").write_text(
                "from pathlib import Path\nPath(" + repr(str(marker)) + ").touch()\n",
                encoding="utf-8",
            )
            with self.assertRaises(native_planning.NativePlanningError):
                native_planning.inspect_pair(root, plugin, "academy-feature", b"fake", b"fake")
            self.assertFalse(marker.exists())

    def test_native_inspector_requires_an_explicit_installation(self):
        from academy_engine import native_planning
        with self.assertRaises(native_planning.NativePlanningError):
            native_planning.inspect_pair(Path.cwd(), None, "academy-feature", b"fake", b"fake")


@unittest.skipUnless(os.environ.get("ARBITER_ACADEMY_TEST_PLUGIN_ROOT"), "native integration requires the reviewed installed plugin")
class InstalledNativePlanningTests(unittest.TestCase):
    def _assert_corrupt_producer_refused(self, component):
        import json
        import platform
        import shutil
        from unittest.mock import patch
        from academy_engine.native_planning import NativePlanningError, inspect_pair

        installed = Path(os.environ["ARBITER_ACADEMY_TEST_PLUGIN_ROOT"])
        manifest = json.loads((installed / "helpers/artifacts/release.json").read_bytes())
        architecture = {"x86_64": "amd64", "amd64": "amd64", "arm64": "arm64", "aarch64": "arm64"}[platform.machine().lower()]
        binary = manifest["binaries"][platform.system().lower() + "/" + architecture]["file"]
        paths = {"bridge": "hooks/_artifactlib.py", "helper": "hooks/_gitexec.py",
                 "manifest": "helpers/artifacts/release.json", "binary": "helpers/artifacts/" + binary}
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory).resolve()
            learner, producer = base / "learner", base / "external-producer"
            learner.mkdir()
            for relative in paths.values():
                target = producer / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(installed / relative, target)
            target = producer / paths[component]
            if component == "manifest":
                changed = dict(manifest)
                changed["unreviewed"] = True
                target.write_text(json.dumps(changed), encoding="utf-8")
            else:
                with target.open("ab") as handle:
                    handle.write(b"\n# altered producer component\n")
            expected = "producer fails its reviewed digest" if component == "binary" else "producer differs from this Academy cohort"
            with patch("academy_engine.native_planning.subprocess.run") as worker:
                with self.assertRaisesRegex(NativePlanningError, expected):
                    inspect_pair(learner, producer, "academy-feature", b"inert", b"inert")
                worker.assert_not_called()

    def test_altered_external_bridge_is_rejected_before_execution(self):
        self._assert_corrupt_producer_refused("bridge")

    def test_altered_external_git_helper_is_rejected_before_execution(self):
        self._assert_corrupt_producer_refused("helper")

    def test_altered_external_manifest_is_rejected_before_execution(self):
        self._assert_corrupt_producer_refused("manifest")

    def test_altered_external_binary_is_rejected_before_execution(self):
        self._assert_corrupt_producer_refused("binary")

    def test_current_sprint_checkpoint_accepts_native_pair_without_invented_log_event(self):
        from tests.test_power_user_u01 import U01SprintDecisionSemanticsTests
        from tests.native_planning_fixture import create_pair
        from academy_engine.checkpoints import Predicate, _Attempt, _SemanticContext, _semantic
        plugin = Path(os.environ["ARBITER_ACADEMY_TEST_PLUGIN_ROOT"])
        helper = U01SprintDecisionSemanticsTests()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old = helper._context(root)
            helper._git(root, "reset", "--soft", old.attempt.prepared)
            for kind in ("specs", "plans"):
                path = f".codearbiter/{kind}/academy-sprint.md"
                helper._git(root, "restore", "--staged", path)
                (root / path).unlink()
            helper._git(root, "restore", "--source", old.attempt.prepared, "--staged", "--worktree", ".codearbiter/sprint-log.md")
            create_pair(plugin, root, "academy-sprint")
            with (root / ".git/info/exclude").open("a", encoding="utf-8") as f:
                f.write("\n.codearbiter/.artifacts/\n")
            guide = root / "docs/academy-sprint-summary.md"
            guide.write_text("# Operate a bounded autonomous sprint\n\n## Approval boundary\nThe original request authorizes this bounded work; merge and publish require their own authority.\n\n## SMARTS decision trail\nRecord material choices and their reasons without inventing approvals.\n\n## Hard-gate stop\nPreserve the concrete blocker and resolve it before continuing.\n", encoding="utf-8")
            helper._git(root, "add", ".codearbiter/specs/academy-sprint.html", ".codearbiter/plans/academy-sprint.html", "docs/academy-sprint-summary.md")
            helper._git(root, "commit", "-m", "complete bounded native sprint")
            data = {**old.predicate.data, "spec": ".codearbiter/specs/academy-sprint.html", "plan": ".codearbiter/plans/academy-sprint.html"}
            attempt = _Attempt(old.attempt.branch, 1, old.attempt.prepared, old.attempt.base, helper._git(root, "rev-parse", "HEAD"))
            context = _SemanticContext(root, attempt, Predicate(old.predicate.id, old.predicate.type, data), plugin)
            self.assertTrue(_semantic(context))
            self.assertFalse(_semantic(_SemanticContext(root, attempt, context.predicate)))
            (root / "unrelated.txt").write_text("outside scope", encoding="utf-8")
            self.assertFalse(_semantic(context))

    def test_worker_receives_a_private_pinned_producer_snapshot(self):
        import json
        from unittest.mock import patch
        from types import SimpleNamespace
        from academy_engine.native_planning import inspect_pair
        plugin = Path(os.environ["ARBITER_ACADEMY_TEST_PLUGIN_ROOT"])
        def run(argv, **kwargs):
            snapshot = Path(argv[5])
            self.assertNotEqual(snapshot.resolve(), plugin.resolve())
            self.assertEqual(json.loads((snapshot / "helpers/artifacts/release.json").read_bytes()),
                             json.loads((plugin / "helpers/artifacts/release.json").read_bytes()))
            binaries = list((snapshot / "helpers/artifacts").glob("ca-artifact-*"))
            self.assertEqual(len(binaries), 1)
            self.assertGreater(binaries[0].stat().st_size, 0)
            return SimpleNamespace(returncode=0, stdout=b'{"spec": {}, "plan": {}}')
        with tempfile.TemporaryDirectory() as directory, patch("academy_engine.native_planning.subprocess.run", side_effect=run):
            inspect_pair(Path(directory), plugin, "academy-feature", b"inert", b"inert")

    def test_real_writer_pair_is_readable_and_tampering_fails_without_mutating_the_source(self):
        from academy_engine.native_planning import NativePlanningError, inspect_pair
        from tests.native_planning_fixture import create_pair

        plugin = Path(os.environ["ARBITER_ACADEMY_TEST_PLUGIN_ROOT"])
        for slug in ("academy-feature", "academy-sprint"):
            with self.subTest(slug=slug), tempfile.TemporaryDirectory() as directory:
                root = Path(directory).resolve()
                spec, plan = create_pair(plugin, root, slug)
                before = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
                result = inspect_pair(root, plugin, slug, spec, plan)
                self.assertTrue(any(item["kind"] == "criteria" for item in result["spec"]["records"]))
                self.assertTrue(any(item["kind"] == "tasks" for item in result["plan"]["records"]))
                with self.assertRaises(NativePlanningError):
                    inspect_pair(root, plugin, slug, spec.replace(b"Academy", b"Changed", 1), plan)
                self.assertEqual(before, {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()})

    def test_unfinished_drafts_are_not_ready_for_the_lesson_checkpoint(self):
        from academy_engine.native_planning import NativePlanningError, inspect_pair
        from tests.native_planning_fixture import client

        plugin = Path(os.environ["ARBITER_ACADEMY_TEST_PLUGIN_ROOT"])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            engine = client(plugin, root)
            for kind in ("spec", "plan"):
                request = {"operation_id": "draft-fixture-" + kind, "kind": kind, "artifact_id": kind.upper() + "-DRAFT", "slug": "academy-feature", "title": "Incomplete draft", "summary": "An unfinished working draft is valid but not ready."}
                if kind == "plan":
                    request["spec_id"] = "SPEC-DRAFT"
                engine.call("create", request)
            with self.assertRaises(NativePlanningError):
                inspect_pair(root, plugin, "academy-feature",
                             (root / ".codearbiter/specs/academy-feature.html").read_bytes(),
                             (root / ".codearbiter/plans/academy-feature.html").read_bytes())
