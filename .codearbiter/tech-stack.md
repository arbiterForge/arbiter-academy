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

### Bounded lab and publication cells

For an ordinary bounded cell, run every focused affected and cross-lab test named
by its approved plan or report. The recorded command must include the direct
behavior suite, structural or curriculum consumers, and any shared-state
dependents identified during implementation or review. A convenient narrow test
is not sufficient evidence when an affected consumer exists.

```sh
python -m unittest <affected modules, classes, or methods> -v
python -m tabnanny academy_engine workshop_queue scripts tests
python -m compileall academy_engine workshop_queue scripts tests
python -m unittest tests.test_project_state -v
python scripts/scan_secrets.py --staged
```

The exact focused unittest command and its cross-lab rationale are commit-gate
evidence. Independent review remains required. `compileall` is syntax
verification, not lint.

### Integration and release milestones

Run the complete real-Git suite at Practitioner consolidation, first-draft
completion, every release or PR gate, or earlier after a demonstrated broad
shared-state regression:

```sh
python -m unittest discover -v
python -m tabnanny academy_engine workshop_queue scripts tests
python -m compileall academy_engine workshop_queue scripts tests
python -m unittest tests.test_project_state -v
python scripts/scan_secrets.py --staged
```

The secret scan reads added, copied, modified, and renamed blobs from Git's staged
index by object identity; it does not substitute mutable worktree content. Exit `1`
reports redacted high-confidence findings and exit `2` fails closed when inspection
cannot be completed.

The application remains dependency-free at runtime. Repository verification also
requires the externally installed Academy verifier and the reviewed offline wheel
proof. An installation test may report its documented offline prerequisite skip only
when the reviewed build backend is unavailable; required release and milestone runs
supply that backend. All other selected or exhaustive test results must pass. The
baseline is [the 2026-07-20 checkpoint](checkpoints/2026-07-20-baseline.md).

Learner runtime and offline lab use require no database server, external API, paid
service, hosted CI, or network connection. Maintainer publication is a separate
repository gate: pull requests and main-branch publication must pass the hosted
Academy verification workflows described above. Those gates verify and publish
the fixture; they do not add a hosted-service dependency to learner execution.
