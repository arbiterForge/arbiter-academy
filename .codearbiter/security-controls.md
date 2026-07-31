# Security controls - Workshop Queue Academy fixture

## Data and trust boundary

Workshop Queue persists only learner-created demonstration tickets in a local JSON
file. The application does not send ticket data over a network. The boundary and
validation rationale are in [ADR-0001](decisions/0001-json-storage-boundary.md).

Authoritative Academy `check` and `graduate` operations use a verifier installed
outside the explicitly selected learner repository. The checkout and all Git and
artifact data it contains are untrusted inputs; the installed local verifier is the
trust anchor. Receipts label this model and are deterministic, tamper-evident local
evidence, not signed credentials. The boundary and its limits are in
[ADR-0003](decisions/0003-local-verifier-trust-boundary.md).

## Sensitive material

- Do not place credentials, personal contact details, private keys, or real ticket
  contents in Academy fixtures, tests, logs, or reports.
- Training identities use role names only; historical dates are fictional fixtures.
- No secret store or authentication mechanism is needed for this local-first exercise.
- Verifier output, Git output, manifests, identities, hashes, and receipt values are
  strictly bounded and validated before use or serialization.

## Dependency and release controls

- Runtime remains Python standard library only. A proposed package is blocked until
  provenance, license, and offline impact are reviewed.
- The release board item is local exercise evidence, not authority to publish.

The [baseline checkpoint](checkpoints/2026-07-20-baseline.md) records the starting
review posture.
