"""Direct, installation-free command entry point for Academy setup checks."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from academy_engine.doctor import inspect_doctor


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Arbiter Academy local tooling")
    parser.add_argument("command", choices=("doctor",))
    arguments = parser.parse_args(argv)
    if arguments.command == "doctor":
        report = inspect_doctor(Path.cwd())
        print(report.render())
        return 0 if report.safe_for_push_labs else 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
