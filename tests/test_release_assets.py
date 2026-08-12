from __future__ import annotations

import base64
import hashlib
import io
import importlib.util
import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import tarfile
import unittest
from unittest.mock import patch
import zipfile
from pathlib import Path


REPOSITORY = Path(__file__).resolve().parents[1]
BUILDER = REPOSITORY / "scripts" / "build_release_assets.py"
RELEASE = "preview-0.6"
ARCHIVE = f"arbiter-academy-{RELEASE}.zip"
EPOCH = 1_767_225_600
EXPECTED_ASSETS = {
    "install.ps1",
    "install.ps1.sha256",
    "install.sh",
    "install.sh.sha256",
    ARCHIVE,
    f"{ARCHIVE}.sha256",
}
CHECKSUM = re.compile(rb"([0-9a-f]{64})  ([A-Za-z0-9_.-]+)\n")
_REVIEWED_IMMUTABLE_RELEASE_COMMITS = {
    "preview-0.6": "db8e00d747d49039b3c225e8c0646806445c6346",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def immutable_release_tag_commit() -> str | None:
    expected = _REVIEWED_IMMUTABLE_RELEASE_COMMITS.get(RELEASE)
    if expected is None:
        return None
    resolved = subprocess.run(
        ["git", "rev-parse", "--verify", f"refs/tags/{RELEASE}^{{commit}}"],
        cwd=REPOSITORY,
        text=True,
        capture_output=True,
        check=False,
    )
    if resolved.returncode:
        raise AssertionError(f"missing reviewed immutable {RELEASE} tag: {resolved.stderr}")
    actual = resolved.stdout.strip()
    if actual != expected:
        raise AssertionError(
            f"reviewed immutable {RELEASE} tag resolves to {actual}, expected {expected}"
        )
    return actual


def immutable_release_tag_exists() -> bool:
    return immutable_release_tag_commit() is not None


def extract_tagged_release(destination: Path) -> Path:
    """Materialize the current immutable release source, never the mutable candidate."""
    tag_sha = immutable_release_tag_commit()
    if tag_sha is None:
        raise AssertionError(f"{RELEASE} is not a reviewed immutable release")
    ancestry = subprocess.run(
        ["git", "merge-base", "--is-ancestor", tag_sha, "HEAD"],
        cwd=REPOSITORY,
        text=True,
        capture_output=True,
        check=False,
    )
    if ancestry.returncode:
        raise AssertionError(f"immutable {RELEASE} tag is not an ancestor of HEAD")
    archive = subprocess.run(
        ["git", "archive", "--format=tar", tag_sha],
        cwd=REPOSITORY,
        capture_output=True,
        check=False,
    )
    if archive.returncode:
        raise AssertionError(
            f"could not archive immutable {RELEASE} source: {archive.stderr.decode()}"
        )
    with tarfile.open(fileobj=io.BytesIO(archive.stdout), mode="r:") as bundle:
        # Python 3.11.4 backported the safe extraction-filter API. The archive is
        # produced locally by `git archive` from the verified immutable commit.
        if sys.version_info >= (3, 11, 4):
            bundle.extractall(destination, filter="data")
        else:
            bundle.extractall(destination)
    return destination


def published_release_source(destination: Path) -> Path:
    """Use immutable bytes once published; otherwise test the fresh release candidate."""
    return extract_tagged_release(destination) if immutable_release_tag_exists() else REPOSITORY


def posix_path(path: Path) -> str:
    if os.name != "nt":
        return str(path)
    resolved = path.resolve().as_posix()
    if len(resolved) < 3 or resolved[1:3] != ":/":
        raise unittest.SkipTest("a drive-backed WSL path is required")
    return f"/mnt/{resolved[0].lower()}/{resolved[3:]}"


def release_builder_module() -> object:
    specification = importlib.util.spec_from_file_location("academy_release_builder", BUILDER)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


class ReleaseAssetBuilderTests(unittest.TestCase):
    def test_current_immutable_tag_is_bound_to_its_reviewed_commit(self) -> None:
        """A same-named branch or retargeted tag cannot stand in for Preview 0.6."""
        self.assertEqual(
            immutable_release_tag_commit(),
            "db8e00d747d49039b3c225e8c0646806445c6346",
        )

    def test_immutable_tag_resolution_uses_the_tag_namespace(self) -> None:
        """A branch named like the release never participates in release-source selection."""
        expected = "db8e00d747d49039b3c225e8c0646806445c6346"
        with patch("tests.test_release_assets.subprocess.run") as run:
            run.return_value = subprocess.CompletedProcess([], 0, f"{expected}\n", "")
            self.assertEqual(immutable_release_tag_commit(), expected)
        self.assertEqual(
            run.call_args.args[0],
            ["git", "rev-parse", "--verify", "refs/tags/preview-0.6^{commit}"],
        )

    def test_immutable_tag_resolution_rejects_missing_or_retargeted_tag(self) -> None:
        """Published Preview 0.6 fails closed rather than accepting a replacement ref."""
        with self.subTest(case="missing"), patch("tests.test_release_assets.subprocess.run") as run:
            run.return_value = subprocess.CompletedProcess([], 1, "", "not found")
            with self.assertRaisesRegex(AssertionError, "missing reviewed immutable"):
                immutable_release_tag_commit()
        with self.subTest(case="retargeted"), patch("tests.test_release_assets.subprocess.run") as run:
            run.return_value = subprocess.CompletedProcess([], 0, "0" * 40 + "\n", "")
            with self.assertRaisesRegex(AssertionError, "resolves to"):
                immutable_release_tag_commit()

    def test_extract_tagged_release_uses_the_python_3_11_compatible_extraction_path(self) -> None:
        """The declared Python 3.11 floor includes releases before tar's data filter backport."""
        archive = unittest.mock.MagicMock()
        archive.__enter__.return_value = archive
        destination = Path("release-source")
        with (
            patch("tests.test_release_assets.immutable_release_tag_commit", return_value="a" * 40),
            patch(
                "tests.test_release_assets.subprocess.run",
                side_effect=(
                    subprocess.CompletedProcess([], 0, "", ""),
                    subprocess.CompletedProcess([], 0, b"archive", b""),
                ),
            ),
            patch("tests.test_release_assets.tarfile.open", return_value=archive),
            patch("tests.test_release_assets.sys.version_info", (3, 11, 3)),
        ):
            self.assertEqual(extract_tagged_release(destination), destination)
        archive.extractall.assert_called_once_with(destination)

    def test_fresh_preview_uses_its_candidate_source_until_the_immutable_tag_exists(self) -> None:
        """A new public route still needs candidate bytes before its tag can be published."""
        global RELEASE
        previous_release = RELEASE
        RELEASE = "preview-9.9"
        try:
            with tempfile.TemporaryDirectory() as temporary_directory:
                self.assertEqual(
                    published_release_source(Path(temporary_directory) / "source"),
                    REPOSITORY,
                )
        finally:
            RELEASE = previous_release

    def test_wheel_normalization_canonicalizes_backend_metadata_and_record(self) -> None:
        """Catches platform line endings leaking through a ZIP-only wheel normalization."""
        builder = release_builder_module()
        timestamp = (2026, 1, 1, 0, 0, 0)
        dist_info = "workshop_queue-0.1.0.dist-info"
        payload_members = {
            "academy_engine/__init__.py": b"VERSION = '0.1.0'\n",
            f"{dist_info}/METADATA": b"Metadata-Version: 2.4\nName: workshop-queue\n",
            f"{dist_info}/WHEEL": b"Wheel-Version: 1.0\nGenerator: setuptools\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
        }

        def raw_wheel(path: Path, metadata_newline: bytes, record_order: list[str]) -> None:
            members = dict(payload_members)
            members[f"{dist_info}/METADATA"] = members[f"{dist_info}/METADATA"].replace(b"\n", metadata_newline)
            record_rows = []
            for name in record_order:
                payload = members[name]
                digest = hashlib.sha256(payload).digest()
                encoded = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
                record_rows.append(f"{name},sha256={encoded},{len(payload)}")
            record_rows.append(f"{dist_info}/RECORD,,")
            members[f"{dist_info}/RECORD"] = (metadata_newline.decode("ascii").join(record_rows) + metadata_newline.decode("ascii")).encode("utf-8")
            with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for name in reversed(list(members)):
                    archive.writestr(name, members[name])

        with tempfile.TemporaryDirectory() as temporary_directory:
            scratch = Path(temporary_directory)
            first_raw, second_raw = scratch / "windows.whl", scratch / "linux.whl"
            first_normalized, second_normalized = scratch / "first.whl", scratch / "second.whl"
            member_order = sorted(payload_members)
            raw_wheel(first_raw, b"\r\n", list(reversed(member_order)))
            raw_wheel(second_raw, b"\n", member_order)

            builder._normalize_wheel(first_raw, first_normalized, timestamp)
            builder._normalize_wheel(second_raw, second_normalized, timestamp)

            self.assertEqual(first_normalized.read_bytes(), second_normalized.read_bytes())
            with zipfile.ZipFile(first_normalized) as archive:
                members = {info.filename: archive.read(info) for info in archive.infolist()}
            self.assertEqual(members[f"{dist_info}/METADATA"], payload_members[f"{dist_info}/METADATA"])
            record_name = f"{dist_info}/RECORD"
            expected_rows = []
            for name in sorted(members):
                if name == record_name:
                    expected_rows.append(f"{name},,")
                    continue
                digest = base64.urlsafe_b64encode(hashlib.sha256(members[name]).digest()).rstrip(b"=").decode("ascii")
                expected_rows.append(f"{name},sha256={digest},{len(members[name])}")
            self.assertEqual(members[record_name], ("\n".join(expected_rows) + "\n").encode("utf-8"))

    def test_canonical_archives_use_runtime_independent_stored_members(self) -> None:
        """Catches zlib or interpreter versions changing canonical release bytes."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            source = published_release_source(Path(temporary_directory) / "source")
            output = Path(temporary_directory) / "output"
            output.mkdir()
            result = subprocess.run(
                [
                    sys.executable,
                    str(source / "scripts" / "build_release_assets.py"),
                    "--source", str(source),
                    "--output", str(output),
                    "--epoch", str(EPOCH),
                    "--release", RELEASE,
                ],
                cwd=REPOSITORY, text=True, capture_output=True, check=False, timeout=600,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            archives = [output / ARCHIVE]
            with zipfile.ZipFile(output / ARCHIVE) as bundle:
                wheel = Path(temporary_directory) / "academy.whl"
                wheel.write_bytes(bundle.read("wheelhouse/workshop_queue-0.1.0-py3-none-any.whl"))
                archives.append(wheel)
            for archive_path in archives:
                with self.subTest(archive=archive_path.name), zipfile.ZipFile(archive_path) as archive:
                    self.assertTrue(archive.infolist())
                    self.assertEqual(
                        {info.compress_type for info in archive.infolist()},
                        {zipfile.ZIP_STORED},
                    )

    def test_two_isolated_builds_are_canonical_and_byte_identical(self) -> None:
        """Catches host metadata, order, or undeclared files changing release bytes."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            scratch = Path(temporary_directory)
            source = published_release_source(scratch / "source")
            outputs = (scratch / "first", scratch / "second")
            for output in outputs:
                output.mkdir()
                result = subprocess.run(
                    [
                        sys.executable,
                        str(source / "scripts" / "build_release_assets.py"),
                        "--source",
                        str(source),
                        "--output",
                        str(output),
                        "--epoch",
                        str(EPOCH),
                        "--release",
                        RELEASE,
                    ],
                    cwd=REPOSITORY,
                    text=True,
                    capture_output=True,
                    check=False,
                    timeout=600,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual({path.name for path in output.iterdir()}, EXPECTED_ASSETS)

            for name in EXPECTED_ASSETS:
                self.assertEqual((outputs[0] / name).read_bytes(), (outputs[1] / name).read_bytes(), name)

            for target in ("install.ps1", "install.sh", ARCHIVE):
                checksum_path = outputs[0] / f"{target}.sha256"
                match = CHECKSUM.fullmatch(checksum_path.read_bytes())
                self.assertIsNotNone(match, checksum_path.name)
                assert match is not None
                self.assertEqual(match.group(2).decode("ascii"), target)
                self.assertEqual(match.group(1).decode("ascii"), sha256(outputs[0] / target))

            bundle = outputs[0] / ARCHIVE
            with zipfile.ZipFile(bundle) as archive:
                names = archive.namelist()
                self.assertEqual(names, sorted(names))
                self.assertEqual(
                    names,
                    [
                        "bundle-manifest.json",
                        "wheelhouse/workshop_queue-0.1.0-py3-none-any.whl",
                    ],
                )
                self.assertNotIn("install.ps1", "\n".join(names))
                self.assertNotIn("install.sh", "\n".join(names))
                for info in archive.infolist():
                    self.assertEqual(info.date_time, (2026, 1, 1, 0, 0, 0), info.filename)
                    self.assertEqual((info.external_attr >> 16) & 0o777, 0o644, info.filename)
                manifest_bytes = archive.read("bundle-manifest.json")
                wheel_bytes = archive.read("wheelhouse/workshop_queue-0.1.0-py3-none-any.whl")

            manifest = json.loads(manifest_bytes)
            self.assertEqual(
                manifest,
                {
                    "format_version": 1,
                    "release": RELEASE,
                    "wheelhouse": [
                        {
                            "filename": "workshop_queue-0.1.0-py3-none-any.whl",
                            "sha256": hashlib.sha256(wheel_bytes).hexdigest(),
                            "size": len(wheel_bytes),
                        }
                    ],
                },
            )
            self.assertEqual(
                manifest_bytes,
                json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n",
            )

            with zipfile.ZipFile(Path(outputs[1] / ARCHIVE)) as second:
                self.assertEqual(
                    wheel_bytes,
                    second.read("wheelhouse/workshop_queue-0.1.0-py3-none-any.whl"),
                )

    def test_builder_rejects_a_nonempty_output_without_touching_it(self) -> None:
        """Catches release files being mixed with stale or undeclared upload bytes."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory)
            marker = output / "keep.txt"
            marker.write_bytes(b"existing\n")
            result = subprocess.run(
                [
                    sys.executable,
                    str(BUILDER),
                    "--source",
                    str(REPOSITORY),
                    "--output",
                    str(output),
                    "--epoch",
                    str(EPOCH),
                    "--release",
                    RELEASE,
                ],
                text=True,
                capture_output=True,
                check=False,
                timeout=30,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("existing empty directory", result.stderr)
            self.assertEqual({path.name for path in output.iterdir()}, {"keep.txt"})
            self.assertEqual(marker.read_bytes(), b"existing\n")

    def test_builder_failure_leaves_the_required_empty_output_empty(self) -> None:
        """Catches a failed digest/source binding leaking a partial publication set."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory)
            result = subprocess.run(
                [
                    sys.executable,
                    str(BUILDER),
                    "--source",
                    str(REPOSITORY),
                    "--output",
                    str(output),
                    "--epoch",
                    str(EPOCH),
                    "--release",
                    "preview-9.9",
                ],
                text=True,
                capture_output=True,
                check=False,
                timeout=600,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("does not embed the final bundle digest", result.stderr)
            self.assertEqual(list(output.iterdir()), [])

    def test_builder_rejects_an_out_of_range_epoch_without_a_traceback(self) -> None:
        """Catches hostile or mistaken epoch input escaping the fail-closed CLI contract."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory)
            result = subprocess.run(
                [
                    sys.executable,
                    str(BUILDER),
                    "--source",
                    str(REPOSITORY),
                    "--output",
                    str(output),
                    "--epoch",
                    str(10**30),
                    "--release",
                    RELEASE,
                ],
                text=True,
                capture_output=True,
                check=False,
                timeout=30,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("ZIP-supported UTC year", result.stderr)
            self.assertNotIn("Traceback", result.stderr)
            self.assertEqual(list(output.iterdir()), [])


class InstallerSourceContractTests(unittest.TestCase):
    def test_published_release_source_remains_the_immutable_tag_when_private_content_changes(self) -> None:
        """Private, nonroutable lesson work must not retarget Preview 0.6 installer evidence."""
        if not immutable_release_tag_exists():
            self.skipTest("the current preview has not been published yet")
        with tempfile.TemporaryDirectory() as temporary_directory:
            scratch = Path(temporary_directory)
            release_source = extract_tagged_release(scratch / "release-source")
            candidate = scratch / "candidate"
            shutil.copytree(REPOSITORY, candidate, ignore=shutil.ignore_patterns(".git", "__pycache__"))
            candidate_guide = candidate / "academy/tracks/practitioner/P01-feature-through-plan.md"
            candidate_guide.write_text(
                candidate_guide.read_text(encoding="utf-8") + "\nPrivate candidate edit.\n",
                encoding="utf-8",
            )

            self.assertNotEqual(
                candidate_guide.read_bytes(),
                (release_source / "academy/tracks/practitioner/P01-feature-through-plan.md").read_bytes(),
            )
            self.assertEqual(
                (release_source / "academy/publication/preview-0.6.json").read_bytes(),
                (REPOSITORY / "academy/publication/preview-0.6.json").read_bytes(),
            )
            manifest = json.loads((candidate / "academy/publication/preview-0.6.json").read_text(encoding="utf-8"))
            self.assertNotIn("P01-feature-through-plan", manifest["available_labs"])

            candidate_output = scratch / "candidate-assets"
            candidate_output.mkdir()
            candidate_build = subprocess.run(
                [
                    sys.executable,
                    str(candidate / "scripts" / "build_release_assets.py"),
                    "--source",
                    str(candidate),
                    "--output",
                    str(candidate_output),
                    "--epoch",
                    str(EPOCH),
                    "--release",
                    RELEASE,
                ],
                cwd=candidate,
                text=True,
                capture_output=True,
                check=False,
                timeout=600,
            )
            self.assertNotEqual(candidate_build.returncode, 0)
            self.assertIn("does not embed the final bundle digest", candidate_build.stderr)

            release_output = scratch / "release-assets"
            release_output.mkdir()
            release_build = subprocess.run(
                [
                    sys.executable,
                    str(release_source / "scripts" / "build_release_assets.py"),
                    "--source",
                    str(release_source),
                    "--output",
                    str(release_output),
                    "--epoch",
                    str(EPOCH),
                    "--release",
                    RELEASE,
                ],
                cwd=release_source,
                text=True,
                capture_output=True,
                check=False,
                timeout=600,
            )
            self.assertEqual(release_build.returncode, 0, release_build.stdout + release_build.stderr)

    def test_tracked_installers_and_checksums_are_the_canonical_upload_bytes(self) -> None:
        """Catches publishing installer bytes that were not the reviewed tracked bytes."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            source = published_release_source(Path(temporary_directory) / "source")
            output = Path(temporary_directory) / "assets"
            output.mkdir()
            result = subprocess.run(
                [
                    sys.executable,
                    str(source / "scripts" / "build_release_assets.py"),
                    "--source",
                    str(source),
                    "--output",
                    str(output),
                    "--epoch",
                    str(EPOCH),
                    "--release",
                    RELEASE,
                ],
                cwd=REPOSITORY,
                text=True,
                capture_output=True,
                check=False,
                timeout=600,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            bundle_digest = sha256(output / ARCHIVE)
            for name in ("install.ps1", "install.sh"):
                tracked = source / "install" / name
                tracked_checksum = source / "install" / f"{name}.sha256"
                self.assertEqual(tracked.read_bytes(), (output / name).read_bytes(), name)
                self.assertEqual(tracked_checksum.read_bytes(), (output / f"{name}.sha256").read_bytes(), name)
                self.assertIn(bundle_digest.encode("ascii"), tracked.read_bytes(), name)

    def test_installer_source_review_has_pinned_offline_fail_closed_contract(self) -> None:
        """Catches mutable downloads, command injection, or package-index installation."""
        immutable_url = (
            "https://github.com/arbiterForge/arbiter-academy/releases/download/"
            f"{RELEASE}/{ARCHIVE}"
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            release_source = published_release_source(Path(temporary_directory) / "source")
            for name in ("install.ps1", "install.sh"):
                source = (release_source / "install" / name).read_text(encoding="utf-8")
                self.assertIn(immutable_url, source, name)
                self.assertIn("--no-index", source, name)
                self.assertIn("--no-deps", source, name)
                self.assertIn("bundle-manifest.json", source, name)
                self.assertIn("install-manifest.json", source, name)
                self.assertIn("doctor", source, name)
                self.assertIn("release-assets.githubusercontent.com", source, name)
                self.assertNotIn("raw.githubusercontent.com", source, name)
                self.assertNotRegex(source, r"/(?:refs/heads/|main/|master/)")
                self.assertNotRegex(source, r"(?i)(?:invoke-expression|\biex\b|\beval\b)")
            powershell = (release_source / "install" / "install.ps1").read_text(encoding="utf-8")
            posix = (release_source / "install" / "install.sh").read_text(encoding="utf-8")
        self.assertIn("AllowAutoRedirect = $false", powershell)
        self.assertIn("--proto '=https'", posix)
        self.assertNotIn("--location", posix)

    def test_powershell_http_client_loads_explicitly_without_overriding_system_tls_policy(self) -> None:
        """Catches Windows PowerShell 5.1 failing type resolution or a global TLS downgrade."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            release_source = published_release_source(Path(temporary_directory) / "source")
            source = (release_source / "install" / "install.ps1").read_text(encoding="utf-8")
        assembly_load = source.index("Add-Type -AssemblyName System.Net.Http")
        client_construction = source.index("New-Object Net.Http.HttpClientHandler")
        self.assertLess(assembly_load, client_construction)
        self.assertNotRegex(
            source,
            r"(?im)^\s*\[Net\.ServicePointManager\]::SecurityProtocol\s*=",
        )


class InstallerBehaviorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        cls.scratch = Path(cls.temporary.name)
        cls.release_source = published_release_source(cls.scratch / "source")
        cls.assets = cls.scratch / "assets"
        cls.assets.mkdir()
        result = subprocess.run(
            [
                sys.executable,
                str(cls.release_source / "scripts" / "build_release_assets.py"),
                "--source",
                str(cls.release_source),
                "--output",
                str(cls.assets),
                "--epoch",
                str(EPOCH),
                "--release",
                RELEASE,
            ],
            cwd=cls.release_source,
            text=True,
            capture_output=True,
            check=False,
            timeout=600,
        )
        if result.returncode:
            raise AssertionError(result.stdout + result.stderr)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def test_powershell_rejects_and_preserves_an_unowned_install_path(self) -> None:
        """Catches an installer overwriting files it did not create and own."""
        powershell = shutil.which("powershell") or shutil.which("pwsh")
        if powershell is None or os.name != "nt":
            self.skipTest("Windows PowerShell is required")
        local_app_data = self.scratch / "powershell-conflict"
        destination = local_app_data / "ArbiterAcademy" / RELEASE
        destination.mkdir(parents=True)
        intruder = destination / "keep.txt"
        intruder.write_bytes(b"unowned\n")
        environment = os.environ.copy()
        environment["LOCALAPPDATA"] = str(local_app_data)
        result = subprocess.run(
            [
                powershell,
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(self.assets / "install.ps1"),
                "-BundlePath",
                str(self.assets / ARCHIVE),
            ],
            cwd=REPOSITORY,
            env=environment,
            text=True,
            capture_output=True,
            check=False,
            timeout=120,
        )
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("conflicting or unowned install path", result.stderr)
        self.assertEqual(intruder.read_bytes(), b"unowned\n")
        self.assertEqual({path.name for path in destination.iterdir()}, {"keep.txt"})

    def test_powershell_rejects_a_preexisting_academy_root_junction(self) -> None:
        """Catches installer writes escaping through an Academy-root junction."""
        powershell = shutil.which("powershell") or shutil.which("pwsh")
        if powershell is None or os.name != "nt":
            self.skipTest("Windows PowerShell with junction support is required")
        local_app_data = self.scratch / "powershell-root-junction"
        local_app_data.mkdir()
        external = self.scratch / "powershell-root-external"
        external.mkdir()
        sentinel = external / "keep.txt"
        sentinel.write_bytes(b"outside\n")
        junction = local_app_data / "ArbiterAcademy"
        created = subprocess.run(
            [
                powershell,
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                "& { param($link, $target) New-Item -ItemType Junction -Path $link -Target $target | Out-Null }",
                str(junction),
                str(external),
            ],
            text=True,
            capture_output=True,
            check=False,
            timeout=30,
        )
        self.assertEqual(created.returncode, 0, created.stdout + created.stderr)
        tampered = self.scratch / "junction-tampered.zip"
        tampered.write_bytes(b"not the reviewed bundle")
        environment = os.environ.copy()
        environment["LOCALAPPDATA"] = str(local_app_data)
        result = subprocess.run(
            [
                powershell,
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(self.assets / "install.ps1"),
                "-BundlePath",
                str(tampered),
            ],
            cwd=REPOSITORY,
            env=environment,
            text=True,
            capture_output=True,
            check=False,
            timeout=60,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Academy tools directory cannot be a reparse point", result.stdout + result.stderr)
        self.assertEqual(sentinel.read_bytes(), b"outside\n")
        self.assertEqual({path.name for path in external.iterdir()}, {"keep.txt"})
        self.assertTrue(junction.exists())
        os.rmdir(junction)

    def test_posix_rejects_and_preserves_an_unowned_install_path(self) -> None:
        """Catches the POSIX installer overwriting files it did not create and own."""
        bash = shutil.which("bash")
        if bash is None:
            self.skipTest("a POSIX shell is required")
        data_home = self.scratch / "posix-conflict"
        destination = data_home / "arbiter-academy" / RELEASE
        destination.mkdir(parents=True)
        intruder = destination / "keep.txt"
        intruder.write_bytes(b"unowned\n")
        command = (
            f"export XDG_DATA_HOME={shlex.quote(posix_path(data_home))}; "
            f"sh {shlex.quote(posix_path(self.assets / 'install.sh'))} "
            f"--bundle {shlex.quote(posix_path(self.assets / ARCHIVE))}"
        )
        result = subprocess.run(
            [bash, "-lc", command],
            cwd=REPOSITORY,
            text=True,
            capture_output=True,
            check=False,
            timeout=120,
        )
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("conflicting or unowned install path", result.stderr)
        self.assertEqual(intruder.read_bytes(), b"unowned\n")
        self.assertEqual({path.name for path in destination.iterdir()}, {"keep.txt"})

    def test_powershell_installs_only_manifest_owned_paths_and_runs_doctor(self) -> None:
        """Catches online resolution, undeclared writes, or omitting the final Doctor invocation."""
        powershell = shutil.which("powershell") or shutil.which("pwsh")
        if powershell is None or os.name != "nt":
            self.skipTest("Windows PowerShell is required")
        local_app_data = self.scratch / "powershell-success"
        environment = os.environ.copy()
        environment["LOCALAPPDATA"] = str(local_app_data)
        environment["PIP_INDEX_URL"] = "https://index.invalid/must-not-be-used"
        result = subprocess.run(
            [
                powershell,
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(self.assets / "install.ps1"),
                "-BundlePath",
                str(self.assets / ARCHIVE),
            ],
            cwd=REPOSITORY,
            env=environment,
            text=True,
            capture_output=True,
            check=False,
            timeout=300,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(f"Installed Arbiter Academy {RELEASE}", result.stdout)
        self.assertRegex(result.stdout, r"Academy Doctor|Repository|Git")
        install_root = local_app_data / "ArbiterAcademy" / RELEASE
        manifest_path = install_root / "install-manifest.json"
        manifest_bytes = manifest_path.read_bytes()
        manifest = json.loads(manifest_bytes)
        self.assertEqual(manifest["release"], RELEASE)
        self.assertEqual(manifest["bundle_sha256"], sha256(self.assets / ARCHIVE))
        self.assertEqual(manifest["executable"], "Scripts/arbiter-academy.exe")
        actual = {
            path.relative_to(install_root).as_posix()
            for path in install_root.rglob("*")
        }
        self.assertEqual(set(manifest["owned_paths"]), actual)
        self.assertFalse(any(path.name.startswith(f".{RELEASE}-") for path in install_root.parent.iterdir()))

    def test_posix_installs_only_manifest_owned_paths_and_runs_doctor(self) -> None:
        """Catches the POSIX path resolving packages online or leaving undeclared files."""
        bash = shutil.which("bash")
        if bash is None:
            self.skipTest("a POSIX shell is required")
        ensurepip = subprocess.run(
            [bash, "-lc", "python3 -c 'import ensurepip'"],
            text=True,
            capture_output=True,
            check=False,
            timeout=30,
        )
        path_prefix = ""
        if ensurepip.returncode:
            fake_bin = self.scratch / "posix-success-python"
            fake_bin.mkdir()
            real_python = subprocess.run(
                [bash, "-lc", "command -v python3"],
                text=True,
                capture_output=True,
                check=True,
            ).stdout.strip()
            fake_python = fake_bin / "python3"
            fake_python.write_bytes((
                "#!/bin/sh\n"
                "if [ \"${1:-}\" = -m ] && [ \"${2:-}\" = venv ]; then\n"
                "  destination=$4\n"
                "  mkdir -p -- \"$destination/bin\"\n"
                "  cat >\"$destination/bin/python\" <<'VENV'\n"
                "#!/bin/sh\n"
                "case \" $* \" in *' --no-index '* ) ;; *) exit 91;; esac\n"
                "case \" $* \" in *' --no-deps '* ) ;; *) exit 92;; esac\n"
                "case \" $* \" in *' --find-links '* ) ;; *) exit 93;; esac\n"
                "root=$(CDPATH= cd -- \"$(dirname -- \"$0\")/..\" && pwd)\n"
                "cat >\"$root/bin/arbiter-academy\" <<'ACADEMY'\n"
                "#!/bin/sh\n"
                "printf 'Academy Doctor hermetic offline fixture\\n'\n"
                "exit 0\n"
                "ACADEMY\n"
                "chmod 700 \"$root/bin/arbiter-academy\"\n"
                "exit 0\n"
                "VENV\n"
                "  chmod 700 \"$destination/bin/python\"\n"
                "  exit 0\n"
                "fi\n"
                f"exec {shlex.quote(real_python)} \"$@\"\n"
            ).encode("utf-8"))
            path_prefix = (
                f"chmod 700 {shlex.quote(posix_path(fake_python))}; "
                f"export PATH={shlex.quote(posix_path(fake_bin))}:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin; "
            )
        data_home = self.scratch / "posix-success"
        command = path_prefix + (
            f"export XDG_DATA_HOME={shlex.quote(posix_path(data_home))}; "
            "export PIP_INDEX_URL=https://index.invalid/must-not-be-used; "
            f"sh {shlex.quote(posix_path(self.assets / 'install.sh'))} "
            f"--bundle {shlex.quote(posix_path(self.assets / ARCHIVE))}"
        )
        result = subprocess.run(
            [bash, "-lc", command],
            cwd=REPOSITORY,
            text=True,
            capture_output=True,
            check=False,
            timeout=300,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(f"Installed Arbiter Academy {RELEASE}", result.stdout)
        self.assertRegex(result.stdout, r"Academy Doctor|Repository|Git")
        install_root = data_home / "arbiter-academy" / RELEASE
        manifest_path = install_root / "install-manifest.json"
        manifest_bytes = manifest_path.read_bytes()
        manifest = json.loads(manifest_bytes)
        self.assertEqual(
            manifest_bytes,
            json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode() + b"\n",
        )
        self.assertEqual(manifest["release"], RELEASE)
        self.assertEqual(manifest["bundle_sha256"], sha256(self.assets / ARCHIVE))
        self.assertEqual(manifest["executable"], "bin/arbiter-academy")
        actual = {
            path.relative_to(install_root).as_posix()
            for path in install_root.rglob("*")
        }
        self.assertEqual(set(manifest["owned_paths"]), actual)
        self.assertFalse(any(path.name.startswith(f".{RELEASE}-") for path in install_root.parent.iterdir()))

    @unittest.skipIf(os.name == "nt", "POSIX venv symlink behavior")
    def test_posix_installer_accepts_its_owned_internal_venv_symlink(self) -> None:
        """Catches rejecting the in-root compatibility links made by a successful POSIX venv."""
        bash = shutil.which("bash")
        if bash is None:
            self.skipTest("a POSIX shell is required")
        fake_bin = self.scratch / "posix-owned-venv-link-python"
        fake_bin.mkdir()
        real_python = subprocess.run(
            [bash, "-lc", "command -v python3"], text=True, capture_output=True, check=True
        ).stdout.strip()
        fake_python = fake_bin / "python3"
        fake_python.write_bytes((
            "#!/bin/sh\n"
            "if [ \"${1:-}\" = -m ] && [ \"${2:-}\" = venv ]; then\n"
            f"  {shlex.quote(real_python)} \"$@\"\n"
            "  destination=${4:?expected venv destination}\n"
            "  if [ ! -e \"$destination/lib64\" ] && [ ! -L \"$destination/lib64\" ]; then\n"
            "    ln -s -- lib \"$destination/lib64\"\n"
            "  fi\n"
            "  exit 0\n"
            "fi\n"
            f"exec {shlex.quote(real_python)} \"$@\"\n"
        ).encode("utf-8"))
        data_home = self.scratch / "posix-owned-venv-link"
        controlled_path = (
            f"{posix_path(fake_bin)}:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
        )
        command = (
            f"chmod 700 {shlex.quote(posix_path(fake_python))}; "
            f"PATH={shlex.quote(controlled_path)} XDG_DATA_HOME={shlex.quote(posix_path(data_home))} "
            f"sh {shlex.quote(posix_path(self.assets / 'install.sh'))} "
            f"--bundle {shlex.quote(posix_path(self.assets / ARCHIVE))}"
        )
        result = subprocess.run(
            [bash, "-lc", command],
            cwd=REPOSITORY,
            text=True,
            capture_output=True,
            check=False,
            timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        install_root = data_home / "arbiter-academy" / RELEASE
        self.assertTrue((install_root / "lib64").is_symlink())
        manifest = json.loads((install_root / "install-manifest.json").read_text(encoding="utf-8"))
        self.assertIn("lib64", manifest["owned_paths"])

    @unittest.skipIf(os.name == "nt", "POSIX venv symlink behavior")
    def test_posix_installer_rejects_an_external_venv_symlink(self) -> None:
        """Catches treating a venv-created link to data outside the owned root as installed content."""
        bash = shutil.which("bash")
        if bash is None:
            self.skipTest("a POSIX shell is required")
        external = self.scratch / "posix-external-venv-link-target"
        external.mkdir()
        sentinel = external / "keep.txt"
        sentinel.write_bytes(b"outside\n")
        fake_bin = self.scratch / "posix-external-venv-link-python"
        fake_bin.mkdir()
        real_python = subprocess.run(
            [bash, "-lc", "command -v python3"], text=True, capture_output=True, check=True
        ).stdout.strip()
        fake_python = fake_bin / "python3"
        fake_python.write_bytes((
            "#!/bin/sh\n"
            "if [ \"${1:-}\" = -m ] && [ \"${2:-}\" = venv ]; then\n"
            f"  {shlex.quote(real_python)} \"$@\"\n"
            "  destination=${4:?expected venv destination}\n"
            "  rm -f -- \"$destination/lib64\"\n"
            f"  ln -s -- {shlex.quote(posix_path(external))} \"$destination/lib64\"\n"
            "  exit 0\n"
            "fi\n"
            f"exec {shlex.quote(real_python)} \"$@\"\n"
        ).encode("utf-8"))
        data_home = self.scratch / "posix-external-venv-link"
        controlled_path = (
            f"{posix_path(fake_bin)}:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
        )
        command = (
            f"chmod 700 {shlex.quote(posix_path(fake_python))}; "
            f"PATH={shlex.quote(controlled_path)} XDG_DATA_HOME={shlex.quote(posix_path(data_home))} "
            f"sh {shlex.quote(posix_path(self.assets / 'install.sh'))} "
            f"--bundle {shlex.quote(posix_path(self.assets / ARCHIVE))}"
        )
        result = subprocess.run(
            [bash, "-lc", command],
            cwd=REPOSITORY,
            text=True,
            capture_output=True,
            check=False,
            timeout=60,
        )
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("symbolic link", result.stdout + result.stderr)
        self.assertEqual(sentinel.read_bytes(), b"outside\n")

    def test_powershell_rolls_back_a_partial_owned_environment(self) -> None:
        """Catches a failed venv build leaving an installer-owned partial path behind."""
        powershell = shutil.which("powershell") or shutil.which("pwsh")
        if powershell is None or os.name != "nt":
            self.skipTest("Windows PowerShell is required")
        fake_bin = self.scratch / "powershell-fake-python"
        fake_bin.mkdir()
        fake_python = fake_bin / "python.cmd"
        fake_python.write_text(
            "@echo off\r\nmkdir \"%~4\"\r\necho partial>\"%~4\\partial.txt\"\r\nexit /b 19\r\n",
            encoding="ascii",
        )
        local_app_data = self.scratch / "powershell-rollback"
        environment = os.environ.copy()
        environment["LOCALAPPDATA"] = str(local_app_data)
        environment["PATH"] = str(fake_bin) + os.pathsep + environment["PATH"]
        result = subprocess.run(
            [
                powershell,
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(self.assets / "install.ps1"),
                "-BundlePath",
                str(self.assets / ARCHIVE),
            ],
            cwd=REPOSITORY,
            env=environment,
            text=True,
            capture_output=True,
            check=False,
            timeout=120,
        )
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Python failed to create", result.stderr)
        academy_root = local_app_data / "ArbiterAcademy"
        self.assertFalse((academy_root / RELEASE).exists())
        self.assertFalse(academy_root.exists())

    def test_posix_rolls_back_a_partial_owned_environment(self) -> None:
        """Catches a failed POSIX venv build leaving an installer-owned partial path behind."""
        bash = shutil.which("bash")
        if bash is None:
            self.skipTest("a POSIX shell is required")
        data_home = self.scratch / "posix-rollback"
        fake_bin = self.scratch / "posix-fake-python"
        fake_bin.mkdir()
        real_python = subprocess.run(
            [bash, "-lc", "command -v python3"],
            text=True,
            capture_output=True,
            check=True,
        ).stdout.strip()
        fake_python = fake_bin / "python3"
        fake_python.write_bytes((
            "#!/bin/sh\n"
            "if [ \"${1:-}\" = -m ] && [ \"${2:-}\" = venv ]; then\n"
            "  mkdir -p -- \"$4\"\n"
            "  printf partial >\"$4/partial.txt\"\n"
            "  exit 19\n"
            "fi\n"
            f"exec {shlex.quote(real_python)} \"$@\"\n"
        ).encode("utf-8"))
        command = (
            f"chmod 700 {shlex.quote(posix_path(fake_python))}; "
            f"export PATH={shlex.quote(posix_path(fake_bin))}:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin; "
            f"export XDG_DATA_HOME={shlex.quote(posix_path(data_home))}; "
            f"sh {shlex.quote(posix_path(self.assets / 'install.sh'))} "
            f"--bundle {shlex.quote(posix_path(self.assets / ARCHIVE))}"
        )
        result = subprocess.run(
            [bash, "-lc", command],
            cwd=REPOSITORY,
            text=True,
            capture_output=True,
            check=False,
            timeout=120,
        )
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Python failed to create", result.stderr)
        academy_root = data_home / "arbiter-academy"
        self.assertFalse((academy_root / RELEASE).exists())
        self.assertFalse(academy_root.exists())

    def test_posix_rolls_back_when_interrupted_after_claiming_the_install_root(self) -> None:
        """Catches cleanup expanding an unset install marker during an ownership-window interrupt."""
        bash = shutil.which("bash")
        if bash is None:
            self.skipTest("a POSIX shell is required")
        interrupted_installer = self.scratch / "posix-interrupted-after-ownership.sh"
        source = (self.assets / "install.sh").read_text(encoding="utf-8")
        needle = "owns_install=1\n"
        self.assertIn(needle, source)
        interrupted_installer.write_text(
            source.replace(needle, "owns_install=1\nkill -TERM \"$$\"\n", 1),
            encoding="utf-8",
            newline="\n",
        )
        data_home = self.scratch / "posix-interrupted-after-ownership"
        command = (
            f"export XDG_DATA_HOME={shlex.quote(posix_path(data_home))}; "
            f"sh {shlex.quote(posix_path(interrupted_installer))} "
            f"--bundle {shlex.quote(posix_path(self.assets / ARCHIVE))}"
        )
        result = subprocess.run(
            [bash, "-lc", command],
            cwd=REPOSITORY,
            text=True,
            capture_output=True,
            check=False,
            timeout=120,
        )
        academy_root = data_home / "arbiter-academy"
        self.assertFalse((academy_root / RELEASE).exists(), result.stdout + result.stderr)
        self.assertFalse(academy_root.exists(), result.stdout + result.stderr)

    def test_powershell_preserves_a_substituted_install_root_on_rollback(self) -> None:
        """Catches a substitution after cleanup precheck escaping quarantine revalidation."""
        powershell = shutil.which("powershell") or shutil.which("pwsh")
        if powershell is None or os.name != "nt":
            self.skipTest("Windows PowerShell with junction support is required")
        fake_bin = self.scratch / "powershell-substitution-python"
        fake_bin.mkdir()
        fake_python = fake_bin / "python.cmd"
        fake_python.write_text(
            "@echo off\r\nexit /b 19\r\n",
            encoding="ascii",
        )
        external = self.scratch / "powershell-substitution-external"
        external.mkdir()
        sentinel = external / "keep.txt"
        sentinel.write_bytes(b"outside\n")
        local_app_data = self.scratch / "powershell-substitution-data"
        environment = os.environ.copy()
        environment["LOCALAPPDATA"] = str(local_app_data)
        environment["ATTACK_TARGET"] = str(external)
        environment["PATH"] = str(fake_bin) + os.pathsep + environment["PATH"]
        install_root = local_app_data / "ArbiterAcademy" / RELEASE
        attack_event = self.scratch / "powershell-quarantine-race.txt"
        environment["ATTACK_SOURCE"] = str(install_root)
        environment["ATTACK_EVENT"] = str(attack_event)
        harness = self.scratch / "powershell-quarantine-race.ps1"
        harness.write_text(
            "param([string]$Installer, [string]$Bundle)\n"
            "function Move-Item {\n"
            "  [CmdletBinding()] param([string]$LiteralPath, [string]$Destination)\n"
            "  if ($LiteralPath -ceq $env:ATTACK_SOURCE) {\n"
            "    Microsoft.PowerShell.Management\\Remove-Item -LiteralPath (Join-Path $LiteralPath '.academy-install-owner') -Force\n"
            "    Microsoft.PowerShell.Management\\Remove-Item -LiteralPath $LiteralPath -Force\n"
            "    New-Item -ItemType Junction -Path $LiteralPath -Target $env:ATTACK_TARGET | Out-Null\n"
            "    [IO.File]::WriteAllText($env:ATTACK_EVENT, 'fired')\n"
            "  }\n"
            "  Microsoft.PowerShell.Management\\Move-Item -LiteralPath $LiteralPath -Destination $Destination -ErrorAction Stop\n"
            "}\n"
            "& $Installer -BundlePath $Bundle\n",
            encoding="utf-8",
        )
        result = subprocess.run(
            [
                powershell,
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-File", str(harness),
                str(self.assets / "install.ps1"),
                str(self.assets / ARCHIVE),
            ],
            cwd=REPOSITORY,
            env=environment,
            text=True,
            capture_output=True,
            check=False,
            timeout=120,
        )
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("rollback ownership check failed", result.stdout + result.stderr)
        self.assertTrue(attack_event.is_file(), result.stdout + result.stderr)
        self.assertEqual(sentinel.read_bytes(), b"outside\n")
        quarantines = list((local_app_data / "ArbiterAcademy").glob(".academy-delete-*"))
        self.assertEqual(len(quarantines), 1, result.stdout + result.stderr)
        self.assertTrue(
            bool((quarantines[0].lstat().st_file_attributes or 0) & 0x400),
            "substituted install root must remain quarantined as a reparse point",
        )
        os.rmdir(quarantines[0])

    def test_posix_preserves_a_substituted_install_root_on_rollback(self) -> None:
        """Catches POSIX substitution after precheck escaping quarantine revalidation."""
        bash = shutil.which("bash")
        if bash is None:
            self.skipTest("a POSIX shell is required")
        data_home = self.scratch / "posix-substitution-data"
        external = self.scratch / "posix-substitution-external"
        external.mkdir()
        sentinel = external / "keep.txt"
        sentinel.write_bytes(b"outside\n")
        fake_bin = self.scratch / "posix-substitution-python"
        fake_bin.mkdir()
        real_python = subprocess.run(
            [bash, "-lc", "command -v python3"], text=True, capture_output=True, check=True
        ).stdout.strip()
        fake_python = fake_bin / "python3"
        fake_python.write_bytes((
            "#!/bin/sh\n"
            "if [ \"${1:-}\" = -m ] && [ \"${2:-}\" = venv ]; then\n"
            "  exit 19\n"
            "fi\n"
            f"exec {shlex.quote(real_python)} \"$@\"\n"
        ).encode("utf-8"))
        fake_mv = fake_bin / "mv"
        fake_mv.write_bytes((
            "#!/bin/sh\n"
            "printf 'arg1=%s arg2=%s arg3=%s\\n' \"${1:-}\" \"${2:-}\" \"${3:-}\" >>\"$ATTACK_EVENT\"\n"
            "case \"${2:-}\" in\n"
            "*/preview-0.6)\n"
            "  rm -f -- \"$2/.academy-install-owner\"\n"
            "  rmdir -- \"$2\"\n"
            "  ln -s -- \"$ATTACK_TARGET\" \"$2\"\n"
            "  printf 'fired\\n' >>\"$ATTACK_EVENT\"\n"
            "  ;;\n"
            "esac\n"
            "exec /usr/bin/mv \"$@\"\n"
        ).encode("utf-8"))
        controlled_path = f"{posix_path(fake_bin)}:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
        install_root_posix = f"{posix_path(data_home)}/arbiter-academy/{RELEASE}"
        command = (
            f"chmod 700 {shlex.quote(posix_path(fake_python))} {shlex.quote(posix_path(fake_mv))}; "
            f"PATH={shlex.quote(controlled_path)} XDG_DATA_HOME={shlex.quote(posix_path(data_home))} "
            f"ATTACK_TARGET={shlex.quote(posix_path(external))} "
            f"ATTACK_SOURCE={shlex.quote(install_root_posix)} "
            f"ATTACK_EVENT={shlex.quote(posix_path(self.scratch / 'posix-quarantine-race.txt'))} "
            f"sh {shlex.quote(posix_path(self.assets / 'install.sh'))} --bundle {shlex.quote(posix_path(self.assets / ARCHIVE))}"
        )
        result = subprocess.run(
            [bash, "-lc", command], cwd=REPOSITORY, text=True, capture_output=True,
            check=False, timeout=120,
        )
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        attack_event = self.scratch / "posix-quarantine-race.txt"
        details = result.stdout + result.stderr
        if attack_event.is_file():
            details += "\n" + attack_event.read_text(encoding="utf-8")
        self.assertIn("rollback ownership check failed", details)
        self.assertTrue(attack_event.is_file(), result.stdout + result.stderr)
        self.assertIn("fired", attack_event.read_text(encoding="utf-8"))
        quarantines = list((data_home / "arbiter-academy").glob(".academy-delete-*"))
        self.assertEqual(len(quarantines), 1, result.stdout + result.stderr)
        link_result = subprocess.run(
            [bash, "-lc", f"test -L {shlex.quote(posix_path(quarantines[0]))}"],
            check=False, capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(link_result.returncode, 0, link_result.stdout + link_result.stderr)
        self.assertEqual(sentinel.read_bytes(), b"outside\n")
        subprocess.run(
            [bash, "-lc", f"rm -- {shlex.quote(posix_path(quarantines[0]))}"],
            check=True, capture_output=True, text=True, timeout=30,
        )

    def test_powershell_redirect_validator_rejects_nondefault_https_ports(self) -> None:
        """Catches trusted-host redirects escaping through an attacker-selected port."""
        powershell = shutil.which("powershell") or shutil.which("pwsh")
        if powershell is None or os.name != "nt":
            self.skipTest("Windows PowerShell is required")
        harness = self.scratch / "redirect-validator.ps1"
        harness.write_text(
            "param([string]$Installer)\n"
            "$tokens = $null; $errors = $null\n"
            "$ast = [Management.Automation.Language.Parser]::ParseFile($Installer, [ref]$tokens, [ref]$errors)\n"
            "$function = $ast.Find({ param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Test-TrustedReleaseRedirect' }, $true)\n"
            "if ($null -eq $function) { throw 'missing redirect validator' }\n"
            ". ([ScriptBlock]::Create($function.Extent.Text))\n"
            "$github = [Uri]'https://github.com/arbiterForge/arbiter-academy/releases/download/preview-0.6/file.zip'\n"
            "$cdn = [Uri]'https://release-assets.githubusercontent.com/path?sig=x'\n"
            "$badPort = [Uri]'https://release-assets.githubusercontent.com:444/path?sig=x'\n"
            "$badHost = [Uri]'https://evil.example/path'\n"
            "$badScheme = [Uri]'http://release-assets.githubusercontent.com/path'\n"
            "if (-not (Test-TrustedReleaseRedirect $github $cdn)) { throw 'trusted redirect rejected' }\n"
            "foreach ($candidate in @($badPort, $badHost, $badScheme)) { if (Test-TrustedReleaseRedirect $github $candidate) { throw \"unsafe redirect accepted: $candidate\" } }\n",
            encoding="utf-8",
        )
        result = subprocess.run(
            [powershell, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(harness), str(self.assets / "install.ps1")],
            text=True, capture_output=True, check=False, timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_both_installers_verify_the_bundle_before_any_extraction(self) -> None:
        """Catches extraction or installation beginning before the pinned digest passes."""
        tampered = self.scratch / "tampered.zip"
        payload = bytearray((self.assets / ARCHIVE).read_bytes())
        payload[len(payload) // 2] ^= 1
        tampered.write_bytes(payload)

        powershell = shutil.which("powershell") or shutil.which("pwsh")
        if powershell is not None and os.name == "nt":
            local_app_data = self.scratch / "powershell-tampered"
            environment = os.environ.copy()
            environment["LOCALAPPDATA"] = str(local_app_data)
            result = subprocess.run(
                [powershell, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(self.assets / "install.ps1"), "-BundlePath", str(tampered)],
                cwd=REPOSITORY,
                env=environment,
                text=True,
                capture_output=True,
                check=False,
                timeout=60,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("extraction was not attempted", result.stderr)
            self.assertFalse((local_app_data / "ArbiterAcademy").exists())

        bash = shutil.which("bash")
        if bash is not None:
            data_home = self.scratch / "posix-tampered"
            command = (
                f"export XDG_DATA_HOME={shlex.quote(posix_path(data_home))}; "
                f"sh {shlex.quote(posix_path(self.assets / 'install.sh'))} --bundle {shlex.quote(posix_path(tampered))}"
            )
            result = subprocess.run([bash, "-lc", command], cwd=REPOSITORY, text=True, capture_output=True, check=False, timeout=60)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("extraction was not attempted", result.stderr)
            self.assertFalse((data_home / "arbiter-academy").exists())

    def test_posix_download_rejects_untrusted_redirect_without_installing(self) -> None:
        """Catches the required GitHub redirect allowance becoming an open redirect."""
        bash = shutil.which("bash")
        if bash is None:
            self.skipTest("a POSIX shell is required")
        fake_bin = self.scratch / "untrusted-redirect-bin"
        fake_bin.mkdir()
        fake_curl = fake_bin / "curl"
        fake_curl.write_bytes((
            "#!/bin/sh\n"
            "while [ \"$#\" -gt 0 ]; do\n"
            "  case \"$1\" in --dump-header) headers=$2; shift 2;; --output) body=$2; shift 2;; *) shift;; esac\n"
            "done\n"
            "printf 'HTTP/1.1 302 Found\\r\\nLocation: https://evil.example/payload.zip\\r\\n\\r\\n' >\"$headers\"\n"
            ": >\"$body\"\n"
            "printf 302\n"
        ).encode("utf-8"))
        data_home = self.scratch / "untrusted-redirect-data"
        controlled_path = f"{posix_path(fake_bin)}:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
        command = (
            f"chmod 700 {shlex.quote(posix_path(fake_curl))}; "
            f"PATH={shlex.quote(controlled_path)} XDG_DATA_HOME={shlex.quote(posix_path(data_home))} "
            f"sh {shlex.quote(posix_path(self.assets / 'install.sh'))}"
        )
        result = subprocess.run([bash, "-lc", command], cwd=REPOSITORY, text=True, capture_output=True, check=False, timeout=60)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("untrusted or mutable location", result.stderr)
        self.assertFalse((data_home / "arbiter-academy").exists())

    def test_posix_download_allows_only_the_required_trusted_redirect_chain(self) -> None:
        """Catches rejecting GitHub's immutable CDN hop or skipping hash verification after it."""
        bash = shutil.which("bash")
        if bash is None:
            self.skipTest("a POSIX shell is required")
        fake_bin = self.scratch / "trusted-redirect-bin"
        fake_bin.mkdir()
        fake_curl = fake_bin / "curl"
        fake_curl.write_bytes((
            "#!/bin/sh\n"
            "while [ \"$#\" -gt 0 ]; do\n"
            "  case \"$1\" in --dump-header) headers=$2; shift 2;; --output) body=$2; shift 2;; *) shift;; esac\n"
            "done\n"
            "if [ ! -e \"$CURL_STATE\" ]; then\n"
            "  printf 1 >\"$CURL_STATE\"\n"
            "  printf 'HTTP/1.1 302 Found\\r\\nLocation: https://release-assets.githubusercontent.com/github-production-release-asset/immutable?sig=reviewed\\r\\n\\r\\n' >\"$headers\"\n"
            "  : >\"$body\"\n"
            "  printf 302\n"
            "else\n"
            "  printf 2 >\"$CURL_STATE\"\n"
            "  printf 'HTTP/1.1 200 OK\\r\\n\\r\\n' >\"$headers\"\n"
            "  cp -- \"$CANONICAL_BUNDLE\" \"$body\"\n"
            "  printf 200\n"
            "fi\n"
        ).encode("utf-8"))
        real_python = subprocess.run([bash, "-lc", "command -v python3"], text=True, capture_output=True, check=True).stdout.strip()
        fake_python = fake_bin / "python3"
        fake_python.write_bytes((
            "#!/bin/sh\n"
            "if [ \"${1:-}\" = -m ] && [ \"${2:-}\" = venv ]; then mkdir -p -- \"$4\"; exit 19; fi\n"
            f"exec {shlex.quote(real_python)} \"$@\"\n"
        ).encode("utf-8"))
        data_home = self.scratch / "trusted-redirect-data"
        state = self.scratch / "trusted-redirect-count"
        controlled_path = f"{posix_path(fake_bin)}:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
        command = (
            f"chmod 700 {shlex.quote(posix_path(fake_curl))} {shlex.quote(posix_path(fake_python))}; "
            f"CURL_STATE={shlex.quote(posix_path(state))} CANONICAL_BUNDLE={shlex.quote(posix_path(self.assets / ARCHIVE))} "
            f"PATH={shlex.quote(controlled_path)} XDG_DATA_HOME={shlex.quote(posix_path(data_home))} "
            f"sh {shlex.quote(posix_path(self.assets / 'install.sh'))}"
        )
        result = subprocess.run([bash, "-lc", command], cwd=REPOSITORY, text=True, capture_output=True, check=False, timeout=120)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Python failed to create", result.stderr)
        self.assertNotIn("untrusted or mutable", result.stderr)
        self.assertNotIn("SHA-256 mismatch", result.stderr)
        self.assertEqual(state.read_text(encoding="ascii"), "2")
        self.assertFalse((data_home / "arbiter-academy").exists())

    def test_both_installers_reject_archive_traversal_before_writing_outside_root(self) -> None:
        """Catches a validly hashed hostile archive escaping the owned extraction directory."""
        hostile = self.scratch / "hostile.zip"
        manifest = {
            "format_version": 1,
            "release": RELEASE,
            "wheelhouse": [{"filename": "workshop_queue-0.1.0-py3-none-any.whl", "sha256": "0" * 64, "size": 0}],
        }
        with zipfile.ZipFile(hostile, "w") as archive:
            archive.writestr("bundle-manifest.json", json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n")
            archive.writestr("../escaped.whl", b"")
        hostile_digest = sha256(hostile)
        canonical_digest = sha256(self.assets / ARCHIVE)

        powershell = shutil.which("powershell") or shutil.which("pwsh")
        if powershell is not None and os.name == "nt":
            script = self.scratch / "hostile-install.ps1"
            script.write_bytes((self.assets / "install.ps1").read_bytes().replace(canonical_digest.encode(), hostile_digest.encode()))
            local_app_data = self.scratch / "powershell-traversal"
            environment = os.environ.copy()
            environment["LOCALAPPDATA"] = str(local_app_data)
            result = subprocess.run(
                [powershell, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(script), "-BundlePath", str(hostile)],
                cwd=REPOSITORY, env=environment, text=True, capture_output=True, check=False, timeout=60,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("unsafe archive path", result.stderr)
            self.assertFalse(any(local_app_data.rglob("escaped.whl")))

        bash = shutil.which("bash")
        if bash is not None:
            script = self.scratch / "hostile-install.sh"
            script.write_bytes((self.assets / "install.sh").read_bytes().replace(canonical_digest.encode(), hostile_digest.encode()))
            data_home = self.scratch / "posix-traversal"
            command = (
                f"export XDG_DATA_HOME={shlex.quote(posix_path(data_home))}; "
                f"sh {shlex.quote(posix_path(script))} --bundle {shlex.quote(posix_path(hostile))}"
            )
            result = subprocess.run([bash, "-lc", command], cwd=REPOSITORY, text=True, capture_output=True, check=False, timeout=60)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("unsafe archive path", result.stderr)
            self.assertFalse(any(data_home.rglob("escaped.whl")))

    def test_both_installers_reject_the_hostile_archive_matrix(self) -> None:
        """Catches platform-specific path spellings, links, and colliding ZIP entries."""
        manifest = {
            "format_version": 1,
            "release": RELEASE,
            "wheelhouse": [{"filename": "workshop_queue-0.1.0-py3-none-any.whl", "sha256": "0" * 64, "size": 0}],
        }
        manifest_bytes = (json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n").encode()
        wheel_path = "wheelhouse/workshop_queue-0.1.0-py3-none-any.whl"
        parent_link_target = self.scratch / "archive-parent-link-target"
        parent_link_target.mkdir()
        cases = {
            "rooted": [("bundle-manifest.json", manifest_bytes, None), ("/escaped.whl", b"", None)],
            "backslash": [("bundle-manifest.json", manifest_bytes, None), ("wheelhouse\\escaped.whl", b"", None)],
            "drive-colon": [("bundle-manifest.json", manifest_bytes, None), ("C:/escaped.whl", b"", None)],
            "dot-component": [("bundle-manifest.json", manifest_bytes, None), ("wheelhouse/./escaped.whl", b"", None)],
            "empty-component": [("bundle-manifest.json", manifest_bytes, None), ("wheelhouse//escaped.whl", b"", None)],
            "symlink": [("bundle-manifest.json", manifest_bytes, None), (wheel_path, b"../../escaped.whl", "symlink")],
            "duplicate": [("bundle-manifest.json", manifest_bytes, None), ("bundle-manifest.json", manifest_bytes, None), (wheel_path, b"", None)],
            "case-collision": [("bundle-manifest.json", manifest_bytes, None), ("Bundle-Manifest.json", manifest_bytes, None), (wheel_path, b"", None)],
            "parent-symlink-child": [
                ("bundle-manifest.json", manifest_bytes, None),
                ("wheelhouse", posix_path(parent_link_target).encode(), "symlink"),
                (wheel_path, b"outside", None),
            ],
        }
        canonical_digest = sha256(self.assets / ARCHIVE)
        powershell = shutil.which("powershell") or shutil.which("pwsh")
        bash = shutil.which("bash")
        for label, entries in cases.items():
            hostile = self.scratch / f"hostile-{label}.zip"
            with zipfile.ZipFile(hostile, "w") as archive:
                for name, payload, kind in entries:
                    if kind == "symlink":
                        info = zipfile.ZipInfo(name)
                        info.create_system = 3
                        info.external_attr = (stat.S_IFLNK | 0o777) << 16
                        archive.writestr(info, payload)
                    else:
                        archive.writestr(name, payload)
            if label == "backslash":
                # zipfile normalizes separators on Windows; patch both ZIP name records
                # byte-for-byte so the installers receive the hostile spelling.
                hostile.write_bytes(
                    hostile.read_bytes().replace(b"wheelhouse/escaped.whl", b"wheelhouse\\escaped.whl")
                )
            hostile_digest = sha256(hostile)

            if powershell is not None and os.name == "nt":
                with self.subTest(platform="powershell", archive=label):
                    script = self.scratch / f"hostile-{label}-install.ps1"
                    script.write_bytes((self.assets / "install.ps1").read_bytes().replace(canonical_digest.encode(), hostile_digest.encode()))
                    local_app_data = self.scratch / f"powershell-hostile-{label}"
                    environment = os.environ.copy()
                    environment["LOCALAPPDATA"] = str(local_app_data)
                    result = subprocess.run(
                        [powershell, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(script), "-BundlePath", str(hostile)],
                        cwd=REPOSITORY, env=environment, text=True, capture_output=True, check=False, timeout=60,
                    )
                    self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertIn("bundle contains", result.stdout + result.stderr)
                    self.assertFalse((local_app_data / "ArbiterAcademy" / RELEASE).exists())
                    self.assertFalse((parent_link_target / Path(wheel_path).name).exists())

            if bash is not None:
                with self.subTest(platform="posix", archive=label):
                    script = self.scratch / f"hostile-{label}-install.sh"
                    script.write_bytes((self.assets / "install.sh").read_bytes().replace(canonical_digest.encode(), hostile_digest.encode()))
                    data_home = self.scratch / f"posix-hostile-{label}"
                    command = (
                        f"XDG_DATA_HOME={shlex.quote(posix_path(data_home))} "
                        f"sh {shlex.quote(posix_path(script))} --bundle {shlex.quote(posix_path(hostile))}"
                    )
                    result = subprocess.run([bash, "-lc", command], cwd=REPOSITORY, text=True, capture_output=True, check=False, timeout=60)
                    self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertIn("bundle contains", result.stdout + result.stderr)
                    self.assertFalse((data_home / "arbiter-academy" / RELEASE).exists())
                    self.assertFalse((parent_link_target / Path(wheel_path).name).exists())


if __name__ == "__main__":
    unittest.main()
