#!/usr/bin/env python3
"""Scan the exact staged Git blobs for high-confidence credential material."""

from __future__ import annotations

import os
import re
import signal
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path

def _standalone_secret_rule_functions():
    """Build rules without importing any module from the scanned checkout."""
    _STANDALONE_FIXED_SECRET_RULES = (
        (
            "PEM_PRIVATE_KEY",
            re.compile(
                rb"(?<![A-Za-z0-9_])-----BEGIN[ \t]+"
                rb"(?:RSA[ \t]+|EC[ \t]+|OPENSSH[ \t]+|DSA[ \t]+|ENCRYPTED[ \t]+)?"
                rb"PRIVATE[ \t]+KEY-----(?![A-Za-z0-9_])"
            ),
        ),
        (
            "GITHUB_TOKEN",
            re.compile(
                rb"(?<![A-Za-z0-9_])gh[pousr]_[A-Za-z0-9]{20,255}(?![A-Za-z0-9_])"
            ),
        ),
        (
            "GITHUB_TOKEN",
            re.compile(
                rb"(?<![A-Za-z0-9_])github_pat_[A-Za-z0-9_]{20,255}"
                rb"(?![A-Za-z0-9_])"
            ),
        ),
        (
            "AWS_ACCESS_KEY_ID",
            re.compile(
                rb"(?<![A-Za-z0-9_])(?:AKIA|ASIA)[A-Z0-9]{16}(?![A-Za-z0-9_])"
            ),
        ),
        (
            "OPENAI_API_KEY",
            re.compile(
                rb"(?<![A-Za-z0-9_-])sk-(?!proj-)[A-Za-z0-9_-]{20,255}"
                rb"(?![A-Za-z0-9_-])"
            ),
        ),
        (
            "OPENAI_API_KEY",
            re.compile(
                rb"(?<![A-Za-z0-9_-])sk-proj-[A-Za-z0-9_-]{20,255}"
                rb"(?![A-Za-z0-9_-])"
            ),
        ),
        (
            "SLACK_TOKEN",
            re.compile(
                rb"(?<![A-Za-z0-9_-])xox[A-Za-z]-[A-Za-z0-9-]{20,255}"
                rb"(?![A-Za-z0-9_-])"
            ),
        ),
        (
            "CREDENTIAL_URL",
            re.compile(
                rb"(?<![A-Za-z0-9_])https?://[A-Za-z0-9._~-]+:"
                rb"[A-Za-z0-9._~+/-]{12,255}@[A-Za-z0-9.-]+"
                rb"(?::[0-9]{1,5})?(?:/[A-Za-z0-9._~!$&'()*+,;=:@%/?#-]*)?"
                rb"(?![A-Za-z0-9._~+/-])",
                re.IGNORECASE,
            ),
        ),
        (
            "BEARER_AUTHORIZATION",
            re.compile(
                rb"(?<![A-Za-z0-9_-])Authorization[ \t]*:[ \t]*Bearer[ \t]+"
                rb"[A-Za-z0-9._~+/-]{20,255}={0,2}(?![A-Za-z0-9._~+/-=])",
                re.IGNORECASE,
            ),
        ),
    )
    _STANDALONE_ASSIGNMENT = re.compile(
        rb"^[ \t]*(?:api_key|access_token|secret|password|passwd)[ \t]*[:=][ \t]*"
        rb"(?:\"(?P<double>[^\"\r\n]{16,255})\"|'(?P<single>[^'\r\n]{16,255})'|"
        rb"(?P<bare>[^\s#;,\"']{16,255}))"
        rb"[ \t]*(?:[#;][^\r\n]*)?\r?$",
        re.IGNORECASE | re.MULTILINE,
    )
    _STANDALONE_MALFORMED_ASSIGNMENT = re.compile(
        rb"^[ \t]*(?:api_key|access_token|secret|password|passwd)[ \t]*[:=][ \t]*"
        rb"(?:\"(?P<double_malformed>[^\"'\r\n]{16,255}?)(?:')?|"
        rb"'(?P<single_malformed>[^\"'\r\n]{16,255}?)(?:\")?)"
        rb"[ \t]*(?:[#;][^\r\n]*)?\r?$",
        re.IGNORECASE | re.MULTILINE,
    )
    _STANDALONE_PLACEHOLDER_VALUES = frozenset(
        (b"placeholder-value", b"example-credential", b"not-a-real-secret")
    )
    _STANDALONE_ENVIRONMENT_REFERENCE = re.compile(rb"\$\{[A-Z][A-Z0-9_]{0,63}\}")

    def _standalone_is_placeholder(value: bytes) -> bool:
        return (
            value in _STANDALONE_PLACEHOLDER_VALUES
            or _STANDALONE_ENVIRONMENT_REFERENCE.fullmatch(value) is not None
        )

    def iter_secret_matches(data: bytes):
        """Yield canonical secret findings when the scanner is copied alone."""
        seen: set[tuple[str, int]] = set()
        for rule, pattern in _STANDALONE_FIXED_SECRET_RULES:
            for match in pattern.finditer(data):
                item = (rule, match.start())
                if item not in seen:
                    seen.add(item)
                    yield item
        for match in _STANDALONE_ASSIGNMENT.finditer(data):
            group = next(
                name
                for name in ("double", "single", "bare")
                if match.group(name) is not None
            )
            value = match.group(group)
            if not _standalone_is_placeholder(value):
                item = ("CREDENTIAL_ASSIGNMENT", match.start(group))
                if item not in seen:
                    seen.add(item)
                    yield item
        for match in _STANDALONE_MALFORMED_ASSIGNMENT.finditer(data):
            group = next(
                name
                for name in ("double_malformed", "single_malformed")
                if match.group(name) is not None
            )
            value = match.group(group)
            if not _standalone_is_placeholder(value):
                item = ("CREDENTIAL_ASSIGNMENT", match.start(group))
                if item not in seen:
                    seen.add(item)
                    yield item

    def iter_secret_content_views(content: bytes):
        """Yield raw and BOM-declared UTF-16 views for a standalone scanner."""
        yield content
        if content.startswith(b"\xff\xfe"):
            encoding = "utf-16-le"
        elif content.startswith(b"\xfe\xff"):
            encoding = "utf-16-be"
        else:
            return
        decoded = content[2:].decode(encoding, errors="strict")
        yield decoded.encode("utf-8")

    return iter_secret_content_views, iter_secret_matches


