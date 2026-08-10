# ADR-0003: Treat local graduation as trusted-verifier evidence, not cryptographic attestation

- **Status:** accepted
- **Date:** 2026-07-31
- **Decided by:** SUaDtL
- **Decision category:** architecture
- **Supersedes:** none

## Context

Arbiter Academy runs entirely in a learner-controlled local repository. Its checkpoint engine can
recompute Git and governed-artifact evidence, reject stale or fabricated records, and bind a
graduation receipt to exact commits. It cannot cryptographically authenticate verifier code loaded
from the same mutable checkout: a user with arbitrary local code execution can replace both the
verifier and any receipt it emits.

The Academy has no hosted attestation service, signing key, authentication system, or paid
dependency. Claiming that an in-repository script produces tamper-proof credentials would therefore
be false.

## Decision

Authoritative `check` and `graduate` operations run through an Academy verifier installed outside
the learner checkout and target the checkout explicitly. The learner repository, Git history, and
governed artifacts are untrusted inputs; the installed verifier process is the local trust anchor.

The resulting receipt is deterministic, privacy-safe, tamper-evident evidence under that trust
model. It is not a cryptographically signed credential and does not prove resistance to an operator
who replaces the installed verifier or hand-authors a receipt. Documentation and receipt metadata
must state this boundary plainly.

Repository-local tooling may prepare, reset, update, export, or provide development diagnostics, but
must not silently present an in-checkout `check` or `graduate` run as authoritative.

## SMARTS rationale

This choice is strong for Maintainability, Availability, Reliability, Testability, and Securability:
it preserves the offline, no-spend curriculum; establishes a testable verifier/input boundary; and
avoids false cryptographic claims. A hosted verifier or signed credential would require a new
service, authentication, key custody, and operational budget. Treating the mutable checkout as its
own trust anchor is weak for correctness because it is circular.

## Consequences

- `academy_engine` is packaged with a dedicated console entry point.
- Authoritative commands reject execution when the loaded verifier resides inside the target
  learner repository.
- Verification instructions install or invoke a built verifier artifact outside the learner clone.
- Subprocess output, manifests, receipts, identities, remotes, nested repositories, and attempt
  histories remain strictly bounded and recomputed.
- Graduation receipts identify their trust model and remain locally reproducible, not signed.
- A future hosted or cryptographically signed attestation system requires a new ADR and explicit
  security-control approval.
