---
id: U05-debug-spike-conflict
track: power-user
order: 5
title: Debug, spike, and conflict without inventing evidence
outcome: Preserve a real debug no-action close and a findings-only spike transfer, while stopping for a human conflict decision.
prerequisites: U04-initialize-projects
estimated_minutes: 45
scenario_command: {{action:U05-prepare-attempt}}
checkpoint_command: {{action:U05-check-status}}
next_lab: U06-preview-and-advanced-surfaces
---

# U05: Debug, spike, and conflict without inventing evidence

## Know before you begin

U05 remains private source material in Preview 0.17. The website is the primary learning surface,
but the installed Preview refuses U05 Prepare and Check. Do not make an Academy-only branch, report,
or command to bypass that boundary.

{{action:U05-confirm-private-boundary}}

## What you will prove

The future private walkthrough uses one matching released integration: CodeArbiter 2.15.1 (Claude); ca-codex 0.7.1 (Codex); or ca-pi 0.8.1 (Pi). Each carries the
[findings-only spike contract](https://github.com/arbiterForge/codeArbiter/pull/687):
`$ca-spike` creates `spike/<slug>`, transfers only the committed findings file back to its parent,
and deletes the spike branch. `$ca-debug` makes no code change and may create a real taskwriter
`debug.note` board entry. `$ca-conflict` halts, presents competing rules and their hierarchy, and
waits for a person; it has no fictional command receipt.

## Prepare safely

{{action:U05-prepare-attempt}}

Preview stops here. It creates no U05 attempt and writes no evidence. Use a published lab unless a
maintainer has supplied the future private-source attempt described below.

## Practice

The remaining cards describe the accepted source-level lifecycle but are not executable through the
Preview 0.17 binary. They are deliberately separated from the refusal above so a learner cannot
mistake them for current Preview actions.

{{action:U05-read-observation}}

### Debug: preserve the no-action close

{{action:U05-run-debug}}

{{action:U05-review-debug-board}}

{{action:U05-commit-debug-board}}

The first parent commit contains only `.codearbiter/open-tasks.md`. Check verifies the resulting
taskwriter shape and clean tree, not a claimed command invocation.

### Spike: transfer only the answer

{{action:U05-run-spike}}

{{action:U05-confirm-spike-question}}

{{action:U05-transfer-findings}}

{{action:U05-review-findings}}

{{action:U05-commit-findings}}

{{action:U05-delete-spike}}

The native `git branch -D` is intentional: the findings-only restore leaves the disposable spike
commit unmerged. Do not merge merely to make ordinary `git branch -d` succeed. The parent receives
the findings file's contents, never the spike commit or exploratory code.

### Conflict: stop for a person

{{action:U05-halt-for-conflict}}

## Recognize success

The private Check predicate accepts repository facts only: the exact prepared observation; a first
parent commit containing the taskwriter-shaped no-action board entry; a second parent commit with
only `.codearbiter/spikes/u05-cache-key.md`; and no `spike/u05-cache-key` ref. It rejects copied
or uncommitted exploratory code. It cannot prove that a host command ran or that a person resolved
a conflict wisely.

## Check

{{action:U05-check-status}}

## Recover or continue

Preserve a failed private attempt. Never merge or open a pull request for a spike branch, copy spike
code to the parent, or keep a spike branch merely to satisfy Check. If `$ca-conflict` fires, stop
work and wait for the user's resolution before continuing.

### Hint 1

Read the prepared observation before debugging. It is an input to investigate, not a transcript that
you can edit into evidence.

### Hint 2

The parent board commit and parent findings commit are intentionally separate. Check rejects a
single commit that combines them.

### Hint 3

`git branch -D` is correct only after the parent has committed the restored findings file. It deletes
the intentionally unmerged disposable branch; it does not merge it.

## Understand the mechanism

The scenario prepares a fictional cache-key observation, not a fake tool transcript. The only
durable plugin-facing artifacts are the board entry produced by the debug no-action exit and the
four-section findings file. Their two parent commits make the handoff reviewable without claiming
that Academy can observe an agent's internal reasoning.
