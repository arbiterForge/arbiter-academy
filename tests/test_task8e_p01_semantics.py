from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from academy_engine.checkpoints import CheckpointError, Predicate, _Attempt, _SemanticContext, _semantic, load_checkpoint
from academy_engine.scenario import prepare_lab
from tests._temporary import RetryingTemporaryDirectory


SOURCE = Path(__file__).resolve().parents[1]


def git(root: Path, *arguments: str, env: dict[str, str] | None = None) -> str:
    result = subprocess.run(
        ["git", *arguments],
        cwd=root,
        text=True,
        encoding="utf-8",
        capture_output=True,
        env=None if env is None else {**os.environ, **env},
        check=True,
    )
    return result.stdout.strip()


class P01PreparationSemanticsTests(unittest.TestCase):
    def test_feature_checkpoint_accepts_one_bounded_final_commit_without_executing_learner_code(self) -> None:
        """Catches a feature checkpoint that cannot verify the native one-commit contract."""
        with RetryingTemporaryDirectory() as directory:
            root = Path(directory) / "learner"
            root.mkdir()
            for path in ("academy", ".codearbiter", "data", "workshop_queue"):
                shutil.copytree(SOURCE / path, root / path)
            (root / "tests").mkdir()
            shutil.copy2(SOURCE / "tests/test_cli.py", root / "tests/test_cli.py")
            git(root, "init", "-b", "main")
            git(root, "config", "user.name", "Academy Learner")
            git(root, "config", "user.email", "learner@example.invalid")
            git(root, "add", ".")
            git(root, "commit", "-m", "base")
            git(root, "remote", "add", "origin", "https://github.com/learner/arbiter-academy.git")
            git(root, "remote", "add", "upstream", "https://github.com/arbiterForge/arbiter-academy.git")
            git(root, "remote", "set-url", "--push", "upstream", "DISABLED")
            prepared = prepare_lab(root, "P01-feature-through-plan")

            (root / ".codearbiter/specs").mkdir(exist_ok=True)
            (root / ".codearbiter/plans").mkdir(exist_ok=True)
            (root / ".codearbiter/specs/academy-feature.md").write_text(
                "# Unresolved ticket report\n\n## Problem\nThe Workshop Queue JSON report lacks an unresolved count.\n\n"
                "## Scope\nJSON report behavior in workshop_queue/cli.py and verification in tests/test_cli.py only; "
                "exclude text-output changes, lifecycle changes, storage changes, dependencies, network behavior, credentials, and real personal data.\n\n"
                "## Acceptance criteria\n1. The JSON report adds integer unresolved equal to open + claimed.\n"
                "2. Existing integer open, claimed, and completed counts remain exact, and completed tickets do not contribute to unresolved.\n\n"
                "## Open questions\nNone.\n",
                encoding="utf-8",
            )
            (root / ".codearbiter/plans/academy-feature.md").write_text(
                "# Academy feature plan\n\n## Acceptance criteria ledger\n"
                "- AC-01: The JSON report adds integer unresolved equal to open + claimed.\n"
                "- AC-02: Existing integer open, claimed, and completed counts remain exact, and completed tickets do not contribute to unresolved.\n\n"
                "## Tasks\n| ID | Path(s) | Verification | Maps to | Covers | Depends on | Status |\n"
                "| --- | --- | --- | --- | --- | --- | --- |\n"
                "| T-01 | tests/test_cli.py | focused unresolved-summary test | AC-01, AC-02 | AC-01, AC-02 | none | ACCEPTED |\n"
                "| T-02 | workshop_queue/cli.py | focused unresolved-summary test; python -m unittest discover -v; python -m compileall workshop_queue tests | AC-01, AC-02 | AC-01, AC-02 | T-01 | ACCEPTED |\n\n"
                "## MVP slice\nT-01 through T-02\n",
                encoding="utf-8",
            )
            board = root / ".codearbiter/open-tasks.md"
            board.write_text(
                board.read_text(encoding="utf-8").replace(
                    "- [ ] academy.feature.0002 - Show unresolved tickets in the summary",
                    "- [~] academy.feature.0002 - Show unresolved tickets in the summary  (started 2026-08-04)",
                ),
                encoding="utf-8",
            )
            test_path = root / "tests/test_cli.py"
            test_path.write_text(
                test_path.read_text(encoding="utf-8").replace(
                    "    def test_list_json_is_machine_readable(self) -> None:\n",
                    "    def test_report_json_counts_open_and_claimed_as_unresolved(self) -> None:\n"
                    "        result = self.run_cli_for(\n"
                    "            self.data_root / \"p01-unresolved-tickets.json\",\n"
                    "            \"report\",\n"
                    "            \"--format\",\n"
                    "            \"json\",\n"
                    "        )\n"
                    "        self.assertEqual(result.returncode, 0, result.stderr)\n"
                    "        self.assertEqual(\n"
                    "            json.loads(result.stdout),\n"
                    "            {\"claimed\": 1, \"completed\": 1, \"open\": 1, \"unresolved\": 2},\n"
                    "        )\n\n"
                    "    def test_list_json_is_machine_readable(self) -> None:\n",
                ),
                encoding="utf-8",
            )
            cli = root / "workshop_queue/cli.py"
            cli.write_text(
                cli.read_text(encoding="utf-8").replace(
                    '    counts = {status.value: sum(ticket.status is status for ticket in tickets) for status in TicketStatus}\n',
                    '    counts = {status.value: sum(ticket.status is status for ticket in tickets) for status in TicketStatus}\n'
                    '    counts["unresolved"] = (\n'
                    '        counts[TicketStatus.OPEN.value]\n'
                    '        + counts[TicketStatus.CLAIMED.value]\n'
                    '    )\n',
                ),
                encoding="utf-8",
            )
            git(root, "add", ".codearbiter/specs/academy-feature.md", ".codearbiter/plans/academy-feature.md", ".codearbiter/open-tasks.md", "tests/test_cli.py", "workshop_queue/cli.py")
            git(
                root,
                "commit",
                "-m",
                "feat: add unresolved summary",
                env={
                    "GIT_AUTHOR_DATE": "2026-08-04T12:00:00+00:00",
                    "GIT_COMMITTER_DATE": "2026-08-04T12:00:00+00:00",
                },
            )
            head = git(root, "rev-parse", "HEAD")
            predicate = Predicate(
                "feature_spec_plan_commit",
                "lab_semantics",
                {
                    "profile": "feature_spec_plan",
                    "spec": ".codearbiter/specs/academy-feature.md",
                    "plan": ".codearbiter/plans/academy-feature.md",
                    "board": ".codearbiter/open-tasks.md",
                    "test": "tests/test_cli.py",
                    "code": "workshop_queue/cli.py",
                    "fixture": "data/p01-unresolved-tickets.json",
                    "source_identity": "training_scenarios/P01-codearbiter-source.json",
                    "task_id": "academy.feature.0002",
                },
            )
            attempt = _Attempt(prepared.branch, 1, prepared.commit_sha, prepared.base_sha, head)

            self.assertTrue(_semantic(_SemanticContext(root, attempt, predicate)))

    def test_feature_profile_exposes_the_complete_one_commit_semantic_boundary(self) -> None:
        """Catches the old profile that cannot bind the final P01 learner artifact set."""
        definition = {
            "schema_version": 2,
            "id": "P01-feature-through-plan",
            "predicates": [
                {
                    "id": "feature_spec_plan_commit",
                    "type": "lab_semantics",
                    "profile": "feature_spec_plan",
                    "spec": ".codearbiter/specs/academy-feature.md",
                    "plan": ".codearbiter/plans/academy-feature.md",
                    "board": ".codearbiter/open-tasks.md",
                    "test": "tests/test_cli.py",
                    "code": "workshop_queue/cli.py",
                    "fixture": "data/p01-unresolved-tickets.json",
                    "source_identity": "training_scenarios/P01-codearbiter-source.json",
                    "task_id": "academy.feature.0002",
                }
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "P01.json"
            path.write_text(json.dumps(definition), encoding="utf-8")
            try:
                checkpoint = load_checkpoint(path)
            except CheckpointError:
                checkpoint = None

        self.assertIsNotNone(checkpoint)
        self.assertEqual(checkpoint.predicates[0].id, "feature_spec_plan_commit")

    def test_prepare_materializes_the_complete_immutable_p01_semantic_inputs(self) -> None:
        """Catches a P01 prepare that omits the verifier-owned exercise inputs."""
        with RetryingTemporaryDirectory() as directory:
            root = Path(directory) / "learner"
            root.mkdir()
            shutil.copytree(SOURCE / "academy", root / "academy")
            shutil.copytree(SOURCE / ".codearbiter", root / ".codearbiter")
            git(root, "init", "-b", "main")
            git(root, "config", "user.name", "Academy Learner")
            git(root, "config", "user.email", "learner@example.invalid")
            git(root, "add", ".")
            git(root, "commit", "-m", "base")
            git(root, "remote", "add", "origin", "https://github.com/learner/arbiter-academy.git")
            git(root, "remote", "add", "upstream", "https://github.com/arbiterForge/arbiter-academy.git")
            git(root, "remote", "set-url", "--push", "upstream", "DISABLED")

            prepare_lab(root, "P01-feature-through-plan")

            board = (root / ".codearbiter/open-tasks.md").read_text(encoding="utf-8")
            fixture_path = root / "data/p01-unresolved-tickets.json"
            identity_path = root / "training_scenarios/P01-codearbiter-source.json"
            descriptor_path = root / "training_scenarios/P01-feature-through-plan.json"

            self.assertIn(
                "- [ ] academy.feature.0002 - Show unresolved tickets in the summary",
                board,
            )
            self.assertTrue(fixture_path.is_file())
            self.assertTrue(identity_path.is_file())
            self.assertTrue(descriptor_path.is_file())
            fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
            identity = json.loads(identity_path.read_text(encoding="utf-8"))
            descriptor = json.loads(descriptor_path.read_text(encoding="utf-8"))
            self.assertEqual([ticket["status"] for ticket in fixture], ["open", "claimed", "completed"])
            self.assertEqual(identity["repository"], "arbiterForge/codeArbiter")
            self.assertEqual(descriptor["target"], "workshop_queue/cli.py")


if __name__ == "__main__":
    unittest.main()
