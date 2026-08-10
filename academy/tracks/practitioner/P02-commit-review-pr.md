---
id: P02-commit-review-pr
track: practitioner
order: 2
title: Review commit push and offline local PR receipt
outcome: Review and resolve a bounded change, commit it, push only to the prepared learner origin, and bind the exact range in an offline-local receipt commit.
prerequisites: P01-feature-through-plan
estimated_minutes: 60
scenario_command: arbiter-academy --repository <learner-repository> prepare P02-commit-review-pr
checkpoint_command: arbiter-academy --repository <learner-repository> check P02-commit-review-pr
next_lab: P03-record-an-adr
---

# P02 — Review, commit, push, and record an offline local PR receipt

## Why this mechanism matters

Review, commit, push, and receipt creation are separate, ordered facts. This lab uses real local bare
repositories so you can practice the entire relationship without risking a push to somebody else's
repository. It does not pretend that a hosted pull request exists; Task 11 audits the graduation
contract and validates that separate hosted path.

Preparation temporarily routes the learner checkout's `origin` and `upstream` to verifier-owned local
repositories. Their `file:` URLs are visible in `.git/config` and `git remote -v` while the exercise is
active. The logical repository IDs printed below are the logical receipt identities; they are not the temporary `file:` URLs
or physical storage locations.

## Start the scenario

Follow this workflow from top to bottom. Preparation begins outside the learner checkout so the
external verifier-state boundary is explicit before repository-local work starts.

### 1. Prepare outside the learner checkout and capture its identity

Open PowerShell in a directory that is not inside the learner repository. Replace the placeholder in
the first line, then run this block unchanged. It refuses malformed output before any later command
can accidentally bind the wrong branch, commit, or sidecar identity.

```powershell
$learnerRepository = (Resolve-Path -LiteralPath '<learner-repository>').Path
$prepareOutput = @(arbiter-academy --repository $learnerRepository prepare P02-commit-review-pr)
$prepareOutput | ForEach-Object { Write-Host $_ }

if ($prepareOutput.Count -ne 3) { throw 'P02 preparation returned unexpected output' }
$preparedMatch = [regex]::Match($prepareOutput[0], '^Academy prepared: (?<branch>academy/P02-commit-review-pr/(?<attempt>[1-9]|[12][0-9]|3[0-2])) at (?<commit>[0-9a-f]{40}|[0-9a-f]{64})$')
$originMatch = [regex]::Match($prepareOutput[1], '^Origin repository ID: (?<id>[0-9a-f]{64})$')
$upstreamMatch = [regex]::Match($prepareOutput[2], '^Upstream repository ID: (?<id>[0-9a-f]{64})$')
if (-not $preparedMatch.Success -or -not $originMatch.Success -or -not $upstreamMatch.Success) {
  throw 'P02 preparation identity is malformed'
}

$branch = $preparedMatch.Groups['branch'].Value
$attempt = [int]$preparedMatch.Groups['attempt'].Value
$preparedCommit = $preparedMatch.Groups['commit'].Value
$originRepositoryId = $originMatch.Groups['id'].Value
$upstreamRepositoryId = $upstreamMatch.Groups['id'].Value
```

The three lines you just captured have this shape:

```text
Academy prepared: academy/P02-commit-review-pr/1 at <prepared-commit>
Origin repository ID: <64hex>
Upstream repository ID: <64hex>
```

### 2. Enter the learner checkout and prove the starting point

The preparation command owns external verifier state, but `$ca-*` and Git commands act on the current
repository. `Set-Location` is therefore a real safety boundary, not cosmetic navigation. Do not run a
review or commit command until both guards pass.

```powershell
Set-Location -LiteralPath $learnerRepository
if ((git branch --show-current) -ne $branch) { throw 'current branch is not the prepared P02 branch' }
if ((git rev-parse HEAD) -ne $preparedCommit) { throw 'P02 prepared range no longer starts at the printed commit' }
git status --short
git remote -v
```

## 60-minute pacing guide

| Phase | Typical time |
|---|---:|
| Prepare, capture the identity, and pass both starting guards | 10 minutes |
| Review the two-path work change and clear findings | 15 minutes |
| Run the first bounded gate and create the work commit | 10 minutes |
| Push only to origin and build the exact receipt | 10 minutes |
| Run the second bounded gate and create the receipt-only commit | 10 minutes |
| Run the installed checkpoint and inspect the result | 5 minutes |

Preparation commits an attempt-local `.codearbiter/tech-stack.md` so both sanctioned commit gates stay
bounded to the Workshop Queue exercise. The gate runs these commands:

```sh
python -m unittest tests.test_cli -v
python -m compileall -q workshop_queue tests/test_cli.py
python scripts/scan_secrets.py --staged
```

These commands intentionally exclude the Academy verifier's long acceptance matrices; the installed
checkpoint still recomputes the full P02 evidence after both commits. Academy main keeps the full
release verification profile for maintainer acceptance and release work. Reset returns you to that
main profile, while the archived attempt retains the bounded profile that governed its two commits.

## Use your host

**3. Use exactly one host lane for review and the work commit.**

Stage only the two exercise paths, prove that exact staged set, inspect the change, clear every
blocking finding, and use the sanctioned commit path. The commit command intentionally has no
message argument: the sanctioned lane owns its commit interface.
Choose the block for the host you are actually using; do not run all three.