iter_secret_content_views, iter_secret_matches = _standalone_secret_rule_functions()


MAX_STAGED_PATHS = 1024
MAX_PATH_BYTES = 4096
MAX_MANIFEST_BYTES = 2 * 1024 * 1024
MAX_BLOB_BYTES = 8 * 1024 * 1024
MAX_AGGREGATE_BYTES = 32 * 1024 * 1024
MAX_GIT_STDERR_BYTES = 64 * 1024
GIT_TIMEOUT_SECONDS = 15
MAX_FINDINGS = 20
MAX_METADATA_BYTES = 4096


@dataclass(frozen=True)
class Finding:
    rule: str
    path: bytes
    location: int | str


@dataclass(frozen=True)
class IndexRecord:
    path: bytes
    mode: bytes
    object_id: str
    stage: int


@dataclass(frozen=True)
class RepositoryIdentity:
    root: Path
    git_dir: Path


class InspectionError(RuntimeError):
    def __init__(self, operation: str, detail: str) -> None:
        super().__init__(detail)
        self.operation = operation
        self.detail = detail


_INDEX_RECORD = re.compile(
    rb"(?P<mode>[0-7]{6}) (?P<object>(?:[0-9a-f]{40}|[0-9a-f]{64})) "
    rb"(?P<stage>[0-3])\t(?P<path>.*)",
    re.DOTALL,
)


