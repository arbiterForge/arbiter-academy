"""Lanes that record a work item must still pass their Academy Check.

From codeArbiter 3.3, the fix and feature lanes record an actionable change as one
stable work item. On a legacy board that is one queued row with detail bullets,
and commit-gate keeps it in the work commit. These tests write the row with the
reviewed producer's own work facade, so a re-pinned cohort that changes the row
format fails here instead of in a learner's Check.
"""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

from academy_engine.checkpoints import evaluate_checkpoint
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


if __name__ == "__main__":
    unittest.main()
