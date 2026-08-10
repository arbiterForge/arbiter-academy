---
id: F02-orient-to-state
track: foundations
order: 2
title: Orient to live governance state
outcome: Bind a compact orientation record to the exact current context bytes and project stage.
prerequisites: F01-fork-clone-doctor
estimated_minutes: 15
scenario_command: python scripts/academy.py prepare F02-orient-to-state
checkpoint_command: arbiter-academy --repository <learner-repository> check F02-orient-to-state
next_lab: F03-work-the-board
---

# F02 — Orient to live governance state

## Why this mechanism matters

Governed work begins with repository state, not a remembered prompt. `CONTEXT.md` identifies the
project stage and boundaries, then links to the task board, standards, decisions, plans, and
evidence. Hashing the tracked bytes makes your orientation record specific to the state you read
without copying sensitive terminal output or personal machine details.

## Start the scenario

From a clean `main` branch with fork-safe origin routing, prepare the orientation attempt:

```powershell
python scripts/academy.py prepare F02-orient-to-state
```

The overlay records only the starting condition. The enabled stage-2 Workshop Queue state already
in the repository remains the source of truth.

## Use your host

All forms require enabled repository state. Read the files the status result cites; the status
summary alone is not the exercise.

### Claude Code

```text
/ca:status
```

### Codex

```text
$ca-status
```

### Pi (Feature Forge preview)

Pi is the supported Feature Forge preview. Grant project trust before loading the project skill; use
`/skill:ca-status` as the documented fallback.

```text
/ca-status
```

## Do the work

Read `.codearbiter/CONTEXT.md`, then follow its links to `open-tasks.md`, `coding-standards.md`, the
decision log, and current plans. Record exactly four fields in
`.codearbiter/reports/academy/F02-orientation.json`: integer `schema_version` 1, canonical
`context_path`, the SHA-256 of the tracked file bytes, and the integer stage from those same bytes.

PowerShell can compute the byte digest without normalizing line endings:

```powershell
$bytes = [IO.File]::ReadAllBytes('.codearbiter/CONTEXT.md')
$digest = [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($bytes)).ToLowerInvariant()
```

Create the JSON with those values, inspect it, then commit only the orientation record. Do not edit
`CONTEXT.md` to fit a stale digest.

## Hints

### Hint 1

Start at the activation front matter. Find `stage:` before following every linked artifact.

### Hint 2

Cross-check the host status with the file, but hash the file's bytes—not copied output or rendered prose.

### Hint 3

Use `.codearbiter/CONTEXT.md` literally as `context_path`, compute its current byte digest, preserve
stage as an integer, and commit the four-field object on this attempt branch.

## Success evidence

The learner commit adds a four-field orientation record. The external verifier reloads the tracked
`CONTEXT.md` at the attempt head, recomputes its SHA-256, extracts its stage, and rejects extra keys,
stale values, altered paths, uncommitted files, or a modified context.

```powershell
arbiter-academy --repository <learner-repository> check F02-orient-to-state
```

## Recovery

If the record or context became muddled, leave the attempt intact and prepare a deterministic retry:

```powershell
python scripts/academy.py reset F02-orient-to-state
```

Work only on the new retry branch. Update never rewrites completed attempts.

## Next lab

Continue to **F03 — Work the governed board** after the orientation checkpoint passes.
