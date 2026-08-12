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

# P01 - Feature through a user-approved spec and derived plan

## Know before you begin

P01 is the first Practitioner lesson in Preview 0.11. It starts from the F04 repair boundary and ends with one preserved feature attempt on a safe learner branch.

Complete F04 and begin in the same Academy fork and clone. Before Prepare, switch to `main` and
confirm that `git status --short` prints nothing. Keep a native terminal open at the clone root for
Academy Prepare, Check, and Reset. Keep one CodeArbiter harness open at that same clone for the
feature workflow.

This lesson has two honest review paths. In **Solo practice**, you review the drafted specification
yourself, using the checklist below. In **Collaborative practice**, you ask for or use feedback in the
Arbiter Academy GitHub Discussion, then relay that feedback to your agent. If feedback is not
available, return to Solo practice. Neither path asks you to make up feedback or persist a marker
that pretends to prove another person approved the work.

Commands shown as native-terminal actions are entered directly and never begin with `!`. A shell
command shown for a harness begins with exactly one `!`. CodeArbiter commands and agent messages are
entered in the selected harness and never begin with `!`.

## What you will prove

You will preserve one feature attempt containing the exact specification, a plan derived from its
acceptance criteria, the sanctioned transition of `academy.feature.0002`, a focused regression, and
the bounded unresolved-ticket repair. The task is to report the exact total of `open` plus `claimed`
tickets through the existing summary boundary.

The agent drafts the specification and stops. You choose a review path, then send a separate proceed
instruction. Only then does the agent derive the plan, start the staged task, run the focused RED
test, make the bounded repair, run GREEN verification, and invoke the governed commit gate.

## Prepare safely

{{action:P01-prepare}}

`ATTEMPT_NUMBER` means the number Academy prints, such as `1`; it is not text to type literally.
Stay on that numbered branch for the whole attempt.

{{action:P01-draft-spec}}

The feature command creates the draft and stops at the specification decision. It does not grant
approval, derive a plan, start the task, or change production code.

## Practice

{{action:P01-read-spec}}

Use exactly one review path before you continue.

{{action:P01-solo-review}}

{{action:P01-discussion-review}}

### If review finds a concrete correction

Use the revision action. It sends a bounded request and returns you to the same review choice. It does not begin planning or implementation.

{{action:P01-revise-spec}}

### When the draft is acceptable

{{action:P01-proceed}}

After you send the proceed instruction, let the agent execute the governed path it describes. Add and run a focused summary test before touching production code. The RED result must fail because unresolved tickets are absent, not because a file, import, or fixture is broken. The repair remains the exact `open + claimed` assignment. Do not create a RED commit, amend, or rebase.

## Recognize success

The attempt has one final green commit after Prepare. That commit contains exactly the feature
specification, derived plan, canonical task-board transition, focused regression, and bounded
production repair. The task has a writer-produced start date, and `git status --short` prints
nothing before Check.

The specification is the review boundary. The plan has authority because it maps each approved
criterion to implementation and verification work. It is not a separate approval ceremony.

## Check

{{action:P01-check}}

A pass contains `checkpoint P01-feature-through-plan: passed; progress: .academy/progress.json`.
Check validates the final descendant commit, exact spec and plan shape, task transition, focused regression, bounded repair, and a clean worktree. It does not authenticate a human approval. It does not authenticate a GitHub Discussion response. It does not prove that you ran the test before production code or the order in which the agent ran RED and GREEN commands. Those are workflow practices you observe during the lesson, not claims made by this final-state verifier.

## Recover or continue

If the draft is wrong, use the revision action and repeat the review before proceeding. If review is
incomplete, plan coverage is weak, the task transition is wrong, or Check fails, preserve the attempt.
Read the named predicate and correct only that boundary in a new numbered attempt. Do not conceal
evidence by amending or rebasing history.

### Hint 1

Read the queued task and current report API before reviewing the draft. Describe visible ticket
states and caller-visible output, not a private loop you expect to edit.

### Hint 2

For Solo practice, check that every acceptance criterion is observable, names the relevant ticket
states, and can map to one plan step and one focused test. For Collaborative practice, compare the
feedback with those same facts before relaying it.

### Hint 3

The final verifier recomputes data and repository shape. Keep the test narrow and inspect the final
commit boundary; it cannot reconstruct chat, review, or command history.

After Check passes, leave the completed branch intact and return to `main` with this native-terminal action.

{{action:P01-return-base}}

P02 is not available in this preview. Continue only after its guided Academy lesson is published. Do not
use unpublished source exercises as a substitute for the accepted course.

If P01 needs another attempt, use the preserved retry action.

{{action:P01-reset-retry}}

## Understand the mechanism

A feature contract begins with observable behavior. The specification tells the agent and reviewer
what must be true; the plan traces that contract into work; the focused test protects the caller
boundary; and the commit gate records only the verified final change. Academy Check then compares
the prepared baseline, commit ancestry, required artifacts, and live worktree without trusting a
transcript supplied by the learner checkout.