def _git_environment() -> dict[str, str]:
    allowed = (
        "PATH",
        "PATHEXT",
        "SYSTEMROOT",
        "WINDIR",
        "COMSPEC",
        "TEMP",
        "TMP",
        "LANG",
        "LC_ALL",
    )
    environment = {key: os.environ[key] for key in allowed if key in os.environ}
    environment.update(
        {
            "GIT_NO_REPLACE_OBJECTS": "1",
            "GIT_NO_LAZY_FETCH": "1",
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_PAGER": "cat",
            "PAGER": "cat",
        }
    )
    return environment


def _windows_system_taskkill() -> Path:
    import ctypes

    buffer = ctypes.create_unicode_buffer(32768)
    length = ctypes.windll.kernel32.GetSystemDirectoryW(buffer, len(buffer))
    if length <= 0 or length >= len(buffer):
        raise OSError("system directory unavailable")
    executable = (Path(buffer.value) / "taskkill.exe").resolve(strict=True)
    if not executable.is_file():
        raise OSError("taskkill unavailable")
    return executable


def _windows_process_job(process: subprocess.Popen[bytes]) -> int | None:
    import ctypes
    from ctypes import wintypes

    class BasicLimitInformation(ctypes.Structure):
        _fields_ = (
            ("PerProcessUserTimeLimit", ctypes.c_longlong),
            ("PerJobUserTimeLimit", ctypes.c_longlong),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        )

    class IoCounters(ctypes.Structure):
        _fields_ = tuple(
            (name, ctypes.c_ulonglong)
            for name in (
                "ReadOperationCount",
                "WriteOperationCount",
                "OtherOperationCount",
                "ReadTransferCount",
                "WriteTransferCount",
                "OtherTransferCount",
            )
        )

    class ExtendedLimitInformation(ctypes.Structure):
        _fields_ = (
            ("BasicLimitInformation", BasicLimitInformation),
            ("IoInfo", IoCounters),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        )

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateJobObjectW.argtypes = (ctypes.c_void_p, wintypes.LPCWSTR)
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.SetInformationJobObject.argtypes = (
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
    )
    kernel32.SetInformationJobObject.restype = wintypes.BOOL
    kernel32.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
    kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel32.CloseHandle.restype = wintypes.BOOL
    handle = kernel32.CreateJobObjectW(None, None)
    if not handle:
        return None
    information = ExtendedLimitInformation()
    information.BasicLimitInformation.LimitFlags = 0x00002000
    if not kernel32.SetInformationJobObject(
        handle, 9, ctypes.byref(information), ctypes.sizeof(information)
    ) or not kernel32.AssignProcessToJobObject(
        handle, wintypes.HANDLE(int(process._handle))
    ):
        kernel32.CloseHandle(handle)
        return None
    return int(handle)


def _windows_terminate_job(handle: int) -> bool:
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.TerminateJobObject.argtypes = (wintypes.HANDLE, wintypes.UINT)
    kernel32.TerminateJobObject.restype = wintypes.BOOL
    return bool(kernel32.TerminateJobObject(wintypes.HANDLE(handle), 1))


def _windows_close_job(handle: int) -> None:
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.CloseHandle(wintypes.HANDLE(handle))


