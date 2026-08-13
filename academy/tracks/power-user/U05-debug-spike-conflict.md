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

This lesson uses the released CodeArbiter contract. The website gives the sequence and your host runs the real commands. Academy can inspect repository facts at the end, but it cannot prove an agent’s private reasoning or a human conflict decision.

{{action:U05-confirm-readiness}}

## What you will prove

You will preserve two real outputs. The debug no-action exit records its cited conclusion through
taskwrite. The spike preserves only its four-part findings file on the parent branch, then deletes
the exploratory branch. Neither output proves a command transcript or invents a conflict receipt.

## Prepare safely

{{action:U05-prepare-attempt}}

{{action:U05-read-observation}}

## Practice

Keep the parent attempt clean between the two commits. The commands below state which surface owns each action and what evidence must remain afterward.

## Debug: preserve the no-action close

{{action:U05-run-debug}}

{{action:U05-review-debug-board}}

{{action:U05-commit-debug-board}}

The first parent commit contains only `.codearbiter/open-tasks.md`. Check verifies the resulting taskwrite shape and clean tree, not a claimed command invocation.

## Spike: transfer only the answer

{{action:U05-run-spike}}

{{action:U05-confirm-spike-question}}

{{action:U05-transfer-findings}}

{{action:U05-review-findings}}

{{action:U05-commit-findings}}

{{action:U05-delete-spike}}

The native `git branch -D` is intentional. The findings-only restore leaves the disposable spike commit unmerged. Do not merge merely to make ordinary branch deletion succeed. The parent receives the findings file’s contents, never the spike commit or exploratory code.

## Conflict: stop for a person

{{action:U05-halt-for-conflict}}

## Recognize success

Check accepts repository facts only: the exact prepared observation; a first parent commit containing the taskwrite-shaped no-action board entry; a second parent commit with only `.codearbiter/spikes/u05-cache-key.md`; and no `spike/u05-cache-key` ref. It rejects copied or uncommitted exploratory code. It cannot prove that a host command ran or that a person resolved a conflict wisely.

## Check

{{action:U05-check-status}}

## Recover or continue

{{action:U05-reset-retry}}

Never merge or open a pull request for a spike branch, copy spike code to the parent, or keep a spike branch merely to satisfy Check. If `$ca-conflict` fires, stop work and wait for the user’s resolution before continuing.

### Hint 1

Read the prepared observation before debugging. It is an input to investigate, not a transcript that you can edit into evidence.

### Hint 2

The parent board commit and parent findings commit are intentionally separate. Check rejects a single commit that combines them.

### Hint 3

`git branch -D` is correct only after the parent has committed the restored findings file. It deletes the intentionally unmerged disposable branch; it does not merge it.

## Understand the mechanism

Prepare commits the fictional observation so every learner begins from the same bounded question.
The host owns debug and spike behavior. Academy Check reads only the resulting Git range, task board,
findings file, deleted U05 spike ref, and clean worktree. That is why a copied exploratory change,
retained branch, invented receipt, or merged spike cannot pass.
