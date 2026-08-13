"""Trusted U07 local-capstone fixture construction."""

from __future__ import annotations

import os
import ast
import tempfile
import textwrap
from pathlib import Path

from academy_engine.command import GitCommandError, run_git


class U07FixtureError(ValueError):
    """The U07 fixture cannot be constructed or verified exactly."""


U07_TEST_PATH = "tests/test_service.py"
U07_SERVICE_PATH = "workshop_queue/service.py"
U07_OVERLAY_PATH = "training_scenarios/U07-capstone.json"
U07_OVERLAY_SOURCE = "academy/scenarios/U07-capstone/files/scenario.json"
U07_FIXTURE_PATHS = (U07_TEST_PATH,)
_PREPARED_TEST = '''\n    def test_u07_prepared_resolution_control_is_accepted(self) -> None:
        claimed = claim_ticket([open_ticket("RQ-U07")], "RQ-U07", "Sam", fixed_now())
        updated = complete_ticket(claimed, "RQ-U07", "done\\nagain", fixed_now())
        self.assertEqual(updated[0].resolution, "done\\nagain")
'''
_TEST_ANCHOR = '\n\nif __name__ == "__main__":'
_SERVICE_DEFECT = '            if not resolution.strip():\n                raise ValueError("resolution must be non-empty")\n'
_SERVICE_REMEDIATION = (
    _SERVICE_DEFECT
    + '            if any(ord(character) < 32 or ord(character) == 127 for character in resolution):\n'
    + '                raise ValueError("resolution must not contain control characters")\n'
)


def _blob(repository: Path, ref: str, path: str) -> bytes | None:
    result = run_git(repository, ["show", f"{ref}:{path}"], check=False, trust_local_config=True)
    return result.stdout.encode("utf-8", "surrogateescape") if result.returncode == 0 else None


def _atomic_write(path: Path, raw: bytes) -> None:
    descriptor, temporary_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _prepared_test(base: bytes) -> bytes:
    try:
        text = base.decode("utf-8")
    except UnicodeDecodeError as error:
        raise U07FixtureError("U07 fixture test source is not UTF-8.") from error
    if text.count(_TEST_ANCHOR) != 1 or "test_u07_prepared_resolution_control_is_accepted" in text:
        raise U07FixtureError("U07 fixture test source is not canonical.")
    return text.replace(_TEST_ANCHOR, _PREPARED_TEST + _TEST_ANCHOR, 1).encode("utf-8")


def _service_has_prepared_defect(raw: bytes) -> bool:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return text.count(_SERVICE_DEFECT) == 1 and "resolution must not contain control characters" not in text


def stage_u07_fixture(repository: Path, *, base: str) -> tuple[str, ...]:
    """Stage the one known resolution-input defect on a fresh U07 attempt."""
    if run_git(repository, ["rev-parse", "HEAD"], trust_local_config=True).stdout.strip() != base:
        raise U07FixtureError("U07 fixture must be staged from its declared base.")
    test = _blob(repository, base, U07_TEST_PATH)
    service = _blob(repository, base, U07_SERVICE_PATH)
    if test is None or service is None or not _service_has_prepared_defect(service):
        raise U07FixtureError("U07 fixture base does not contain the reviewed resolution defect.")
    try:
        target = repository / U07_TEST_PATH
        _atomic_write(target, _prepared_test(test))
        run_git(repository, ["add", "--", *U07_FIXTURE_PATHS], trust_local_config=True)
    except (OSError, GitCommandError) as error:
        raise U07FixtureError("U07 fixture could not be staged.") from error
    return U07_FIXTURE_PATHS


def validate_u07_fixture(repository: Path, prepared: str) -> bool:
    """Prove the prepared attempt preserved exactly the declared local defect."""
    parents = run_git(repository, ["rev-list", "--parents", "-n", "1", prepared], check=False, trust_local_config=True).stdout.split()
    if len(parents) != 2 or parents[0] != prepared:
        return False
    base = parents[1]
    changed = tuple(run_git(repository, ["diff-tree", "--no-commit-id", "--name-only", "-r", prepared], check=False, trust_local_config=True).stdout.splitlines())
    expected_paths = tuple(sorted((*U07_FIXTURE_PATHS, U07_OVERLAY_PATH)))
    if changed != expected_paths:
        return False
    test = _blob(repository, base, U07_TEST_PATH)
    service = _blob(repository, base, U07_SERVICE_PATH)
    overlay = _blob(repository, prepared, U07_OVERLAY_PATH)
    source = _blob(repository, base, U07_OVERLAY_SOURCE)
    if test is None or service is None or overlay is None or overlay != source or not _service_has_prepared_defect(service):
        return False
    try:
        return _blob(repository, prepared, U07_TEST_PATH) == _prepared_test(test)
    except U07FixtureError:
        return False


def u07_remediation_source_is_exact(raw: bytes) -> bool:
    """Bind the learner implementation to executable control-character validation."""
    try:
        text = raw.decode("utf-8")
        tree = ast.parse(textwrap.dedent(text))
    except (UnicodeDecodeError, SyntaxError):
        return False
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or node.name != "complete_ticket":
            continue
        for candidate in ast.walk(node):
            if not isinstance(candidate, ast.If):
                continue
            rendered = ast.unparse(candidate.test)
            if "ord(character) < 32" in rendered and "ord(character) == 127" in rendered:
                return any(
                    isinstance(descendant, ast.Raise)
                    and isinstance(descendant.exc, ast.Call)
                    and any(
                        isinstance(arg, ast.Constant)
                        and arg.value == "resolution must not contain control characters"
                        for arg in descendant.exc.args
                    )
                    for descendant in ast.walk(candidate)
                )
    return False


def u07_remediation_test_is_exact(raw: bytes) -> bool:
    """Require a live unittest method that exercises the three control characters."""
    try:
        text = raw.decode("utf-8")
        tree = ast.parse(textwrap.dedent(text))
    except (UnicodeDecodeError, SyntaxError):
        return False
    methods = [
        method
        for test_case in tree.body
        if isinstance(test_case, ast.ClassDef)
        and any(
            isinstance(base, ast.Attribute)
            and isinstance(base.value, ast.Name)
            and base.value.id == "unittest"
            and base.attr == "TestCase"
            for base in test_case.bases
        )
        for method in test_case.body
        if isinstance(method, ast.FunctionDef)
        and method.name == "test_u07_rejects_control_characters_in_resolution"
    ]
    if len(methods) != 1 or methods[0].decorator_list:
        return False
    method = methods[0]
    constants = {node.value for node in ast.walk(method) if isinstance(node, ast.Constant) and isinstance(node.value, str)}
    calls = [node for node in ast.walk(method) if isinstance(node, ast.Call)]
    return bool(
        {"done\nagain", "done\tagain", "done\x7fagain"}.issubset(constants)
        and "control characters" in constants
        and any(isinstance(call.func, ast.Name) and call.func.id == "complete_ticket" for call in calls)
        and any(isinstance(call.func, ast.Attribute) and call.func.attr == "assertRaisesRegex" for call in calls)
    )