def _terminate_process_tree(
    process: subprocess.Popen[bytes], windows_job: int | None
) -> None:
    if os.name == "nt":
        if windows_job is not None and _windows_terminate_job(windows_job):
            return
        try:
            taskkill = _windows_system_taskkill()
            subprocess.run(
                [str(taskkill), "/PID", str(process.pid), "/T", "/F"],
                env=_git_environment(),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            try:
                process.kill()
            except OSError:
                pass
        return
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (OSError, ProcessLookupError):
        try:
            process.kill()
        except OSError:
            pass


def _bounded_process(
    root: Path,
    command: list[str],
    operation: str,
    *,
    max_stdout: int,
) -> tuple[int, bytes]:
    try:
        process = subprocess.Popen(
            command,
            cwd=root,
            env=_git_environment(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=os.name != "nt",
            creationflags=(
                subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
            ),
        )
    except OSError as error:
        raise InspectionError(operation, type(error).__name__) from error
    windows_job = _windows_process_job(process) if os.name == "nt" else None
    assert process.stdout is not None and process.stderr is not None
    buffers = {"stdout": bytearray(), "stderr": bytearray()}
    overflow: list[str] = []
    termination_lock = threading.Lock()
    termination_started = False
    job_closed = False

    def close_job() -> None:
        nonlocal job_closed
        if os.name == "nt" and windows_job is not None and not job_closed:
            _windows_close_job(windows_job)
            job_closed = True

    def terminate_tree() -> None:
        nonlocal termination_started
        with termination_lock:
            if termination_started:
                return
            termination_started = True
            _terminate_process_tree(process, windows_job)

    def consume(name: str, limit: int) -> None:
        stream = process.stdout if name == "stdout" else process.stderr
        try:
            while True:
                remaining = limit - len(buffers[name])
                chunk = stream.read(min(64 * 1024, remaining + 1))
                if not chunk:
                    return
                buffers[name].extend(chunk)
                if len(buffers[name]) > limit:
                    overflow.append(name)
                    terminate_tree()
                    return
        except OSError:
            overflow.append(name)
            terminate_tree()

    threads = (
        threading.Thread(target=consume, args=("stdout", max_stdout), daemon=True),
        threading.Thread(
            target=consume, args=("stderr", MAX_GIT_STDERR_BYTES), daemon=True
        ),
    )
    for thread in threads:
        thread.start()
    try:
        returncode = process.wait(timeout=GIT_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired as error:
        terminate_tree()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                process.kill()
            except OSError:
                pass
            process.wait(timeout=5)
        for thread in threads:
            thread.join(timeout=2)
        if not any(thread.is_alive() for thread in threads):
            process.stdout.close()
            process.stderr.close()
        close_job()
        raise InspectionError("resource-limits", f"{operation} timeout") from error
    for thread in threads:
        thread.join(timeout=1)
    if any(thread.is_alive() for thread in threads):
        terminate_tree()
        for thread in threads:
            thread.join(timeout=2)
        if not any(thread.is_alive() for thread in threads):
            process.stdout.close()
            process.stderr.close()
        close_job()
        raise InspectionError("resource-limits", f"{operation} stream timeout")
    process.stdout.close()
    process.stderr.close()
    close_job()
    if overflow:
        raise InspectionError("resource-limits", f"{operation} output limit exceeded")
    return returncode, bytes(buffers["stdout"])


def _git(
    repository: RepositoryIdentity,
    arguments: list[str],
    operation: str,
    *,
    max_stdout: int = MAX_METADATA_BYTES,
) -> bytes:
    returncode, stdout = _bounded_process(
        repository.root,
        [
            "git",
            "--no-pager",
            f"--git-dir={repository.git_dir}",
            f"--work-tree={repository.root}",
            "-c",
            "core.fsmonitor=false",
            "-c",
            "protocol.ext.allow=never",
            *arguments,
        ],
        operation,
        max_stdout=max_stdout,
    )
    if returncode:
        raise InspectionError(operation, f"git exit {returncode}")
    return stdout


def _repository_marker(start: Path) -> tuple[Path, Path]:
    try:
        current = start.resolve(strict=True)
    except (OSError, ValueError) as error:
        raise InspectionError("repository-discovery", "invalid working directory") from error
    if not current.is_dir():
        current = current.parent
    for candidate in (current, *current.parents):
        marker = candidate / ".git"
        if marker.is_dir():
            try:
                return candidate.resolve(strict=True), marker.resolve(strict=True)
            except (OSError, ValueError) as error:
                raise InspectionError(
                    "repository-discovery", "invalid repository marker"
                ) from error
        if not marker.is_file():
            continue
        try:
            payload = marker.read_bytes()
        except OSError as error:
            raise InspectionError(
                "repository-discovery", "invalid repository marker"
            ) from error
        if len(payload) > MAX_PATH_BYTES + len(b"gitdir: \r\n"):
            raise InspectionError("repository-discovery", "invalid repository marker")
        lines = payload.splitlines()
        if len(lines) != 1 or not lines[0].startswith(b"gitdir: "):
            raise InspectionError("repository-discovery", "invalid repository marker")
        target = lines[0][len(b"gitdir: ") :]
        if not target or b"\0" in target:
            raise InspectionError("repository-discovery", "invalid repository marker")
        try:
            git_dir = Path(os.fsdecode(target))
            if not git_dir.is_absolute():
                git_dir = candidate / git_dir
            git_dir = git_dir.resolve(strict=True)
            root = candidate.resolve(strict=True)
        except (OSError, ValueError) as error:
            raise InspectionError(
                "repository-discovery", "invalid repository marker"
            ) from error
        if not git_dir.is_dir():
            raise InspectionError("repository-discovery", "invalid repository marker")
        return root, git_dir
    raise InspectionError("repository-discovery", "Git worktree marker not found")


def _repository_root(start: Path | None = None) -> RepositoryIdentity:
    root, git_dir = _repository_marker(Path.cwd() if start is None else start)
    repository = RepositoryIdentity(root, git_dir)
    output = _git(
        repository, ["rev-parse", "--show-toplevel"], "repository-discovery"
    )
    lines = output.splitlines()
    if len(lines) != 1 or not lines[0]:
        raise InspectionError("repository-discovery", "malformed Git output")
    try:
        reported_root = Path(os.fsdecode(lines[0])).resolve(strict=True)
    except (OSError, ValueError) as error:
        raise InspectionError("repository-discovery", "malformed Git output") from error
    if reported_root != root:
        raise InspectionError("repository-discovery", "repository identity mismatch")
    index_output = _git(
        repository, ["rev-parse", "--git-path", "index"], "repository-discovery"
    )
    index_lines = index_output.splitlines()
    if len(index_lines) != 1 or not index_lines[0]:
        raise InspectionError("repository-discovery", "malformed Git output")
    try:
        reported_index = Path(os.fsdecode(index_lines[0]))
        if not reported_index.is_absolute():
            reported_index = root / reported_index
        reported_index = reported_index.absolute()
        expected_index = (git_dir / "index").absolute()
    except (OSError, ValueError) as error:
        raise InspectionError("repository-discovery", "malformed Git output") from error
    if reported_index != expected_index:
        raise InspectionError("repository-discovery", "index identity mismatch")
    return repository


def _nul_records(output: bytes, operation: str) -> list[bytes]:
    if not output:
        return []
    if not output.endswith(b"\0"):
        raise InspectionError(operation, "malformed Git output")
    return output[:-1].split(b"\0")


def _staged_paths(root: RepositoryIdentity) -> tuple[bytes, ...]:
    unmerged = _git(
        root,
        ["ls-files", "--unmerged", "-z"],
        "unmerged-index",
        max_stdout=MAX_MANIFEST_BYTES,
    )
    if unmerged:
        _nul_records(unmerged, "unmerged-index")
        raise InspectionError("unmerged-index", "conflict stages present")
    output = _git(
        root,
        [
            "diff",
            "--no-ext-diff",
            "--no-textconv",
            "--cached",
            "--name-status",
            "-z",
            "--diff-filter=ACMRT",
            "--ignore-submodules=none",
            "--no-renames",
        ],
        "staged-paths",
        max_stdout=MAX_MANIFEST_BYTES,
    )
    records = _nul_records(output, "staged-paths")
    paths: list[bytes] = []
    index = 0
    while index < len(records):
        status = records[index]
        index += 1
        if not status or status[:1] not in {b"A", b"C", b"M", b"R", b"T"}:
            raise InspectionError("staged-paths", "malformed Git output")
        required = 2 if status[:1] in {b"C", b"R"} else 1
        if index + required > len(records):
            raise InspectionError("staged-paths", "malformed Git output")
        selected = records[index + required - 1]
        if not selected or b"\0" in selected:
            raise InspectionError("staged-paths", "malformed Git output")
        if len(selected) > MAX_PATH_BYTES:
            raise InspectionError("resource-limits", "staged path exceeds byte limit")
        paths.append(selected)
        index += required
    if len(paths) > MAX_STAGED_PATHS:
        raise InspectionError("resource-limits", "staged path count exceeds limit")
    if len(paths) != len(set(paths)):
        raise InspectionError("staged-paths", "malformed Git output")
    return tuple(paths)


def _index_manifest(
    root: RepositoryIdentity, changed_paths: tuple[bytes, ...]
) -> tuple[bytes, dict[bytes, str]]:
    output = _git(
        root,
        ["ls-files", "--stage", "-z"],
        "index-records",
        max_stdout=MAX_MANIFEST_BYTES,
    )
    records = _nul_records(output, "index-records")
    entries: dict[bytes, list[IndexRecord]] = {}
    all_records: list[IndexRecord] = []
    for record in records:
        match = _INDEX_RECORD.fullmatch(record)
        if match is None:
            raise InspectionError("index-records", "malformed Git output")
        path = match.group("path")
        if len(path) > MAX_PATH_BYTES:
            raise InspectionError("resource-limits", "index path exceeds byte limit")
        stage = int(match.group("stage"))
        object_id = match.group("object").decode("ascii")
        mode = match.group("mode")
        parsed = IndexRecord(path, mode, object_id, stage)
        entries.setdefault(path, []).append(parsed)
        all_records.append(parsed)
    if any(record.stage != 0 for record in all_records):
        raise InspectionError("unmerged-index", "conflict stages present")
    if any(len(candidates) != 1 for candidates in entries.values()):
        raise InspectionError("index-records", "duplicate index path")
    selected: dict[bytes, str] = {}
    selected_records: list[IndexRecord] = []
    for path in changed_paths:
        candidates = entries.get(path, [])
        if len(candidates) != 1 or candidates[0].stage != 0:
            raise InspectionError("index-records", "changed path has no unique stage-0 record")
        candidate = candidates[0]
        if candidate.mode == b"160000":
            raise InspectionError("inspect-object", "index object is not a blob")
        selected[path] = candidate.object_id
        selected_records.append(candidate)
    canonical = b"".join(
        record.mode
        + b" "
        + record.object_id.encode("ascii")
        + b" "
        + str(record.stage).encode("ascii")
        + b"\t"
        + record.path
        + b"\0"
        for record in sorted(
            all_records,
            key=lambda item: (item.path, item.mode, item.object_id, item.stage),
        )
    )
    if len(canonical) > MAX_MANIFEST_BYTES:
        raise InspectionError("resource-limits", "index manifest exceeds byte limit")
    return canonical, selected


def _object_format(root: RepositoryIdentity) -> int:
    value = _git(root, ["rev-parse", "--show-object-format"], "object-format").strip()
    if value == b"sha1":
        return 40
    if value == b"sha256":
        return 64
    raise InspectionError("object-format", "unsupported object format")


def _blob(
    root: RepositoryIdentity,
    object_id: str,
    object_id_width: int,
    aggregate_remaining: int,
) -> bytes:
    if len(object_id) != object_id_width or not re.fullmatch(r"[0-9a-f]+", object_id):
        raise InspectionError("inspect-object", "malformed object identity")
    object_type = _git(root, ["cat-file", "-t", object_id], "inspect-object").strip()
    if object_type != b"blob":
        raise InspectionError("inspect-object", "index object is not a blob")
    raw_size = _git(root, ["cat-file", "-s", object_id], "inspect-object").strip()
    if not raw_size or not raw_size.isdigit():
        raise InspectionError("inspect-object", "malformed blob size")
    size = int(raw_size)
    if size > MAX_BLOB_BYTES:
        raise InspectionError("resource-limits", "blob exceeds byte limit")
    if size > aggregate_remaining:
        raise InspectionError("resource-limits", "aggregate blob bytes exceed limit")
    content = _git(
        root,
        ["cat-file", "blob", object_id],
        "inspect-object",
        max_stdout=size,
    )
    if len(content) != size:
        raise InspectionError("resource-limits", "blob short read")
    return content


def _line(data: bytes, offset: int) -> int:
    return data.count(b"\n", 0, offset) + 1


def _path_matches(path: bytes):
    seen: set[str] = set()
    for component in path.split(b"/"):
        for rule, _ in iter_secret_matches(component):
            if rule not in seen:
                seen.add(rule)
                yield rule


def _content_views(content: bytes):
    """Yield the raw blob, then a strict UTF-8 view for BOM-declared UTF-16."""
    try:
        yield from iter_secret_content_views(content)
    except UnicodeDecodeError as error:
        raise InspectionError("decode-utf16", "malformed declared text") from error


def _safe_path(path: bytes) -> str:
    if next(_path_matches(path), None) is not None:
        return "<redacted-path>"
    rendered: list[str] = []
    for byte in path:
        if (
            ord("0") <= byte <= ord("9")
            or ord("A") <= byte <= ord("Z")
            or ord("a") <= byte <= ord("z")
            or byte in b"._/-"
        ):
            rendered.append(chr(byte))
        else:
            rendered.append(f"\\x{byte:02x}")
    return "".join(rendered)


def scan_staged(
    root: Path | RepositoryIdentity,
) -> tuple[int, list[Finding], bool]:
    repository = root if isinstance(root, RepositoryIdentity) else _repository_root(root)
    object_id_width = _object_format(repository)
    paths = _staged_paths(repository)
    manifest, objects = _index_manifest(repository, paths)
    findings: list[Finding] = []
    suppressed = False
    aggregate = 0
    for path in paths:
        if not suppressed:
            for rule in _path_matches(path):
                if len(findings) == MAX_FINDINGS:
                    suppressed = True
                    break
                findings.append(Finding(rule, path, "path"))
        content = _blob(
            repository,
            objects[path],
            object_id_width,
            MAX_AGGREGATE_BYTES - aggregate,
        )
        aggregate += len(content)
        if aggregate > MAX_AGGREGATE_BYTES:
            raise InspectionError("resource-limits", "aggregate blob bytes exceed limit")
        blob_findings: set[tuple[str, int]] = set()
        for view in _content_views(content):
            if suppressed:
                continue
            for rule, offset in iter_secret_matches(view):
                location = _line(view, offset)
                item = (rule, location)
                if item in blob_findings:
                    continue
                if len(findings) == MAX_FINDINGS:
                    suppressed = True
                    break
                blob_findings.add(item)
                findings.append(Finding(rule, path, location))
    try:
        final_paths = _staged_paths(repository)
        final_manifest, _ = _index_manifest(repository, final_paths)
    except InspectionError as error:
        raise InspectionError("index-stability", error.detail) from error
    if final_paths != paths or final_manifest != manifest:
        raise InspectionError("index-stability", "index changed during inspection")
    findings.sort(key=lambda item: (item.path, str(item.location), item.rule))
    return len(paths), findings, suppressed


def _error(error: InspectionError) -> int:
    print(f"ERROR: {error.operation} failed ({error.detail}).", file=sys.stderr)
    return 2


def main(arguments: list[str] | None = None) -> int:
    argv = sys.argv[1:] if arguments is None else arguments
    if argv != ["--staged"]:
        return _error(InspectionError("invocation", "expected --staged"))
    try:
        root = _repository_root()
        inspected, findings, suppressed = scan_staged(root)
    except InspectionError as error:
        return _error(error)
    except Exception as error:
        return _error(InspectionError("inspection", type(error).__name__))
    if not findings:
        print(f"PASS: inspected {inspected} staged files; 0 findings.")
        return 0
    for finding in findings:
        print(f"{finding.rule} {_safe_path(finding.path)}:{finding.location}")
    if suppressed:
        print("additional findings suppressed")
    else:
        print(f"FINDINGS: {len(findings)}.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
