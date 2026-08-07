from __future__ import annotations

import builtins
import hashlib
import io
import json
import socket
import subprocess
import sys
import warnings
import zipfile
from copy import deepcopy
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch


DATEUTIL_WHEEL = "python_dateutil-2.9.0.post0-py2.py3-none-any.whl"
SIX_WHEEL = "six-1.17.0-py2.py3-none-any.whl"
DATEUTIL_LICENSE = "python_dateutil-2.9.0.post0.LICENSE"
SIX_LICENSE = "six-1.17.0.LICENSE"
APACHE_LICENSE = "Apache-2.0.txt"


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _wheel(
    *,
    name: str,
    version: str,
    license_name: str,
    license_bytes: bytes,
    requires_dist: tuple[str, ...] = (),
    requires_python: str = "!=3.0.*,!=3.1.*,!=3.2.*,>=2.7",
    tags: tuple[str, ...] = ("py2-none-any", "py3-none-any"),
    purelib: str = "true",
    extra_members: tuple[tuple[str, bytes], ...] = (),
) -> bytes:
    metadata = [
        "Metadata-Version: 2.1",
        f"Name: {name}",
        f"Version: {version}",
        f"Requires-Python: {requires_python}",
    ]
    metadata.extend(f"Requires-Dist: {value}" for value in requires_dist)
    wheel = ["Wheel-Version: 1.0", "Generator: academy-test", f"Root-Is-Purelib: {purelib}"]
    wheel.extend(f"Tag: {tag}" for tag in tags)
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        prefix = f"{name.replace('-', '_')}-{version}.dist-info"
        archive.writestr(f"{prefix}/METADATA", "\n".join(metadata) + "\n\nfixture description\n")
        archive.writestr(f"{prefix}/WHEEL", "\n".join(wheel) + "\n\n")
        archive.writestr(f"{prefix}/LICENSE", license_bytes)
        for member, contents in extra_members:
            archive.writestr(member, contents)
    return stream.getvalue()


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("utf-8") + b"\n"


