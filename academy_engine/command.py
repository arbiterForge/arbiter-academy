"""A narrow, argument-safe subprocess boundary for local Git commands."""

from __future__ import annotations

import subprocess
import os
import signal
import stat
import sys
import threading
import re
import ctypes
from pathlib import Path
from typing import Sequence

_MAX_STREAM_BYTES = 1024 * 1024
_COMMAND_TIMEOUT_SECONDS = 10.0
_UNBOUND_EXPLICIT_GIT_COMMANDS = frozenset(
    {
        "cat-file",
        "config",
        "fetch",
        "for-each-ref",
        "merge-base",
        "rev-list",
        "rev-parse",
        "show-ref",
    }
)
_WINDOWS_GATE = (
    "import subprocess,sys; "
    "ready=sys.stdin.buffer.read(1); "
    "sys.stdin.close(); "
    "raise SystemExit(125 if ready != b'1' else "
    "subprocess.call(sys.argv[1:], stdin=subprocess.DEVNULL))"
)


class GitCommandError(RuntimeError):
    """A local Git invocation could not be completed."""


_SAFE_LOCAL_CONFIG = tuple(
    re.compile(pattern)
    for pattern in (
        r"core\.(?:repositoryformatversion|filemode|bare|logallrefupdates|symlinks|ignorecase|precomposeunicode|autocrlf|eol|safecrlf|quotepath|protectntfs|protecthfs)",
        r"remote\.[^.]+\.(?:url|pushurl|fetch|tagopt|mirror|prune|prunetags)",
        r"remote\.pushdefault",
        r"branch\..+\.(?:remote|merge|pushremote|rebase|vscode-merge-base)",
        r"user\.(?:name|email)",
        r"init\.defaultbranch",
        r"extensions\.objectformat",
        r"status\.showuntrackedfiles",
        r"push\.default",
    )
)


class _WindowsJob:
    def __init__(self, handle: int) -> None:
        self.handle = handle
        self.lock = threading.Lock()

    def terminate(self) -> None:
        with self.lock:
            if not self.handle:
                return
            ctypes.windll.kernel32.TerminateJobObject(self.handle, 1)
            ctypes.windll.kernel32.CloseHandle(self.handle)
            self.handle = 0

    def close(self) -> None:
        with self.lock:
            if self.handle:
                ctypes.windll.kernel32.CloseHandle(self.handle)
                self.handle = 0


