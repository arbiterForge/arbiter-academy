---
id: F03-work-the-board
track: foundations
order: 3
title: Start a task with its work
outcome: Start the prepared docs task and co-locate its in-progress board transition with the bounded documentation correction.
prerequisites: F02-orient-to-state
estimated_minutes: 20
scenario_command: {{action:F03-prepare}}
checkpoint_command: {{action:F03-check}}
next_lab: F04-fix-with-evidence
---

# F03: Start a task with its work

## Know before you begin

Preview 0.26 publishes F03 as a runnable Foundation lesson. Begin from a clean numbered attempt with `academy.docs.0001` queued and
`docs/ticket-list-contract.md` seeded. Keep a native terminal and one active CodeArbiter host at that
same repository. Agent commands do not run in the shell.

## What you will prove

This attempt uses `$ca-task start academy.docs.0001`, then `$ca-chore docs`, to create one
post-Prepare commit. That commit must contain both `.codearbiter/open-tasks.md` and
`docs/ticket-list-contract.md`. The task remains `[~]`; this lesson starts bounded work but does not
mark it done.

The docs chore ends at its normal branch-completion handoff. Choose **Keep the branch as-is (I'll
handle it later)**. This exercise stays local, with no push and no hosted pull request.

## Prepare safely

{{action:F03-prepare}}

{{action:F03-read-target-task}}

Read the task's description, done condition, boundary, lane, and evidence link. Do not substitute a
similarly named task or broaden the correction.

## Practice

{{action:F03-start-task}}

{{action:F03-inspect-started-task}}

The task writer's change stays uncommitted while you do the work it started.

{{action:F03-read-contract}}

{{action:F03-run-docs-chore}}

When the docs chore pauses at its commit gate, inspect the staged state before you approve it.

{{action:F03-review-co-commit-boundary}}

After the commit gate succeeds, use the normal branch-completion handoff.

{{action:F03-choose-keep-branch}}

{{action:F03-confirm-clean}}

## Recognize success

The numbered attempt is clean and has exactly one learner commit after Prepare. Its changed
path set is exactly `.codearbiter/open-tasks.md` plus `docs/ticket-list-contract.md`. The board keeps
the original `academy.docs.0001` task text, changes its marker from `[ ]` to `[~]`, and records the
started date that matches the commit date.

The contract note has one correction: claimed tickets show their claimant, while open tickets show
no claimant. No other content changes. The branch remains local and checked out after **Keep the
branch as-is**. There is no hosted pull request.

## Check

{{action:F03-check}}

A Check can compare the prepared board and document blobs with the one post-Prepare commit. It can
validate the exact task transition, correction, commit parent, commit date, changed paths, and clean
worktree. It cannot prove that `$ca-task` ran, and it cannot prove that `$ca-chore` ran. Those
are agent invocations, not authenticated repository facts.

## Recover or continue

If Check reports a durable-state mismatch, repair only that mismatch and run Check again. Use Reset
from clean main when you need a fresh numbered attempt; it preserves failed evidence rather than
rewriting the retained branch.

**Hint 1.** The target is `academy.docs.0001`, and its only work file is
`docs/ticket-list-contract.md`.

**Hint 2.** The task must remain `[~]`. A done transition belongs to later work, not this co-commit.

**Hint 3.** Review the staged path list before authorizing the docs chore's commit gate. A board-only
commit and a document-only commit both fail the boundary.

{{action:F03-reset-retry}}

## Understand the mechanism

`$ca-task start` records that work began. `$ca-chore docs` performs the bounded non-behavioral change
and carries the dirty board transition through the same governed commit. Co-locating those paths
prevents a board-only commit from claiming progress without work and prevents a document-only commit
from hiding that the task entered progress.

The local Git result is deliberately narrower than the workflow that produced it. Check can
verify the one commit and its bytes, but not either agent invocation, the learner's review, or the
branch-handoff choice. The guide states those limits instead of treating durable state as telemetry.
