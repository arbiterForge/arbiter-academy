"""Inspect committed native artifacts through the reviewed installed producer.

The learner checkout supplies inert HTML bytes, never executable code or a helper
location. The invoking host supplies its installed plugin root explicitly. All
native reads run against a disposable copy, not the learner's journal or files.
"""
from __future__ import annotations

import hashlib
import json
import platform
import re
import subprocess
import sys
import tempfile
from pathlib import Path


# Released cohort at codeArbiter 849a3cf6; update with the lesson source review.
BRIDGE_SHA256 = "5761e096518fc760ba1aa8fc73dd3a84de7148e9aa88c01ecf66bf129a0eabeb"
GIT_HELPER_SHA256 = "6dc323512f8a50b2a82a8ff63cd5eb2d1e98aefb9dafcc802b8053a2bc838d68"
RELEASE_SHA256 = "138bc85f914e10442eae34070ea19ff0c36534570d93c8fb297939fe5a6d4609"
MAX_DOCUMENT = 2 << 20


class NativePlanningError(ValueError):
    """Native planning inspection could not establish the lesson contract."""


_WORKER = '''
import json, sys, types
from pathlib import Path
bridge = types.ModuleType("academy_reviewed_artifact_bridge")
sources = json.load(sys.stdin)
git_helper = types.ModuleType("_gitexec")
exec(compile(sources["git"], "<reviewed-git-helper>", "exec"), git_helper.__dict__)
sys.modules["_gitexec"] = git_helper
exec(compile(sources["bridge"], "<reviewed-artifact-bridge>", "exec"), bridge.__dict__)
client = bridge.ArtifactClient(Path(sys.argv[2]), Path(sys.argv[1]) / "helpers/artifacts", timeout=15)
index = client.call("index", {})
if index.get("next_offset") is not None or index.get("total") != 2:
    raise ValueError("expected exactly one spec and one plan")
result = {}
for item in index["entries"]:
    kind = item["kind"]
    expected_path = ".codearbiter/" + kind + "s/" + sys.argv[3] + ".html"
    if kind not in ("spec", "plan") or kind in result or item["path"] != expected_path:
        raise ValueError("unexpected native artifact identity")
    aid = item["artifact_id"]
    checked = client.call("validate", {"artifact_id": aid, "gate": "ready"}, permit_invalid=True)
    if checked.get("valid") is not True or checked.get("model_sha256") != item["model_sha256"]:
        raise ValueError("native artifact is not ready")
    outline = client.call("outline", {"artifact_id": aid})
    if outline.get("next_offset") is not None or outline.get("total", 129) > 128:
        raise ValueError("lesson artifact exceeds bounded inspection")
    records = []
    for symbol in outline["records"]:
        if symbol.get("retired") or symbol["kind"] not in ("intent", "scope", "criteria", "tasks"):
            continue
        read = client.call("read", {"artifact_id": aid, "symbol": symbol["id"], "mode": "exact"})
        if read.get("model_sha256") != item["model_sha256"]:
            raise ValueError("native artifact changed during inspection")
        records.append({"kind": symbol["kind"], "record": read["record"]})
    result[kind] = {"artifact_id": aid, "model_sha256": item["model_sha256"], "records": records}
encoded = json.dumps(result, ensure_ascii=True)
if len(encoded) > 1048576:
    raise ValueError("native lesson inspection exceeded response budget")
print(encoded)
'''


def inspect_pair(repository: Path, plugin_root: Path | None, slug: str,
                 spec: bytes | None, plan: bytes | None) -> dict:
    """Return bounded native records; readiness is not approval or test proof."""
    if plugin_root is None:
        raise NativePlanningError("native lessons require --plugin-root from the host's loaded installation")
    if not re.fullmatch(r"academy-(?:feature|sprint)", slug):
        raise NativePlanningError("unsupported lesson artifact slug")
    plugin = Path(plugin_root)
    if not plugin.is_absolute():
        raise NativePlanningError("plugin root must be an absolute installed path")
    try:
        plugin = plugin.resolve(strict=True)
    except OSError as error:
        raise NativePlanningError("installed plugin root is unavailable") from error
    if plugin.is_relative_to(repository.resolve()):
        raise NativePlanningError("plugin root must be outside the learner checkout")
    if any(not isinstance(raw, bytes) or not raw or len(raw) > MAX_DOCUMENT for raw in (spec, plan)):
        raise NativePlanningError("native lesson artifacts are missing or oversized")
    try:
        bridge_path = plugin / "hooks/_artifactlib.py"
        git_path = plugin / "hooks/_gitexec.py"
        manifest_path = plugin / "helpers/artifacts/release.json"
        if bridge_path.stat().st_size > 262144 or git_path.stat().st_size > 65536 or manifest_path.stat().st_size > 65536:
            raise NativePlanningError("installed producer metadata exceeds its bound")
        bridge = bridge_path.read_bytes().replace(b"\r\n", b"\n")
        git_helper = git_path.read_bytes().replace(b"\r\n", b"\n")
        manifest = json.loads(manifest_path.read_bytes())
        manifest_digest = hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        if (hashlib.sha256(bridge).hexdigest() != BRIDGE_SHA256
                or hashlib.sha256(git_helper).hexdigest() != GIT_HELPER_SHA256
                or manifest_digest != RELEASE_SHA256):
            raise NativePlanningError("installed producer differs from this Academy cohort; update the reviewed course or installation")
        with tempfile.TemporaryDirectory(prefix="academy-native-check-") as directory:
            scratch = Path(directory).resolve()
            # The worker must never reopen the mutable installation after pinning.
            producer = scratch / "producer"
            helpers = producer / "helpers/artifacts"
            helpers.mkdir(parents=True)
            system = platform.system().lower()
            machine = platform.machine().lower()
            architecture = {"x86_64": "amd64", "amd64": "amd64", "arm64": "arm64", "aarch64": "arm64"}.get(machine)
            entry = manifest["binaries"].get(f"{system}/{architecture}")
            if not entry or Path(entry["file"]).name != entry["file"]:
                raise NativePlanningError("this host has no reviewed native producer")
            executable = plugin / "helpers/artifacts" / entry["file"]
            with executable.open("rb") as handle:
                binary = handle.read((32 << 20) + 1)
            if len(binary) > (32 << 20) or hashlib.sha256(binary).hexdigest() != entry["sha256"]:
                raise NativePlanningError("installed native producer fails its reviewed digest")
            (helpers / "release.json").write_text(json.dumps(manifest), encoding="utf-8")
            target_binary = helpers / entry["file"]
            target_binary.write_bytes(binary)
            target_binary.chmod(0o700)
            for kind, raw in (("spec", spec), ("plan", plan)):
                target = scratch / f".codearbiter/{kind}s/{slug}.html"
                target.parent.mkdir(parents=True)
                target.write_bytes(raw)
            response = subprocess.run(
                [sys.executable, "-I", "-B", "-c", _WORKER, str(producer), str(scratch), slug],
                input=json.dumps({"bridge": bridge.decode("utf-8"), "git": git_helper.decode("utf-8")}).encode(),
                capture_output=True, timeout=60, cwd=scratch, check=False,
            )
            if response.returncode or len(response.stdout) > (1 << 20):
                raise NativePlanningError("native inspection failed; use the installed engine to inspect readiness and package diagnostics")
            result = json.loads(response.stdout)
            if not isinstance(result, dict) or set(result) != {"spec", "plan"}:
                raise NativePlanningError("native inspection returned an invalid pair")
            return result
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        if isinstance(error, NativePlanningError):
            raise
        raise NativePlanningError("native inspection could not complete") from error
