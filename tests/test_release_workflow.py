"""Static contract tests for the hosted Academy release publisher."""

from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RELEASE_WORKFLOW = ROOT / ".github" / "workflows" / "academy-release.yml"

GUARD = "if: github.repository == 'arbiterForge/arbiter-academy' && github.ref == 'refs/heads/main'"
FULL_REFSPEC_PUSH = 'push origin "refs/tags/$RELEASE_TAG:refs/tags/$RELEASE_TAG"'
RELEASE_BUILD = '( eval "$release_build" )'
REQUIRED_PREFLIGHT_CHECKS = (
    # The pinned helper source is published codeArbiter history.
    'gh api "repos/arbiterForge/codeArbiter/compare/$CODEARBITER_SHA...main"',
    'if [[ "$status" != identical && "$status" != ahead ]]; then',
    # Main has not moved since dispatch.
    'remote_main="$(git ls-remote origin refs/heads/main | cut -f1)"',
    # The dispatched commit is the release-prep merge that advanced the changelog.
    'git log --first-parent -1 --format=%H -- "$changelog"',
    'helper check-manifests "$target" "$VERSION"',
    "--allow-absent-path",
    # The repository still locks published releases.
    "--json isImmutable --jq '.isImmutable')\" = true",
    # Exact-head CI evidence from the Pages push run on main for this commit.
    "academy-pages.yml/runs?event=push&branch=main&head_sha=$candidate",
    '"$run_branch" != main || "$run_sha" != "$candidate" || "$run_event" != push',
    "if len(shards) != 16 or not all(map(passed, shards)):",
    "if len(builds) != 1 or not passed(builds[0]):",
)
REQUIRED_ASSET_CHECKS = (
    # The installers and checksums are the reviewed, committed bytes.
    'git show "$CANDIDATE_SHA:install/$name" | cmp - "$assets/$name"',
    # Both installers embed exactly the bundle being published.
    'test "$(grep -o "$bundle_digest" "$assets/$installer" | wc -l)" -eq 1',
    "printf '%s  %s\\n' \"$bundle_digest\" \"$bundle\" | cmp - \"$assets/$bundle.sha256\"",
)
REQUIRED_PUBLISH_BINDINGS = (
    '[[ "$VERSION" =~ ^[0-9]+\\.[0-9]+$ ]]',
    'prefix="$(python -E -s "$lib" show-row "$target" --field prefix)"',
    'test "$RELEASE_TAG" = "$prefix$VERSION"',
    'test "$(python -E -s "$lib" show-row "$target" --field latest-eligible)" = "true"',
)
# Repository code must never run beside the write token.
PUBLISH_FORBIDDEN = ("eval", "scripts/", "academy_engine", "build_release_assets", "pip ", "npm ", "python -m")
PREFLIGHT_FORBIDDEN = ("academy_engine", "scripts/", "python -m")
FORBIDDEN = ("--force", "push --delete", "push -d ", "gh release delete", "git tag -d", "git tag -f", "tag -a -f")


def _jobs(text: str) -> dict[str, str]:
    body = text.split("\njobs:\n", 1)[1]
    names = list(re.finditer(r"(?m)^  ([a-z][a-z0-9-]*):\n", body))
    return {
        match.group(1): body[match.end(): names[index + 1].start() if index + 1 < len(names) else len(body)]
        for index, match in enumerate(names)
    }


def _steps(job: str) -> dict[str, str]:
    names = list(re.finditer(r"(?m)^      - name: (.+)\n", job))
    return {
        match.group(1): job[match.end(): names[index + 1].start() if index + 1 < len(names) else len(job)]
        for index, match in enumerate(names)
    }


def _run_blocks(text: str) -> list[str]:
    return [match.group(2) for match in re.finditer(r"(?m)^( +)run: \|\n((?:\1  .*\n|[ \t]*\n)*)", text)]


