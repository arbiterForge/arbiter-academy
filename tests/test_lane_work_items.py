"""Lanes that record a work item must still pass their Academy Check.

From codeArbiter 3.3, the fix and feature lanes record an actionable change as one
stable work item. On a legacy board that is one queued row with detail bullets,
and commit-gate keeps it in the work commit. These tests write the row with the
reviewed producer's own work facade, so a re-pinned cohort that changes the row
format fails here instead of in a learner's Check.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from academy_engine.checkpoints import _Attempt, _p01_board_transition, evaluate_checkpoint
from tests import test_checkpoints as checkpoints
from tests import test_current_plugin_workflows as workflows
from tests import test_foundations_labs as foundations

BOARD = ".codearbiter/open-tasks.md"
F04_TITLE = "Reject control characters in a claimant label"


def work_facade() -> Path:
    writer = foundations.pinned_task_writer()[0]
    facade = writer.parent / "work.py"
    if not facade.is_file():
        raise AssertionError("the reviewed codeArbiter source has no work facade")
    return facade


def run_work(root: Path, *arguments: str) -> dict[str, object]:
    result = subprocess.run(
        [sys.executable, "-I", str(work_facade()), *arguments],
        cwd=root,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(f"work facade refused {arguments[0]}: {result.stdout}{result.stderr}")
    return json.loads(result.stdout)


def create_item(root: Path, title: str, *, work_type: str = "fix", operation: str = "academy-lane") -> str:
    created = run_work(
        root, "create", "--type", work_type, "--title", title, "--intent", title,
        "--operation-id", operation,
    )
    return str(created["work_id"])


class FixLaneWorkItemTests(unittest.TestCase):
    def green_f04(self) -> foundations.AcademyRepository:
        fixture = foundations.FoundationsCheckpointMatrixTests()._prepared("F04-fix-with-evidence")
        self.addCleanup(fixture.close)
        workflows.write_f04_green_change(self, fixture.root)
        return fixture

    def test_f04_accepts_the_queued_fix_item_riding_the_green_commit(self) -> None:
        fixture = self.green_f04()
        create_item(fixture.root, F04_TITLE)
        fixture.commit("fix: validate claimant labels", "tests/test_service.py", "workshop_queue/service.py", BOARD)
        self.assertTrue(evaluate_checkpoint(fixture.root, "F04-fix-with-evidence").passed)

    def test_f04_rejects_board_changes_beyond_one_queued_fix_item(self) -> None:
        def second_item(root: Path) -> None:
            create_item(root, F04_TITLE)
            create_item(root, "Also reject tabs", operation="academy-lane-2")

        def feature_item(root: Path) -> None:
            create_item(root, F04_TITLE, work_type="feature")

        def started_item(root: Path) -> None:
            work_id = create_item(root, F04_TITLE)
            run_work(root, "start", work_id, "--operation-id", "academy-start")

        def unrelated_line(root: Path) -> None:
            create_item(root, F04_TITLE)
            board = root / BOARD
            text = board.read_text(encoding="utf-8")
            first = next(line for line in text.splitlines() if line.startswith("- ["))
            board.write_bytes(text.replace(first, first + " (edited)", 1).encode("utf-8"))

        for name, mutate in (
            ("second item", second_item),
            ("feature item", feature_item),
            ("started item", started_item),
            ("unrelated line", unrelated_line),
        ):
            with self.subTest(mutant=name):
                fixture = self.green_f04()
                mutate(fixture.root)
                fixture.commit("fix: validate claimant labels", "tests/test_service.py", "workshop_queue/service.py", BOARD)
                self.assertFalse(evaluate_checkpoint(fixture.root, "F04-fix-with-evidence").passed)

    def test_f04_rejects_the_fix_item_left_out_of_the_commit(self) -> None:
        fixture = self.green_f04()
        create_item(fixture.root, F04_TITLE)
        fixture.commit("fix: validate claimant labels", "tests/test_service.py", "workshop_queue/service.py")
        self.assertFalse(evaluate_checkpoint(fixture.root, "F04-fix-with-evidence").passed)

    def test_p05_accepts_the_queued_fix_item_riding_the_repair_commit(self) -> None:
        for work_type, expected in (("fix", True), ("feature", False)):
            with self.subTest(work_type=work_type):
                helper = checkpoints.CheckpointTests()
                helper.setUp()
                self.addCleanup(helper.tearDown)

                def record_item(root: Path) -> None:
                    # A learner clone ignores the board writer's lock through Academy's .gitignore.
                    with (root / ".git/info/exclude").open("a", encoding="utf-8") as exclude:
                        exclude.write(f"\n{BOARD}.lock\n")
                    create_item(root, "Treat blocked tickets as unresolved", work_type=work_type)

                history = workflows.current_p05_history(
                    helper,
                    before_repair=record_item,
                    repair_paths=("tests/test_cli.py", "workshop_queue/cli.py", BOARD),
                )
                self.assertIs(helper._p05_semantic(history), expected)

    def test_academy_ignores_the_board_writer_lock(self) -> None:
        ignored = subprocess.run(
            ["git", "check-ignore", "--no-index", "-q", f"{BOARD}.lock"],
            cwd=foundations.SOURCE,
            check=False,
        )
        self.assertEqual(ignored.returncode, 0)


P01_SEED = foundations.SOURCE / "academy/scenarios/P01-feature-through-plan/files/open-tasks.md"
P01_TASK = "academy.feature.0002"
P01_IDS = {"spec": "SPEC-ACADEMY-FEATURE", "plan": "PLAN-ACADEMY-FEATURE"}


class FeatureLaneWorkItemTests(unittest.TestCase):
    """P01 starts its seeded row; the 3.8.3 feature lane may also record its own item."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(foundations.cleanup_temporary_directory, self.temporary)
        self.root = Path(self.temporary.name) / "learner"
        (self.root / ".codearbiter").mkdir(parents=True)
        (self.root / BOARD).write_bytes(P01_SEED.read_bytes())
        (self.root / ".gitignore").write_text(f"{BOARD}.lock\n", encoding="utf-8")
        for arguments in (("init", "-b", "main"), ("config", "user.name", "Academy Learner"),
                          ("config", "user.email", "learner@example.invalid"), ("add", "."),
                          ("commit", "-m", "prepared")):
            foundations.git(self.root, *arguments)
        self.prepared = foundations.git(self.root, "rev-parse", "HEAD").stdout.strip()

    def start_seeded_task(self) -> None:
        writer = foundations.pinned_task_writer()[0]
        subprocess.run([sys.executable, "-I", str(writer), "start", P01_TASK], cwd=self.root,
                       check=True, capture_output=True)

    def record_feature(self, *, spec: str = P01_IDS["spec"], plan: str = P01_IDS["plan"],
                       work_type: str = "feature", origin: str | None = None) -> str:
        created = run_work(
            self.root, "create", "--type", work_type, "--title", "Show unresolved tickets in the summary",
            "--intent", "Show unresolved tickets in the summary", "--spec-id", spec,
            "--origin", origin or f"feature-spec#{spec}",
        )
        work_id = str(created["work_id"])
        run_work(self.root, "attach", work_id, "--plan-id", plan, "--operation-id", f"attach-{work_id}")
        return work_id

    def transition(self) -> bool:
        foundations.git(self.root, "add", BOARD)
        foundations.git(self.root, "commit", "-m", "feat: unresolved summary")
        head = foundations.git(self.root, "rev-parse", "HEAD").stdout.strip()
        attempt = _Attempt("academy/P01-feature-through-plan/1", 1, self.prepared, self.prepared, head)
        return _p01_board_transition(self.root, attempt, BOARD, P01_TASK, P01_IDS)

    def test_p01_accepts_the_start_flip_alone(self) -> None:
        self.start_seeded_task()
        self.assertTrue(self.transition())

    def test_p01_accepts_the_start_flip_with_the_lanes_bound_feature_item(self) -> None:
        self.start_seeded_task()
        self.record_feature()
        self.assertTrue(self.transition())

    def test_p01_rejects_a_feature_item_that_names_another_spec_or_plan(self) -> None:
        for name, kwargs in (("spec", {"spec": "SPEC-OTHER"}), ("plan", {"plan": "PLAN-OTHER"})):
            with self.subTest(mismatch=name):
                self.setUp()
                self.start_seeded_task()
                self.record_feature(**kwargs)
                self.assertFalse(self.transition())

    def test_p01_rejects_other_board_shapes(self) -> None:
        def second_item() -> None:
            self.start_seeded_task()
            self.record_feature()
            run_work(self.root, "create", "--type", "feature", "--title", "Another", "--intent", "Another",
                     "--operation-id", "another")

        def fix_item() -> None:
            self.start_seeded_task()
            self.record_feature(work_type="fix")

        def started_item() -> None:
            self.start_seeded_task()
            work_id = self.record_feature()
            run_work(self.root, "start", work_id, "--operation-id", "start-new")

        def no_start() -> None:
            self.record_feature()

        for name, mutate in (("second item", second_item), ("fix item", fix_item),
                             ("started item", started_item), ("no start flip", no_start)):
            with self.subTest(mutant=name):
                self.setUp()
                mutate()
                self.assertFalse(self.transition())


