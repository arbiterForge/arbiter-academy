---
id: P05-checkpoint-remediation
track: practitioner
order: 5
title: Remediate a checkpoint finding
outcome: Reproduce a genuine blocked-ticket summary defect and prove it with ordered test-only RED and code-only GREEN commits.
prerequisites: P04-review-a-dependency
estimated_minutes: 45
scenario_command: arbiter-academy --repository <learner-repository> prepare P05-checkpoint-remediation
checkpoint_command: arbiter-academy --repository <learner-repository> check P05-checkpoint-remediation
next_lab: P06-context-drift-recovery
---

# P05 - Remediate a checkpoint finding

## Know before you begin

This is private authoring material. It is unavailable in Preview 0.10. Its action cards document an unreleased lesson and do not create a public course route.

P05 is the first Practitioner exercise that asks you to preserve a precise remediation history. It
uses the Workshop Queue practice project that Academy prepares in your learner clone; it does not
ask you to experiment in your own production repository. Complete P04 first. If you need to learn
how to make a GitHub fork, clone it locally, install Academy, or distinguish your terminal from
your harness, use the prerequisite action below and return after F01.

Keep two places open: a native terminal at the learner clone for Academy and Git commands, and one
CodeArbiter harness at the same clone for agent and CodeArbiter actions. A native-terminal command
is entered directly and never starts with `!`. A shell command sent through a harness starts with
exactly one `!`; this lesson does not ask you to type one. CodeArbiter commands and agent messages
belong in the harness and never begin with `!`.

{{action:P05-prerequisite}}

## What you will prove

The prepared exercise can persist a terminal `blocked` ticket through its normal model and store,
but its JSON report wrongly excludes that ticket from the `unresolved` count. You will preserve four
linear commits after Academy Prepare:

1. an exact finding-only report;
2. a test-only RED regression that exposes the defect;
3. a code-only GREEN repair that leaves the regression unchanged; and
4. a canonical receipt that names the first three real commit IDs.

The repair is deliberately small: unresolved means every ticket that is not completed. P05 Check
can reconstruct the fixture, commits, path roles, regression, repair, receipt, and clean worktree.
It cannot prove who reviewed a result, whether a checkpoint command was run, or the chronology of
commands that led to the final commits.

## Prepare safely

{{action:P05-prepare}}

`ATTEMPT_NUMBER` is a value Academy prints, such as `1`; it is not text to type literally. Stay on
that numbered branch. The prepared commit also adds ADR-0005 and its decision-log entry. Do not edit
those decision records, and do not repair the deliberately stale `CONTEXT.md` reference: that is
the starting condition for P06.

{{action:P05-guard-attempt}}

{{action:P05-read-prepared-boundary}}

## Practice

{{action:P05-surface-finding}}

{{action:P05-inspect-finding}}

{{action:P05-record-finding}}

{{action:P05-verify-finding-commit}}

{{action:P05-add-red-regression}}

{{action:P05-observe-red}}

{{action:P05-commit-red}}

{{action:P05-apply-green-repair}}

{{action:P05-commit-green}}

{{action:P05-record-receipt}}

{{action:P05-commit-receipt}}

Do not add a fifth evidence commit. Do not amend, rebase, force-reset, or use copied terminal output
as a substitute for the required repository evidence. The point is not a plausible story about a
repair; it is a reviewable history that makes the defect, regression, repair, and final receipt
separable.

## Recognize success

The completed attempt has exactly four descendant commits after Prepare and no pending worktree
changes. The first changes only `.codearbiter/reports/academy/P05-finding.md`; the second changes
only `tests/test_cli.py`; the third changes only `workshop_queue/cli.py`; and the fourth changes
only `.codearbiter/checkpoints/P05-academy.json`.

The finding says that blocked `RQ-105` is omitted from the unresolved summary. The RED action gives
the agent the verifier's exact taught method; an equivalent replacement is not accepted. That test
persists the fixture, reaches the real report, and fails because `unresolved` is wrong, not because
the setup broke. The GREEN repair changes the unresolved predicate to every ticket that is not
completed. Run the native-terminal action to generate the receipt last; its deterministic generator
writes sorted keys, compact separators, ASCII escaping, and exactly one LF. The receipt contains
`schema_version`, `finding_id`, `finding_commit`, `red_commit`, `remediation_commit`, and `status`.
`affected_paths` is exactly, in order, `tests/test_cli.py` then `workshop_queue/cli.py`. A copied host command is guidance, not evidence that either command was invoked.

{{action:P05-confirm-clean}}

## Check

{{action:P05-check}}

A pass contains `checkpoint P05-checkpoint-remediation: passed` and records progress in
`.academy/progress.json`. Check independently verifies the prepared ADR, decision log, blocked
ticket lifecycle, staged defect, exact four-commit topology, path roles, RED regression, GREEN
repair, canonical receipt, and clean worktree. Check does not authenticate a checkpoint run or a
human review, and it does not prove command chronology. Treat the commands and inspection steps as
the practice you observe, not as claims that a final-state verifier can honestly make.

## Recover or continue

If the branch identity, finding boundary, RED result, code-only GREEN boundary, receipt shape, or
Check result is wrong, preserve the attempt. Read the named failure and create a fresh numbered
attempt rather than trying to make past commits look correct. A preserved failed attempt is useful
evidence; a rewritten one teaches the wrong habit.

{{action:P05-reset-retry}}

### Hint 1

When a path boundary is unclear, read the latest commit's path list before doing more work. The
finding is one report path; RED is one test path; GREEN is one production path; and the receipt is
one checkpoint path.

### Hint 2

The prepared defect is already in `workshop_queue/cli.py`. The RED test must create the blocked
ticket through the existing CLI boundary and show that `blocked` is `1` while `unresolved` is wrong.
Do not create a second fixture or a second production change to make that assertion easier.

### Hint 3

The receipt is not a progress note. It is the last commit and its three IDs must be the real finding,
RED, and GREEN descendants in that order. If you cannot name those four one-path commits, use Reset
rather than trying to repair the history.

Continue to **P06 — Recover context drift without losing unrelated work** after P05 passes. Leave
the completed P05 branch intact: P06 is a separate recovery case, not a repair to fold into this
remediation attempt.

## Understand the mechanism

Checkpoint remediation is a chain of independently inspectable facts. The prepared fixture creates
a real domain state; the finding narrows the observed defect; a direct test records the caller
expectation before code changes; the production change is isolated; and the receipt binds those
commits into one checkable statement. This makes a later reviewer able to distinguish a real
remediation from an invented report, a generic event, a broad patch, or a history assembled after
the fact.
