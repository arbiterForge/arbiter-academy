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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Arbiter Academy local tooling")
    parser.add_argument("command", choices=("doctor", "prepare", "reset", "update", "progress"))
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
        print(inspect_progress(Path.cwd()).render())
        return 0
    except (CatalogError, GitCommandError, PreparationError, RemoteSafetyError, UpdateError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
