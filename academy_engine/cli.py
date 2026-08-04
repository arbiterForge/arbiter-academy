"""Console entry point for repository-targeted Arbiter Academy operations."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from academy_engine.catalog import CatalogError
from academy_engine.checkpoints import CheckpointError, evaluate_checkpoint
from academy_engine.command import (
    GitCommandError,
    repository_root,
    validate_repository_git_config,
)
from academy_engine.curriculum import CurriculumError, verify_track
from academy_engine.doctor import inspect_doctor, record_foundations_doctor
from academy_engine.evidence import record_checkpoint
from academy_engine.external_state import ExternalStateError, ExternalStateStore
from academy_engine.progress import inspect_progress
from academy_engine.receipt import ReceiptPrivacyError, export_catalog, graduate
from academy_engine.remotes import RemoteSafetyError
from academy_engine.scenario import (
    PreparationError,
    p02_state_reachable,
    prepare_lab,
    reset_lab,
)
from academy_engine.update import UpdateError, update_academy


class VerifierTrustError(ValueError):
    """An authoritative command would use a verifier from untrusted input."""


def _inside(candidate: Path, root: Path) -> bool:
    try:
        candidate.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def ensure_authoritative_verifier(repository: Path) -> None:
    """Reject circular authority when this package is loaded from the learner checkout."""
    verifier = Path(__file__).resolve().parent
    if _inside(verifier, repository):
        raise VerifierTrustError(
            "authoritative Academy commands require a verifier installed outside the target repository."
        )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Arbiter Academy local tooling")
    parser.add_argument(
        "--repository",
        type=Path,
        help="explicit learner repository targeted by the command",
    )
    parser.add_argument(
        "command",
        choices=(
            "doctor",
            "prepare",
            "reset",
            "update",
            "progress",
            "check",
            "graduate",
            "export-catalog",
            "verify-track",
        ),
    )
    parser.add_argument("lab_id", nargs="?")
    parser.add_argument(
        "--matrix",
        action="store_true",
        help="include the declared positive/adversarial curriculum matrix",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    arguments = parser.parse_args(argv)
    authoritative_exercise = (
        arguments.command in {"prepare", "reset"}
        and arguments.lab_id in {"P02-commit-review-pr", "P08-repository-hygiene"}
    )
    later_p02_reachable = (
        arguments.command in {"prepare", "reset"}
        and arguments.lab_id != "P02-commit-review-pr"
        and p02_state_reachable(arguments.lab_id)
    )
    if (arguments.command in {"check", "graduate"} or authoritative_exercise) and arguments.repository is None:
        parser.error(f"{arguments.command} requires --repository TARGET")
    requested_repository = (
        arguments.repository.expanduser().resolve()
        if arguments.repository is not None
        else Path.cwd().resolve()
    )
    try:
        repository = repository_root(requested_repository)
        installed_authority = False
        if (
            arguments.command in {"check", "graduate"}
            or authoritative_exercise
            or (later_p02_reachable and arguments.repository is not None)
        ):
            validate_repository_git_config(repository)
            ensure_authoritative_verifier(repository)
            installed_authority = True
        elif later_p02_reachable:
            try:
                p02_records_present = ExternalStateStore.has_records(
                    repository, lab="p02"
                )
            except (ExternalStateError, GitCommandError) as error:
                raise VerifierTrustError(
                    "P02 exercise state probe could not complete."
                ) from error
            if p02_records_present:
                raise VerifierTrustError(
                    "P02 exercise records require installed Academy authority."
                )
        if arguments.command == "doctor":
            report = inspect_doctor(repository)
            print(report.render())
            if arguments.lab_id:
                if arguments.lab_id != "F01-fork-clone-doctor":
                    parser.error("doctor evidence is available only for F01-fork-clone-doctor")
                destination = record_foundations_doctor(repository, report)
                print(f"Recorded {destination.relative_to(repository).as_posix()}")
            return 0 if report.safe_for_push_labs else 1
        if arguments.command in {"prepare", "reset"}:
            if not arguments.lab_id:
                parser.error(f"{arguments.command} requires LAB_ID")
            result = (
                prepare_lab(
                    repository,
                    arguments.lab_id,
                    installed_authority=installed_authority,
                )
                if arguments.command == "prepare"
                else reset_lab(
                    repository,
                    arguments.lab_id,
                    installed_authority=installed_authority,
                )
            )
            identities = (
                result.origin_repository_id,
                result.upstream_repository_id,
            )
            if (identities[0] is None) != (identities[1] is None) or any(
                value is not None and re.fullmatch(r"[0-9a-f]{64}", value) is None
                for value in identities
            ):
                raise ValueError("prepared lab repository identity is invalid.")
            completed_action = {
                "prepare": "prepared",
                "reset": "reset",
            }[arguments.command]
            print(f"Academy {completed_action}: {result.branch} at {result.commit_sha}")
            if identities[0] is not None:
                print(f"Origin repository ID: {identities[0]}")
                print(f"Upstream repository ID: {identities[1]}")
            return 0
        if arguments.command == "update":
            print(update_academy(repository).render())
            return 0
        if arguments.command == "check":
            if not arguments.lab_id:
                parser.error("check requires LAB_ID")
            result = evaluate_checkpoint(repository, arguments.lab_id)
            if result.passed:
                progress_path = repository / ".academy" / "progress.json"
                record_checkpoint(progress_path, result)
                print(
                    f"checkpoint {result.lab_id}: passed; progress: .academy/progress.json"
                )
                return 0
            print(
                f"checkpoint {result.lab_id}: failed ({', '.join(result.failed_predicates)})",
                file=sys.stderr,
            )
            return 1
        if arguments.command == "graduate":
            receipt = graduate(repository)
            print(f"{receipt.path.name} {receipt.digest}")
            return 0
        if arguments.command == "export-catalog":
            if not arguments.lab_id:
                parser.error("export-catalog requires OUTPUT")
            result = export_catalog(repository, Path(arguments.lab_id))
            print(result.digest)
            return 0
        if arguments.command == "verify-track":
            if not arguments.lab_id:
                parser.error("verify-track requires TRACK")
            report = verify_track(repository, arguments.lab_id, matrix=arguments.matrix)
            print(report.render())
            return 0 if report.passed else 1
        print(inspect_progress(repository).render())
        return 0
    except (
        CatalogError,
        CurriculumError,
        GitCommandError,
        PreparationError,
        RemoteSafetyError,
        UpdateError,
        CheckpointError,
        ReceiptPrivacyError,
        VerifierTrustError,
        ValueError,
    ) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    except OSError:
        print("error: Academy command could not complete.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
