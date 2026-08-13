"""Static contract tests for the GitHub Pages release workflow."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VERIFY_WORKFLOW = ROOT / ".github" / "workflows" / "academy-verify.yml"
PAGES_WORKFLOW = ROOT / ".github" / "workflows" / "academy-pages.yml"

RELEASE_ASSETS = (
    "install.ps1",
    "install.ps1.sha256",
    "install.sh",
    "install.sh.sha256",
    "arbiter-academy-preview-0.19.zip",
    "arbiter-academy-preview-0.19.zip.sha256",
)

NODE_SETUP_STEP = (
    "      - name: Select Node 22.19.0\n"
    "        uses: actions/setup-node@820762786026740c76f36085b0efc47a31fe5020 # v7.0.0\n"
    "        with:\n"
    '          node-version: "22.19.0"\n'
    "          check-latest: false"
)

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
        "Verify Academy browser controls",
        "      - name: Verify Academy browser controls\n"
        "        run: node --test tests/site/academy.test.mjs",
    ),
    (
        "Build the Academy site",
        "      - name: Build the Academy site\n"
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


def _workflow_jobs(workflow: str) -> dict[str, str]:
    """Return top-level workflow job bodies keyed by job ID."""
    jobs = _block(workflow, "jobs:", r"[a-zA-Z0-9_-]+:")
    return {
        match.group("name"): match.group(0)
        for match in re.finditer(
            r"(?ms)^  (?P<name>[a-zA-Z0-9_-]+):\n.*?(?=^  [a-zA-Z0-9_-]+:|\Z)",
            jobs,
        )
    }


def _job_needs(job: str) -> set[str]:
    """Read scalar, flow-list, or block-list job dependencies."""
    match = re.search(
        r"(?m)^    needs:(?P<inline>[^\n]*)\n(?P<block>(?:      - [a-zA-Z0-9_-]+\n)*)",
        job,
    )
    if match is None:
        return set()
    return set(re.findall(r"[a-zA-Z0-9_-]+", match.group("inline") + match.group("block")))


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


def _release_validation_script(workflow: str) -> str:
    """Extract the standard-library release metadata validator from the gate."""
    job = _workflow_jobs(workflow).get("verify-release", "")
    shell = _literal_step_script(job, "Verify immutable Preview release assets")
    scripts = re.findall(
        r"(?ms)^\s*(?:if )?python - <<'(?P<marker>[A-Z]+)'\n(?P<body>.*?)^(?P=marker)$",
        shell,
    )
    return "\n".join(body for _marker, body in scripts)


def _assert_release_gate_is_fail_closed(workflow: str) -> None:
    """Reject security-significant workflow mutations without executing GitHub Actions."""
    job = _workflow_jobs(workflow).get("verify-release", "")
    shell = _literal_step_script(job, "Verify immutable Preview release assets")
    required = (
        'if [[ "$resolved_sha" != "$CANDIDATE_SHA" ]]; then',
        'test "$(git -C "$release_source" rev-parse HEAD)" = "$resolved_sha"',
        'asset_api="https://api.github.com/repos/${GITHUB_REPOSITORY}/releases/assets/${asset_id}"',
        'raise SystemExit("release asset inventory mismatch")',
        'raise SystemExit("release asset ID is invalid")',
        "checksum_pattern.fullmatch",
        'raise SystemExit(f"non-canonical checksum manifest: {manifest}")',
        'release.get("immutable") is not True',
        'raise SystemExit("release is not immutable")',
        'release.get("draft") is not False',
        'raise SystemExit("release is still a draft")',
        'raise SystemExit("release is not published")',
        'raise SystemExit("release asset is not published")',
        'raise SystemExit("release asset public URL mismatch")',
        "for attempt in {1..30}; do",
        "sleep 60",
        'test "$release_ready" = true',
        'test "$(git -C "$GITHUB_WORKSPACE" rev-parse HEAD)" = "$CANDIDATE_SHA"',
        'python "$release_source/scripts/build_release_assets.py"',
        'cmp --silent "$asset_name" "$public_dir/$asset_name"',
        'cmp --silent "$asset_name" "$reproduced_dir/$asset_name"',
        'cmp --silent "$public_dir/$asset_name" "$reproduced_dir/$asset_name"',
    )
    for fragment in required:
        if fragment not in shell:
            raise AssertionError(f"release gate lost fail-closed fragment: {fragment}")
    checkout = _named_step(job, "Check out the exact Pages candidate")
    setup = _named_step(job, "Select release-builder Python 3.12")
    if "ref: ${{ github.sha }}" not in checkout or "persist-credentials: false" not in checkout:
        raise AssertionError("Pages candidate checkout is not exact and credential-free")
    if not re.search(r"(?m)^          fetch-depth: 0$", checkout):
        raise AssertionError("release ancestry validation requires the complete Pages candidate history")
    executable_lines = [
        line.strip()
        for line in shell.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    release_tag_fetch = 'git -C "$GITHUB_WORKSPACE" fetch --no-tags --depth=1 origin "$resolved_sha"'
    exact_sha_check = 'if [[ "$resolved_sha" != "$CANDIDATE_SHA" ]]; then'
    if release_tag_fetch not in executable_lines:
        raise AssertionError("release source is not fetched after its immutable tag resolves")
    if executable_lines.index(release_tag_fetch) > executable_lines.index(exact_sha_check):
        raise AssertionError("release source must be fetched before exact Pages/tag validation")
    if 'git -C "$GITHUB_WORKSPACE" worktree add --detach "$release_source" "$resolved_sha"' not in shell:
        raise AssertionError("release reproduction does not use an exact detached tag source")
    if '--source "$GITHUB_WORKSPACE"' in shell:
        raise AssertionError("immutable release reproduction must not rebuild the mutable Pages candidate")
    if 'python-version: "3.12"' not in setup:
        raise AssertionError("release reproduction must use pinned Python 3.12")
    nonempty_lines = [line for line in shell.splitlines() if line.strip()]
    if not nonempty_lines or nonempty_lines[0] != "set -euo pipefail":
        raise AssertionError("release verification must start in exact strict shell mode")
    if any(line.startswith("set ") for line in nonempty_lines[1:]):
        raise AssertionError("release verification may not relax strict shell mode")
    if "||" in shell:
        raise AssertionError("release verification may not tolerate a failed command")
    if not re.search(
        r'(?m)^if \[\[ "\$resolved_sha" != "\$CANDIDATE_SHA" \]\]; then$',
        shell,
    ):
        raise AssertionError("release tag must resolve to the exact Pages candidate")
    if '"$asset_api" --output "$asset_name"' not in shell:
        raise AssertionError("release download must consume the validated asset API URL")
    public_download = re.search(
        r'(?ms)^\s*public_url="https://github\.com/\$\{GITHUB_REPOSITORY\}/releases/download/\$\{RELEASE_TAG\}/\$\{asset_name\}"\n'
        r'(?P<curl>\s*curl .*?"\$public_url" --output "\$public_dir/\$asset_name")$',
        shell,
    )
    if public_download is None or "Authorization:" in public_download.group("curl"):
        raise AssertionError("public asset download must be exact, HTTPS-only, and unauthenticated")
    if "while true" in shell or "for attempt in {1..30}; do" not in shell:
        raise AssertionError("release readiness retry must be bounded to thirty attempts")
    for manifest in (
        "install.ps1.sha256",
        "install.sh.sha256",
        "arbiter-academy-preview-0.19.zip.sha256",
    ):
        if not re.search(
            rf"(?m)^sha256sum --check {re.escape(manifest)}$",
            shell,
        ):
            raise AssertionError(f"release gate does not verify {manifest}")


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
        self.browser = _block(
            self.verify_workflow, "  academy-browser:", r"  [a-zA-Z0-9_-]+:"
        )
        self.main_verify = _block(
            self.pages_workflow, "  verify-main:", r"  [a-zA-Z0-9_-]+:"
        )
        self.build = _block(self.pages_workflow, "  build:", r"  [a-zA-Z0-9_-]+:")
        self.deploy = _block(self.pages_workflow, "  deploy:", r"  [a-zA-Z0-9_-]+:")

    def test_pages_release_gate_targets_the_exact_preview_zero_nineteen_candidate(self) -> None:
        """Catches Pages reproducing or accepting superseded preview release assets."""
        self.assertEqual(
            RELEASE_ASSETS,
            (
                "install.ps1",
                "install.ps1.sha256",
                "install.sh",
                "install.sh.sha256",
                "arbiter-academy-preview-0.19.zip",
                "arbiter-academy-preview-0.19.zip.sha256",
            ),
        )
        release_job = _workflow_jobs(self.pages_workflow)["verify-release"]
        self.assertRegex(release_job, r"(?m)^      RELEASE_TAG: preview-0\.19\s*$")
        self.assertRegex(release_job, r"(?m)^      RELEASE_EPOCH: 1787011200\s*$")
        self.assertNotIn("preview-0.7", release_job)

    def test_workflow_verifies_pull_requests_and_main_pushes(self) -> None:
        verify_trigger = _block(self.verify_workflow, "on:", r"[a-zA-Z0-9_-]+:")
        pages_trigger = _block(self.pages_workflow, "on:", r"[a-zA-Z0-9_-]+:")
        self.assertRegex(verify_trigger, r"(?m)^  pull_request:\s*$")
        self.assertNotRegex(verify_trigger, r"(?m)^  push:\s*$")
        self.assertNotIn("pull_request", pages_trigger)
        self.assertRegex(pages_trigger, r"(?ms)^  push:\s+branches:\s+- main\s*$")
        self.assertIn("github.ref == 'refs/heads/main'", self.deploy)

    def test_browser_visual_baselines_use_a_fixed_public_release_identity(self) -> None:
        """Visual snapshots must not churn merely because a PR head SHA changes."""
        self.assertRegex(
            self.browser,
            r"(?m)^      CA_VISUAL_RELEASE_SHA: a{40}\s*$",
        )

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
                "node --test tests/site/academy.test.mjs",
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
            ("verify_candidate", "Verify Academy browser controls", "continue on error"),
            ("build", "Verify Academy browser controls", "step if"),
            ("verify_candidate", "Build the Academy site", "shell exit zero"),
            ("build", "Build the Academy site", "shell or success"),
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
            odd_name = "- odd name [brackets] Î©.txt"
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
        self.assertIn("build", _job_needs(self.deploy))

    def test_pages_deploy_requires_a_successful_release_asset_gate(self) -> None:
        """Catches Pages publishing before the immutable release is ready."""
        jobs = _workflow_jobs(self.pages_workflow)
        release_jobs = [
            (job_id, job)
            for job_id, job in jobs.items()
            if all(asset in job for asset in RELEASE_ASSETS)
        ]
        self.assertEqual(
            len(release_jobs),
            1,
            "Pages must have one pre-deploy job that verifies all six Preview 0.6 assets",
        )
        release_job_id, release_job = release_jobs[0]
        self.assertRegex(release_job, r"(?m)^    outputs:\s*$")
        self.assertRegex(
            release_job,
            r"(?m)^      verified: \$\{\{ steps\.[a-zA-Z0-9_-]+\.outputs\.verified \}\}\s*$",
        )
        self.assertTrue(
            {"build", release_job_id}.issubset(_job_needs(self.deploy)),
            "deploy must need both the site build and release-asset gate",
        )
        self.assertIn(
            f"needs.{release_job_id}.outputs.verified == 'true'",
            self.deploy,
        )

    def test_release_asset_gate_resolves_preview_tag_to_exact_candidate_and_checks_all_digests(self) -> None:
        """Catches a release gate accepting a stale tag, missing asset, or unchecked bytes."""
        jobs = _workflow_jobs(self.pages_workflow)
        release_jobs = [
            job
            for job in jobs.values()
            if all(asset in job for asset in RELEASE_ASSETS)
        ]
        self.assertEqual(
            len(release_jobs),
            1,
            "release verification job with the exact six-asset inventory is missing",
        )
        release_job = release_jobs[0]
        self.assertRegex(release_job, r"(?m)^      RELEASE_TAG: preview-0\.19\s*$")
        self.assertRegex(release_job, r"(?m)^      CANDIDATE_SHA: \$\{\{ github\.sha \}\}\s*$")
        self.assertIn(
            "api.github.com/repos/${GITHUB_REPOSITORY}/releases/tags/${RELEASE_TAG}",
            release_job,
        )
        self.assertIn("$CANDIDATE_SHA", release_job)
        self.assertRegex(
            release_job,
            r"(?i)(?:tag|commit).{0,80}(?:resolve|target|object|sha)",
        )
        for asset in RELEASE_ASSETS:
            with self.subTest(asset=asset):
                self.assertIn(asset, release_job)
        for checksum in (
            "install.ps1.sha256",
            "install.sh.sha256",
            "arbiter-academy-preview-0.19.zip.sha256",
        ):
            with self.subTest(checksum=checksum):
                self.assertRegex(
                    release_job,
                    rf"sha256sum\s+(?:--check|-c)\s+[^\n]*{re.escape(checksum)}",
                )
        self.assertRegex(
            release_job,
            r"(?m)^\s*echo [\"']verified=true[\"']\s*>>\s*[\"']?\$GITHUB_OUTPUT[\"']?\s*$",
        )

    def test_release_gate_waits_boundedly_for_the_complete_immutable_release(self) -> None:
        """Catches the sole main-push run racing release publication or accepting mutable metadata."""
        release_job = _workflow_jobs(self.pages_workflow)["verify-release"]
        shell = _literal_step_script(release_job, "Verify immutable Preview release assets")
        self.assertIn("for attempt in {1..30}; do", shell)
        self.assertIn("sleep 60", shell)
        self.assertIn('test "$release_ready" = true', shell)
        self.assertNotIn("while true", shell)
        self.assertIn('release.get("immutable") is not True', shell)
        self.assertIn('release.get("draft") is not False', shell)
        self.assertIn('not isinstance(release.get("published_at"), str)', shell)
        loop = shell.index("for attempt in {1..30}; do")
        immutable = shell.index('release.get("immutable") is not True')
        ready = shell.index('test "$release_ready" = true')
        self.assertLess(loop, immutable)
        self.assertLess(immutable, ready)

    def test_release_job_timeout_exceeds_retry_window_with_rebuild_margin(self) -> None:
        """Catches the job timeout expiring before release polling and verification can finish."""
        release_job = _workflow_jobs(self.pages_workflow)["verify-release"]
        shell = _literal_step_script(release_job, "Verify immutable Preview release assets")
        timeout_match = re.search(r"(?m)^    timeout-minutes:\s*(\d+)\s*$", release_job)
        retry_match = re.search(r"for attempt in \{1\.\.(\d+)\}; do", shell)
        sleep_match = re.search(r"(?m)^\s*sleep\s+(\d+)\s*$", shell)
        self.assertIsNotNone(timeout_match)
        self.assertIsNotNone(retry_match)
        self.assertIsNotNone(sleep_match)
        timeout_seconds = int(timeout_match.group(1)) * 60
        retry_window_seconds = int(retry_match.group(1)) * int(sleep_match.group(1))
        setup_download_rebuild_margin_seconds = 10 * 60
        self.assertGreater(
            timeout_seconds,
            retry_window_seconds + setup_download_rebuild_margin_seconds,
        )

    def test_release_gate_reproduces_all_assets_from_the_exact_tag(self) -> None:
        """Catches remote assets being trusted without rebuilding their immutable tag source."""
        release_job = _workflow_jobs(self.pages_workflow)["verify-release"]
        checkout = _named_step(release_job, "Check out the exact Pages candidate")
        setup = _named_step(release_job, "Select release-builder Python 3.12")
        shell = _literal_step_script(release_job, "Verify immutable Preview release assets")
        self.assertIn(
            "uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1",
            checkout,
        )
        self.assertIn("ref: ${{ github.sha }}", checkout)
        self.assertIn("persist-credentials: false", checkout)
        self.assertIn('git -C "$GITHUB_WORKSPACE" fetch --no-tags --depth=1 origin "$resolved_sha"', shell)
        self.assertIn('git -C "$GITHUB_WORKSPACE" worktree add --detach "$release_source" "$resolved_sha"', shell)
        self.assertIn(
            "uses: actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97 # v7.0.0",
            setup,
        )
        self.assertRegex(setup, r'(?m)^          python-version: ["\']3\.12["\']\s*$')
        self.assertRegex(release_job, r"(?m)^      RELEASE_EPOCH: 1787011200\s*$")
        self.assertIn(
            'test "$(git -C "$GITHUB_WORKSPACE" rev-parse HEAD)" = "$CANDIDATE_SHA"',
            shell,
        )
        self.assertIn(
            'test "$(git -C "$release_source" rev-parse HEAD)" = "$resolved_sha"',
            shell,
        )
        self.assertIn('python "$release_source/scripts/build_release_assets.py"', shell)
        self.assertIn('--source "$release_source"', shell)
        self.assertIn('--output "$reproduced_dir"', shell)
        self.assertIn('--epoch "$RELEASE_EPOCH"', shell)
        self.assertIn('--release "$RELEASE_TAG"', shell)
        self.assertIn('cmp --silent "$asset_name" "$reproduced_dir/$asset_name"', shell)
        self.assertIn('--proto-redir "=https"', shell)
        self.assertIn('public_url="https://github.com/${GITHUB_REPOSITORY}/releases/download/${RELEASE_TAG}/${asset_name}"', shell)
        self.assertIn('cmp --silent "$asset_name" "$public_dir/$asset_name"', shell)
        self.assertIn('cmp --silent "$public_dir/$asset_name" "$reproduced_dir/$asset_name"', shell)
        build = shell.index('python "$release_source/scripts/build_release_assets.py"')
        compare = shell.index('cmp --silent "$asset_name" "$reproduced_dir/$asset_name"')
        verified = shell.index('echo "verified=true" >> "$GITHUB_OUTPUT"')
        self.assertLess(build, compare)
        self.assertLess(compare, verified)

    def test_release_gate_requires_the_immutable_tag_to_match_the_pages_candidate(self) -> None:
        """Catches Pages publishing later main content under an older immutable release identity."""
        release_job = _workflow_jobs(self.pages_workflow)["verify-release"]
        shell = _literal_step_script(release_job, "Verify immutable Preview release assets")

        self.assertIn(
            'if [[ "$resolved_sha" != "$CANDIDATE_SHA" ]]; then',
            shell,
        )
        self.assertNotIn('merge-base --is-ancestor "$resolved_sha" "$CANDIDATE_SHA"', shell)
        self.assertNotIn('release_bound_paths=', shell)
        self.assertNotIn('release-bound files changed after the immutable tag.', shell)
        self.assertIn('python "$release_source/scripts/build_release_assets.py"', shell)
        self.assertIn('--source "$release_source"', shell)

    def test_release_metadata_validator_rejects_noncanonical_checksums_and_inventory_drift(self) -> None:
        """Catches ambiguous digest files or a release asset multiset beyond the six approved names."""
        validator = _release_validation_script(self.pages_workflow)
        self.assertTrue(validator, "release metadata validator is missing")

        def run_validator(
            assets: list[dict[str, object]],
            checksum_overrides: dict[str, bytes] | None = None,
            immutable: object = True,
        ) -> subprocess.CompletedProcess[str]:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "release.json").write_text(
                    json.dumps(
                        {
                            "tag_name": "preview-0.19",
                            "immutable": immutable,
                            "draft": False,
                            "published_at": "2026-08-10T12:00:00Z",
                            "assets": assets,
                        }
                    ),
                    encoding="utf-8",
                )
                checksums = {
                    "install.ps1.sha256": f"{'a' * 64}  install.ps1\n".encode(),
                    "install.sh.sha256": f"{'b' * 64}  install.sh\n".encode(),
                    "arbiter-academy-preview-0.19.zip.sha256": (
                        f"{'c' * 64}  arbiter-academy-preview-0.19.zip\n".encode()
                    ),
                }
                checksums.update(checksum_overrides or {})
                for name, content in checksums.items():
                    (root / name).write_bytes(content)
                environment = os.environ.copy()
                environment["RELEASE_TAG"] = "preview-0.19"
                environment["GITHUB_REPOSITORY"] = "arbiterForge/arbiter-academy"
                return subprocess.run(
                    [sys.executable, "-c", validator],
                    cwd=root,
                    env=environment,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=False,
                )

        valid_assets = [
            {
                "id": index,
                "name": name,
                "browser_download_url": (
                    f"https://github.com/arbiterForge/arbiter-academy/releases/download/"
                    f"preview-0.19/{name}"
                ),
                "state": "uploaded",
            }
            for index, name in enumerate(RELEASE_ASSETS, start=1)
        ]
        accepted = run_validator(valid_assets)
        self.assertEqual(accepted.returncode, 0, accepted.stderr)

        for mutable in (False, None, 1, "true"):
            with self.subTest(immutable=mutable):
                self.assertNotEqual(run_validator(valid_assets, immutable=mutable).returncode, 0)

        release_state_cases = (
            {"draft": True},
            {"draft": None},
            {"published_at": None},
            {"published_at": ""},
        )
        for mutation in release_state_cases:
            with self.subTest(release_state=mutation):
                # The validator fixture is intentionally rewritten to pressure the real script.
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    release = {
                        "tag_name": "preview-0.19",
                        "immutable": True,
                        "draft": False,
                        "published_at": "2026-08-10T12:00:00Z",
                        "assets": valid_assets,
                    }
                    release.update(mutation)
                    (root / "release.json").write_text(json.dumps(release), encoding="utf-8")
                    for name, digest in (
                        ("install.ps1.sha256", "a"),
                        ("install.sh.sha256", "b"),
                        ("arbiter-academy-preview-0.19.zip.sha256", "c"),
                    ):
                        target = name.removesuffix(".sha256")
                        (root / name).write_bytes(f"{digest * 64}  {target}\n".encode())
                    environment = os.environ.copy()
                    environment["RELEASE_TAG"] = "preview-0.19"
                    environment["GITHUB_REPOSITORY"] = "arbiterForge/arbiter-academy"
                    rejected = subprocess.run(
                        [sys.executable, "-c", validator], cwd=root, env=environment,
                        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
                    )
                    self.assertNotEqual(rejected.returncode, 0)

        for mutation in (
            {"state": "new"},
            {"state": None},
            {"browser_download_url": "http://github.com/arbiterForge/arbiter-academy/releases/download/preview-0.19/install.ps1"},
            {"browser_download_url": "https://evil.example/preview-0.19/install.ps1"},
        ):
            with self.subTest(asset_state=mutation):
                assets = [dict(asset) for asset in valid_assets]
                assets[0].update(mutation)
                self.assertNotEqual(run_validator(assets).returncode, 0)

        inventory_cases = {
            "extra": valid_assets + [{"id": 99, "name": "unreviewed.bin"}],
            "duplicate": valid_assets + [valid_assets[0]],
            "missing": valid_assets[:-1],
        }
        for case, assets in inventory_cases.items():
            with self.subTest(inventory=case):
                self.assertNotEqual(run_validator(assets).returncode, 0)

        checksum_cases = {
            "duplicate-entry": {
                "install.ps1.sha256": (
                    f"{'a' * 64}  install.ps1\n{'a' * 64}  install.ps1\n"
                ).encode()
            },
            "wrong-file": {
                "install.sh.sha256": f"{'b' * 64}  other.sh\n".encode()
            },
            "uppercase": {
                "arbiter-academy-preview-0.19.zip.sha256": (
                    f"{'C' * 64}  arbiter-academy-preview-0.19.zip\n"
                ).encode()
            },
            "single-space": {
                "install.ps1.sha256": f"{'a' * 64} install.ps1\n".encode()
            },
            "missing-lf": {
                "install.sh.sha256": f"{'b' * 64}  install.sh".encode()
            },
        }
        for case, override in checksum_cases.items():
            with self.subTest(checksum=case):
                self.assertNotEqual(
                    run_validator(valid_assets, override).returncode,
                    0,
                )

    def test_release_gate_contract_rejects_fail_open_security_mutations(self) -> None:
        """Catches exact-SHA, digest, inventory, or authenticated-download checks being bypassed."""
        _assert_release_gate_is_fail_closed(self.pages_workflow)
        release_job = _workflow_jobs(self.pages_workflow)["verify-release"]
        fail_open_job = release_job.replace("set -euo pipefail", "set +e", 1)
        mutations = {
            "sha-echo": self.pages_workflow.replace(
                'if [[ "$resolved_sha" != "$CANDIDATE_SHA" ]]; then',
                'echo "$resolved_sha $CANDIDATE_SHA"',
                1,
            ),
            "checksum-or-true": self.pages_workflow.replace(
                "sha256sum --check install.ps1.sha256",
                "sha256sum --check install.ps1.sha256 || true",
                1,
            ),
            "inventory-warning": self.pages_workflow.replace(
                'raise SystemExit("release asset inventory mismatch")',
                'print("release asset inventory mismatch")',
                1,
            ),
            "unsafe-url": self.pages_workflow.replace(
                'releases/assets/${asset_id}',
                'downloads/${asset_name}?source=untrusted#asset',
                1,
            ),
            "sha-or-colon": self.pages_workflow.replace(
                'if [[ "$resolved_sha" != "$CANDIDATE_SHA" ]]; then',
                'if false; then',
                1,
            ),
            "checksum-or-colon": self.pages_workflow.replace(
                "sha256sum --check install.ps1.sha256",
                "sha256sum --check install.ps1.sha256 || :",
                1,
            ),
            "shell-fail-open": self.pages_workflow.replace(
                release_job,
                fail_open_job,
                1,
            ),
            "download-release-json": self.pages_workflow.replace(
                '"$asset_api" --output "$asset_name"',
                '"$release_api" --output "$asset_name"',
                1,
            ),
            "immutable-warning": self.pages_workflow.replace(
                'raise SystemExit("release is not immutable")',
                'print("release is not immutable")',
                1,
            ),
            "draft-warning": self.pages_workflow.replace(
                'raise SystemExit("release is still a draft")',
                'print("release is still a draft")',
                1,
            ),
            "unbounded-retry": self.pages_workflow.replace(
                "for attempt in {1..30}; do",
                "while true; do",
                1,
            ),
            "single-attempt": self.pages_workflow.replace(
                "for attempt in {1..30}; do",
                "for attempt in {1..1}; do",
                1,
            ),
            "no-retry-delay": self.pages_workflow.replace("sleep 60", ":", 1),
            "wrong-release-checkout": self.pages_workflow.replace(
                release_job,
                release_job.replace("ref: ${{ github.sha }}", "ref: main", 1),
                1,
            ),
            "shallow-release-history-comment": self.pages_workflow.replace(
                release_job,
                release_job.replace(
                    "fetch-depth: 0",
                    "fetch-depth: 1 # fetch-depth: 0",
                    1,
                ),
                1,
            ),
            "late-release-tag-fetch-comment": self.pages_workflow.replace(
                'git -C "$GITHUB_WORKSPACE" fetch --no-tags --depth=1 origin "$resolved_sha"',
                '# git -C "$GITHUB_WORKSPACE" fetch --no-tags --depth=1 origin "$resolved_sha"',
                1,
            ).replace(
                'release_source="$RUNNER_TEMP/academy-release-source"',
                'git -C "$GITHUB_WORKSPACE" fetch --no-tags --depth=1 origin "$resolved_sha"\n'
                '          release_source="$RUNNER_TEMP/academy-release-source"',
                1,
            ),
            "wrong-release-python": self.pages_workflow.replace(
                release_job,
                release_job.replace('python-version: "3.12"', 'python-version: "3.11"', 1),
                1,
            ),
            "skip-public-compare": self.pages_workflow.replace(
                'cmp --silent "$asset_name" "$public_dir/$asset_name"',
                'echo "$asset_name $public_dir/$asset_name"',
                1,
            ),
            "skip-reproduced-compare": self.pages_workflow.replace(
                'cmp --silent "$asset_name" "$reproduced_dir/$asset_name"',
                'echo "$asset_name $reproduced_dir/$asset_name"',
                1,
            ),
            "public-download-auth": self.pages_workflow.replace(
                '"$public_url" --output "$public_dir/$asset_name"',
                '--header "Authorization: Bearer ${GITHUB_TOKEN}" \\\n+              "$public_url" --output "$public_dir/$asset_name"',
                1,
            ),
        }
        for mutation, workflow in mutations.items():
            with self.subTest(mutation=mutation):
                with self.assertRaises(AssertionError):
                    _assert_release_gate_is_fail_closed(workflow)

    def test_workflow_adds_no_install_or_third_party_action_step(self) -> None:
        actions = re.findall(r"(?m)^\s*-?\s*uses:\s*([^\s]+)", self.workflow)
        self.assertTrue(actions)
        self.assertTrue(
            all(
                action.startswith(("actions/", "actions/upload-artifact@"))
                for action in actions
            ),
            actions,
        )
        self.assertTrue(
            all(re.fullmatch(r"actions/[a-z-]+@[0-9a-f]{40}", action) for action in actions),
            actions,
        )
        for job in (self.verify, self.verify_candidate, self.main_verify, self.build):
            with self.subTest(job=job[:32]):
                self.assertNotRegex(job, r"(?i)\b(?:pip|npm|pnpm|yarn)\s+(?:ci|install)\b")
                self.assertNotRegex(job, r"(?i)\bnpx\b|https?://[^\s]+\.js\b|\bcdn\b")
        self.assertIn("npm ci --ignore-scripts", self.browser)
        self.assertIn("./node_modules/.bin/playwright install --with-deps --only-shell chromium", self.browser)
        self.assertNotRegex(self.browser, r"(?i)\bnpx\b|https?://[^\s]+\.js\b|\bcdn\b")

    def test_each_candidate_gate_runs_browser_controls_before_site_build(self) -> None:
        """Catches a PR or deployment build skipping browser controls before rendering."""
        for label, job in (
            ("pull request", self.verify_candidate),
            ("main", self.build),
        ):
            with self.subTest(label=label):
                node_setup = job.find("- name: Select Node 22.19.0")
                javascript = job.find("node --test tests/site/academy.test.mjs")
                build = job.find("- name: Build the Academy site")
                self.assertEqual(_named_step(job, "Select Node 22.19.0"), NODE_SETUP_STEP)
                self.assertGreaterEqual(node_setup, 0)
                self.assertGreaterEqual(javascript, 0)
                self.assertGreater(javascript, node_setup)
                self.assertGreater(build, javascript)

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

    def test_academy_checkouts_retain_the_real_training_history(self) -> None:
        """Catches hosted fixtures losing reviewed ancestor commits to shallow checkout."""
        academy_checkouts = (
            (self.verify, "Check out the exact Academy candidate"),
            (self.verify_candidate, "Check out the exact Academy candidate"),
            (self.main_verify, "Check out the exact reviewed main commit"),
            (self.build, "Check out the exact reviewed main commit"),
        )
        for job, step_name in academy_checkouts:
            with self.subTest(step=step_name):
                checkout = _named_step(job, step_name)
                self.assertIn("fetch-depth: 0", checkout)

    def test_hosted_verifier_has_pinned_codearbiter_and_offline_build_wheel(self) -> None:
        """Catches hosted acceptance running without its reviewed local prerequisites."""
        for label, job in (("pull request", self.verify), ("main", self.main_verify)):
            with self.subTest(job=label):
                self.assertIn("repository: arbiterForge/codeArbiter", job)
                self.assertIn("ref: debb49da71aa1b97bca0988f72e46bb5875a23e3", job)
                self.assertIn("CODEARBITER_SOURCE_SHA: debb49da71aa1b97bca0988f72e46bb5875a23e3", job)
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
