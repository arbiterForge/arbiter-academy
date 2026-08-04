---
id: P03-record-an-adr
track: practitioner
order: 3
title: Record an accepted learner-attributed ADR
outcome: Decide the Workshop Queue summary-format boundary in accepted ADR 0004 and a matching learner-attributed decision-log entry.
prerequisites: P02-commit-review-pr
estimated_minutes: 25
scenario_command: arbiter-academy --repository <learner-repository> prepare P03-record-an-adr
checkpoint_command: arbiter-academy --repository <learner-repository> check P03-record-an-adr
next_lab: P04-review-a-dependency
---

# P03 — Record an accepted ADR

## Why this mechanism matters

An ADR preserves a consequential choice, its context, and its trade-offs where future maintainers
can find them. The append-only decision log makes the accepted lifecycle discoverable. These two
artifacts are codeArbiter's canonical result for this exercise; there is no third generic event to
invent. ADR 0003 already governs Academy verifier trust, so this decision must allocate 0004.

## Start the scenario

Run this from the learner checkout. The explicit installed verifier restores an active P02 attempt
to the original safe remotes before it prepares the decision tension. Preserved P02 records keep
this external-authority requirement in place after restoration.

```powershell
$learnerRepository = (Resolve-Path -LiteralPath '.').Path
arbiter-academy --repository $learnerRepository prepare P03-record-an-adr
```

The scenario presents stable text versus structured JSON for Workshop Queue summaries. It does not
pre-create an ADR, copy a SMARTS table, or append a decision-log entry.

## Use your host

Invoke the ADR lane with the bounded summary-format decision.

### Claude Code

```text
/ca:adr "Choose the Workshop Queue summary-format boundary"
```

### Codex

```text
$ca-adr "Choose the Workshop Queue summary-format boundary"
```

### Pi (Feature Forge preview)

Pi is the supported Feature Forge preview and requires project trust. Its documented fallback is
`/skill:ca-adr "Choose the Workshop Queue summary-format boundary"`.

```text
/ca-adr "Choose the Workshop Queue summary-format boundary"
```

## Do the work

Read the existing decisions and decision log before allocating a number. Compare the compatibility,
automation, schema-evolution, and local-first consequences of stable text and structured JSON.
Complete the sanctioned ADR flow and accept one bounded option.

The result must be `.codearbiter/decisions/0004-academy-lab.md` with substantive `Context`,
`Decision`, and `Consequences` sections. Append the matching accepted record to
`.codearbiter/decisions/decision-log.md`. Both artifacts must agree on ordinal, decision, lifecycle,
and the learner identity captured at prepare. Commit them together after preparation. Do not
overwrite or rename ADR 0003 and do not create a generic governance-event artifact.

## Hints

### Hint 1

Inventory `.codearbiter/decisions/` first. ADR 0003 is occupied by the verifier trust boundary, not
the summary-format question.

### Hint 2

Write consequences that distinguish stable human-readable output from structured automation and
versioning. A restatement of the chosen option is not a trade-off analysis.

### Hint 3

Before committing, compare the ADR heading/status/attribution with the new decision-log line. The
accepted ordinal and bounded decision must match in both places.

## Success evidence

The attempt introduces accepted ADR 0004 and a later or co-committed append-only decision-log entry,
both after preparation and both attributed to the prepared learner identity. The verifier rejects
duplicate 0003, missing canonical sections, stale or mismatched lifecycle/decision/attribution, and
uncommitted lookalikes. No third event is required.

```powershell
$learnerRepository = (Resolve-Path -LiteralPath '.').Path
arbiter-academy --repository $learnerRepository check P03-record-an-adr
```

## Recovery

If the wrong number, decision, lifecycle, or attribution was recorded, preserve the attempt and
reset:

```powershell
$learnerRepository = (Resolve-Path -LiteralPath '.').Path
arbiter-academy --repository $learnerRepository reset P03-record-an-adr
```

Never rename or overwrite ADR 0003 to make room.

## Next lab

Continue to **P04 — Review a real dependency before installation** after P03 passes.
