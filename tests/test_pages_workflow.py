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
VERIFY_WORKFLOW = ROOT / ".github" / "workflows" / "academy-verify.yml"
PAGES_WORKFLOW = ROOT / ".github" / "workflows" / "academy-pages.yml"

AGGREGATE_GATE_STEPS = (
    (
        "Check Python indentation",
        "      - name: Check Python indentation\n"
        "        run: python -m tabnanny academy_engine scripts tests workshop_queue",
    ),
    (
        "Compile Python sources",
        "      - name: Compile Python sources\n"
        "        run: python -m compileall -q academy_engine scripts tests workshop_queue",
    ),
    (
        "Verify project state",
        "      - name: Verify project state\n"
        "        run: python -m unittest tests.test_project_state -v",
    ),
    (
        "Build the Preview 0.1 site",
        "      - name: Build the Preview 0.1 site\n"
        "        run: >-\n"
        "          python scripts/build_preview_site.py\n"
        "          --output site/generated\n"
        '          --release-sha "$CANDIDATE_SHA"',
    ),
    (
        "Check the generated site",
        "      - name: Check the generated site\n"
        "        run: python scripts/check_preview_site.py site/generated",
    ),
    (
        "Scan every tracked file for secrets",
        """      - name: Scan every tracked file for secrets
        shell: bash
        run: |
          set -euo pipefail
          scan_root="$RUNNER_TEMP/academy-secret-scan"
          mkdir -p "$scan_root"
          object_format="$(git -C "$GITHUB_WORKSPACE" rev-parse --show-object-format)"
          git -C "$scan_root" init --quiet --object-format="$object_format"
          git -C "$GITHUB_WORKSPACE" ls-tree -r -z HEAD |
            while IFS= read -r -d '' entry; do
              metadata="${entry%%$'\\t'*}"
              path="${entry#*$'\\t'}"
              read -r mode object_type object_id <<< "$metadata"
              if [[ "$mode" == "160000" ]]; then
                continue
              fi
              if [[ "$object_type" != "blob" ]]; then
                echo "ERROR: unexpected non-blob tree entry." >&2
                exit 2
              fi
              imported="$({
                git -C "$GITHUB_WORKSPACE" cat-file blob "$object_id"
              } | git -C "$scan_root" hash-object -w --stdin)"
              if [[ "$imported" != "$object_id" ]]; then
                echo "ERROR: reconstructed blob identity mismatch." >&2
                exit 2
              fi
              git -C "$scan_root" update-index --add \\
                --cacheinfo "$mode,$object_id,$path"
            done
          (
            cd "$scan_root"
            python "$GITHUB_WORKSPACE/scripts/scan_secrets.py" --staged
          )""",
    ),
)


def _block(text: str, start: str, next_pattern: str) -> str:
    """Return an indentation-delimited YAML block without parsing dependencies."""
    match = re.search(
        rf"(?ms)^{re.escape(start)}\n(?P<body>.*?)(?=^{next_pattern}|\Z)",
        text,
    )
    return match.group(0) if match else ""


