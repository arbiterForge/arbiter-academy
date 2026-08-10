# Practitioner

Practitioner turns the Foundations workflow into eight complete governed delivery exercises. The
labs are linear: begin only after F04 passes, keep every deterministic preparation commit, and
finish each exercise with at least one later learner commit on its numbered attempt branch.

| Lab | Observable result | Typical time |
|---|---|---:|
| P01 | A user-approved feature spec, derived plan, and regression-first implementation history | 45 minutes |
| P02 | A reviewed work commit pushed only to a local learner origin, followed by an offline-local receipt | 60 minutes |
| P03 | Accepted ADR 0004 and its matching learner-attributed decision-log entry | 25 minutes |
| P04 | A SMARTS-backed dependency decision made before any permitted manifest change | 35 minutes |
| P05 | A real checkpoint finding linked to a later regression and repair | 45 minutes |
| P06 | Updated context and a digest-bound handoff that preserves unrelated work byte-for-byte | 30 minutes |
| P07 | A complete STRIDE conversation wrapped with separately labeled Academy target binding | 30 minutes |
| P08 | A complete live branch/worktree classification with no destructive cleanup | 30 minutes |

Repository-local `python scripts/academy.py` prepare/reset remains available before P02 has ever
created external verifier state. P02 preparation must use the installed external
`arbiter-academy --repository <learner-repository>` command. Because P02 records are deliberately
preserved, every later Practitioner prepare/reset must keep using that installed command even after
the original GitHub remotes have been restored. Every lab's authoritative check also runs through
the externally installed verifier with an explicit learner repository. Structural track
verification is course-authoring diagnostics only; it does not prove a learner checkpoint.

Reset preserves the failed attempt and starts a fresh numbered branch. It does not authorize
rebasing, force operations, branch deletion, worktree deletion, or removal of evidence. P02 has an
additional fail-closed remote restoration rule, and P08 permits classification and recommendations
only.
