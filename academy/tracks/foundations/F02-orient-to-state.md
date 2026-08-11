---
id: F02-orient-to-state
track: foundations
order: 2
title: Orient to live governance state
outcome: Bind a compact orientation record to the exact current context bytes and project stage.
prerequisites: F01-fork-clone-doctor
estimated_minutes: 25
scenario_command: arbiter-academy --repository . prepare F02-orient-to-state
checkpoint_command: arbiter-academy --repository . check F02-orient-to-state
next_lab: F03-work-the-board
---

# F02 — Orient to live governance state

## Know before you begin

Complete F01 first and begin from the same arbiter-academy fork and clone. Before Prepare, switch
to `main` and confirm the clone is clean. Keep two surfaces open at the repository root: a native
terminal for installed Academy and shell commands, and your Claude Code, Codex, or Pi harness for
CodeArbiter commands and learner approvals.

This page labels every command with its actor and surface. A native-terminal command is entered
directly in PowerShell or your shell and therefore has no `!`. A harness shell command begins with
exactly one `!`. A CodeArbiter command is handled by the active harness and never begins with `!`.
You do not need to know how to construct JSON, calculate a digest, or choose a Git commit boundary
before starting; the actions below provide those exact steps.

## What you will prove

You will read the live repository state from its tracked source, follow the source links, and bind
one four-field orientation report to the exact context bytes you inspected. The evidence report
contains only `schema_version`, `context_path`, `context_sha256`, and `stage`. You will stage only
that report, approve only that boundary, let CodeArbiter commit it, and pass the external Academy
Check with no uncommitted work.

The status screen helps you navigate. It is not the evidence source. The tracked
`.codearbiter/CONTEXT.md` bytes and the files linked from that document are the source.

## Prepare safely

{{action:F02-prepare}}

`ATTEMPT_NUMBER` in a branch name means the number Academy prints, such as `1`. Do not type the
words or angle brackets literally. Stay on that numbered branch until Check passes.

{{action:F02-run-status}}

## Practice

Compare the Status summary with the tracked files instead of accepting either from memory.

{{action:F02-read-context}}

{{action:F02-follow-context-links}}

The linked sources answer different questions: specifications and plans define intended work,
ADRs preserve architecture choices, standards and security controls constrain changes, and the
task and question boards show work that is still open.

{{action:F02-hash-context}}

{{action:F02-write-orientation}}

The creation action reads one byte snapshot and derives both `stage` and `context_sha256` from it.
That prevents a digest copied from one version of the file being paired with a stage copied from
another. The report must not contain your username, local path, email, remote URL, credential, or
terminal transcript.

{{action:F02-inspect-orientation}}

{{action:F02-stage-orientation}}

{{action:F02-review-commit-boundary}}

{{action:F02-run-commit-gate}}

{{action:F02-confirm-clean}}

## Recognize success

The attempt contains exactly one learner commit after Prepare. That commit adds only
`.codearbiter/reports/academy/F02-orientation.json`. The tracked context at the attempt head is
byte-for-byte identical to the context at Prepare, the report has exactly four fields, and
`git status --short` prints nothing.

The digest is not a secret and does not summarize the text for a human. It is a reproducible claim:
someone else can hash the preserved context bytes and prove that they are the same bytes you read.

## Check

{{action:F02-check}}

A pass contains `checkpoint F02-orient-to-state: passed; progress: .academy/progress.json`.
Check reads the committed report, the prepared and current context blobs, the commit path list, and
the live worktree. A correct-looking uncommitted file does not pass, and neither does a report
committed beside another file.

## Recover or continue

If Check fails, preserve the attempt and read the failed predicate. A wrong field, changed context,
extra commit path, additional learner commit, or dirty worktree has a different recovery. Do not
hide the evidence by force-resetting or amending it; use a numbered retry when the attempt boundary
is no longer exact.

### Hint 1

Start with the `arbiter` and `stage` front-matter fields, then read the project identity, scope, and
every linked governing artifact.

### Hint 2

Hash `.codearbiter/CONTEXT.md` as bytes. Do not hash copied Status output, rendered website prose,
or text saved through an editor.

### Hint 3

The final commit changes one path. If anything else is staged, committed, or left uncommitted, stop
before Check and preserve that state for recovery.

{{action:F02-return-base}}

{{action:F02-reset-retry}}

After Check passes, return to `main` and keep the completed attempt branch intact. Continue to F03
only when it is published as a guided Academy lesson. An Academy lesson appears on the course home only after its guided rewrite; unpublished source exercises are not a substitute for the accepted course.

## Understand the mechanism

Status is advisory orientation generated for the current host. The repository files are durable
state. The report connects those layers without copying a transcript: its canonical path tells the
verifier what was read, its raw-byte digest identifies the exact version, and its integer stage
records the active maturity boundary.

The verifier also protects the shape of the attempt. It compares the prepared context blob with the
attempt head, requires one post-Prepare learner commit containing only the report, and requires a
clean worktree. That makes the lesson reconstructable later: the claim, source bytes, commit
boundary, and external verdict all agree.
