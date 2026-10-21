---
id: P05-checkpoint-remediation
track: practitioner
order: 5
title: Turn a review finding into a tested repair
outcome: Reproduce a blocked-ticket summary defect, commit a green repair, and bind the finding to the result.
prerequisites: P04-review-a-dependency
estimated_minutes: 45
scenario_command: arbiter-academy --repository <learner-repository> prepare P05-checkpoint-remediation
checkpoint_command: arbiter-academy --repository <learner-repository> check P05-checkpoint-remediation
next_lab: P06-context-drift-recovery
---

# P05: Turn a review finding into a tested repair

## Know before you begin

A review finding becomes useful when you can reproduce it, fix it, and show what
changed. Workshop Queue can store a blocked ticket, but its summary omits that
ticket from the unresolved count. Follow that finding through a regression and repair.

Complete P04 and start from clean main in the same clone. Use your native terminal
for Academy and Git, and the selected harness for agent requests.

{{action:P05-prerequisite}}

## What you will prove

Preserve three commits after Prepare: the checkpoint report and finding; the passing
test and minimal repair together; then a schema-3 receipt naming the finding and repair
commits. Observe RED before production changes and GREEN afterward. Do not commit a
failing regression or claim that a receipt authenticates command chronology.

## Prepare safely

{{action:P05-prepare}}

{{action:P05-guard-attempt}}

{{action:P05-read-prepared-boundary}}

Prepare supplies the fictional ADR-0005 and its log entry for blocked-ticket behavior.
Preserve them. P06 practices a separate source-backed context refresh.

## Practice

{{action:P05-surface-finding}}

{{action:P05-inspect-finding}}

{{action:P05-record-finding}}

{{action:P05-verify-finding-commit}}

Explain the defect before requesting code: RQ-105 is blocked, so it is unresolved,
but the current expression counts only open and claimed tickets.

{{action:P05-add-red-regression}}

{{action:P05-observe-red}}

Keep the test uncommitted. Successful claim, block, and report commands followed by
the wrong unresolved count are the meaningful RED result.

{{action:P05-apply-green-repair}}

{{action:P05-commit-green}}

{{action:P05-record-receipt}}

{{action:P05-commit-receipt}}

## Recognize success

The first commit contains the generated dated checkpoint report,
.codearbiter/last-checkpoint, and .codearbiter/reports/academy/P05-finding.md.
The second contains `tests/test_cli.py` and `workshop_queue/cli.py`.
The third contains only .codearbiter/checkpoints/P05-academy.json.

The unchanged regression reaches the real CLI. The repair counts every ticket that
is not completed. The schema-3 receipt names `finding_commit` and `remediation_commit`;
it has no `red_commit` field.

{{action:P05-confirm-clean}}

## Check

{{action:P05-check}}

Check validates the prepared fixture, finding, source changes, three-commit history,
receipt, and clean worktree. It cannot authenticate a checkpoint invocation, a human
review, or RED/GREEN chronology. Keep those actual observations separate.

## Recover or continue

{{action:P05-reset-retry}}

**Hint 1.** Inspect each commit's paths. Keep finding, repair, and receipt separate.

**Hint 2.** A setup error is not evidence of the summary bug. Confirm the CLI commands
succeeded before reading the count assertion.

**Hint 3.** Generate the receipt last. Never guess an ID or invent a RED commit.

Leave the completed attempt intact and return to clean main before P06.

## Understand the mechanism

A checkpoint can surface many findings. Take one through a complete repair and
keep adjacent cleanup separate. The receipt connects a diagnosis to its result;
it does not replace tests.

**Use this in your own project.** Ask for the impact and reproduction of a finding,
repair the affected behavior, and report what remains open.
