---
id: F04-fix-with-evidence
track: foundations
order: 4
title: Fix with evidence
outcome: Preserve a failing claimant-label regression in Git before a later minimal production repair.
prerequisites: F03-work-the-board
estimated_minutes: 30
scenario_command: python scripts/academy.py prepare F04-fix-with-evidence
checkpoint_command: arbiter-academy --repository <learner-repository> check F04-fix-with-evidence
next_lab: P01-feature-through-plan
---

# F04 — Fix with evidence

## Know before you begin

Complete F03 first, then start from a clean `main` branch in the same Academy clone.
Keep two surfaces open at the clone root: a native terminal for Academy and shell commands, and your
Claude Code, Codex, or Pi harness for messages to your agent and CodeArbiter commands.

This page names the surface for every action. Put a native-terminal command directly in PowerShell
or your shell; it never starts with `!`. Put a learner prompt or CodeArbiter command in the selected
harness; neither starts with `!`. The `!` prefix is only for a shell command deliberately sent
through a harness, and this lesson does not use that route. Do not use `git commit` yourself: the
agent runs the governed commit gate after you inspect and approve each boundary.

## What you will prove

You will turn a real claimant-label defect into durable evidence. A **regression** is a test that
demonstrates a defect before it is repaired. **Red** means that new test fails for the intended
reason; **green** means the same test passes after the repair. A **control character** is a non-printing
character such as newline, tab, or DEL. This lesson rejects control characters in a claimant label
while preserving an ordinary label such as `Sam Allen`.

The proof has two commits after Prepare: first a test-only red regression in
`tests/test_service.py`, then a service-only repair in `workshop_queue/service.py`. A **commit
boundary** is the exact path set in one commit. The **production boundary** is the real
`claim_ticket` function that receives the label, not a helper, transcript, CLI, or JSON copy.

## Prepare safely

{{action:F04-prepare}}

The printed attempt number is evidence metadata. Academy uses it in the branch name; do not type
the literal word `ATTEMPT_NUMBER`. The attempt starts from a deterministic defective service and
keeps `main` untouched.

{{action:F04-inspect-defect}}

{{action:F04-confirm-baseline}}

## Practice

### The proof map

| Moment | Durable evidence |
|---|---|
| Prepare | A clean, deliberately defective baseline on a numbered attempt branch. |
| Prove red | One test-only commit that reaches `claim_ticket` and fails for the intended control characters. |
| Repair green | One service-only commit that makes the unchanged regression pass. |
| Check | An external reconstruction of the two snapshots, path boundaries, and clean worktree. |

### Establish the red proof

Open the governed fix lane before requesting any change. The copied command below belongs in your
selected harness, not in a terminal.

{{action:F04-start-fix}}

Ask your agent for one direct executable regression and nothing in production. The request already
states the three rejected labels, the expected `ValueError`, and the ordinary-name control. Send it
unchanged first; it is specific enough to review.

{{action:F04-request-regression}}

{{action:F04-run-red-regression}}

Read the diff before staging. A test that is red because it cannot import, has a typo, or never
calls `claim_ticket` is not evidence of this defect.

{{action:F04-inspect-test-boundary}}

{{action:F04-stage-regression}}

{{action:F04-review-regression-boundary}}

When the report says the whole worktree and staged set contain only `tests/test_service.py`, let
the agent make the first governed commit.

{{action:F04-commit-regression}}

{{action:F04-prove-red-commit}}

### Repair only the live boundary

Now request the smallest reachable repair. It must reject characters below `U+0020` and `U+007F`
at the existing claimant-label boundary, leave the committed regression unchanged, add no
dependency, and retain ordinary-name behavior.

{{action:F04-request-repair}}

{{action:F04-prove-repair}}

{{action:F04-inspect-repair-boundary}}

{{action:F04-stage-repair}}

{{action:F04-review-repair-boundary}}

After that report identifies only `workshop_queue/service.py`, let the agent make the second
governed commit.

{{action:F04-commit-repair}}

{{action:F04-inspect-history}}

### Verify independently and preserve the result

## Recognize success

Success is not a reassuring transcript. Git shows a clean worktree and exactly two learner commits
after Prepare: the older commit changes only `tests/test_service.py` and is still red at that point;
the newer commit changes only `workshop_queue/service.py` and makes the same regression green.
The full service suite remains green, and `Sam Allen` still succeeds.

That separation lets another person reconstruct what was wrong, confirm that the first commit
actually detected it, and see the narrow repair without trusting a chat summary.

## Check

{{action:F04-check}}

**Check** is the external Academy verifier. It reads the prepared baseline, your commit order and
path sets, the retained regression and reachable repair shapes, and whether the live worktree is
clean. It does not execute learner-authored code. The red and green commands you ran above are your
real behavioral evidence; Check reconstructs their source and history safely. A green final test
alone is not enough: Check rejects a same-commit fix, a code-first path, an unreachable guard,
unrelated changes, or uncommitted work.

Python can refresh its own cache file while it runs the service test. Check excludes only those
two exercised cache files; every learner-authored, staged, tracked, or untracked change still fails
the clean-worktree condition.

## Recover or continue

If Check fails, preserve the branch and read the named predicate before attempting anything else.
Do not amend, rebase, force-reset, delete the branch, or hide evidence. Use Reset only after a
failed Check or an attempt whose commit boundary is irrecoverably wrong; it preserves the failed
attempt and creates the next numbered retry.

### Hint 1

The defect is at `claim_ticket`. A test that only validates a new helper does not prove the service
rejects an unsafe label when it claims a ticket.

### Hint 2

The first commit must remain red. Inspect it before asking for production work, then keep that test
unchanged while the production repair turns it green.

### Hint 3

If a report shows two paths, another commit, a changed regression, or a dirty worktree, stop before
Check. A fresh numbered retry is more useful evidence than rewritten history.

{{action:F04-reset-retry}}

After Check passes, return to `main` and leave the completed attempt branch available for review.

{{action:F04-return-base}}

F04 is complete only after the external Check passes. Continue to P01 when that guided Academy
lesson is published; an unpublished source exercise is not a substitute for a course step.

## Understand the mechanism

This pattern is a causal proof, not a ritual. Prepare establishes a known defective baseline. The
first commit records a test that reaches the live production boundary and fails for the missing
validation. The second commit adds the smallest reachable validation that makes that exact test
pass. The external verifier checks both snapshots, both path boundaries, and the clean current
worktree.

The operations surface stays small on purpose. Academy prepares, checks, resets, and returns an
attempt; the website teaches the decisions; CodeArbiter governs the agent work. Each part has one
job, so a learner can tell which command belongs where and a reviewer can reproduce the result.
