---
id: F01-fork-clone-doctor
track: foundations
order: 1
title: Fork, clone, and doctor safety
outcome: Prove origin is your fork, upstream is the official Academy, and push routing cannot target upstream.
prerequisites: none
estimated_minutes: 30
scenario_command: python scripts/academy.py prepare F01-fork-clone-doctor
checkpoint_command: arbiter-academy --repository <learner-repository> check F01-fork-clone-doctor
next_lab: F02-orient-to-state
---

# F01 — Fork, clone, and Doctor safety

## Know before you begin

**No prior Academy lesson is required.** Complete [five Academy Home setup steps](../../index.html#complete-these-five-setup-steps-before-f01)
before Prepare. New here? Stop on this page until you have created
your personal GitHub fork, cloned that fork, installed Academy, [chosen and installed your CodeArbiter host](https://arbiterforge.github.io/codeArbiter/getting-started/choose-your-host/), and run Home Doctor in the clone.
An expected missing `upstream` finding proceeds to F01; this lesson repairs that boundary.
Those steps require Git 2.39 or newer, Python 3.11 or newer, and Claude Code, Codex, or Pi.

Work only in the `arbiter-academy` fork and clone you prepared from Home. A **fork** is the GitHub
copy you own. A **clone** is its local working copy. In that clone, `origin` must mean your fork and
`upstream` must mean the official `arbiterForge/arbiter-academy` repository. You fetch updates from
upstream, but this lesson makes pushing there fail locally.

Begin on a clean `main`: `clean` means the repository has no staged or unstaged changes. Keep the
Installed Academy commands available in a **Native terminal** for preparation, Doctor, Check, and Reset. Use that terminal for a
command you run directly. When a command appears for your Claude Code, Codex, or Pi **harness**, its
single leading `!` passes that shell command to the terminal. CodeArbiter commands never use `!`.

## What you will prove

You will create one numbered attempt, make push routing safe, pass both Doctors, and commit only the
bounded Doctor report through CodeArbiter. Then the externally installed Academy verifier will read
the committed report and current Git configuration before recording progress. It does not trust
code imported from this learner checkout.

The evidence report must decode to exactly these three values (formatting whitespace may differ):

`{"schema_version":1,"safe_for_push_labs":true,"effective_push_remote":"origin"}`

## Prepare safely

{{action:F01-prepare}}

The branch printed by Academy has the form `academy/F01-fork-clone-doctor/ATTEMPT_NUMBER`. Here,
`ATTEMPT_NUMBER` means the number Academy prints, such as `1`; it is not text you type literally.

{{action:F01-inspect-remotes}}

## Practice

Repair only the fact each action names, then inspect the result. Do not copy a guessed owner, remove
a remote to silence a diagnostic, or make the official repository a push destination.

{{action:F01-repair-origin}}

{{action:F01-set-upstream}}

{{action:F01-disable-upstream-push}}

{{action:F01-select-push-default}}

{{action:F01-host-doctor}}

{{action:F01-academy-doctor}}

Doctor failure forbids the evidence commit. Continue only after Host Doctor passes and Academy
Doctor creates `.codearbiter/reports/academy/F01-doctor.json` from the live repository state.

{{action:F01-inspect-report}}

{{action:F01-stage-report}}

{{action:F01-review-commit-boundary}}

{{action:F01-commit-report}}

{{action:F01-confirm-clean}}

## Recognize success

The Doctor report contains only `schema_version`, `safe_for_push_labs`, and
`effective_push_remote`. The evidence commit changes only
`.codearbiter/reports/academy/F01-doctor.json`. Immediately before Check, `git status --short`
prints nothing. No output is the expected successful result: the attempt is clean.

## Check

{{action:F01-check}}

A pass contains `checkpoint F01-fork-clone-doctor: passed; progress: .academy/progress.json`.
The progress record is written only after the external verifier independently reads the clean,
committed report and live Git configuration. A report by itself, a Host Doctor pass, or an Academy
Doctor pass does not complete the lesson.

## Recover or continue

If Check fails, preserve the clean committed attempt. Read the failed predicate, compare it with the
matching action's expected result and recovery, and change only that boundary. Check failure never
requires deleting the evidence commit.

### Hint 1

Start with `origin`, `upstream`, and `remote.pushDefault`. Name where each push would go before
changing it.

### Hint 2

Both the committed report and the current Git configuration must be safe. Regenerate the report
after changing a remote.

### Hint 3

If an attempt mixes unrelated files into the evidence commit, preserve it and use Reset. A new
numbered attempt is safer than rewriting evidence history.

{{action:F01-return-base}}

{{action:F01-reset-retry}}

After Check passes, return to `main` when you want to leave the completed attempt untouched. The next
Academy lesson appears on the course home only after its guided rewrite and acceptance evidence are
complete. Do not use unpublished source exercises as a substitute for the next guided lesson. Use Reset
only to preserve a failed attempt and prepare the next number.

## Understand the mechanism

The report is deliberately small and learner-controlled; it records no username, URL, credential,
email, local path, or terminal transcript. The verifier therefore checks two independent sources:
the exact report committed on the numbered branch and the live Git configuration at Check time.
Changing either after Doctor breaks the proof. Keeping preparation, the governed evidence commit,
clean state, and external verification separate makes the result reconstructable instead of merely
plausible.
