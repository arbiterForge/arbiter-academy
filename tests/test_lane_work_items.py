"""Lanes that record a work item must still pass their Academy Check.

From codeArbiter 3.8, the fix, feature and sprint lanes record an actionable change
as one stable work item. On a legacy board that is one queued row with detail
bullets. These tests write the row with the reviewed producer's own work facade and
ask the producer's own commit-gate classifier whether it keeps each shape, so a
re-pinned cohort that changes the row format or what the gate keeps fails here
instead of in a learner's Check.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from academy_engine.checkpoints import (
    _Attempt,
    _one_queued_work_item_added,
    _p01_board_transition,
    evaluate_checkpoint,
)
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


def producer_keeps(before: bytes, after: bytes) -> bool:
    """Return whether the reviewed producer's commit-gate classifier keeps this board change."""
    source = foundations.pinned_task_writer()[0].parent
    result = subprocess.run(
        [
            sys.executable, "-I", "-c",
            "import json, sys; sys.path.insert(0, sys.argv[1]); import _taskboardlib as board; "
            "old, new = json.load(sys.stdin); print(json.dumps(board.classify_board_diff(old, new)))",
            str(source),
        ],
        input=json.dumps([before.decode("utf-8"), after.decode("utf-8")]),
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(f"producer classifier failed: {result.stdout}{result.stderr}")
    return json.loads(result.stdout) is True


class FixLaneWorkItemTests(unittest.TestCase):
    def green_f04(self) -> foundations.AcademyRepository:
        fixture = foundations.FoundationsCheckpointMatrixTests()._prepared("F04-fix-with-evidence")
        self.addCleanup(fixture.close)
        workflows.write_f04_green_change(self, fixture.root)
        return fixture

    def test_f04_accepts_the_queued_fix_item_riding_the_green_commit(self) -> None:
        fixture = self.green_f04()
        before = (fixture.root / BOARD).read_bytes()
        create_item(fixture.root, F04_TITLE)
        self.assertTrue(producer_keeps(before, (fixture.root / BOARD).read_bytes()))
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
                    before = (root / BOARD).read_bytes()
                    create_item(root, "Treat blocked tickets as unresolved", work_type=work_type)
                    self.assertTrue(producer_keeps(before, (root / BOARD).read_bytes()))

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


def legacy_repository(case: unittest.TestCase, seed: bytes) -> Path:
    temporary = tempfile.TemporaryDirectory()
    case.addCleanup(foundations.cleanup_temporary_directory, temporary)
    root = Path(temporary.name) / "learner"
    (root / ".codearbiter").mkdir(parents=True)
    (root / BOARD).write_bytes(seed)
    (root / ".gitignore").write_text(f"{BOARD}.lock\n", encoding="utf-8")
    for arguments in (("init", "-b", "main"), ("config", "user.name", "Academy Learner"),
                      ("config", "user.email", "learner@example.invalid"), ("add", "."),
                      ("commit", "-m", "prepared")):
        foundations.git(root, *arguments)
    return root


def record_bound_item(root: Path, *, spec: str | None, plan: str | None, work_type: str = "feature") -> str:
    arguments = ["create", "--type", work_type, "--title", "Show unresolved tickets in the summary",
                 "--intent", "Show unresolved tickets in the summary"]
    if spec is not None:
        arguments += ["--spec-id", spec, "--origin", f"feature-spec#{spec}"]
    else:
        arguments += ["--operation-id", "academy-unbound"]
    work_id = str(run_work(root, *arguments)["work_id"])
    if plan is not None:
        run_work(root, "attach", work_id, "--plan-id", plan, "--operation-id", f"attach-{work_id}")
    return work_id


class FeatureLaneWorkItemTests(unittest.TestCase):
    """P01 starts its seeded row and records no other work item.

    The 3.8.3 commit gate keeps a start flip or a new item, never both in one commit
    (arbiterForge/codeArbiter#1089), so P01 asks the feature lane not to record one.
    """

    def setUp(self) -> None:
        self.root = legacy_repository(self, P01_SEED.read_bytes())
        self.prepared = foundations.git(self.root, "rev-parse", "HEAD").stdout.strip()

    def start_seeded_task(self) -> None:
        writer = foundations.pinned_task_writer()[0]
        subprocess.run([sys.executable, "-I", str(writer), "start", P01_TASK], cwd=self.root,
                       check=True, capture_output=True)

    def transition(self) -> bool:
        foundations.git(self.root, "add", BOARD)
        foundations.git(self.root, "commit", "-m", "feat: unresolved summary")
        head = foundations.git(self.root, "rev-parse", "HEAD").stdout.strip()
        attempt = _Attempt("academy/P01-feature-through-plan/1", 1, self.prepared, self.prepared, head)
        return _p01_board_transition(self.root, attempt, BOARD, P01_TASK)

    def test_p01_accepts_the_start_flip_the_gate_keeps(self) -> None:
        before = (self.root / BOARD).read_bytes()
        self.start_seeded_task()
        self.assertTrue(producer_keeps(before, (self.root / BOARD).read_bytes()))
        self.assertTrue(self.transition())

    def test_p01_rejects_the_lanes_own_item_beside_the_start(self) -> None:
        """When the gate learns to keep this shape, the first assertion fails and P01 can be revisited."""
        before = (self.root / BOARD).read_bytes()
        self.start_seeded_task()
        record_bound_item(self.root, spec=P01_IDS["spec"], plan=P01_IDS["plan"])
        self.assertFalse(producer_keeps(before, (self.root / BOARD).read_bytes()))
        self.assertFalse(self.transition())


SHAPE_SEED = (
    b"# Open tasks\n\n## In-flight\n\n"
    b"- [ ] academy.feature.0001 - Show totals\n"
    b"  - Desc: Count every ticket\n"
    b"  - Boundaries: CLI, local JSON\n\n"
    b"## Blocked\n\n"
    b"- [ ] academy.docs.0009 - Waiting on review\n"
)
NO_IN_FLIGHT_SEED = b"# Open tasks\n\n## Blocked\n\n- [ ] academy.docs.0009 - Waiting on review\n"
FIX = frozenset({"fix"})
SPRINT = frozenset({"feature", "chore"})


class WorkItemShapeTests(unittest.TestCase):
    """The verifier accepts the producer's own rows, only where the producer writes them."""

    def recorded(self, seed: bytes, record) -> bytes:
        root = legacy_repository(self, seed)
        record(root)
        return (root / BOARD).read_bytes()

    def test_origins_with_spaces_are_accepted_as_the_producer_writes_them(self) -> None:
        for name, arguments in (
            ("origin", ("--origin", "F04 claimant defect")),
            ("operation", ("--operation-id", "fix claimant labels")),
        ):
            with self.subTest(source=name):
                after = self.recorded(SHAPE_SEED, lambda root: run_work(
                    root, "create", "--type", "fix", "--title", F04_TITLE, "--intent", F04_TITLE, *arguments))
                self.assertIn(b"  (from ", after)
                self.assertTrue(producer_keeps(SHAPE_SEED, after))
                self.assertTrue(_one_queued_work_item_added(SHAPE_SEED, after, FIX))

    def test_a_board_without_in_flight_gains_the_heading_and_the_row(self) -> None:
        after = self.recorded(NO_IN_FLIGHT_SEED, lambda root: create_item(root, F04_TITLE))
        self.assertTrue(after.startswith(NO_IN_FLIGHT_SEED + b"## In-flight\n- [ ] "))
        self.assertTrue(producer_keeps(NO_IN_FLIGHT_SEED, after))
        self.assertTrue(_one_queued_work_item_added(NO_IN_FLIGHT_SEED, after, FIX))

    def test_the_row_must_sit_where_the_producer_writes_it(self) -> None:
        after = self.recorded(SHAPE_SEED, lambda root: create_item(root, F04_TITLE))
        self.assertTrue(_one_queued_work_item_added(SHAPE_SEED, after, FIX))
        heading = b"## In-flight\n"
        insertion = SHAPE_SEED.index(heading) + len(heading)
        block = after[insertion:insertion + len(after) - len(SHAPE_SEED)]
        self.assertEqual(SHAPE_SEED.replace(heading, heading + block, 1), after)
        row = b"- [ ] academy.feature.0001 - Show totals\n"
        no_heading_block = self.recorded(NO_IN_FLIGHT_SEED, lambda root: create_item(root, F04_TITLE))[len(NO_IN_FLIGHT_SEED):]
        stray = b"# Open tasks\n\n## In-flight\n  - Desc: stray detail\n"
        for name, before, moved in (
            ("above a stray detail bullet it would adopt", stray, stray.replace(heading, heading + block, 1)),
            ("inside another task's bullets", SHAPE_SEED, SHAPE_SEED.replace(row, row + block, 1)),
            ("appended at the end", SHAPE_SEED, SHAPE_SEED + block),
            ("new heading before Blocked", NO_IN_FLIGHT_SEED,
             NO_IN_FLIGHT_SEED.replace(b"## Blocked\n", no_heading_block + b"## Blocked\n", 1)),
            ("empty prior board", b"", no_heading_block),
        ):
            with self.subTest(position=name):
                self.assertFalse(_one_queued_work_item_added(before, moved, FIX))

    def test_a_lesson_bound_to_a_native_pair_requires_both_artifact_ids(self) -> None:
        for name, spec, plan, expected in (
            ("spec and plan", P01_IDS["spec"], P01_IDS["plan"], True),
            ("spec only", P01_IDS["spec"], None, False),
            ("neither", None, None, False),
            ("another spec", "SPEC-OTHER", P01_IDS["plan"], False),
            ("another plan", P01_IDS["spec"], "PLAN-OTHER", False),
        ):
            with self.subTest(binding=name):
                after = self.recorded(SHAPE_SEED, lambda root: record_bound_item(root, spec=spec, plan=plan))
                if expected:
                    self.assertTrue(producer_keeps(SHAPE_SEED, after))
                self.assertIs(_one_queued_work_item_added(SHAPE_SEED, after, SPRINT, P01_IDS), expected)


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
