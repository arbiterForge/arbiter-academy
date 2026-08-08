"""Static contract tests for the GitHub Pages release workflow."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "academy-pages.yml"


def _block(text: str, start: str, next_pattern: str) -> str:
    """Return an indentation-delimited YAML block without parsing dependencies."""
    match = re.search(
        rf"(?ms)^{re.escape(start)}\n(?P<body>.*?)(?=^{next_pattern}|\Z)",
        text,
    )
    return match.group(0) if match else ""


def _literal_step_script(job: str, name: str) -> str:
    """Return the executable body of one literal ``run: |`` workflow step."""
    lines = job.splitlines()
    marker = f"      - name: {name}"
    try:
        start = lines.index(marker) + 1
    except ValueError:
        return ""
    step: list[str] = []
    for line in lines[start:]:
        if line.startswith("      - name:"):
            break
        step.append(line)
    try:
        run = step.index("        run: |") + 1
    except ValueError:
        return ""
    return "\n".join(
        line[10:] if line.startswith("          ") else "" for line in step[run:]
    )


def _git(repository: Path, *arguments: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", "-C", str(repository), *arguments],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def _tree_entries(output: bytes) -> dict[bytes, tuple[bytes, bytes, bytes]]:
    entries: dict[bytes, tuple[bytes, bytes, bytes]] = {}
    for record in output.rstrip(b"\0").split(b"\0") if output else ():
        metadata, path = record.split(b"\t", 1)
        mode, object_type, object_id = metadata.split(b" ", 2)
        entries[path] = (mode, object_type, object_id)
    return entries


def _index_entries(output: bytes) -> dict[bytes, tuple[bytes, bytes]]:
    entries: dict[bytes, tuple[bytes, bytes]] = {}
    for record in output.rstrip(b"\0").split(b"\0") if output else ():
        metadata, path = record.split(b"\t", 1)
        mode, object_id, stage = metadata.split(b" ", 2)
        if stage == b"0":
            entries[path] = (mode, object_id)
    return entries


class PagesWorkflowContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workflow = WORKFLOW.read_text(encoding="utf-8") if WORKFLOW.exists() else ""
        self.verify = _block(self.workflow, "  verify:", r"  [a-zA-Z0-9_-]+:")
        self.deploy = _block(self.workflow, "  deploy:", r"  [a-zA-Z0-9_-]+:")

    def test_workflow_verifies_pull_requests_and_main_pushes(self) -> None:
        trigger = _block(self.workflow, "on:", r"[a-zA-Z0-9_-]+:")
        self.assertRegex(trigger, r"(?m)^  pull_request:\s*$")
        self.assertRegex(trigger, r"(?m)^  push:\s*$")
        self.assertRegex(trigger, r"(?ms)^  push:\s+branches:\s+- main\s*$")
        self.assertIn("github.event_name == 'push'", self.deploy)
        self.assertIn("github.ref == 'refs/heads/main'", self.deploy)
        self.assertIn("needs: verify", self.deploy)

    def test_concurrency_isolated_by_ref_and_cancels_only_stale_non_main_runs(self) -> None:
        concurrency = _block(self.workflow, "concurrency:", r"[a-zA-Z0-9_-]+:")
        self.assertIn("group: ${{ github.workflow }}-${{ github.ref }}", concurrency)
        self.assertIn(
            "cancel-in-progress: ${{ github.ref != 'refs/heads/main' }}",
            concurrency,
        )

    def test_permissions_are_read_only_except_in_the_deploy_job(self) -> None:
        top_level_permissions = _block(
            self.workflow,
            "permissions:",
            r"[a-zA-Z0-9_-]+:",
        )
        self.assertRegex(top_level_permissions, r"(?m)^  contents: read\s*$")
        self.assertNotIn("pages: write", top_level_permissions)
        self.assertNotIn("id-token: write", top_level_permissions)
        self.assertNotIn("pages: write", self.verify)
        self.assertNotIn("id-token: write", self.verify)
        self.assertRegex(self.deploy, r"(?m)^      pages: write\s*$")
        self.assertRegex(self.deploy, r"(?m)^      id-token: write\s*$")
        self.assertEqual(self.workflow.count("pages: write"), 1)
        self.assertEqual(self.workflow.count("id-token: write"), 1)

    def test_verify_job_runs_the_complete_milestone_gate_in_order(self) -> None:
        required_fragments = (
            'python -m unittest discover -s tests -p "test_*.py" -v',
            "python -m tabnanny academy_engine scripts tests workshop_queue",
            "python -m compileall -q academy_engine scripts tests workshop_queue",
            "python -m unittest tests.test_project_state -v",
            "python scripts/build_preview_site.py",
            "--output site/generated",
            '--release-sha "$GITHUB_SHA"',
            "python scripts/check_preview_site.py site/generated",
        )
        positions = [self.verify.find(fragment) for fragment in required_fragments]
        self.assertTrue(
            all(position >= 0 for position in positions),
            f"missing gate from verify job: {dict(zip(required_fragments, positions))}",
        )
        self.assertEqual(positions, sorted(positions))

    def test_secret_scan_reconstructs_exact_head_blobs_and_skips_gitlinks(self) -> None:
        script = _literal_step_script(
            self.verify, "Scan every tracked file for secrets"
        )
        self.assertTrue(script, "secret-scan run script is missing")
        bash = shutil.which("bash")
        if os.name == "nt":
            git_bash = Path(r"C:\Program Files\Git\bin\bash.exe")
            if git_bash.is_file():
                bash = str(git_bash)
        if bash is None:
            self.skipTest("bash is required to exercise the workflow step")

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = root / "fixture"
            repository.mkdir()
            self.assertEqual(_git(repository, "init", "--quiet").returncode, 0)
            self.assertEqual(
                _git(repository, "config", "user.name", "Academy Test").returncode,
                0,
            )
            self.assertEqual(
                _git(repository, "config", "user.email", "academy@example.invalid").returncode,
                0,
            )

            (repository / "scripts").mkdir()
            shutil.copyfile(ROOT / "scripts" / "scan_secrets.py", repository / "scripts" / "scan_secrets.py")
            (repository / ".gitattributes").write_text(
                "export-ignored.txt export-ignore\nsubstituted.txt export-subst\n",
                encoding="utf-8",
            )
            (repository / ".gitignore").write_text("tracked-ignored.txt\n", encoding="utf-8")
            (repository / "export-ignored.txt").write_text("archive must not omit me\n", encoding="utf-8")
            (repository / "substituted.txt").write_text("$Format:%H$\n", encoding="utf-8")
            (repository / "tracked-ignored.txt").write_text("tracked despite ignore rules\n", encoding="utf-8")
            odd_name = "- odd name [brackets] Ω.txt"
            (repository / odd_name).write_text("odd path survives\n", encoding="utf-8")
            added = _git(repository, "add", "-f", "--", ".")
            self.assertEqual(added.returncode, 0, added.stderr.decode(errors="replace"))
            committed = _git(repository, "commit", "--quiet", "-m", "fixture base")
            self.assertEqual(committed.returncode, 0, committed.stderr.decode(errors="replace"))
            base = _git(repository, "rev-parse", "HEAD").stdout.strip().decode("ascii")
            linked = _git(
                repository,
                "update-index",
                "--add",
                "--cacheinfo",
                f"160000,{base},training-submodule",
            )
            self.assertEqual(linked.returncode, 0, linked.stderr.decode(errors="replace"))
            committed = _git(repository, "commit", "--quiet", "-m", "add gitlink")
            self.assertEqual(committed.returncode, 0, committed.stderr.decode(errors="replace"))

            environment = os.environ.copy()
            environment["GITHUB_WORKSPACE"] = str(repository).replace("\\", "/")
            environment["RUNNER_TEMP"] = str(root / "runner").replace("\\", "/")
            result = subprocess.run(
                [bash, "-c", script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=environment,
                check=False,
            )
            self.assertEqual(
                result.returncode,
                0,
                (result.stdout + result.stderr).decode(errors="replace"),
            )

            head = _tree_entries(_git(repository, "ls-tree", "-r", "-z", "HEAD").stdout)
            scan_root = root / "runner" / "academy-secret-scan"
            staged = _index_entries(
                _git(scan_root, "ls-files", "--stage", "-z").stdout
            )
            expected = {
                path: (mode, object_id)
                for path, (mode, object_type, object_id) in head.items()
                if object_type == b"blob"
            }
            self.assertEqual(staged, expected)
            self.assertIn(b"export-ignored.txt", staged)
            self.assertIn(b"substituted.txt", staged)
            self.assertIn(b"tracked-ignored.txt", staged)
            self.assertIn(odd_name.encode("utf-8"), staged)
            self.assertNotIn(b"training-submodule", staged)
            self.assertNotIn("git archive", script)

    def test_pages_artifact_is_uploaded_then_deployed(self) -> None:
        pins = (
            "uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1",
            "uses: actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97 # v7.0.0",
            "uses: actions/upload-pages-artifact@fc324d3547104276b827a68afc52ff2a11cc49c9 # v5.0.0",
            "uses: actions/configure-pages@45bfe0192ca1faeb007ade9deae92b16b8254a0d # v6.0.0",
            "uses: actions/deploy-pages@cd2ce8fcbc39b97be8ca5fce6e763baed58fa128 # v5.0.0",
        )
        for pin in pins:
            self.assertIn(pin, self.workflow)
        self.assertRegex(self.verify, r"(?m)^          path: site/generated\s*$")

        build = self.verify.find("python scripts/build_preview_site.py")
        checker = self.verify.find("python scripts/check_preview_site.py site/generated")
        scanner = self.verify.find(
            'python "$GITHUB_WORKSPACE/scripts/scan_secrets.py" --staged'
        )
        upload = self.verify.find("uses: actions/upload-pages-artifact@")
        self.assertTrue(min(build, checker, scanner, upload) >= 0)
        self.assertEqual([build, checker, scanner, upload], sorted((build, checker, scanner, upload)))

        configure = self.deploy.find("uses: actions/configure-pages@")
        deployment = self.deploy.find("uses: actions/deploy-pages@")
        self.assertGreaterEqual(configure, 0)
        self.assertGreater(deployment, configure)
        self.assertIn("id: deployment", self.deploy)
        self.assertIn("name: github-pages", self.deploy)
        self.assertIn("steps.deployment.outputs.page_url", self.deploy)

    def test_workflow_adds_no_install_or_third_party_action_step(self) -> None:
        actions = re.findall(r"(?m)^\s*-?\s*uses:\s*([^\s]+)", self.workflow)
        self.assertTrue(actions)
        self.assertTrue(all(action.startswith("actions/") for action in actions), actions)
        self.assertTrue(
            all(re.fullmatch(r"actions/[a-z-]+@[0-9a-f]{40}", action) for action in actions),
            actions,
        )
        self.assertNotRegex(self.workflow, r"(?i)\b(?:pip|npm|pnpm|yarn)\s+install\b")


if __name__ == "__main__":
    unittest.main()
