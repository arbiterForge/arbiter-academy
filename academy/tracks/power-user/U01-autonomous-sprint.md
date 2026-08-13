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

U01 has a reviewed source scenario and positive Check contract, but it is not public or runnable in
Preview 0.13. The website remains the primary lesson surface. Academy CLI is only the future helper
for Prepare, Check, and Reset. The installed public verifier deliberately refuses those operations
until the lesson has an accepted public release boundary.

Complete P08 first. In a later private integration environment, keep the repository root open in a
native terminal and the selected CodeArbiter harness. A command typed directly in a native terminal
has no `!`. A shell command passed through a harness begins with exactly one `!`. A host-native
CodeArbiter command belongs to the harness and has no `!`. The action cards label each case.

{{action:U01-confirm-private-boundary}}

## What you will prove

On a prepared U01 attempt, you will prove that a sprint did not self-authorize its work. The learner
reads the proposed specification, decides whether its scope is acceptable, then preserves the derived
specification, plan, append-only sprint log, and one bounded operator guide.

This is a documentation-only sprint. Its allowed final commit contains four paths: the spec, plan,
sprint log, and `docs/academy-sprint-summary.md`. The real sprint lane then pushes only the learner
fork branch and opens a pull request. It never pushes directly to upstream or merges. It does not
change product code, tests, dependencies, or remotes.

## Prepare safely

{{action:U01-inspect-scenario}}

{{action:U01-prepare-attempt}}

The expected public result is still a refusal, not an attempt branch. Do not convert that refusal into
a private shortcut by copying scenario files into a learner checkout. A later public U01 fixture must
be installed through the accepted Academy authority.

## Practice

The next actions describe the private exercise only after a maintainer has supplied a prepared
attempt. They are not permission to start an autonomous sprint on an ordinary checkout.

{{action:U01-run-sprint}}

{{action:U01-approve-or-decline-spec}}

{{action:U01-inspect-artifacts}}

The sprint specification gate is where the learner sets authority. Check can verify the resulting
repository evidence, but it cannot prove that a person understood the proposal, made a good judgment
call, typed a host command, or created the pull request.

## Recognize success

For the private exercise design, success is a reviewable boundary: a prepared attempt, a bounded
specification and plan, an append-only sprint record, and one operator guide in the same committed
packet. The real sprint lane opens a pull request from the learner fork after its commit gate. It is
not a public release claim, proof that a pull request exists, or permission to merge.

The future Check accepts one linear learner commit containing exactly those four paths. It checks the
prepared brief, exact headings and scope, a preserved sprint-log prefix, the required guide topics,
and a clean worktree. It does not authenticate approval.

## Check

{{action:U01-check-status}}

The public refusal is deliberate. In a prepared source-only attempt, Check verifies
repository-derived evidence rather than a transcript supplied by the learner. It does not prove that
a host command ran, that a learner approved a proposal knowingly, or that an autonomous process
reasoned well. It does not prove that a pull request was created.

## Recover or continue

Keep a failed attempt intact for review. Do not amend, rebase, force-update, delete, or overwrite
history to make an incomplete sprint look completed.

### Hint 1

Separate the sprint's specification approval from its later implementation activity. Autonomous
execution may begin only after the explicit scope gate.

### Hint 2

The four named artifact paths are an evidence boundary. A valid packet keeps the prepared sprint-log
prefix unchanged and commits no unrelated file.

### Hint 3

Treat an unavailable public Check as a release-boundary signal. It protects the public course from
recording progress before the installed verifier includes this accepted contract.

{{action:U01-return-base}}

{{action:U01-reset-retry}}

U02 is also private in Preview 0.13. Do not use unpublished source exercises as a substitute for a
published Academy lesson.

## Understand the mechanism

The scenario supplies an approval-required documentation scope, the required operator-guide title,
and three topics. The checkpoint compares that prepared brief with the final spec, plan, guide, and
append-only sprint log. It accepts one clean descendant commit with no extra paths.

This guide uses the same shared action manifest and renderer as published lessons, records each actor
and execution surface, and keeps the website-first lesson boundary intact. Publishing U01 still
requires package, route, browser, and hosted-release acceptance evidence for the complete learner path.
