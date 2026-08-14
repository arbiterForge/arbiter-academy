---
id: U04-initialize-projects
track: power-user
order: 4
title: Initialize a greenfield and a brownfield project
outcome: Compare the sanctioned project routes, commit each child through CodeArbiter, and bind both committed repositories with a canonical report.
prerequisites: U03-refactor-chore-release
estimated_minutes: 55
scenario_command: {{action:U04-prepare-attempt}}
checkpoint_command: {{action:U04-check-status}}
next_lab: U05-debug-spike-conflict
---

# U04: Initialize a greenfield and a brownfield project

## Know before you begin

U04 is a guided Preview 0.21 lesson. It prepares two separate child repositories beneath the Academy
attempt root. The Academy root controls the attempt and stores the final binding report; it is not a
CodeArbiter project for this lesson.

{{action:U04-confirm-private-boundary}}

## What you will prove

U04 keeps the Academy root as the attempt controller and final-report repository. Do not initialize a
child project in the Academy root. Host-native commands act on
the folder visible in that host. A terminal `cd` does not switch it, and neither native-terminal nor
CodeArbiter commands use `!`.

Greenfield will use `ca-init`, then `ca-decompose`, which generates the three exact reconciliation
inputs under `.codearbiter/plans/`. After learner review, greenfield alone will use `ca-reconcile`,
then `ca-adr` drafts the learner-attributed decision for the learner to review and explicitly
accept. Reconciliation does not author ADRs or advance their status.
Brownfield will use `ca-init`, then `ca-create-context`; the accepted walkthrough must use
`ca-create-context` on the brownfield and must not use `ca-decompose` on the brownfield. The real
brownfield route does not create the three `ca-reconcile` plan inputs, so this lesson does not
invent them or run brownfield reconciliation.

Each child follows the same repository boundary: inspect generated changes, explicitly stage
only those changes, review the cached diff, run host-native `ca-commit` while visibly rooted at that
child, and prove clean status. An unresolved `[CONFIRM-NN]` stops the attempt.

## Prepare safely

Prepare creates the greenfield and brownfield child repositories and switches the Academy repository
to the dedicated attempt branch. Do not make either child yourself.

{{action:U04-prepare-attempt}}

{{action:U04-inspect-root}}

## Practice

Complete and commit greenfield before opening brownfield:

{{action:U04-inspect-greenfield}}

{{action:U04-run-greenfield-init}}

{{action:U04-run-greenfield-decompose}}

{{action:U04-read-greenfield-plans}}

{{action:U04-choose-greenfield-reconciliation}}

{{action:U04-run-greenfield-reconcile}}

{{action:U04-record-greenfield-adr}}

{{action:U04-accept-greenfield-adr}}

{{action:U04-inspect-greenfield-changes}}

{{action:U04-stage-greenfield-changes}}

{{action:U04-review-greenfield-commit-boundary}}

{{action:U04-run-greenfield-commit-gate}}

{{action:U04-confirm-greenfield-clean}}

Then create and commit the real brownfield context without synthetic plan documents:

{{action:U04-inspect-brownfield}}

{{action:U04-run-brownfield-init}}

{{action:U04-run-brownfield-create-context}}

{{action:U04-inspect-brownfield-changes}}

{{action:U04-stage-brownfield-changes}}

{{action:U04-review-brownfield-commit-boundary}}

{{action:U04-run-brownfield-commit-gate}}

{{action:U04-confirm-brownfield-clean}}

Only after both child commits are clean may the Academy parent bind them. The canonical writer derives
the report from committed child state, so no learner or agent has to guess headings, labels, field
order, or terminal newline.

{{action:U04-inspect-project-evidence}}

{{action:U04-write-binding-report}}

{{action:U04-inspect-report}}

{{action:U04-stage-report}}

{{action:U04-review-commit-boundary}}

{{action:U04-run-commit-gate}}

{{action:U04-confirm-clean}}

## Recognize success

At success, greenfield has committed initialized context, the exact three
`.codearbiter/plans/` artifacts, and at least one accepted ADR. Brownfield has committed initialized
context from its existing source and does not contain a synthetic three-plan reconciliation set.
Both child worktrees are clean before their heads, trees, and committed context digests are bound.
The parent commit changes only `.codearbiter/reports/academy/U04-initialization.md`.

The U04 Check will prove these repository facts. It will not prove that a host command
ran, that a learner made a good decision, or that anything was pushed or published.

## Check

Check validates committed repository facts. It does not prove that a host command ran, that a learner
made a good decision, or that anything was pushed or published.

{{action:U04-check-status}}

## Recover or continue

U04 Reset deliberately refuses until Academy can archive both child histories. Preserve failures and
return to the exact child whose review or commit gate stopped. Do not reset, rewrite, or delete child
history to make status look clean.

{{action:U04-reset-retry}}

## Understand the mechanism

The action manifest preserves actor, surface, timing, expected result, evidence, recovery, and next
safe step. Its verifier reads real CodeArbiter layout from committed
child heads: decompose plans live under `.codearbiter/plans/`; context-creation documents remain in
their real root locations. The canonical writer and Check use the same byte renderer, so the report
that you inspect is the report Check verifies.
