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

## Why this mechanism matters

A passing test added after a repair cannot show that it detects the original defect. Regression-first
history can: one commit introduces an executable test that fails against the prepared code, and a
later commit makes that same test pass with the smallest repair. This lab uses the real Workshop
Queue service boundary, not a syntax error or a narrated transcript.

## Start the scenario

From clean `main`, prepare the deterministic defective service and pre-regression test file:

```powershell
python scripts/academy.py prepare F04-fix-with-evidence
```

The scenario makes `claim_ticket` accept a claimant label containing newline, tab, or DEL even though
`academy.security.0004` requires those labels to be rejected while ordinary names remain valid.

## Use your host

Enter the governed fix lane before editing production code. Enabled repository state is required.

### Claude Code

```text
/ca:fix "Reject control characters in a claimant label"
```

### Codex

```text
$ca-fix "Reject control characters in a claimant label"
```

### Pi (Feature Forge preview)

Pi is the supported Feature Forge preview and requires project trust. The documented fallback is
`/skill:ca-fix "Reject control characters in a claimant label"`.

```text
/ca-fix "Reject control characters in a claimant label"
```

## Do the work

First add an executable `unittest` case in `tests/test_service.py` that calls the real `claim_ticket`
boundary with a control-character label and expects rejection. Run it and observe a test **failure**,
not an import or syntax error. Commit only the regression test.

```powershell
python -m unittest tests.test_service.TicketTransitionTests.test_claim_rejects_control_characters_in_volunteer_label -v
git add tests/test_service.py
git commit -m "test: reproduce control-character claimant defect"
```

Only after that commit, apply the smallest validation at the existing claimant boundary in
`workshop_queue/service.py`. Keep dependency-free runtime, UTC injection, explicit ticket states,
and valid ordinary labels intact. Re-run the focused test and the service suite, then commit the
production repair separately.

## Hints

### Hint 1

Call the service function directly with an open ticket and a label containing `\n`; the bug is at
the claimant boundary, not JSON storage or the CLI.

### Hint 2

Your regression must fail while `workshop_queue/service.py` is still at the prepared defect. Commit
that test before editing production code.

### Hint 3

Reject characters below U+0020 and U+007F at the existing non-empty volunteer check. Prove a normal
label such as `Sam Allen` still succeeds, then commit the repair later in history.

## Success evidence

The attempt history has a test-only commit after preparation and a later service commit. Running the
focused regression at the test-only commit produces the expected assertion failure; running it at
the final repair commit passes and retains ordinary claimant behavior. Same-commit test/fix, code-only,
test-only, unrelated tests, reversed order, or transcript-only claims fail.

```powershell
arbiter-academy --repository <learner-repository> check F04-fix-with-evidence
```

The verifier evaluates immutable Git history and bounded semantics. It does not treat raw terminal
output or learner progress JSON as proof.

## Recovery

If test and code landed together or in the wrong order, do not rewrite history. Preserve it and reset:

```powershell
python scripts/academy.py reset F04-fix-with-evidence
```

The new retry starts from the same deterministic defect and keeps the old branch available.

## Next lab

Continue to **P01 — Feature through plan** in the Practitioner track after F04 passes.
