"""Direct, installation-free command entry point for Academy setup checks."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from academy_engine.catalog import CatalogError
from academy_engine.command import GitCommandError
from academy_engine.doctor import inspect_doctor
from academy_engine.progress import inspect_progress
from academy_engine.scenario import PreparationError, prepare_lab, reset_lab
from academy_engine.update import UpdateError, update_academy
from academy_engine.remotes import RemoteSafetyError
from academy_engine.checkpoints import CheckpointError, evaluate_checkpoint
from academy_engine.receipt import ReceiptPrivacyError, export_catalog, graduate


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Arbiter Academy local tooling")
    parser.add_argument("command", choices=("doctor", "prepare", "reset", "update", "progress", "check", "graduate", "export-catalog"))
    parser.add_argument("lab_id", nargs="?")
    arguments = parser.parse_args(argv)
    try:
        if arguments.command == "doctor":
            report = inspect_doctor(Path.cwd())
            print(report.render())
            return 0 if report.safe_for_push_labs else 1
        if arguments.command in {"prepare", "reset"}:
            if not arguments.lab_id:
                parser.error(f"{arguments.command} requires LAB_ID")
            result = prepare_lab(Path.cwd(), arguments.lab_id) if arguments.command == "prepare" else reset_lab(Path.cwd(), arguments.lab_id)
            print(f"Academy {arguments.command}d: {result.branch} at {result.commit_sha}")
            return 0
        if arguments.command == "update":
            print(update_academy(Path.cwd()).render())
            return 0
        if arguments.command == "check":
            if not arguments.lab_id:
                parser.error("check requires LAB_ID")
            result = evaluate_checkpoint(Path.cwd(), arguments.lab_id)
            if result.passed:
                print(f"checkpoint {result.lab_id}: passed")
                return 0
            print(f"checkpoint {result.lab_id}: failed ({', '.join(result.failed_predicates)})", file=sys.stderr)
            return 1
        if arguments.command == "graduate":
            receipt = graduate(Path.cwd())
            print(receipt.digest)
            return 0
        if arguments.command == "export-catalog":
            if not arguments.lab_id:
                parser.error("export-catalog requires OUTPUT")
            result = export_catalog(Path.cwd(), Path(arguments.lab_id))
            print(result.digest)
            return 0
        print(inspect_progress(Path.cwd()).render())
        return 0
    except (CatalogError, GitCommandError, PreparationError, RemoteSafetyError, UpdateError, CheckpointError, ReceiptPrivacyError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    except OSError:
        print("error: Academy command could not complete.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
