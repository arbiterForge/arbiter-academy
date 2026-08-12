---
id: P06-context-drift-recovery
track: practitioner
order: 6
title: Recover context drift without losing unrelated work
outcome: Repair one source-contradicted context claim through re-scout while preserving the prepared unrelated note byte-for-byte.
prerequisites: P05-checkpoint-remediation
estimated_minutes: 30
scenario_command: {{action:P06-prepare}}
checkpoint_command: {{action:P06-check}}
next_lab: P07-threat-model
---

# P06 - Recover context drift without losing unrelated work

## Know before you begin

This is private authoring material. It is unavailable in Preview 0.7. Its action cards document an unreleased lesson and do not create a public course route.

Complete P05 in the same Academy fork and clone. Before Prepare, return to `main` and confirm that
your worktree is clean: `git status --short` should print nothing. Keep a native terminal open at
the clone root for Academy Prepare, Check, and Reset. Keep one CodeArbiter harness open at that
same clone for inspection, the context audit, and the two governed commits.

This is a recovery lesson, not a cleanup lesson. The prepared scenario contains a stale
`.codearbiter/CONTEXT.md`, a matching stale provenance record, and an unrelated
`docs/preserved-note.md`. You will prove that the note survived byte-for-byte. Never delete,
recreate, normalize, or “tidy” it.

Native-terminal commands are entered directly and never start with `!`. CodeArbiter commands and
agent messages are entered in your selected harness and never start with `!`. Every action card
names the actor and the surface so you do not have to infer where a command belongs.

## What you will prove

The prepared context says `Workshop Queue report output is JSON-only.` The prepared source proves
the opposite: stable text is the default and structured JSON is optional. The old lifecycle link
also points to ADR-0002 even though P05 accepted ADR-0005. The provenance record names the older
CLI object `042746e43698e5d2a6de4c536f1024f893aef805`; the prepared source object is
`5b41fb168a8b258cfae7eebc46e8b9ea7696ba56`.

You will make exactly two ordered single-parent commits after Prepare. The first changes only the
context and provenance record. The second introduces only a canonical recovery handoff. Academy
Check independently compares those commits with the prepared baseline and verifies that the
unrelated note has identical raw Git-object bytes before and after the repair.

## Prepare safely

{{action:P06-prepare}}

`ATTEMPT_NUMBER` means the number Academy prints, such as `1`; do not type that word literally.
Stay on the numbered branch until Check passes or Reset creates a preserved retry.

{{action:P06-inspect-evidence}}

## Practice

{{action:P06-run-context-audit}}

{{action:P06-select-rescout}}

`re-scout` is the sole permitted recovery route because the prepared source directly contradicts
the recorded claim. It refreshes this bounded evidence; it does not authorize an alternate route,
a broad context rewrite, or a new baseline.

{{action:P06-apply-correction}}

{{action:P06-review-correction-boundary}}

{{action:P06-commit-correction}}

{{action:P06-write-handoff}}

{{action:P06-review-handoff-boundary}}

{{action:P06-commit-handoff}}

## Recognize success

The first learner commit after Prepare changes exactly `.codearbiter/CONTEXT.md` and
`.codearbiter/.provenance/CONTEXT.json`. The second changes exactly
`.codearbiter/reports/academy/P06-recovery.json`. The corrected context states:
`Workshop Queue report output defaults to stable text and supports structured JSON with --format json.`

The handoff declares `re-scout`, identifies the prepared and correction commits, records the
before/after SHA-256 values for context, provenance, and the preserved note, and has identical
before/after note digests. Immediately before Check, `git status --short` prints nothing.

## Check

{{action:P06-check}}

A pass contains `checkpoint P06-context-drift-recovery: passed; progress: .academy/progress.json`.
Check proves the committed state, path boundaries, topology, raw-object digests, and preserved-note
identity. It does not prove that the host command ran, that a particular agent made an edit, or why
you selected the route. Those are honest workflow observations, not final-state claims.

## Recover or continue

If Check names a failed predicate, preserve the committed attempt and compare the failure with the
matching action card. Do not amend, rebase, force-reset, or conceal an earlier attempt.

### Hint 1

The stale claim is a source contradiction, not a date mismatch. Compare the report parser choices
and default with the context statement before you choose a route.

### Hint 2

Before values come from the prepared Git objects. A filesystem hash read after an edit cannot prove
what the prepared context, provenance, or note contained.

### Hint 3

Keep the correction and handoff separate. The first commit has two paths; the second has one. The
note’s two digests match because leaving an unrelated file untouched is the point of the exercise.

{{action:P06-reset-retry}}

After Check passes, leave the completed branch intact and return to `main` when you are ready. P07
appears on the course home only after its guided rewrite and acceptance evidence are complete. Do
not use unpublished source exercises as a substitute for the accepted course.

## Understand the mechanism

Context becomes trustworthy when its claims can be traced to the source and decision that support
them. A re-scout repairs a contradiction without pretending all repository context was freshly
reviewed. The two commits separate the source-backed correction from the record that describes it;
the external verifier then reconstructs both against the prepared baseline. Keeping unrelated work
byte-identical makes recovery auditable instead of destructive.
