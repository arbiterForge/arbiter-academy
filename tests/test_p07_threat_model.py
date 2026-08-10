from __future__ import annotations

import hashlib
import shutil
import subprocess
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

import academy_engine.checkpoints as installed_checkpoints
from academy_engine.checkpoints import evaluate_checkpoint
from academy_engine.scenario import prepare_lab


LAB_ID = "P07-threat-model"
REPORT_PATH = ".codearbiter/reports/academy/P07-threat-model.md"
TARGET_PATH = "academy_engine/paths.py"
TARGET_BLOB = "b36801add4eb375f796d1107ee63dd604d08a034"
TARGET_SHA256 = "e40a7655ce6ba6cde58a91ae10a714f10046c055ac90dcbc58f0696c39133a5d"

P07_INTENDED_REPORT = b"""# P07 Threat Model - Archive import containment boundary

## Scope
This review covers academy_engine/paths.py handling learner-controlled archive-member destinations beneath the selected repository root.
The boundary must prove containment before a destination write.

## STRIDE findings
| Threat | Category | Likelihood | Impact | Control |
| --- | --- | --- | --- | --- |
| Archive-member provenance could be mistaken for authenticated identity | S | L | M | N/A: local archive input has no authenticated principal at this boundary. |
| Traversal could overwrite a destination outside the repository root | T | H | H | PRESENT: destination resolution rejects parent traversal before copying. |
| A local learner could dispute which archive member supplied a path | R | L | L | GAP: retain bounded import provenance before future automation. |
| A containment error could expose a resolved repository location | I | M | M | PRESENT: bounded path errors omit the resolved destination. |
| Oversized archive path sets could exhaust repeated validation work | D | M | M | PLANNED: bound member count and path length before extraction. |
| A reparse-point ancestor could cross into a privileged destination | E | H | H | PRESENT: symlink and reparse-point ancestors fail before a write. |

## Recommended controls before implementation
- Keep destination resolution under the selected repository root before creating or copying a file.
- Reject absolute, traversal, symlink, and Windows reparse-point ancestors in archive destinations.
- Fail closed on a different drive or an unrepresentable containment path before any write.

## Clearance
CLEAR TO IMPLEMENT

## Academy Target-SHA256/identity binding
Academy-Target-Path: academy_engine/paths.py
Academy-Target-Prepared-Blob: b36801add4eb375f796d1107ee63dd604d08a034
Academy-Target-Head-Blob: b36801add4eb375f796d1107ee63dd604d08a034
Academy-Target-SHA256: e40a7655ce6ba6cde58a91ae10a714f10046c055ac90dcbc58f0696c39133a5d
"""

P07_EQUIVALENT_REPORT = b"""# P07 Threat Model - Archive import containment boundary

## Scope
This review covers academy_engine/paths.py handling learner-supplied archive-member destinations before copying a file beneath the selected repository root.
The boundary resolves the destination and rejects an escape before a destination write.

## STRIDE findings
| Threat | Category | Likelihood | Impact | Control |
| --- | --- | --- | --- | --- |
| Archive member naming could suggest a trusted source | S | L | M | N/A: archive member text carries no authenticated principal at this local boundary. |
| A traversal destination could overwrite a file outside the repository root | T | H | H | PRESENT: ensure_within rejects traversal, symlink, and reparse-point ancestors. |
| A learner cannot later attribute an archive member to a remote actor | R | L | L | N/A: this local path boundary has no remote actor or audit identity. |
| A path failure could disclose a repository location | I | M | M | PRESENT: PathBoundaryError returns a bounded reason without a resolved path. |
| Excessive archive members could exhaust destination validation work | D | M | M | PLANNED: bound archive member count and path length before repeated resolution. |
| A reparse-point destination could cross into a more privileged location | E | H | H | PRESENT: reparse-point ancestor rejection stops the destination write. |

## Recommended controls before implementation
- Keep destination resolution under the selected repository root before creating or copying a file.
- Reject absolute, traversal, symlink, and Windows reparse-point ancestors in archive destinations.
- Fail closed on a different drive or an unrepresentable containment path before any write.

## Clearance
BLOCKED - resolve findings first

## Academy Target-SHA256/identity binding
Academy-Target-Path: academy_engine/paths.py
Academy-Target-Prepared-Blob: b36801add4eb375f796d1107ee63dd604d08a034
Academy-Target-Head-Blob: b36801add4eb375f796d1107ee63dd604d08a034
Academy-Target-SHA256: e40a7655ce6ba6cde58a91ae10a714f10046c055ac90dcbc58f0696c39133a5d
"""


def git(root: Path, *arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *arguments],
        cwd=root,
        check=check,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


