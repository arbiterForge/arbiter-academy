#!/usr/bin/env python3
"""Run the canonical unittest inventory in eight deterministic exhaustive shards."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import unittest
from typing import Iterable, Sequence, TextIO


ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"
SHARD_COUNT = 8


class ShardError(RuntimeError):
    """The exhaustive inventory or its shard evidence is incomplete."""


def _flatten_suite(suite: unittest.TestSuite) -> Iterable[unittest.TestCase]:
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from _flatten_suite(item)
        elif isinstance(item, unittest.TestCase):
            yield item
        else:
            raise ShardError(
                f"unittest discovery returned unsupported leaf {type(item).__name__}."
            )


def _case_id(test: unittest.TestCase) -> str:
    try:
        test_id = test.id()
    except Exception as error:
        raise ShardError(
            f"unittest test ID failed with {type(error).__name__}."
        ) from error
    if not isinstance(test_id, str) or not test_id or test_id.strip() != test_id:
        raise ShardError("unittest discovery returned an empty or malformed test ID.")
    if "\n" in test_id or "\r" in test_id:
        raise ShardError("unittest discovery returned a multiline test ID.")
    return test_id


def _validate_unique_ids(test_ids: Sequence[str], *, label: str) -> tuple[str, ...]:
    normalized = tuple(test_ids)
    if not normalized:
        raise ShardError(f"{label} is empty.")
    malformed = [item for item in normalized if not isinstance(item, str) or not item]
    if malformed:
        raise ShardError(f"{label} contains an invalid test ID.")
    duplicates = sorted(
        test_id for test_id, count in Counter(normalized).items() if count != 1
    )
    if duplicates:
        raise ShardError(f"{label} contains duplicate test IDs.")
    return normalized


def discover_test_cases(
    *, loader: unittest.TestLoader | None = None
) -> tuple[unittest.TestCase, ...]:
    """Discover, validate, and stably sort the canonical test inventory."""
    root_text = str(ROOT)
    if root_text not in sys.path:
        sys.path.insert(0, root_text)
    selected_loader = loader if loader is not None else unittest.TestLoader()
    try:
        suite = selected_loader.discover(str(TESTS), pattern="test_*.py")
    except Exception as error:
        raise ShardError(
            f"unittest discovery failed with {type(error).__name__}."
        ) from error
    loader_errors = tuple(getattr(selected_loader, "errors", ()))
    if loader_errors:
        raise ShardError(
            f"unittest discovery reported {len(loader_errors)} loader error(s)."
        )

    cases = tuple(_flatten_suite(suite))
    ids = tuple(_case_id(test) for test in cases)
    _validate_unique_ids(ids, label="canonical unittest inventory")
    return tuple(test for _, test in sorted(zip(ids, cases), key=lambda item: item[0]))


def validate_partition(
    canonical_ids: Sequence[str], shard_ids: Sequence[Sequence[str]]
) -> None:
    """Fail closed unless shards are the exact eight-way round-robin partition."""
    canonical = _validate_unique_ids(
        tuple(canonical_ids), label="canonical unittest inventory"
    )
    if canonical != tuple(sorted(canonical)):
        raise ShardError("canonical unittest inventory is not stably sorted.")
    if len(canonical) < SHARD_COUNT:
        raise ShardError("canonical unittest inventory cannot populate every shard.")
    if len(shard_ids) != SHARD_COUNT:
        raise ShardError(f"expected exactly {SHARD_COUNT} shards.")

    normalized = tuple(tuple(items) for items in shard_ids)
    for index, items in enumerate(normalized):
        _validate_unique_ids(items, label=f"shard {index}")
    expected = tuple(canonical[index::SHARD_COUNT] for index in range(SHARD_COUNT))
    if normalized != expected:
        raise ShardError(
            "shards omit, duplicate, reorder, or reassign canonical unittest IDs."
        )


def partition_test_cases(
    cases: Sequence[unittest.TestCase], *, shard_count: int = SHARD_COUNT
) -> tuple[tuple[unittest.TestCase, ...], ...]:
    """Return the fixed eight-way sorted round-robin case partition."""
    if isinstance(shard_count, bool) or shard_count != SHARD_COUNT:
        raise ShardError(f"shard count must be exactly {SHARD_COUNT}.")
    pairs = sorted(((_case_id(test), test) for test in cases), key=lambda item: item[0])
    canonical_ids = _validate_unique_ids(
        tuple(test_id for test_id, _ in pairs), label="canonical unittest inventory"
    )
    partitions = tuple(
        tuple(test for _, test in pairs[index::SHARD_COUNT])
        for index in range(SHARD_COUNT)
    )
    validate_partition(
        canonical_ids,
        tuple(tuple(_case_id(test) for test in partition) for partition in partitions),
    )
    return partitions


class RecordingTextResult(unittest.TextTestResult):
    """Standard text result that records every test entering unittest execution."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.executed_test_ids: list[str] = []

    def startTest(self, test):  # noqa: N802 - unittest extension point
        self.executed_test_ids.append(_case_id(test))
        super().startTest(test)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run_shard(
    shard_index: int,
    *,
    loader: unittest.TestLoader | None = None,
    stream: TextIO | None = None,
    result_path: Path | None = None,
) -> int:
    """Run one exhaustive shard and return unittest-compatible success/failure."""
    if isinstance(shard_index, bool) or not isinstance(shard_index, int):
        raise ShardError("shard index must be an integer.")
    if shard_index < 0 or shard_index >= SHARD_COUNT:
        raise ShardError(f"shard index must be between 0 and {SHARD_COUNT - 1}.")

    started = datetime.now(timezone.utc)
    timer = time.monotonic()
    cases = discover_test_cases(loader=loader)
    partitions = partition_test_cases(cases)
    selected = partitions[shard_index]
    planned_ids = tuple(_case_id(test) for test in selected)
    runner = unittest.TextTestRunner(
        stream=stream if stream is not None else sys.stderr,
        verbosity=2,
        resultclass=RecordingTextResult,
    )
    result = runner.run(unittest.TestSuite(selected))
    executed_ids = tuple(result.executed_test_ids)
    integrity_error = executed_ids != planned_ids
    exit_code = 2 if integrity_error else (0 if result.wasSuccessful() else 1)
    status = "incomplete" if integrity_error else ("passed" if exit_code == 0 else "failed")
    payload = {
        "shard_index": shard_index,
        "shard_count": SHARD_COUNT,
        "status": status,
        "exit_code": exit_code,
        "planned_test_ids": list(planned_ids),
        "executed_test_ids": list(executed_ids),
        "tests_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "skipped": len(result.skipped),
        "expected_failures": len(result.expectedFailures),
        "unexpected_successes": len(result.unexpectedSuccesses),
        "started_utc": started.isoformat(),
        "ended_utc": datetime.now(timezone.utc).isoformat(),
        "duration_seconds": round(time.monotonic() - timer, 3),
        "python": sys.version,
    }
    if result_path is not None:
        _write_json(Path(result_path), payload)
    if integrity_error:
        target = stream if stream is not None else sys.stderr
        print("ERROR: shard execution did not match its planned test IDs.", file=target)
    return exit_code


