"""Installed-verifier-owned, path-private state storage."""

from __future__ import annotations

import hashlib
import json
import math
import ntpath
import os
import re
import secrets
import stat
import sys
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Any, ContextManager

from academy_engine.command import GitCommandError, run_git


_MAX_RECORD_BYTES = 65_536
_IDENTITY_KEYS = frozenset(
    {
        "schema_version",
        "repository_id",
        "locator",
        "locator_source",
        "object_format",
        "academy_base_commit",
        "catalog_sha256",
    }
)
_OWNED_COMPONENT = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}")
_WINDOWS_RESERVED_NAMES = frozenset(
    {"con", "prn", "aux", "nul", "clock$"}
    | {f"com{index}" for index in range(1, 10)}
    | {f"lpt{index}" for index in range(1, 10)}
)
_LOCK_CAPABILITY = object()
_MESSAGES = {
    "invalid-state-root": "External state root is invalid.",
    "state-root-inside-repository": "External state root must be outside the learner repository.",
    "unsafe-state-path": "External state path is unsafe.",
    "repository-identity": "Repository identity could not be established.",
    "state-identity-mismatch": "External state identity does not match.",
    "state-busy": "External state is busy.",
    "state-corrupt": "External state is corrupt.",
    "state-too-large": "External state exceeds its size limit.",
    "attempt-limit": "External state attempt is outside the supported range.",
    "generation-mismatch": "External state generation does not match.",
    "state-missing": "External state is missing.",
}


class ExternalStateError(ValueError):
    """A stable, path-free failure at the installed state boundary."""

    code: str

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(_MESSAGES.get(code, "External state operation failed."))


@dataclass(frozen=True)
class RepositoryLocator:
    digest: str
    object_format: str
    source_kind: str


def _has_control(value: str) -> bool:
    return any(ord(character) < 0x20 or ord(character) == 0x7F for character in value)


def _is_windows_unc(value: str) -> bool:
    normalized = value.replace("/", "\\")
    return normalized.startswith("\\\\")


