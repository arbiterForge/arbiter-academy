---
id: P06-context-drift-recovery
track: practitioner
order: 6
title: Recover context drift without losing unrelated work
outcome: Update stale CONTEXT.md through the documented recovery route while preserving the prepared docs/preserved-note.md bytes exactly.
prerequisites: P05-checkpoint-remediation
estimated_minutes: 30
scenario_command: arbiter-academy --repository <learner-repository> prepare P06-context-drift-recovery
checkpoint_command: arbiter-academy --repository <learner-repository> check P06-context-drift-recovery
next_lab: P07-threat-model
---

# P06 - Recover context drift without losing unrelated work

## Why this mechanism matters

Repository context is useful only while its claims still match the source and accepted decisions.
P06 begins after P05 accepted ADR-0005, but the prepared context still cites ADR-0002 and says
`Workshop Queue report output is JSON-only.` Its provenance still points to the older CLI object
`042746e43698e5d2a6de4c536f1024f893aef805`, while the prepared CLI object is
`5b41fb168a8b258cfae7eebc46e8b9ea7696ba56`. The prepared code proves that text is the default and JSON is optional.
You will repair that bounded drift while proving an unrelated note survived.

## Start the scenario

Run the installed Academy command from your learner checkout:

```powershell
$learnerRepository = (Resolve-Path -LiteralPath '.').Path
arbiter-academy --repository $learnerRepository prepare P06-context-drift-recovery
```

Read `.codearbiter/CONTEXT.md`, `workshop_queue/cli.py`,
`.codearbiter/.provenance/CONTEXT.json`, and the prepared `docs/preserved-note.md` Git object before
editing. Record the prepared context, provenance, and note raw-byte SHA-256 values.

## Use your host

These are host routes to the context audit. The committed recovery record does not prove that any host command was invoked;
it proves only the repository state and your declared route. For this
contradicted claim, `re-scout` is the sole permitted recovery route.

### Claude Code

```text
/ca:context-check
```

### Codex

```text
$ca-context-check
```

### Pi (Feature Forge preview)

Pi requires project trust. Use the generated `/ca-context-check` alias shown below. If that alias is unavailable,
use the host-native `/skill:ca-context-check` fallback.

```text
/ca-context-check
```

## Do the work

1. Read `.codearbiter/CONTEXT.md`, `workshop_queue/cli.py`, and the prepared
   `docs/preserved-note.md` object.
2. Identify `Workshop Queue report output is JSON-only.` as stale from the code evidence and notice
   that accepted ADR-0005 replaced the older lifecycle decision.
3. Run the host audit and select scoped `re-scout`. Replace the stale report line with exactly
   `Workshop Queue report output defaults to stable text and supports structured JSON with --format json.`
   Update the lifecycle link to ADR-0005 and update only the provenance record's sole source hash to the prepared CLI object ID.
   Commit exactly `.codearbiter/CONTEXT.md` and `.codearbiter/.provenance/CONTEXT.json` together.
4. Recompute raw Git-object digests without editing the note, write the canonical v2 handoff at
   `.codearbiter/reports/academy/P06-recovery.json`, and commit only the handoff. Record the prepared
   commit, the immediately preceding recovery commit, exact repository-relative paths, route
   `re-scout`, and before/after digests for context, provenance, and preserved note.
5. Run the installed check:

```powershell
$learnerRepository = (Resolve-Path -LiteralPath '.').Path
arbiter-academy --repository $learnerRepository check P06-context-drift-recovery
```

## Hints

### Hint 1

Compare the context's report statement with `report_parser.add_argument("--format", ...)` and
`_write_report`; the tracked source is the contrary evidence.

### Hint 2

Use `git show <prepared-commit>:<path>` when calculating before values. A filesystem read after an
edit cannot reconstruct the prepared object.

### Hint 3

The correction commit has exactly two paths. The next commit has exactly one. Both note digests are
the same because the note existed at prepare and remains byte-identical at HEAD.

## Success evidence

The verifier requires a clean worktree and exactly two ordered, single-parent commits after prepare:
first the exact stale-to-corrected context/provenance transition, then the canonical handoff alone.
It recomputes every digest and proves prepared/head equality for the unrelated note. Equivalent
commit subjects are accepted because messages are not invented evidence. Route evidence does not
prove host invocation.

```powershell
$learnerRepository = (Resolve-Path -LiteralPath '.').Path
arbiter-academy --repository $learnerRepository check P06-context-drift-recovery
```

## Recovery

If the attempt is wrong, retain the failed branch and use only the installed reset route:

```powershell
$learnerRepository = (Resolve-Path -LiteralPath '.').Path
arbiter-academy --repository $learnerRepository reset P06-context-drift-recovery
```

Reset archives rather than discards the attempt; the failed branch remains available for diagnosis,
and preparation continues on a numbered retry.

## Next lab

Continue to **P07 - Threat-model the path-handling boundary** after P06 passes.
