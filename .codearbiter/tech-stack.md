# Tech stack - Workshop Queue Academy fixture

## Stack

- Python 3.10 or newer.
- Python standard library only at runtime.
- `unittest` from the standard library for tests.
- Local JSON persistence as constrained by [ADR-0001](decisions/0001-json-storage-boundary.md).

## Coverage

No coverage command or threshold is configured for this standard-library Academy
surface. Current TDD uses Phase 4 obligation verification under the no-tooling
exemption.

## Lint

```sh
python -m tabnanny academy_engine workshop_queue scripts tests
```

## Verification

```sh
python -m unittest discover -v
python -m compileall workshop_queue tests
python -m unittest tests.test_project_state -v
python scripts/scan_secrets.py --staged
```

`python -m compileall workshop_queue tests` is syntax verification, not lint.

The secret scan reads added, copied, modified, and renamed blobs from Git's staged
index by object identity; it does not substitute mutable worktree content. Exit `1`
reports redacted high-confidence findings and exit `2` fails closed when inspection
cannot be completed.

The application remains dependency-free at runtime. Repository verification also
requires the externally installed Academy verifier and the reviewed offline wheel
proof. An installation test may report its documented offline prerequisite skip only
when the reviewed build backend is unavailable; required release/acceptance runs supply
that backend. All other test results must pass. The baseline is [the 2026-07-20
checkpoint](checkpoints/2026-07-20-baseline.md).

No database server, external API, paid service, or hosted CI requirement belongs to
this Academy fixture.
