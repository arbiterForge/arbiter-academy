# Tech stack - Workshop Queue Academy fixture

## Stack

- Python 3.10 or newer.
- Python standard library only at runtime.
- `unittest` from the standard library for tests.
- Local JSON persistence as constrained by [ADR-0001](decisions/0001-json-storage-boundary.md).

## Verification

```sh
python -m unittest discover -v
python -m compileall workshop_queue tests
python -m unittest tests.test_project_state -v
```

The installation test may report its documented offline prerequisite skip when the
build backend is unavailable. All other test results must pass. The baseline is
[the 2026-07-20 checkpoint](checkpoints/2026-07-20-baseline.md).

No database server, package install, external API, or hosted CI requirement belongs
to this Academy fixture.
