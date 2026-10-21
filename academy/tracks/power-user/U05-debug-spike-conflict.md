---
id: U05-debug-spike-conflict
track: power-user
order: 5
title: Investigate before changing code
outcome: Reach a read-only debug conclusion, then preserve only a disposable spike answer.
prerequisites: U04-initialize-projects
estimated_minutes: 45
scenario_command: {{action:U05-prepare-attempt}}
checkpoint_command: {{action:U05-check-status}}
next_lab: U06-preview-and-advanced-surfaces
---

# U05: Investigate before changing code

## Know before you begin

Use debug when the cause is unknown. Use a spike for a short experiment that answers
one design or implementation question. Investigation does not silently authorize
a production change.

{{action:U05-confirm-readiness}}

## What you will prove

Investigate the fictional cache-key observation. A current no-action debug exit
returns a cited explanation and leaves the board and source unchanged.

Then bring only the spike's findings file back to the Academy branch in one commit.
Confirm deletion of the disposable spike only after preserving its answer.

## Prepare safely

{{action:U05-prepare-attempt}}

{{action:U05-read-observation}}

The prepared observation is input to investigate, not a transcript or a conclusion
you may rewrite to make the lesson pass.

## Practice

{{action:U05-run-debug}}

{{action:U05-review-debug-board}}

Read the cited evidence. A no-action conclusion needs a positive reason; an unsuccessful
attempt to reproduce a reported problem is not enough.

{{action:U05-run-spike}}

{{action:U05-confirm-spike-question}}

{{action:U05-transfer-findings}}

{{action:U05-review-findings}}

{{action:U05-commit-findings}}

{{action:U05-delete-spike}}

The findings-only transfer does not merge the spike. The deletion uses git branch -D
because that exploratory commit remains unmerged. Confirm the exact branch and the
preserved answer before running it.

{{action:U05-halt-for-conflict}}

Use conflict when actual sources disagree. Do not invent a conflict or a resolution
receipt to finish the exercise.

## Recognize success

The task board matches Prepare. One new parent commit contains only
.codearbiter/spikes/u05-cache-key.md, with Question, What tried, Answer, and Implication
sections. The disposable spike ref is absent and the worktree is clean.

## Check

{{action:U05-check-status}}

Check observes the prepared input, preserved board, findings, commit boundary, and
missing spike ref. It cannot prove debug invocation, reasoning quality, or deletion
approval.

## Recover or continue

{{action:U05-reset-retry}}

**Hint 1.** A debug conclusion does not create a task by default.

**Hint 2.** Transfer the findings file, never exploratory code or the spike commit.

**Hint 3.** If rules conflict, preserve the state and wait for the actual user's
resolution. A passing Check is not that decision.

## Understand the mechanism

Investigation reduces uncertainty. A spike leaves an answer that guides later
production work through its proper feature or fix workflow.

**Use this in your own project.** Give debug the observed behavior, expected behavior,
and available evidence. Give a spike one question and a stopping condition. Take a
confirmed bug's reproduction and regression idea into the fix lane.
