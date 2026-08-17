from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from academy_engine.checkpoints import Predicate, _Attempt, _SemanticContext, _semantic
from academy_engine.lesson_actions import load_action_manifest
from academy_engine.preview import load_preview_manifest
from academy_engine import curriculum


SOURCE = Path(__file__).parents[1]
U05 = "U05-debug-spike-conflict"
U05_RELEASED_INTEGRATION = (
    "matching released integration: CodeArbiter 2.15.1 (Claude); ca-codex 0.7.2 (Codex); "
    "or ca-pi 0.8.1 (Pi)"
)


class U05PluginContractTests(unittest.TestCase):
    """U05 accepts real plugin outputs, never a retained Academy-only spike ref."""

    data = {
        "profile": "debug_spike_conflict",
        "spike": ".codearbiter/spikes/u05-cache-key.md",
        "board": ".codearbiter/open-tasks.md",
        "observation": "docs/U05-cache-key-observation.md",
    }

    def git(self, root: Path, *args: str) -> str:
        return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True).stdout.strip()

    def context(
        self,
        root: Path,
        *,
        retain_spike: bool = False,
        copy_spike_code: bool = False,
        leave_untracked_spike_code: bool = False,
        split_debug_metadata: bool = False,
        include_observation: bool = True,
        include_spike_question: bool = True,
        include_extra_debug_note: bool = False,
        idless_debug_note: bool = False,
        collapse_evidence_into_one_commit: bool = False,
    ) -> _SemanticContext:
        (root / ".codearbiter/spikes").mkdir(parents=True)
        initial_board = (
            "# Open tasks\n\n## Queued\n\n"
            "- [ ] academy.fixture.0001 - preserve this prepared task\n"
            "  - Desc: Academy control state\n"
        )
        (root / ".codearbiter/open-tasks.md").write_text(initial_board, encoding="utf-8")
        if include_observation:
            (root / "docs").mkdir()
            observation = (
                "# U05 cache-key observation\n\n"
                "## Observed behavior\nFixture observation.\n\n"
                "## Reproduction\nRead-only evidence.\n\n"
                "## Expected behavior\nNo code change.\n"
            )
            if include_spike_question:
                observation += "\n## Spike question\nWhich cache key is stale?\n"
            (root / "docs/U05-cache-key-observation.md").write_text(observation, encoding="utf-8")
        self.git(root, "init", "-b", "main")
        self.git(root, "config", "user.name", "Academy Learner")
        self.git(root, "config", "user.email", "learner@example.invalid")
        self.git(root, "add", ".")
        self.git(root, "commit", "-m", "academy: prepare U05")
        prepared = self.git(root, "rev-parse", "HEAD")
        self.git(root, "switch", "-c", "academy/U05-debug-spike-conflict/1")
        board = initial_board + "## In-flight\n"
        board += (
            "- [ ] U05 cache-key observation\n"
            "  - Desc: cited read-only trace\n"
            if idless_debug_note
            else "- [ ] debug.note.0001 - U05 cache-key investigation closed without code changes\n"
            "  - Desc: cited read-only trace\n"
        )
        if split_debug_metadata:
            board = (
                "# Open tasks\n\n## In-flight\n\n"
                "- [ ] debug.note.0001 - U05 cache-key investigation\n"
                "  - Context: cited read-only trace\n"
                "- [ ] maintenance.note.0001 - unrelated work closed without code changes\n"
                "  - Desc: unrelated maintenance\n"
            )
        elif include_extra_debug_note:
            board += (
                "- [ ] debug.note.0002 - unrelated investigation closed without code changes\n"
                "  - Desc: unrelated evidence\n"
            )
        (root / ".codearbiter/open-tasks.md").write_text(board, encoding="utf-8")
        if collapse_evidence_into_one_commit:
            (root / ".codearbiter/spikes/u05-cache-key.md").write_text(
                "# Cache-key spike\n\n## Question\nWhich cache key is stale?\n\n## What tried\nRead-only trace.\n\n## Answer\nThe tenant key is omitted.\n\n## Implication\nRoute a fix through $ca-fix.\n",
                encoding="utf-8",
            )
            if copy_spike_code:
                (root / "exploratory_spike.py").write_text("unsafe exploratory code\n", encoding="utf-8")
            paths = [".codearbiter"]
            if copy_spike_code:
                paths.append("exploratory_spike.py")
            self.git(root, "add", *paths)
            self.git(root, "commit", "-m", "docs: retain U05 findings")
        else:
            self.git(root, "add", ".codearbiter/open-tasks.md")
            self.git(root, "commit", "-m", "docs: close U05 debug investigation")
            self.git(root, "switch", "-c", "spike/u05-cache-key")
            (root / ".codearbiter/spikes/u05-cache-key.md").write_text(
                "# Cache-key spike\n\n## Question\nWhich cache key is stale?\n\n## What tried\nRead-only trace.\n\n## Answer\nThe tenant key is omitted.\n\n## Implication\nRoute a fix through $ca-fix.\n",
                encoding="utf-8",
            )
            self.git(root, "add", ".codearbiter/spikes/u05-cache-key.md")
            self.git(root, "commit", "-m", "docs: record U05 spike findings")
            self.git(root, "switch", "academy/U05-debug-spike-conflict/1")
            self.git(root, "restore", "--source", "spike/u05-cache-key", "--", ".codearbiter/spikes/u05-cache-key.md")
            if copy_spike_code:
                (root / "exploratory_spike.py").write_text("unsafe exploratory code\n", encoding="utf-8")
            paths = [".codearbiter/spikes/u05-cache-key.md"]
            if copy_spike_code:
                paths.append("exploratory_spike.py")
            self.git(root, "add", *paths)
            self.git(root, "commit", "-m", "docs: retain U05 findings")
            if not retain_spike:
                self.git(root, "branch", "-D", "spike/u05-cache-key")
        head = self.git(root, "rev-parse", "HEAD")
        if leave_untracked_spike_code:
            (root / "exploratory_spike.py").write_text("unsafe exploratory code\n", encoding="utf-8")
        if retain_spike and collapse_evidence_into_one_commit:
            self.git(root, "branch", "spike/u05-cache-key", head)
        return _SemanticContext(root, _Attempt("academy/U05-debug-spike-conflict/1", 1, prepared, prepared, head), Predicate("u05", "lab_semantics", self.data))

    def test_accepts_real_findings_and_no_action_board_exit_after_spike_deletion(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            self.assertTrue(_semantic(self.context(Path(directory))))

    def test_accepts_the_idless_taskwrite_no_action_close(self) -> None:
        """ca-debug may use taskwrite without the optional --id debug.note."""
        with tempfile.TemporaryDirectory() as directory:
            self.assertTrue(_semantic(self.context(Path(directory), idless_debug_note=True)))

    def test_rejects_a_retained_real_spike_branch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            self.assertFalse(_semantic(self.context(Path(directory), retain_spike=True)))

    def test_rejects_spike_code_copied_into_the_parent_attempt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            self.assertFalse(_semantic(self.context(Path(directory), copy_spike_code=True)))

    def test_rejects_uncommitted_exploratory_spike_code_after_valid_findings(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            self.assertFalse(_semantic(self.context(Path(directory), leave_untracked_spike_code=True)))

    def test_rejects_debug_metadata_separated_from_its_no_action_entry(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            self.assertFalse(_semantic(self.context(Path(directory), split_debug_metadata=True)))

    def test_rejects_a_generic_spike_and_board_without_the_prepared_observation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            self.assertFalse(_semantic(self.context(Path(directory), include_observation=False)))

    def test_rejects_an_observation_without_the_declared_spike_question(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            self.assertFalse(_semantic(self.context(Path(directory), include_spike_question=False)))

    def test_rejects_a_second_taskwrite_shaped_debug_note(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            self.assertFalse(_semantic(self.context(Path(directory), include_extra_debug_note=True)))

    def test_rejects_debug_and_spike_evidence_collapsed_into_one_commit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            self.assertFalse(
                _semantic(self.context(Path(directory), collapse_evidence_into_one_commit=True))
            )

    def test_allows_an_unrelated_spike_branch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            context = self.context(root)
            self.git(root, "branch", "spike/unrelated", context.attempt.head)
            self.assertTrue(_semantic(context))

    def test_public_cards_name_real_plugin_contracts_and_recovery(self) -> None:
        manifest = load_action_manifest(SOURCE, U05)
        by_id = {action.id: action for action in manifest.actions}
        self.assertEqual(tuple(by_id), (
            "U05-confirm-readiness", "U05-prepare-attempt", "U05-read-observation",
            "U05-run-debug", "U05-review-debug-board", "U05-commit-debug-board",
            "U05-run-spike", "U05-confirm-spike-question", "U05-transfer-findings", "U05-review-findings",
            "U05-commit-findings", "U05-delete-spike", "U05-halt-for-conflict",
            "U05-check-status", "U05-reset-retry",
        ))
        self.assertIn("taskwrite", by_id["U05-run-debug"].expected_result)
        self.assertIn("taskwrite", by_id["U05-run-debug"].rationale)
        self.assertIn("taskwrite", by_id["U05-commit-debug-board"].evidence or "")
        self.assertNotIn("debug-note", by_id["U05-commit-debug-board"].evidence or "")
        self.assertIn("U05 cache key", by_id["U05-run-spike"].instruction)
        self.assertIn("CodeArbiter 2.15.1", by_id["U05-confirm-readiness"].instruction)
        self.assertIn("ca-codex 0.7.2", by_id["U05-confirm-readiness"].instruction)
        self.assertIn("ca-pi 0.8.1", by_id["U05-confirm-readiness"].instruction)
        self.assertIn("confirm", by_id["U05-confirm-spike-question"].instruction.casefold())
        self.assertIn("pauses before creating", by_id["U05-run-spike"].expected_result)
        self.assertIn("commits only .codearbiter/spikes/u05-cache-key.md", by_id["U05-confirm-spike-question"].expected_result)
        self.assertIn("git restore --source spike/u05-cache-key", by_id["U05-transfer-findings"].variants[0].command)
        self.assertIn("git branch -D spike/u05-cache-key", by_id["U05-delete-spike"].variants[0].command)
        self.assertNotIn("git merge", by_id["U05-transfer-findings"].instruction.casefold())
        self.assertIn("stop", by_id["U05-halt-for-conflict"].expected_result.casefold())
        for action_id in ("U05-prepare-attempt", "U05-check-status", "U05-reset-retry"):
            self.assertEqual(
                tuple(variant.operating_system for variant in by_id[action_id].variants),
                ("windows", "macos", "linux"),
            )
            self.assertTrue(all("preview-0.30" in variant.command for variant in by_id[action_id].variants))
        check_variants = {variant.id: variant for variant in by_id["U05-check-status"].variants}
        self.assertEqual(set(check_variants), {"windows", "macos", "linux"})
        self.assertIn("check U05-debug-spike-conflict", check_variants["linux"].command)
        self.assertNotIn("prepare U05-debug-spike-conflict", check_variants["linux"].command)
        self.assertIn(
            "Next safe step: continue to U06.",
            by_id["U05-check-status"].expected_result,
        )
        self.assertNotIn(
            "when it is published",
            by_id["U05-check-status"].expected_result,
        )

    def test_public_guide_keeps_the_real_plugin_boundary_visible(self) -> None:
        guide = (SOURCE / "academy/tracks/power-user/U05-debug-spike-conflict.md").read_text(encoding="utf-8")
        lab = curriculum._parse_lab(SOURCE / "academy/tracks/power-user/U05-debug-spike-conflict.md")
        self.assertEqual(lab.id, U05)
        self.assertIn("released CodeArbiter contract", guide)
        self.assertIn("$ca-conflict", guide)
        self.assertIn("cannot prove an agent's private reasoning", guide)
        self.assertIn("{{action:U05-reset-retry}}", guide)

    def test_public_u05_cards_are_runnable_without_private_source_framing(self) -> None:
        """A released U05 must guide its accepted real-plugin lifecycle, not a refusal."""
        manifest = load_action_manifest(SOURCE, U05)
        by_id = {action.id: action for action in manifest.actions}

        self.assertTrue(all("Future private-source walkthrough only" not in action.instruction for action in manifest.actions))
        self.assertIn("creates a clean U05 attempt", by_id["U05-prepare-attempt"].expected_result)
        self.assertIn("evaluates the prepared U05 attempt", by_id["U05-check-status"].expected_result)
        self.assertNotIn("not published", by_id["U05-prepare-attempt"].expected_result.casefold())
        self.assertNotIn("not published", by_id["U05-check-status"].expected_result.casefold())


if __name__ == "__main__":
    unittest.main()
