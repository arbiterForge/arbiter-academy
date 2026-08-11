---
id: F03-work-the-board
track: foundations
order: 3
title: Work the governed board
outcome: Move one exact queued Academy task through CodeArbiter start and done transitions, then preserve a one-file evidence commit.
prerequisites: F02-orient-to-state
estimated_minutes: 20
scenario_command: arbiter-academy --repository . prepare F03-work-the-board
checkpoint_command: arbiter-academy --repository . check F03-work-the-board
next_lab: F04-fix-with-evidence
---

# F03 — Work the governed board

## Know before you begin

Complete F01 and F02 first. Begin at the root of the same forked Academy clone, on a clean `main`
branch. Keep a native terminal open for Academy and Git commands, and your Claude Code, Codex, or
Pi harness open for CodeArbiter commands and review requests.

This page labels the execution surface on purpose. Native-terminal commands go directly into
PowerShell or your shell and never start with `!`. Harness shell commands start with one `!`.
CodeArbiter commands are handled by the harness and never start with `!`. You will not use a direct
`git commit` in this lesson.

The task board is repository state, not a to-do list you casually edit. F03 changes the lifecycle
of one prepared training task. It does not implement the feature named on that task.

## What you will prove

You will identify the scope of `academy.feature.0001`, ask CodeArbiter to move it from queued to
started and then done, inspect the exact one-line final diff, and approve one board-only commit
through the CodeArbiter commit gate. External Check accepts the attempt only when all of these are
true. The final task line changes from `[ ]` to `[x]` with a real `(done YYYY-MM-DD)` date, and
every other board line remains unchanged. The numbered attempt has exactly one learner commit after
Prepare, that commit changes only `.codearbiter/open-tasks.md`, and `git status --short` prints
nothing.

The temporary `[~]` started state is something you observe before completion. The final board keeps
the done state, so Check verifies final board evidence rather than pretending it can reconstruct the
exact executable invocation.

## Prepare safely

{{action:F03-prepare}}

Stay on the numbered attempt branch Academy prints until Check passes. If the number is `1`, the
branch is `academy/F03-work-the-board/1`; the word `ATTEMPT_NUMBER` is an explanation, not text you
type.

## Practice

{{action:F03-read-target-task}}

Write down four things before changing state: the target's description, its `Done when` condition,
its `Boundaries`, and its `Evidence` link. They explain why you must not implement the ticket-list
feature, alter a second task, or rewrite the task body during this lab.

{{action:F03-start-task}}

{{action:F03-inspect-started-task}}

The started date is produced by the sanctioned task writer. Seeing `[~]` first matters: the writer
does not treat a queued task as complete just because a checkbox was edited.

{{action:F03-complete-task}}

{{action:F03-inspect-final-diff}}

{{action:F03-stage-board}}

{{action:F03-review-commit-boundary}}

{{action:F03-run-commit-gate}}

{{action:F03-confirm-clean}}

## Recognize success

Before Check, the final board diff contains one changed line: `academy.feature.0001` has its
original task body, but its marker is `[x]` and it ends with one real done date. The feature's
description, `Done when`, `Boundaries`, curriculum lane, and Evidence link remain in place.

Your numbered attempt has one learner commit after Prepare, and that commit contains only
`.codearbiter/open-tasks.md`. There are no uncommitted, staged, or untracked files anywhere in the
worktree. An additional empty commit, an unrelated note committed beside the board, or a dirty file
outside the board is a failed evidence boundary—not a harmless detail.

## Check

{{action:F03-check}}

A pass contains `checkpoint F03-work-the-board: passed; progress: .academy/progress.json`. Check
compares the board at Prepare with the board at the attempt head, confirms the canonical done date
against the board-changing commit date, enforces the one-commit/one-path boundary, and rejects any
dirty worktree state.

## Recover or continue

If Check fails, preserve the attempt and read the failed predicate before retrying. Do not amend,
force-reset, delete, or hide an incorrect route. Reset makes a new numbered attempt from the clean
lesson base while leaving the previous attempt reachable for learning and review.

### Hint 1

The target is `academy.feature.0001`, not the nearby security, release, or deliberately stale
fixture task. Read its body and child lines before you ask the harness to change it.

### Hint 2

The `start` command produces `[~]` with a started date. Inspect that live diff, then use `done`.
Do not turn `[ ]` into `[x]` yourself or skip the start transition.

### Hint 3

The final commit has one path and the entire attempt has one learner commit. If another path,
commit, or dirty file exists, preserve it and use a numbered retry rather than making the history
look simpler than it was.

{{action:F03-reset-retry}}

After a successful Check, return to `main` and leave the completed attempt branch intact.

{{action:F03-return-base}}

Continue to F04
only when it is available as a guided Academy lesson; unpublished reference exercises are not a
substitute for the accepted course.

## Understand the mechanism

The board is the durable record of work state. The task writer owns the legitimate transition and
its dates; it does not create a fictional secondary audit record for this lesson. The learner's job
is to inspect the state, bound the change, approve it, and preserve it through the project’s commit
gate.

Check is deliberately stricter than “the line looks done.” It ties the final state to the prepared
baseline, requires exactly one post-Prepare learner commit containing only the board, and requires
a clean worktree. That produces evidence another person can inspect without trusting a chat
transcript or guessing what happened between commands.
