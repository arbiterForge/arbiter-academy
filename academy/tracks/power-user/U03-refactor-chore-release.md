---
lesson_id: U03-refactor-chore-release
id: U03-refactor-chore-release
track: power-user
order: 3
title: Refactor, chore, and cut a local release
outcome: Complete a behavior-preserving refactor, a docs-only chore, and a local annotated release without claiming a remote publication.
prerequisites: U02-override-audit-metrics
estimated_minutes: 40
scenario_command: {{action:U03-prepare}}
checkpoint_command: {{action:U03-check}}
next_lab: U04-initialize-projects
---

# U03: Refactor, chore, and local release evidence

This guided lesson prepares a sealed local release exercise in your fork. It creates no remote tag, GitHub Release, or publication claim.

## Know before you begin

Read the boundary before running anything. U03 proves a local refactor, a docs chore, and the local release artifacts that the real CodeArbiter release lane creates.

{{action:U03-read-boundary}}

## What you will prove

The contract is deliberately narrow. Check can observe a sealed refactor of `workshop_queue/store.py`, a later docs-only `README.md` commit, the generated `CHANGELOG.md` release commit, unchanged pre-existing `tests/test_store.py`, a clean worktree, and local annotated `academy-v0.0.1` at the attempt head. Its tag body reproduces the generated 0.0.1 changelog section followed by the matching `Released-at` date.

It does not prove behavioral parity, human approval, CodeArbiter command execution, tag push, or publication.

## Prepare safely

Start from a clean Academy clone root. Prepare creates the sealed branch and brief. Do not make U03 files by hand.

{{action:U03-prepare}}

{{action:U03-confirm-prepared}}

## Practice

The following cards operate on the prepared attempt. The sealed brief supplies the exact approved values. The website remains the teaching surface; commands appear only in their action cards.

{{action:U03-review-sealed-brief}}

{{action:U03-run-refactor}}

{{action:U03-inspect-refactor}}

{{action:U03-review-refactor}}

{{action:U03-stage-refactor}}

{{action:U03-commit-refactor}}

{{action:U03-run-chore}}

{{action:U03-inspect-chore}}

{{action:U03-review-chore}}

{{action:U03-stage-chore}}

{{action:U03-commit-chore}}

{{action:U03-run-release}}

{{action:U03-review-release}}

{{action:U03-inspect-tag}}

## Recognize success

Success is limited to the observed local boundary: three ordered commits (refactor, docs chore, generated changelog), the named paths, an unchanged pre-existing test file, a clean worktree, and an annotated `academy-v0.0.1` tag at the attempt head. The tag body must reproduce the generated changelog section and matching `Released-at` date exactly. It is not a claim about a remote tag, a release page, or published software.

## Check

Academy Check validates this local contract. It does not prove a remote tag, a GitHub Release, or command execution.

{{action:U03-check}}

## Recover or continue

Do not destroy a failed attempt to make it look clean. Preserve the state and use Academy Reset so it archives the attempt before restoring the sealed state.

{{action:U03-reset}}

## Understand the mechanism

The guide and its action manifest are one shared renderer contract. Every command card names who acts and where. Native terminal commands never use `!`. CodeArbiter commands use the selected host directly. Check can compare repository state, but it cannot infer a learner's judgment or an external release event.
