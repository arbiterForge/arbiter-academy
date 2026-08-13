---
id: U07-capstone
track: power-user
order: 7
title: Complete a bounded local capstone
outcome: Complete a small governed change in a forked Workshop Queue repository using real CodeArbiter artifacts, without pretending a local record proves a hosted pull request.
prerequisites: U06-preview-and-advanced-surfaces
estimated_minutes: 60
scenario_command: {{action:U07-prepare-refusal}}
checkpoint_command: {{action:U07-check-refusal}}
next_lab: none
---

# U07: Complete a bounded local capstone

## Know before you begin

### Current Preview boundary

U07 is private source material, not a runnable Preview 0.16 lesson. The website remains the
primary teaching surface. Current Preview deliberately refuses Prepare and Check for U07; it does
not create an attempt, evidence, report, route, or capstone branch.

{{action:U07-read-private-boundary}}

## What you will prove

The future capstone proves a bounded local history: one feature-derived spec and plan, a
learner-attributed ADR, a test-first implementation, fork-safe remotes, and a clean worktree. It
does not prove an agent command, a hosted pull request, a review, a merge, or CI.

## Prepare safely

{{action:U07-prepare-refusal}}

Stop here when using Preview 0.16. Continue with a published lab. The rest of this page is a
future private-source walkthrough describing the real CodeArbiter workflow that a later accepted
fixture will teach.

## Practice

### Future private-source walkthrough

The capstone is one local Workshop Queue change: reject control characters in a ticket resolution.
It has a narrow implementation boundary: `tests/test_service.py` first, then
`workshop_queue/service.py`. It must preserve the normal fork-safe remote configuration and a
clean worktree. Its real feature lane ends by opening a hosted pull request, but Academy Check does
not attempt to prove that hosted result, review, merge, CI result, or command invocation.

{{action:U07-read-capstone-brief}}

### Create the actual feature record

{{action:U07-run-governed-feature}}

The feature lane derives the specification and plan filenames from the feature, so do not invent
fixed `capstone.md` names. Keep its generated spec and plan together with one numbered ADR in the
first local commit. The learner decides the validation boundary; the agent records it with the
learner's attribution.

{{action:U07-record-architecture-decision}}

### Use test-first commits

Make the focused regression a commit before the implementation commit. The regression must reject
newline, tab, and DEL control characters in a resolution; the implementation rejects those inputs
at the service boundary. Do not add cleanup, unrelated behavior, or a shortcut that makes the test
vacuous.

### Review without faking a receipt

{{action:U07-run-local-review}}

`$ca-review` is read-only. Its triaged verdict is useful while you are working, but it creates no
review file and Academy Check cannot prove that it ran. Resolve any blocking finding in the normal
feature workflow; never create a review receipt to claim that review happened.

## Recognize success

A future U07 Check accepts exactly three linear learner commits after preparation:

1. One feature-derived spec, matching feature-derived plan, and one numbered ADR.
2. The focused regression in `tests/test_service.py`.
3. The matching implementation in `workshop_queue/service.py`.

It reruns the focused control-character behavior, verifies no secret-like learner blob in the
implementation, confirms fork-safe remotes, and requires a clean worktree. It rejects extra changed
paths, a skipped regression, a nonfunctional source-shaped fix, fabricated receipts, or an
uncommitted change. It does not authenticate the later audit or hosted PR.

## Check

{{action:U07-check-refusal}}

Until U07 is published, this refusal is the only expected Check result. Preserve a failed future
attempt; do not amend, rebase, force-push, delete evidence, or edit a record to make it look
accepted.

## Recover or continue

If any future step produces an extra changed path, a fabricated receipt, a dirty worktree, or an
unsafe remote, preserve the attempt for diagnosis and Reset it when that lifecycle is published.
Do not hide the mismatch by rewriting commits or copying an artifact from another lab. Until then,
continue with a published Preview 0.16 lab.

### Hint 1

The feature and plan filenames are derived by the real feature lane. Check matches their shared
slug instead of requiring an Academy-invented filename.

### Hint 2

`$ca-review` is deliberately not evidence. Its verdict guides the next action, while Check looks
only at the committed history and focused regression.

### Hint 3

The capstone does not add an audit receipt. Never replace a real command workflow with Academy JSON
that claims a scan, reviewer list, or remote pull request.

## Understand the mechanism

Academy can inspect durable Git state and rerun the focused regression. It cannot authenticate an
agent invocation, a human review, or a hosted event. U07 therefore teaches those real CodeArbiter
commands for their actual purpose while its future Check accepts only their honest observable
repository effects.
