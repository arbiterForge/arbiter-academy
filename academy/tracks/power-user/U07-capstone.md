---
id: U07-capstone
track: power-user
order: 7
title: Deliver a tested fix for review
outcome: Repair a known resolution-label defect and open a real pull request inside your fork.
prerequisites: U06-preview-and-advanced-surfaces
estimated_minutes: 60
scenario_command: {{action:U07-prepare}}
checkpoint_command: {{action:U07-check}}
next_lab: none
---

# U07: Deliver a tested fix for review

## Know before you begin

This capstone combines scope, regression testing, review, and a real pull request.
Complete U06 first. Start from clean main in your fork, with the terminal and harness
at that same clone.

The prepared defect accepts control characters in ticket resolutions. Use the fix
lane for this known bug. It does not need a feature mini-spec or a small-lane record.

## What you will prove

Reject newline, tab, and DEL while preserving ordinary resolution text. Observe
the focused regression fail, make the minimal repair, then run affected service checks.
Commit the passing test with its repair.

Open a real PR in your personal fork and retain its browser URL. The local Academy
Check and the hosted pull request establish different facts.

## Prepare safely

{{action:U07-return-to-main}}

{{action:U07-prepare}}

Stay on the numbered branch. Read the existing resolution behavior. Do not add a
made-up review, approval, feature classification, or PR record.

## Practice

{{action:U07-run-fix}}

The test must reach `complete_ticket` and the service must still accept ordinary text.
Read the failure and final diff. Reject unrelated dependency, storage, or API changes.

{{action:U07-open-pr}}

Inspect the actual base repository and branch before creating the PR. A safe origin
push does not guarantee that a hosting tool selected your fork as the PR base.
Keep the exercise PR inside your fork and leave merge for a separate decision.

## Recognize success

The branch is clean, the focused regression and narrow service repair are committed,
and the affected checks passed. Your fork shows the correct open pull request.

Explain what the test protects and which checks ran. An open PR, local Check,
passing CI, review approval, merge, and release are separate states.

## Check

{{action:U07-check}}

Check validates the prepared baseline, bounded committed source, executable service
behavior, safe remotes, and clean worktree. It cannot prove earlier RED chronology,
a host invocation, a human approval, hosted CI, review, or merge.

## Recover or continue

{{action:U07-reset-retry}}

**Hint 1.** Reproduce the defect before editing the service. A final passing test
alone does not show that it caught the bug.

**Hint 2.** Inspect the actual PR in the browser. A local URL field proves no hosted event.

**Hint 3.** Preserve a failed attempt. Correct real defects through the fix lane;
use Reset when the attempt needs a fresh baseline.

## Understand the mechanism

You have taken a concrete problem from reproduction to reviewable delivery.

**Build something of your own.** Choose a useful feature, such as filtering a reading
list or exporting a small inventory. State who uses it, one visible success case,
one failure case, and what is out of scope. Ask codeArbiter to build it through the
feature lane. Request a review pause where it helps you; let ordinary in-scope work
continue under the original request. Use the Home page's own-project guide for setup.
