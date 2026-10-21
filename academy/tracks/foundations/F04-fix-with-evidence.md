---
id: F04-fix-with-evidence
track: foundations
order: 4
title: Fix a bug with a regression test
outcome: Observe RED, repair the claimant boundary, and commit the passing test with its minimal fix.
prerequisites: F02-orient-to-state
estimated_minutes: 30
scenario_command: python scripts/academy.py prepare F04-fix-with-evidence
checkpoint_command: arbiter-academy --repository <learner-repository> check F04-fix-with-evidence
next_lab: P01-feature-through-plan
---

# F04: Fix a bug with a regression test

## Know before you begin

A bug fix should explain what failed and leave a test that catches it next time.
Here you stop a ticket claimant from putting a newline, tab, or DEL character into
a display name, while keeping an ordinary name such as Sam Allen valid.

Complete F02 first. F03 offers practice with task and commit boundaries. Start from clean main in your Academy clone. Keep your native
terminal and selected codeArbiter harness at the same clone. Run Academy and shell
commands in the terminal. Send agent requests in the harness. The cards label both.

## What you will prove

Run the new regression before editing production code. RED means it fails because
the service accepts an invalid name. GREEN means the same test passes after the fix.
An import error is a setup problem, not RED evidence.

Commit only after the focused test and service suite pass. One final commit contains
`tests/test_service.py` and `workshop_queue/service.py`. The current commit gate does
not permit a failing-test commit.

## Prepare safely

{{action:F04-prepare}}

{{action:F04-inspect-defect}}

{{action:F04-confirm-baseline}}

Stay on the numbered branch printed by Prepare; do not edit main.

## Practice

Request a pause at RED so you can inspect the failure yourself.

{{action:F04-start-fix}}

{{action:F04-request-regression}}

{{action:F04-run-red-regression}}

{{action:F04-inspect-test-boundary}}

The assertion should reach the real `claim_ticket` function and fail because
ValueError was not raised. Explain why the ordinary-name assertion matters:
rejecting every name would also be a bug.

{{action:F04-request-repair}}

{{action:F04-prove-repair}}

{{action:F04-inspect-repair-boundary}}

{{action:F04-stage-repair}}

{{action:F04-review-repair-boundary}}

{{action:F04-commit-repair}}

{{action:F04-inspect-history}}

## Recognize success

One green learner commit follows Prepare and contains only the test and service repair.
The regression rejects all three control characters and accepts Sam Allen.
The short Git status prints nothing. Keep the observed RED and GREEN results in
your session: the final commit cannot prove when a test ran.

## Check

{{action:F04-check}}

Check compares the prepared source, retained regression, reachable repair, and clean
worktree. It does not execute learner-authored code or authenticate test chronology.
Your actual test runs establish the behavior you observed.

## Recover or continue

Preserve a failed attempt and read the named failure before changing anything.

**Hint 1.** Test `claim_ticket`, not a helper that production never calls.

**Hint 2.** Keep the regression unchanged during repair. Never weaken an assertion
to get GREEN.

**Hint 3.** Keep unrelated paths out of the commit. Use Reset when the history needs
a fresh numbered attempt.

{{action:F04-reset-retry}}

{{action:F04-return-base}}

After a passing Check, continue to P01.

## Understand the mechanism

Running a regression before a fix shows it detects the defect. Running it afterward
checks the repair. A green commit retains both the protection and implementation.

**Use this in your own project.** Describe the input, actual result, and expected result
in a fix request. Ask for a regression at the caller boundary. You need not pause
after each step outside this exercise unless you want to inspect it.
