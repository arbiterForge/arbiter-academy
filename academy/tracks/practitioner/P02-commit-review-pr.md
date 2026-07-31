---
id: P02-commit-review-pr
track: practitioner
order: 2
title: Review commit push and offline local PR receipt
outcome: Review and resolve a bounded change, commit it, push only to the prepared learner origin, and bind the exact range in an offline-local receipt commit.
prerequisites: P01-feature-through-plan
estimated_minutes: 40
scenario_command: arbiter-academy --repository <learner-repository> prepare P02-commit-review-pr
checkpoint_command: arbiter-academy --repository <learner-repository> check P02-commit-review-pr
next_lab: P03-record-an-adr
---

# P02 — Review, commit, push, and record an offline local PR receipt

## Why this mechanism matters

Review, commit, push, and receipt creation are distinct ordered facts. This hermetic exercise uses
real local bare repositories while preserving learner/official roles, so it can prove the Git
relationships offline without pretending a GitHub pull request exists. Task 11 owns hosted fork,
pull-request, and hosted-check proof. The receipt's cleared review field is evidence bound to the
verified range; it is not executable attestation that a particular review command ran.

## Start the scenario

P02 preparation changes remotes, so run the installed external command from outside the learner
checkout and explicitly select it:

```powershell
arbiter-academy --repository <learner-repository> prepare P02-commit-review-pr
```

Preparation first validates and privately records the credential-free original GitHub-shaped
topology. It then installs sidecar-owned bare repositories as learner `origin` and official-shaped
`upstream`. Stop if preparation rejects the topology; do not hand-edit around that safety check.

## Use your host

Review the uncommitted P01-compatible change, resolve blocking findings, and only then enter the
sanctioned commit gate.

### Claude Code

```text
/ca:review
/ca:commit "feat(queue): include unresolved tickets in summary"
```

### Codex

```text
$ca-review
$ca-commit "feat(queue): include unresolved tickets in summary"
```

### Pi (Feature Forge preview)

Pi is the supported Feature Forge preview and requires project trust. The documented fallbacks are
`/skill:ca-review` and `/skill:ca-commit "feat(queue): include unresolved tickets in summary"`.

```text
/ca-review
/ca-commit "feat(queue): include unresolved tickets in summary"
```

## Do the work

Inspect `git remote -v` and the effective push URLs. Confirm `origin` is the prepared learner bare
repository and `upstream` is the prepared official-shaped bare repository. Review the uncommitted
change, resolve every blocking finding, and rerun review until clear. Then use the sanctioned commit
gate to create the work commit.

Determine the prepared base and ordered `prepared_base..work_head` range from Git. Push the current
attempt branch explicitly to `origin`; never push it to `upstream`. Confirm the origin branch tip is
the work head and upstream has no corresponding attempt ref.

Create `.codearbiter/reports/academy/P02-pr-receipt.json` with `mode: offline-local`, the path-free
prepared repository identities and learner/official roles, exact attempt branch, prepared base,
work head, pushed tip, ordered commit range, receipt-bound cleared review status, and
`pr_reference: local-pr:<first-12-characters-of-work-head>`. Commit only that receipt after the
push. Its sole parent must be the work head. Do not include local paths, remote URLs, credentials,
email, or a GitHub-shaped PR claim.

## Hints

### Hint 1

Use `git remote get-url --all` and `git remote get-url --push --all` before review or push. The
prepared sidecar identities—not a familiar remote name—establish each role.

### Hint 2

Keep the ordering visible: cleared review, sanctioned work commit, origin push, then one-path receipt
commit. A receipt cannot retroactively make a pre-review commit governed.

### Hint 3

Derive the commit list with `git rev-list --reverse <prepared-base>..<work-head>` and inspect the
bare remote refs. The pushed tip and work head must match exactly; the receipt commit comes later.

## Success evidence

The verifier-held sidecar state matches the current local remote configuration and roles. Git shows
reviewed work committed before push, only the learner origin gaining the attempt ref, an exact
ordered work range, and a later one-path offline-local receipt whose parent is the work head. The
receipt review status is evaluated only in that verified relationship. No hosted PR is claimed.

```powershell
arbiter-academy --repository <learner-repository> check P02-commit-review-pr
```

## Recovery

Run reset only while the current fetch/push configuration still matches the prepared sidecar
topology exactly:

```powershell
python scripts/academy.py reset P02-commit-review-pr
```

On an exact match, reset can archive the attempt and restore the recorded original topology. On any
mismatch it fails closed and preserves remotes, branches, and work for recovery. Do not delete refs,
rewrite remotes, or force-push.

## Next lab

Continue to **P03 — Record an accepted ADR**. Its preparation independently revalidates restored
fork safety before changing scenario state.
