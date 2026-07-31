---
id: P01-feature-through-plan
track: practitioner
order: 1
title: Feature through a user-approved spec and derived plan
outcome: Deliver unresolved-ticket summary behavior through an approved spec, coverage-valid derived plan, sanctioned task transition, and test-before-code history.
prerequisites: F04-fix-with-evidence
estimated_minutes: 45
scenario_command: python scripts/academy.py prepare P01-feature-through-plan
checkpoint_command: arbiter-academy --repository <learner-repository> check P01-feature-through-plan
next_lab: P02-commit-review-pr
---

# P01 — Feature through a user-approved spec and derived plan

## Why this mechanism matters

A governed feature begins with agreement about observable behavior, not an implementation-shaped
task list. Here the approval boundary is the specification. The implementation plan derives from
that approved contract and must cover it, but codeArbiter does not define a separate plan-approval
event for this lane. Real Git ordering then distinguishes a regression that exposed missing
behavior from a test written after the code.

## Start the scenario

From clean `main`, prepare the bounded Workshop Queue feature:

```powershell
python scripts/academy.py prepare P01-feature-through-plan
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
tickets are absent from the summary, not because of syntax, import, or fixture errors. Commit that
RED test alone. Only then make the smallest Workshop Queue change, run focused and full tests, and
commit the GREEN implementation later in the same attempt history.

## Hints

### Hint 1

Start from the staged task and existing report API. Phrase the spec in terms of which ticket states
must be represented and what a caller can observe, not the private loop you expect to edit.

### Hint 2

Build a coverage table from each approved acceptance criterion to a plan step and test. There is no
second approval gate to fabricate; the plan's authority comes from its traceable derivation.

### Hint 3

At the RED commit, inspect `git diff <prepared-commit>..HEAD` and confirm only the test/evidence side
changed. The production summary path must first change in a later commit where the same test passes.

## Success evidence

The selected attempt contains the approved spec, its coverage-valid derived plan, and the canonical
task-board transition. Immutable Git history places a meaningful failing summary regression after
prepare and a later minimal production repair, with focused and full verification passing at head.
Prose saying “approved,” a hand-edited task, a same-commit test/fix, or an invented plan-approval
event is insufficient.

```powershell
arbiter-academy --repository <learner-repository> check P01-feature-through-plan
```

The installed verifier recomputes bounded repository state; terminal transcripts and progress JSON
are not outcome evidence.

## Recovery

If approval, plan coverage, task movement, or TDD ordering is wrong, preserve the attempt and reset:

```powershell
python scripts/academy.py reset P01-feature-through-plan
```

Do not amend or rebase to manufacture the required history.

## Next lab

Continue to **P02 — Review, commit, push, and record an offline local PR receipt** after P01 passes.
