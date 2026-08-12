---
id: P02-commit-review-pr
track: practitioner
order: 2
title: Review, commit, push, and record an offline-local receipt
outcome: Create a reviewed local work range, push it only to the prepared learner origin, and preserve an offline-local receipt in a separate commit.
prerequisites: P01-feature-through-plan
estimated_minutes: 60
scenario_command: arbiter-academy --repository <learner-repository> prepare P02-commit-review-pr
checkpoint_command: arbiter-academy --repository <learner-repository> check P02-commit-review-pr
next_lab: P03-record-an-adr
---

# P02: Review, commit, push, and record an offline-local receipt

## Know before you begin

This is an offline-local pull-request rehearsal. Academy temporarily routes the checkout to two verifier-owned local bare repositories. It does not open GitHub, contact a hosted reviewer, run hosted CI, or prove that a person reviewed the change. The Browser explains the boundary; the native terminal and active CodeArbiter harness perform the lesson work.

{{action:P02-read-boundary}}

## What you will prove

You will leave two learner commits after the prepared commit: one exact Workshop Queue work range, then one separate receipt-only commit. The prepared learner origin receives the work head. The prepared official upstream never receives the attempt branch.

{{action:P02-prepare}}

## Prepare safely

Prepare from outside the checkout, preserve the printed branch, prepared commit, and logical repository IDs, then enter that exact checkout. Do not use an active harness shell command for this setup: it changes the repository and belongs in the native terminal.

{{action:P02-enter-and-guard}}

{{action:P02-inspect-change}}

{{action:P02-stage-work}}

## Practice

You decide whether the local review is cleared. Ask the active agent to inspect the staged two-file boundary and run the CodeArbiter review gate. A cleared learner declaration is evidence you supply; it is not authenticated human approval.

{{action:P02-request-review}}

{{action:P02-run-review}}

{{action:P02-run-work-commit}}

{{action:P02-prove-and-push}}

{{action:P02-record-receipt}}

{{action:P02-stage-receipt}}

{{action:P02-run-receipt-commit}}

## Recognize success

The worktree is clean. The work range is nonempty, origin has its exact work head, upstream has no attempt ref, and the receipt is committed separately. This is local evidence only, not a hosted pull request.

{{action:P02-confirm-clean}}

## Check

Academy Check recomputes the prepared branch, remotes, exact patch, pushed work range, and later receipt-only commit. It cannot prove who reviewed, review quality, command chronology, a hosted pull request, hosted CI, or GitHub remote use.

{{action:P02-check}}

## Recover or continue

If a guard, record, or Check step fails, preserve its output. The Reset action runs `arbiter-academy --repository $learnerRepository reset P02-commit-review-pr` only when the prepared topology still matches; it archives the attempt before restoring original remotes. Do not edit remotes, delete evidence, rebase, force-push, or manufacture a receipt.

{{action:P02-reset}}

### Hint 1

Compare the branch and HEAD printed by Prepare with `git branch --show-current` and `git rev-parse HEAD`. A mismatch means you are not in the prepared attempt.

### Hint 2

Keep the two commits distinct: first the two Workshop Queue paths, then the one receipt path. The helper refuses an uncommitted or ambiguous work range.

### Hint 3

If origin or upstream evidence differs, stop. The local bare routes are verifier-owned exercise state; editing them would erase the condition you need to understand.

## Understand the mechanism

The receipt is a canonical local statement that binds your declared cleared review to Git facts the verifier can recompute. The separate receipt commit keeps the reviewed work range distinct from the declaration about it. Continue to P03 after Reset or after preserving this completed attempt.
