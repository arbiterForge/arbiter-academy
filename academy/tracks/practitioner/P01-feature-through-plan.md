---
id: P01-feature-through-plan
track: practitioner
order: 1
title: Feature through a user-approved spec and derived plan
outcome: Deliver unresolved-ticket summary behavior through an approved spec, coverage-valid derived plan, sanctioned task transition, and test-before-code workflow.
prerequisites: F04-fix-with-evidence
estimated_minutes: 45
scenario_command: arbiter-academy --repository <learner-repository> prepare P01-feature-through-plan
checkpoint_command: arbiter-academy --repository <learner-repository> check P01-feature-through-plan
next_lab: P02-commit-review-pr
---

# P01 — Feature through a user-approved spec and derived plan

## Why this mechanism matters

A governed feature begins with agreement about observable behavior, not an implementation-shaped
task list. Here the approval boundary is the specification. The implementation plan derives from
that approved contract and must cover it, but codeArbiter does not define a separate plan-approval
event for this lane. You still practice test-before-code; the bounded, one-final-commit Academy
checkpoint verifies the final repository contract rather than reconstructing command execution order.

## Start the scenario

From clean `main`, prepare the bounded Workshop Queue feature:

```powershell
$learnerRepository = (Resolve-Path -LiteralPath '.').Path
arbiter-academy --repository $learnerRepository prepare P01-feature-through-plan
```

Preparation creates the next numbered attempt branch and queues
`academy.feature.0002 - Show unresolved tickets in the summary`. It does not approve a spec, derive
a plan, start the task, or implement the summary.

## Use your host

Invoke the feature lane for the exact staged request. Enabled repository state is required.

### Claude Code

```text
/ca:feature "Show unresolved tickets in the Workshop Queue summary"
/ca:task start academy.feature.0002
```

### Codex

```text
$ca-feature "Show unresolved tickets in the Workshop Queue summary"
$ca-task start academy.feature.0002
```

### Pi (Feature Forge preview)

Pi is the supported Feature Forge preview and requires project trust. Its documented fallbacks are
`/skill:ca-feature "Show unresolved tickets in the Workshop Queue summary"` and
`/skill:ca-task start academy.feature.0002`.

```text
/ca-feature "Show unresolved tickets in the Workshop Queue summary"
/ca-task start academy.feature.0002
```

## Do the work

Inspect `.codearbiter/CONTEXT.md`, the queued task, and the current summary boundary. Author
`.codearbiter/specs/academy-feature.md` so its acceptance criteria identify unresolved ticket
states and the observable summary result. Pause for real user approval of that spec. Record only
the approval representation the sanctioned feature lane supports; do not invent a plan approval or
a generic approval event.

Derive `.codearbiter/plans/academy-feature.md` from the approved acceptance criteria. The plan must
map every criterion to a concrete implementation or verification step. Then run the copyable task
command for your host to move exactly `academy.feature.0002` from queued to in progress with its
writer-produced start date.

Add and run a focused summary test before touching production code. It must fail because unresolved
tickets are absent from the summary, not because of syntax, import, or fixture errors. Then make
only the bounded `open + claimed` assignment, run focused and full GREEN verification, and let the
terminal commit gate create one final green commit containing the spec, derived plan, task-board
transition, test, and production change. Do not create a RED commit, amend, or rebase.

## Hints

### Hint 1

Start from the staged task and existing report API. Phrase the spec in terms of which ticket states
must be represented and what a caller can observe, not the private loop you expect to edit.

### Hint 2

Build a coverage table from each approved acceptance criterion to a plan step and test. There is no
second approval gate to fabricate; the plan's authority comes from its traceable derivation.

### Hint 3

Keep the retained regression exact and narrow. The installed Academy checkpoint parses it as data
against a verifier-owned prepared/intended model; it does not run learner Python, prove chat
approval, or prove which executable wrote byte-identical files.

## Success evidence

The selected attempt contains the approved spec, its coverage-valid derived plan, the canonical
task-board transition, and one final green commit with the exact bounded test and production
artifacts. The checkpoint reconstructs the regression's expected result from the frozen fixture and
verifies the final AST/data contract. It does not prove that you ran the test before production code,
observed a terminal RED/GREEN run, or created separate test and repair commits. Those are essential
workflow instructions for the exercise; they are not durable claims made by a non-executing,
one-final-commit verifier.

```powershell
arbiter-academy --repository <learner-repository> check P01-feature-through-plan
```

The installed verifier recomputes bounded repository state; terminal transcripts and progress JSON
are not outcome evidence.

## Recovery

If approval, plan coverage, task movement, or TDD ordering is wrong, preserve the attempt and reset:

```powershell
$learnerRepository = (Resolve-Path -LiteralPath '.').Path
arbiter-academy --repository $learnerRepository reset P01-feature-through-plan
```

Do not amend or rebase a retry; preserve the attempt and let reset create the next one.

## Next lab

Continue to **P02 — Review, commit, push, and record an offline local PR receipt** after P01 passes.
