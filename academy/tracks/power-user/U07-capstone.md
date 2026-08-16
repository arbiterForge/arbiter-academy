---
id: U07-capstone
track: power-user
order: 7
title: Complete a bounded feature capstone
outcome: Use the real CodeArbiter feature lane to repair one known defect, preserve its local evidence, and open the resulting feature branch as a hosted pull request.
prerequisites: U06-preview-and-advanced-surfaces
estimated_minutes: 60
scenario_command: {{action:U07-prepare}}
checkpoint_command: {{action:U07-check}}
next_lab: none
---

# U07: Complete a bounded feature capstone

## Know before you begin

U07 is the capstone in the public Academy course. Start at your Academy fork and clone on `main` with
an empty `git status --short`. Keep a native terminal at the clone root and one CodeArbiter harness
opened at the same repository.

This capstone uses the real CodeArbiter feature lane. Its terminal offers a real hosted pull request.
Academy can inspect local Git state, but it cannot authenticate a harness invocation, browser event,
hosted review, CI run, or merge.

## What you will prove

You will repair the prepared behavior: a ticket resolution must reject newline, tab, and DEL control
characters. This bounded two-file change uses the small lane of the real feature workflow, so it leaves its
classification in `.codearbiter/triage.log`, a live focused regression, and executable service
behavior on the prepared branch. It does not manufacture full-lane specification or plan files.

You will also choose **Open a PR** at the real feature terminal and retain its browser URL. That URL is
evidence of the hosted pull request for you and its reviewers. It is not an Academy receipt.

## Prepare safely

{{action:U07-return-to-main}}

{{action:U07-prepare}}

`ATTEMPT_NUMBER` is the number Academy prints, such as `1`. It is not text to type. Do not switch to
another branch before the real feature terminal finishes.

## Practice

{{action:U07-run-feature}}

Read the proposed mini-spec and criteria before you confirm them. Reject a draft that adds unrelated workflow,
dependencies, data migration, or an unrelated public API. If CodeArbiter stops for a real decision,
answer that decision in the harness. Do not imitate the feature lane by creating an Academy-only spec,
plan, review marker, or pull-request record.

When the feature lane reaches its terminal, use the browser action.

{{action:U07-open-pr}}

## Recognize success

The local branch is clean. It contains the small-lane classification in `.codearbiter/triage.log`,
a focused service test that rejects all three control characters, and the narrow service validation
that makes it pass. Your fork's browser shows the feature branch as an open hosted pull request.

Leave that hosted pull request open. Its review and merge are part of the normal feature lifecycle,
not a local Academy simulation.

## Check

{{action:U07-check}}

A passing Check validates the prepared baseline, the local small-lane record, the committed test and
service behavior, safe remotes, and a clean worktree. It does not prove that the feature command ran,
that you approved its spec, that a hosted pull request exists, that CI passed, or that anyone reviewed
or merged it.

## Recover or continue

If Check fails, retain the branch and read the failed predicate. Repair the local boundary it names
through the real feature workflow. Do not amend history to make it resemble a template and do not add
a fake review or PR artifact.

If the branch is beyond repair, use the preserved retry action.

{{action:U07-reset-retry}}

**Hint 1.** Read the prepared test before approving the feature scope. It shows the existing resolution behavior accepts a control character. Add the missing resolution regression through the real feature lane.

**Hint 2.** A clean local branch and a browser-visible pull request are separate facts. Keep evidence for both, but do not turn either into a fabricated receipt.

**Hint 3.** If Check rejects the attempt, repair the named committed path and rerun it. Reset is for a new baseline, not a way to hide a failed branch.

After a pass, continue the actual hosted pull request through its normal review and merge process.
There is no next Academy lab in this course.

## Understand the mechanism

The feature lane owns the conversational gates and its terminal choice. The prepared attempt gives
Academy an immutable baseline. Check compares that baseline with committed files and executes the
focused behavior itself. The browser URL remains deliberately outside that verifier because a local
file cannot prove a hosted event.