def _assign_windows_job(process: subprocess.Popen[bytes]) -> _WindowsJob | None:
    if os.name != "nt":
        return None
    from ctypes import wintypes

    class BasicLimitInformation(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_longlong),
            ("PerJobUserTimeLimit", ctypes.c_longlong),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class IoCounters(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_ulonglong),
            ("WriteOperationCount", ctypes.c_ulonglong),
            ("OtherOperationCount", ctypes.c_ulonglong),
            ("ReadTransferCount", ctypes.c_ulonglong),
            ("WriteTransferCount", ctypes.c_ulonglong),
            ("OtherTransferCount", ctypes.c_ulonglong),
        ]

    class ExtendedLimitInformation(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", BasicLimitInformation),
            ("IoInfo", IoCounters),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    kernel32 = ctypes.windll.kernel32
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    handle = kernel32.CreateJobObjectW(None, None)
    if not handle:
        return None
    information = ExtendedLimitInformation()
    information.BasicLimitInformation.LimitFlags = 0x00002000
    configured = kernel32.SetInformationJobObject(
        handle,
        9,
        ctypes.byref(information),
        ctypes.sizeof(information),
    )
    assigned = configured and kernel32.AssignProcessToJobObject(
        handle, wintypes.HANDLE(process._handle)  # type: ignore[attr-defined]
    )
    if not assigned:
        kernel32.CloseHandle(handle)
        return None
    return _WindowsJob(handle)


def _terminate_process_tree(
    process: subprocess.Popen[bytes], job: _WindowsJob | None = None
) -> None:
    if os.name == "nt":
        if job is not None:
            job.terminate()
        elif process.poll() is None:
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    if process.poll() is None:
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def _read_bounded(
    pipe: object,
    label: str,
    sink: bytearray,
    process: subprocess.Popen[bytes],
    job: _WindowsJob | None,
    overflow: list[str],
    lock: threading.Lock,
) -> None:
    stream = pipe
    try:
        while True:
            remaining = _MAX_STREAM_BYTES - len(sink)
            chunk = stream.read(min(8192, remaining + 1))  # type: ignore[attr-defined]
            if not chunk:
                return
            if len(chunk) > remaining:
                sink.extend(chunk[:remaining])
                with lock:
                    if not overflow:
                        overflow.append(label)
                _terminate_process_tree(process, job)
                return
            sink.extend(chunk)
    finally:
        stream.close()  # type: ignore[attr-defined]


def _run(
    command: Sequence[str],
    *,
    cwd: Path,
    check: bool,
    trust_local_config: bool = False,
) -> subprocess.CompletedProcess[str]:
    # Preserve only runtime variables Git needs; credentials, tokens, and arbitrary
    # caller variables are deliberately omitted.
    environment = {key: os.environ[key] for key in ("SystemRoot", "WINDIR", "PATH", "PATHEXT", "COMSPEC", "HOME", "USERPROFILE", "TMP", "TEMP") if key in os.environ}
    environment["GIT_TERMINAL_PROMPT"] = "0"
    environment["GIT_CONFIG_NOSYSTEM"] = "1"
    environment["GIT_CONFIG_GLOBAL"] = os.devnull
    environment["GIT_OPTIONAL_LOCKS"] = "0"
    environment["GIT_NO_LAZY_FETCH"] = "1"
    environment["GIT_PAGER"] = "cat"
    environment["PAGER"] = "cat"
    invocation = list(command)
    if invocation and Path(invocation[0]).name.casefold() in {"git", "git.exe"}:
        invocation = [
            invocation[0],
            "--no-optional-locks",
            "--no-replace-objects",
            "-c",
            f"core.autocrlf={'true' if os.name == 'nt' else 'false'}",
            *(
                []
                if trust_local_config
                else [
                    "-c",
                    "core.fsmonitor=false",
                    "-c",
                    f"core.hooksPath={os.devnull}",
                    "-c",
                    "credential.helper=",
                    "-c",
                    "commit.gpgSign=false",
                    "-c",
                    "tag.gpgSign=false",
                    "-c",
                    "protocol.ext.allow=never",
                ]
            ),
            *invocation[1:],
        ]
    launched = (
        [sys.executable, "-c", _WINDOWS_GATE, *invocation]
        if os.name == "nt"
        else invocation
    )
    try:
        creationflags = (
            subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
        )
        process = subprocess.Popen(
            launched,
            cwd=cwd,
            shell=False,
            env=environment,
            stdin=subprocess.PIPE if os.name == "nt" else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=creationflags,
            start_new_session=os.name != "nt",
        )
    except FileNotFoundError as error:
        raise GitCommandError("Git executable was not found on PATH.") from error
    job = _assign_windows_job(process)
    if os.name == "nt":
        if job is None:
            process.kill()
            process.wait()
            raise GitCommandError(
                "Git command could not enter its bounded Windows process job."
            )
        assert process.stdin is not None
        process.stdin.write(b"1")
        process.stdin.close()
    assert process.stdout is not None and process.stderr is not None
    stdout = bytearray()
    stderr = bytearray()
    overflow: list[str] = []
    lock = threading.Lock()
    readers = [
        threading.Thread(
            target=_read_bounded,
            args=(process.stdout, "stdout", stdout, process, job, overflow, lock),
            daemon=True,
        ),
        threading.Thread(
            target=_read_bounded,
            args=(process.stderr, "stderr", stderr, process, job, overflow, lock),
            daemon=True,
        ),
    ]
    for reader in readers:
        reader.start()
    try:
        returncode = process.wait(timeout=_COMMAND_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired as error:
        _terminate_process_tree(process, job)
        for reader in readers:
            reader.join(timeout=2)
        raise GitCommandError("Git command exceeded its bounded timeout.") from error
    _terminate_process_tree(process, job)
    for reader in readers:
        reader.join(timeout=2)
    if any(reader.is_alive() for reader in readers):
        _terminate_process_tree(process, job)
        raise GitCommandError("Git output capture could not be cleaned up.")
    if overflow:
        raise GitCommandError(
            f"Git {overflow[0]} exceeded the {_MAX_STREAM_BYTES}-byte output limit."
        )
    result = subprocess.CompletedProcess(
        list(command),
        returncode,
        bytes(stdout).decode("utf-8", "surrogateescape"),
        bytes(stderr).decode("utf-8", "surrogateescape"),
    )
    if check and result.returncode:
        detail = result.stderr.strip() or result.stdout.strip() or "Git command failed."
        raise GitCommandError(detail)
    return result


def _repository_layout(root: Path) -> tuple[Path, Path]:
    """Discover a worktree and Git directory without consuming repository config."""
    candidate = Path(root).expanduser().resolve()
    if not candidate.is_dir():
        raise GitCommandError("target repository path is not a directory.")
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    for repository in (candidate, *candidate.parents):
        marker = repository / ".git"
        try:
            metadata = marker.lstat()
        except FileNotFoundError:
            continue
        except OSError as error:
            raise GitCommandError("target Git metadata could not be inspected.") from error
        if stat.S_ISLNK(metadata.st_mode) or (
            reparse_flag
            and getattr(metadata, "st_file_attributes", 0) & reparse_flag
        ):
            raise GitCommandError("target Git metadata cannot be a link or reparse point.")
        if stat.S_ISDIR(metadata.st_mode):
            return repository.resolve(), marker.resolve()
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > 4096:
            raise GitCommandError("target .git marker is malformed.")
        try:
            marker_text = marker.read_text(encoding="utf-8").strip()
        except (OSError, UnicodeError) as error:
            raise GitCommandError("target .git marker could not be read.") from error
        match = re.fullmatch(r"gitdir:\s*(?P<path>[^\r\n\x00]+)", marker_text)
        if match is None:
            raise GitCommandError("target .git marker is malformed.")
        configured = Path(match.group("path"))
        git_directory = (
            configured if configured.is_absolute() else repository / configured
        ).resolve()
        try:
            git_metadata = git_directory.lstat()
        except OSError as error:
            raise GitCommandError("target Git directory could not be inspected.") from error
        if (
            not stat.S_ISDIR(git_metadata.st_mode)
            or stat.S_ISLNK(git_metadata.st_mode)
            or (
                reparse_flag
                and getattr(git_metadata, "st_file_attributes", 0) & reparse_flag
            )
        ):
            raise GitCommandError("target Git directory is not a plain directory.")
        return repository.resolve(), git_directory
    raise GitCommandError("target path is not inside a Git working tree.")


def repository_root(root: Path) -> Path:
    """Resolve *root* to its worktree root without trusting repository config."""
    repository, _ = _repository_layout(root)
    return repository


def validate_repository_git_config(root: Path) -> None:
    """Reject local Git configuration outside the authoritative read allowlist."""
    repository, git_directory = _repository_layout(root)
    result = _run(
        [
            "git",
            f"--git-dir={git_directory}",
            f"--work-tree={repository}",
            "config",
            "--local",
            "--no-includes",
            "--name-only",
            "--get-regexp",
            ".*",
        ],
        cwd=repository,
        check=False,
    )
    if result.returncode not in {0, 1}:
        raise GitCommandError("local Git configuration could not be validated.")
    keys = tuple(line.casefold() for line in result.stdout.splitlines() if line)
    if any(
        not any(pattern.fullmatch(key) for pattern in _SAFE_LOCAL_CONFIG)
        for key in keys
    ):
        raise GitCommandError(
            "unsafe local Git configuration blocks authoritative verification."
        )


def git_version(directory: Path | None = None) -> str:
    """Return the locally installed Git version without requiring a repository."""
    cwd = Path.cwd() if directory is None else Path(directory).expanduser().resolve()
    return _run(["git", "--version"], cwd=cwd, check=True).stdout.strip()


def run_git(
    root: Path,
    args: Sequence[str],
    *,
    check: bool = True,
    trust_local_config: bool = False,
    validate_local_config: bool | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run Git argument-by-argument from the resolved working-tree root."""
    if isinstance(args, str) or not all(isinstance(argument, str) for argument in args):
        raise TypeError("Git arguments must be a sequence of strings.")
    repository, git_directory = _repository_layout(root)
    actual_args = list(args)
    should_validate_local_config = (
        not trust_local_config
        if validate_local_config is None
        else validate_local_config
    )
    if actual_args and actual_args[0] == "config":
        actual_args.insert(1, "--no-includes")
    elif should_validate_local_config:
        validate_repository_git_config(repository)
    return _run(
        [
            "git",
            f"--git-dir={git_directory}",
            f"--work-tree={repository}",
            *actual_args,
        ],
        cwd=repository,
        check=check,
        trust_local_config=trust_local_config,
    )


def run_git_unbound(
    cwd: Path,
    args: Sequence[str],
    *,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run a default-isolated Git command without binding learner Git metadata."""
    if isinstance(args, str) or not all(isinstance(argument, str) for argument in args):
        raise TypeError("Git arguments must be a sequence of strings.")
    directory = Path(cwd).expanduser().resolve()
    if not directory.is_dir():
        raise GitCommandError("Git command directory is not a directory.")
    actual_args = list(args)
    if any(
        argument == "-c"
        or (argument.startswith("-c") and len(argument) > 2)
        or argument == "--config-env"
        or argument.startswith("--config-env=")
        for argument in actual_args
    ):
        raise GitCommandError("unbound Git does not allow caller configuration.")
    if "--git-dir" in actual_args:
        raise GitCommandError(
            "unbound Git directory must use one --git-dir=<absolute> argument."
        )
    explicit_git_directories = [
        argument.removeprefix("--git-dir=")
        for argument in actual_args
        if argument.startswith("--git-dir=")
    ]
    explicit_git_directory = bool(explicit_git_directories)
    if explicit_git_directory:
        command_index = 0
        while command_index < len(actual_args) and (
            actual_args[command_index].startswith("--git-dir=")
            or actual_args[command_index] == "--no-replace-objects"
        ):
            command_index += 1
        if (
            command_index == len(actual_args)
            or actual_args[command_index] not in _UNBOUND_EXPLICIT_GIT_COMMANDS
        ):
            raise GitCommandError("unbound Git command is not authorized.")
        if len(explicit_git_directories) != 1:
            raise GitCommandError("unbound Git requires one absolute Git directory.")
        selected = Path(explicit_git_directories[0])
        if not selected.is_absolute():
            raise GitCommandError("unbound Git requires an absolute Git directory.")
        try:
            metadata = selected.lstat()
        except OSError as error:
            raise GitCommandError(
                "unbound Git directory could not be inspected."
            ) from error
        reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
        if (
            not stat.S_ISDIR(metadata.st_mode)
            or stat.S_ISLNK(metadata.st_mode)
            or (
                reparse_flag
                and getattr(metadata, "st_file_attributes", 0) & reparse_flag
            )
        ):
            raise GitCommandError("unbound Git directory is not a plain directory.")
    sidecar_init = False
    init_indices = [
        index for index, argument in enumerate(actual_args) if argument == "init"
    ]
    if init_indices:
        if init_indices != [0]:
            raise GitCommandError(
                "unbound Git init requires one absolute empty bare sidecar destination."
            )
        bare_count = actual_args[1:].count("--bare")
        templates = [
            argument
            for argument in actual_args[1:]
            if argument.startswith("--template=")
        ]
        object_formats = [
            argument
            for argument in actual_args[1:]
            if argument.startswith("--object-format=")
        ]
        positional = [
            argument for argument in actual_args[1:] if not argument.startswith("-")
        ]
        allowed_options = all(
            argument == "--bare"
            or argument.startswith("--template=")
            or argument in {"--object-format=sha1", "--object-format=sha256"}
            or not argument.startswith("-")
            for argument in actual_args[1:]
        )
        if (
            bare_count != 1
            or len(templates) != 1
            or len(object_formats) > 1
            or len(positional) != 1
            or not allowed_options
        ):
            raise GitCommandError(
                "unbound Git init requires one absolute empty bare sidecar destination."
            )
        target = Path(positional[0])
        if not target.is_absolute() or target.parent.resolve() != directory:
            raise GitCommandError(
                "unbound Git init requires one absolute empty bare sidecar destination."
            )
        if os.path.lexists(target):
            try:
                details = target.lstat()
                occupied = any(target.iterdir())
            except OSError as error:
                raise GitCommandError(
                    "unbound Git init destination could not be inspected."
                ) from error
            reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
            if (
                not stat.S_ISDIR(details.st_mode)
                or stat.S_ISLNK(details.st_mode)
                or bool(
                    reparse_flag
                    and getattr(details, "st_file_attributes", 0) & reparse_flag
                )
                or occupied
            ):
                raise GitCommandError(
                    "unbound Git init destination is not an empty plain directory."
                )
        sidecar_init = True
    repository_independent = bool(actual_args) and (
        actual_args[0] == "--version"
        or sidecar_init
        or (actual_args[0] == "apply" and "--no-index" in actual_args[1:])
    )
    if not explicit_git_directory and not repository_independent:
        isolated = directory / ".arbiter-academy-unbound-no-repository"
        if os.path.lexists(isolated):
            raise GitCommandError("unbound Git isolation marker is occupied.")
        actual_args.insert(0, f"--git-dir={isolated}")
    return _run(["git", *actual_args], cwd=directory, check=check)
