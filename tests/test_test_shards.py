"""Mutation-proof contracts for exhaustive unittest sharding."""

from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

from scripts import run_test_shards as shards


ROOT = Path(__file__).resolve().parents[1]


def _flatten_independently(suite: unittest.TestSuite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from _flatten_independently(item)
        else:
            yield item


class _FactoryLoader:
    errors: list[str] = []

    def __init__(self, factory):
        self.factory = factory

    def discover(self, *args, **kwargs):
        return self.factory()


class TestShardContracts(unittest.TestCase):
    def test_all_shards_disable_worker_bytecode_writes_without_dropping_environment(self) -> None:
        """Catches concurrent workers mutating the shared checkout with pycache files."""
        case_type = type(
            "PassingCase",
            (unittest.TestCase,),
            {
                f"test_{index}": (lambda self: None)
                for index in range(shards.SHARD_COUNT)
            },
        )
        cases = tuple(
            case_type(f"test_{index}") for index in range(shards.SHARD_COUNT)
        )
        partitions = shards.partition_test_cases(cases)
        environments: list[dict[str, str]] = []

        class CompletedProcess:
            returncode = 0

            def poll(self):
                return 0

            def kill(self):
                raise AssertionError("a completed synthetic shard must not be killed")

            def wait(self):
                return 0

        def launch(command, *, cwd, env, stdout, stderr):
            self.assertEqual(cwd, shards.ROOT)
            environments.append(env)
            index = int(command[command.index("--shard-index") + 1])
            result_path = Path(command[command.index("--result-json") + 1])
            planned = [test.id() for test in partitions[index]]
            result_path.write_text(
                json.dumps(
                    {
                        "shard_index": index,
                        "shard_count": shards.SHARD_COUNT,
                        "status": "passed",
                        "exit_code": 0,
                        "planned_test_ids": planned,
                        "executed_test_ids": planned,
                        "tests_run": len(planned),
                        "failures": 0,
                        "errors": 0,
                        "skipped": 0,
                    }
                ),
                encoding="utf-8",
            )
            return CompletedProcess()

        with tempfile.TemporaryDirectory() as temporary, patch.dict(
            os.environ,
            {"PYTHONDONTWRITEBYTECODE": "0", "ACADEMY_ENV_SENTINEL": "preserved"},
        ), patch.object(
            shards, "discover_test_cases", return_value=cases
        ), patch.object(
            shards.subprocess, "Popen", side_effect=launch
        ):
            exit_code = shards.run_all_shards(
                Path(temporary), timeout_seconds=60
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(len(environments), shards.SHARD_COUNT)
        for environment in environments:
            self.assertEqual(environment["PYTHONDONTWRITEBYTECODE"], "1")
            self.assertEqual(environment["ACADEMY_ENV_SENTINEL"], "preserved")

    def test_readme_names_the_explicit_local_release_wrapper(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn(
            "python scripts/run_test_shards.py --all --evidence-dir",
            readme,
        )

    def test_discovery_exactly_matches_the_canonical_unittest_inventory(self) -> None:
        loader = unittest.TestLoader()
        suite = loader.discover(str(ROOT / "tests"), pattern="test_*.py")
        self.assertEqual(loader.errors, [])
        expected = sorted(test.id() for test in _flatten_independently(suite))

        actual = [test.id() for test in shards.discover_test_cases()]

        self.assertTrue(expected)
        self.assertEqual(actual, expected)
        self.assertEqual(len(actual), len(set(actual)))

    def test_eight_shards_are_exact_disjoint_stable_round_robin_partitions(self) -> None:
        cases = shards.discover_test_cases()
        canonical = tuple(test.id() for test in cases)

        first = shards.partition_test_cases(cases)
        second = shards.partition_test_cases(shards.discover_test_cases())
        first_ids = tuple(tuple(test.id() for test in shard) for shard in first)
        second_ids = tuple(tuple(test.id() for test in shard) for shard in second)

        self.assertEqual(shards.SHARD_COUNT, 8)
        self.assertEqual(first_ids, second_ids)
        self.assertEqual(first_ids, tuple(canonical[index::8] for index in range(8)))
        self.assertEqual(set().union(*(set(items) for items in first_ids)), set(canonical))
        for left in range(8):
            for right in range(left + 1, 8):
                self.assertTrue(set(first_ids[left]).isdisjoint(first_ids[right]))
        self.assertLessEqual(max(map(len, first_ids)) - min(map(len, first_ids)), 1)

        p02_counts = [
            sum("test_exercise_state.P02RealRepositoryTests" in test_id for test_id in items)
            for items in first_ids
        ]
        self.assertGreater(sum(p02_counts), 100)
        self.assertLessEqual(max(p02_counts) - min(p02_counts), 1)

    def test_partition_validation_fails_closed_on_omission_duplicate_or_assignment_drift(self) -> None:
        canonical = tuple(f"test.module.Case.test_{index:03d}" for index in range(24))
        valid = [list(canonical[index::8]) for index in range(8)]
        shards.validate_partition(canonical, valid)

        mutations = {}
        omitted = [list(items) for items in valid]
        omitted[0].pop()
        mutations["omission"] = omitted
        duplicated = [list(items) for items in valid]
        duplicated[1].append(valid[0][0])
        mutations["duplicate"] = duplicated
        reassigned = [list(items) for items in valid]
        reassigned[0][0], reassigned[1][0] = reassigned[1][0], reassigned[0][0]
        mutations["assignment"] = reassigned
        reordered = [list(items) for items in valid]
        reordered[0][0], reordered[0][1] = reordered[0][1], reordered[0][0]
        mutations["order"] = reordered

        for label, mutation in mutations.items():
            with self.subTest(label=label), self.assertRaises(shards.ShardError):
                shards.validate_partition(canonical, mutation)

    def test_discovery_rejects_loader_errors_empty_inventory_and_duplicate_ids(self) -> None:
        class PassingCase(unittest.TestCase):
            def test_passes(self) -> None:
                self.assertTrue(True)

        cases = (
            (
                "loader error",
                _FactoryLoader(lambda: unittest.TestSuite([PassingCase("test_passes")])),
            ),
            ("empty", _FactoryLoader(unittest.TestSuite)),
            (
                "duplicate",
                _FactoryLoader(
                    lambda: unittest.TestSuite(
                        [PassingCase("test_passes"), PassingCase("test_passes")]
                    )
                ),
            ),
        )
        cases[0][1].errors = ["synthetic loader failure"]

        for label, loader in cases:
            with self.subTest(label=label), self.assertRaises(shards.ShardError):
                shards.discover_test_cases(loader=loader)

    def test_cli_rejects_missing_empty_non_numeric_and_out_of_range_shards(self) -> None:
        invalid = (
            [],
            ["--shard-index", ""],
            ["--shard-index", "not-a-number"],
            ["--shard-index", "-1"],
            ["--shard-index", "8"],
            ["--all"],
        )
        for arguments in invalid:
            with self.subTest(arguments=arguments), redirect_stderr(
                io.StringIO()
            ), self.assertRaises(SystemExit) as raised:
                shards.parse_arguments(arguments)
            self.assertEqual(raised.exception.code, 2)

    def test_one_shard_returns_unittest_success_and_failure_semantics(self) -> None:
        class MixedCase(unittest.TestCase):
            def test_fail_one(self) -> None:
                self.fail("synthetic shard failure one")

            def test_fail_two(self) -> None:
                self.fail("synthetic shard failure two")

            def test_pass_one(self) -> None:
                self.assertTrue(True)

            def test_pass_two(self) -> None:
                self.assertTrue(True)

            def test_pass_three(self) -> None:
                self.assertTrue(True)

            def test_pass_four(self) -> None:
                self.assertTrue(True)

            def test_pass_five(self) -> None:
                self.assertTrue(True)

            def test_pass_six(self) -> None:
                self.assertTrue(True)

            def test_pass_seven(self) -> None:
                self.assertTrue(True)

            def test_pass_eight(self) -> None:
                self.assertTrue(True)

        def suite_factory():
            return unittest.TestSuite(
                [
                    MixedCase("test_pass_one"),
                    MixedCase("test_fail_one"),
                    MixedCase("test_pass_two"),
                    MixedCase("test_fail_two"),
                    MixedCase("test_pass_three"),
                    MixedCase("test_pass_four"),
                    MixedCase("test_pass_five"),
                    MixedCase("test_pass_six"),
                    MixedCase("test_pass_seven"),
                    MixedCase("test_pass_eight"),
                ]
            )

        cases = shards.discover_test_cases(loader=_FactoryLoader(suite_factory))
        partitions = shards.partition_test_cases(cases)
        failing_index = next(
            index
            for index, partition in enumerate(partitions)
            if any("test_fail" in test.id() for test in partition)
        )
        passing_index = next(
            index
            for index, partition in enumerate(partitions)
            if partition and all("test_pass" in test.id() for test in partition)
        )

        with tempfile.TemporaryDirectory() as temporary:
            result_path = Path(temporary) / "result.json"
            failure_stream = io.StringIO()
            failure_code = shards.run_shard(
                failing_index,
                loader=_FactoryLoader(suite_factory),
                stream=failure_stream,
                result_path=result_path,
            )
            failure_result = json.loads(result_path.read_text(encoding="utf-8"))
            self.assertEqual(failure_code, 1)
            self.assertIn("FAILED", failure_stream.getvalue())
            self.assertGreater(failure_result["failures"], 0)
            self.assertEqual(
                failure_result["planned_test_ids"],
                failure_result["executed_test_ids"],
            )

            success_stream = io.StringIO()
            success_code = shards.run_shard(
                passing_index,
                loader=_FactoryLoader(suite_factory),
                stream=success_stream,
            )
            self.assertEqual(success_code, 0)
            self.assertIn("OK", success_stream.getvalue())

    def test_aggregate_validation_proves_exact_execution_and_propagates_failure(self) -> None:
        canonical = tuple(f"test.module.Case.test_{index:03d}" for index in range(24))
        partitions = tuple(tuple(canonical[index::8]) for index in range(8))
        payloads = [
            {
                "shard_index": index,
                "shard_count": 8,
                "planned_test_ids": list(partition),
                "executed_test_ids": list(partition),
                "tests_run": len(partition),
                "failures": 0,
                "errors": 0,
                "skipped": 0,
                "exit_code": 0,
                "status": "passed",
            }
            for index, partition in enumerate(partitions)
        ]

        aggregate = shards.aggregate_results(canonical, payloads)
        self.assertEqual(aggregate["tests_run"], len(canonical))
        self.assertEqual(aggregate["status"], "passed")

        mutations = {}
        omitted = json.loads(json.dumps(payloads))
        omitted[0]["executed_test_ids"].pop()
        omitted[0]["tests_run"] -= 1
        mutations["omission"] = omitted
        duplicated = json.loads(json.dumps(payloads))
        duplicated[1]["executed_test_ids"].append(duplicated[0]["executed_test_ids"][0])
        duplicated[1]["tests_run"] += 1
        mutations["duplicate"] = duplicated
        failed = json.loads(json.dumps(payloads))
        failed[2]["status"] = "failed"
        failed[2]["failures"] = 1
        failed[2]["exit_code"] = 1
        mutations["failure"] = failed

        for label, mutation in mutations.items():
            with self.subTest(label=label), self.assertRaises(shards.ShardError):
                shards.aggregate_results(canonical, mutation)

    def test_all_shards_default_and_readme_timeout_absorb_local_contention(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            parsed = shards.parse_arguments(
                ["--all", "--evidence-dir", temporary]
            )

        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertEqual(parsed.timeout_seconds, 90 * 60)
        self.assertIn("--timeout-seconds 5400", readme)
        self.assertNotIn("--timeout-seconds 4500", readme)


if __name__ == "__main__":
    unittest.main()