```powershell
git add -- tests/test_cli.py workshop_queue/cli.py
$stagedWorkPaths = @(git diff --cached --name-only)
if (($stagedWorkPaths -join "`n") -ne "tests/test_cli.py`nworkshop_queue/cli.py") {
  throw 'P02 work commit must stage exactly tests/test_cli.py and workshop_queue/cli.py'
}
```

### Claude Code

```text
/ca:review
/ca:commit
```

### Codex

```text
$ca-review
$ca-commit
```

### Pi (Feature Forge preview)

Pi requires project trust. Its documented fallbacks are `/skill:ca-review` and
`/skill:ca-commit`.

```text
/ca-review
/ca-commit
```

## Do the work

### 4. Freeze the nonempty reviewed range, push only origin, and verify both roles

Return to PowerShell after the sanctioned work commit. A zero-length range means the ordering was
broken; stop rather than manufacturing a receipt.

```powershell
$workHead = git rev-parse HEAD
$commits = @(git rev-list --reverse "$preparedCommit..$workHead")
if ($workHead -eq $preparedCommit -or $commits.Count -lt 1) {
  throw 'P02 requires at least one reviewed work commit after the prepared commit'
}

git push origin "HEAD:refs/heads/$branch"
$originResult = @(git ls-remote origin "refs/heads/$branch")
$upstreamResult = @(git ls-remote upstream "refs/heads/$branch")
if ($originResult.Count -ne 1 -or $originResult[0].Split()[0] -ne $workHead) {
  throw 'origin attempt ref does not equal the work head'
}
if ($upstreamResult.Count -ne 0) {
  throw 'upstream unexpectedly contains the attempt ref'
}
```

### 5. Write and stage the exact offline receipt

The receipt says the review is cleared and binds that declaration to a graph the verifier can
recompute. It contains no path, URL, credential, email, hosted check, or GitHub pull-request claim.

```powershell
$receipt = [ordered]@{
  schema_version = 1
  mode = 'offline-local'
  lab_id = 'P02-commit-review-pr'
  attempt = $attempt
  branch = $branch
  prepared_commit = $preparedCommit
  work_head = $workHead
  pushed_tip = $workHead
  commits = $commits
  review = [ordered]@{ status = 'cleared' }
  repositories = [ordered]@{
    origin = [ordered]@{ repository_id = $originRepositoryId; role = 'learner' }
    upstream = [ordered]@{ repository_id = $upstreamRepositoryId; role = 'official' }
  }
  pr_reference = "local-pr:$($workHead.Substring(0, 12))"
}
$receiptPath = Join-Path $learnerRepository '.codearbiter/reports/academy/P02-pr-receipt.json'
[IO.Directory]::CreateDirectory((Split-Path $receiptPath)) | Out-Null
[IO.File]::WriteAllText($receiptPath, (($receipt | ConvertTo-Json -Depth 5) + "`n"), [Text.UTF8Encoding]::new($false))
git add -- .codearbiter/reports/academy/P02-pr-receipt.json
$stagedReceiptPaths = @(git diff --cached --name-only)
if (($stagedReceiptPaths -join "`n") -ne '.codearbiter/reports/academy/P02-pr-receipt.json') {
  throw 'P02 receipt commit must stage only the receipt path'
}
```

### 6. Use the same host for the second, receipt-only sanctioned commit

Choose exactly one block. This commit must have the work head as its sole parent and change only the
receipt path.

### Claude Code receipt commit

```text
/ca:commit
```

### Codex receipt commit

```text
$ca-commit
```

### Pi receipt commit

```text
/ca-commit
```

### 7. Ask the installed verifier to recompute the evidence

```powershell
arbiter-academy --repository $learnerRepository check P02-commit-review-pr
```

Passing means the work range exactly produces the prepared patch, origin alone has the attempt ref,
upstream retains its prepared identity, and the final commit contains only the matching receipt.

## Hints

### Hint 1

If a guard fails, compare the printed branch and prepared commit with `git branch --show-current` and
`git rev-parse HEAD`. Do not continue from a different checkout.

### Hint 2

Keep the ordering visible: capture preparation identity, enter the checkout, clear review, create the
work commit, push origin, then create one receipt-only commit.

### Hint 3

Use `git rev-list --reverse "$preparedCommit..$workHead"` to inspect the range and `git ls-remote`
against each role. The receipt commit is deliberately outside that work range.

## Success evidence

The learner has a nonempty reviewed work range after the prepared commit; only the learner origin has
the attempt ref at the work head; the official upstream has no attempt ref; and a later one-path
receipt commit binds the exact ordered range, roles, logical repository IDs, and cleared status.

## Recovery

Run reset only while the current fetch/push configuration still matches the prepared sidecar topology:

```powershell
arbiter-academy --repository $learnerRepository reset P02-commit-review-pr
```

On an exact match, reset archives the attempt and restores the original GitHub-shaped topology. On a
mismatch it fails closed and preserves remotes, refs, and learner work. Do not rewrite remotes, delete
refs, or force-push around it.

## Next lab

Continue to **P03 — Record an accepted ADR** after reset or later-lab preparation restores P02.
