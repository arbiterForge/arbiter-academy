---
id: P07-threat-model
track: practitioner
order: 7
title: Threat-model the path-handling boundary
outcome: Produce one committed, target-bound STRIDE report for archive-import containment without changing the reviewed code.
prerequisites: P06-context-drift-recovery
estimated_minutes: 35
scenario_command: arbiter-academy --repository <learner-repository> prepare P07-threat-model
checkpoint_command: arbiter-academy --repository <learner-repository> check P07-threat-model
next_lab: P08-repository-hygiene
---

# P07 - Threat-model the path-handling boundary

## Know before you begin

P07 is a public guided and runnable Academy lesson in this preview. It is opt-in and read-only.
Start in the Academy clone that completed P06. Switch to `main`, then confirm `git status --short` has
no output before Prepare.

Keep a native terminal at the clone root and one CodeArbiter harness open at that same clone. Native
terminal commands go directly into the terminal and never begin with `!`. Harness-shell commands,
when a lesson uses them, begin with exactly one `!`. This lesson uses no harness-shell commands.
CodeArbiter commands and agent messages are entered in the selected harness and never begin with `!`.

The bounded target is `academy_engine/paths.py`. It handles learner-controlled archive-member or
overlay-destination input beneath the selected repository root. P07 checks containment or rejection
before a destination write. It does not edit the target.

## What you will prove

You will commit one report after Prepare at `.codearbiter/reports/academy/P07-threat-model.md`.
The report has four native threat-model sections followed by a separate Academy target identity
binding. The target stays byte-identical from the prepared commit to the final commit.

The report can use either `CLEAR TO IMPLEMENT` or `BLOCKED - resolve findings first`. Neither
clearance outcome authorizes a P07 code change. Both are advisory conclusions from the review.

## Prepare safely

{{action:P07-read-boundary}}

{{action:P07-prepare}}

{{action:P07-read-target}}

Preparation materializes the frozen scenario descriptor for this attempt. The installed verifier later recomputes
the target identity from committed Git objects; it does not trust a copied value from the report.

`ATTEMPT_NUMBER` is the number Academy prints, such as `1`; do not type it literally. Stay on the
numbered P07 branch until Check or Reset tells you otherwise.

## Practice

{{action:P07-request-draft}}

{{action:P07-review-model}}

The report must be strict UTF-8 with LF line endings and one final newline. Keep it at or below 12
KiB. Native sections are Scope, STRIDE findings, Recommended controls before implementation, and
Clearance, in that order. Scope must name controlled input, repository-root boundary, and containment
or rejection before write. STRIDE findings need six distinct, concrete threats in S, T, R, I, D, E
order. Each row needs likelihood, impact, and a `PRESENT:`, `PLANNED:`, `GAP:`, or justified `N/A:`
control.

Use concrete controls in the report: keep destination resolution under the selected repository root
before creating or copying a file. Reject absolute, traversal, symlink, and Windows reparse-point
ancestors in archive destinations. Fail closed on a different drive or an unrepresentable containment
path before any write.

{{action:P07-write-binding}}

After Clearance, add `## Academy Target-SHA256/identity binding` with the exact target path, prepared
blob, head blob, and SHA-256 values from the prepared scenario. Do not mix `Academy-Target-` labels
into native sections. Do not add a secret, a generic governance event, another changed path, or a
claim that a host command was invoked.

{{action:P07-commit-report}}

{{action:P07-inspect-commit}}

## Recognize success

The final branch has one report-only commit after Prepare. The report has the four native sections
in order, the separate Academy Target-SHA256/identity binding, and a permitted advisory Clearance.
The final target object and raw SHA-256 match the prepared target. `git status --short` is empty.

## Check

{{action:P07-check}}

Check proves the committed report grammar and bytes, prepared and final target identity, allowed Git
ordering, report-only path scope, and clean final worktree. It does not prove that a host command was
invoked. It does not prove that the agent drafted first. It does not prove that you reviewed the
draft. It does not prove the review happened in any particular order. Those are learner and team
practices, not final-state facts that this verifier can authenticate.

## Recover or continue

If Scope is generic, STRIDE rows are reordered, Academy labels mix into native fields, a target value
is stale, the target changed, or Check names a failed predicate, preserve the attempt. Do not amend,
rebase, force-reset, or alter `academy_engine/paths.py` to fit an old digest.

**Hint 1.** Trace one untrusted archive-member or overlay-destination value from normalization through resolved
containment to the extraction root. State what the code must establish before it creates or copies a
destination.

**Hint 2.** The Threat cells need real outcomes. A row that only says "Tampering" does not say what an attacker
can change or which containment failure would permit it.

**Hint 3.** Academy target identity is verifier evidence, not native threat-model prose. Keep it after Clearance
and copy the prepared values exactly. A passing Check does not turn this review into authorization to
implement controls.

{{action:P07-reset}}

After Check passes, leave the completed branch intact and continue to P08. Do not substitute
unpublished source exercises for a released lesson.

## Understand the mechanism

Threat modeling connects an untrusted input to a concrete boundary, then records threats and controls
that matter at that boundary. STRIDE supplies coverage categories, not a substitute for specific
reasoning. The Academy binding freezes which source bytes were reviewed. It makes the report auditable
without pretending it proves the live conversation or permits implementation.
