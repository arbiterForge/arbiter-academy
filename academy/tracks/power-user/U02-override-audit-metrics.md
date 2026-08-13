---
id: U02-override-audit-metrics
track: power-user
order: 2
title: Record a scoped override with local audit evidence
outcome: Record one safe training override and bind local audit and metrics evidence without claiming an approval or hosted result.
prerequisites: U01-autonomous-sprint
estimated_minutes: 35
scenario_command: {{action:U02-prepare}}
checkpoint_command: {{action:U02-check}}
next_lab: U03-refactor-chore-release
---

# U02: Record a scoped override with local audit evidence

## Know before you begin

The Power User track remains private. This guide is source material for the shared website action renderer, not a published Preview lesson. The action cards are the primary route; the Academy CLI is only the local Prepare, Check, and Reset helper.

Keep a native terminal and one supported CodeArbiter harness at the same clone. Native shell commands never begin with `!`. Harness shell commands begin with exactly one `!`. Host CodeArbiter commands never begin with `!`.

{{action:U02-read-boundary}}

## What you will prove

Preview 0.14 refuses U02 because the Power User track is unavailable and not published there. Prepare, Check, and Reset must leave the repository unchanged. Do not create an attempt, evidence files, or an override record to simulate a published lesson.

The remaining cards specify the future private prepared-attempt contract. In that future private surface, the learner can record one scoped override for the `safe-training-gate` exercise, inspect the append-only local entry, read the local audit and metrics output, and commit only the real CodeArbiter artifacts.

The checkpoint verifies deterministic local artifacts: one new well-formed override line and the exact `$ca-audit` packet that quotes it. `$ca-metrics` is a read-only, three-line terminal glance; it writes no artifact, and Check does not treat a learner-written transcript or JSON file as metrics output. Check does not prove that a human approved an override or that any hosted service accepted, ran, or reported anything.

## Prepare safely

### Current Preview 0.14 refusal

{{action:U02-prepare}}

{{action:U02-read-scenario}}

## Practice

### Future private prepared-attempt contract

Do not run the following actions from Preview 0.14. They document the private course contract only after a future private surface has prepared an attempt.

{{action:U02-decide-scope}}

{{action:U02-log-override}}

{{action:U02-inspect-log}}

{{action:U02-run-audit}}

{{action:U02-run-metrics}}

{{action:U02-write-evidence}}

{{action:U02-review-evidence-boundary}}

{{action:U02-stage-evidence}}

{{action:U02-commit-evidence}}

## Recognize success

The future private attempt stages exactly two paths: `.codearbiter/overrides.log` and the exact dated audit packet path printed by this attempt's audit command. Historical audit packets may remain unstaged. The new, well-formed `safe-training-gate` override line appears verbatim in that printed packet. The learner reads the `$ca-metrics` glance for context, but does not preserve a transcript, JSON summary, or claim that it proves the command ran.

No card asks you to treat a generated log, audit packet, metric glance, commit, or checkpoint result as proof of your own approval, another person's approval, or a hosted fact.

## Check

Preview 0.14 still refuses the U02 checkpoint action and leaves the repository unchanged. In a future private prepared attempt, its local checkpoint would validate the deterministic evidence contract, but it would not prove a human or hosted fact.

{{action:U02-check}}

## Recover or continue

In the future private contract, if Check reports a missing boundary, correct only that local evidence. Never change prior override lines, make up a digest, or rewrite an attempt to hide a failed check.

**Hint 1.** Re-read the local override lines and include exactly one line added after the future private Prepare step whose gate is exactly `safe-training-gate` and that contains `| BY:` and `| REASON:`.

**Hint 2.** The audit packet must quote the qualifying new line verbatim; do not add an Academy digest or metric summary beside it.

**Hint 3.** A future private Reset is only for an attempt that cannot be corrected within its evidence boundary. It preserves rather than erases the earlier attempt.

{{action:U02-reset}}

## Understand the mechanism

The guide and action manifest are one contract. The renderer turns each action reference into the same website card, with the correct operating-system, harness, and copy control. The checkpoint remains the local deterministic authority for the real artifact boundary; the renderer does not claim that a command was invoked or that an approval happened.
