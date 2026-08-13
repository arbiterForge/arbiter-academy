---
id: U04-initialize-projects
track: power-user
order: 4
title: Initialize a greenfield and a brownfield project
outcome: In a future accepted release, compare the sanctioned project routes, commit each child through CodeArbiter, and bind both committed repositories with a canonical report.
prerequisites: U03-refactor-chore-release
estimated_minutes: 55
scenario_command: {{action:U04-prepare-attempt}}
checkpoint_command: {{action:U04-check-status}}
next_lab: U05-debug-spike-conflict
---

# U04: Initialize a greenfield and a brownfield project

## Know before you begin

U04 is future private-source material and is not runnable with Preview 0.12. The current release
refuses U04 Prepare, Check, Reset, and the canonical report writer before the U04 lifecycle begins.
Do not use the detailed cards below as a workaround for that publication boundary.

### Current Preview 0.12 boundary

{{action:U04-confirm-private-boundary}}

## What you will prove

The future accepted walkthrough will keep the Academy root as the attempt controller and final-report
repository. It must not initialize a child project in the Academy root. Host-native commands act on
the folder visible in that host. A terminal `cd` does not switch it, and neither native-terminal nor
CodeArbiter commands use `!`.

Greenfield will use `ca-init`, then `ca-decompose`, which generates the three exact reconciliation
inputs under `.codearbiter/plans/`. After learner review, greenfield alone will use `ca-reconcile`.
Brownfield will use `ca-init`, then `ca-create-context`; the accepted walkthrough must use
`ca-create-context` on the brownfield and must not use `ca-decompose` on the brownfield. The real
brownfield route does not create the three `ca-reconcile` plan inputs, so the future lesson will not
invent them or run brownfield reconciliation.

Each future child then follows the same repository boundary: inspect generated changes, explicitly stage
only those changes, review the cached diff, run host-native `ca-commit` while visibly rooted at that
child, and prove clean status. An unresolved `[CONFIRM-NN]` stops the attempt.

## Prepare safely

The optional card below proves only that installed Preview 0.12 refuses Prepare. It does not create
the two children or authorize the remaining lifecycle.

{{action:U04-prepare-attempt}}

After the refusal, stop and use a published Preview 0.12 lab.

### Future private-source walkthrough

Everything from the next card through the parent clean-state card requires a future accepted U04
release that publishes the lesson and its supported tooling. These cards preserve the reviewed
lifecycle contract, but they are not executable with Preview 0.12.

{{action:U04-inspect-root}}

## Practice

In the future accepted walkthrough, complete and commit greenfield before opening brownfield:

{{action:U04-inspect-greenfield}}

{{action:U04-run-greenfield-init}}

{{action:U04-run-greenfield-decompose}}

{{action:U04-read-greenfield-plans}}

{{action:U04-choose-greenfield-reconciliation}}

{{action:U04-run-greenfield-reconcile}}

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

Only after both future child commits are clean may the Academy parent bind them. Preview 0.12 cannot
write that report. The future accepted tooling must publish one supported canonical writer so no
learner or agent has to guess verifier-sensitive headings, labels, field order, or terminal newline.

{{action:U04-inspect-project-evidence}}

{{action:U04-write-binding-report}}

{{action:U04-inspect-report}}

{{action:U04-stage-report}}

{{action:U04-review-commit-boundary}}

{{action:U04-run-commit-gate}}

{{action:U04-confirm-clean}}

## Recognize success

In a future accepted U04 release, greenfield has committed initialized context, the exact three
`.codearbiter/plans/` artifacts, and at least one accepted ADR. Brownfield has committed initialized
context from its existing source and does not contain a synthetic three-plan reconciliation set.
Both child worktrees are clean before their heads, trees, and committed context digests are bound.
The parent commit changes only `.codearbiter/reports/academy/U04-initialization.md`.

The future accepted Check will prove these repository facts. It will not prove that a host command
ran, that a learner made a good decision, or that anything was pushed or published.

## Check

Current Preview 0.12 Check is only an optional refusal probe. It cannot verify the future lifecycle.

{{action:U04-check-status}}

## Recover or continue

Preview 0.12 Reset is only an optional refusal probe and cannot recover this unpublished lesson.
For a future accepted attempt, preserve failures and return to the exact child whose review or commit
gate stopped. Do not reset, rewrite, or delete child history to make status look clean.

{{action:U04-reset-retry}}

## Understand the mechanism

The private action manifest preserves actor, surface, timing, expected result, evidence, recovery,
and next safe step for future acceptance. Its verifier reads real CodeArbiter layout from committed
child heads: decompose plans live under `.codearbiter/plans/`; context-creation documents remain in
their real root locations. Future accepted tooling must expose the canonical report writer and Check
through the same byte renderer. Until then, Preview 0.12 refuses the commands before those U04
mechanics run.
