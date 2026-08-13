#!/usr/bin/env python3
"""Build canonical, offline Arbiter Academy release assets."""

from __future__ import annotations

import argparse
import base64
import csv
import datetime as dt
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


SETUPTOOLS_WHEEL = "setuptools-83.0.0-py3-none-any.whl"
SETUPTOOLS_SHA256 = "29b23c360f22f414dc7336bb39178cc7bcbf6021ed2733cde173f09dba19abb3"
RELEASE_PATTERN = re.compile(r"preview-[0-9]+\.[0-9]+")


class BuildError(RuntimeError):
    pass


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _zip_datetime(epoch: int) -> tuple[int, int, int, int, int, int]:
    try:
        moment = dt.datetime.fromtimestamp(epoch, tz=dt.timezone.utc)
    except (OverflowError, OSError, ValueError) as error:
        raise BuildError("epoch must map to a ZIP-supported UTC year from 1980 through 2107") from error
    if not 1980 <= moment.year <= 2107:
        raise BuildError("epoch must map to a ZIP-supported UTC year from 1980 through 2107")
    return (moment.year, moment.month, moment.day, moment.hour, moment.minute, moment.second // 2 * 2)


def _zip_info(name: str, timestamp: tuple[int, int, int, int, int, int], mode: int = 0o644) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, timestamp)
    info.compress_type = zipfile.ZIP_STORED
    info.create_system = 3
    info.external_attr = mode << 16
    return info


def _write_zip(path: Path, members: dict[str, bytes], timestamp: tuple[int, int, int, int, int, int]) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
        for name in sorted(members):
            archive.writestr(_zip_info(name, timestamp), members[name])


def _canonical_wheel_record(members: dict[str, bytes], record_name: str) -> bytes:
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    for name in sorted(members):
        if name == record_name:
            writer.writerow((name, "", ""))
            continue
        digest = base64.urlsafe_b64encode(hashlib.sha256(members[name]).digest()).rstrip(b"=").decode("ascii")
        writer.writerow((name, f"sha256={digest}", str(len(members[name]))))
    return output.getvalue().encode("utf-8")


def _normalize_wheel(source: Path, destination: Path, timestamp: tuple[int, int, int, int, int, int]) -> None:
    with zipfile.ZipFile(source) as archive:
        members = {info.filename: archive.read(info) for info in archive.infolist() if not info.is_dir()}
    record_names = [name for name in members if name.endswith(".dist-info/RECORD")]
    if len(record_names) != 1:
        raise BuildError(f"wheel must contain exactly one dist-info RECORD, found {len(record_names)}")
    record_name = record_names[0]
    dist_info = record_name.rsplit("/", 1)[0]
    text_suffixes = (".css", ".html", ".js", ".json", ".md", ".py", ".toml", ".txt", ".yaml", ".yml")
    for name, payload in members.items():
        if name.endswith(text_suffixes):
            members[name] = payload.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    for metadata_name in ("METADATA", "WHEEL", "entry_points.txt", "top_level.txt"):
        name = f"{dist_info}/{metadata_name}"
        if name in members:
            members[name] = members[name].replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    members[record_name] = _canonical_wheel_record(members, record_name)
    _write_zip(destination, members, timestamp)


def _verified_build_wheelhouse(source: Path) -> Path:
    wheelhouse = source / ".github" / "wheelhouse"
    wheel = wheelhouse / SETUPTOOLS_WHEEL
    if not wheel.is_file() or _sha256_bytes(wheel.read_bytes()) != SETUPTOOLS_SHA256:
        raise BuildError(f"reviewed build prerequisite is missing or has the wrong digest: {wheel}")
    return wheelhouse