class SprintLaneWorkItemTests(unittest.TestCase):
    @unittest.skipUnless(os.environ.get("ARBITER_ACADEMY_TEST_PLUGIN_ROOT"), "requires reviewed installed producer")
    def test_u01_accepts_the_queued_sprint_item_bound_to_its_native_pair(self) -> None:
        from tests import test_power_user_u01 as u01

        for spec, expected in (("SPEC-ACADEMY-FIXTURE", True), ("SPEC-OTHER", False)):
            with self.subTest(spec=spec), tempfile.TemporaryDirectory() as directory:
                root = Path(directory) / "learner"
                plugin = u01.write_native_sprint_packet(root)
                with (root / ".git/info/exclude").open("a", encoding="utf-8") as exclude:
                    exclude.write(f"\n{BOARD}.lock\n")
                created = run_work(
                    root, "create", "--type", "feature", "--title", "Operate a bounded autonomous sprint",
                    "--intent", "Write the operator guide", "--spec-id", spec, "--origin", f"feature-spec#{spec}",
                )
                run_work(root, "attach", str(created["work_id"]), "--plan-id", "PLAN-ACADEMY-FIXTURE",
                         "--operation-id", "attach-sprint")
                u01.commit_native_sprint_packet(root, BOARD)
                self.assertIs(evaluate_checkpoint(root, "U01-autonomous-sprint", plugin_root=plugin).passed, expected)


if __name__ == "__main__":
    unittest.main()
