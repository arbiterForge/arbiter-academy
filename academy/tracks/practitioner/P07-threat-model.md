---
id: P07-threat-model
track: practitioner
order: 7
title: Threat-model the path-handling boundary
outcome: Preserve the complete native threat-model conversation and add a separately labeled Academy identity and SHA-256 binding for academy_engine/paths.py.
prerequisites: P06-context-drift-recovery
estimated_minutes: 30
scenario_command: arbiter-academy --repository <learner-repository> prepare P07-threat-model
checkpoint_command: arbiter-academy --repository <learner-repository> check P07-threat-model
next_lab: P08-repository-hygiene
---

# P07 — Threat-model the path-handling boundary

## Why this mechanism matters

Threat modeling is a scoped design review, not automatic authorization to change a security control.
The codeArbiter conversation has four native fields: Scope, a complete six-row STRIDE table,
Recommended controls, and Clearance. Academy needs additional deterministic target evidence, so the
learner wraps those native fields and adds a clearly separate Academy target identity/SHA section.
That augmented wrapper is Academy evidence; it must never be called native or canonical codeArbiter
output.

## Start the scenario

Run this from the learner checkout. Preserved P02 verifier records require the installed command for
every later Practitioner transition, even though the original GitHub remotes are already restored.
Prepare the archive-import path request:

```powershell
$learnerRepository = (Resolve-Path -LiteralPath '.').Path
arbiter-academy --repository $learnerRepository prepare P07-threat-model
```

The bounded target is `academy_engine/paths.py`. Preparation records its tracked blob and raw
SHA-256 outside the learner checkout and does not prewrite a threat model or weaken containment.

## Use your host

Invoke the opt-in lightweight STRIDE pass for the exact target and request.

### Claude Code

```text
/ca:threat-model "academy_engine/paths.py archive-import containment boundary"
```

### Codex

```text
$ca-threat-model "academy_engine/paths.py archive-import containment boundary"
```

### Pi (Feature Forge preview)

Pi is the supported Feature Forge preview and requires project trust. Its documented fallback is
`/skill:ca-threat-model "academy_engine/paths.py archive-import containment boundary"`.

```text
/ca-threat-model "academy_engine/paths.py archive-import containment boundary"
```

## Do the work

Define path input, trust boundary, archive member behavior, resolved destination, and relevant
assets. Complete all Spoofing, Tampering, Repudiation, Information Disclosure, Denial of Service,
and Elevation of Privilege rows with an applicable disposition; do not leave a row blank or fill it
with generic boilerplate. Preserve the command's Scope, STRIDE table, Recommended controls, and
Clearance exactly as the conversational result.

Create `.codearbiter/reports/academy/P07-threat-model.md`. Put those four fields in a section labeled
as the native codeArbiter conversation. Add a separate **Academy Target-SHA256/identity binding**
section naming `academy_engine/paths.py`, its current tracked blob identity, and the lowercase raw
SHA-256 of those exact head bytes. Commit the wrapper after prepare without changing the target.
This lab assesses controls; it does not authorize implementing them.

## Hints

### Hint 1

Draw the boundary from untrusted archive path/member input through normalization and resolved
containment to the intended extraction root before enumerating threats.

### Hint 2

Traversal and extraction concerns usually require concrete Tampering, Information Disclosure, and
Denial of Service analysis. Give every other STRIDE row an explicit applicable or justified
not-applicable disposition.

### Hint 3

Hash the exact tracked target bytes at the wrapper commit. Keep the Academy identity and digest out
of the four native conversational fields and verify the target never changes afterward.

## Success evidence

The committed Academy wrapper preserves Scope, all six STRIDE dispositions, Recommended controls,
and Clearance, then separately labels an exact target path/blob/raw-SHA binding. Git orders it after
prepare, and the target bytes at head still match the wrapper. Missing fields, generic/blank rows,
mixed metadata, stale digest, another target, post-wrapper mutation, or calling the augmented file
native/canonical output fails.

```powershell
$learnerRepository = (Resolve-Path -LiteralPath '.').Path
arbiter-academy --repository $learnerRepository check P07-threat-model
```

## Recovery

For a wrong target, incomplete model, or stale digest, preserve the attempt and reset:

```powershell
$learnerRepository = (Resolve-Path -LiteralPath '.').Path
arbiter-academy --repository $learnerRepository reset P07-threat-model
```

Do not alter `academy_engine/paths.py` merely to fit an old digest or copy a model from another
attempt.

## Next lab

Continue to **P08 — Classify repository hygiene without destructive cleanup** after P07 passes.
