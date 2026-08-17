---
id: U02-override-audit-metrics
track: power-user
order: 2
title: Observe an audit-log guard without changing the audit trail
outcome: Observe one H-05 refusal, preserve the protected audit log, and commit a limited local observation note without claiming that the refusal chronology is proven.
prerequisites: U01-autonomous-sprint
estimated_minutes: 25
scenario_command: {{action:U02-prepare}}
checkpoint_command: {{action:U02-check}}
next_lab: U03-refactor-chore-release
---

# U02: Observe an audit-log guard without changing the audit trail

## Know before you begin

U02 is a published Power User lesson in Preview 0.30. The action cards are the primary route. Academy provides local Prepare, Check, and Reset helpers.

Keep a native terminal and one supported CodeArbiter harness at the same clone. Native shell commands never begin with `!`. Harness shell commands begin with exactly one `!`. Host CodeArbiter commands never begin with `!`.

{{action:U02-read-boundary}}

## What you will prove

Prepare creates a numbered U02 branch with a committed scenario overlay and binds the starting bytes of `.codearbiter/overrides.log`. The learner makes one content-neutral restore request. H-05 protects the audit log from that rewrite-shaped shell operation before Git runs.

The only committed learner artifact is `.codearbiter/reports/academy/U02-observation.md`. It records the prepared baseline digest and the displayed H-05 line, then says plainly that a written note cannot prove the event chronology. The audit log remains unchanged.

This lesson does not practice `$ca-override`, write audit packets, or preserve metrics output. Those are separate real CodeArbiter surfaces. Do not represent an Academy note as their output.

## Prepare safely

### Create the prepared U02 attempt

{{action:U02-prepare}}

## Practice

### Observe the protected path once

{{action:U02-inspect-baseline}}

{{action:U02-attempt-guarded-restore}}

### Preserve the limited local note

{{action:U02-record-observation}}

{{action:U02-review-observation-boundary}}

{{action:U02-stage-observation}}

{{action:U02-commit-observation}}

## Recognize success

The prepared attempt has exactly one child commit. It changes only `.codearbiter/reports/academy/U02-observation.md`; `.codearbiter/overrides.log` is byte-for-byte identical to the prepared baseline. The note has eight lines, including the displayed H-05 line and the chronology limitation.

This is not proof that the selected host ran the command at a particular time. It is a bounded local record whose path, bytes, prepared baseline, and commit scope Check can validate.

## Check

Check validates the prepared baseline, protected-log preservation, note bytes, one child commit, and clean worktree. It does not authenticate a transcript, a person, or a hosted result.

{{action:U02-check}}

## Recover or continue

If Check reports a mismatch, correct only the observation note. Do not edit `.codearbiter/overrides.log`, add a second event line, invent an override, or rewrite the attempt.

**Hint 1.** The probe is exactly `git restore --source=HEAD -- .codearbiter/overrides.log` through the harness shell. It is safe because Prepare bound the target to HEAD before the probe.

**Hint 2.** The note uses the displayed `BLOCKED [H-05]: ...` text verbatim. Hash that exact UTF-8 text for `event_sha256`.

**Hint 3.** Reset is only for an attempt that cannot be corrected inside the observation-note boundary. It preserves rather than erases the failed attempt.

{{action:U02-reset}}

## Understand the mechanism

The guide and action manifest are one contract. The renderer turns each action reference into the same website card, with the correct operating-system, harness, and copy control. Check is the deterministic authority for the local artifact boundary. It does not claim a command invocation, approval, or event chronology that repository state cannot establish.
