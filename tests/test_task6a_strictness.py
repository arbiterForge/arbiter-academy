from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import academy_engine.exercise_state as exercise_module
from academy_engine.checkpoints import (
    Predicate,
    _Attempt,
    _SemanticContext,
    _remote_safe,
    _semantic,
)
from academy_engine.exercise_state import open_p08_store, preflight_p08, prepare_p08


def git(root: Path, *arguments: str, check: bool = True) -> str:
    result = subprocess.run(
        ["git", *arguments],
        cwd=root,
        text=True,
        capture_output=True,
        check=check,
    )
    return result.stdout.strip()


class SemanticStrictnessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        git(self.root, "init", "-b", "main")
        git(self.root, "config", "user.name", "Fixture")
        git(self.root, "config", "user.email", "fixture@example.invalid")
        (self.root / "README.md").write_text("base\n", encoding="utf-8")
        git(self.root, "add", ".")
        git(self.root, "commit", "-m", "base")
        self.base = git(self.root, "rev-parse", "HEAD")

    def commit(self, message: str) -> str:
        git(self.root, "add", ".")
        git(self.root, "commit", "--allow-empty", "-m", message)
        return git(self.root, "rev-parse", "HEAD")

    def p02_context(self, *, mode: str, reference: str) -> tuple[_SemanticContext, str]:
        context = self.root / ".codearbiter/CONTEXT.md"
        context.parent.mkdir()
        context.write_text("stage: 2\n", encoding="utf-8")
        self.base = self.commit("governed state")
        git(self.root, "remote", "add", "origin", "https://github.com/learner/arbiter-academy.git")
        git(self.root, "remote", "add", "upstream", "https://github.com/arbiterForge/arbiter-academy.git")
        git(self.root, "remote", "set-url", "--push", "upstream", "DISABLED")
        branch = "academy/P02-commit-review-pr/1"
        git(self.root, "switch", "-c", branch)
        prepared = self.commit("prepare")
        (self.root / "work.txt").write_text("reviewed\n", encoding="utf-8")
        work_head = self.commit("work")
        report = self.root / ".codearbiter/reports/academy/P02-pr-receipt.json"
        report.parent.mkdir(parents=True)
        report.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "receipt_id": "academy-1234",
                    "mode": mode,
                    "repository": "learner/arbiter-academy",
                    "branch": branch,
                    "prepared_base": prepared,
                    "work_head": work_head,
                    "commits": [work_head],
                    "review_status": "cleared",
                    "pr_reference": (
                        f"local-pr:{work_head[:12]}"
                        if reference == "LOCAL"
                        else reference
                    ),
                }
            ),
            encoding="utf-8",
        )
        head = self.commit("receipt")
        predicate = Predicate(
            "review_pr_commit_range",
            "lab_semantics",
            {"profile": "pr_receipt", "receipt": report.relative_to(self.root).as_posix()},
        )
        return (
            _SemanticContext(
                self.root,
                _Attempt(branch, 1, prepared, self.base, head),
                predicate,
            ),
            branch,
        )

    def test_p02_repository_must_match_the_validated_origin(self) -> None:
        context = self.root / ".codearbiter/CONTEXT.md"
        context.parent.mkdir()
        context.write_text("stage: 2\n", encoding="utf-8")
        self.base = self.commit("governed state")
        git(self.root, "remote", "add", "origin", "https://github.com/learner/arbiter-academy.git")
        git(self.root, "remote", "add", "upstream", "https://github.com/arbiterForge/arbiter-academy.git")
        git(self.root, "remote", "set-url", "--push", "upstream", "DISABLED")
        branch = "academy/P02-commit-review-pr/1"
        git(self.root, "switch", "-c", branch)
        prepared = self.commit("prepare")
        (self.root / "work.txt").write_text("reviewed\n", encoding="utf-8")
        work_head = self.commit("work")
        report = self.root / ".codearbiter/reports/academy/P02-pr-receipt.json"
        report.parent.mkdir(parents=True)
        report.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "receipt_id": "academy-1234",
                    "mode": "offline-local",
                    "repository": "different-owner/arbiter-academy",
                    "branch": branch,
                    "prepared_base": prepared,
                    "work_head": work_head,
                    "commits": [work_head],
                    "review_status": "cleared",
                    "pr_reference": f"local-pr:{work_head[:12]}",
                }
            ),
            encoding="utf-8",
        )
        head = self.commit("receipt")
        predicate = Predicate(
            "review_pr_commit_range",
            "lab_semantics",
            {"profile": "pr_receipt", "receipt": report.relative_to(self.root).as_posix()},
        )

        self.assertTrue(_remote_safe(self.root))
        self.assertFalse(
            _semantic(_SemanticContext(self.root, _Attempt(branch, 1, prepared, self.base, head), predicate))
        )

    def test_p02_github_reference_must_match_validated_origin(self) -> None:
        context, _ = self.p02_context(
            mode="github",
            reference="https://github.com/different-owner/arbiter-academy/pull/17",
        )

        self.assertFalse(_semantic(context))

    def test_p02_receipt_must_be_the_exact_attempt_head(self) -> None:
        context, _ = self.p02_context(
            mode="offline-local",
            reference="LOCAL",
        )
        later = self.commit("unreviewed later work")
        attempt = _Attempt(
            context.attempt.branch,
            1,
            context.attempt.prepared,
            context.attempt.base,
            later,
        )

        self.assertFalse(_semantic(_SemanticContext(self.root, attempt, context.predicate)))

    def test_p05_rejects_disjoint_finding_and_remediation_paths(self) -> None:
        prepared = self.commit("prepare")
        finding_path = self.root / "workshop_queue/service.py"
        finding_path.parent.mkdir()
        finding_path.write_text("finding\n", encoding="utf-8")
        finding = self.commit("finding")
        remediation_path = self.root / "tests/test_service.py"
        remediation_path.parent.mkdir()
        remediation_path.write_text("unrelated remediation\n", encoding="utf-8")
        remediation = self.commit("remediation")
        report = self.root / ".codearbiter/checkpoints/P05-academy.json"
        report.parent.mkdir(parents=True)
        report.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "finding_id": "ACADEMY-P05",
                    "finding_commit": finding,
                    "remediation_commit": remediation,
                    "paths": [
                        finding_path.relative_to(self.root).as_posix(),
                        remediation_path.relative_to(self.root).as_posix(),
                    ],
                    "status": "remediated",
                }
            ),
            encoding="utf-8",
        )
        head = self.commit("report")
        predicate = Predicate(
            "finding_remediation_link",
            "lab_semantics",
            {"profile": "checkpoint_remediation", "report": report.relative_to(self.root).as_posix()},
        )

        self.assertFalse(
            _semantic(
                _SemanticContext(
                    self.root,
                    _Attempt("academy/P05-checkpoint-remediation/1", 1, prepared, self.base, head),
                    predicate,
                )
            )
        )

    def test_p05_rejects_option_shaped_commit_before_git_invocation(self) -> None:
        prepared = self.commit("prepare")
        sentinel = self.root / "git-option-output.txt"
        report = self.root / ".codearbiter/checkpoints/P05-academy.json"
        report.parent.mkdir(parents=True)
        report.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "finding_id": "ACADEMY-P05",
                    "finding_commit": f"--output={sentinel.as_posix()}",
                    "remediation_commit": self.base,
                    "paths": ["workshop_queue/service.py", "tests/test_service.py"],
                    "status": "remediated",
                }
            ),
            encoding="utf-8",
        )
        head = self.commit("malicious report")
        predicate = Predicate(
            "finding_remediation_link",
            "lab_semantics",
            {"profile": "checkpoint_remediation", "report": report.relative_to(self.root).as_posix()},
        )

        self.assertFalse(
            _semantic(
                _SemanticContext(
                    self.root,
                    _Attempt("academy/P05-checkpoint-remediation/1", 1, prepared, self.base, head),
                    predicate,
                )
            )
        )
        self.assertFalse(sentinel.exists())

    def test_p06_handoff_must_be_introduced_after_preparation(self) -> None:
        context = self.root / ".codearbiter/CONTEXT.md"
        preserved = self.root / "docs/preserved.txt"
        handoff = self.root / ".codearbiter/reports/academy/P06-recovery.json"
        context.parent.mkdir(parents=True)
        preserved.parent.mkdir(parents=True)
        handoff.parent.mkdir(parents=True)
        before = b"stage: 1\n"
        after = b"stage: 2\n"
        context.write_bytes(before)
        preserved.write_text("unchanged\n", encoding="utf-8")
        handoff.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "context_before_sha256": hashlib.sha256(before).hexdigest(),
                    "context_after_sha256": hashlib.sha256(after).hexdigest(),
                    "preserved_path": "docs/preserved.txt",
                }
            ),
            encoding="utf-8",
        )
        self.commit("preexisting handoff")
        prepared = self.commit("prepare")
        context.write_bytes(after)
        head = self.commit("recover context")
        predicate = Predicate(
            "provenance_drift_recovery",
            "lab_semantics",
            {
                "profile": "provenance_recovery",
                "context": ".codearbiter/CONTEXT.md",
                "handoff": ".codearbiter/reports/academy/P06-recovery.json",
            },
        )

        self.assertFalse(
            _semantic(
                _SemanticContext(
                    self.root,
                    _Attempt("academy/P06-context-drift-recovery/1", 1, prepared, self.base, head),
                    predicate,
                )
            )
        )

    def test_p08_rejects_unauthenticated_hygiene_snapshot_inventory(self) -> None:
        git(self.root, "branch", "merged-extra")
        branch = "academy/P08-repository-hygiene/1"
        git(self.root, "branch", branch)
        git(self.root, "switch", "-c", "report-work")
        prepared = self.commit("prepare")
        snapshot = self.root / ".codearbiter/reports/academy/P08-hygiene.json"
        snapshot.parent.mkdir(parents=True)
        snapshot.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "refs": [
                        {"name": branch, "classification": "retain"},
                        {"name": "main", "classification": "retain"},
                        {"name": "merged-extra", "classification": "merged"},
                        {"name": "report-work", "classification": "unique"},
                    ],
                    "worktrees": [{"branch": "report-work", "dirty": False}],
                }
            ),
            encoding="utf-8",
        )
        valid_head = self.commit("complete snapshot")
        predicate = Predicate(
            "live_ref_hygiene",
            "lab_semantics",
            {"profile": "hygiene_snapshot", "snapshot": snapshot.relative_to(self.root).as_posix()},
        )
        valid = _SemanticContext(
            self.root,
            _Attempt(branch, 1, prepared, self.base, valid_head),
            predicate,
        )
        self.assertFalse(_semantic(valid))

        incomplete = json.loads(snapshot.read_text(encoding="utf-8"))
        incomplete["refs"] = [
            ref for ref in incomplete["refs"] if ref["name"] != "merged-extra"
        ]
        snapshot.write_text(json.dumps(incomplete), encoding="utf-8")
        incomplete_head = self.commit("omit one live ref")

        self.assertFalse(
            _semantic(
                _SemanticContext(
                    self.root,
                    _Attempt(branch, 1, prepared, self.base, incomplete_head),
                    predicate,
                )
            )
        )

    def test_p08_accepts_real_authority_bound_attempt_instead_of_snapshot(self) -> None:
        source = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary = Path(temporary_directory)
            repository = temporary / "learner"
            installed_data = temporary / "installed-data"
            installed = installed_data / "share/arbiter-academy/academy"
            installed.parent.mkdir(parents=True)
            shutil.copytree(source / "academy", installed)
            shutil.copytree(source / "academy", repository / "academy")
            shutil.copytree(source / "workshop_queue", repository / "workshop_queue")
            shutil.copytree(source / "data", repository / "data")
            shutil.copy2(source / "pyproject.toml", repository / "pyproject.toml")
            shutil.copy2(source / ".gitignore", repository / ".gitignore")
            (repository / ".codearbiter").mkdir()
            shutil.copy2(source / ".codearbiter/tech-stack.md", repository / ".codearbiter/tech-stack.md")
            (repository / "scripts").mkdir()
            shutil.copy2(source / "scripts/scan_secrets.py", repository / "scripts/scan_secrets.py")
            (repository / "tests").mkdir()
            shutil.copy2(source / "tests/test_cli.py", repository / "tests/test_cli.py")
            git(repository, "init", "-b", "main")
            git(repository, "config", "user.name", "Fixture")
            git(repository, "config", "user.email", "fixture@example.invalid")
            git(repository, "add", ".")
            git(repository, "commit", "-m", "academy base")
            git(repository, "remote", "add", "origin", "https://github.com/learner/arbiter-academy.git")
            git(repository, "remote", "add", "upstream", "https://github.com/arbiterForge/arbiter-academy.git")
            git(repository, "remote", "set-url", "--push", "upstream", "DISABLED")
            state_root = temporary / "state"

            with patch("academy_engine.exercise_state.sysconfig.get_path", return_value=str(installed_data)):
                base, lab, authority = preflight_p08(repository)
                store = open_p08_store(repository, base=base, authority=authority, test_root=state_root)
                prepared = prepare_p08(repository, store, lab)
            with store.locked() as locked:
                record = locked.read_record("p08", 1)
            self.assertIsNotNone(record)
            assert record is not None
            target = repository / ".codearbiter/reports/academy/P08-hygiene.json"
            target.parent.mkdir(parents=True)
            target.write_bytes(
                json.dumps(
                    exercise_module._p08_expected_report(repository, record, base),
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                ).encode("utf-8") + b"\n"
            )
            git(repository, "add", ".codearbiter/reports/academy/P08-hygiene.json")
            git(repository, "commit", "-m", "academy: report P08 hygiene")
            head = git(repository, "rev-parse", "HEAD")
            predicate = Predicate("live_ref_hygiene", "lab_semantics", {"profile": "p08_authenticated"})
            context = _SemanticContext(
                repository,
                _Attempt(prepared.branch, 1, prepared.commit_sha, base, head),
                predicate,
            )
            with patch("academy_engine.exercise_state.sysconfig.get_path", return_value=str(installed_data)), patch(
                "academy_engine.checkpoints.open_p08_store", return_value=store
            ) as opened:
                self.assertTrue(_semantic(context))
            opened.assert_called_once_with(repository, base=base, authority=authority)

    def test_u04_rejects_mutable_unbound_child_repository_state(self) -> None:
        prepared = self.commit("prepare")
        workspace = self.root / ".academy/workspaces/U04-secondary"
        workspace.mkdir(parents=True)
        git(workspace, "init", "-b", "main")
        git(workspace, "config", "user.name", "Fixture")
        git(workspace, "config", "user.email", "fixture@example.invalid")
        child_context = workspace / ".codearbiter/CONTEXT.md"
        child_context.parent.mkdir(parents=True)
        child_context.write_text("stage: 2\n", encoding="utf-8")
        git(workspace, "add", ".")
        git(workspace, "commit", "-m", "initialize child")
        child_head = git(workspace, "rev-parse", "HEAD")
        child_tree = git(workspace, "rev-parse", "HEAD^{tree}")
        committed_context = subprocess.run(
            ["git", "show", f"{child_head}:.codearbiter/CONTEXT.md"],
            cwd=workspace,
            capture_output=True,
            check=True,
        ).stdout
        context_digest = hashlib.sha256(committed_context).hexdigest()
        report = self.root / ".codearbiter/reports/academy/U04-initialization.md"
        report.parent.mkdir(parents=True)
        report.write_text(
            (
                "## Init\n\n"
                "## Brownfield\n\n"
                "## Greenfield\n\n"
                "## Reconciliation\n\n"
                f"Child-HEAD: {child_head}\n"
                f"Child-Tree: {child_tree}\n"
                f"CONTEXT-SHA256: {context_digest}\n"
            ),
            encoding="utf-8",
        )
        head = self.commit("record child initialization")
        predicate = Predicate(
            "initialized_secondary_fixture",
            "lab_semantics",
            {
                "profile": "initialized_fixture",
                "workspace": ".academy/workspaces/U04-secondary",
                "report": report.relative_to(self.root).as_posix(),
            },
        )
        context = _SemanticContext(
            self.root,
            _Attempt("academy/U04-initialize-projects/1", 1, prepared, self.base, head),
            predicate,
        )
        self.assertTrue(_semantic(context))

        child_context.write_text("stage: tampered\n", encoding="utf-8")
        self.assertFalse(_semantic(context))

    def test_u04_rejects_a_clean_symlink_to_mutable_external_context(self) -> None:
        prepared = self.commit("prepare")
        workspace = self.root / ".academy/workspaces/U04-secondary"
        workspace.mkdir(parents=True)
        git(workspace, "init", "-b", "main")
        git(workspace, "config", "user.name", "Fixture")
        git(workspace, "config", "user.email", "fixture@example.invalid")
        git(workspace, "config", "core.symlinks", "true")

        external_directory = tempfile.TemporaryDirectory()
        self.addCleanup(external_directory.cleanup)
        external_context = Path(external_directory.name) / "CONTEXT.md"
        external_context.write_text("stage: 2\n", encoding="utf-8")
        child_context = workspace / ".codearbiter/CONTEXT.md"
        child_context.parent.mkdir(parents=True)
        child_context.symlink_to(external_context)
        self.assertTrue(child_context.is_symlink())

        git(workspace, "add", ".")
        git(workspace, "commit", "-m", "initialize symlink child")
        child_head = git(workspace, "rev-parse", "HEAD")
        child_tree = git(workspace, "rev-parse", "HEAD^{tree}")
        committed_context = subprocess.run(
            ["git", "show", f"{child_head}:.codearbiter/CONTEXT.md"],
            cwd=workspace,
            capture_output=True,
            check=True,
        ).stdout
        report = self.root / ".codearbiter/reports/academy/U04-initialization.md"
        report.parent.mkdir(parents=True)
        report.write_text(
            (
                "## Init\n\n"
                "## Brownfield\n\n"
                "## Greenfield\n\n"
                "## Reconciliation\n\n"
                f"Child-HEAD: {child_head}\n"
                f"Child-Tree: {child_tree}\n"
                f"CONTEXT-SHA256: {hashlib.sha256(committed_context).hexdigest()}\n"
            ),
            encoding="utf-8",
        )
        head = self.commit("record symlink child initialization")
        predicate = Predicate(
            "initialized_secondary_fixture",
            "lab_semantics",
            {
                "profile": "initialized_fixture",
                "workspace": ".academy/workspaces/U04-secondary",
                "report": report.relative_to(self.root).as_posix(),
            },
        )
        context = _SemanticContext(
            self.root,
            _Attempt("academy/U04-initialize-projects/1", 1, prepared, self.base, head),
            predicate,
        )

        self.assertEqual(git(workspace, "status", "--porcelain", "--untracked-files=all"), "")
        self.assertFalse(_semantic(context))
        external_context.write_text("stage: externally tampered\n", encoding="utf-8")
        self.assertEqual(git(workspace, "status", "--porcelain", "--untracked-files=all"), "")
        self.assertFalse(_semantic(context))


if __name__ == "__main__":
    unittest.main()
