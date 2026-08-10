"""Bounded, opaque validation for P04's reviewed candidate package data."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
import json
import re
from typing import Mapping
from zipfile import BadZipFile, ZipFile


P04_CANDIDATE_ROOT = "academy/candidates/P04-review-a-dependency"

_DATEUTIL_WHEEL = "python_dateutil-2.9.0.post0-py2.py3-none-any.whl"
_SIX_WHEEL = "six-1.17.0-py2.py3-none-any.whl"
_DATEUTIL_LICENSE = "python_dateutil-2.9.0.post0.LICENSE"
_SIX_LICENSE = "six-1.17.0.LICENSE"
_APACHE_LICENSE = "Apache-2.0.txt"
_MANIFEST = "candidate-set.json"
_WHEEL_NAMES = (_DATEUTIL_WHEEL, _SIX_WHEEL)
_LICENSE_NAMES = (_DATEUTIL_LICENSE, _SIX_LICENSE, _APACHE_LICENSE)
_REQUIRED_NAMES = frozenset((_MANIFEST, *_WHEEL_NAMES, *_LICENSE_NAMES))
_MAX_SIZES = {
    _MANIFEST: 16 * 1024,
    _DATEUTIL_WHEEL: 1024 * 1024,
    _SIX_WHEEL: 1024 * 1024,
    _DATEUTIL_LICENSE: 64 * 1024,
    _SIX_LICENSE: 64 * 1024,
    _APACHE_LICENSE: 64 * 1024,
}
_MAX_TOTAL_SIZE = 3 * 1024 * 1024
_MAX_UNCOMPRESSED_SIZE = 4 * 1024 * 1024
_DRIVE_PREFIX = re.compile(r"^[A-Za-z]:")


class CandidateDataError(ValueError):
    """Packaged P04 candidate evidence is absent, malformed, or mismatched."""


@dataclass(frozen=True)
class CandidatePayload:
    filename: str
    size_bytes: int
    sha256: str


@dataclass(frozen=True)
class P04CandidateSet:
    wheels: tuple[CandidatePayload, CandidatePayload]
    licenses: tuple[CandidatePayload, CandidatePayload, CandidatePayload]


_EXPECTED_MANIFEST: dict[str, object] = {
    "install_policy": "review-only-never-install",
    "lab_id": "P04-review-a-dependency",
    "license_payloads": [
        {
            "filename": _DATEUTIL_LICENSE,
            "sha256": "ba00f51a0d92823b5a1cde27d8b5b9d2321e67ed8da9bc163eff96d5e17e577e",
            "size_bytes": 2889,
            "source": f"{_DATEUTIL_WHEEL}!/python_dateutil-2.9.0.post0.dist-info/LICENSE",
        },
        {
            "filename": _SIX_LICENSE,
            "sha256": "4375ba20e2b9c6c4e7cad2940a628fd90e95cc3d50ee92aae755715d8ba1fbd0",
            "size_bytes": 1066,
            "source": f"{_SIX_WHEEL}!/six-1.17.0.dist-info/LICENSE",
        },
        {
            "filename": _APACHE_LICENSE,
            "sha256": "cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30",
            "size_bytes": 11358,
            "source": "https://www.apache.org/licenses/LICENSE-2.0.txt",
        },
    ],
    "schema_version": 1,
    "wheels": [
        {
            "filename": _DATEUTIL_WHEEL,
            "name": "python-dateutil",
            "sha256": "a8b2bc7bffae282281c8140a97d3aa9c14da0b136dfe83f850eea9a5f7470427",
            "size_bytes": 229892,
            "version": "2.9.0.post0",
        },
        {
            "filename": _SIX_WHEEL,
            "name": "six",
            "sha256": "4721f391ed90541fddacab5acf947aa0d3dc7d27b2e1e8eda2be8970586c3274",
            "size_bytes": 11050,
            "version": "1.17.0",
        },
    ],
}


def _error(filename: str, mismatch: str) -> CandidateDataError:
    return CandidateDataError(f"P04 candidate {filename}: {mismatch}.")


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("utf-8") + b"\n"


def _manifest_types(value: object) -> bool:
    if not isinstance(value, dict) or set(value) != {
        "schema_version", "lab_id", "install_policy", "wheels", "license_payloads"
    }:
        return False
    if type(value["schema_version"]) is not int or type(value["lab_id"]) is not str or type(value["install_policy"]) is not str:
        return False
    wheels = value["wheels"]
    licenses = value["license_payloads"]
    if not isinstance(wheels, list) or not isinstance(licenses, list) or len(wheels) != 2 or len(licenses) != 3:
        return False
    for item in wheels:
        if not isinstance(item, dict) or set(item) != {"name", "version", "filename", "size_bytes", "sha256"}:
            return False
        if any(type(item[key]) is not str for key in ("name", "version", "filename", "sha256")) or type(item["size_bytes"]) is not int:
            return False
    for item in licenses:
        if not isinstance(item, dict) or set(item) != {"filename", "size_bytes", "sha256", "source"}:
            return False
        if any(type(item[key]) is not str for key in ("filename", "sha256", "source")) or type(item["size_bytes"]) is not int:
            return False
    return True


def _parse_manifest(raw: bytes) -> dict[str, object]:
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise _error(_MANIFEST, "invalid JSON") from None
    if not _manifest_types(value) or raw != _canonical_json(value) or value != _EXPECTED_MANIFEST:
        raise _error(_MANIFEST, "mismatch")
    return value


def _payloads_from_manifest(manifest: Mapping[str, object]) -> dict[str, CandidatePayload]:
    result: dict[str, CandidatePayload] = {}
    for category in ("wheels", "license_payloads"):
        entries = manifest[category]
        assert isinstance(entries, list)
        for entry in entries:
            assert isinstance(entry, dict)
            result[str(entry["filename"])] = CandidatePayload(
                filename=str(entry["filename"]),
                size_bytes=int(entry["size_bytes"]),
                sha256=str(entry["sha256"]),
            )
    return result


def _verify_payload_hashes(blobs: Mapping[str, bytes], manifest: Mapping[str, object]) -> None:
    for payload in _payloads_from_manifest(manifest).values():
        raw = blobs[payload.filename]
        if len(raw) != payload.size_bytes or sha256(raw).hexdigest() != payload.sha256:
            raise _error(payload.filename, "identity mismatch")


def _safe_member_name(name: str) -> bool:
    if not name or name.startswith("/") or _DRIVE_PREFIX.match(name) or "\\" in name or any(ord(character) < 32 or ord(character) == 127 for character in name):
        return False
    parts = name.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        return False
    basename = parts[-1].casefold()
    return not (basename in {"notice", "patent"} or basename.startswith("notice.") or basename.startswith("patent."))


def _headers(raw: bytes, filename: str) -> dict[str, list[str]]:
    if len(raw) > 16 * 1024:
        raise _error(filename, "metadata too large")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise _error(filename, "metadata encoding") from None
    result: dict[str, list[str]] = {}
    for line in text.splitlines():
        if not line:
            break
        if not line or line[0] in " \t" or ":" not in line:
            raise _error(filename, "metadata format")
        key, value = line.split(":", 1)
        if not key or not value.startswith(" "):
            raise _error(filename, "metadata format")
        result.setdefault(key.casefold(), []).append(value[1:])
    return result


def _single_entry(archive: ZipFile, name: str, wheel: str):
    matches = [entry for entry in archive.infolist() if entry.filename == name]
    if len(matches) != 1:
        raise _error(wheel, "required entry mismatch")
    return matches[0]


def _validate_wheel(
    raw: bytes,
    *,
    filename: str,
    distribution: str,
    version: str,
    requires_dist: tuple[str, ...],
    requires_python: str,
    license_name: str,
    external_license: bytes,
) -> None:
    try:
        with ZipFile(BytesIO(raw)) as archive:
            entries = archive.infolist()
            if any(entry.flag_bits & 0x1 for entry in entries):
                raise _error(filename, "encrypted archive")
            names = [entry.orig_filename for entry in entries]
            if len(names) != len(set(names)) or any(not _safe_member_name(name) for name in names):
                raise _error(filename, "unsafe archive")
            if sum(entry.file_size for entry in entries) > _MAX_UNCOMPRESSED_SIZE:
                raise _error(filename, "archive too large")
            prefix = f"{distribution.replace('-', '_')}-{version}.dist-info"
            metadata = _headers(archive.read(_single_entry(archive, f"{prefix}/METADATA", filename)), filename)
            wheel = _headers(archive.read(_single_entry(archive, f"{prefix}/WHEEL", filename)), filename)
            embedded_license = archive.read(_single_entry(archive, f"{prefix}/LICENSE", filename))
    except CandidateDataError:
        raise
    except (BadZipFile, OSError, RuntimeError, ValueError):
        raise _error(filename, "invalid archive") from None
    if metadata.get("name") != [distribution] or metadata.get("version") != [version]:
        raise _error(filename, "metadata mismatch")
    if metadata.get("requires-python") != [requires_python]:
        raise _error(filename, "metadata mismatch")
    if tuple(metadata.get("requires-dist", ())) != requires_dist:
        raise _error(filename, "metadata mismatch")
    if wheel.get("root-is-purelib") != ["true"] or tuple(wheel.get("tag", ())) != ("py2-none-any", "py3-none-any"):
        raise _error(filename, "wheel metadata mismatch")
    if embedded_license != external_license:
        raise _error(license_name, "embedded license mismatch")


def validate_p04_candidate_blobs(blobs: Mapping[str, bytes]) -> P04CandidateSet:
    """Validate the complete immutable P04 candidate set without executing its contents."""
    if set(blobs) != _REQUIRED_NAMES:
        raise _error(_MANIFEST, "file set mismatch")
    if any(not isinstance(value, bytes) for value in blobs.values()):
        raise _error(_MANIFEST, "byte payload required")
    if any(len(blobs[name]) > _MAX_SIZES[name] for name in _REQUIRED_NAMES) or sum(len(value) for value in blobs.values()) > _MAX_TOTAL_SIZE:
        raise _error(_MANIFEST, "size limit exceeded")
    manifest = _parse_manifest(blobs[_MANIFEST])
    _verify_payload_hashes(blobs, manifest)
    _validate_wheel(
        blobs[_DATEUTIL_WHEEL], filename=_DATEUTIL_WHEEL, distribution="python-dateutil", version="2.9.0.post0",
        requires_dist=("six >=1.5",), requires_python="!=3.0.*,!=3.1.*,!=3.2.*,>=2.7",
        license_name=_DATEUTIL_LICENSE, external_license=blobs[_DATEUTIL_LICENSE],
    )
    _validate_wheel(
        blobs[_SIX_WHEEL], filename=_SIX_WHEEL, distribution="six", version="1.17.0",
        requires_dist=(), requires_python=">=2.7, !=3.0.*, !=3.1.*, !=3.2.*",
        license_name=_SIX_LICENSE, external_license=blobs[_SIX_LICENSE],
    )
    payloads = _payloads_from_manifest(manifest)
    return P04CandidateSet(
        wheels=(payloads[_DATEUTIL_WHEEL], payloads[_SIX_WHEEL]),
        licenses=(payloads[_DATEUTIL_LICENSE], payloads[_SIX_LICENSE], payloads[_APACHE_LICENSE]),
    )
