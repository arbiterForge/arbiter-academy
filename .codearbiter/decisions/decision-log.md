## DECISION-0001 — ADR-0001 — Keep ticket persistence at a validated local JSON boundary

**Date:** 2026-07-30
**Status:** accepted
**Supersedes:** none
**Decided by:** SUaDtL
**Decision category:** architecture
**Artifact-section-hash:** n/a

### Variance summary
- **Artifact position:** The approved Academy specification selects an offline Python CLI with deterministic local JSON persistence.
- **Scaffold position:** The new Academy repository had no prior persistence decision.
- **Status type:** open-decision-closure

### Decision
Workshop Queue keeps ticket state in validated local JSON behind one bounded store. Source checkouts
use repository-local data; installed use initializes a packaged seed into app-specific user data.

### SMARTS rationale
The choice is strong for Maintainability, Availability, Reliability, Testability, and Securability:
it shares codeArbiter's Python prerequisite, remains offline, supports atomic replacement and
temporary-root tests, and makes path containment explicit. Hosted or opaque storage would add
prerequisites without improving the curriculum.

### Implementation implication
`workshop_queue/store.py` owns validated atomic persistence, `workshop_queue/app_data.py` owns trusted
data-root selection and seed initialization, and their tests must defend both boundaries.

---

## DECISION-0003 — ADR-0003 — Treat local graduation as trusted-verifier evidence, not cryptographic attestation

**Date:** 2026-07-31
**Status:** accepted
**Supersedes:** none
**Decided by:** SUaDtL
**Decision category:** architecture
**Artifact-section-hash:** n/a

### Variance summary
- **Artifact position:** The Academy specification requires recomputed, privacy-safe local graduation evidence.
- **Scaffold position:** The local-only fixture had no explicit verifier bootstrap or attestation boundary.
- **Status type:** open-decision-closure

### Decision
Authoritative checks run from an Academy verifier installed outside the learner checkout. The
checkout is untrusted input; the local verifier process is the trust anchor. Receipts are
tamper-evident under that boundary, not cryptographically signed credentials.

### SMARTS rationale
The installed-verifier boundary is strong for Maintainability, Availability, Reliability,
Testability, and Securability because it remains offline and no-spend while avoiding a circular
self-attestation claim. Hosted or signed attestation adds service, authentication, and key-custody
boundaries outside the approved project.

### Implementation implication
Package `academy_engine` with an external console entry point, reject authoritative commands loaded
from the target checkout, state the trust model in receipts/docs, and retain strict recomputation of
all learner-controlled inputs.

---

## DECISION-0002 — ADR-0002 — Enforce an explicit immutable ticket state machine

**Date:** 2026-07-30
**Status:** accepted
**Supersedes:** none
**Decided by:** SUaDtL
**Decision category:** architecture
**Artifact-section-hash:** n/a

### Variance summary
- **Artifact position:** The approved Academy plan requires immutable models, enumerated states, and explicit transition functions.
- **Scaffold position:** The new Academy repository had no prior lifecycle decision.
- **Status type:** open-decision-closure

### Decision
Tickets use the explicit states `open`, `claimed`, and `completed`, with only open-to-claimed and
claimed-to-completed transitions. Domain functions return immutable replacements and reject invalid
or missing-ticket operations before persistence.

### SMARTS rationale
The explicit state machine is strong for Maintainability, Reliability, Testability, and
Securability because the valid graph is small, domain-owned, deterministic, and covered without CLI
or filesystem effects. Ad hoc mutation would be faster only at the cost of silent invalid states.

### Implementation implication
`workshop_queue/model.py` owns immutable ticket values, `workshop_queue/service.py` owns transitions,
and model/service tests must fail for any unapproved state or transition.

---
