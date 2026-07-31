from __future__ import annotations

import hashlib
import importlib.util
import os
import shutil
import stat
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock


SOURCE = Path(__file__).resolve().parents[1]
SCANNER = SOURCE / "scripts" / "scan_secrets.py"


def git(root: Path, *arguments: str, check: bool = True) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", *arguments],
        cwd=root,
        capture_output=True,
        check=check,
    )


class IndexedRepository:
    def __init__(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "repository"
        self.root.mkdir()
        git(self.root, "init", "-b", "main")
        git(self.root, "config", "user.name", "Scanner Fixture")
        git(self.root, "config", "user.email", "fixture@example.invalid")

    def close(self) -> None:
        self.temporary.cleanup()

    def write(self, relative: str, content: bytes) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def stage(self, *paths: str) -> None:
        git(self.root, "add", "--", *paths)

    def commit(self, message: str) -> None:
        git(self.root, "commit", "-m", message)

    def hash_blob(self, content: bytes) -> bytes:
        return subprocess.run(
            ["git", "hash-object", "-w", "--stdin"],
            cwd=self.root,
            input=content,
            capture_output=True,
            check=True,
        ).stdout.strip()

    def add_index_records(self, records: list[tuple[bytes, bytes]]) -> None:
        payload = b"".join(
            b"100644 " + object_id + b"\t" + path + b"\0"
            for path, object_id in records
        )
        subprocess.run(
            ["git", "update-index", "-z", "--index-info"],
            cwd=self.root,
            input=payload,
            capture_output=True,
            check=True,
        )

    def replace_raw_index_records(self, records: list[tuple[bytes, bytes]]) -> None:
        """Install a valid v2 SHA-1 index without asking the host filesystem for the paths."""
        entries: list[bytes] = []
        for path, object_id in sorted(records):
            if len(object_id) != 40:
                raise ValueError("raw index helper requires SHA-1 fixtures")
            stat_fields = (0, 0, 0, 0, 0, 0, 0o100644, 0, 0, 0)
            entry = (
                struct.pack(">10L", *stat_fields)
                + bytes.fromhex(object_id.decode("ascii"))
                + struct.pack(">H", min(len(path), 0xFFF))
                + path
                + b"\0"
            )
            entry += b"\0" * ((8 - len(entry) % 8) % 8)
            entries.append(entry)
        body = struct.pack(">4sLL", b"DIRC", 2, len(entries)) + b"".join(entries)
        (self.root / ".git" / "index").write_bytes(body + hashlib.sha1(body).digest())

    def scan(
        self, *, environment: dict[str, str] | None = None
    ) -> subprocess.CompletedProcess[bytes]:
        process_environment = os.environ.copy()
        if environment:
            process_environment.update(environment)
        return subprocess.run(
            [sys.executable, str(SCANNER), "--staged"],
            cwd=self.root,
            env=process_environment,
            capture_output=True,
            check=False,
        )


def github_classic() -> bytes:
    return b"gh" + b"p_" + b"A7" * 18


def github_fine_grained() -> bytes:
    return b"github_" + b"pat_" + b"A7" * 12 + b"_" + b"B8" * 24


def aws_access(prefix: bytes = b"AK" + b"IA") -> bytes:
    return prefix + b"A7" * 8


def openai_key(*, project: bool = False) -> bytes:
    prefix = b"s" + b"k-" + (b"proj-" if project else b"")
    return prefix + b"A7" * 20


def slack_token() -> bytes:
    return b"xo" + b"xb-" + b"1234567890-" + b"A7" * 12


def credential_url() -> bytes:
    return b"https://operator:" + b"A7" * 10 + b"@example.invalid/path"


def bearer_value() -> bytes:
    return b"Authorization: Bear" + b"er " + b"A7" * 20


def assigned_value(key: bytes = b"api_" + b"key") -> bytes:
    return key + b" = \"" + b"A7" * 12 + b"\""


def shaped_body(length: int) -> bytes:
    return (b"A7" * (length // 2 + 1))[:length]


def load_scanner_module():
    name = "academy_staged_secret_scanner"
    spec = importlib.util.spec_from_file_location(name, SCANNER)
    if spec is None or spec.loader is None:
        raise AssertionError("scanner module could not be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class StagedSecretScanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = IndexedRepository()
        self.addCleanup(self.fixture.close)

    def assert_bounded(self, result: subprocess.CompletedProcess[bytes]) -> None:
        self.assertLess(len(result.stdout) + len(result.stderr), 8192)
        self.assertNotIn(str(self.fixture.root).encode(), result.stdout + result.stderr)

    def test_no_staged_paths_reports_zero_file_pass(self) -> None:
        """Catches scanners that treat an empty index as an inspection failure."""
        result = self.fixture.scan()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(
            result.stdout.replace(b"\r\n", b"\n"),
            b"PASS: inspected 0 staged files; 0 findings.\n",
        )
        self.assertEqual(result.stderr, b"")

    def test_clean_text_and_binary_index_blobs_pass(self) -> None:
        """Catches worktree-only readers or blanket rejection of binary content."""
        self.fixture.write("notes.txt", b"ordinary Academy notes\n")
        self.fixture.write("asset.bin", b"\x00\x01ordinary\xff\n")
        self.fixture.stage("notes.txt", "asset.bin")

        result = self.fixture.scan()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(b"inspected 2 staged files", result.stdout)
        self.assert_bounded(result)

    def test_each_required_high_confidence_rule_family_fails(self) -> None:
        """Catches deletion or weakening of any required detection rule."""
        cases = (
            ("pem", b"-----BEGIN " + b"PRIVATE KEY-----\nbody\n", b"PEM_PRIVATE_KEY"),
            ("github-classic", github_classic(), b"GITHUB_TOKEN"),
            ("github-fine", github_fine_grained(), b"GITHUB_TOKEN"),
            ("aws-akia", aws_access(), b"AWS_ACCESS_KEY_ID"),
            ("aws-asia", aws_access(b"AS" + b"IA"), b"AWS_ACCESS_KEY_ID"),
            ("openai", openai_key(), b"OPENAI_API_KEY"),
            ("openai-project", openai_key(project=True), b"OPENAI_API_KEY"),
            ("slack", slack_token(), b"SLACK_TOKEN"),
            ("credential-url", credential_url(), b"CREDENTIAL_URL"),
            ("bearer", bearer_value(), b"BEARER_AUTHORIZATION"),
            ("assignment-api", assigned_value(), b"CREDENTIAL_ASSIGNMENT"),
            ("assignment-password", assigned_value(b"pass" + b"word"), b"CREDENTIAL_ASSIGNMENT"),
        )
        for label, value, rule in cases:
            with self.subTest(label=label):
                fixture = IndexedRepository()
                self.addCleanup(fixture.close)
                fixture.write("candidate.txt", b"prefix\n" + value + b"\nsuffix\n")
                fixture.stage("candidate.txt")

                result = fixture.scan()

                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn(rule + b" candidate.txt:2", result.stdout)
                self.assertNotIn(value, result.stdout + result.stderr)
                self.assertLess(len(result.stdout) + len(result.stderr), 8192)

    def test_unterminated_and_mismatched_quoted_assignments_are_detected(self) -> None:
        """Catches malformed quote delimiters hiding credential-shaped assignments."""
        value = b"Abcdefghijklmnop!@"
        cases = (
            ("unterminated-double", b'password = "' + value),
            ("unterminated-single", b"api_key = '" + value),
            ("mismatched-double", b'password = "' + value + b"'"),
            ("mismatched-single", b"api_key = '" + value + b'"'),
        )
        for label, content in cases:
            with self.subTest(label=label):
                fixture = IndexedRepository()
                self.addCleanup(fixture.close)
                fixture.write("malformed.txt", content + b"\n")
                fixture.stage("malformed.txt")

                result = fixture.scan()

                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn(b"CREDENTIAL_ASSIGNMENT malformed.txt:1", result.stdout)
                self.assertNotIn(value, result.stdout + result.stderr)

        clean_cases = (
            b'password = "too-short!@',
            b"api_key = 'placeholder-value",
        )
        for content in clean_cases:
            with self.subTest(clean=content.split(b"=", 1)[0].strip()):
                fixture = IndexedRepository()
                self.addCleanup(fixture.close)
                fixture.write("clean-malformed.txt", content + b"\n")
                fixture.stage("clean-malformed.txt")

                result = fixture.scan()

                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_nested_malformed_assignment_component_redacts_all_findings(self) -> None:
        """Catches malformed assignment components leaking through content diagnostics."""
        value = b"Abcdefghijklmnop!"
        component = (b"password='" + value).decode("ascii")
        relative = f"archive/{component}/finding.txt"
        self.fixture.write(relative, aws_access() + b"\n")
        self.fixture.stage(relative)

        result = self.fixture.scan()

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn(b"CREDENTIAL_ASSIGNMENT <redacted-path>:path", result.stdout)
        self.assertIn(b"AWS_ACCESS_KEY_ID <redacted-path>:1", result.stdout)
        self.assertNotIn(b"Abcdefghijklmnop", result.stdout + result.stderr)

    def test_staged_secret_survives_clean_unstaged_worktree_copy(self) -> None:
        """Catches replacing index-object reads with mutable worktree reads."""
        value = github_classic()
        self.fixture.write("config.txt", value + b"\n")
        self.fixture.stage("config.txt")
        self.fixture.write("config.txt", b"clean working copy\n")

        result = self.fixture.scan()

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn(b"GITHUB_TOKEN config.txt:1", result.stdout)
        self.assertNotIn(value, result.stdout + result.stderr)

    def test_unstaged_secret_does_not_poison_clean_staged_blob(self) -> None:
        """Catches scanners that inspect the worktree instead of the staged blob."""
        self.fixture.write("config.txt", b"clean staged content\n")
        self.fixture.stage("config.txt")
        self.fixture.write("config.txt", openai_key() + b"\n")

        result = self.fixture.scan()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(b"inspected 1 staged files", result.stdout)

    def test_type_changed_blob_is_scanned(self) -> None:
        """Catches ACMR-only discovery that omits a staged type-change blob."""
        value = github_classic()
        self.fixture.write("target.txt", b"clean regular file\n")
        self.fixture.stage("target.txt")
        self.fixture.commit("base regular file")
        object_id = self.fixture.hash_blob(value + b"\n").decode("ascii")
        git(
            self.fixture.root,
            "update-index",
            "--cacheinfo",
            f"120000,{object_id},target.txt",
        )
        status = git(self.fixture.root, "diff", "--cached", "--name-status").stdout
        self.assertEqual(status.split(maxsplit=1)[0], b"T")

        result = self.fixture.scan()

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn(b"GITHUB_TOKEN target.txt:1", result.stdout)
        self.assertNotIn(value, result.stdout + result.stderr)

    def test_binary_index_blob_with_token_fails(self) -> None:
        """Catches text decoding that silently skips binary staged blobs."""
        value = slack_token()
        self.fixture.write("payload.bin", b"\x00\xff" + value + b"\x00")
        self.fixture.stage("payload.bin")

        result = self.fixture.scan()

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn(b"SLACK_TOKEN payload.bin:1", result.stdout)
        self.assertNotIn(value, result.stdout + result.stderr)

    def test_secret_shaped_filename_is_detected_and_redacted(self) -> None:
        """Catches path leaks and scanners that inspect content but not staged path bytes."""
        secret_name = github_classic().decode("ascii") + ".txt"
        self.fixture.write(secret_name, b"clean body\n")
        self.fixture.stage(secret_name)

        result = self.fixture.scan()

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn(b"GITHUB_TOKEN <redacted-path>:path", result.stdout)
        self.assertNotIn(secret_name.encode(), result.stdout + result.stderr)
        self.assert_bounded(result)

    def test_nested_secret_shaped_path_component_is_redacted(self) -> None:
        """Catches whole-path matching that misses a secret-shaped nested component."""
        value = shaped_body(24)
        component = (b"password=" + value).decode("ascii")
        relative = f"archive/{component}/finding.txt"
        self.fixture.write(relative, b"clean content\n")
        self.fixture.stage(relative)

        result = self.fixture.scan()

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn(b"CREDENTIAL_ASSIGNMENT <redacted-path>:path", result.stdout)
        self.assertNotIn(value, result.stdout + result.stderr)

    def test_nested_secret_shaped_component_redacts_content_findings_too(self) -> None:
        """Catches content diagnostics that reveal a separate secret-shaped path component."""
        value = shaped_body(24)
        component = (b"password=" + value).decode("ascii")
        relative = f"archive/{component}/finding.txt"
        self.fixture.write(relative, aws_access() + b"\n")
        self.fixture.stage(relative)

        result = self.fixture.scan()

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn(b"CREDENTIAL_ASSIGNMENT <redacted-path>:path", result.stdout)
        self.assertIn(b"AWS_ACCESS_KEY_ID <redacted-path>:1", result.stdout)
        self.assertNotIn(value, result.stdout + result.stderr)

    def test_multiple_findings_emit_metadata_only(self) -> None:
        """Catches diagnostics that replay matched values or surrounding lines."""
        first, second = aws_access(), openai_key(project=True)
        self.fixture.write("settings.txt", b"one=" + first + b"\ntwo=" + second + b"\n")
        self.fixture.stage("settings.txt")

        result = self.fixture.scan()

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn(b"AWS_ACCESS_KEY_ID settings.txt:1", result.stdout)
        self.assertIn(b"OPENAI_API_KEY settings.txt:2", result.stdout)
        self.assertIn(b"FINDINGS: 2", result.stdout)
        self.assertNotIn(first, result.stdout + result.stderr)
        self.assertNotIn(second, result.stdout + result.stderr)
        self.assert_bounded(result)

    def test_staged_deletion_has_no_committed_content_to_scan(self) -> None:
        """Catches scanners that reopen deleted worktree paths or scan historical blobs."""
        self.fixture.write("retired.txt", github_classic() + b"\n")
        self.fixture.stage("retired.txt")
        self.fixture.commit("fixture with retired value")
        (self.fixture.root / "retired.txt").unlink()
        git(self.fixture.root, "add", "--", "retired.txt")

        result = self.fixture.scan()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(
            result.stdout.replace(b"\r\n", b"\n"),
            b"PASS: inspected 0 staged files; 0 findings.\n",
        )

    def test_unmerged_index_fails_closed(self) -> None:
        """Catches selecting an arbitrary conflict stage as committed content."""
        self.fixture.write("conflict.txt", b"base\n")
        self.fixture.stage("conflict.txt")
        self.fixture.commit("base")
        git(self.fixture.root, "switch", "-c", "other")
        self.fixture.write("conflict.txt", b"other\n")
        self.fixture.stage("conflict.txt")
        self.fixture.commit("other")
        git(self.fixture.root, "switch", "main")
        self.fixture.write("conflict.txt", b"main\n")
        self.fixture.stage("conflict.txt")
        self.fixture.commit("main")
        merge = git(self.fixture.root, "merge", "other", check=False)
        self.assertNotEqual(merge.returncode, 0)

        result = self.fixture.scan()

        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn(b"unmerged-index", result.stderr)
        self.assertNotIn(b"<<<<<<<", result.stdout + result.stderr)
        self.assert_bounded(result)

    def test_non_repository_and_missing_index_object_fail_closed_safely(self) -> None:
        """Catches Git failures being downgraded to clean or raw stderr being replayed."""
        with tempfile.TemporaryDirectory() as directory:
            outside = Path(directory)
            not_repository = subprocess.run(
                [sys.executable, str(SCANNER), "--staged"],
                cwd=outside,
                capture_output=True,
                check=False,
            )
            self.assertEqual(not_repository.returncode, 2)
            self.assertIn(b"repository-discovery", not_repository.stderr)
            self.assertNotIn(str(outside).encode(), not_repository.stdout + not_repository.stderr)
            self.assertNotIn(b"fatal:", not_repository.stdout + not_repository.stderr)

        self.fixture.write("indexed.txt", b"clean indexed content\n")
        self.fixture.stage("indexed.txt")
        record = git(self.fixture.root, "ls-files", "--stage", "--", "indexed.txt").stdout
        object_id = record.split()[1].decode("ascii")
        git_directory = Path(
            git(self.fixture.root, "rev-parse", "--git-dir").stdout.decode().strip()
        )
        if not git_directory.is_absolute():
            git_directory = self.fixture.root / git_directory
        object_path = git_directory / "objects" / object_id[:2] / object_id[2:]
        os.chmod(object_path, stat.S_IWRITE)
        object_path.unlink()

        missing = self.fixture.scan()

        self.assertEqual(missing.returncode, 2, missing.stdout + missing.stderr)
        self.assertIn(b"inspect-object", missing.stderr)
        self.assertNotIn(object_id.encode(), missing.stdout + missing.stderr)
        self.assertNotIn(str(self.fixture.root).encode(), missing.stdout + missing.stderr)
        self.assertNotIn(b"fatal:", missing.stdout + missing.stderr)

    def test_security_prose_hashes_regex_and_placeholders_remain_clean(self) -> None:
        """Catches broad substring or scanner-source self-matching false positives."""
        scanner_source = SCANNER.read_bytes()
        test_source = Path(__file__).read_bytes()
        digest = hashlib.sha256(b"ordinary source identity").hexdigest().encode()
        prose = b"\n".join(
            (
                b"secret_scan is a preventive security control",
                b"regex example: gh[pousr]_[A-Za-z0-9]{20,255}",
                b"api_key = \"placeholder\"",
                b"access_token=example-value",
                b"password = changeme",
                b"sha256=" + digest,
            )
        )
        self.fixture.write("security-controls.md", prose + b"\n")
        self.fixture.write("scanner-source.py", scanner_source)
        self.fixture.write("dynamic-tests.py", test_source)
        self.fixture.stage("security-controls.md", "scanner-source.py", "dynamic-tests.py")

        result = self.fixture.scan()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(b"inspected 3 staged files", result.stdout)
        self.assert_bounded(result)

    def test_alternate_index_cannot_hide_the_real_staged_secret(self) -> None:
        """Catches inherited GIT_INDEX_FILE steering the scan to a clean index."""
        value = github_classic()
        self.fixture.write("real-index.txt", value + b"\n")
        self.fixture.stage("real-index.txt")
        alternate = self.fixture.root / "clean-alternate-index"
        environment = os.environ.copy()
        environment["GIT_INDEX_FILE"] = str(alternate)
        subprocess.run(
            ["git", "read-tree", "--empty"],
            cwd=self.fixture.root,
            env=environment,
            capture_output=True,
            check=True,
        )

        result = self.fixture.scan(environment={"GIT_INDEX_FILE": str(alternate)})

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn(b"GITHUB_TOKEN real-index.txt:1", result.stdout)
        self.assertNotIn(value, result.stdout + result.stderr)

    def test_git_environment_and_config_injection_cannot_redirect_the_scan(self) -> None:
        """Catches repository, object, and config steering inherited by Git subprocesses."""
        value = openai_key()
        self.fixture.write("authoritative.txt", value + b"\n")
        self.fixture.stage("authoritative.txt")
        decoy = IndexedRepository()
        self.addCleanup(decoy.close)
        decoy.write("clean.txt", b"clean\n")
        decoy.stage("clean.txt")
        empty_objects = self.fixture.root / "empty-objects"
        empty_objects.mkdir()
        hostile_config = self.fixture.root / "hostile.gitconfig"
        hostile_config.write_text("[core]\n\tbare = true\n", encoding="utf-8")
        environment = {
            "GIT_DIR": str(decoy.root / ".git"),
            "GIT_WORK_TREE": str(decoy.root),
            "GIT_INDEX_FILE": str(decoy.root / ".git/index"),
            "GIT_OBJECT_DIRECTORY": str(empty_objects),
            "GIT_ALTERNATE_OBJECT_DIRECTORIES": str(decoy.root / ".git/objects"),
            "GIT_COMMON_DIR": str(decoy.root / ".git"),
            "GIT_CONFIG": str(hostile_config),
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "core.bare",
            "GIT_CONFIG_VALUE_0": "true",
            "GIT_NAMESPACE": "decoy",
            "GIT_REPLACE_REF_BASE": "refs/replace-decoy/",
        }

        result = self.fixture.scan(environment=environment)

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn(b"OPENAI_API_KEY authoritative.txt:1", result.stdout)
        self.assertNotIn(value, result.stdout + result.stderr)
        self.assert_bounded(result)

    def test_local_core_worktree_cannot_redirect_scan_to_clean_decoy(self) -> None:
        """Catches repository-local core.worktree steering root/index discovery."""
        value = aws_access()
        self.fixture.write("authoritative.txt", value + b"\n")
        self.fixture.stage("authoritative.txt")
        decoy = IndexedRepository()
        self.addCleanup(decoy.close)
        git(self.fixture.root, "config", "core.worktree", str(decoy.root))
        victim_index = git(
            self.fixture.root,
            "--git-dir",
            str(self.fixture.root / ".git"),
            "--work-tree",
            str(self.fixture.root),
            "ls-files",
            "--stage",
        ).stdout
        self.assertIn(b"authoritative.txt", victim_index)

        result = self.fixture.scan()

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn(b"AWS_ACCESS_KEY_ID authoritative.txt:1", result.stdout)
        self.assertNotIn(value, result.stdout + result.stderr)

    def test_local_ignore_submodules_cannot_hide_added_gitlink(self) -> None:
        """Catches local diff.ignoreSubmodules hiding a staged non-blob object."""
        self.fixture.write("base.txt", b"base\n")
        self.fixture.stage("base.txt")
        self.fixture.commit("base commit")
        head = git(self.fixture.root, "rev-parse", "HEAD").stdout.strip().decode("ascii")
        git(
            self.fixture.root,
            "update-index",
            "--add",
            "--cacheinfo",
            f"160000,{head},vendor",
        )
        git(self.fixture.root, "config", "diff.ignoreSubmodules", "all")
        hidden = git(self.fixture.root, "diff", "--cached", "--name-status").stdout
        explicit = git(
            self.fixture.root,
            "diff",
            "--cached",
            "--name-status",
            "--ignore-submodules=none",
        ).stdout
        self.assertEqual(hidden, b"")
        self.assertIn(b"vendor", explicit)

        result = self.fixture.scan()

        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn(b"inspect-object", result.stderr)

    def test_replace_ref_and_diff_helpers_cannot_change_or_execute_during_scan(self) -> None:
        """Catches replace refs, textconv, or external diff changing the object view."""
        value = github_classic()
        self.fixture.write("replace.txt", value + b"\n")
        self.fixture.write(".gitattributes", b"*.txt diff=sentinel\n")
        self.fixture.stage("replace.txt", ".gitattributes")
        record = git(self.fixture.root, "ls-files", "--stage", "--", "replace.txt").stdout
        secret_object = record.split()[1].decode("ascii")
        clean_object = subprocess.run(
            ["git", "hash-object", "-w", "--stdin"],
            cwd=self.fixture.root,
            input=b"clean replacement\n",
            capture_output=True,
            check=True,
        ).stdout.strip().decode("ascii")
        git(self.fixture.root, "replace", secret_object, clean_object)
        marker = self.fixture.root / "helper-ran.marker"
        helper = self.fixture.root / "helper.py"
        helper.write_text(
            "from pathlib import Path\nPath('helper-ran.marker').write_text('ran')\n",
            encoding="utf-8",
        )
        command = f'"{sys.executable}" "{helper}"'
        git(self.fixture.root, "config", "diff.sentinel.textconv", command)
        git(self.fixture.root, "config", "diff.external", command)
        git(self.fixture.root, "config", "credential.helper", command)

        result = self.fixture.scan()

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn(b"GITHUB_TOKEN replace.txt:1", result.stdout)
        self.assertFalse(marker.exists())
        self.assertNotIn(value, result.stdout + result.stderr)

    def test_index_change_during_blob_reads_fails_closed(self) -> None:
        """Catches a one-time manifest read that permits mixed-index evidence."""
        for index in range(10):
            self.fixture.write(f"bulk-{index}.bin", b"ordinary\x00" * 100_000)
        self.fixture.write("racing.txt", b"version 0\n")
        self.fixture.stage(*(f"bulk-{index}.bin" for index in range(10)), "racing.txt")
        process = subprocess.Popen(
            [sys.executable, str(SCANNER), "--staged"],
            cwd=self.fixture.root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        stop = threading.Event()

        def churn_index() -> None:
            counter = 1
            time.sleep(0.02)
            while not stop.is_set():
                self.fixture.write("racing.txt", f"version {counter}\n".encode())
                git(self.fixture.root, "add", "--", "racing.txt", check=False)
                counter += 1

        thread = threading.Thread(target=churn_index, daemon=True)
        thread.start()
        stdout, stderr = process.communicate(timeout=30)
        stop.set()
        thread.join(timeout=5)

        self.assertEqual(process.returncode, 2, stdout + stderr)
        self.assertIn(b"index-stability", stderr)
        self.assert_bounded(subprocess.CompletedProcess([], process.returncode, stdout, stderr))

    def test_late_staged_path_between_final_path_and_manifest_fails_closed(self) -> None:
        """Catches a final path/manifest window that omits a newly staged path."""
        self.fixture.write("selected.txt", b"clean selected change\n")
        self.fixture.stage("selected.txt")
        scanner = load_scanner_module()
        original = scanner._index_manifest
        calls = 0

        def interposed(root: Path, paths: tuple[bytes, ...]):
            nonlocal calls
            calls += 1
            if calls == 2:
                self.fixture.write("late.txt", github_classic() + b"\n")
                self.fixture.stage("late.txt")
            return original(root, paths)

        scanner._index_manifest = interposed

        with self.assertRaises(scanner.InspectionError) as raised:
            scanner.scan_staged(self.fixture.root)

        self.assertEqual(raised.exception.operation, "index-stability")
        self.assertEqual(calls, 2)

    def test_unselected_index_record_mutation_during_final_capture_fails_closed(self) -> None:
        """Catches selected-only manifests that ignore other raw index records."""
        self.fixture.write("anchor.txt", b"committed anchor\n")
        self.fixture.stage("anchor.txt")
        self.fixture.commit("anchor baseline")
        self.fixture.write("selected.txt", b"clean selected change\n")
        self.fixture.stage("selected.txt")
        replacement = self.fixture.hash_blob(b"mutated anchor index record\n").decode("ascii")
        scanner = load_scanner_module()
        original = scanner._index_manifest
        calls = 0

        def interposed(root: Path, paths: tuple[bytes, ...]):
            nonlocal calls
            calls += 1
            if calls == 2:
                git(
                    self.fixture.root,
                    "update-index",
                    "--cacheinfo",
                    f"100644,{replacement},anchor.txt",
                )
            return original(root, paths)

        scanner._index_manifest = interposed

        with self.assertRaises(scanner.InspectionError) as raised:
            scanner.scan_staged(self.fixture.root)

        self.assertEqual(raised.exception.operation, "index-stability")
        self.assertEqual(calls, 2)

    @staticmethod
    def _long_index_path(index: int, length: int) -> bytes:
        prefix = f"p{index:04d}/".encode()
        remaining = length - len(prefix)
        if remaining < 1:
            raise ValueError("path length is too small")
        pieces: list[bytes] = []
        while remaining > 0:
            take = min(200, remaining)
            pieces.append(b"a" * take)
            remaining -= take
            if remaining:
                pieces.append(b"/")
                remaining -= 1
        return prefix + b"".join(pieces)

    def test_staged_path_count_cap_is_exact(self) -> None:
        """Catches off-by-one or absent MAX_STAGED_PATHS enforcement."""
        for count, expected in ((1023, 0), (1024, 0), (1025, 2)):
            with self.subTest(count=count):
                fixture = IndexedRepository()
                self.addCleanup(fixture.close)
                object_id = fixture.hash_blob(b"clean\n")
                fixture.add_index_records(
                    [(f"f{index:04d}.txt".encode(), object_id) for index in range(count)]
                )

                result = fixture.scan()

                self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
                if expected == 2:
                    self.assertIn(b"resource-limits", result.stderr)

    def test_path_byte_cap_is_exact(self) -> None:
        """Catches path-byte cap bypasses and an off-by-one at 4096 bytes."""
        for length, expected in ((4095, 0), (4096, 0), (4097, 2)):
            with self.subTest(length=length):
                fixture = IndexedRepository()
                self.addCleanup(fixture.close)
                object_id = fixture.hash_blob(b"clean\n")
                fixture.add_index_records([(self._long_index_path(0, length), object_id)])

                result = fixture.scan()

                self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
                if expected == 2:
                    self.assertIn(b"resource-limits", result.stderr)

    def test_manifest_byte_cap_is_exact(self) -> None:
        """Catches unbounded index-manifest capture and cap off-by-one errors."""
        cap = 2 * 1024 * 1024
        record_overhead = 51
        for delta, expected in ((-1, 0), (0, 0), (1, 2)):
            with self.subTest(delta=delta):
                fixture = IndexedRepository()
                self.addCleanup(fixture.close)
                object_id = fixture.hash_blob(b"clean\n")
                target_path_bytes = cap + delta - 1024 * record_overhead
                base, remainder = divmod(target_path_bytes, 1024)
                lengths = [base + (1 if index < remainder else 0) for index in range(1024)]
                fixture.add_index_records(
                    [
                        (self._long_index_path(index, length), object_id)
                        for index, length in enumerate(lengths)
                    ]
                )

                result = fixture.scan()

                self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
                if expected == 2:
                    self.assertIn(b"resource-limits", result.stderr)

    def test_complete_index_over_manifest_cap_fails_with_only_one_small_change(self) -> None:
        """Catches selected-only cap accounting that ignores the complete raw index."""
        cap = 512
        object_id = self.fixture.hash_blob(b"baseline\n")
        self.fixture.add_index_records(
            [
                (f"baseline-{index:02d}-{'x' * 24}.txt".encode(), object_id)
                for index in range(10)
            ]
        )
        tree = git(self.fixture.root, "write-tree").stdout.strip()
        commit = subprocess.run(
            ["git", "commit-tree", tree.decode("ascii"), "-m", "large baseline"],
            cwd=self.fixture.root,
            capture_output=True,
            check=True,
        ).stdout.strip()
        git(self.fixture.root, "update-ref", "refs/heads/main", commit.decode("ascii"))
        small = self.fixture.hash_blob(b"small staged change\n")
        self.fixture.add_index_records([(b"small.txt", small)])
        selected = git(self.fixture.root, "diff", "--cached", "--name-only").stdout
        self.assertEqual(selected, b"small.txt\n")
        complete = git(self.fixture.root, "ls-files", "--stage", "-z").stdout
        self.assertGreater(len(complete), cap)
        scanner = load_scanner_module()
        scanner.MAX_MANIFEST_BYTES = cap

        with self.assertRaises(scanner.InspectionError) as raised:
            scanner.scan_staged(self.fixture.root)

        self.assertEqual(raised.exception.operation, "resource-limits")

    def test_blob_and_aggregate_byte_caps_are_exact(self) -> None:
        """Catches skipped oversized blobs, aggregate bypasses, and cap off-by-ones."""
        blob_cap = 8 * 1024 * 1024
        for size, expected in ((blob_cap - 1, 0), (blob_cap, 0), (blob_cap + 1, 2)):
            with self.subTest(kind="blob", size=size):
                fixture = IndexedRepository()
                self.addCleanup(fixture.close)
                fixture.write("blob.bin", b"A" * size)
                fixture.stage("blob.bin")

                result = fixture.scan()

                self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
                if expected == 2:
                    self.assertIn(b"resource-limits", result.stderr)

        aggregate_cap = 32 * 1024 * 1024
        for delta, expected in ((-1, 0), (0, 0), (1, 2)):
            with self.subTest(kind="aggregate", delta=delta):
                fixture = IndexedRepository()
                self.addCleanup(fixture.close)
                sizes = [blob_cap] * 3 + [blob_cap + delta]
                for index, size in enumerate(sizes):
                    fixture.write(f"aggregate-{index}.bin", bytes([65 + index]) * size)
                fixture.stage(*(f"aggregate-{index}.bin" for index in range(4)))

                result = fixture.scan()

                self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
                if expected == 2:
                    self.assertIn(b"resource-limits", result.stderr)

    def test_aggregate_cap_rejects_before_reading_the_overflow_blob(self) -> None:
        """Catches aggregate enforcement that reads a whole blob before rejecting it."""
        scanner = load_scanner_module()
        scanner.MAX_BLOB_BYTES = 8
        scanner.MAX_AGGREGATE_BYTES = 32
        for index in range(4):
            self.fixture.write(f"blob-{index}.bin", bytes([65 + index]) * 8)
            self.fixture.stage(f"blob-{index}.bin")

        count, findings, suppressed = scanner.scan_staged(self.fixture.root)
        self.assertEqual((count, findings, suppressed), (4, [], False))

        self.fixture.write("blob-4.bin", b"E")
        self.fixture.stage("blob-4.bin")
        original_git = scanner._git
        content_reads: list[str] = []

        def recording_git(*args, **kwargs):
            arguments = args[1]
            if arguments[:2] == ["cat-file", "blob"]:
                content_reads.append(arguments[2])
            return original_git(*args, **kwargs)

        with mock.patch.object(scanner, "_git", side_effect=recording_git):
            with self.assertRaises(scanner.InspectionError) as raised:
                scanner.scan_staged(self.fixture.root)

        self.assertEqual(raised.exception.operation, "resource-limits")
        self.assertEqual(len(content_reads), 4)

    def test_finding_output_cap_stops_at_twenty_without_a_total(self) -> None:
        """Catches unbounded matching/output and count-bearing suppression summaries."""
        values = [
            b"gh" + b"p_" + f"{index:02d}".encode() + b"A" * 34
            for index in range(21)
        ]
        self.fixture.write("many.txt", b"\n".join(values) + b"\n")
        self.fixture.stage("many.txt")

        result = self.fixture.scan()

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        records = [line for line in result.stdout.splitlines() if line.startswith(b"GITHUB_TOKEN ")]
        self.assertEqual(len(records), 20)
        self.assertIn(b"additional findings suppressed", result.stdout)
        self.assertNotIn(b"21", result.stdout)
        for value in values:
            self.assertNotIn(value, result.stdout + result.stderr)
        self.assert_bounded(result)

    def test_leading_dash_path_is_safe_and_rename_copy_postimages_are_scanned(self) -> None:
        """Catches option confusion and selecting rename/copy preimages instead of postimages."""
        value = github_classic()
        self.fixture.write("-leading.txt", value + b"\n")
        self.fixture.stage("-leading.txt")
        leading = self.fixture.scan()
        self.assertEqual(leading.returncode, 1, leading.stdout + leading.stderr)
        self.assertIn(b"GITHUB_TOKEN -leading.txt:1", leading.stdout)

        renamed = IndexedRepository()
        self.addCleanup(renamed.close)
        body = b"".join(f"ordinary line {index}\n".encode() for index in range(100))
        renamed.write("before.txt", body)
        renamed.stage("before.txt")
        renamed.commit("base rename source")
        git(renamed.root, "mv", "--", "before.txt", "after.txt")
        renamed.write("after.txt", body + value + b"\n")
        renamed.stage("after.txt")
        rename_result = renamed.scan()
        self.assertEqual(rename_result.returncode, 1, rename_result.stdout + rename_result.stderr)
        self.assertIn(b"GITHUB_TOKEN after.txt:101", rename_result.stdout)
        self.assertNotIn(b"before.txt", rename_result.stdout)

        copied = IndexedRepository()
        self.addCleanup(copied.close)
        copied.write("source.txt", body + value + b"\n")
        copied.stage("source.txt")
        copied.commit("base copy source")
        shutil.copyfile(copied.root / "source.txt", copied.root / "copy.txt")
        copied.stage("copy.txt")
        copy_result = copied.scan()
        self.assertEqual(copy_result.returncode, 1, copy_result.stdout + copy_result.stderr)
        self.assertIn(b"GITHUB_TOKEN copy.txt:101", copy_result.stdout)
        self.assertNotIn(b"source.txt", copy_result.stdout)

    @unittest.skipIf(os.name == "nt", "raw control and invalid UTF-8 paths are filesystem-impossible on Windows")
    def test_raw_control_and_invalid_utf8_paths_render_ascii_without_collision(self) -> None:
        """Catches lossy path decoding, line forging, and collisions between raw byte paths."""
        value = github_classic()
        raw_root = os.fsencode(self.fixture.root)
        paths = (b"line\nbreak\tcontrol\x01.txt", b"invalid-\xff.txt", b"invalid-\xfe.txt")
        for path in paths:
            descriptor = os.open(os.path.join(raw_root, path), os.O_WRONLY | os.O_CREAT, 0o600)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(value + b"\n")
        subprocess.run(
            [b"git", b"add", b"--", *paths],
            cwd=raw_root,
            capture_output=True,
            check=True,
        )

        result = self.fixture.scan()

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertTrue(all(byte < 128 for byte in result.stdout + result.stderr))
        self.assertIn(b"line\\x0abreak\\x09control\\x01.txt:1", result.stdout)
        self.assertIn(b"invalid-\\xff.txt:1", result.stdout)
        self.assertIn(b"invalid-\\xfe.txt:1", result.stdout)

    def test_index_only_raw_paths_render_safely_on_every_platform(self) -> None:
        """Catches platform skips hiding byte-parser defects in index-only paths."""
        value = github_classic()
        object_id = self.fixture.hash_blob(value + b"\n")
        paths = (b"line\nbreak\tcontrol\x01.txt", b"invalid-\xff.txt")
        self.fixture.replace_raw_index_records([(path, object_id) for path in paths])

        result = self.fixture.scan()

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertTrue(all(byte < 128 for byte in result.stdout + result.stderr))
        self.assertIn(b"line\\x0abreak\\x09control\\x01.txt:1", result.stdout)
        self.assertIn(b"invalid-\\xff.txt:1", result.stdout)
        self.assertNotIn(value, result.stdout + result.stderr)

    def test_token_family_length_and_ascii_boundaries_are_exact(self) -> None:
        """Catches partial-token matches, off-by-one lengths, and identifier adjacency bypasses."""
        families = (
            (
                "github-classic",
                20,
                255,
                lambda size: b"gh" + b"p_" + shaped_body(size),
                b"GITHUB_TOKEN",
            ),
            (
                "github-fine",
                20,
                255,
                lambda size: b"github_" + b"pat_" + shaped_body(size),
                b"GITHUB_TOKEN",
            ),
            (
                "aws",
                16,
                16,
                lambda size: b"AK" + b"IA" + shaped_body(size),
                b"AWS_ACCESS_KEY_ID",
            ),
            (
                "openai",
                20,
                255,
                lambda size: b"s" + b"k-" + shaped_body(size),
                b"OPENAI_API_KEY",
            ),
            (
                "openai-project",
                20,
                255,
                lambda size: b"s" + b"k-" + b"proj-" + shaped_body(size),
                b"OPENAI_API_KEY",
            ),
            (
                "slack",
                20,
                255,
                lambda size: b"xo" + b"xb-" + shaped_body(size),
                b"SLACK_TOKEN",
            ),
            (
                "bearer",
                20,
                255,
                lambda size: b"Authorization: Bear" + b"er " + shaped_body(size),
                b"BEARER_AUTHORIZATION",
            ),
            (
                "credential-url",
                12,
                255,
                lambda size: b"https://operator:" + shaped_body(size) + b"@example.invalid/path",
                b"CREDENTIAL_URL",
            ),
            (
                "assignment",
                16,
                255,
                lambda size: b"api_" + b"key = \"" + shaped_body(size) + b"\"",
                b"CREDENTIAL_ASSIGNMENT",
            ),
        )
        for label, minimum, maximum, build, rule in families:
            sizes = ((minimum - 1, 0), (minimum, 1), (maximum, 1), (maximum + 1, 0))
            for size, expected in dict(sizes).items():
                with self.subTest(label=label, size=size):
                    fixture = IndexedRepository()
                    self.addCleanup(fixture.close)
                    value = build(size)
                    fixture.write("boundary.txt", value + b"\n")
                    fixture.stage("boundary.txt")

                    result = fixture.scan()

                    self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
                    if expected:
                        self.assertIn(rule + b" boundary.txt:1", result.stdout)
                        self.assertNotIn(value, result.stdout + result.stderr)

            if label not in {"credential-url", "assignment", "bearer"}:
                mutations = (
                    ("leading", b"A" + build(minimum)),
                    ("trailing", build(maximum) + b"A"),
                )
                for edge, mutation in mutations:
                    with self.subTest(label=label, adjacency=edge):
                        fixture = IndexedRepository()
                        self.addCleanup(fixture.close)
                        fixture.write("adjacent.txt", mutation + b"\n")
                        fixture.stage("adjacent.txt")
                        result = fixture.scan()
                        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

        for content in (
            b"A-----BEGIN " + b"PRIVATE KEY-----\n",
            b"-----BEGIN " + b"PRIVATE KEY-----A\n",
        ):
            with self.subTest(label="pem-adjacency"):
                fixture = IndexedRepository()
                self.addCleanup(fixture.close)
                fixture.write("pem.txt", content)
                fixture.stage("pem.txt")
                result = fixture.scan()
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_aws_token_does_not_partially_match_inside_ascii_identifier(self) -> None:
        """Catches lowercase and underscore omissions in AWS token lookarounds."""
        value = aws_access()
        cases = (
            b"x" + value,
            value + b"y",
            b"_" + value,
            value + b"_",
        )
        for index, content in enumerate(cases):
            with self.subTest(index=index):
                fixture = IndexedRepository()
                self.addCleanup(fixture.close)
                fixture.write("identifier.txt", content + b"\n")
                fixture.stage("identifier.txt")

                result = fixture.scan()

                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_promisor_lazy_fetch_cannot_execute_reachable_remote_helper(self) -> None:
        """Catches lazy object fetching or helper execution during missing-blob inspection."""
        source = IndexedRepository()
        self.addCleanup(source.close)
        missing_object = source.hash_blob(b"object available only from the remote").decode("ascii")
        helper = self.fixture.root / "promisor-helper.py"
        marker = self.fixture.root / "promisor-helper-ran.txt"
        helper.write_text(
            "from pathlib import Path\nimport sys\n"
            "Path(sys.argv[1]).write_text('ran', encoding='ascii')\n"
            "raise SystemExit(1)\n",
            encoding="utf-8",
        )
        remote = (
            f"ext::{Path(sys.executable).as_posix()} "
            f"{helper.as_posix()} {marker.as_posix()}"
        )
        git(self.fixture.root, "config", "core.repositoryformatversion", "1")
        git(self.fixture.root, "config", "extensions.partialclone", "origin")
        git(self.fixture.root, "config", "remote.origin.promisor", "true")
        git(self.fixture.root, "config", "remote.origin.partialclonefilter", "blob:none")
        git(self.fixture.root, "config", "remote.origin.url", remote)
        git(
            self.fixture.root,
            "update-index",
            "--add",
            "--info-only",
            "--cacheinfo",
            f"100644,{missing_object},lazy.txt",
        )
        control = git(
            self.fixture.root,
            "-c",
            "protocol.ext.allow=always",
            "cat-file",
            "-t",
            missing_object,
            check=False,
        )
        self.assertNotEqual(control.returncode, 0)
        self.assertTrue(marker.is_file(), "control did not prove the helper was reachable")
        marker.unlink()

        result = self.fixture.scan()

        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn(b"inspect-object", result.stderr)
        self.assertFalse(marker.exists(), "scanner executed the promisor helper")
        self.assertNotIn(missing_object.encode(), result.stdout + result.stderr)

    def test_assignment_grammar_and_exact_placeholder_allowlist(self) -> None:
        """Catches cross-line values, key overmatch, and substring/case placeholder exemptions."""
        exact_placeholders = (
            b"placeholder-value",
            b"example-credential",
            b"not-a-real-secret",
            b"${ACADEMY_TOKEN}",
        )
        for value in exact_placeholders:
            with self.subTest(kind="exact", value_length=len(value)):
                fixture = IndexedRepository()
                self.addCleanup(fixture.close)
                fixture.write("placeholder.txt", b"access_token = \"" + value + b"\"\r\n")
                fixture.stage("placeholder.txt")
                result = fixture.scan()
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

        mutations = (
            b"prefix-placeholder-value",
            b"placeholder-value-suffix",
            b"xplaceholder-valuex",
            b"PLACEHOLDER-VALUE",
            b"${ACADEMY_TOKEN}-suffix",
            b" placeholder-value",
            b"placeholder-value ",
            b" ${ACADEMY_TOKEN} ",
        )
        for value in mutations:
            with self.subTest(kind="mutation", value_length=len(value)):
                fixture = IndexedRepository()
                self.addCleanup(fixture.close)
                fixture.write("mutation.txt", b"Access_Token = '" + value + b"' # local\r\n")
                fixture.stage("mutation.txt")
                result = fixture.scan()
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn(b"CREDENTIAL_ASSIGNMENT mutation.txt:1", result.stdout)
                self.assertNotIn(value, result.stdout + result.stderr)

        clean_grammar = (
            b"xapi_key = \"" + shaped_body(20) + b"\"\n",
            b"api_key_suffix = \"" + shaped_body(20) + b"\"\n",
            b"api_key = \"unterminated\n" + shaped_body(20) + b"\n",
            b"api_key =\r\n" + shaped_body(20) + b"\r\n",
        )
        for content in clean_grammar:
            with self.subTest(kind="grammar"):
                fixture = IndexedRepository()
                self.addCleanup(fixture.close)
                fixture.write("grammar.txt", content)
                fixture.stage("grammar.txt")
                result = fixture.scan()
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_bom_utf16le_and_utf16be_detect_with_stable_line_numbers(self) -> None:
        """Catches raw-ASCII-only scanning of realistic Windows encoded secrets."""
        token = github_classic().decode("ascii")
        text = "ordinary first line\r\n" + token + "\r\n"
        cases = (
            ("le", b"\xff\xfe" + text.encode("utf-16-le")),
            ("be", b"\xfe\xff" + text.encode("utf-16-be")),
        )
        for label, content in cases:
            with self.subTest(label=label):
                fixture = IndexedRepository()
                self.addCleanup(fixture.close)
                fixture.write("encoded.txt", content)
                fixture.stage("encoded.txt")
                result = fixture.scan()
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn(b"GITHUB_TOKEN encoded.txt:2", result.stdout)
                self.assertNotIn(token.encode(), result.stdout + result.stderr)

    def test_malformed_bom_utf16_fails_closed_and_clean_unicode_passes(self) -> None:
        """Catches permissive decoding that turns malformed declared text into a clean result."""
        for label, content in (
            ("odd-le", b"\xff\xfeA"),
            ("surrogate-be", b"\xfe\xff\xd8\x00"),
        ):
            with self.subTest(label=label):
                fixture = IndexedRepository()
                self.addCleanup(fixture.close)
                fixture.write("malformed.txt", content)
                fixture.stage("malformed.txt")
                result = fixture.scan()
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertIn(b"decode-utf16", result.stderr)

        clean = IndexedRepository()
        self.addCleanup(clean.close)
        clean.write("clean-utf16.txt", b"\xff\xfe" + "Academy safety notes\n".encode("utf-16-le"))
        clean.stage("clean-utf16.txt")
        result = clean.scan()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_bounded_runner_caps_metadata_stderr_and_timeout_with_inert_helper(self) -> None:
        """Catches unbounded Git metadata/stderr capture and missing process timeout."""
        scanner = load_scanner_module()
        for mode in ("stdout", "stderr", "timeout"):
            with self.subTest(mode=mode):
                fixture = IndexedRepository()
                self.addCleanup(fixture.close)
                helper_directory = fixture.root / f"helper-{mode}"
                helper_directory.mkdir()
                helper = helper_directory / "helper.py"
                marker = helper_directory / "invoked.txt"
                if mode == "stdout":
                    body = (
                        "from pathlib import Path\nimport sys\n"
                        "Path(sys.argv[1]).write_text('stdout', encoding='ascii')\n"
                        "sys.stdout.buffer.write(b'x' * 4097)\n"
                    )
                elif mode == "stderr":
                    body = (
                        "from pathlib import Path\nimport sys\n"
                        "Path(sys.argv[1]).write_text('stderr', encoding='ascii')\n"
                        "sys.stderr.buffer.write(b'x' * 65537)\n"
                    )
                else:
                    body = (
                        "from pathlib import Path\nimport sys, time\n"
                        "Path(sys.argv[1]).write_text('timeout', encoding='ascii')\n"
                        "time.sleep(20)\n"
                    )
                helper.write_text(body, encoding="utf-8")

                with self.assertRaises(scanner.InspectionError) as raised:
                    scanner._bounded_process(
                        fixture.root,
                        [sys.executable, str(helper), str(marker)],
                        "bounded-helper",
                        max_stdout=4096,
                    )

                self.assertEqual(raised.exception.operation, "resource-limits")
                self.assertTrue(marker.is_file(), "the inert helper was not invoked")
                self.assertEqual(marker.read_text(encoding="ascii"), mode)

    def test_bounded_runner_terminates_pipe_inheriting_descendant_within_limit(self) -> None:
        """Catches direct-child timeout handling that hangs on descendant-held pipes."""
        scanner = load_scanner_module()
        scanner.GIT_TIMEOUT_SECONDS = 1
        helper = self.fixture.root / "descendant-helper.py"
        helper.write_text(
            "import subprocess, sys, time\n"
            "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(5)'])\n"
            "time.sleep(5)\n",
            encoding="utf-8",
        )
        started = time.monotonic()

        with self.assertRaises(scanner.InspectionError) as raised:
            scanner._bounded_process(
                self.fixture.root,
                [sys.executable, str(helper)],
                "descendant-helper",
                max_stdout=4096,
            )

        elapsed = time.monotonic() - started
        self.assertEqual(raised.exception.operation, "resource-limits")
        self.assertLess(elapsed, 3.0, f"process tree cleanup took {elapsed:.2f}s")


if __name__ == "__main__":
    unittest.main()
