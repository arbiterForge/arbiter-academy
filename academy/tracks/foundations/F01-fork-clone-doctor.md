---
id: F01-fork-clone-doctor
track: foundations
order: 1
title: Fork, clone, and doctor safety
outcome: Prove origin is your fork, upstream is the official Academy, and push routing cannot target upstream.
prerequisites: none
estimated_minutes: 20
scenario_command: python scripts/academy.py prepare F01-fork-clone-doctor
checkpoint_command: arbiter-academy --repository <learner-repository> check F01-fork-clone-doctor
next_lab: F02-orient-to-state
---

# F01 — Fork, clone, and doctor safety

## Why this mechanism matters

Training should be safe to abandon, repeat, and publish in your own fork. Git remote names are not
cosmetic: `origin` is where an ordinary push goes, while `upstream` is the source you update from.
This lab makes that routing visible and disables pushes to the official Academy repository. Offline
checks can prove URL shape and routing; they cannot prove GitHub fork lineage.

## Start the scenario

Fork `arbiterForge/arbiter-academy` on GitHub, clone **your fork**, and enter the clone. Before
preparation, `origin` must already be a non-official GitHub repository named `arbiter-academy` whose
push URL resolves to the same owner/repository. `upstream` may still be absent or wrong; fixing and
verifying it is the exercise.

```powershell
python scripts/academy.py prepare F01-fork-clone-doctor
```

Preparation creates `academy/F01-fork-clone-doctor/1` (or the next unused number) and commits the
scenario marker. Inspect the real state rather than editing the marker:

```powershell
git remote -v
git config --get remote.pushDefault
git branch --show-current
```

## Use your host

All host commands require enabled repository state. They inspect the same checkout; they do not
replace the independent Academy checkpoint.

### Claude Code

```text
/ca:doctor
```

### Codex

```text
$ca-doctor
```

### Pi (Feature Forge preview)

Pi is the supported Feature Forge preview and requires project trust before project skills load.
If direct dispatch is unavailable, use the documented `/skill:ca-doctor` fallback.

```text
/ca-doctor
```

## Do the work

Reconcile the two remotes from what `git remote -v` actually reports:

```powershell
git remote set-url origin https://github.com/<your-owner>/arbiter-academy.git
git remote add upstream https://github.com/arbiterForge/arbiter-academy.git
git remote set-url --push upstream DISABLED
git config remote.pushDefault origin
```

If `upstream` already exists, use `git remote set-url upstream ...` instead of `add`. Re-run the host
doctor, then ask the Academy doctor to recompute and record its bounded three-field observation:

```powershell
python scripts/academy.py doctor F01-fork-clone-doctor
git add .codearbiter/reports/academy/F01-doctor.json
git commit -m "academy: record fork-safe doctor result"
```

The report contains no remote URL, username, email, credential, local path, or raw terminal output.
It is learner-controlled input; the external verifier independently reads live Git configuration.

## Hints

### Hint 1

Start with the doctor issues and `git remote -v`. Do not change a URL until you can name the mismatch.

### Hint 2

Compare both fetch and push URLs. `origin` must identify your owner and `arbiter-academy`; every
`upstream` fetch URL must identify `arbiterForge/arbiter-academy`, and upstream push must be `DISABLED`.

### Hint 3

Restore `origin` to your fork, set the official `upstream`, disable upstream push, and make the
current branch resolve pushes through `origin`; then regenerate the doctor report.

## Success evidence

On the numbered F01 attempt branch, a learner commit changes
`.codearbiter/reports/academy/F01-doctor.json` to schema version 1 with
`safe_for_push_labs: true` and `effective_push_remote: "origin"`. The worktree is clean, and the
external verifier accepts the report only while the live remote configuration remains safe.

Run the authoritative check from the externally installed package:

```powershell
arbiter-academy --repository <learner-repository> check F01-fork-clone-doctor
```

## Recovery

Return to a clean F01 attempt branch, then preserve it and create a retry:

```powershell
python scripts/academy.py reset F01-fork-clone-doctor
```

Reset archives the old ref and prepares a new numbered attempt. Do not delete remotes, erase the old
branch, force-reset, or force-push to make diagnostics disappear.

## Next lab

Continue to **F02 — Orient to live governance state** after the external checkpoint passes.