def contract_problems(text: str) -> list[str]:
    """Name every way *text* breaks the publisher's release contract."""
    problems: list[str] = []
    triggers = text.split("\non:\n", 1)[1].split("\npermissions:\n", 1)[0]
    if "workflow_dispatch:" not in triggers:
        problems.append("the publisher must be dispatched by a maintainer")
    for automatic in ("push:", "pull_request", "workflow_run", "schedule:", "release:"):
        if automatic in triggers:
            problems.append(f"the publisher must not start on {automatic.rstrip(':')}")
    if not re.search(r"(?m)^permissions:\n  contents: read\n\n", text):
        problems.append("top-level permissions must be contents: read only")
    if not re.search(r"(?m)^concurrency:\n  group: academy-release\n  cancel-in-progress: false\n", text):
        problems.append("publications must queue, never cancel each other")

    jobs = _jobs(text)
    if set(jobs) != {"preflight", "build", "publish"}:
        return problems + [f"expected preflight, build and publish jobs, found {sorted(jobs)}"]
    preflight, build, publish = jobs["preflight"], jobs["build"], jobs["publish"]
    for name, job in jobs.items():
        if f"    {GUARD}\n" not in job:
            problems.append(f"{name} must run only on main in the Academy repository")
    if "    needs: preflight\n" not in build:
        problems.append("build must wait for preflight")
    if "    needs: [preflight, build]\n" not in publish:
        problems.append("publish must wait for preflight and build")

    # Only publish writes, behind its environment, and only build runs repository build code.
    if text.count("contents: write") != 1 or "    permissions:\n      contents: write\n    env:\n" not in publish:
        problems.append("only the publish job may write contents")
    if "    environment: academy-release\n" not in publish:
        problems.append("publish must run in the academy-release environment")
    if "      contents: read\n      actions: read\n" not in preflight or re.search(r"(?m)^\s+[a-z-]+: write\s*$", preflight):
        problems.append("preflight must stay read-only")
    if "    permissions:\n      contents: read\n    env:\n" not in build:
        problems.append("build must hold only contents: read")
    for credential in ("GH_TOKEN", "github.token", "secrets."):
        if credential in build:
            problems.append(f"no credential may reach the release build: {credential}")
    if text.count(RELEASE_BUILD) != 1 or RELEASE_BUILD not in build:
        problems.append("the declared release build must run once, in the build job")
    for token in PUBLISH_FORBIDDEN:
        if token in publish:
            problems.append(f"publish must not run repository code: {token}")
    for call in re.findall(r"(?<![\w-])python3?(?=\s)[^\n]*", publish):
        if not call.startswith(('python -E -s "$lib"', "python -I -")):
            problems.append(f"publish must run Python isolated: {call.strip()}")

    # Academy code must not select the external helper that later runs beside
    # the write token. Read the exact candidate manifest only as inert JSON.
    source_step = _steps(preflight).get("Read the Preview compatibility source as data", "")
    for token in PREFLIGHT_FORBIDDEN:
        if token in preflight:
            problems.append(f"preflight must not run Academy code: {token}")
    for call in re.findall(r"(?<![\w-])python3?(?=\s)[^\n]*", preflight):
        if not call.startswith(('python -E -s "$lib"', "python -I -")):
            problems.append(f"preflight must run Python isolated: {call.strip()}")
    required_source_checks = (
        'if [[ ! "$VERSION" =~ ^[0-9]+\\.[0-9]+$ ]]; then',
        'git show "$GITHUB_SHA:academy/publication/preview-$VERSION.json"',
        'manifest = json.load(open(sys.argv[1], encoding="utf-8"))',
        'components = manifest.get("integration_compatibility", {}).get("components")',
        "if not isinstance(components, list) or len(components) != 3:",
        "if any(not isinstance(component, dict) for component in components):",
        "if len(source_commits) != 1:",
        'if re.fullmatch(r"[0-9a-f]{40}", source) is None:',
    )
    for check in required_source_checks:
        if check not in source_step:
            problems.append(f"helper-source binding is missing: {check}")

    for line in re.findall(r"(?m)^\s+uses: (\S+)", text):
        if not re.fullmatch(r"[\w.-]+/[\w.-]+@[0-9a-f]{40}", line):
            problems.append(f"action {line} is not pinned to a commit")
    if text.count("uses: actions/checkout@") != text.count("persist-credentials: false"):
        problems.append("every checkout must drop its credentials")
    for line in re.findall(r"(?m)^.*\$\{\{ (?:inputs|github\.event\.inputs)\..*$", text):
        if not re.fullmatch(r"\s+[A-Z_]+: \$\{\{ inputs\.[a-z_]+ \}\}", line):
            problems.append(f"dispatch input reaches a script directly: {line.strip()}")
    for block in _run_blocks(text):
        if "${{" in block:
            problems.append("an expression is interpolated into a script; pass it through env")

    bind = _steps(preflight).get("Bind the release candidate", "")
    helper_source = _steps(preflight).get("Fetch the release helper from that codeArbiter source", "")
    for check in REQUIRED_PREFLIGHT_CHECKS:
        if check not in bind and check not in helper_source:
            problems.append(f"preflight is missing: {check}")
    if 'awk -v current="$release_tag" \'$0 != current\'' not in bind:
        problems.append("resume must exclude the requested tag from predecessor selection")
    if bind.find('tag_rows="$(git ls-remote --tags origin') > bind.find('last_tag="$(git tag -l'):
        problems.append("resume must classify the requested tag before checking its predecessor")
    monotonic_check = (
        'if [[ "$last_tag" != "<none>" ]]; then\n'
        '            helper version-greater "$VERSION" "${last_tag#"$prefix"}" "$policy" "$initial"'
    )
    if monotonic_check not in bind:
        problems.append("fresh and resumed releases must both advance the immutable predecessor")

    publish_steps = _steps(publish)
    asset_step = publish_steps.get("Check the assets against the committed installers", "")
    for check in REQUIRED_ASSET_CHECKS:
        if check not in asset_step:
            problems.append(f"asset check is missing: {check}")
    for check in REQUIRED_PUBLISH_BINDINGS:
        if check not in asset_step:
            problems.append(f"publish binding is missing: {check}")
    for name, step in publish_steps.items():
        if "GH_TOKEN" in step and 'python -E -s "$lib"' in step:
            problems.append(f"{name} must not run the external helper beside the write token")
    tag_step = publish_steps.get("Compose and check the annotated tag", "")
    if "--cleanup=verbatim" not in tag_step:
        problems.append("the tag message must keep its changelog headings")
    if 'cmp "$RUNNER_TEMP/release-tag-stored-body.md" "$body"' not in tag_step:
        problems.append("the stored tag message must be compared byte for byte")
    push_step = publish_steps.get("Push the tag", "")
    if FULL_REFSPEC_PUSH not in push_step:
        problems.append("the tag must be pushed by its full refspec")
    if "git -c core.hooksPath=/dev/null" not in push_step:
        problems.append("no Git hook may run while the token is in the push command")
    release_step = publish_steps.get("Publish the release", "")
    if "--verify-tag" not in release_step or '--notes-file "$RUNNER_TEMP/release-section.md"' not in release_step:
        problems.append("the release must use the pushed tag and the committed changelog section")
    readback = publish_steps.get("Read the release back", "")
    for check in ('if release.get("draft") is not False:', 'if release.get("immutable") is not True:',
                  "if published != expected:"):
        if check not in readback:
            problems.append(f"read-back is missing: {check}")
    for token in FORBIDDEN:
        if token in text:
            problems.append(f"a published tag or release must never be rewritten: {token}")
    return problems


class ReleaseWorkflowContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = RELEASE_WORKFLOW.read_text(encoding="utf-8")

    def test_publisher_meets_its_release_contract(self) -> None:
        self.assertEqual(contract_problems(self.text), [])

    def test_contract_rejects_each_unsafe_publisher_change(self) -> None:
        """Catches a publisher edit that weakens a release gate while the workflow still parses."""
        publish_head = "  publish:\n    needs: [preflight, build]\n"
        build_env_tail = "      RELEASE_TAG: ${{ needs.preflight.outputs.release-tag }}\n      PYTHONDONTWRITEBYTECODE"
        mutants = {
            "automatic trigger": ("on:\n  workflow_dispatch:", "on:\n  push:\n    branches: [main]\n  workflow_dispatch:"),
            "fork runs": (publish_head + "    " + GUARD, publish_head + "    if: github.ref == 'refs/heads/main'"),
            "writable token everywhere": ("permissions:\n  contents: read\n\nconcurrency", "permissions:\n  contents: write\n\nconcurrency"),
            "cancelled publication": ("cancel-in-progress: false", "cancel-in-progress: true"),
            "build without preflight": ("  build:\n    needs: preflight\n", "  build:\n"),
            "publish before build": (publish_head, "  publish:\n    needs: preflight\n"),
            "unprotected publish": ("    environment: academy-release\n", ""),
            "writable build": ("    permissions:\n      contents: read\n    env:\n", "    permissions:\n      contents: write\n    env:\n"),
            "token during build": (build_env_tail,
                                   build_env_tail.replace("\n", "\n      GH_TOKEN: ${{ github.token }}\n", 1)),
            "build beside the token": ('          bundle="arbiter-academy-$RELEASE_TAG.zip"',
                                       '          "$PY" scripts/build_release_assets.py --output "$assets"\n'
                                       '          bundle="arbiter-academy-$RELEASE_TAG.zip"'),
            "unisolated publish Python": ('python -I - "$RUNNER_TEMP/release-readback.json"',
                                          'python - "$RUNNER_TEMP/release-readback.json"'),
            "Academy code selects helper": ("import json", "from academy_engine.preview import load_preview_manifest"),
            "worktree manifest selects helper": ('git show "$GITHUB_SHA:academy/publication/preview-$VERSION.json"',
                                                  'cat "academy/publication/preview-$VERSION.json"'),
            "one component selects helper": ("if not isinstance(components, list) or len(components) != 3:",
                                              "if not isinstance(components, list):"),
            "non-object component selects helper": (
                "if any(not isinstance(component, dict) for component in components):",
                "if False:",
            ),
            "unisolated preflight Python": ('python -I - "$RUNNER_TEMP/preview-manifest.json"',
                                             'python - "$RUNNER_TEMP/preview-manifest.json"'),
            "requested tag used as predecessor": ('awk -v current="$release_tag" \'$0 != current\'', "cat"),
            "resume skips monotonic version check": (
                'if [[ "$last_tag" != "<none>" ]]; then\n'
                '            helper version-greater "$VERSION" "${last_tag#"$prefix"}" "$policy" "$initial"',
                'if [[ "$mode" = fresh && "$last_tag" != "<none>" ]]; then\n'
                '            helper version-greater "$VERSION" "${last_tag#"$prefix"}" "$policy" "$initial"',
            ),
            "malformed publish version": ('[[ "$VERSION" =~ ^[0-9]+\\.[0-9]+$ ]]', "true"),
            "different publish tag": ('test "$RELEASE_TAG" = "$prefix$VERSION"', "true"),
            "external helper beside write token": (
                'test "$(printf \'%s\\n\' "$remote_rows" | awk -v ref="refs/tags/$RELEASE_TAG^{}" \'$2 == ref { print $1 }\')" = "$CANDIDATE_SHA"',
                'test "$(printf \'%s\\n\' "$remote_rows" | python -E -s "$lib" peel-tag "$RELEASE_TAG")" = "$CANDIDATE_SHA"',
            ),
            "unpinned action": ("actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1", "actions/checkout@v7"),
            "persisted credentials": ("persist-credentials: false", "persist-credentials: true"),
            "input injection": ('if [[ ! "$VERSION" =~', 'if [[ ! "${{ inputs.version }}" =~'),
            "expression in a script": ('test "$(git -C "$helper_root" rev-parse HEAD)" = "$CODEARBITER_SHA"',
                                       'test "$(git -C "$helper_root" rev-parse HEAD)" = "${{ steps.codearbiter-source.outputs.sha }}"'),
            "fork-only helper source": ('if [[ "$status" != identical && "$status" != ahead ]]; then', "if false; then"),
            "moved main accepted": ('remote_main="$(git ls-remote origin refs/heads/main | cut -f1)"', 'remote_main="$candidate"'),
            "stale changelog accepted": ("git log --first-parent -1 --format=%H", "git log -1 --format=%H"),
            "mutable predecessor accepted": ("--json isImmutable --jq '.isImmutable')\" = true", "--json tagName --jq '.tagName')\" != ''"),
            "any-branch CI accepted": ("event=push&branch=main&head_sha", "event=push&head_sha"),
            "no exact-head CI": ("if len(shards) != 16 or not all(map(passed, shards)):", "if False:"),
            "unreviewed installers": ('git show "$CANDIDATE_SHA:install/$name" | cmp - "$assets/$name"', "true"),
            "unbound bundle": ('test "$(grep -o "$bundle_digest" "$assets/$installer" | wc -l)" -eq 1', "true"),
            "stripped tag headings": (" --cleanup=verbatim", ""),
            "hooks beside the token": ("git -c core.hooksPath=/dev/null \\\n              ", "git "),
            "short refspec push": (FULL_REFSPEC_PUSH, 'push origin "$RELEASE_TAG"'),
            "forced tag push": ("push origin \"refs/tags", "push --force origin \"refs/tags"),
            "unverified tag": (" --latest --verify-tag", " --latest"),
            "mutable release accepted": ('if release.get("immutable") is not True:', "if False:"),
            "unchecked asset digests": ("if published != expected:", "if False:"),
            "release deletion": ("gh release create", "gh release delete \"$RELEASE_TAG\" --yes\n          gh release create"),
        }
        for name, (old, new) in mutants.items():
            with self.subTest(mutant=name):
                self.assertIn(old, self.text)
                self.assertNotEqual(contract_problems(self.text.replace(old, new, 1)), [])


if __name__ == "__main__":
    unittest.main()
