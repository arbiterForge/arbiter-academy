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
