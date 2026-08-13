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

Preview 0.13 refuses U02 because the Power User track is unavailable and not published there. Prepare, Check, and Reset must leave the repository unchanged. Do not create an attempt, evidence files, or an override record to simulate a published lesson.

The remaining cards specify the future private prepared-attempt contract. In that future private surface, the learner can record one scoped override for the `safe-training-gate` exercise, inspect the append-only local entry, review local audit and metrics output, and commit only the derived evidence boundary.

The checkpoint verifies deterministic local artifacts: new well-formed override lines, their SHA-256 digests in the U02 audit, and exact JSON keys and counts in the U02 metrics file. It does not prove that a human approved an override. It also does not prove that any hosted service accepted, ran, or reported anything.

## Prepare safely

### Current Preview 0.13 refusal

{{action:U02-prepare}}

{{action:U02-read-scenario}}

## Practice

### Future private prepared-attempt contract

Do not run the following actions from Preview 0.13. They document the private course contract only after a future private surface has prepared an attempt.

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

The future private attempt stages exactly four paths: `.codearbiter/overrides.log`, the exact dated audit packet path printed by this attempt's audit command, `.codearbiter/reports/academy/U02-audit.md`, and `.codearbiter/reports/academy/U02-metrics.json`. Historical audit packets may remain unstaged. The new, well-formed `safe-training-gate` override line appears in that printed packet and has its SHA-256 digest in the U02 audit. The metrics JSON has only `schema_version`, `override_count`, and `low_confidence_count`; its override count is one and its low-confidence count is a nonnegative integer.

No card asks you to treat a generated log, audit packet, metric glance, commit, or checkpoint result as proof of your own approval, another person's approval, or a hosted fact.

## Check

Preview 0.13 still refuses the U02 checkpoint action and leaves the repository unchanged. In a future private prepared attempt, its local checkpoint would validate the deterministic evidence contract, but it would not prove a human or hosted fact.

{{action:U02-check}}

## Recover or continue

In the future private contract, if Check reports a missing boundary, correct only that local evidence. Never change prior override lines, make up a digest, or rewrite an attempt to hide a failed check.

**Hint 1.** Re-read the local override lines and include exactly one line added after the future private Prepare step whose gate is exactly `safe-training-gate` and that contains `| BY:` and `| REASON:`.

**Hint 2.** The audit needs the SHA-256 digest of every qualifying new line, not a prose summary of the line.

**Hint 3.** A future private Reset is only for an attempt that cannot be corrected within its evidence boundary. It preserves rather than erases the earlier attempt.

{{action:U02-reset}}

## Understand the mechanism

The guide and action manifest are one contract. The renderer turns each action reference into the same website card, with the correct operating-system, harness, and copy control. The checkpoint remains the local deterministic authority for file shapes and counts; the renderer does not claim that a command was invoked or that an approval happened.
