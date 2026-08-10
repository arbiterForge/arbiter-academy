---
id: F03-work-the-board
track: foundations
order: 3
title: Work the governed board
outcome: Move the exact queued Academy task through the sanctioned start and done transitions.
prerequisites: F02-orient-to-state
estimated_minutes: 15
scenario_command: python scripts/academy.py prepare F03-work-the-board
checkpoint_command: arbiter-academy --repository <learner-repository> check F03-work-the-board
next_lab: F04-fix-with-evidence
---

# F03 — Work the governed board

## Why this mechanism matters

The task board is durable repository state. A sanctioned transition preserves the task's scope and
evidence while adding a dated lifecycle marker. That lets another session distinguish queued,
active, and completed work without trusting chat history. The checkpoint proves the exact Git state;
under the local trust model it does not claim cryptographic proof of which executable made it.

## Start the scenario

From clean `main`, prepare the board attempt:

```powershell
python scripts/academy.py prepare F03-work-the-board
```

Read `.codearbiter/open-tasks.md` before acting. The target is `academy.feature.0001`; its description,
completion condition, boundaries, and evidence link are part of the exercise. You are moving the
task lifecycle, not implementing the listed feature.

## Use your host

Run both transitions through the installed codeArbiter surface in an enabled repository.

### Claude Code

```text
/ca:task start academy.feature.0001
/ca:task done academy.feature.0001
```

### Codex

```text
$ca-task start academy.feature.0001
$ca-task done academy.feature.0001
```

### Pi (Feature Forge preview)

Pi is the supported Feature Forge preview and requires project trust. If the direct form is not
available, use `/skill:ca-task` with the same `start` or `done` arguments.

```text
/ca-task start academy.feature.0001
/ca-task done academy.feature.0001
```

## Do the work

Inspect the board after `start`: the target should be `[~]` with a real started date. Then run
`done` and inspect again: the same task line should be `[x]` with `(done YYYY-MM-DD)`. No other task,
section, description, or evidence link should change.

Commit the final board transition as the sole board change:

```powershell
git diff -- .codearbiter/open-tasks.md
git add .codearbiter/open-tasks.md
git commit -m "academy: complete governed board transition"
```

The shipped task writer owns this observable file transition. It does not append `gate-events.log`,
so this lab neither asks for nor accepts an invented audit event.

## Hints

### Hint 1

Read the exact task ID and its boundaries. Do not select the similarly named security or fixture task.

### Hint 2

Use `start` before `done`, then compare the final board against the prepared commit. Only the target
line should differ.

### Hint 3

The accepted final shape keeps the complete original line, changes its marker to `[x]`, and carries
the date written by the sanctioned `done` transition. Commit that one-file outcome.

## Success evidence

The external verifier compares the board blob at preparation with the board blob at learner head.
It requires the exact queued target to become canonical done form, binds the date stamp to the
board-changing commit date, and byte-compares every unrelated line. Checkbox-only edits, stale or
malformed dates, unrelated edits, wrong tasks, and uncommitted changes fail.

```powershell
arbiter-academy --repository <learner-repository> check F03-work-the-board
```

## Recovery

If you selected another task or changed unrelated board text, preserve the current attempt and retry:

```powershell
python scripts/academy.py reset F03-work-the-board
```

Do not amend or erase the old branch to hide the route you tried.

## Next lab

Continue to **F04 — Fix with evidence** after the board checkpoint passes.