def resolve_state_root(
    *,
    platform_name: str | None = None,
    environ: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> Path:
    """Resolve the fixed per-user verifier-state root for a platform."""
    platform = sys.platform if platform_name is None else platform_name
    environment = os.environ if environ is None else environ
    user_home = Path.home() if home is None else Path(home)
    if platform == "win32":
        configured = environment.get("LOCALAPPDATA")
        root = (
            Path(configured) / "ArbiterAcademy/VerifierState"
            if configured is not None
            else user_home / "AppData/Local/ArbiterAcademy/VerifierState"
        )
        rendered = str(root)
        if _has_control(rendered) or _is_windows_unc(rendered) or not (
            ntpath.isabs(rendered) or root.is_absolute()
        ):
            raise ExternalStateError("invalid-state-root")
        return root
    if platform == "darwin":
        root = user_home / "Library/Application Support/ArbiterAcademy/VerifierState"
    else:
        configured = environment.get("XDG_STATE_HOME")
        candidate = Path(configured) if configured else None
        root = (
            candidate / "arbiter-academy"
            if candidate is not None
            and candidate.is_absolute()
            and not _has_control(str(candidate))
            else user_home / ".local/state/arbiter-academy"
        )
    if not root.is_absolute() or _has_control(str(root)):
        raise ExternalStateError("invalid-state-root")
    return root


def _is_redirect(details: os.stat_result) -> bool:
    return bool(
        stat.S_ISLNK(details.st_mode)
        or getattr(details, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    )


def _set_private_mode(path: Path, *, directory: bool) -> None:
    if os.name == "nt":
        return
    wanted = 0o700 if directory else 0o600
    try:
        os.chmod(path, wanted, follow_symlinks=False)
        if stat.S_IMODE(path.stat(follow_symlinks=False).st_mode) & 0o077:
            raise ExternalStateError("unsafe-state-path")
    except ExternalStateError:
        raise
    except OSError as error:
        raise ExternalStateError("unsafe-state-path") from error


def _ensure_directory(path: Path) -> None:
    try:
        path.mkdir(mode=0o700)
    except FileExistsError:
        pass
    except OSError as error:
        raise ExternalStateError("unsafe-state-path") from error
    try:
        details = path.lstat()
    except OSError as error:
        raise ExternalStateError("unsafe-state-path") from error
    if _is_redirect(details) or not stat.S_ISDIR(details.st_mode):
        raise ExternalStateError("unsafe-state-path")
    _set_private_mode(path, directory=True)


def _validate_private_directory(path: Path) -> None:
    try:
        details = path.lstat()
    except FileNotFoundError as error:
        raise ExternalStateError("state-missing") from error
    except OSError as error:
        raise ExternalStateError("unsafe-state-path") from error
    if _is_redirect(details) or not stat.S_ISDIR(details.st_mode):
        raise ExternalStateError("unsafe-state-path")
    if os.name != "nt" and stat.S_IMODE(details.st_mode) & 0o077:
        raise ExternalStateError("unsafe-state-path")


def _validate_private_file(path: Path) -> None:
    try:
        details = path.lstat()
    except FileNotFoundError as error:
        raise ExternalStateError("state-missing") from error
    except OSError as error:
        raise ExternalStateError("unsafe-state-path") from error
    if _is_redirect(details) or not stat.S_ISREG(details.st_mode):
        raise ExternalStateError("unsafe-state-path")
    if os.name != "nt" and stat.S_IMODE(details.st_mode) & 0o077:
        raise ExternalStateError("unsafe-state-path")


def _ensure_descendant(base: Path, *parts: str) -> Path:
    current = base
    for part in parts:
        current /= part
        _ensure_directory(current)
    return current


def _validate_lexical_ancestor_chain(path: Path) -> None:
    """Reject redirects in every existing lexical ancestor without chmod."""
    for current in reversed((path, *path.parents)):
        if not os.path.lexists(current):
            continue
        try:
            details = current.lstat()
        except OSError as error:
            raise ExternalStateError("unsafe-state-path") from error
        if _is_redirect(details) or not stat.S_ISDIR(details.st_mode):
            raise ExternalStateError("unsafe-state-path")


def _create_missing_directory_chain(path: Path) -> None:
    """Create missing components only after all existing ancestors are trusted."""
    for current in reversed((path, *path.parents)):
        if os.path.lexists(current):
            continue
        try:
            current.mkdir(mode=0o700)
        except OSError as error:
            raise ExternalStateError("unsafe-state-path") from error
        _set_private_mode(current, directory=True)


def _validate_descendant_chain(base: Path, *parts: str) -> Path:
    current = base
    for index, part in enumerate(parts):
        current /= part
        if not os.path.lexists(current):
            break
        try:
            details = current.lstat()
        except OSError as error:
            raise ExternalStateError("unsafe-state-path") from error
        if _is_redirect(details):
            raise ExternalStateError("unsafe-state-path")
        if index < len(parts) - 1 and not stat.S_ISDIR(details.st_mode):
            raise ExternalStateError("unsafe-state-path")
    return base.joinpath(*parts)


def _validate_root(root: Path, repository_root: Path) -> Path:
    supplied = Path(root)
    if not supplied.is_absolute() or _has_control(str(supplied)):
        raise ExternalStateError("invalid-state-root")
    if os.name == "nt" and _is_windows_unc(str(supplied)):
        raise ExternalStateError("invalid-state-root")
    _validate_lexical_ancestor_chain(supplied)
    if os.path.lexists(supplied):
        try:
            details = supplied.lstat()
        except OSError as error:
            raise ExternalStateError("invalid-state-root") from error
        if _is_redirect(details):
            raise ExternalStateError("unsafe-state-path")
        if not stat.S_ISDIR(details.st_mode):
            raise ExternalStateError("invalid-state-root")
    try:
        normalized_root = supplied.resolve(strict=False)
        normalized_repository = repository_root.resolve(strict=True)
        common = os.path.commonpath(
            [os.path.normcase(str(normalized_root)), os.path.normcase(str(normalized_repository))]
        )
    except (OSError, ValueError) as error:
        raise ExternalStateError("invalid-state-root") from error
    if common == os.path.normcase(str(normalized_repository)):
        raise ExternalStateError("state-root-inside-repository")
    _create_missing_directory_chain(supplied)
    _ensure_directory(supplied)
    return supplied.resolve(strict=True)


def _read_only_root(root: Path, repository_root: Path) -> Path | None:
    supplied = Path(root)
    if not supplied.is_absolute() or _has_control(str(supplied)):
        raise ExternalStateError("invalid-state-root")
    if os.name == "nt" and _is_windows_unc(str(supplied)):
        raise ExternalStateError("invalid-state-root")
    _validate_lexical_ancestor_chain(supplied)
    try:
        normalized_root = supplied.resolve(strict=False)
        normalized_repository = repository_root.resolve(strict=True)
        common = os.path.commonpath(
            [
                os.path.normcase(str(normalized_root)),
                os.path.normcase(str(normalized_repository)),
            ]
        )
    except (OSError, ValueError) as error:
        raise ExternalStateError("invalid-state-root") from error
    if common == os.path.normcase(str(normalized_repository)):
        raise ExternalStateError("state-root-inside-repository")
    if not os.path.lexists(supplied):
        return None
    _validate_private_directory(supplied)
    try:
        return supplied.resolve(strict=True)
    except OSError as error:
        raise ExternalStateError("unsafe-state-path") from error


def _existing_private_directory(parent: Path, name: str) -> Path | None:
    candidate = parent / name
    if not os.path.lexists(candidate):
        return None
    _validate_private_directory(candidate)
    return candidate


def _canonical_attempt_number(name: str) -> int | None:
    if re.fullmatch(r"(?:[1-9]|[12][0-9]|3[0-2])", name) is None:
        return None
    return int(name)


def _observed_record_attempts(lab_directory: Path) -> tuple[int, ...]:
    _validate_private_directory(lab_directory)
    try:
        entries = tuple(lab_directory.iterdir())
    except OSError as error:
        raise ExternalStateError("unsafe-state-path") from error
    if not entries:
        raise ExternalStateError("state-corrupt")
    attempts: list[int] = []
    for attempt_directory in entries:
        attempt = _canonical_attempt_number(attempt_directory.name)
        if attempt is None:
            raise ExternalStateError("state-corrupt")
        _validate_private_directory(attempt_directory)
        state_path = attempt_directory / "state.json"
        if not os.path.lexists(state_path):
            raise ExternalStateError("state-corrupt")
        _validate_private_file(state_path)
        try:
            contents = tuple(attempt_directory.iterdir())
        except OSError as error:
            raise ExternalStateError("unsafe-state-path") from error
        if len(contents) != 1 or contents[0].name != "state.json":
            raise ExternalStateError("state-corrupt")
        attempts.append(attempt)
    return tuple(sorted(attempts))


def _shallow_repository_storage_id(
    locator_digest: str,
    epoch_digest: str,
    lab: str,
    attempt: int,
    repository_id: str,
) -> str:
    return hashlib.sha256(
        (
            "arbiter-academy/shallow-repository/v1\0"
            f"{locator_digest}\0{epoch_digest}\0{lab}\0{attempt}\0{repository_id}\n"
        ).encode("ascii")
    ).hexdigest()


def _p08_worktree_parent_storage_id(
    locator_digest: str,
    epoch_digest: str,
    attempt: int,
    worktree_id: str,
) -> str:
    return hashlib.sha256(
        (
            "arbiter-academy/p08-worktree-parent/v1\0"
            f"{locator_digest}\0{epoch_digest}\0p08\0{attempt}\0{worktree_id}\n"
        ).encode("ascii")
    ).hexdigest()[:32]


def _git_value(
    repository: Path,
    arguments: list[str],
    *,
    validate_local_config: bool = True,
) -> str:
    result = run_git(
        repository,
        arguments,
        check=False,
        validate_local_config=validate_local_config,
    )
    if result.returncode != 0:
        raise ExternalStateError("repository-identity")
    value = result.stdout.strip()
    if not value or _has_control(value):
        raise ExternalStateError("repository-identity")
    return value


def _repository_details(
    repository: Path,
    *,
    validate_local_config: bool = True,
) -> tuple[Path, Path, str]:
    try:
        supplied = Path(repository).expanduser().resolve(strict=True)
        top_level = Path(
            _git_value(
                supplied,
                ["rev-parse", "--show-toplevel"],
                validate_local_config=validate_local_config,
            )
        ).resolve(strict=True)
        common_text = _git_value(
            supplied,
            ["rev-parse", "--git-common-dir"],
            validate_local_config=validate_local_config,
        )
        common_candidate = Path(common_text)
        if not common_candidate.is_absolute():
            common_candidate = supplied / common_candidate
        common = common_candidate.resolve(strict=True)
        object_format = _git_value(
            supplied,
            ["rev-parse", "--show-object-format"],
            validate_local_config=validate_local_config,
        ).lower()
    except ExternalStateError:
        raise
    except (GitCommandError, OSError, RuntimeError, UnicodeError) as error:
        raise ExternalStateError("repository-identity") from error
    if object_format not in {"sha1", "sha256"} or not common.is_dir() or not top_level.is_dir():
        raise ExternalStateError("repository-identity")
    return top_level, common, object_format


def _filesystem_identity(common_directory: Path) -> tuple[int, int] | None:
    try:
        details = common_directory.stat()
    except OSError:
        return None
    device = details.st_dev
    inode = details.st_ino
    if (
        isinstance(device, int)
        and not isinstance(device, bool)
        and isinstance(inode, int)
        and not isinstance(inode, bool)
        and device > 0
        and inode > 0
    ):
        return device, inode
    return None


def repository_locator(
    repository: Path,
    *,
    validate_local_config: bool = True,
) -> RepositoryLocator:
    """Return an opaque locator shared by linked worktrees."""
    try:
        _, common, object_format = _repository_details(
            Path(repository),
            validate_local_config=validate_local_config,
        )
        filesystem_identity = _filesystem_identity(common)
        if filesystem_identity is not None:
            device, inode = filesystem_identity
            source_kind = "filesystem-id"
            preimage = (
                "arbiter-academy/repository-locator/v1\0filesystem-id\0"
                f"{object_format}\0{device}\0{inode}\n"
            ).encode("ascii")
        else:
            normalized = os.path.normcase(str(common)).replace("\\", "/")
            if _has_control(normalized):
                raise ExternalStateError("repository-identity")
            source_kind = "resolved-path-fallback"
            preimage = (
                "arbiter-academy/repository-locator/v1\0resolved-path-fallback\0"
                f"{object_format}\0{normalized}\n"
            ).encode("utf-8")
        return RepositoryLocator(
            digest=hashlib.sha256(preimage).hexdigest(),
            object_format=object_format,
            source_kind=source_kind,
        )
    except ExternalStateError:
        raise
    except (OSError, UnicodeError, ValueError) as error:
        raise ExternalStateError("repository-identity") from error


class _DuplicateKey(ValueError):
    pass


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKey
        result[key] = value
    return result


def _reject_constant(_: str) -> None:
    raise ValueError


def _validate_strings(value: Any) -> None:
    if isinstance(value, str):
        if _has_control(value):
            raise ExternalStateError("state-corrupt")
    elif isinstance(value, Mapping):
        for key, child in value.items():
            if not isinstance(key, str) or _has_control(key):
                raise ExternalStateError("state-corrupt")
            _validate_strings(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            _validate_strings(child)


def _read_json(path: Path, *, max_bytes: int) -> dict[str, Any]:
    try:
        details = path.lstat()
        if _is_redirect(details) or not stat.S_ISREG(details.st_mode):
            raise ExternalStateError("unsafe-state-path")
        if os.name != "nt" and stat.S_IMODE(details.st_mode) & 0o077:
            raise ExternalStateError("unsafe-state-path")
        if details.st_size > max_bytes:
            raise ExternalStateError("state-too-large")
        raw = path.read_bytes()
        if len(raw) > max_bytes:
            raise ExternalStateError("state-too-large")
        decoded = raw.decode("utf-8")
        value = json.loads(
            decoded,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except ExternalStateError:
        raise
    except FileNotFoundError:
        raise
    except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError) as error:
        raise ExternalStateError("state-corrupt") from error
    if not isinstance(value, dict):
        raise ExternalStateError("state-corrupt")
    _validate_strings(value)
    return value


def _canonical_json(value: Mapping[str, object], *, max_bytes: int) -> bytes:
    try:
        materialized = dict(value)
        _validate_strings(materialized)
        encoded = (
            json.dumps(
                materialized,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
    except ExternalStateError:
        raise
    except (TypeError, ValueError, UnicodeError) as error:
        raise ExternalStateError("state-corrupt") from error
    if len(encoded) > max_bytes:
        raise ExternalStateError("state-too-large")
    return encoded


def _fsync_parent(path: Path) -> None:
    if os.name == "nt":
        return
    directory_descriptor = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_descriptor)
    finally:
        os.close(directory_descriptor)


def _atomic_write(path: Path, payload: bytes) -> None:
    unique = secrets.token_hex(16)
    temporary = path.parent / f".{path.name}.{unique}.tmp"
    backup = path.parent / f".{path.name}.{unique}.bak"
    descriptor: int | None = None
    created = False
    backup_created = False
    replaced = False
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_BINARY"):
            flags |= os.O_BINARY
        descriptor = os.open(temporary, flags, 0o600)
        created = True
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            descriptor = None
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        _set_private_mode(temporary, directory=False)
        if os.path.lexists(path):
            details = path.lstat()
            if _is_redirect(details) or not stat.S_ISREG(details.st_mode):
                raise ExternalStateError("unsafe-state-path")
            previous = path.read_bytes()
            backup_descriptor = os.open(backup, flags, 0o600)
            backup_created = True
            with os.fdopen(backup_descriptor, "wb", closefd=True) as stream:
                stream.write(previous)
                stream.flush()
                os.fsync(stream.fileno())
            _set_private_mode(backup, directory=False)
        os.replace(temporary, path)
        created = False
        replaced = True
        _set_private_mode(path, directory=False)
        _fsync_parent(path)
        if backup_created:
            os.unlink(backup)
            backup_created = False
    except (ExternalStateError, OSError) as error:
        if replaced:
            try:
                if backup_created:
                    os.replace(backup, path)
                    backup_created = False
                else:
                    os.unlink(path)
            except OSError as rollback_error:
                raise ExternalStateError("state-corrupt") from rollback_error
        if isinstance(error, ExternalStateError):
            raise
        raise ExternalStateError("state-corrupt") from error
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
        if created:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
            except OSError:
                pass
        if backup_created:
            try:
                os.unlink(backup)
            except FileNotFoundError:
                pass
            except OSError:
                pass


def _validate_binding(academy_base_commit: str, catalog_sha256: str) -> None:
    if (
        not isinstance(academy_base_commit, str)
        or len(academy_base_commit) not in {40, 64}
        or any(character not in "0123456789abcdef" for character in academy_base_commit)
        or not isinstance(catalog_sha256, str)
        or len(catalog_sha256) != 64
        or any(character not in "0123456789abcdef" for character in catalog_sha256)
    ):
        raise ExternalStateError("state-identity-mismatch")


def _validate_identity(identity: dict[str, Any], expected: dict[str, object]) -> None:
    if set(identity) != _IDENTITY_KEYS:
        raise ExternalStateError("state-corrupt")
    repository_id = identity.get("repository_id")
    if (
        identity.get("schema_version") != 1
        or isinstance(identity.get("schema_version"), bool)
        or not isinstance(repository_id, str)
        or len(repository_id) != 32
        or any(character not in "0123456789abcdef" for character in repository_id)
    ):
        raise ExternalStateError("state-corrupt")
    for key, value in expected.items():
        if identity.get(key) != value:
            raise ExternalStateError("state-identity-mismatch")


class _AdvisoryLock:
    def __init__(self, path: Path, timeout_seconds: float) -> None:
        self.path = path
        self.timeout_seconds = timeout_seconds
        self.stream: IO[bytes] | None = None

    def __enter__(self) -> "_AdvisoryLock":
        if not isinstance(self.timeout_seconds, (int, float)) or isinstance(
            self.timeout_seconds, bool
        ):
            raise ExternalStateError("state-busy")
        try:
            timeout = float(self.timeout_seconds)
        except (OverflowError, TypeError, ValueError) as error:
            raise ExternalStateError("state-busy") from error
        if not math.isfinite(timeout) or timeout < 0:
            raise ExternalStateError("state-busy")
        try:
            binary = getattr(os, "O_BINARY", 0)
            try:
                descriptor = os.open(
                    self.path, os.O_RDWR | os.O_CREAT | os.O_EXCL | binary, 0o600
                )
                created = True
            except FileExistsError:
                _validate_private_file(self.path)
                descriptor = os.open(self.path, os.O_RDWR | binary)
                created = False
            self.stream = os.fdopen(descriptor, "r+b", closefd=True)
            if os.name == "nt":
                if created:
                    self.stream.write(b"\0")
                    self.stream.flush()
                    os.fsync(self.stream.fileno())
                elif os.fstat(descriptor).st_size != 1:
                    raise ExternalStateError("state-busy")
            if created:
                _set_private_mode(self.path, directory=False)
        except (OSError, ExternalStateError) as error:
            if self.stream is not None:
                self.stream.close()
                self.stream = None
            if isinstance(error, ExternalStateError):
                raise
            raise ExternalStateError("state-busy") from error
        deadline = time.monotonic() + timeout
        while True:
            try:
                self.stream.seek(0)
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
                    self.stream.seek(0)
                    if self.stream.read(1) != b"\0":
                        msvcrt.locking(self.stream.fileno(), msvcrt.LK_UNLCK, 1)
                        self.stream.close()
                        self.stream = None
                        raise ExternalStateError("state-busy")
                else:
                    import fcntl

                    fcntl.flock(self.stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                return self
            except OSError:
                if time.monotonic() >= deadline:
                    self.stream.close()
                    self.stream = None
                    raise ExternalStateError("state-busy")
                time.sleep(min(0.01, max(0.0, deadline - time.monotonic())))

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        if self.stream is None:
            return
        try:
            self.stream.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self.stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.stream.fileno(), fcntl.LOCK_UN)
        finally:
            self.stream.close()
            self.stream = None


class ExternalStateStore:
    """A repository- and Academy-epoch-bound state store."""

    def __init__(
        self,
        *,
        epoch_directory: Path,
        identity_path: Path,
        lock_path: Path,
        repository_id: str,
        state_root: Path,
        locator_digest: str,
        epoch_digest: str,
    ) -> None:
        self._epoch_dir = epoch_directory
        self._identity_path = identity_path
        self._lock_path = lock_path
        self._state_root = state_root
        self._locator_digest = locator_digest
        self._epoch_digest = epoch_digest
        self.repository_id = repository_id

    @classmethod
    def has_records(
        cls,
        repository: Path,
        *,
        lab: str,
        test_root: Path | None = None,
    ) -> bool:
        """Probe for existing records without reading content or mutating state."""
        if lab != "p02":
            raise ExternalStateError("unsafe-state-path")
        repository_root, _, _ = _repository_details(
            Path(repository),
            validate_local_config=False,
        )
        locator = repository_locator(
            Path(repository),
            validate_local_config=False,
        )
        selected = resolve_state_root() if test_root is None else Path(test_root)
        state_root = _read_only_root(selected, repository_root)
        if state_root is None:
            return False
        repositories = _existing_private_directory(state_root, "repositories")
        if repositories is None:
            return False
        locator_directory = _existing_private_directory(repositories, locator.digest)
        if locator_directory is None:
            return False
        lock_path = locator_directory / "lock"
        if not os.path.lexists(lock_path):
            raise ExternalStateError("state-identity-mismatch")
        _validate_private_file(lock_path)
        epochs = _existing_private_directory(locator_directory, "epochs")
        if epochs is None:
            raise ExternalStateError("state-identity-mismatch")
        try:
            epoch_entries = tuple(epochs.iterdir())
        except OSError as error:
            raise ExternalStateError("unsafe-state-path") from error
        if not epoch_entries:
            raise ExternalStateError("state-identity-mismatch")
        found = False
        for epoch_directory in epoch_entries:
            if re.fullmatch(r"[0-9a-f]{64}", epoch_directory.name) is None:
                raise ExternalStateError("state-identity-mismatch")
            _validate_private_directory(epoch_directory)
            identity_path = epoch_directory / "identity.json"
            if not os.path.lexists(identity_path):
                raise ExternalStateError("state-identity-mismatch")
            _validate_private_file(identity_path)
            identity = _read_json(identity_path, max_bytes=_MAX_RECORD_BYTES)
            academy_base_commit = identity.get("academy_base_commit")
            catalog_sha256 = identity.get("catalog_sha256")
            _validate_binding(academy_base_commit, catalog_sha256)
            expected_commit_length = 40 if locator.object_format == "sha1" else 64
            if len(academy_base_commit) != expected_commit_length:
                raise ExternalStateError("state-identity-mismatch")
            expected: dict[str, object] = {
                "locator": locator.digest,
                "locator_source": locator.source_kind,
                "object_format": locator.object_format,
                "academy_base_commit": academy_base_commit,
                "catalog_sha256": catalog_sha256,
            }
            _validate_identity(identity, expected)
            expected_epoch = hashlib.sha256(
                (
                    "arbiter-academy/state-epoch/v1\0"
                    f"{academy_base_commit}\0{catalog_sha256}\n"
                ).encode("ascii")
            ).hexdigest()
            if epoch_directory.name != expected_epoch:
                raise ExternalStateError("state-identity-mismatch")
            lab_directory = _existing_private_directory(epoch_directory, lab)
            if lab_directory is None:
                continue
            if _observed_record_attempts(lab_directory):
                found = True
        return found

    @classmethod
    def open_existing(
        cls,
        repository: Path,
        *,
        academy_base_commit: str,
        catalog_sha256: str,
        test_root: Path | None = None,
    ) -> "ExternalStateStore | None":
        """Open an exact existing epoch without creating or repairing state."""
        _validate_binding(academy_base_commit, catalog_sha256)
        repository_root, _, _ = _repository_details(Path(repository))
        locator = repository_locator(Path(repository))
        expected_commit_length = 40 if locator.object_format == "sha1" else 64
        if len(academy_base_commit) != expected_commit_length:
            raise ExternalStateError("state-identity-mismatch")
        selected = resolve_state_root() if test_root is None else Path(test_root)
        state_root = _read_only_root(selected, repository_root)
        if state_root is None:
            return None
        repositories = _existing_private_directory(state_root, "repositories")
        if repositories is None:
            return None
        locator_directory = _existing_private_directory(repositories, locator.digest)
        if locator_directory is None:
            return None
        lock_path = locator_directory / "lock"
        if not os.path.lexists(lock_path):
            raise ExternalStateError("state-identity-mismatch")
        _validate_private_file(lock_path)
        epochs = _existing_private_directory(locator_directory, "epochs")
        if epochs is None:
            raise ExternalStateError("state-identity-mismatch")
        try:
            epoch_entries = tuple(epochs.iterdir())
        except OSError as error:
            raise ExternalStateError("unsafe-state-path") from error
        if not epoch_entries:
            raise ExternalStateError("state-identity-mismatch")
        validated_epochs: dict[str, Path] = {}
        for observed_epoch in epoch_entries:
            if re.fullmatch(r"[0-9a-f]{64}", observed_epoch.name) is None:
                raise ExternalStateError("state-identity-mismatch")
            _validate_private_directory(observed_epoch)
            observed_identity_path = observed_epoch / "identity.json"
            if not os.path.lexists(observed_identity_path):
                raise ExternalStateError("state-identity-mismatch")
            _validate_private_file(observed_identity_path)
            observed_identity = _read_json(
                observed_identity_path, max_bytes=_MAX_RECORD_BYTES
            )
            observed_base = observed_identity.get("academy_base_commit")
            observed_catalog = observed_identity.get("catalog_sha256")
            _validate_binding(observed_base, observed_catalog)
            if len(observed_base) != expected_commit_length:
                raise ExternalStateError("state-identity-mismatch")
            observed_expected: dict[str, object] = {
                "locator": locator.digest,
                "locator_source": locator.source_kind,
                "object_format": locator.object_format,
                "academy_base_commit": observed_base,
                "catalog_sha256": observed_catalog,
            }
            _validate_identity(observed_identity, observed_expected)
            observed_digest = hashlib.sha256(
                (
                    "arbiter-academy/state-epoch/v1\0"
                    f"{observed_base}\0{observed_catalog}\n"
                ).encode("ascii")
            ).hexdigest()
            if observed_epoch.name != observed_digest:
                raise ExternalStateError("state-identity-mismatch")
            observed_p02 = _existing_private_directory(observed_epoch, "p02")
            if observed_p02 is not None:
                _observed_record_attempts(observed_p02)
            validated_epochs[observed_epoch.name] = observed_epoch
        epoch = hashlib.sha256(
            (
                "arbiter-academy/state-epoch/v1\0"
                f"{academy_base_commit}\0{catalog_sha256}\n"
            ).encode("ascii")
        ).hexdigest()
        epoch_directory = validated_epochs.get(epoch)
        if epoch_directory is None:
            return None
        identity_path = epoch_directory / "identity.json"
        if not os.path.lexists(identity_path) or not os.path.lexists(lock_path):
            raise ExternalStateError("state-identity-mismatch")
        _validate_private_file(identity_path)
        _validate_private_file(lock_path)
        expected: dict[str, object] = {
            "locator": locator.digest,
            "locator_source": locator.source_kind,
            "object_format": locator.object_format,
            "academy_base_commit": academy_base_commit,
            "catalog_sha256": catalog_sha256,
        }
        identity = _read_json(identity_path, max_bytes=_MAX_RECORD_BYTES)
        _validate_identity(identity, expected)
        repository_id = identity["repository_id"]
        assert isinstance(repository_id, str)
        return cls(
            epoch_directory=epoch_directory,
            identity_path=identity_path,
            lock_path=lock_path,
            repository_id=repository_id,
            state_root=state_root,
            locator_digest=locator.digest,
            epoch_digest=epoch,
        )

    @classmethod
    def open(
        cls,
        repository: Path,
        *,
        academy_base_commit: str,
        catalog_sha256: str,
        test_root: Path | None = None,
    ) -> "ExternalStateStore":
        _validate_binding(academy_base_commit, catalog_sha256)
        repository_root, _, _ = _repository_details(Path(repository))
        locator = repository_locator(Path(repository))
        expected_commit_length = 40 if locator.object_format == "sha1" else 64
        if len(academy_base_commit) != expected_commit_length:
            raise ExternalStateError("state-identity-mismatch")
        selected_root = resolve_state_root() if test_root is None else Path(test_root)
        state_root = _validate_root(selected_root, repository_root)
        repositories = _ensure_descendant(state_root, "repositories")
        locator_directory = _ensure_descendant(repositories, locator.digest)
        lock_path = locator_directory / "lock"
        epoch = hashlib.sha256(
            (
                "arbiter-academy/state-epoch/v1\0"
                f"{academy_base_commit}\0{catalog_sha256}\n"
            ).encode("ascii")
        ).hexdigest()
        expected: dict[str, object] = {
            "locator": locator.digest,
            "locator_source": locator.source_kind,
            "object_format": locator.object_format,
            "academy_base_commit": academy_base_commit,
            "catalog_sha256": catalog_sha256,
        }
        with _AdvisoryLock(lock_path, 2.0):
            epochs = _ensure_descendant(locator_directory, "epochs")
            epoch_directory = _ensure_descendant(epochs, epoch)
            identity_path = epoch_directory / "identity.json"
            if identity_path.exists():
                identity = _read_json(identity_path, max_bytes=_MAX_RECORD_BYTES)
                _validate_identity(identity, expected)
            else:
                if os.path.lexists(identity_path):
                    raise ExternalStateError("unsafe-state-path")
                try:
                    if next(epoch_directory.iterdir(), None) is not None:
                        raise ExternalStateError("state-identity-mismatch")
                except ExternalStateError:
                    raise
                except OSError as error:
                    raise ExternalStateError("unsafe-state-path") from error
                identity = {
                    "schema_version": 1,
                    "repository_id": secrets.token_hex(16),
                    **expected,
                }
                payload = _canonical_json(identity, max_bytes=_MAX_RECORD_BYTES)
                _atomic_write(identity_path, payload)
            repository_id = identity["repository_id"]
            assert isinstance(repository_id, str)
        return cls(
            epoch_directory=epoch_directory,
            identity_path=identity_path,
            lock_path=lock_path,
            repository_id=repository_id,
            state_root=state_root,
            locator_digest=locator.digest,
            epoch_digest=epoch,
        )

    def locked(
        self, *, timeout_seconds: float = 2.0
    ) -> ContextManager["LockedExternalState"]:
        return self._locked(timeout_seconds)

    @contextmanager
    def _locked(self, timeout_seconds: float) -> Iterator["LockedExternalState"]:
        with _AdvisoryLock(self._lock_path, timeout_seconds):
            locked = LockedExternalState(self, _capability=_LOCK_CAPABILITY)
            try:
                yield locked
            finally:
                locked._invalidate()


class LockedExternalState:
    """Record operations available only while the store lock is held."""

    def __init__(
        self, store: ExternalStateStore, *, _capability: object | None = None
    ) -> None:
        if _capability is not _LOCK_CAPABILITY:
            raise ExternalStateError("state-busy")
        self._store = store
        self._active = True
        self.repository_id = store.repository_id

    def _invalidate(self) -> None:
        self._active = False

    def _require_active(self) -> None:
        if not self._active:
            raise ExternalStateError("state-busy")

    @staticmethod
    def _validate_location(lab: str, attempt: int) -> None:
        if lab not in {"p02", "p08"}:
            raise ExternalStateError("unsafe-state-path")
        if not isinstance(attempt, int) or isinstance(attempt, bool) or not 1 <= attempt <= 32:
            raise ExternalStateError("attempt-limit")

    @staticmethod
    def _validate_max_bytes(max_bytes: int) -> None:
        if (
            not isinstance(max_bytes, int)
            or isinstance(max_bytes, bool)
            or not 1 <= max_bytes <= _MAX_RECORD_BYTES
        ):
            raise ExternalStateError("state-too-large")

    def _record_path(self, lab: str, attempt: int) -> Path:
        self._validate_location(lab, attempt)
        return _validate_descendant_chain(
            self._store._epoch_dir, lab, str(attempt), "state.json"
        )

    def read_record(
        self, lab: str, attempt: int, *, max_bytes: int = _MAX_RECORD_BYTES
    ) -> dict[str, Any] | None:
        self._require_active()
        self._validate_max_bytes(max_bytes)
        path = self._record_path(lab, attempt)
        if not os.path.lexists(path):
            return None
        record = _read_json(path, max_bytes=max_bytes)
        generation = record.get("generation")
        if not isinstance(generation, int) or isinstance(generation, bool) or generation < 1:
            raise ExternalStateError("state-corrupt")
        return record

    def record_attempts(self, lab: str) -> tuple[int, ...]:
        """Return canonical observed attempts without reading record content."""
        self._require_active()
        if lab not in {"p02", "p08"}:
            raise ExternalStateError("unsafe-state-path")
        lab_directory = self._store._epoch_dir / lab
        if not os.path.lexists(lab_directory):
            return ()
        return _observed_record_attempts(lab_directory)

    def write_record(
        self,
        lab: str,
        attempt: int,
        record: Mapping[str, object],
        *,
        expected_generation: int,
        max_bytes: int = _MAX_RECORD_BYTES,
    ) -> None:
        self._require_active()
        self._validate_max_bytes(max_bytes)
        path = self._record_path(lab, attempt)
        if (
            not isinstance(expected_generation, int)
            or isinstance(expected_generation, bool)
            or expected_generation < 0
        ):
            raise ExternalStateError("generation-mismatch")
        if not isinstance(record, Mapping):
            raise ExternalStateError("state-corrupt")
        materialized = dict(record)
        generation = materialized.get("generation")
        if not isinstance(generation, int) or isinstance(generation, bool) or generation < 1:
            raise ExternalStateError("state-corrupt")
        existing = self.read_record(lab, attempt, max_bytes=max_bytes)
        if existing is None:
            if expected_generation != 0 or generation != 1:
                raise ExternalStateError("generation-mismatch")
        elif (
            existing["generation"] != expected_generation
            or generation != expected_generation + 1
        ):
            raise ExternalStateError("generation-mismatch")
        payload = _canonical_json(materialized, max_bytes=max_bytes)
        attempt_directory = _ensure_descendant(
            self._store._epoch_dir, lab, str(attempt)
        )
        _atomic_write(attempt_directory / "state.json", payload)

    def owned_directory(
        self, lab: str, attempt: int, *components: str
    ) -> Path:
        self._require_active()
        self._validate_location(lab, attempt)
        if not 1 <= len(components) <= 4:
            raise ExternalStateError("unsafe-state-path")
        for component in components:
            if (
                not isinstance(component, str)
                or not component.isascii()
                or component in {".", ".."}
                or component.endswith((".", " "))
                or "/" in component
                or "\\" in component
                or _has_control(component)
                or ntpath.splitdrive(component)[0]
                or _OWNED_COMPONENT.fullmatch(component) is None
                or component.split(".", 1)[0].casefold()
                in _WINDOWS_RESERVED_NAMES
            ):
                raise ExternalStateError("unsafe-state-path")
        trusted = _ensure_descendant(
            self._store._epoch_dir, lab, str(attempt), *components
        )
        return trusted.resolve(strict=True)

    def owned_repository_directory(
        self,
        lab: str,
        attempt: int,
        repository_id: str,
        *,
        create: bool = False,
    ) -> tuple[Path, bool]:
        """Look up or atomically create one shallow P02 repository directory."""
        self._require_active()
        self._validate_location(lab, attempt)
        if lab != "p02":
            raise ExternalStateError("unsafe-state-path")
        if (
            not isinstance(repository_id, str)
            or re.fullmatch(r"[0-9a-f]{64}", repository_id) is None
        ):
            raise ExternalStateError("unsafe-state-path")
        storage_id = _shallow_repository_storage_id(
            self._store._locator_digest,
            self._store._epoch_digest,
            lab,
            attempt,
            repository_id,
        )
        candidate = self._store._state_root / "remotes" / storage_id
        path_units = len(os.fspath(candidate).encode("utf-16-le")) // 2
        if os.name == "nt" and path_units > 240:
            raise ExternalStateError("unsafe-state-path")
        remotes = self._store._state_root / "remotes"
        if not create:
            _validate_private_directory(remotes)
            _validate_private_directory(candidate)
            return candidate.resolve(strict=True), False
        if not os.path.lexists(remotes):
            _ensure_directory(remotes)
        else:
            _validate_private_directory(remotes)
        created = False
        try:
            candidate.mkdir(mode=0o700)
            created = True
        except FileExistsError:
            pass
        except OSError as error:
            raise ExternalStateError("unsafe-state-path") from error
        if created:
            _set_private_mode(candidate, directory=True)
        else:
            _validate_private_directory(candidate)
        return candidate.resolve(strict=True), created

    def owned_p08_worktree_parent(self, attempt: int, worktree_id: str) -> Path:
        """Create or validate one shallow, externally-owned P08 worktree parent."""
        self._require_active()
        self._validate_location("p08", attempt)
        if (
            not isinstance(worktree_id, str)
            or re.fullmatch(r"[0-9a-f]{64}", worktree_id) is None
        ):
            raise ExternalStateError("unsafe-state-path")
        storage_id = _p08_worktree_parent_storage_id(
            self._store._locator_digest,
            self._store._epoch_digest,
            attempt,
            worktree_id,
        )
        state_root = self._store._state_root
        shallow_root = state_root / "p08-worktrees"
        parent = shallow_root / storage_id
        target = parent / worktree_id
        path_units = len(os.fspath(target / ".git").encode("utf-16-le")) // 2
        if os.name == "nt" and path_units > 240:
            raise ExternalStateError("unsafe-state-path")
        try:
            parent.relative_to(shallow_root)
            shallow_root.relative_to(state_root)
        except ValueError as error:
            raise ExternalStateError("unsafe-state-path") from error
        for directory in (state_root, shallow_root, parent):
            if os.path.lexists(directory):
                _validate_private_directory(directory)
        if not os.path.lexists(shallow_root):
            _ensure_directory(shallow_root)
        if not os.path.lexists(parent):
            _ensure_directory(parent)
        try:
            resolved_root = state_root.resolve(strict=True)
            resolved_parent = parent.resolve(strict=True)
            resolved_parent.relative_to(resolved_root)
        except (OSError, RuntimeError, ValueError) as error:
            raise ExternalStateError("unsafe-state-path") from error
        return resolved_parent
