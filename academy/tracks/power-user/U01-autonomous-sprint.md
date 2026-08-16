---
id: U01-autonomous-sprint
track: power-user
order: 1
title: Govern an autonomous sprint without outsourcing approval
outcome: Complete a bounded documentation sprint, preserve its durable decision evidence, and distinguish a human approval gate from the repository facts that Check can verify.
prerequisites: P08-repository-hygiene
estimated_minutes: 35
scenario_command: {{action:U01-prepare-attempt}}
checkpoint_command: {{action:U01-check-status}}
next_lab: U02-override-audit-metrics
---

# U01: Govern an autonomous sprint without outsourcing approval

## Know before you begin

U01 is a guided, runnable lesson in Preview 0.30. The website remains the primary lesson surface.
Academy CLI prepares the reviewed attempt, checks its local evidence boundary, and creates a
non-destructive numbered retry when recovery is needed.

Complete P08 first. In your personal fork, keep the repository root open in a native terminal and
the selected CodeArbiter harness. A command typed directly in a native terminal
has no `!`. A shell command passed through a harness begins with exactly one `!`. A host-native
CodeArbiter command belongs to the harness and has no `!`. The action cards label each case.

{{action:U01-confirm-fork-boundary}}

## What you will prove

On a prepared U01 attempt, you will prove that a sprint did not self-authorize its work. The learner
reads the proposed specification, decides whether its scope is acceptable, then reads and explicitly approves the derived plan before autonomy can begin. The completed attempt preserves the derived specification, plan, append-only sprint log, and one bounded operator guide.

This is a documentation-only sprint. Its allowed final commit contains four paths: the spec, plan,
sprint log, and `docs/academy-sprint-summary.md`. The real sprint lane then pushes only the learner
fork branch and opens a pull request. It never pushes directly to upstream or merges. It does not
change product code, tests, dependencies, or remotes.

## Prepare safely

{{action:U01-prepare-attempt}}

Prepare must run in the forked checkout that passed P08's remote safety work. It creates the numbered
attempt from reviewed fixture bytes; do not recreate that branch or scenario manually.

{{action:U01-inspect-scenario}}

The scenario is installed by the reviewed Academy fixture. Its named deliverable and approval-required
starting condition explain the exact boundary the prepared attempt now contains.

## Practice

The next actions run only on the numbered attempt that Prepare just created. They do not authorize
an autonomous sprint on an ordinary checkout.

{{action:U01-run-sprint}}

{{action:U01-approve-or-decline-spec}}

{{action:U01-approve-or-decline-plan}}

{{action:U01-inspect-artifacts}}

The sprint specification and plan gates are where the learner sets authority. Check can verify the resulting
repository evidence, but it cannot prove that a person understood the proposal, made a good judgment
call, typed a host command, or created the pull request.

## Recognize success

Success is a reviewable boundary: a prepared attempt, a bounded
specification and plan, an append-only sprint record, and one operator guide in the same committed
packet. The real sprint lane opens a pull request from the learner fork after its commit gate. It is
not a public release claim, proof that a pull request exists, or permission to merge.

Check accepts one linear learner commit containing exactly those four paths. It checks the
prepared brief, exact headings and scope, a preserved sprint-log prefix, the required guide topics,
and a clean worktree. It does not authenticate approval.

## Check

{{action:U01-check-status}}

Check verifies repository-derived evidence rather than a transcript supplied by the learner. It does not prove that
a host command ran, that a learner approved a proposal knowingly, or that an autonomous process
reasoned well. It does not prove that a pull request was created.

## Recover or continue

Keep a failed attempt intact for review. Do not amend, rebase, force-update, delete, or overwrite
history to make an incomplete sprint look completed.

### Hint 1

Separate the sprint's specification approval and plan approval from its later implementation activity. Autonomous
execution may begin only after both explicit gates.

### Hint 2

The four named artifact paths are an evidence boundary. A valid packet keeps the prepared sprint-log
prefix unchanged and commits no unrelated file.

### Hint 3

Treat a failed Check as evidence to inspect, not an invitation to rewrite history or manufacture
artifact content. Preserve the attempt and use Reset only after returning safely to main.

{{action:U01-return-base}}

{{action:U01-reset-retry}}

U02 is published in Preview 0.30. Continue through its published Academy lesson rather than using
unpublished source exercises as a substitute for a guided route.

## Understand the mechanism

The scenario supplies an approval-required documentation scope, the required operator-guide title,
and three topics. The checkpoint compares that prepared brief with the final spec, plan, guide, and
append-only sprint log. It accepts one clean descendant commit with no extra paths.

This guide uses the shared action manifest and renderer, records each actor and execution surface,
and keeps the website-first lesson boundary intact.