class CandidateDataTests(TestCase):
    """Catches unsafe or non-reproducible P04 candidate evidence validation."""

    def setUp(self) -> None:
        self.dateutil_license = b"dateutil-license\n"
        self.six_license = b"six-license\n"
        self.apache_license = b"apache-license\n"
        self.blobs = {
            DATEUTIL_WHEEL: _wheel(
                name="python-dateutil",
                version="2.9.0.post0",
                license_name=DATEUTIL_LICENSE,
                license_bytes=self.dateutil_license,
                requires_dist=("six >=1.5",),
            ),
            SIX_WHEEL: _wheel(
                name="six",
                version="1.17.0",
                license_name=SIX_LICENSE,
                license_bytes=self.six_license,
                requires_python=">=2.7, !=3.0.*, !=3.1.*, !=3.2.*",
            ),
            DATEUTIL_LICENSE: self.dateutil_license,
            SIX_LICENSE: self.six_license,
            APACHE_LICENSE: self.apache_license,
        }
        self.expected = self._manifest_for(self.blobs)
        self.blobs["candidate-set.json"] = _canonical_json(self.expected)

    def _manifest_for(self, blobs: dict[str, bytes]) -> dict[str, object]:
        return {
            "install_policy": "review-only-never-install",
            "lab_id": "P04-review-a-dependency",
            "license_payloads": [
                {
                    "filename": DATEUTIL_LICENSE,
                    "sha256": _sha256(blobs[DATEUTIL_LICENSE]),
                    "size_bytes": len(blobs[DATEUTIL_LICENSE]),
                    "source": f"{DATEUTIL_WHEEL}!/python_dateutil-2.9.0.post0.dist-info/LICENSE",
                },
                {
                    "filename": SIX_LICENSE,
                    "sha256": _sha256(blobs[SIX_LICENSE]),
                    "size_bytes": len(blobs[SIX_LICENSE]),
                    "source": f"{SIX_WHEEL}!/six-1.17.0.dist-info/LICENSE",
                },
                {
                    "filename": APACHE_LICENSE,
                    "sha256": _sha256(blobs[APACHE_LICENSE]),
                    "size_bytes": len(blobs[APACHE_LICENSE]),
                    "source": "https://www.apache.org/licenses/LICENSE-2.0.txt",
                },
            ],
            "schema_version": 1,
            "wheels": [
                {
                    "filename": DATEUTIL_WHEEL,
                    "name": "python-dateutil",
                    "sha256": _sha256(blobs[DATEUTIL_WHEEL]),
                    "size_bytes": len(blobs[DATEUTIL_WHEEL]),
                    "version": "2.9.0.post0",
                },
                {
                    "filename": SIX_WHEEL,
                    "name": "six",
                    "sha256": _sha256(blobs[SIX_WHEEL]),
                    "size_bytes": len(blobs[SIX_WHEEL]),
                    "version": "1.17.0",
                },
            ],
        }

    def _module(self):
        from academy_engine import candidate_data

        return candidate_data

    def _validated(self, blobs: dict[str, bytes] | None = None, expected: dict[str, object] | None = None):
        module = self._module()
        supplied = blobs or self.blobs
        with patch.object(module, "_EXPECTED_MANIFEST", expected or self.expected):
            return module.validate_p04_candidate_blobs(supplied)

    def _replace_payload(self, filename: str, contents: bytes) -> tuple[dict[str, bytes], dict[str, object]]:
        blobs = dict(self.blobs)
        blobs[filename] = contents
        expected = self._manifest_for(blobs)
        blobs["candidate-set.json"] = _canonical_json(expected)
        return blobs, expected

    def _encrypted(self, contents: bytes) -> bytes:
        mutated = bytearray(contents)
        for marker, offset in ((b"PK\x03\x04", 6), (b"PK\x01\x02", 8)):
            start = 0
            while (found := mutated.find(marker, start)) >= 0:
                mutated[found + offset] |= 1
                start = found + len(marker)
        return bytes(mutated)

    def test_valid_fixture_returns_ordered_opaque_payloads(self) -> None:
        """Catches a validator that accepts a candidate set without binding each opaque payload."""
        result = self._validated()

        self.assertEqual([payload.filename for payload in result.wheels], [DATEUTIL_WHEEL, SIX_WHEEL])
        self.assertEqual([payload.filename for payload in result.licenses], [DATEUTIL_LICENSE, SIX_LICENSE, APACHE_LICENSE])
        self.assertEqual(result.wheels[0].sha256, _sha256(self.blobs[DATEUTIL_WHEEL]))

    def test_production_candidate_directory_has_exact_validated_bytes(self) -> None:
        """Catches a package candidate directory that drifts from its immutable P04 byte contract."""
        module = self._module()
        root = Path(__file__).resolve().parents[1] / module.P04_CANDIDATE_ROOT
        blobs = {path.name: path.read_bytes() for path in root.iterdir() if path.is_file()}

        result = module.validate_p04_candidate_blobs(blobs)
        self.assertEqual([item.size_bytes for item in result.wheels], [229892, 11050])
        self.assertEqual([item.size_bytes for item in result.licenses], [2889, 1066, 11358])

    def test_rejects_missing_extra_or_renamed_candidate_basename(self) -> None:
        """Catches a validator that permits an ambiguous packaged candidate directory."""
        cases = {
            "missing": {key: value for key, value in self.blobs.items() if key != SIX_LICENSE},
            "extra": {**self.blobs, "NOTICE.txt": b"invented"},
            "renamed": {**{key: value for key, value in self.blobs.items() if key != SIX_LICENSE}, "six-license.txt": self.six_license},
        }
        for name, blobs in cases.items():
            with self.subTest(name=name), self.assertRaises(self._module().CandidateDataError):
                self._validated(blobs)

    def test_rejects_noncanonical_or_wrongly_typed_manifest(self) -> None:
        """Catches a validator that parses JSON but loses the immutable manifest contract."""
        pretty = dict(self.blobs)
        pretty["candidate-set.json"] = json.dumps(self.expected, indent=2).encode("utf-8")
        with self.assertRaises(self._module().CandidateDataError):
            self._validated(pretty)

        expected = deepcopy(self.expected)
        expected["wheels"][0]["size_bytes"] = True
        typed = dict(self.blobs)
        typed["candidate-set.json"] = _canonical_json(expected)
        with self.assertRaises(self._module().CandidateDataError):
            self._validated(typed, expected)

    def test_rejects_payload_byte_or_hash_mutations_before_zip_parsing(self) -> None:
        """Catches a validator that opens or trusts a wheel before whole-file identity validation."""
        for filename in (DATEUTIL_WHEEL, SIX_WHEEL, DATEUTIL_LICENSE, SIX_LICENSE, APACHE_LICENSE):
            blobs = dict(self.blobs)
            blobs[filename] += b"!"
            with self.subTest(filename=filename), self.assertRaises(self._module().CandidateDataError) as caught:
                self._validated(blobs)
            self.assertIn(filename, str(caught.exception))

        expected = deepcopy(self.expected)
        expected["wheels"][0]["sha256"] = str(expected["wheels"][0]["sha256"]).upper()
        blobs = dict(self.blobs)
        blobs["candidate-set.json"] = _canonical_json(expected)
        with self.assertRaises(self._module().CandidateDataError):
            self._validated(blobs, expected)

    def test_rejects_payload_size_limit_before_manifest_parsing(self) -> None:
        """Catches a validator that accepts oversized opaque inputs before applying its bounds."""
        blobs = dict(self.blobs)
        blobs["candidate-set.json"] = b"{" + b" " * (16 * 1024) + b"}"
        with self.assertRaises(self._module().CandidateDataError):
            self._validated(blobs)

    def test_rejects_unsafe_duplicate_or_oversized_zip_structure(self) -> None:
        """Catches ZIP member traversal, duplication, and decompression-bomb acceptance."""
        unsafe_wheel = _wheel(
            name="python-dateutil", version="2.9.0.post0", license_name=DATEUTIL_LICENSE,
            license_bytes=self.dateutil_license, requires_dist=("six >=1.5",), extra_members=(("../escape", b"x"),),
        )
        blobs, expected = self._replace_payload(DATEUTIL_WHEEL, unsafe_wheel)
        with self.assertRaises(self._module().CandidateDataError):
            self._validated(blobs, expected)

        for member in ("/absolute", "C:/absolute", "C:relative", "folder/\x01control", "NOTICE.txt", "PATENT"):
            wheel = _wheel(
                name="python-dateutil", version="2.9.0.post0", license_name=DATEUTIL_LICENSE,
                license_bytes=self.dateutil_license, requires_dist=("six >=1.5",), extra_members=((member, b"x"),),
            )
            blobs, expected = self._replace_payload(DATEUTIL_WHEEL, wheel)
            with self.subTest(member=repr(member)), self.assertRaises(self._module().CandidateDataError):
                self._validated(blobs, expected)

        wheel = _wheel(
            name="python-dateutil", version="2.9.0.post0", license_name=DATEUTIL_LICENSE,
            license_bytes=self.dateutil_license, requires_dist=("six >=1.5",), extra_members=(("folder/backslash", b"x"),),
        ).replace(b"folder/backslash", b"folder\\backslash")
        blobs, expected = self._replace_payload(DATEUTIL_WHEEL, wheel)
        with self.assertRaises(self._module().CandidateDataError):
            self._validated(blobs, expected)

        duplicate = io.BytesIO()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with zipfile.ZipFile(duplicate, "w") as archive:
                prefix = "python_dateutil-2.9.0.post0.dist-info"
                archive.writestr(f"{prefix}/METADATA", "Name: python-dateutil\nVersion: 2.9.0.post0\nRequires-Dist: six >=1.5\n")
                archive.writestr(f"{prefix}/METADATA", "Name: python-dateutil\nVersion: 2.9.0.post0\nRequires-Dist: six >=1.5\n")
                archive.writestr(f"{prefix}/WHEEL", "Root-Is-Purelib: true\nTag: py2-none-any\nTag: py3-none-any\n")
                archive.writestr(f"{prefix}/LICENSE", self.dateutil_license)
        blobs, expected = self._replace_payload(DATEUTIL_WHEEL, duplicate.getvalue())
        with self.assertRaises(self._module().CandidateDataError):
            self._validated(blobs, expected)

        blobs, expected = self._replace_payload(DATEUTIL_WHEEL, self._encrypted(self.blobs[DATEUTIL_WHEEL]))
        with self.assertRaises(self._module().CandidateDataError):
            self._validated(blobs, expected)

        bomb = _wheel(
            name="python-dateutil", version="2.9.0.post0", license_name=DATEUTIL_LICENSE,
            license_bytes=self.dateutil_license, requires_dist=("six >=1.5",), extra_members=(("payload", b"x" * (4 * 1024 * 1024 + 1)),),
        )
        blobs, expected = self._replace_payload(DATEUTIL_WHEEL, bomb)
        with self.assertRaises(self._module().CandidateDataError):
            self._validated(blobs, expected)

    def test_rejects_metadata_wheel_or_embedded_license_mismatch(self) -> None:
        """Catches a validator that accepts a wrong closure, platform claim, or redistributed license."""
        invalid = (
            _wheel(name="wrong", version="2.9.0.post0", license_name=DATEUTIL_LICENSE, license_bytes=self.dateutil_license, requires_dist=("six >=1.5",)),
            _wheel(name="python-dateutil", version="0", license_name=DATEUTIL_LICENSE, license_bytes=self.dateutil_license, requires_dist=("six >=1.5",)),
            _wheel(name="python-dateutil", version="2.9.0.post0", license_name=DATEUTIL_LICENSE, license_bytes=self.dateutil_license, requires_dist=("six >1.5",)),
            _wheel(name="python-dateutil", version="2.9.0.post0", license_name=DATEUTIL_LICENSE, license_bytes=self.dateutil_license, requires_dist=("six >=1.5", "six <2")),
            _wheel(name="python-dateutil", version="2.9.0.post0", license_name=DATEUTIL_LICENSE, license_bytes=self.dateutil_license, requires_dist=("six >=1.5",), tags=("py3-none-any",)),
            _wheel(name="python-dateutil", version="2.9.0.post0", license_name=DATEUTIL_LICENSE, license_bytes=self.dateutil_license, requires_dist=("six >=1.5",), purelib="false"),
            _wheel(name="python-dateutil", version="2.9.0.post0", license_name=DATEUTIL_LICENSE, license_bytes=b"wrong", requires_dist=("six >=1.5",)),
        )
        for contents in invalid:
            blobs, expected = self._replace_payload(DATEUTIL_WHEEL, contents)
            with self.subTest(contents_hash=_sha256(contents)), self.assertRaises(self._module().CandidateDataError):
                self._validated(blobs, expected)

        six = _wheel(
            name="six", version="1.17.0", license_name=SIX_LICENSE, license_bytes=self.six_license,
            requires_dist=("extra >=1",),
        )
        blobs, expected = self._replace_payload(SIX_WHEEL, six)
        with self.assertRaises(self._module().CandidateDataError):
            self._validated(blobs, expected)

    def test_validation_performs_no_candidate_import_network_subprocess_or_extraction(self) -> None:
        """Catches a validator that treats package evidence as executable or filesystem archive input."""
        module = self._module()
        real_import = builtins.__import__

        def guarded_import(name, *args, **kwargs):
            if name.partition(".")[0] in {"dateutil", "six"}:
                raise AssertionError("candidate import")
            return real_import(name, *args, **kwargs)

        with (
            patch("builtins.__import__", side_effect=guarded_import),
            patch.object(socket, "socket", side_effect=AssertionError("network")),
            patch.object(socket, "create_connection", side_effect=AssertionError("network")),
            patch.object(subprocess, "run", side_effect=AssertionError("subprocess")),
            patch.object(zipfile.ZipFile, "extract", side_effect=AssertionError("extract")),
            patch.object(zipfile.ZipFile, "extractall", side_effect=AssertionError("extract")),
        ):
            result = self._validated()
        self.assertEqual(result.wheels[1].filename, SIX_WHEEL)
        self.assertNotIn("dateutil", sys.modules)
        self.assertNotIn("six", sys.modules)

    def test_errors_never_disclose_member_contents_or_local_path(self) -> None:
        """Catches diagnostics that turn untrusted archive content into learner-visible output."""
        secret = b"P04-private-canary-C:\\cache\\candidate"
        blobs, expected = self._replace_payload(DATEUTIL_WHEEL, secret)
        with self.assertRaises(self._module().CandidateDataError) as caught:
            self._validated(blobs, expected)
        self.assertNotIn(secret.decode("ascii"), str(caught.exception))
        self.assertNotIn("C:\\cache", str(caught.exception))
