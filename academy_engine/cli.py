"""Console entry point for repository-targeted Arbiter Academy operations."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from academy_engine.catalog import CatalogError
from academy_engine.checkpoints import CheckpointError, evaluate_checkpoint
from academy_engine.command import (
    GitCommandError,
    repository_root,
    validate_repository_git_config,
)
from academy_engine.doctor import inspect_doctor
from academy_engine.evidence import record_checkpoint
from academy_engine.progress import inspect_progress
from academy_engine.receipt import ReceiptPrivacyError, export_catalog, graduate
from academy_engine.remotes import RemoteSafetyError
from academy_engine.scenario import PreparationError, prepare_lab, reset_lab
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
            "authoritative check and graduate require a verifier installed outside the target repository."
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
        ),
    )
    parser.add_argument("lab_id", nargs="?")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    arguments = parser.parse_args(argv)
    if arguments.command in {"check", "graduate"} and arguments.repository is None:
        parser.error(f"{arguments.command} requires --repository TARGET")
    requested_repository = (
        arguments.repository.expanduser().resolve()
        if arguments.repository is not None
        else Path.cwd().resolve()
    )
    try:
        repository = repository_root(requested_repository)
        if arguments.command in {"check", "graduate"}:
            validate_repository_git_config(repository)
            ensure_authoritative_verifier(repository)
        if arguments.command == "doctor":
            report = inspect_doctor(repository)
            print(report.render())
            return 0 if report.safe_for_push_labs else 1
        if arguments.command in {"prepare", "reset"}:
            if not arguments.lab_id:
                parser.error(f"{arguments.command} requires LAB_ID")
            result = (
                prepare_lab(repository, arguments.lab_id)
                if arguments.command == "prepare"
                else reset_lab(repository, arguments.lab_id)
            )
            print(f"Academy {arguments.command}d: {result.branch} at {result.commit_sha}")
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
        print(inspect_progress(repository).render())
        return 0
    except (
        CatalogError,
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