def aggregate_results(
    canonical_ids: Sequence[str], payloads: Sequence[dict[str, object]]
) -> dict[str, object]:
    """Validate exact-once execution and aggregate eight successful shard results."""
    canonical = _validate_unique_ids(
        tuple(canonical_ids), label="canonical unittest inventory"
    )
    if canonical != tuple(sorted(canonical)):
        raise ShardError("canonical unittest inventory is not stably sorted.")
    if len(payloads) != SHARD_COUNT:
        raise ShardError(f"expected exactly {SHARD_COUNT} shard result files.")

    by_index: dict[int, dict[str, object]] = {}
    for payload in payloads:
        index = payload.get("shard_index")
        if isinstance(index, bool) or not isinstance(index, int):
            raise ShardError("shard result has an invalid index.")
        if index in by_index or index < 0 or index >= SHARD_COUNT:
            raise ShardError("shard results contain a duplicate or invalid index.")
        if payload.get("shard_count") != SHARD_COUNT:
            raise ShardError("shard result has an invalid shard count.")
        by_index[index] = payload

    ordered = tuple(by_index[index] for index in range(SHARD_COUNT))
    planned = tuple(tuple(payload.get("planned_test_ids", ())) for payload in ordered)
    executed = tuple(tuple(payload.get("executed_test_ids", ())) for payload in ordered)
    validate_partition(canonical, planned)
    validate_partition(canonical, executed)

    for index, payload in enumerate(ordered):
        if planned[index] != executed[index]:
            raise ShardError(f"shard {index} did not execute its exact plan.")
        if payload.get("tests_run") != len(executed[index]):
            raise ShardError(f"shard {index} reported an inconsistent test count.")
        if payload.get("exit_code") != 0 or payload.get("status") != "passed":
            raise ShardError(f"shard {index} did not pass.")
        if payload.get("failures") != 0 or payload.get("errors") != 0:
            raise ShardError(f"shard {index} reported failures or errors.")

    return {
        "status": "passed",
        "shard_count": SHARD_COUNT,
        "tests_run": sum(int(payload["tests_run"]) for payload in ordered),
        "failures": 0,
        "errors": 0,
        "skipped": sum(int(payload.get("skipped", 0)) for payload in ordered),
        "shard_test_counts": [len(items) for items in executed],
        "shard_durations_seconds": [
            float(payload.get("duration_seconds", 0.0)) for payload in ordered
        ],
        "executed_test_ids": [test_id for items in executed for test_id in items],
    }