def _named_step(job: str, name: str) -> str:
    """Return one complete named workflow step, including all of its keys."""
    match = re.search(
        rf"(?ms)^      - name: {re.escape(name)}\n.*?(?=^      - |\Z)",
        job,
    )
    return match.group(0).rstrip() if match else ""


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
        self.verify_workflow = VERIFY_WORKFLOW.read_text(encoding="utf-8") if VERIFY_WORKFLOW.exists() else ""
        self.pages_workflow = PAGES_WORKFLOW.read_text(encoding="utf-8") if PAGES_WORKFLOW.exists() else ""
        self.workflow = self.verify_workflow + "\n" + self.pages_workflow
        self.verify = _block(self.verify_workflow, "  verify:", r"  [a-zA-Z0-9_-]+:")
        self.verify_candidate = _block(
            self.verify_workflow, "  verify-candidate:", r"  [a-zA-Z0-9_-]+:"
        )
        self.main_verify = _block(
            self.pages_workflow, "  verify-main:", r"  [a-zA-Z0-9_-]+:"
        )
        self.build = _block(self.pages_workflow, "  build:", r"  [a-zA-Z0-9_-]+:")
        self.deploy = _block(self.pages_workflow, "  deploy:", r"  [a-zA-Z0-9_-]+:")

    def test_workflow_verifies_pull_requests_and_main_pushes(self) -> None:
        verify_trigger = _block(self.verify_workflow, "on:", r"[a-zA-Z0-9_-]+:")
        pages_trigger = _block(self.pages_workflow, "on:", r"[a-zA-Z0-9_-]+:")
        self.assertRegex(verify_trigger, r"(?m)^  pull_request:\s*$")
        self.assertNotRegex(verify_trigger, r"(?m)^  push:\s*$")
        self.assertNotIn("pull_request", pages_trigger)
        self.assertRegex(pages_trigger, r"(?ms)^  push:\s+branches:\s+- main\s*$")
        self.assertIn("github.ref == 'refs/heads/main'", self.deploy)

    def test_concurrency_isolated_by_ref_and_cancels_only_stale_non_main_runs(self) -> None:
        concurrency = _block(self.verify_workflow, "concurrency:", r"[a-zA-Z0-9_-]+:")
        self.assertIn("group: ${{ github.workflow }}-${{ github.ref }}", concurrency)
        self.assertIn(
            "cancel-in-progress: ${{ github.ref != 'refs/heads/main' }}",
            concurrency,
        )

    def test_permissions_are_read_only_except_in_the_deploy_job(self) -> None:
        top_level_permissions = _block(
            self.pages_workflow,
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
        self.assertEqual(self.pages_workflow.count("pages: write"), 1)
        self.assertEqual(self.pages_workflow.count("id-token: write"), 1)

    def test_verify_job_runs_the_complete_milestone_gate_in_order(self) -> None:
        for label, job in (("pull request", self.verify_candidate), ("main", self.build)):
            expected_directives = (
                (
                    "    needs: verify",
                    "    runs-on: ubuntu-latest",
                    "    timeout-minutes: 30",
                    "    env:",
                    "    steps:",
                )
                if label == "pull request"
                else (
                    "    if: github.ref == 'refs/heads/main'",
                    "    needs: verify-main",
                    "    runs-on: ubuntu-latest",
                    "    timeout-minutes: 30",
                    "    env:",
                    "    steps:",
                )
            )
            self.assertEqual(
                tuple(re.findall(r"(?m)^    \S.*$", job)),
                expected_directives,
                f"{label} aggregate job has missing, duplicate, reordered, or extra direct keys",
            )
            required_fragments = (
                "python -m tabnanny academy_engine scripts tests workshop_queue",
                "python -m compileall -q academy_engine scripts tests workshop_queue",
                "python -m unittest tests.test_project_state -v",
                "python scripts/build_preview_site.py",
                "--output site/generated",
                '--release-sha "$CANDIDATE_SHA"',
                "python scripts/check_preview_site.py site/generated",
            )
            positions = [job.find(fragment) for fragment in required_fragments]
            self.assertTrue(
                all(position >= 0 for position in positions),
                f"missing gate from {label} verify job: {dict(zip(required_fragments, positions))}",
            )
            self.assertEqual(positions, sorted(positions))
            for step_name, expected_step in AGGREGATE_GATE_STEPS:
                self.assertEqual(
                    _named_step(job, step_name),
                    expected_step,
                    f"{label} {step_name} step must match the strict gate",
                )

    def test_aggregate_gate_contract_rejects_fail_open_step_mutations(self) -> None:
        cases = (
            ("verify_candidate", "Check Python indentation", "step if"),
            ("build", "Check Python indentation", "extra key"),
            ("verify_candidate", "Compile Python sources", "continue on error"),
            ("build", "Compile Python sources", "folded wrapper"),
            ("verify_candidate", "Verify project state", "shell or success"),
            ("build", "Verify project state", "shell exit zero"),
            ("verify_candidate", "Build the Preview 0.1 site", "shell exit zero"),
            ("build", "Build the Preview 0.1 site", "shell or success"),
            ("verify_candidate", "Check the generated site", "folded wrapper"),
            ("build", "Check the generated site", "continue on error"),
            ("verify_candidate", "Scan every tracked file for secrets", "extra key"),
            ("build", "Scan every tracked file for secrets", "step if"),
        )
        for job_name, step_name, mutation in cases:
            with self.subTest(job=job_name, step=step_name, mutation=mutation):
                probe = type(self)(
                    methodName="test_verify_job_runs_the_complete_milestone_gate_in_order"
                )
                probe.setUp()
                job = getattr(probe, job_name)
                step = _named_step(job, step_name)
                if mutation == "step if":
                    mutated = step + "\n        if: ${{ false }}"
                elif mutation == "continue on error":
                    mutated = step + "\n        continue-on-error: true"
                elif mutation == "extra key":
                    mutated = step + "\n        env:\n          ACADEMY_BYPASS: \"1\""
                elif mutation == "folded wrapper":
                    prefix = "        run: "
                    command = step.split(prefix, 1)[1]
                    mutated = step.replace(
                        prefix + command,
                        "        run: >-\n          " + command + "\n          || true",
                    )
                elif mutation == "shell or success":
                    mutated = step + " || true"
                else:
                    mutated = step + "; exit 0"
                setattr(probe, job_name, job.replace(step, mutated))

                with self.assertRaises(
                    AssertionError,
                    msg=f"{job_name} {step_name} {mutation} survived the aggregate gate contract",
                ):
                    probe.test_verify_job_runs_the_complete_milestone_gate_in_order()

    def test_aggregate_job_contract_rejects_conditional_bypass_mutations(self) -> None:
        cases = (
            ("verify_candidate", "false", "  verify-candidate:\n    if: false"),
            ("verify_candidate", "true", "  verify-candidate:\n    if: true"),
            (
                "verify_candidate",
                "expression false",
                "  verify-candidate:\n    if: ${{ false }}",
            ),
            (
                "verify_candidate",
                "arbitrary",
                "  verify-candidate:\n    if: github.event_name == 'never'",
            ),
            (
                "verify_candidate",
                "duplicate key",
                "  verify-candidate:\n    runs-on: ubuntu-latest",
            ),
            (
                "verify_candidate",
                "reordered keys",
                "  verify-candidate:\n    runs-on: ubuntu-latest\n    needs: verify",
            ),
            ("build", "false", "    if: false"),
            ("build", "true", "    if: true"),
            ("build", "expression false", "    if: ${{ false }}"),
            ("build", "arbitrary", "    if: github.event_name == 'never'"),
            (
                "build",
                "duplicate condition",
                "    if: github.ref == 'refs/heads/main'\n    if: true",
            ),
            (
                "build",
                "reordered condition",
                "    needs: verify-main\n    if: github.ref == 'refs/heads/main'",
            ),
        )
        for job_name, mutation, replacement in cases:
            with self.subTest(job=job_name, mutation=mutation):
                probe = type(self)(
                    methodName="test_verify_job_runs_the_complete_milestone_gate_in_order"
                )
                probe.setUp()
                job = getattr(probe, job_name)
                if job_name == "verify_candidate":
                    mutated = job.replace("  verify-candidate:", replacement)
                else:
                    mutated = job.replace(
                        "    if: github.ref == 'refs/heads/main'",
                        replacement,
                    )
                setattr(probe, job_name, mutated)

                with self.assertRaises(
                    AssertionError,
                    msg=f"{job_name} {mutation} survived the aggregate-job contract",
                ):
                    probe.test_verify_job_runs_the_complete_milestone_gate_in_order()

    def test_each_branch_requires_all_sixteen_shard_jobs_before_aggregate_gates(self) -> None:
        for label, job, consumer in (
            ("pull request", self.verify, self.verify_candidate),
            ("main", self.main_verify, self.build),
        ):
            with self.subTest(job=label):
                expected_directives = (
                    (
                        "    runs-on: ubuntu-latest",
                        "    timeout-minutes: 90",
                        "    strategy:",
                        "    env:",
                        "    steps:",
                    )
                    if label == "pull request"
                    else (
                        "    if: github.ref == 'refs/heads/main'",
                        "    runs-on: ubuntu-latest",
                        "    timeout-minutes: 90",
                        "    strategy:",
                        "    env:",
                        "    steps:",
                    )
                )
                self.assertEqual(
                    tuple(re.findall(r"(?m)^    \S.*$", job)),
                    expected_directives,
                    f"{label} shard job has missing, duplicate, or extra direct keys",
                )
                self.assertEqual(
                    _block(job, "    strategy:", r"    [a-zA-Z0-9_-]+:").rstrip(),
                    "    strategy:\n"
                    "      fail-fast: false\n"
                    "      matrix:\n"
                    '        python-version: ["3.11", "3.12"]\n'
                    "        shard-index: [0, 1, 2, 3, 4, 5, 6, 7]",
                    f"{label} strategy and matrix must match the sixteen-job gate",
                )
                self.assertRegex(job, r"(?m)^    timeout-minutes: 90\s*$")
                self.assertRegex(job, r'python-version:\s*\["3\.11", "3\.12"\]')
                self.assertRegex(job, r"shard-index:\s*\[0, 1, 2, 3, 4, 5, 6, 7\]")
                self.assertEqual(
                    _named_step(job, "Run one exhaustive milestone shard"),
                    "      - name: Run one exhaustive milestone shard\n"
                    "        timeout-minutes: 75\n"
                    '        run: python scripts/run_test_shards.py --shard-index "${{ matrix.shard-index }}"',
                    f"{label} exhaustive shard step must match the strict gate",
                )
                self.assertNotIn("unittest discover", job)
                dependency = "verify" if label == "pull request" else "verify-main"
                self.assertRegex(consumer, rf"(?m)^    needs: {dependency}\s*$")
                self.assertNotIn("strategy:", consumer)
                for gated_job in (job, consumer):
                    self.assertNotRegex(
                        gated_job,
                        r"(?m)^\s+continue-on-error:",
                        f"{label} gate must not tolerate a failed job or step",
                    )
                    job_conditions = "\n".join(
                        re.findall(r"(?m)^    if:\s*(.+?)\s*$", gated_job)
                    )
                    self.assertNotRegex(
                        job_conditions,
                        r"\b(?:always|failure|cancelled)\s*\(",
                        f"{label} gate has a condition that can bypass dependency success",
                    )

        self.assertNotIn("upload-pages-artifact", self.main_verify)
        self.assertEqual(self.pages_workflow.count("upload-pages-artifact@"), 1)

    def test_hosted_shards_remove_checkout_only_git_config(self) -> None:
        cleanup = (
            "      - name: Remove checkout-only Git configuration\n"
            "        run: git config --local --unset-all gc.auto"
        )
        for label, job in (("pull request", self.verify), ("main", self.main_verify)):
            with self.subTest(job=label):
                self.assertEqual(
                    _named_step(job, "Remove checkout-only Git configuration"),
                    cleanup,
                )
                self.assertLess(
                    job.index("Remove checkout-only Git configuration"),
                    job.index("Run one exhaustive milestone shard"),
                )

    def test_shard_gate_contract_rejects_failure_tolerance_mutations(self) -> None:
        mutations = (
            "fail-tolerant shard steps",
            "conditional shard steps",
            "shell-or-success shard steps",
            "shell-exit-zero shard steps",
            "folded-shell-success shard steps",
            "fail-tolerant shard jobs",
            "unconditional aggregate jobs",
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                probe = type(self)(
                    methodName=(
                        "test_each_branch_requires_all_sixteen_shard_jobs_before_aggregate_gates"
                    )
                )
                probe.setUp()
                if mutation == "fail-tolerant shard steps":
                    shard_command = (
                        '        run: python scripts/run_test_shards.py --shard-index '
                        '"${{ matrix.shard-index }}"'
                    )
                    fail_tolerant_step = shard_command + "\n        continue-on-error: true"
                    probe.verify = probe.verify.replace(shard_command, fail_tolerant_step)
                    probe.main_verify = probe.main_verify.replace(
                        shard_command, fail_tolerant_step
                    )
                elif mutation == "conditional shard steps":
                    shard_command = (
                        '        run: python scripts/run_test_shards.py --shard-index '
                        '"${{ matrix.shard-index }}"'
                    )
                    skipped_step = shard_command + "\n        if: ${{ false }}"
                    probe.verify = probe.verify.replace(shard_command, skipped_step)
                    probe.main_verify = probe.main_verify.replace(
                        shard_command, skipped_step
                    )
                elif mutation in (
                    "shell-or-success shard steps",
                    "shell-exit-zero shard steps",
                    "folded-shell-success shard steps",
                ):
                    shard_command = (
                        '        run: python scripts/run_test_shards.py --shard-index '
                        '"${{ matrix.shard-index }}"'
                    )
                    suffix = {
                        "shell-or-success shard steps": " || true",
                        "shell-exit-zero shard steps": "; exit 0",
                        "folded-shell-success shard steps": "\n          || true",
                    }[mutation]
                    fail_tolerant_command = shard_command + suffix
                    probe.verify = probe.verify.replace(
                        shard_command, fail_tolerant_command
                    )
                    probe.main_verify = probe.main_verify.replace(
                        shard_command, fail_tolerant_command
                    )
                elif mutation == "fail-tolerant shard jobs":
                    probe.verify = probe.verify.replace(
                        "    timeout-minutes: 90",
                        "    timeout-minutes: 90\n    continue-on-error: true",
                    )
                    probe.main_verify = probe.main_verify.replace(
                        "    timeout-minutes: 90",
                        "    timeout-minutes: 90\n    continue-on-error: true",
                    )
                else:
                    probe.verify_candidate = probe.verify_candidate.replace(
                        "  verify-candidate:",
                        "  verify-candidate:\n    if: always()",
                    )
                    probe.build = probe.build.replace(
                        "    if: github.ref == 'refs/heads/main'",
                        "    if: always()",
                    )

                with self.assertRaises(
                    AssertionError,
                    msg=f"{mutation} survived the shard-gate contract",
                ):
                    probe.test_each_branch_requires_all_sixteen_shard_jobs_before_aggregate_gates()

    def test_shard_job_contract_rejects_structural_matrix_mutations(self) -> None:
        matrix = (
            '      matrix:\n'
            '        python-version: ["3.11", "3.12"]\n'
            '        shard-index: [0, 1, 2, 3, 4, 5, 6, 7]'
        )
        matrix_mutations = {
            "exclude": matrix + '\n        exclude:\n          - python-version: "3.11"',
            "include": matrix + '\n        include:\n          - python-version: "3.13"',
            "unknown axis": matrix + "\n        runner: [ubuntu-latest]",
            "duplicate axis": matrix + '\n        python-version: ["3.11", "3.12"]',
            "missing axis": matrix.replace(
                '        python-version: ["3.11", "3.12"]\n', ""
            ),
            "substituted axis": matrix.replace("shard-index:", "shard-number:"),
        }
        for job_name in ("verify", "main_verify"):
            for mutation, replacement in matrix_mutations.items():
                with self.subTest(job=job_name, mutation=mutation):
                    probe = type(self)(
                        methodName=(
                            "test_each_branch_requires_all_sixteen_shard_jobs_before_aggregate_gates"
                        )
                    )
                    probe.setUp()
                    job = getattr(probe, job_name)
                    setattr(probe, job_name, job.replace(matrix, replacement))
                    with self.assertRaises(
                        AssertionError,
                        msg=f"{job_name} {mutation} survived the shard-job contract",
                    ):
                        probe.test_each_branch_requires_all_sixteen_shard_jobs_before_aggregate_gates()

        for job_name in ("verify", "main_verify"):
            with self.subTest(job=job_name, mutation="job if false"):
                probe = type(self)(
                    methodName=(
                        "test_each_branch_requires_all_sixteen_shard_jobs_before_aggregate_gates"
                    )
                )
                probe.setUp()
                if job_name == "verify":
                    probe.verify = probe.verify.replace(
                        "  verify:", "  verify:\n    if: false"
                    )
                else:
                    probe.main_verify = probe.main_verify.replace(
                        "    if: github.ref == 'refs/heads/main'", "    if: false"
                    )
                with self.assertRaises(
                    AssertionError,
                    msg=f"{job_name} job if false survived the shard-job contract",
                ):
                    probe.test_each_branch_requires_all_sixteen_shard_jobs_before_aggregate_gates()

    def test_secret_scan_reconstructs_exact_head_blobs_and_skips_gitlinks(self) -> None:
        script = _literal_step_script(
            self.verify_candidate, "Scan every tracked file for secrets"
        )
        self.assertTrue(script, "secret-scan run script is missing")
        self.assertEqual(
            script.strip(),
            _literal_step_script(self.build, "Scan every tracked file for secrets").strip(),
        )
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
        self.assertRegex(self.build, r"(?m)^          path: site/generated\s*$")

        build = self.build.find("python scripts/build_preview_site.py")
        checker = self.build.find("python scripts/check_preview_site.py site/generated")
        scanner = self.build.find(
            'python "$GITHUB_WORKSPACE/scripts/scan_secrets.py" --staged'
        )
        upload = self.build.find("uses: actions/upload-pages-artifact@")
        self.assertTrue(min(build, checker, scanner, upload) >= 0)
        self.assertEqual([build, checker, scanner, upload], sorted((build, checker, scanner, upload)))

        configure = self.deploy.find("uses: actions/configure-pages@")
        deployment = self.deploy.find("uses: actions/deploy-pages@")
        self.assertGreaterEqual(configure, 0)
        self.assertGreater(deployment, configure)
        self.assertIn("id: deployment", self.deploy)
        self.assertIn("name: github-pages", self.deploy)
        self.assertIn("steps.deployment.outputs.page_url", self.deploy)
        self.assertRegex(self.build, r"(?m)^    needs: verify-main\s*$")
        self.assertRegex(self.deploy, r"(?m)^    needs: build\s*$")

    def test_workflow_adds_no_install_or_third_party_action_step(self) -> None:
        actions = re.findall(r"(?m)^\s*-?\s*uses:\s*([^\s]+)", self.workflow)
        self.assertTrue(actions)
        self.assertTrue(all(action.startswith("actions/") for action in actions), actions)
        self.assertTrue(
            all(re.fullmatch(r"actions/[a-z-]+@[0-9a-f]{40}", action) for action in actions),
            actions,
        )
        self.assertNotRegex(self.workflow, r"(?i)\b(?:pip|npm|pnpm|yarn)\s+install\b")

    def test_pull_request_checkout_uses_exact_head_without_credentials(self) -> None:
        """Catches PR verification silently running GitHub's synthetic merge commit."""
        self.assertIn("ref: ${{ github.event.pull_request.head.sha || github.sha }}", self.verify)
        self.assertIn(
            "CANDIDATE_SHA: ${{ github.event.pull_request.head.sha || github.sha }}",
            self.verify,
        )
        self.assertIn('--release-sha "$CANDIDATE_SHA"', self.verify_candidate)
        self.assertNotIn('--release-sha "$GITHUB_SHA"', self.verify_candidate)
        self.assertIn("persist-credentials: false", self.verify)
        self.assertNotIn("refs/pull/", self.verify_workflow)
        self.assertIn("CANDIDATE_SHA: ${{ github.event.pull_request.head.sha || github.sha }}", self.verify_candidate)
        self.assertIn("ref: ${{ github.event.pull_request.head.sha || github.sha }}", self.verify_candidate)
        self.assertIn("persist-credentials: false", self.verify_candidate)
        self.assertIn("CANDIDATE_SHA: ${{ github.sha }}", self.main_verify)
        self.assertIn("ref: ${{ github.sha }}", self.main_verify)
        self.assertIn("persist-credentials: false", self.main_verify)
        self.assertIn("CANDIDATE_SHA: ${{ github.sha }}", self.build)
        self.assertIn("ref: ${{ github.sha }}", self.build)
        self.assertIn("persist-credentials: false", self.build)
        self.assertNotIn("uses: actions/checkout@", self.deploy)

    def test_hosted_verifier_has_pinned_codearbiter_and_offline_build_wheel(self) -> None:
        """Catches hosted acceptance running without its reviewed local prerequisites."""
        for label, job in (("pull request", self.verify), ("main", self.main_verify)):
            with self.subTest(job=label):
                self.assertIn("repository: arbiterForge/codeArbiter", job)
                self.assertIn("ref: 469c2fb82555346a739ab72a0f7284f22874aa3e", job)
                self.assertIn("CODEARBITER_SOURCE_SHA: 469c2fb82555346a739ab72a0f7284f22874aa3e", job)
                self.assertIn("CODEARBITER_TASKWRITE:", job)
                self.assertIn("WORKSHOP_QUEUE_TEST_WHEELHOUSE:", job)
                self.assertRegex(job, r'python-version:\s*\["3\.11", "3\.12"\]')
                self.assertRegex(job, r"shard-index:\s*\[0, 1, 2, 3, 4, 5, 6, 7\]")
        wheel = ROOT / ".github" / "wheelhouse" / "setuptools-83.0.0-py3-none-any.whl"
        self.assertTrue(wheel.is_file())
        import hashlib
        self.assertEqual(
            hashlib.sha256(wheel.read_bytes()).hexdigest(),
            "29b23c360f22f414dc7336bb39178cc7bcbf6021ed2733cde173f09dba19abb3",
        )


if __name__ == "__main__":
    unittest.main()
