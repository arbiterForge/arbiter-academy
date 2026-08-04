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

# P08 — Classify repository hygiene without destructive cleanup

## Why this mechanism matters

Repository cleanup decisions require independent proof of clean state, merge containment, and unique
commit count. A remote `[gone]` marker or “merged” label is not enough. This exercise creates real
refs and worktrees and stores their path-free identities outside the learner checkout, making
deletion, omission, branch movement, or copied inventory detectable. The lab authorizes inspection,
classification, and safe recommendations only—never destructive cleanup.

## Start the scenario

Run this from the learner checkout. Preserved P02 verifier records require the installed command for
every later Practitioner transition, even though the original GitHub remotes are already restored.
Prepare the live local-ref fixture:

```powershell
$learnerRepository = (Resolve-Path -LiteralPath '.').Path
arbiter-academy --repository $learnerRepository prepare P08-repository-hygiene
```

Preparation creates a clean merged branch, a dirty unmerged worktree, the current attempt branch,
and an unmerged branch with unique commits. It does not provide a learner-visible precomputed list.

## Use your host

Invoke standup to inspect the live repository. Decline or stop before any destructive suggestion;
this lab is classification-only.

### Claude Code

```text
/ca:standup
```

### Codex

```text
$ca-standup
```

### Pi (Feature Forge preview)

Pi is the supported Feature Forge preview and requires project trust. Its documented fallback is
`/skill:ca-standup`.

```text
/ca-standup
```

## Do the work

Enumerate the complete live local ref and worktree sets from Git. For every relevant branch, record
its full ref and object ID, whether its worktree is clean or dirty, whether its tip is contained in
the selected base, and the exact count of commits unique to it. For each worktree, record the
path-free prepared identity plus branch/HEAD binding and presence—not an absolute local path.

Write `.codearbiter/reports/academy/P08-hygiene.json` with the complete canonical snapshot and a
classification/recommendation for every prepared identity. A clean merged branch with zero unique
commits may be a future cleanup candidate; dirty, current-attempt, unmerged, or unique-history state
must be preserved. Commit the report without moving or deleting any ref/worktree and without
running prune, force, or cleanup commands.

## Hints

### Hint 1

Start with the complete `for-each-ref` and `worktree list --porcelain` views. Classifying one branch
before freezing the full live set makes omissions easy.

### Hint 2

Evaluate worktree dirtiness, merge-base ancestry, and `rev-list` uniqueness separately. A branch can
be merged yet still unsafe to remove because its worktree is dirty or its identity moved.

### Hint 3

Before committing, re-enumerate the live state and compare every external prepared identity. There
must be no missing, extra, rebound, moved, or deleted ref/worktree.

## Success evidence

The committed snapshot exactly matches the externally recorded live refs and path-free worktree
identities. Each classification is recomputed from current clean/dirty state, merge containment,
and unique commits, and all prepared objects remain present and correctly bound. Omitted/extra
items, stale or copied classifications, merge-only claims, deletion, pruning, force operations, or
absolute local paths fail.

```powershell
$learnerRepository = (Resolve-Path -LiteralPath '.').Path
arbiter-academy --repository $learnerRepository check P08-repository-hygiene
```

## Recovery

If the inventory is incomplete, a classification is stale, or a worktree becomes dirty, preserve
all refs/worktrees and reset through the scenario mechanism only:

```powershell
$learnerRepository = (Resolve-Path -LiteralPath '.').Path
arbiter-academy --repository $learnerRepository reset P08-repository-hygiene
```

Do not delete branches, remove worktrees, prune metadata, or force an operation to make the report
look correct.

## Next lab

Continue to **U01 — Autonomous sprint** in the Power User track after P08 passes. Power User source
guides are not authored by this Practitioner cell.
