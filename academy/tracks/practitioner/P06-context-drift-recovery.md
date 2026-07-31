---
id: P06-context-drift-recovery
track: practitioner
order: 6
title: Recover context drift without losing unrelated work
outcome: Update stale CONTEXT.md through the documented recovery route while preserving the prepared docs/preserved-note.md bytes exactly.
prerequisites: P05-checkpoint-remediation
estimated_minutes: 30
scenario_command: python scripts/academy.py prepare P06-context-drift-recovery
checkpoint_command: arbiter-academy --repository <learner-repository> check P06-context-drift-recovery
next_lab: P07-threat-model
---

# P06 — Recover from provenance drift without losing unrelated work

## Why this mechanism matters

Context recovery must correct stale provenance without treating unrelated learner work as disposable.
The prepared repository contains `docs/preserved-note.md` before the attempt. A machine-readable
handoff binds the old and new context blobs, while Git proves that exact pre-existing note survives
byte-for-byte. Recreating a similar-looking note after deletion is not preservation.

## Start the scenario

Prepare the stale context and unrelated note:

```powershell
python scripts/academy.py prepare P06-context-drift-recovery
```

Inspect `.codearbiter/CONTEXT.md`, current Workshop Queue summary behavior, accepted decisions, and
`docs/preserved-note.md` before taking a recovery action.

## Use your host

Run the context drift audit and follow its documented re-scout or re-baseline route.

### Claude Code

```text
/ca:context-check
```

### Codex

```text
$ca-context-check
```

### Pi (Feature Forge preview)

Pi is the supported Feature Forge preview and requires project trust. Its documented fallback is
`/skill:ca-context-check`.

```text
/ca-context-check
```

## Do the work

Use the audit to identify the exact context statement that conflicts with tracked implementation or
accepted decision state. Before recovery, record the prepared Git blob identity of
`docs/preserved-note.md` and the raw digest of the prepared `.codearbiter/CONTEXT.md` blob.

Take the scoped re-scout or re-baseline route documented by the command. Update only the stale
context boundary and retain unrelated work. Commit the changed context after prepare.

Create `.codearbiter/reports/academy/P06-recovery.json` after the context change. It records the
repository-relative context and preserved paths plus exact before/after context digests derived from
the corresponding Git blobs. Commit the new handoff. Verify the preserved note existed at prepare
and its head blob is byte-identical; copying current bytes into a newly created file cannot satisfy
that ancestry check.

## Hints

### Hint 1

Compare the context's cited summary boundary with both tracked code and accepted ADRs. Identify one
specific stale provenance claim before choosing re-scout or re-baseline.

### Hint 2

Use Git object reads for the before values. Filesystem reads after editing cannot reconstruct the
prepared `.codearbiter/CONTEXT.md` or prove `docs/preserved-note.md` existed then.

### Hint 3

Recompute the after digest from the committed context blob and compare the preserved note's prepared
and head blob IDs. The context digests must differ; the note bytes must not.

## Success evidence

Git shows `.codearbiter/CONTEXT.md` changed after prepare and a machine-readable recovery handoff was
introduced or changed later with exact ordered before/after digests. `docs/preserved-note.md` exists
in the prepared tree and has identical bytes at head. A pre-existing handoff, reversed/stale digest,
unchanged context, missing prepared note, or recreated/modified note fails.

```powershell
arbiter-academy --repository <learner-repository> check P06-context-drift-recovery
```

## Recovery

If the wrong context boundary changed or the preserved note differs, do not overwrite the note with
a new copy. Preserve the failed attempt and reset:

```powershell
python scripts/academy.py reset P06-context-drift-recovery
```

The archived attempt remains available for diagnosis.

## Next lab

Continue to **P07 — Threat-model the path-handling boundary** after P06 passes.