class P07ThreatModelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source = Path(__file__).resolve().parents[1]
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)

    def _repository(self) -> tuple[Path, str, str]:
        root = Path(self.temporary.name) / f"repo-{len(tuple(Path(self.temporary.name).iterdir()))}"
        root.mkdir()
        for relative in ("academy", "academy_engine", "scripts"):
            shutil.copytree(
                self.source / relative,
                root / relative,
                ignore=shutil.ignore_patterns("__pycache__"),
            )
        git(root, "init", "-b", "main")
        git(root, "config", "user.name", "Academy Learner")
        git(root, "config", "user.email", "learner@example.invalid")
        git(root, "add", "academy", "academy_engine", "scripts")
        git(root, "commit", "-m", "base")
        git(root, "remote", "add", "origin", "https://github.com/learner/arbiter-academy.git")
        git(root, "remote", "add", "upstream", "https://github.com/arbiterForge/arbiter-academy.git")
        git(root, "remote", "set-url", "--push", "upstream", "DISABLED")
        base = git(root, "rev-parse", "HEAD").stdout.strip()
        prepared = prepare_lab(root, LAB_ID, installed_authority=True)
        self.assertEqual(prepared.base_sha, base)
        self.assertEqual(
            git(root, "rev-parse", f"{prepared.commit_sha}:{TARGET_PATH}").stdout.strip(),
            TARGET_BLOB,
        )
        return root, base, prepared.commit_sha

    def _commit(
        self,
        root: Path,
        paths: tuple[str, ...],
        subject: str,
        *,
        allow_empty: bool = False,
    ) -> str:
        if paths:
            git(root, "-c", "core.autocrlf=false", "add", "--", *paths)
        arguments = ["commit"]
        if allow_empty:
            arguments.append("--allow-empty")
        arguments.extend(("-m", subject))
        git(root, *arguments)
        return git(root, "rev-parse", "HEAD").stdout.strip()

    def _write_report(self, root: Path, raw: bytes) -> None:
        path = root / REPORT_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)

    def _commit_report(self, root: Path, raw: bytes, subject: str = "learner: record P07 threat model") -> str:
        self._write_report(root, raw)
        return self._commit(root, (REPORT_PATH,), subject)

    def _assert_fails(self, root: Path) -> None:
        result = evaluate_checkpoint(root, LAB_ID)
        self.assertFalse(result.passed, result.passed_predicates)
        evidence = repr(asdict(result))
        self.assertNotIn(str(root), evidence)
        self.assertNotIn("C:\\", evidence)
        self.assertNotIn("C:/", evidence)

    def _assert_full_checkpoint_rejects(
        self, raw: bytes, *, canary: bytes | None = None
    ) -> None:
        root, _base, _prepared = self._repository()
        self._commit_report(root, raw)

        result = evaluate_checkpoint(root, LAB_ID)
        evidence = repr(asdict(result))
        self.assertNotIn(str(root), evidence)
        self.assertNotIn("C:\\", evidence)
        self.assertNotIn("C:/", evidence)
        if canary is not None:
            self.assertNotIn(canary.decode("ascii"), evidence)
        self.assertFalse(result.passed, result.passed_predicates)

    def test_p07_full_checkpoint_rejects_a_committed_pem_private_key(self) -> None:
        canary = b"P07AcademyCanaryNotARealPrivateKey"
        report = P07_INTENDED_REPORT.replace(
            b"The boundary must prove containment before a destination write.\n",
            b"The boundary must prove containment before a destination write.\n"
            b"-----BEGIN " + b"PRIVATE KEY-----\n"
            + canary
            + b"\n-----END PRIVATE KEY-----\n",
        )

        self._assert_full_checkpoint_rejects(report, canary=canary)

    def test_p07_full_checkpoint_rejects_an_encrypted_pem_private_key(self) -> None:
        canary = b"P07AcademyEncryptedCanaryNotARealPrivateKey"
        report = P07_INTENDED_REPORT.replace(
            b"The boundary must prove containment before a destination write.\n",
            b"The boundary must prove containment before a destination write.\n"
            b"-----BEGIN " + b"ENCRYPTED PRIVATE KEY-----\n"
            + canary
            + b"\n-----END ENCRYPTED PRIVATE KEY-----\n",
        )

        self._assert_full_checkpoint_rejects(report, canary=canary)

    def test_p07_full_checkpoint_fails_closed_when_history_status_fails(self) -> None:
        root, _base, _prepared = self._repository()
        self._commit_report(root, P07_INTENDED_REPORT)
        self.assertTrue(evaluate_checkpoint(root, LAB_ID).passed)
        real_run_git = installed_checkpoints.run_git
        canary = "P07-history-status-error-canary"

        def fail_history_status(
            repository: Path,
            arguments: list[str],
            **options: object,
        ) -> subprocess.CompletedProcess[str]:
            if arguments == ["status", "--porcelain", "--untracked-files=all"]:
                return subprocess.CompletedProcess(
                    ["git", *arguments], 1, stdout="", stderr=canary
                )
            return real_run_git(repository, arguments, **options)

        with patch.object(installed_checkpoints, "run_git", side_effect=fail_history_status):
            result = evaluate_checkpoint(root, LAB_ID)

        evidence = repr(asdict(result))
        self.assertNotIn(canary, evidence)
        self.assertNotIn(str(root), evidence)
        self.assertFalse(result.passed, result.passed_predicates)

    def test_p07_full_checkpoint_fails_closed_when_control_status_fails(self) -> None:
        root, _base, _prepared = self._repository()
        self._commit_report(root, P07_INTENDED_REPORT)
        self.assertTrue(evaluate_checkpoint(root, LAB_ID).passed)
        real_run_git = installed_checkpoints.run_git
        canary = "P07-control-status-error-canary"

        def fail_control_status(
            repository: Path,
            arguments: list[str],
            **options: object,
        ) -> subprocess.CompletedProcess[str]:
            if arguments[:3] == ["status", "--porcelain", "--untracked-files=all"] and "--" in arguments:
                return subprocess.CompletedProcess(
                    ["git", *arguments], 1, stdout="", stderr=canary
                )
            return real_run_git(repository, arguments, **options)

        with patch.object(installed_checkpoints, "run_git", side_effect=fail_control_status):
            result = evaluate_checkpoint(root, LAB_ID)

        evidence = repr(asdict(result))
        self.assertNotIn(canary, evidence)
        self.assertNotIn(str(root), evidence)
        self.assertFalse(result.passed, result.passed_predicates)

    def test_p07_full_checkpoint_rejects_a_bare_actor_command_claim(self) -> None:
        report = P07_INTENDED_REPORT.replace(
            b"The boundary must prove containment before a destination write.",
            b"The boundary must prove containment before a destination write.\n"
            b"I executed the command successfully.",
        )

        self._assert_full_checkpoint_rejects(report)

    def test_p07_full_checkpoint_rejects_category_free_sympathy_rows(self) -> None:
        prefix, separator, remainder = P07_INTENDED_REPORT.partition(
            b"## STRIDE findings\n"
        )
        self.assertTrue(separator)
        _old_table, separator, suffix = remainder.partition(
            b"\n## Recommended controls before implementation\n"
        )
        self.assertTrue(separator)
        table = b"""| Threat | Category | Likelihood | Impact | Control |
| --- | --- | --- | --- | --- |
| Sympathy issue one | S | L | L | N/A: path is not applicable to this local boundary. |
| Sympathy issue two | T | L | L | N/A: path is not applicable to this local boundary. |
| Sympathy issue three | R | L | L | N/A: path is not applicable to this local boundary. |
| Sympathy issue four | I | L | L | N/A: path is not applicable to this local boundary. |
| Sympathy issue five | D | L | L | N/A: path is not applicable to this local boundary. |
| Sympathy issue six | E | L | L | N/A: path is not applicable to this local boundary. |

"""
        report = (
            prefix
            + b"## STRIDE findings\n"
            + table
            + b"## Recommended controls before implementation\n"
            + suffix
        )

        self._assert_full_checkpoint_rejects(report)

    def test_p07_native_rows_require_category_specific_semantics(self) -> None:
        prefix, separator, remainder = P07_INTENDED_REPORT.partition(
            b"## STRIDE findings\n"
        )
        self.assertTrue(separator)
        _old_table, separator, suffix = remainder.partition(
            b"\n## Recommended controls before implementation\n"
        )
        self.assertTrue(separator)
        table = b"""| Threat | Category | Likelihood | Impact | Control |
| --- | --- | --- | --- | --- |
| Path issue one | S | L | L | N/A: path is not applicable to this local boundary. |
| Path issue two | T | L | L | N/A: path is not applicable to this local boundary. |
| Path issue three | R | L | L | N/A: path is not applicable to this local boundary. |
| Path issue four | I | L | L | N/A: path is not applicable to this local boundary. |
| Path issue five | D | L | L | N/A: path is not applicable to this local boundary. |
| Path issue six | E | L | L | N/A: path is not applicable to this local boundary. |

"""
        report = (
            prefix
            + b"## STRIDE findings\n"
            + table
            + b"## Recommended controls before implementation\n"
            + suffix
        )

        sections = installed_checkpoints._p07_sections(report)
        self.assertIsNotNone(sections)
        self.assertFalse(installed_checkpoints._p07_native_conversation(sections or {}))

    def test_p07_full_checkpoint_rejects_scope_terms_hidden_in_html_comments(self) -> None:
        original = (
            b"This review covers academy_engine/paths.py handling learner-controlled "
            b"archive-member destinations beneath the selected repository root.\n"
            b"The boundary must prove containment before a destination write."
        )
        hidden = (
            b"No security boundary was analyzed.\n"
            b"<!-- academy_engine/paths.py archive-member destination repository root "
            b"containment before destination write -->"
        )
        report = P07_INTENDED_REPORT.replace(original, hidden)

        self._assert_full_checkpoint_rejects(report)

    def test_p07_full_checkpoint_rejects_scope_terms_hidden_in_link_metadata(self) -> None:
        original = (
            b"This review covers academy_engine/paths.py handling learner-controlled "
            b"archive-member destinations beneath the selected repository root.\n"
            b"The boundary must prove containment before a destination write."
        )
        hidden = (
            b"No security boundary was analyzed. "
            b"[review](academy_engine/paths.py \"archive-member repository root "
            b"containment before destination write\")"
        )
        report = P07_INTENDED_REPORT.replace(original, hidden)

        self._assert_full_checkpoint_rejects(report)

    def test_p07_full_checkpoint_rejects_modified_and_confusable_command_claims(self) -> None:
        original = b"The boundary must prove containment before a destination write."
        cases = {
            "unlisted-adverb": (
                b"The boundary must prove containment before a destination write.\n"
                b"I definitely executed the command successfully."
            ),
            "unicode-confusable": (
                "The boundary must prove containment before a destination write.\n"
                "I executed the c\u043emmand successfully."
            ).encode("utf-8"),
        }
        for label, replacement in cases.items():
            with self.subTest(label=label):
                self._assert_full_checkpoint_rejects(
                    P07_INTENDED_REPORT.replace(original, replacement)
                )

    def test_p07_full_checkpoint_requires_category_meaning_in_each_threat_cell(self) -> None:
        prefix, separator, remainder = P07_INTENDED_REPORT.partition(
            b"## STRIDE findings\n"
        )
        self.assertTrue(separator)
        _old_table, separator, suffix = remainder.partition(
            b"\n## Recommended controls before implementation\n"
        )
        self.assertTrue(separator)
        table = b"""| Threat | Category | Likelihood | Impact | Control |
| --- | --- | --- | --- | --- |
| Archive path issue one | S | L | L | N/A: authenticated identity is not present at this boundary. |
| Archive path issue two | T | L | L | PRESENT: traversal integrity checks reject an unsafe destination. |
| Archive path issue three | R | L | L | GAP: audit attribution needs a bounded provenance record. |
| Archive path issue four | I | L | L | PRESENT: confidentiality controls omit the resolved location. |
| Archive path issue five | D | L | L | PLANNED: availability limits bound excessive resource consumption. |
| Archive path issue six | E | L | L | PRESENT: privilege authorization rejects reparse-point ancestors. |

"""
        report = (
            prefix
            + b"## STRIDE findings\n"
            + table
            + b"## Recommended controls before implementation\n"
            + suffix
        )

        self._assert_full_checkpoint_rejects(report)

    def test_p07_full_checkpoint_rejects_threat_metadata_and_bare_category_rows(self) -> None:
        metadata = P07_INTENDED_REPORT.replace(
            b"Archive-member provenance could be mistaken for authenticated identity",
            b"Archive path [issue](authentication)",
        )
        prefix, separator, remainder = P07_INTENDED_REPORT.partition(
            b"## STRIDE findings\n"
        )
        self.assertTrue(separator)
        _old_table, separator, suffix = remainder.partition(
            b"\n## Recommended controls before implementation\n"
        )
        self.assertTrue(separator)
        bare_table = b"""| Threat | Category | Likelihood | Impact | Control |
| --- | --- | --- | --- | --- |
| Archive path identity | S | L | M | N/A: local archive input has no authenticated principal at this boundary. |
| Archive path overwrite | T | H | H | PRESENT: destination resolution rejects parent traversal before copying. |
| Archive path audit | R | L | L | GAP: retain bounded import provenance before future automation. |
| Archive path disclose | I | M | M | PRESENT: bounded path errors omit the resolved destination. |
| Archive path resource | D | M | M | PLANNED: bound member count and path length before extraction. |
| Archive path privilege | E | H | H | PRESENT: symlink and reparse-point ancestors fail before a write. |

"""
        bare = (
            prefix
            + b"## STRIDE findings\n"
            + bare_table
            + b"## Recommended controls before implementation\n"
            + suffix
        )

        for label, report in (("metadata", metadata), ("bare-category-rows", bare)):
            with self.subTest(label=label):
                self._assert_full_checkpoint_rejects(report)

    def test_p07_full_checkpoint_rejects_unbounded_execution_claim_forms(self) -> None:
        original = b"The boundary must prove containment before a destination write."
        claims = (
            b"I performed the command successfully.",
            b"I certainly definitely undoubtedly plainly actually really executed the command successfully.",
            b"I completed the host command successfully.",
            b"The host command was performed successfully.",
            b"I deliberately carefully slowly methodically thoroughly definitely executed the command.",
        )
        for claim in claims:
            with self.subTest(claim=claim):
                report = P07_INTENDED_REPORT.replace(
                    original, original + b"\n" + claim
                )
                self._assert_full_checkpoint_rejects(report)

    def test_p07_full_checkpoint_requires_affirmative_scope_relationships(self) -> None:
        original = (
            b"This review covers academy_engine/paths.py handling learner-controlled "
            b"archive-member destinations beneath the selected repository root.\n"
            b"The boundary must prove containment before a destination write."
        )
        cases = (
            b"academy_engine/paths.py does not handle learner-controlled archive-member "
            b"destinations beneath the selected repository root.\n"
            b"There is no containment before a destination write.",
            b"academy_engine/paths.py archive-member repository root containment before "
            b"destination write",
        )
        for scope in cases:
            with self.subTest(scope=scope):
                self._assert_full_checkpoint_rejects(
                    P07_INTENDED_REPORT.replace(original, scope)
                )

    def test_p07_full_checkpoint_rejects_academy_cli_execution_claim(self) -> None:
        original = b"The boundary must prove containment before a destination write."
        report = P07_INTENDED_REPORT.replace(
            original,
            original + b"\nI executed the Academy CLI successfully.",
        )

        self._assert_full_checkpoint_rejects(report)

    def test_p07_full_checkpoint_rejects_polarity_and_markdown_evasions(self) -> None:
        original_scope = (
            b"This review covers academy_engine/paths.py handling learner-controlled "
            b"archive-member destinations beneath the selected repository root."
        )
        original_threat = (
            b"Archive-member provenance could be mistaken for authenticated identity"
        )
        cases = {
            "contracted-scope-negation": P07_INTENDED_REPORT.replace(
                original_scope,
                original_scope[:-1] + b", but doesn't validate them.",
            ),
            "negated-threat": P07_INTENDED_REPORT.replace(
                original_threat,
                b"Archive-member provenance could not be mistaken for authenticated identity",
            ),
            "struck-through-threat": P07_INTENDED_REPORT.replace(
                original_threat,
                b"Archive input could ~~spoof~~ authenticated identity",
            ),
        }
        for label, report in cases.items():
            with self.subTest(label=label):
                self._assert_full_checkpoint_rejects(report)

    def test_p07_full_checkpoint_rejects_third_person_academy_cli_outcome(self) -> None:
        original = b"The boundary must prove containment before a destination write."
        report = P07_INTENDED_REPORT.replace(
            original,
            original + b"\nThe Academy CLI completed successfully.",
        )

        self._assert_full_checkpoint_rejects(report)

    def test_p07_full_checkpoint_rejects_fail_family_polarity(self) -> None:
        original_scope = b"The boundary must prove containment before a destination write."
        original_threat = (
            b"Traversal could overwrite a destination outside the repository root"
        )
        cases = {
            "failed-scope": P07_INTENDED_REPORT.replace(
                original_scope,
                b"The boundary failed to prove containment before a destination write.",
            ),
            "failed-threat": P07_INTENDED_REPORT.replace(
                original_threat,
                b"Traversal could fail to overwrite a destination outside the repository root",
            ),
        }
        for label, report in cases.items():
            with self.subTest(label=label):
                self._assert_full_checkpoint_rejects(report)

    def test_p07_full_checkpoint_rejects_single_delimiter_markdown_emphasis(self) -> None:
        original = b"Traversal could overwrite a destination outside the repository root"
        for marker in (b"*overwrite*", b"_overwrite_"):
            with self.subTest(marker=marker):
                self._assert_full_checkpoint_rejects(
                    P07_INTENDED_REPORT.replace(
                        original,
                        b"Traversal could " + marker + b" a destination outside the repository root",
                    )
                )

    def test_p07_r5_filters_preserve_domain_assertion_repudiation_and_path_underscores(self) -> None:
        report = P07_EQUIVALENT_REPORT.replace(
            b"The boundary resolves the destination and rejects an escape before a destination write.",
            b"The boundary successfully rejects an escape before a destination write.",
        )
        root, _base, _prepared = self._repository()
        self._commit_report(root, report)

        result = evaluate_checkpoint(root, LAB_ID)

        self.assertTrue(result.passed, result.failed_predicates)

    def test_p07_full_checkpoint_rejects_realized_authority_completion_in_every_native_field(self) -> None:
        scope_line = b"The boundary must prove containment before a destination write."
        threat = b"Traversal could overwrite a destination outside the repository root"
        control = b"PRESENT: destination resolution rejects parent traversal before copying."
        cases = {
            "scope-academy-cli": P07_INTENDED_REPORT.replace(
                scope_line,
                scope_line + b"\nThe Academy CLI completed.",
            ),
            "scope-equivalent-authority": P07_INTENDED_REPORT.replace(
                scope_line,
                scope_line + b"\nThe Academy verifier completed.",
            ),
            "threat": P07_INTENDED_REPORT.replace(
                threat,
                threat + b". The Academy CLI completed",
            ),
            "control": P07_INTENDED_REPORT.replace(
                control,
                b"PRESENT: The Academy CLI completed before destination validation.",
            ),
        }
        for label, report in cases.items():
            with self.subTest(label=label):
                self._assert_full_checkpoint_rejects(report)

    def test_p07_full_checkpoint_rejects_negated_adverse_repudiation(self) -> None:
        report = P07_INTENDED_REPORT.replace(
            b"A local learner could dispute which archive member supplied a path",
            b"A local learner could not dispute archive path attribution",
        )

        self._assert_full_checkpoint_rejects(report)

    def test_p07_authority_hypothetical_and_accountability_gap_remain_valid(self) -> None:
        scope_line = (
            b"The boundary resolves the destination and rejects an escape before a destination write."
        )
        report = P07_EQUIVALENT_REPORT.replace(
            scope_line,
            scope_line
            + b"\nThe Academy CLI could run if future automation is added."
            + b"\nThe installed verifier could run if future automation is added.",
        )
        root, _base, _prepared = self._repository()
        self._commit_report(root, report)

        result = evaluate_checkpoint(root, LAB_ID)

        self.assertTrue(result.passed, result.failed_predicates)

    def test_p07_full_checkpoint_rejects_generic_verifier_completion_in_every_native_field(self) -> None:
        scope_line = b"The boundary must prove containment before a destination write."
        threat = b"Traversal could overwrite a destination outside the repository root"
        control = b"PRESENT: destination resolution rejects parent traversal before copying."
        cases = {
            "scope-installed-verifier": P07_INTENDED_REPORT.replace(
                scope_line,
                scope_line + b"\nThe installed verifier completed.",
            ),
            "scope-checker": P07_INTENDED_REPORT.replace(
                scope_line,
                scope_line + b"\nThe checker completed.",
            ),
            "threat": P07_INTENDED_REPORT.replace(
                threat,
                threat + b". The installed verifier completed",
            ),
            "control": P07_INTENDED_REPORT.replace(
                control,
                b"PRESENT: The checker completed before destination validation.",
            ),
        }
        for label, report in cases.items():
            with self.subTest(label=label):
                self._assert_full_checkpoint_rejects(report)

    def test_p07_intended_native_conversation_passes(self) -> None:
        root, _base, _prepared = self._repository()
        intended = self._commit_report(root, P07_INTENDED_REPORT)
        intended_blob = git(root, "rev-parse", f"{intended}:{REPORT_PATH}").stdout.strip()

        self.assertTrue(Path(installed_checkpoints.__file__).resolve().is_relative_to(self.source))
        self.assertFalse(Path(installed_checkpoints.__file__).resolve().is_relative_to(root))
        self.assertTrue(intended_blob)
        self.assertNotEqual(intended_blob, "d45e822f1816f3ebd712e6e918b258ac3cb8389b")
        result = evaluate_checkpoint(root, LAB_ID)
        self.assertTrue(result.passed, result.failed_predicates)

    def test_p07_equivalent_concrete_stride_content_passes(self) -> None:
        self.assertEqual(len(P07_EQUIVALENT_REPORT), 2076)
        self.assertEqual(
            hashlib.sha256(P07_EQUIVALENT_REPORT).hexdigest(),
            "247e79171bbfa7da511e3c8459a49f6e5a73d2b492db91253df9eba10f88e9f7",
        )
        root, _base, _prepared = self._repository()
        commit = self._commit_report(root, P07_EQUIVALENT_REPORT)
        self.assertEqual(
            git(root, "rev-parse", f"{commit}:{REPORT_PATH}").stdout.strip(),
            "d45e822f1816f3ebd712e6e918b258ac3cb8389b",
        )
        result = evaluate_checkpoint(root, LAB_ID)
        self.assertTrue(result.passed, result.failed_predicates)

    def test_p07_untouched_partial_and_wrong_evidence_fail(self) -> None:
        root, _base, _prepared = self._repository()
        self._assert_fails(root)

        for label, report in (
            ("partial", b"# P07 Threat Model - Archive import containment boundary\n"),
            ("wrong", P07_INTENDED_REPORT.replace(b"academy_engine/paths.py", b"workshop_queue/cli.py")),
        ):
            with self.subTest(label=label):
                root, _base, _prepared = self._repository()
                self._commit_report(root, report)
                self._assert_fails(root)

    def test_p07_rejects_missing_reordered_or_generic_stride_rows(self) -> None:
        cases = {
            "missing": P07_INTENDED_REPORT.replace(
                b"| A reparse-point ancestor could cross into a privileged destination | E | H | H | PRESENT: symlink and reparse-point ancestors fail before a write. |\n",
                b"",
            ),
            "reordered": P07_INTENDED_REPORT.replace(b"| S | L | M |", b"| T | L | M |", 1),
            "generic": P07_INTENDED_REPORT.replace(
                b"Archive-member provenance could be mistaken for authenticated identity",
                b"Generic threat",
            ),
        }
        for label, report in cases.items():
            with self.subTest(label=label):
                root, _base, _prepared = self._repository()
                self._commit_report(root, report)
                self._assert_fails(root)

    def test_p07_rejects_native_academy_field_mixing_and_invocation_claims(self) -> None:
        cases = {
            "mixed": P07_INTENDED_REPORT.replace(
                b"The boundary must prove containment before a destination write.\n",
                b"The boundary must prove containment before a destination write.\nAcademy-Target-Path: academy_engine/paths.py\n",
            ),
            "invocation": P07_INTENDED_REPORT.replace(
                b"The boundary must prove containment before a destination write.",
                b"The boundary proves that $ca-threat-model was invoked before a destination write.",
            ),
            "duplicate-native": P07_INTENDED_REPORT + b"## Scope\nduplicate\n",
        }
        for label, report in cases.items():
            with self.subTest(label=label):
                root, _base, _prepared = self._repository()
                self._commit_report(root, report)
                self._assert_fails(root)

    def test_p07_rejects_forbidden_native_command_structure_and_execution_claims(self) -> None:
        original = b"The boundary must prove containment before a destination write."
        cases = {
            "plain-command": b"The ca-threat-model review covers containment before a destination write.",
            "first-person-invocation": b"I invoked ca-threat-model successfully before a destination write.",
            "reproduced-skill-bypass": b"I used the threat-model skill successfully before proving containment before a destination write.",
            "host-completed": b"The host command completed before the containment destination write.",
            "host-ran": b"The host command ran before the containment destination write.",
            "route-reference": b"The /ca:threat-model route covers containment before a destination write.",
            "command-reference": b"The ca-threat-model command covers containment before a destination write.",
            "duplicate-scope-heading": b"## Scope\nThe boundary must prove containment before a destination write.",
        }
        for label, replacement in cases.items():
            with self.subTest(label=label):
                root, _base, _prepared = self._repository()
                self._commit_report(root, P07_INTENDED_REPORT.replace(original, replacement))
                self._assert_fails(root)

    def test_p07_native_invocation_claim_filter_is_contextual(self) -> None:
        original = b"The boundary must prove containment before a destination write."
        negatives = (
            b"The threat-model skill completed before proving containment before a destination write.",
            b"The host invocation succeeded before proving containment before a destination write.",
            b"We used the host tool before proving containment before a destination write.",
            b"The threat-model skill was run before proving containment before a destination write.",
            b"The host tool was executed before proving containment before a destination write.",
        )
        for replacement in negatives:
            with self.subTest(replacement=replacement):
                sections = installed_checkpoints._p07_sections(
                    P07_INTENDED_REPORT.replace(original, replacement)
                )
                self.assertIsNotNone(sections)
                self.assertFalse(installed_checkpoints._p07_native_conversation(sections or {}))

        positive = P07_INTENDED_REPORT.replace(
            original,
            b"The boundary uses skillful analysis and proves containment for "
            b"command-related threats before a destination write.",
        ).replace(
            b"Traversal could overwrite a destination outside the repository root",
            b"A command invocation threat could overwrite an archive destination outside the repository root",
        )
        sections = installed_checkpoints._p07_sections(positive)
        self.assertIsNotNone(sections)
        self.assertTrue(installed_checkpoints._p07_native_conversation(sections or {}))

        root, _base, _prepared = self._repository()
        self._commit_report(root, positive)
        result = evaluate_checkpoint(root, LAB_ID)
        self.assertTrue(result.passed, result.failed_predicates)

    def test_p07_rejects_stride_cell_host_execution_outcome_claims(self) -> None:
        cases = {
            "reproduced-control": P07_INTENDED_REPORT.replace(
                b"PRESENT: destination resolution rejects parent traversal before copying.",
                b"PRESENT: the host tool was executed successfully before archive destination validation.",
            ),
            "equivalent-threat": P07_INTENDED_REPORT.replace(
                b"Archive-member provenance could be mistaken for authenticated identity",
                b"The host command was run successfully before archive destination validation",
            ),
        }
        for label, report in cases.items():
            with self.subTest(label=label):
                sections = installed_checkpoints._p07_sections(report)
                self.assertIsNotNone(sections)
                root, _base, _prepared = self._repository()
                self._commit_report(root, report)
                self._assert_fails(root)

    def test_p07_invocation_claim_truth_table(self) -> None:
        rejected = (
            ("scope", "$ca-threat-model"),
            ("scope", "/ca:threat-model"),
            ("scope", "/ca-threat-model"),
            ("scope", "/skill:ca-threat-model"),
            ("scope", "ca-threat-model"),
            ("scope", "I used the threat-model skill successfully"),
            ("scope", "We successfully ran the host tool"),
            ("scope", "The host command completed"),
            ("scope", "The host tool has executed successfully"),
            ("scope", "The tool successfully executed"),
            ("scope", "The host invocation was successful"),
            ("scope", "The host tool execution succeeded"),
            ("scope", "The threat-model skill was run"),
            ("scope", "The command was executed successfully"),
            ("scope", "The tool completed successfully"),
            ("scope", "I ran the command"),
            ("threat", "The host command was run successfully before archive validation"),
        )
        accepted = (
            ("scope", "Skillful containment analysis is used to model command-related threats before a destination write."),
            ("threat", "A command invocation threat could overwrite an archive destination"),
            ("threat", "Malicious archive input could execute a command outside the repository root"),
            ("threat", "Untrusted archive execution may cross a symlink boundary"),
            ("threat", "Archive command execution threatens destination containment"),
            ("scope", "The host command could run if future automation is added"),
            ("scope", "No host command was invoked"),
            ("scope", "Host-tool execution is planned for a later exercise"),
            ("control", "PRESENT: ensure_within is used to validate destination containment."),
            ("control", "PRESENT: malicious command execution is rejected before a destination write."),
            ("scope", "The path helper successfully rejects traversal"),
            ("threat", "A command-related archive threat could disclose a path"),
        )
        for field, text in rejected:
            with self.subTest(verdict="reject", field=field, text=text):
                self.assertTrue(installed_checkpoints._p07_invocation_claim(text, field=field))
        for field, text in accepted:
            with self.subTest(verdict="accept", field=field, text=text):
                self.assertFalse(installed_checkpoints._p07_invocation_claim(text, field=field))

    def test_p07_accepts_compact_concrete_threat_and_nonetheless_control(self) -> None:
        report = P07_INTENDED_REPORT.replace(
            b"Archive-member provenance could be mistaken for authenticated identity",
            b"Archive input could spoof authenticated identity",
        ).replace(
            b"PRESENT: destination resolution rejects parent traversal before copying.",
            b"PRESENT: Nonetheless, destination resolution rejects parent traversal before copying.",
        )
        sections = installed_checkpoints._p07_sections(report)
        self.assertIsNotNone(sections)
        self.assertTrue(installed_checkpoints._p07_native_conversation(sections or {}))

        root, _base, _prepared = self._repository()
        self._commit_report(root, report)
        result = evaluate_checkpoint(root, LAB_ID)
        self.assertTrue(result.passed, result.failed_predicates)

    def test_p07_rejects_stale_wrong_or_noncanonical_target_binding(self) -> None:
        cases = {
            "wrong-path": P07_INTENDED_REPORT.replace(
                b"Academy-Target-Path: academy_engine/paths.py",
                b"Academy-Target-Path: workshop_queue/cli.py",
            ),
            "wrong-blob": P07_INTENDED_REPORT.replace(TARGET_BLOB.encode(), b"0" * 40, 1),
            "stale-sha": P07_INTENDED_REPORT.replace(TARGET_SHA256.encode(), b"0" * 64),
            "uppercase-sha": P07_INTENDED_REPORT.replace(TARGET_SHA256.encode(), TARGET_SHA256.upper().encode()),
            "label-space": P07_INTENDED_REPORT.replace(b"Academy-Target-SHA256:", b"Academy-Target-SHA256 :"),
            "crlf": P07_INTENDED_REPORT.replace(b"\n", b"\r\n"),
            "no-final-lf": P07_INTENDED_REPORT[:-1],
            "invalid-utf8": P07_INTENDED_REPORT[:-1] + b"\xff\n",
        }
        for label, report in cases.items():
            with self.subTest(label=label):
                root, _base, _prepared = self._repository()
                self._commit_report(root, report)
                self._assert_fails(root)

    def test_p07_rejects_target_mutation_touch_then_revert_and_uncommitted_lookalike(self) -> None:
        root, _base, _prepared = self._repository()
        self._write_report(root, P07_INTENDED_REPORT)
        target = root / TARGET_PATH
        target.write_bytes(target.read_bytes() + b"\n# learner mutation\n")
        self._commit(root, (REPORT_PATH, TARGET_PATH), "learner: report plus target mutation")
        self._assert_fails(root)

        root, _base, prepared = self._repository()
        target = root / TARGET_PATH
        original = target.read_bytes()
        target.write_bytes(original + b"\n# touched\n")
        self._commit(root, (TARGET_PATH,), "learner: touch target")
        target.write_bytes(original)
        self._write_report(root, P07_INTENDED_REPORT)
        self._commit(root, (TARGET_PATH, REPORT_PATH), "learner: restore target and report")
        self.assertEqual(git(root, "rev-parse", f"HEAD:{TARGET_PATH}").stdout.strip(), TARGET_BLOB)
        self.assertNotEqual(git(root, "rev-parse", "HEAD^").stdout.strip(), prepared)
        self._assert_fails(root)

        root, _base, _prepared = self._repository()
        self._commit_report(root, P07_INTENDED_REPORT)
        self._write_report(root, P07_EQUIVALENT_REPORT)
        self._assert_fails(root)

    def test_p07_rejects_merge_extra_path_extra_commit_or_rewritten_report_history(self) -> None:
        root, _base, prepared = self._repository()
        self._write_report(root, P07_INTENDED_REPORT)
        (root / "notes.txt").write_text("extra\n", encoding="utf-8")
        self._commit(root, (REPORT_PATH, "notes.txt"), "learner: report plus extra path")
        self._assert_fails(root)

        root, _base, _prepared = self._repository()
        self._commit_report(root, P07_INTENDED_REPORT)
        self._commit(root, (), "learner: extra commit", allow_empty=True)
        self._assert_fails(root)

        root, _base, prepared = self._repository()
        branch = git(root, "branch", "--show-current").stdout.strip()
        git(root, "switch", "-c", "p07-report-side", prepared)
        self._commit_report(root, P07_INTENDED_REPORT)
        git(root, "switch", branch)
        self._commit(root, (), "learner: main-side marker", allow_empty=True)
        git(root, "merge", "--no-ff", "p07-report-side", "-m", "learner: merge report")
        self._assert_fails(root)

        root, _base, _prepared = self._repository()
        self._commit_report(root, P07_INTENDED_REPORT.replace(b"CLEAR TO IMPLEMENT", b"BLOCKED - resolve findings first"), "learner: draft report")
        self._write_report(root, P07_INTENDED_REPORT)
        self._commit(root, (REPORT_PATH,), "learner: rewrite report")
        self._assert_fails(root)

    def test_p07_rejects_secret_like_report_without_echoing_content(self) -> None:
        canary = b"gh" + b"p_1234567890abcdefghijklmnop"
        report = P07_INTENDED_REPORT.replace(
            b"PRESENT: destination resolution rejects parent traversal before copying.",
            b"PRESENT: " + canary + b" destination resolution rejects parent traversal before copying.",
        )
        sections = installed_checkpoints._p07_sections(report)
        self.assertIsNotNone(sections)
        self.assertTrue(installed_checkpoints._p07_native_conversation(sections or {}))

        root, _base, _prepared = self._repository()
        self._commit_report(root, report)
        result = evaluate_checkpoint(root, LAB_ID)
        self.assertFalse(result.passed)
        evidence = repr(asdict(result))
        self.assertNotIn(canary.decode(), evidence)
        self.assertNotIn(str(root), evidence)

    def test_p07_guide_describes_preparation_and_installed_identity_verification(self) -> None:
        guide = (self.source / "academy/tracks/practitioner/P07-threat-model.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("Preparation materializes the frozen scenario descriptor", guide)
        self.assertIn("installed verifier later recomputes", guide)
        self.assertIn("committed Git objects", guide)
        self.assertNotIn("records its tracked blob and raw\nSHA-256 outside the learner checkout", guide)


if __name__ == "__main__":
    unittest.main()
