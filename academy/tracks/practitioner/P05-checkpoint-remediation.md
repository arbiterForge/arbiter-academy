---
id: P05-checkpoint-remediation
track: practitioner
order: 5
title: Remediate a checkpoint finding
outcome: Reproduce a genuine blocked-ticket summary defect and link a real finding commit to a later regression-backed repair through shared changed paths.
prerequisites: P04-review-a-dependency
estimated_minutes: 45
scenario_command: arbiter-academy --repository <learner-repository> prepare P05-checkpoint-remediation
checkpoint_command: arbiter-academy --repository <learner-repository> check P05-checkpoint-remediation
next_lab: P06-context-drift-recovery
---

# P05 — Remediate a checkpoint finding

## Why this mechanism matters

A remediation report is useful only when it points to a reproduced product defect and a later fix
that actually intersects it. This scenario first gives Workshop Queue a genuine `blocked` state
through its normal boundaries, then stages a summary defect that omits a blocked ticket from the
unresolved count. Git ancestry, diffs, a regression, and shared changed paths prevent an unrelated
patch or synthetic JSON finding from passing as remediation.

## Start the scenario

Run this from the learner checkout. Preserved P02 verifier records require the installed command for
every later Practitioner transition, even though the original GitHub remotes are already restored.
Prepare the blocked-ticket fixture and staged summary defect:

```powershell
$learnerRepository = (Resolve-Path -LiteralPath '.').Path
arbiter-academy --repository $learnerRepository prepare P05-checkpoint-remediation
```

Confirm the fixture can create and persist a blocked ticket independently of summary rendering.
The defect is the unresolved count, not a renamed status string.

## Use your host

Surface the finding through a checkpoint/review lane, then enter the fix lane for the confirmed
defect.

### Claude Code

```text
/ca:checkpoint
/ca:fix "Count blocked tickets as unresolved in the Workshop Queue summary"
```

### Codex

```text
$ca-checkpoint
$ca-fix "Count blocked tickets as unresolved in the Workshop Queue summary"
```

### Pi (Feature Forge preview)

Pi is the supported Feature Forge preview and requires project trust. The documented fallbacks are
`/skill:ca-checkpoint` and
`/skill:ca-fix "Count blocked tickets as unresolved in the Workshop Queue summary"`.

```text
/ca-checkpoint
/ca-fix "Count blocked tickets as unresolved in the Workshop Queue summary"
```

## Do the work

Exercise the real model/store/service path to show that a blocked ticket exists and is omitted from
the unresolved summary count. Run the checkpoint or review surface and inspect the resulting finding.
Commit the finding state so it identifies the real affected product/test boundary.

In a later commit, add an executable regression that constructs the real blocked ticket and expects
it in the unresolved count. Observe the meaningful RED result before repairing production code.
Make the smallest summary repair, run focused and full verification, and commit the GREEN result.

Write `.codearbiter/checkpoints/P05-academy.json` last. Record the exact earlier finding commit,
later remediation commit, affected repository-relative paths, and `remediated` status. Derive paths
from both Git diffs; the sets must have a nonempty intersection and every referenced path must have
changed in this attempt. Do not substitute copied terminal output or a JSON-only invented finding.

## Hints

### Hint 1

Create a blocked ticket through the normal domain and persistence interfaces, then query the summary.
If blocked state itself does not work, you have not isolated the prepared summary defect.

### Hint 2

Keep finding and repair commits distinct. Use `git diff-tree --name-only` on each commit and identify
the real shared path before drafting the report.

### Hint 3

The final report must point backward to commits strictly ordered after prepare. Recompute each ID and
path from Git immediately before committing the report last.

## Success evidence

The selected history proves genuine blocked-state behavior, a later observed summary finding, a
meaningfully failing regression, and a subsequent passing repair. The committed report names ordered
in-attempt commits and shared affected paths and is itself later than the remediation. Disjoint,
same-commit, synthetic, code-only, test-only, pre-prepare, or prose-only evidence fails.

```powershell
$learnerRepository = (Resolve-Path -LiteralPath '.').Path
arbiter-academy --repository $learnerRepository check P05-checkpoint-remediation
```

## Recovery

If IDs are out of range, finding and remediation are disjoint, or the report was committed too soon,
preserve the attempt and reset:

```powershell
$learnerRepository = (Resolve-Path -LiteralPath '.').Path
arbiter-academy --repository $learnerRepository reset P05-checkpoint-remediation
```

Do not edit identifiers in prose to disguise disconnected history.

## Next lab

Continue to **P06 — Recover from context drift without losing unrelated work** after P05 passes.
