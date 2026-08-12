---
id: F03-work-the-board
track: foundations
order: 3
title: Work the governed board
outcome: Move the exact queued Academy task through the sanctioned start and done transitions.
prerequisites: F02-orient-to-state
estimated_minutes: 15
scenario_command: {{action:F03-prepare}}
checkpoint_command: {{action:F03-check}}
next_lab: F04-fix-with-evidence
---

# F03: Work the governed board

## Know before you begin

Complete F02 first. Open a native terminal and your active CodeArbiter harness at the prepared
arbiter-academy clone. Start on a clean `main` branch. Native-terminal commands have no `!`.
CodeArbiter commands are not shell commands and never begin with `!`.

F03 changes only the `academy.feature.0001` lifecycle in `.codearbiter/open-tasks.md`. It does not
implement the feature named by that task, change another task, or create a general board cleanup.

## What you will prove

You will move one queued task through its sanctioned started and done states, then create one
board-only governed commit. The completed attempt remains available if Check fails, so do not amend,
force-push, force-reset, or delete it.

## Prepare safely

{{action:F03-prepare}}

{{action:F03-read-target-task}}

`ATTEMPT_NUMBER` means the number Academy prints. Do not type the word or angle brackets literally.

## Practice

{{action:F03-start-task}}

{{action:F03-inspect-started-task}}

{{action:F03-complete-task}}

{{action:F03-inspect-final-diff}}

{{action:F03-stage-board}}

{{action:F03-review-commit-boundary}}

{{action:F03-run-commit-gate}}

{{action:F03-confirm-clean}}

## Recognize success

The attempt has one post-Prepare learner commit, and that commit changes only
`.codearbiter/open-tasks.md`. The target's full original task text remains present, its marker is
`[x]`, and the task writer supplied its done date. Every other board line is byte-for-byte unchanged.
No non-ignored worktree state remains. Academy ignores the sole task-writer sidecar exception,
`.codearbiter/open-tasks.md.lock`.

## Check

{{action:F03-check}}

Check compares the prepared board blob, committed board blob, one board-only commit boundary, and
non-ignored worktree state. It cannot prove the agent command ran or prove that the learner observed
the transient `[~]` state. A hand-edited checkbox, malformed date, unrelated board edit, extra commit,
or non-ignored worktree change fails.

## Recover or continue

Preserve the failed attempt and read the failed predicate before choosing a retry.

**Hint 1.** Confirm that `academy.feature.0001`, not a similarly named task, was queued before Start.

**Hint 2.** Inspect the `[~]` state before Done. It is a required transition, not a decoration.

**Hint 3.** Review the staged path list before the commit gate. Only `.codearbiter/open-tasks.md`
belongs in the commit.

{{action:F03-reset-retry}}

{{action:F03-return-base}}

After a passing Check, return to `main`. The next Academy lesson appears on the course home only after its guided rewrite. Keep every completed or failed attempt branch intact for later verification.

## Understand the mechanism

The task writer owns the observable start and done transitions. Check can compare durable board bytes,
the commit boundary, and non-ignored worktree state, but it cannot prove the agent command ran or that
the learner observed the transient `[~]` state. Those limits keep the exercise honest while the
preserved attempt supplies reviewable evidence.
