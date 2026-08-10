from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from academy_engine.catalog import Catalog, CatalogError
from academy_engine.checkpoints import CheckpointResult
from academy_engine.cli import main
from academy_engine.command import GitCommandError
from academy_engine.external_state import ExternalStateError
from academy_engine.preview import PreviewManifest, require_published_lab
from academy_engine.scenario import PreparedLab


REPOSITORY = Path(__file__).resolve().parents[1]
LOCAL_P02_RESTORATION_LABS = (
    "P03-record-an-adr",
    "P04-review-a-dependency",
    "P05-checkpoint-remediation",
)
UNPUBLISHED_LABS = (
    "P08-repository-hygiene",
    "U01-autonomous-sprint",
    "U02-override-audit-metrics",
    "U03-refactor-chore-release",
    "U04-initialize-projects",
    "U05-debug-spike-conflict",
    "U06-preview-and-advanced-surfaces",
    "U07-capstone",
)


class AcademyCliTrustTests(unittest.TestCase):
    def test_publication_gate_uses_verifier_data_not_the_learner_repository(self) -> None:
        """Catches installed verification reading release policy from learner input."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            learner = Path(temporary_directory) / "learner"
            learner.mkdir()
            with patch(
                "academy_engine.cli.repository_root", return_value=learner
            ), patch(
                "academy_engine.cli._verifier_publication_root",
                create=True,
                return_value=REPOSITORY,
            ) as verifier_root, patch(
                "academy_engine.cli.require_published_lab",
                side_effect=ValueError("publication gate stopped dispatch"),
            ) as publication_gate, redirect_stderr(StringIO()):
                exit_code = main(
                    [
                        "--repository",
                        str(learner),
                        "check",
                        "F01-fork-clone-doctor",
                    ]
                )

        self.assertEqual(exit_code, 1)
        verifier_root.assert_called_once_with()
        publication_gate.assert_called_once_with(
            REPOSITORY, "F01-fork-clone-doctor"
        )

    def test_unpublished_labs_never_reach_prepare_reset_or_check_dispatch(self) -> None:
        """Catches catalog-only labs becoming runnable outside the release manifest."""
        for lab_id in UNPUBLISHED_LABS:
            for command, dispatch_name in (
                ("prepare", "prepare_lab"),
                ("reset", "reset_lab"),
                ("check", "evaluate_checkpoint"),
            ):
                with self.subTest(lab_id=lab_id, command=command), patch(
                    "academy_engine.cli.repository_root", return_value=REPOSITORY
                ), patch(
                    f"academy_engine.cli.{dispatch_name}"
                ) as dispatch, patch(
                    "academy_engine.cli.validate_repository_git_config"
                ) as git_config, patch(
                    "academy_engine.cli.ensure_authoritative_verifier"
                ) as authority, redirect_stderr(StringIO()) as errors:
                    exit_code = main(
                        ["--repository", str(REPOSITORY), command, lab_id]
                    )

                self.assertEqual(exit_code, 1)
                self.assertEqual(
                    errors.getvalue(),
                    f"error: {lab_id} is not runnable in Academy Preview 0.3\n",
                )
                dispatch.assert_not_called()
                git_config.assert_not_called()
                authority.assert_not_called()

    def test_graduation_dispatch_requires_the_complete_published_catalog(self) -> None:
        """Catches Preview issuing a credential before every catalog lab is published."""
        receipt = SimpleNamespace(
            path=Path("academy-graduation.json"),
            digest="f" * 64,
        )
        full_catalog = Catalog.load(REPOSITORY / "academy" / "catalog.json")
        future_manifest = PreviewManifest(
            "academy-1.0",
            1,
            tuple(lab.id for lab in full_catalog.labs),
            tuple(lab.id for lab in full_catalog.labs),
            ("F01-fork-clone-doctor",),
            (),
            "https://github.com/arbiterForge/arbiter-academy/discussions",
            "a" * 64,
        )

        preview_output, errors = StringIO(), StringIO()
        with patch(
            "academy_engine.cli.repository_root", return_value=REPOSITORY
        ), patch(
            "academy_engine.cli._verifier_publication_root",
            return_value=REPOSITORY,
        ), patch(
            "academy_engine.cli.validate_repository_git_config"
        ) as git_config, patch(
            "academy_engine.cli.ensure_authoritative_verifier"
        ) as authority, patch(
            "academy_engine.cli.graduate", return_value=receipt
        ) as graduate_dispatch, redirect_stdout(preview_output), redirect_stderr(errors):
            preview_exit = main(
                ["--repository", str(REPOSITORY), "graduate"]
            )

        self.assertEqual(preview_exit, 1)
        self.assertEqual(preview_output.getvalue(), "")
        self.assertEqual(
            errors.getvalue(),
            "error: Graduation is not available until the complete Academy catalog is published.\n",
        )
        graduate_dispatch.assert_not_called()
        git_config.assert_not_called()
        authority.assert_not_called()

        output = StringIO()
        with patch(
            "academy_engine.cli.repository_root", return_value=REPOSITORY
        ), patch(
            "academy_engine.cli._verifier_publication_root",
            return_value=REPOSITORY,
        ), patch(
            "academy_engine.preview.load_preview_manifest",
            return_value=future_manifest,
        ), patch(
            "academy_engine.cli.validate_repository_git_config"
        ) as git_config, patch(
            "academy_engine.cli.ensure_authoritative_verifier"
        ) as authority, patch(
            "academy_engine.cli.graduate", return_value=receipt
        ) as graduate_dispatch, redirect_stdout(output):
            complete_exit = main(
                ["--repository", str(REPOSITORY), "graduate"]
            )

        self.assertEqual(complete_exit, 0)
        self.assertEqual(output.getvalue(), f"academy-graduation.json {'f' * 64}\n")
        graduate_dispatch.assert_called_once_with(REPOSITORY)
        git_config.assert_called_once_with(REPOSITORY)
        authority.assert_called_once_with(REPOSITORY)

    def test_p02_prepare_prints_only_labeled_logical_repository_ids(self) -> None:
        result = PreparedLab(
            "P02-commit-review-pr",
            1,
            "academy/P02-commit-review-pr/1",
            "a" * 40,
            "b" * 40,
            "c" * 64,
            "d" * 64,
        )
        output = StringIO()

        with patch("academy_engine.cli.repository_root", return_value=REPOSITORY), patch(
            "academy_engine.cli.validate_repository_git_config"
        ), patch("academy_engine.cli.ensure_authoritative_verifier"), patch(
            "academy_engine.cli.prepare_lab", return_value=result
        ), redirect_stdout(output):
            exit_code = main(
                [
                    "--repository",
                    str(REPOSITORY),
                    "prepare",
                    "P02-commit-review-pr",
                ]
            )

        rendered = output.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertEqual(
            rendered,
            "Academy prepared: academy/P02-commit-review-pr/1 at "
            + "b" * 40
            + "\nOrigin repository ID: "
            + "c" * 64
            + "\nUpstream repository ID: "
            + "d" * 64
            + "\n",
        )
        self.assertNotIn("file:", rendered)
        self.assertNotIn(str(REPOSITORY), rendered)

    def test_p02_reset_prints_exact_past_tense_action_and_logical_repository_ids(self) -> None:
        result = PreparedLab(
            "P02-commit-review-pr",
            2,
            "academy/P02-commit-review-pr/2",
            "a" * 40,
            "b" * 40,
            "c" * 64,
            "d" * 64,
        )
        output = StringIO()

        with patch("academy_engine.cli.repository_root", return_value=REPOSITORY), patch(
            "academy_engine.cli.validate_repository_git_config"
        ), patch("academy_engine.cli.ensure_authoritative_verifier"), patch(
            "academy_engine.cli.reset_lab", return_value=result
        ), redirect_stdout(output):
            exit_code = main(
                [
                    "--repository",
                    str(REPOSITORY),
                    "reset",
                    "P02-commit-review-pr",
                ]
            )

        rendered = output.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertEqual(
            rendered,
            "Academy reset: academy/P02-commit-review-pr/2 at "
            + "b" * 40
            + "\nOrigin repository ID: "
            + "c" * 64
            + "\nUpstream repository ID: "
            + "d" * 64
            + "\n",
        )
        self.assertNotIn("file:", rendered)
        self.assertNotIn(str(REPOSITORY), rendered)

    def test_non_p02_prepare_has_no_repository_identity_output(self) -> None:
        result = PreparedLab(
            "F01-fork-clone-doctor",
            1,
            "academy/F01-fork-clone-doctor/1",
            "a" * 40,
            "b" * 40,
        )
        output = StringIO()

        with patch("academy_engine.cli.repository_root", return_value=REPOSITORY), patch(
            "academy_engine.cli.prepare_lab", return_value=result
        ), redirect_stdout(output):
            exit_code = main(
                [
                    "--repository",
                    str(REPOSITORY),
                    "prepare",
                    "F01-fork-clone-doctor",
                ]
            )

        self.assertEqual(exit_code, 0)
        self.assertIsNone(result.origin_repository_id)
        self.assertIsNone(result.upstream_repository_id)
        self.assertNotIn("repository ID", output.getvalue())

    def test_invalid_repository_identity_result_fails_before_any_stdout(self) -> None:
        result = SimpleNamespace(
            branch="academy/P02-commit-review-pr/1",
            commit_sha="b" * 40,
            origin_repository_id="c" * 64,
            upstream_repository_id=None,
        )
        output, errors = StringIO(), StringIO()

        with patch("academy_engine.cli.repository_root", return_value=REPOSITORY), patch(
            "academy_engine.cli.validate_repository_git_config"
        ), patch("academy_engine.cli.ensure_authoritative_verifier"), patch(
            "academy_engine.cli.prepare_lab", return_value=result
        ), redirect_stdout(output), redirect_stderr(errors):
            exit_code = main(
                [
                    "--repository",
                    str(REPOSITORY),
                    "prepare",
                    "P02-commit-review-pr",
                ]
            )

        self.assertEqual(exit_code, 1)
        self.assertEqual(output.getvalue(), "")
        self.assertEqual(
            errors.getvalue(),
            "error: prepared lab repository identity is invalid.\n",
        )
        self.assertNotIn(str(REPOSITORY), errors.getvalue())

    def test_project_packages_engine_and_registers_console_entrypoint(self) -> None:
        text = (REPOSITORY / "pyproject.toml").read_text(encoding="utf-8")

        self.assertIn('arbiter-academy = "academy_engine.cli:main"', text)
        self.assertIn('"academy_engine"', text)

    def test_authoritative_command_requires_explicit_repository(self) -> None:
        result = subprocess.run(
            [sys.executable, str(REPOSITORY / "scripts" / "academy.py"), "check", "F01-fork-clone-doctor"],
            cwd=REPOSITORY,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--repository", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_p06_clears_publication_and_reaches_external_authoritative_evaluation(self) -> None:
        """Catches P06 remaining gated or bypassing installed authoritative evaluation."""
        result = CheckpointResult(
            "P06-context-drift-recovery",
            False,
            "a" * 64,
            "b" * 64,
            (),
            ("provenance_drift_recovery",),
        )
        with tempfile.TemporaryDirectory() as directory:
            learner = (Path(directory) / "learner").resolve()
            learner.mkdir()
            installed_output, installed_errors = StringIO(), StringIO()
            with patch(
                "academy_engine.cli.repository_root", return_value=learner
            ), patch(
                "academy_engine.cli.require_published_lab", wraps=require_published_lab
            ) as publication_gate, patch(
                "academy_engine.cli.validate_repository_git_config"
            ) as validated, patch(
                "academy_engine.cli.ensure_authoritative_verifier"
            ) as authoritative, patch(
                "academy_engine.cli.evaluate_checkpoint", return_value=result
            ) as evaluated, redirect_stdout(installed_output), redirect_stderr(installed_errors):
                installed_exit = main(
                    [
                        "--repository",
                        str(learner),
                        "check",
                        "P06-context-drift-recovery",
                    ]
                )

            self.assertEqual(installed_exit, 1)
            publication_gate.assert_called_once_with(REPOSITORY, "P06-context-drift-recovery")
            validated.assert_called_once_with(learner)
            authoritative.assert_called_once_with(learner)
            evaluated.assert_called_once_with(learner, "P06-context-drift-recovery")
            self.assertEqual(installed_output.getvalue(), "")
            self.assertIn("provenance_drift_recovery", installed_errors.getvalue())
            self.assertNotIn(str(learner), installed_errors.getvalue())

    def test_p02_prepare_and_reset_require_explicit_repository(self) -> None:
        for command in ("prepare", "reset"):
            with self.subTest(command=command):
                result = subprocess.run(
                    [
                        sys.executable,
                        str(REPOSITORY / "scripts" / "academy.py"),
                        command,
                        "P02-commit-review-pr",
                    ],
                    cwd=REPOSITORY,
                    text=True,
                    capture_output=True,
                    check=False,
                )

                self.assertNotEqual(result.returncode, 0)
                self.assertIn("--repository", result.stderr)
                self.assertNotIn("Traceback", result.stderr)

    def test_later_lab_local_prepare_and_reset_proceed_when_p02_records_are_absent(self) -> None:
        for command, target in (("prepare", "prepare_lab"), ("reset", "reset_lab")):
            for lab_id in LOCAL_P02_RESTORATION_LABS:
                result = PreparedLab(
                    lab_id,
                    1,
                    f"academy/{lab_id}/1",
                    "a" * 40,
                    "b" * 40,
                )
                output = StringIO()
                with self.subTest(command=command, lab_id=lab_id), patch(
                    "academy_engine.cli.repository_root", return_value=REPOSITORY
                ), patch(
                    "academy_engine.external_state.ExternalStateStore.has_records", return_value=False
                ) as probed, patch(
                    "academy_engine.cli.validate_repository_git_config"
                ) as validated, patch(
                    "academy_engine.cli.ensure_authoritative_verifier"
                ) as authoritative, patch(
                    f"academy_engine.cli.{target}", return_value=result
                ) as transitioned, redirect_stdout(output):
                    try:
                        exit_code = main([command, lab_id])
                    except SystemExit as error:
                        exit_code = error.code

                self.assertEqual(exit_code, 0)
                probed.assert_called_once_with(REPOSITORY, lab="p02")
                validated.assert_not_called()
                authoritative.assert_not_called()
                transitioned.assert_called_once_with(
                    REPOSITORY, lab_id, installed_authority=False
                )

    def test_later_lab_local_prepare_and_reset_refuse_present_p02_records_before_mutation(self) -> None:
        expected = "error: P02 exercise records require installed Academy authority.\n"

        for command, target in (("prepare", "prepare_lab"), ("reset", "reset_lab")):
            for lab_id in LOCAL_P02_RESTORATION_LABS:
                output, errors = StringIO(), StringIO()
                with self.subTest(command=command, lab_id=lab_id), patch(
                    "academy_engine.cli.repository_root", return_value=REPOSITORY
                ), patch(
                    "academy_engine.external_state.ExternalStateStore.has_records", return_value=True
                ) as probed, patch(
                    "academy_engine.cli.validate_repository_git_config"
                ) as validated, patch(
                    "academy_engine.cli.ensure_authoritative_verifier"
                ) as authoritative, patch(
                    f"academy_engine.cli.{target}"
                ) as transitioned, redirect_stdout(output), redirect_stderr(errors):
                    try:
                        exit_code = main([command, lab_id])
                    except SystemExit as error:
                        exit_code = error.code

                self.assertEqual(exit_code, 1)
                self.assertEqual(output.getvalue(), "")
                self.assertEqual(errors.getvalue(), expected)
                self.assertNotIn(str(REPOSITORY), errors.getvalue())
                probed.assert_called_once_with(REPOSITORY, lab="p02")
                validated.assert_not_called()
                authoritative.assert_not_called()
                transitioned.assert_not_called()

    def test_later_lab_local_p02_probe_failure_is_path_free_and_nonmutating(self) -> None:
        private_path = r"C:\external\learner-secret\state"
        output, errors = StringIO(), StringIO()

        with patch(
            "academy_engine.cli.repository_root", return_value=REPOSITORY
        ), patch(
            "academy_engine.external_state.ExternalStateStore.has_records",
            side_effect=GitCommandError(f"fatal: failed at {private_path}"),
        ), patch(
            "academy_engine.cli.prepare_lab"
        ) as transitioned, redirect_stdout(output), redirect_stderr(errors):
            exit_code = main(["prepare", "P03-record-an-adr"])

        self.assertEqual(exit_code, 1)
        self.assertEqual(output.getvalue(), "")
        self.assertEqual(
            errors.getvalue(),
            "error: P02 exercise state probe could not complete.\n",
        )
        self.assertNotIn(private_path, errors.getvalue())
        transitioned.assert_not_called()

    def test_later_lab_local_external_state_probe_failure_uses_stable_nonmutating_error(self) -> None:
        output, errors = StringIO(), StringIO()

        with patch(
            "academy_engine.cli.repository_root", return_value=REPOSITORY
        ), patch(
            "academy_engine.external_state.ExternalStateStore.has_records",
            side_effect=ExternalStateError("unsafe-state-path"),
        ), patch(
            "academy_engine.cli.prepare_lab"
        ) as transitioned, redirect_stdout(output), redirect_stderr(errors):
            exit_code = main(["prepare", "P03-record-an-adr"])

        self.assertEqual(exit_code, 1)
        self.assertEqual(output.getvalue(), "")
        self.assertEqual(
            errors.getvalue(),
            "error: P02 exercise state probe could not complete.\n",
        )
        transitioned.assert_not_called()

    def test_later_lab_explicit_prepare_and_reset_preserve_installed_restoration_dispatch(self) -> None:
        result = PreparedLab(
            "P03-record-an-adr",
            1,
            "academy/P03-record-an-adr/1",
            "a" * 40,
            "b" * 40,
        )

        for command, target in (("prepare", "prepare_lab"), ("reset", "reset_lab")):
            with self.subTest(command=command), patch(
                "academy_engine.cli.repository_root", return_value=REPOSITORY
            ), patch(
                "academy_engine.cli.validate_repository_git_config"
            ) as validated, patch(
                "academy_engine.cli.ensure_authoritative_verifier"
            ) as authoritative, patch(
                "academy_engine.external_state.ExternalStateStore.has_records", return_value=True
            ) as local_probe, patch(
                f"academy_engine.cli.{target}", return_value=result
            ) as transitioned:
                exit_code = main(
                    [
                        "--repository",
                        str(REPOSITORY),
                        command,
                        "P03-record-an-adr",
                    ]
                )

            self.assertEqual(exit_code, 0)
            validated.assert_called_once_with(REPOSITORY)
            authoritative.assert_called_once_with(REPOSITORY)
            local_probe.assert_not_called()
            transitioned.assert_called_once_with(
                REPOSITORY,
                "P03-record-an-adr",
                installed_authority=True,
            )

    def test_foundation_prepare_retains_repository_local_non_authoritative_contract(self) -> None:
        result = PreparedLab(
            "F01-fork-clone-doctor",
            1,
            "academy/F01-fork-clone-doctor/1",
            "a" * 40,
            "b" * 40,
        )

        with patch(
            "academy_engine.cli.repository_root", return_value=REPOSITORY
        ), patch(
            "academy_engine.cli.validate_repository_git_config"
        ) as validated, patch(
            "academy_engine.cli.ensure_authoritative_verifier"
        ) as authoritative, patch(
            "academy_engine.cli.prepare_lab", return_value=result
        ):
            exit_code = main(["prepare", "F01-fork-clone-doctor"])

        self.assertEqual(exit_code, 0)
        validated.assert_not_called()
        authoritative.assert_not_called()

    def test_p02_dispatch_sanitizes_catalog_manifest_os_and_git_diagnostics(self) -> None:
        private_path = r"C:\external\learner-secret\catalog.json"
        raw_git = f"fatal: unsafe repository at {private_path} for learner@example.test"

        def checked_git_failure(_root, _args, *, check=True, **_kwargs):
            if check:
                raise GitCommandError(raw_git)
            return subprocess.CompletedProcess(["git"], 128, "", raw_git)

        cases = (
            (
                "catalog",
                "academy_engine.scenario.Catalog.load",
                CatalogError(f"could not read catalog: {private_path}"),
            ),
            (
                "manifest",
                "academy_engine.scenario.load_manifest_file",
                CatalogError(f"could not read scenario manifest: {private_path}"),
            ),
            (
                "os",
                "academy_engine.scenario.Catalog.load",
                OSError(f"access denied: {private_path}"),
            ),
        )
        for label, target, failure in cases:
            with self.subTest(label=label):
                output, errors = StringIO(), StringIO()
                with patch(
                    "academy_engine.cli.require_published_lab"
                ), patch(
                    "academy_engine.cli.validate_repository_git_config"
                ), patch(
                    "academy_engine.cli.ensure_authoritative_verifier"
                ), patch(target, side_effect=failure), redirect_stdout(output), redirect_stderr(errors):
                    exit_code = main(
                        [
                            "--repository",
                            str(REPOSITORY),
                            "prepare",
                            "P02-commit-review-pr",
                        ]
                    )

                self.assertEqual(exit_code, 1)
                self.assertEqual(output.getvalue(), "")
                self.assertEqual(errors.getvalue(), "error: P02 exercise state is invalid.\n")
                self.assertNotIn(private_path, errors.getvalue())
                self.assertNotIn("learner@example.test", errors.getvalue())

        output, errors = StringIO(), StringIO()
        with patch(
            "academy_engine.cli.require_published_lab"
        ), patch(
            "academy_engine.cli.validate_repository_git_config"
        ), patch(
            "academy_engine.cli.ensure_authoritative_verifier"
        ), patch(
            "academy_engine.scenario._run_git", side_effect=checked_git_failure
        ), redirect_stdout(output), redirect_stderr(errors):
            exit_code = main(
                [
                    "--repository",
                    str(REPOSITORY),
                    "prepare",
                    "P02-commit-review-pr",
                ]
            )

        self.assertEqual(exit_code, 1)
        self.assertEqual(output.getvalue(), "")
        self.assertEqual(errors.getvalue(), "error: P02 exercise state is invalid.\n")
        self.assertNotIn(private_path, errors.getvalue())
        self.assertNotIn(raw_git, errors.getvalue())

    def test_in_checkout_p02_prepare_refuses_circular_trust(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(REPOSITORY / "scripts" / "academy.py"),
                "--repository",
                str(REPOSITORY),
                "prepare",
                "P02-commit-review-pr",
            ],
            cwd=REPOSITORY,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("outside the target repository", result.stderr)
        self.assertNotIn(str(REPOSITORY), result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_in_checkout_authoritative_command_refuses_circular_trust(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(REPOSITORY / "scripts" / "academy.py"),
                "--repository",
                str(REPOSITORY),
                "check",
                "F01-fork-clone-doctor",
            ],
            cwd=REPOSITORY,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("outside the target repository", result.stderr)
        self.assertNotIn(str(REPOSITORY), result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_p07_clears_publication_and_reaches_external_authoritative_evaluation(self) -> None:
        """Catches P07 remaining gated or bypassing installed authoritative evaluation."""
        failed = CheckpointResult(
            "P07-threat-model",
            False,
            "a" * 64,
            "b" * 64,
            ("prepared_scenario", "source_integrity"),
            ("stride_model",),
        )
        with tempfile.TemporaryDirectory() as directory:
            learner = (Path(directory) / "learner").resolve()
            learner.mkdir()
            errors = StringIO()
            with patch(
                "academy_engine.cli.repository_root", return_value=learner
            ), patch(
                "academy_engine.cli.require_published_lab", wraps=require_published_lab
            ) as publication_gate, patch(
                "academy_engine.cli.validate_repository_git_config"
            ) as validated, patch(
                "academy_engine.cli.ensure_authoritative_verifier"
            ) as authoritative, patch(
                "academy_engine.cli.evaluate_checkpoint", return_value=failed
            ) as evaluated, redirect_stderr(errors):
                exit_code = main(
                    [
                        "--repository",
                        str(learner),
                        "check",
                        "P07-threat-model",
                    ]
                )

            self.assertEqual(exit_code, 1)
            publication_gate.assert_called_once_with(REPOSITORY, "P07-threat-model")
            validated.assert_called_once_with(learner)
            authoritative.assert_called_once_with(learner)
            evaluated.assert_called_once_with(learner, "P07-threat-model")
            self.assertEqual(errors.getvalue(), "checkpoint P07-threat-model: failed (stride_model)\n")

    def test_nested_target_canonicalizes_before_circular_trust_check(self) -> None:
        nested = REPOSITORY / "tests"
        result = subprocess.run(
            [
                sys.executable,
                str(REPOSITORY / "scripts" / "academy.py"),
                "--repository",
                str(nested),
                "check",
                "F01-fork-clone-doctor",
            ],
            cwd=nested,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("outside the target repository", result.stderr)
        self.assertNotIn(str(REPOSITORY), result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_successful_p02_check_leaves_generated_state_clean_for_immediate_reset(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            xdg_config_home = root / "xdg-config"
            xdg_config_home.mkdir()
            git_environment = {
                key: value
                for key, value in os.environ.items()
                if not key.upper().startswith("GIT_")
            }
            git_environment.update(
                {
                    "GIT_CONFIG_NOSYSTEM": "1",
                    "GIT_CONFIG_GLOBAL": os.devnull,
                    "XDG_CONFIG_HOME": str(xdg_config_home),
                }
            )

            def git(
                *arguments: str, check: bool = True
            ) -> subprocess.CompletedProcess[str]:
                return subprocess.run(
                    ["git", "-c", f"core.excludesFile={os.devnull}", *arguments],
                    cwd=root,
                    env=git_environment,
                    text=True,
                    encoding="utf-8",
                    capture_output=True,
                    check=check,
                )

            git("init", "--template=", "-b", "main")
            git("config", "user.name", "Academy Fixture")
            git("config", "user.email", "academy-fixture@example.invalid")
            (root / ".gitignore").write_text(
                (REPOSITORY / ".gitignore").read_text(encoding="utf-8"),
                encoding="utf-8",
                newline="\n",
            )
            git("add", ".gitignore")
            git("commit", "-m", "fixture base")

            generated_workspace = root / ".academy" / "workspaces" / "U04-secondary" / ".git"
            generated_workspace.mkdir(parents=True)
            (generated_workspace / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
            nested_probe = root / "nested" / ".academy" / "sentinel"
            nested_probe.parent.mkdir(parents=True)
            nested_probe.write_text("visible\n", encoding="utf-8")

            result = CheckpointResult(
                "P02-commit-review-pr",
                True,
                "a" * 64,
                "b" * 64,
                ("review_pr_commit_range",),
                (),
                "c" * 64,
                "d" * 64,
                "e" * 64,
                "f" * 64,
                "academy/P02-commit-review-pr/1",
                "1" * 40,
                "2" * 40,
                "3" * 40,
            )
            reset_result = PreparedLab(
                "P02-commit-review-pr",
                2,
                "academy/P02-commit-review-pr/2",
                "4" * 40,
                "5" * 40,
                "6" * 64,
                "7" * 64,
            )

            def reset_while_clean(
                actual_root: Path, lab_id: str, *, installed_authority: bool
            ) -> PreparedLab:
                self.assertEqual(actual_root, root)
                self.assertEqual(lab_id, "P02-commit-review-pr")
                self.assertTrue(installed_authority)
                self.assertEqual(git("status", "--porcelain", "--untracked-files=all").stdout, "")
                return reset_result

            with patch("academy_engine.cli.repository_root", return_value=root), patch(
                "academy_engine.cli.require_published_lab"
            ), patch(
                "academy_engine.cli.validate_repository_git_config"
            ), patch("academy_engine.cli.ensure_authoritative_verifier"), patch(
                "academy_engine.cli.evaluate_checkpoint", return_value=result
            ), patch(
                "academy_engine.evidence.evaluate_checkpoint", return_value=result
            ), patch("academy_engine.cli.reset_lab", side_effect=reset_while_clean) as reset:
                check_exit = main(
                    ["--repository", str(root), "check", "P02-commit-review-pr"]
                )

                self.assertEqual(check_exit, 0)
                self.assertTrue((root / ".academy" / "progress.json").is_file())
                self.assertNotEqual(
                    git(
                        "check-ignore",
                        "--quiet",
                        "--",
                        "nested/.academy/sentinel",
                        check=False,
                    ).returncode,
                    0,
                )
                nested_probe.unlink()
                self.assertEqual(
                    git("status", "--porcelain", "--untracked-files=all").stdout,
                    "",
                )
                self.assertEqual(
                    git(
                        "check-ignore",
                        "--quiet",
                        "--",
                        ".academy/progress.json",
                        check=False,
                    ).returncode,
                    0,
                )
                self.assertEqual(
                    git(
                        "check-ignore",
                        "--quiet",
                        "--",
                        ".academy/workspaces/U04-secondary/.git/HEAD",
                        check=False,
                    ).returncode,
                    0,
                )

                reset_exit = main(
                    ["--repository", str(root), "reset", "P02-commit-review-pr"]
                )

            self.assertEqual(reset_exit, 0)
            reset.assert_called_once_with(
                root,
                "P02-commit-review-pr",
                installed_authority=True,
            )


if __name__ == "__main__":
    unittest.main()
