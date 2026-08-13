---
id: U05-debug-spike-conflict
track: power-user
order: 5
title: Debug, spike, and conflict without inventing evidence
outcome: Preserve the real findings from a disposable spike, recognize the debug no-action exit, and stop for a real conflict decision.
prerequisites: U04-initialize-projects
estimated_minutes: 30
scenario_command: {{action:U05-prepare-attempt}}
checkpoint_command: {{action:U05-check-status}}
next_lab: U06-preview-and-advanced-surfaces
---

# U05: Debug, spike, and conflict without inventing evidence

## Know before you begin

U05 is a private source contract, not public or runnable in Preview 0.17. The website remains the
primary lesson surface. Current Preview commands refuse to prepare, Check, reset, or write evidence
for U05. Do not substitute an Academy-only branch, report, or made-up command for CodeArbiter.

{{action:U05-confirm-private-boundary}}

## What you will prove

The future private walkthrough requires a matching released integration: CodeArbiter 2.15.1 (Claude); ca-codex 0.7.1 (Codex); or ca-pi 0.8.1 (Pi), each containing the
[findings-only spike contract](https://github.com/arbiterForge/codeArbiter/pull/687): `$ca-spike` uses `spike/<slug>`, retains only
`.codearbiter/spikes/<slug>.md` on the parent, and deletes the spike branch. `$ca-debug` changes no
code and may close with its actual queued `debug.note` board entry. `$ca-conflict` stops, presents
the competing rules and hierarchy, and waits for a person; it produces no fictional command receipt.

## Prepare safely

{{action:U05-prepare-attempt}}

The expected Preview result is refusal and no repository change. The remaining cards are a future
private-source walkthrough only, after a maintainer has supplied a prepared attempt.

## Practice

{{action:U05-run-debug}}

{{action:U05-run-spike}}

{{action:U05-halt-for-conflict}}

## Recognize success

Check accepts repository facts only: a committed findings file with Question, What tried, Answer,
and Implication; a matching deleted `spike/*` branch; and a committed no-action `debug.note` board
entry. It cannot prove that a host command ran or that a person resolved a conflict wisely.

## Check

{{action:U05-check-status}}

## Recover or continue

Keep a failed private attempt intact. Never merge or PR a spike branch, copy spike code to the parent,
or keep a spike branch merely to satisfy Check. If `$ca-conflict` fires, stop work and wait for the
user's resolution before continuing.

### Hint 1

The no-action debug exit is a taskwriter board entry with a dotted `debug.note` ID and a `Desc:` line,
not a free-form bullet or an Academy report.

### Hint 2

The parent receives the committed spike findings file, never the spike branch or its exploratory code.

### Hint 3

A conflict is intentionally not automatable evidence: the safe result is a visible stop until the
person resolves the competing sources.

## Understand the mechanism

The findings transfer is intentionally narrow: commit the finding on `spike/<slug>`, restore only
that file onto the parent, review it, then use `$ca-commit` before deleting the spike branch. This
retains the answer without treating exploratory code as implementation.
