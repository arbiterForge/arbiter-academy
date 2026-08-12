# P02 guided lesson design

## Purpose

Rewrite P02 so a learner can rehearse a bounded review, two commits, and an
origin-only push without mistaking the local exercise for a hosted pull
request. The website remains the primary course interface. Academy tooling
prepares the local topology, records deterministic receipt data, checks the
result, and resets an attempt. It does not decide whether review was
substantive, stage, commit, push, open a pull request, or mark work approved.

## Learner model

P02 follows P01 and operates in the learner's isolated fork. Prepare replaces
the checkout remotes with verifier-owned local bare repositories for the
exercise. The guide calls this an offline-local PR rehearsal throughout. It
must never imply that GitHub, a hosted reviewer, CI, or a human approval took
part.

The learner first prepares outside the checkout, captures the printed branch,
prepared commit, and logical remote identities, then enters the explicit
repository path. Native-terminal commands never start with `!`. Harness shell
commands start with exactly one `!`. CodeArbiter commands and messages never
start with `!`. The rendered action cards make the learner, agent, Browser,
native-terminal, active-harness, and helper surfaces explicit.

## Guided action contract

The rewrite adds `academy/actions/P02-commit-review-pr.json` and replaces
every runnable raw command fence with one rendered action reference. It uses
the Academy's eight required lesson headings: Know before you begin, What you
will prove, Prepare safely, Practice, Recognize success, Check, Recover or
continue, and Understand the mechanism.

The ordered actions are: read the offline boundary; prepare; enter and guard
the checkout; inspect and stage the prepared exercise change; request and inspect the
review boundary; have the active agent run the review and work-commit gates;
prove the nonempty work range and origin-only push; record the receipt; inspect
and stage that one receipt; have the agent commit it; prove the worktree is
clean; run Academy Check; then preserve or reset the attempt.

The guide says who performs each action. The learner asks the agent to review
and commit. The learner, not the agent, runs the native-terminal evidence
commands, decides whether their review is cleared, and inspects the resulting
Git state. Browser material explains the exercise boundary and links to
follow-up guidance only. It never pretends the browser executes course work.

## Deterministic receipt helper

Add an installed `arbiter-academy --repository <learner-repository> record
P02-commit-review-pr --review-declared-cleared` operation. It is a narrow
receipt formatter, not a course controller. Before writing the canonical
UTF-8-without-BOM receipt, it requires installed verifier authority outside the
learner checkout, an active P02 attempt, exact branch and prepared/work-head
state, the known remote topology, an origin-only pushed legal work range, the
exact supplied patch, no receipt file, and a clean working tree.

The helper writes only
`.codearbiter/reports/academy/P02-pr-receipt.json`. It neither stages nor
commits that file. It does not push, change remotes, use a network API, run a
host command, create a hosted pull request, or turn a learner declaration into
an authenticated human-review fact. Its output states that it recorded a
learner-declared offline-local review receipt and did not verify a hosted pull
request or human review.

## Evidence boundary and recovery

Check recomputes the prepared attempt, branch, remote roles, nonempty linear
work range, exact two work paths, supplied patch result, and a later
receipt-only commit. It validates the receipt's declared `review.status` as
`cleared`. It cannot prove who reviewed, whether review occurred, which
CodeArbiter command ran, test chronology, a hosted pull request, hosted CI, or
GitHub remote use. The guide names those limits directly.

Reset is preservation-first and fail-closed. It restores the original topology
only when the prepared sidecar state still matches. The guide directs learners
to preserve the failure output and reset if a guard, record, or Check fails. It
does not authorize remotes edits, ref deletion, rebase, force-push, evidence
deletion, or attempts to manufacture a passing receipt.

## Scope and promotion

P02 stays non-public until F03, F04, and P01 are accepted. Promotion is a
separate release slice that adds it to the public manifest and generated-site
inventory only after the guide, action manifest, CLI helper, adversarial
receipt tests, rendered action tests, focused independent review, and
exact-head hosted CI are accepted.

## Acceptance checks

- Every action has actor, surface, exact variant, copy control, expected
  result, recovery, and evidence.
- The lesson has no raw runnable learner command fences.
- The CLI recorder rejects uninstalled, unpublished, inactive, dirty,
  mismatched, tampered, empty-range, wrong-patch, existing-receipt, and
  ambiguous states without Git or network side effects.
- A successful recorder writes only the canonical receipt. A separately
  requested agent commit is still required before Check can pass.
- Tests cover action rendering, host and operating-system selection, action
  order, offline-local language, Check limits, reset safety, and recorder
  refusal cases.
