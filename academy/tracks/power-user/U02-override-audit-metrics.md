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

U02 is a published Power User lesson in Preview 0.21. The action cards are the primary route; the Academy CLI is the local Prepare, Check, and Reset helper.

Keep a native terminal and one supported CodeArbiter harness at the same clone. Native shell commands never begin with `!`. Harness shell commands begin with exactly one `!`. Host CodeArbiter commands never begin with `!`.

{{action:U02-read-boundary}}

## What you will prove

Prepare creates a numbered U02 branch with a committed scenario overlay. The learner then records one narrow, safe override through CodeArbiter, reads the real audit and metrics output, and commits only the two durable CodeArbiter artifacts.

The prepared attempt is deliberately narrow: one `safe-training-gate` override, its append-only local entry, one exact dated audit packet, and the read-only metrics glance. Do not turn either read-only command into a learner-authored receipt.

The checkpoint verifies deterministic local artifacts: one new well-formed override line and the exact `$ca-audit` packet that quotes it. `$ca-metrics` is a read-only, three-line terminal glance; it writes no artifact, and Check does not treat a learner-written transcript or JSON file as metrics output. Check does not prove that a human approved an override or that any hosted service accepted, ran, or reported anything.

## Prepare safely

### Create the prepared U02 attempt

{{action:U02-prepare}}

{{action:U02-read-scenario}}

## Practice

### Work the prepared U02 attempt

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

The prepared attempt stages exactly two paths: `.codearbiter/overrides.log` and the exact dated audit packet path printed by this attempt's audit command. Historical audit packets may remain unstaged. The new, well-formed `safe-training-gate` override line appears verbatim in that printed packet. The learner reads the `$ca-metrics` glance for context, but does not preserve a transcript, JSON summary, or claim that it proves the command ran.

No card asks you to treat a generated log, audit packet, metric glance, commit, or checkpoint result as proof of your own approval, another person's approval, or a hosted fact.

## Check

Check validates the deterministic local evidence contract for this prepared attempt. It does not prove a human or hosted fact.

{{action:U02-check}}

## Recover or continue

If Check reports a missing boundary, correct only that local evidence. Never change prior override lines, make up a transcript or digest, or rewrite an attempt to hide a failed check.

**Hint 1.** Re-read the local override lines and include exactly one line added after Prepare whose gate is exactly `safe-training-gate` and that contains `| BY:` and `| REASON:`.

**Hint 2.** The audit packet must quote the qualifying new line verbatim; do not add an Academy digest or metric summary beside it.

**Hint 3.** Reset is only for an attempt that cannot be corrected within its evidence boundary. It preserves rather than erases the earlier attempt.

{{action:U02-reset}}

## Understand the mechanism

The guide and action manifest are one contract. The renderer turns each action reference into the same website card, with the correct operating-system, harness, and copy control. The checkpoint remains the local deterministic authority for the real artifact boundary; the renderer does not claim that a command was invoked or that an approval happened.
