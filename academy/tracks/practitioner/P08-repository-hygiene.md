---
id: P08-repository-hygiene
track: practitioner
order: 8
title: Classify repository hygiene without destructive cleanup
outcome: Commit a complete live branch and worktree classification bound to prepared external identities without deleting or pruning anything.
prerequisites: P07-threat-model
estimated_minutes: 30
scenario_command: arbiter-academy --repository <learner-repository> prepare P08-repository-hygiene
checkpoint_command: arbiter-academy --repository <learner-repository> check P08-repository-hygiene
next_lab: U01-autonomous-sprint
---

# P08: Classify repository hygiene without destructive cleanup

## Know before you begin

Complete P07 and begin in the prepared Academy clone. The website is the primary lesson surface.
Academy CLI is limited to Prepare, Check, and Reset. Use Git and the selected host for the work
between those transitions.

Keep the repository root open in a native terminal and in your chosen harness. A native-terminal
command is entered directly and has no `!`. A harness shell command begins with exactly one `!`.
Harness text is a request you type to the agent, not a shell command. An agent-owned CodeArbiter
command belongs to the harness and has no `!`. The action cards label each case.

This lab authorizes observation, classification, a report draft, learner review, and a bounded
commit. It never authorizes deleting a branch, removing a worktree, pruning metadata, rewriting
history, or force operations.

## What you will prove

You will preserve a closed inventory of the prepared live refs and worktrees. For each prepared ref,
the report records its full ref name, object ID, worktree state, merge containment relative to
`main`, unique commit count, classification, and recommendation. For each prepared worktree, it
records the path-free prepared identity, branch binding, head binding, presence, dirtiness,
classification, and recommendation.

The expected classifications are conservative. The current attempt, dirty unmerged state, and
unmerged unique history remain `preserve`. The clean merged fixture is only
`eligible-for-explicit-review`; it is not a deletion instruction. The agent drafts the report; you
review it before the bounded commit gate runs.

## Prepare safely

{{action:P08-prepare}}

Preparation creates the numbered attempt, live fixture refs, and linked worktrees. It does not give
you a precomputed inventory. Stay on the numbered attempt until Check passes or Reset preserves it
for a retry.

{{action:P08-inventory-native}}

{{action:P08-inventory-harness-shell}}

The two inventory actions show the same Git evidence on different surfaces. Use one surface for the
actual inventory. Do not merge partial output from memory or from a previous attempt.

## Practice

{{action:P08-run-standup}}

Standup may organize the inspection, but it is not cleanup authority. Stop any cleanup proposal and
keep all live refs and worktrees intact.

{{action:P08-request-report-draft}}

The report path is `.codearbiter/reports/academy/P08-hygiene.json`. The agent must derive it from the
current live inventory, not copy a list from this page. It must include every prepared identity and
must not include an absolute local path.

{{action:P08-review-report}}

Review all prepared identities before staging. Confirm that the merged-clean branch is classified as
eligible only for an explicit future review, that dirty and unique state is preserved, and that the
current attempt remains preserved. If the report is incomplete or stale, preserve the fixture and
ask for a corrected draft. Do not compensate by changing Git state.

{{action:P08-stage-report}}

Stage the reviewed draft from a native terminal before inspecting the cached diff. This path-scoped
step is required: the next action only reviews what is already in the Git index.

{{action:P08-review-commit-boundary}}

{{action:P08-run-commit-gate}}

{{action:P08-confirm-clean}}

## Recognize success

The attempt has one post-Prepare evidence commit containing only
`.codearbiter/reports/academy/P08-hygiene.json`. Its report is canonical JSON generated from the
live fixture: five refs and three worktrees, with no local worktree path. The fixture itself stays
present and correctly bound. A clean `git status --short` result is required before Check.

## Check

{{action:P08-check}}

A pass contains `checkpoint P08-repository-hygiene: passed; progress: .academy/progress.json`.
Check does not prove that the agent ran standup, read every terminal line, or made an independent
human judgment about a future cleanup. It verifies the installed-authority fixture, the current live
resources, the sole report commit, and the exact canonical report blob. A passing Check does not
make a deletion safe or authorize cleanup.

## Recover or continue

If Check fails, preserve every ref and worktree and read the reported predicate. Never make the
fixture look clean by deleting, pruning, rebasing, force-updating, or overwriting history. Use Reset
only when you need a new numbered attempt; it preserves the failed attempt for inspection.

### Hint 1

Freeze the complete ref and worktree inventory before asking for a classification. A
classification based on one branch at a time can omit a prepared identity.

### Hint 2

Treat merge containment, dirtiness, and unique commits as separate facts. A merged branch
can still need preservation because its associated worktree is dirty.

### Hint 3

Review the report after the agent drafts it and before the commit gate. The learner owns the
decision to accept the bounded evidence, even when the agent prepared the file.

{{action:P08-return-base}}

{{action:P08-reset-retry}}

After a passing Check, return to `main` only when the worktree is clean and leave the completed
attempt intact. U01 remains a source exercise until its own guided rewrite and acceptance evidence
are complete. Do not treat it as the next public Academy lesson.

## Understand the mechanism

P08 records external identities outside the learner checkout, then compares the final report with
the prepared live fixture. The report intentionally carries path-free worktree identities rather
than local paths. That makes a copied inventory, a missing resource, a moved resource, a rebound
branch, and a stale classification detectable.

The verifier is strict about the final state but narrow about the process. It can verify the exact
report, commit boundary, and current prepared resources. It cannot observe every conversation or
decide whether a future cleanup is appropriate. Preserve live state and require a separate explicit
review before any cleanup decision.