def _terminate(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is None:
        process.kill()
    process.wait()


def run_all_shards(evidence_dir: Path, *, timeout_seconds: int) -> int:
    """Run all eight shards concurrently and persist exact aggregate evidence."""
    if isinstance(timeout_seconds, bool) or timeout_seconds <= 0:
        raise ShardError("timeout must be a positive number of seconds.")
    evidence = Path(evidence_dir)
    evidence.mkdir(parents=True, exist_ok=True)
    cases = discover_test_cases()
    canonical_ids = tuple(_case_id(test) for test in cases)
    partitions = partition_test_cases(cases)
    script = Path(__file__).resolve()
    worker_environment = os.environ.copy()
    worker_environment["PYTHONDONTWRITEBYTECODE"] = "1"
    started = datetime.now(timezone.utc)
    wall_timer = time.monotonic()

    processes: list[tuple[int, subprocess.Popen[bytes], TextIO, TextIO, float]] = []
    try:
        for index in range(SHARD_COUNT):
            stdout_path = evidence / f"shard-{index}.stdout.log"
            stderr_path = evidence / f"shard-{index}.stderr.log"
            result_path = evidence / f"shard-{index}.result.json"
            stdout_handle = stdout_path.open("w", encoding="utf-8")
            stderr_handle = stderr_path.open("w", encoding="utf-8")
            command = [
                sys.executable,
                str(script),
                "--shard-index",
                str(index),
                "--result-json",
                str(result_path),
            ]
            process = subprocess.Popen(
                command,
                cwd=ROOT,
                env=worker_environment,
                stdout=stdout_handle,
                stderr=stderr_handle,
            )
            processes.append(
                (index, process, stdout_handle, stderr_handle, time.monotonic())
            )

        pending = {index for index in range(SHARD_COUNT)}
        timed_out: list[int] = []
        while pending:
            for index, process, _, _, process_started in processes:
                if index not in pending:
                    continue
                if process.poll() is not None:
                    pending.remove(index)
                elif time.monotonic() - process_started > timeout_seconds:
                    _terminate(process)
                    pending.remove(index)
                    timed_out.append(index)
            if pending:
                time.sleep(0.1)
    finally:
        for _, process, stdout_handle, stderr_handle, _ in processes:
            if process.poll() is None:
                _terminate(process)
            stdout_handle.close()
            stderr_handle.close()

    aggregate_path = evidence / "aggregate.result.json"
    if timed_out:
        _write_json(
            aggregate_path,
            {
                "status": "timed_out",
                "timed_out_shards": sorted(timed_out),
                "timeout_seconds": timeout_seconds,
                "canonical_test_count": len(canonical_ids),
                "shard_test_counts": [len(items) for items in partitions],
                "duration_seconds": round(time.monotonic() - wall_timer, 3),
            },
        )
        return 2

    payloads: list[dict[str, object]] = []
    try:
        for index, process, _, _, _ in processes:
            result_path = evidence / f"shard-{index}.result.json"
            if not result_path.is_file():
                raise ShardError(f"shard {index} did not write result evidence.")
            payload = json.loads(result_path.read_text(encoding="utf-8-sig"))
            if not isinstance(payload, dict):
                raise ShardError(f"shard {index} wrote a non-object result.")
            if process.returncode != payload.get("exit_code"):
                raise ShardError(f"shard {index} process/result exit codes disagree.")
            payloads.append(payload)
        aggregate = aggregate_results(canonical_ids, payloads)
    except (json.JSONDecodeError, OSError, ShardError) as error:
        _write_json(
            aggregate_path,
            {
                "status": "failed",
                "error": str(error),
                "canonical_test_count": len(canonical_ids),
                "shard_process_exit_codes": [
                    process.returncode for _, process, _, _, _ in processes
                ],
                "duration_seconds": round(time.monotonic() - wall_timer, 3),
            },
        )
        return 1

    aggregate.update(
        {
            "canonical_test_count": len(canonical_ids),
            "started_utc": started.isoformat(),
            "ended_utc": datetime.now(timezone.utc).isoformat(),
            "duration_seconds": round(time.monotonic() - wall_timer, 3),
            "timeout_seconds_per_shard": timeout_seconds,
        }
    )
    _write_json(aggregate_path, aggregate)
    return 0


def _positive_integer(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be an integer") from error
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def parse_arguments(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python scripts/run_test_shards.py",
        description="Run the canonical unittest inventory in eight exhaustive shards."
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--shard-index", type=int, choices=range(SHARD_COUNT))
    mode.add_argument("--all", action="store_true")
    parser.add_argument("--result-json", type=Path)
    parser.add_argument("--evidence-dir", type=Path)
    parser.add_argument("--timeout-seconds", type=_positive_integer, default=5400)
    parsed = parser.parse_args(arguments)
    if parsed.all:
        if parsed.evidence_dir is None:
            parser.error("--all requires --evidence-dir")
        if parsed.result_json is not None:
            parser.error("--result-json belongs to one-shard mode")
    elif parsed.evidence_dir is not None:
        parser.error("--evidence-dir belongs to --all mode")
    return parsed


def main(arguments: Sequence[str] | None = None) -> int:
    parsed = parse_arguments(arguments)
    try:
        if parsed.all:
            return run_all_shards(
                parsed.evidence_dir, timeout_seconds=parsed.timeout_seconds
            )
        return run_shard(parsed.shard_index, result_path=parsed.result_json)
    except ShardError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
