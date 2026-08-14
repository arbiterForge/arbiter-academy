---
id: U02-override-audit-metrics
track: power-user
order: 2
title: Observe an audit guard without changing the audit trail
outcome: Preserve a bound audit-log baseline, observe one harmless H-05 pre-write refusal, and commit one constrained local observation note.
prerequisites: U01-autonomous-sprint
estimated_minutes: 25
scenario_command: {{action:U02-prepare}}
checkpoint_command: {{action:U02-check}}
next_lab: U03-refactor-chore-release
---

# U02: Observe an audit guard without changing the audit trail

## Know before you begin

U02 is a published Power User lesson in Preview 0.21. The website action cards are the primary route; the Academy CLI only prepares, checks, and resets the local attempt.

Keep a native terminal and one supported CodeArbiter harness at the same clone. Native terminal commands never begin with `!`. Harness shell commands begin with exactly one `!`. Host CodeArbiter commands never begin with `!`.

{{action:U02-read-boundary}}

## What you will prove

Prepare snapshots the exact `.codearbiter/overrides.log` bytes and proves they equal `HEAD`. You then make one `git restore --source=HEAD` request. H-05 must refuse it before Git runs; without a guard, that request is content-neutral because the target already equals `HEAD`.

The only learner commit is a constrained observation note. It records the protected target, baseline digest, the displayed refusal line, and that line's digest. It does not prove the refusal chronology: a learner can manually imitate the note, so Check must not present a pass as provenance for a live harness event, a human approval, or a hosted fact.

Audit and metrics may be useful optional read-only observations, but they are not required and never feed the proof of chronology.

## Prepare safely

{{action:U02-prepare}}

After Prepare has bound the scenario and baseline, inspect the protected file without touching it.

{{action:U02-inspect-baseline}}

## Practice

Run the next card exactly once in the harness shell. It is intentionally a content-neutral restore request that the real H-05 shell guard blocks, not a workaround and not an override. If the guard does not refuse it, stop and preserve the resulting state for investigation.

{{action:U02-attempt-guarded-restore}}

Ask the agent to draft the note from the local values. Do not invent a result or change the audit log.

{{action:U02-record-observation}}

{{action:U02-review-observation-boundary}}

{{action:U02-stage-observation}}

{{action:U02-commit-observation}}

## Recognize success

The attempt has one child commit after Prepare and changes exactly `.codearbiter/reports/academy/U02-observation.md`. Its protected `.codearbiter/overrides.log` blob is identical to the prepared commit. The note contains the exact H-05-shaped event line plus matching SHA-256 values for the event and baseline.

This is deliberately a local, deterministic evidence boundary. It cannot establish who caused a refusal, whether it happened in the asserted order, whether a reviewer agreed, or whether any hosted system observed it.

## Check

{{action:U02-check}}

## Recover or continue

If Check reports a mismatch, correct only the observation note. Do not append, rewrite, or delete entries in the protected log. If the attempt itself is no longer trustworthy, use Reset instead of history rewriting.

**Hint 1.** The `git restore --source=HEAD` request should be blocked by H-05. The HEAD-equality precondition makes a missing guard content-neutral, but it is still a host-install stop condition.

**Hint 2.** The observation note has exactly one allowed commit path. Audit or metrics output is optional context, not a second artifact to stage.

**Hint 3.** An actual override belongs only to the optional U07 capstone branch; U02 teaches why a guard exists before any later decision to bypass one.

{{action:U02-reset}}

## Understand the mechanism

The guide and action manifest are one contract. The renderer turns each action reference into the same website card, selecting the right browser, native-terminal, harness, agent, and copy-control treatment. The checkpoint is the local deterministic authority for the prepared baseline, changed path, commit shape, and note bytes. It intentionally stops short of asserting perfect provenance for a manually reproducible observation.