def _build_wheel(source: Path, epoch: int, destination: Path) -> Path:
    wheelhouse = _verified_build_wheelhouse(source)
    raw_directory = destination / "raw-wheel"
    raw_directory.mkdir()
    environment = os.environ.copy()
    environment.update(
        {
            "PIP_DISABLE_PIP_VERSION_CHECK": "1",
            "PIP_NO_INDEX": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "SOURCE_DATE_EPOCH": str(epoch),
        }
    )
    command = [
        sys.executable,
        "-m",
        "pip",
        "wheel",
        "--no-index",
        "--find-links",
        str(wheelhouse),
        "--no-deps",
        "--wheel-dir",
        str(raw_directory),
        str(source),
    ]
    result = subprocess.run(command, env=environment, text=True, capture_output=True, check=False)
    if result.returncode:
        raise BuildError("offline Academy wheel build failed:\n" + result.stdout + result.stderr)
    wheels = list(raw_directory.glob("workshop_queue-*.whl"))
    if len(wheels) != 1:
        raise BuildError(f"offline build produced {len(wheels)} Academy wheels, expected exactly one")
    normalized = destination / wheels[0].name
    _normalize_wheel(wheels[0], normalized, _zip_datetime(epoch))
    return normalized


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8") + b"\n"


def _checksum(name: str, payload: bytes) -> bytes:
    return f"{_sha256_bytes(payload)}  {name}\n".encode("ascii")


def build_assets(source: Path, output: Path, epoch: int, release: str) -> dict[str, str]:
    source = source.resolve(strict=True)
    output = output.resolve(strict=True)
    if not output.is_dir() or any(output.iterdir()):
        raise BuildError("output must be an existing empty directory")
    if RELEASE_PATTERN.fullmatch(release) is None:
        raise BuildError("release must match preview-N.N")
    timestamp = _zip_datetime(epoch)
    archive_name = f"arbiter-academy-{release}.zip"

    with tempfile.TemporaryDirectory(prefix="arbiter-academy-release-") as temporary_directory:
        temporary = Path(temporary_directory)
        staged_assets = temporary / "assets"
        staged_assets.mkdir()
        wheel = _build_wheel(source, epoch, temporary)
        wheel_bytes = wheel.read_bytes()
        manifest = _canonical_json(
            {
                "format_version": 1,
                "release": release,
                "wheelhouse": [
                    {
                        "filename": wheel.name,
                        "sha256": _sha256_bytes(wheel_bytes),
                        "size": len(wheel_bytes),
                    }
                ],
            }
        )
        archive_path = staged_assets / archive_name
        _write_zip(
            archive_path,
            {
                "bundle-manifest.json": manifest,
                f"wheelhouse/{wheel.name}": wheel_bytes,
            },
            timestamp,
        )

        bundle_bytes = archive_path.read_bytes()
        bundle_digest = _sha256_bytes(bundle_bytes)
        for script_name in ("install.ps1", "install.sh"):
            script = (source / "install" / script_name).read_bytes()
            if script.count(bundle_digest.encode("ascii")) != 1:
                raise BuildError(
                    f"tracked installer does not embed the final bundle digest exactly once: "
                    f"{script_name} (expected {bundle_digest})"
                )
            checksum = _checksum(script_name, script)
            tracked_checksum = (source / "install" / f"{script_name}.sha256").read_bytes()
            if tracked_checksum != checksum:
                raise BuildError(f"tracked installer checksum is not canonical or does not match: {script_name}.sha256")
            (staged_assets / script_name).write_bytes(script)
            (staged_assets / f"{script_name}.sha256").write_bytes(tracked_checksum)
        (staged_assets / f"{archive_name}.sha256").write_bytes(_checksum(archive_name, bundle_bytes))

        transferred: list[Path] = []
        try:
            for staged in sorted(staged_assets.iterdir()):
                destination = output / staged.name
                staged.replace(destination)
                transferred.append(destination)
        except OSError:
            for destination in transferred:
                destination.unlink(missing_ok=True)
            raise
    return {path.name: _sha256_bytes(path.read_bytes()) for path in sorted(output.iterdir())}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--epoch", required=True, type=int)
    parser.add_argument("--release", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        digests = build_assets(arguments.source, arguments.output, arguments.epoch, arguments.release)
    except (BuildError, OSError, zipfile.BadZipFile) as error:
        print(f"release asset build failed: {error}", file=sys.stderr)
        return 1
    for name, digest in digests.items():
        print(f"{digest}  {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
