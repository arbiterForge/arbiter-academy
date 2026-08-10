# Coding standards - Workshop Queue Academy fixture

## Python

- Use Python 3 and the standard library only; adding a package requires the
  dependency lane and its recorded review.
- Keep persistence behind the store boundary described in
  [ADR-0001](decisions/0001-json-storage-boundary.md).
- Validate user-controlled values at command boundaries; malformed fixture input
  produces a clear local error, never a network fallback.
- Tests use `unittest`, name observable behavior, and operate against local data.

## Text artifacts

- Tracked text is UTF-8 without a byte-order mark and uses LF line endings.
- Task IDs use `group.type.0000` grammar. Board transitions retain their dates.
- Audit artifacts are append-only; historical material is labeled as a fixture.
- Use relative Markdown links for local cross-references; every link must resolve.

## Boundary

The Academy fixture remains local-first: no network client, paid service, secret
store, or remote queue is introduced by an exercise.
