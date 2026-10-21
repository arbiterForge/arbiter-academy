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

Trace how an untrusted archive path could escape its destination. Use STRIDE to examine threats and controls at that actual boundary before requesting implementation.

P07 is a public guided and runnable Academy lesson in this preview. It is opt-in and read-only.
Start in the Academy clone that completed P06. Switch to `main`, then confirm `git status --short` has
no output before Prepare.

Keep a native terminal at the clone root and one codeArbiter harness open at that same clone. Native
terminal commands go directly into the terminal and never begin with `!`. Harness-shell commands,
when a lesson uses them, begin with exactly one `!`. This lesson uses no harness-shell commands.
codeArbiter commands and agent messages are entered in the selected harness and never begin with `!`.

The proposed feature is an archive importer that would reuse `academy_engine/paths.py`. Trace untrusted archive-member input through the repository-root boundary to a destination write. Existing code supports claims about present controls; the exercise reviews the proposed design. Use a security reviewer for an audit of code already implemented.

## What you will prove

You will commit one learner-owned Academy report after Prepare at `.codearbiter/reports/academy/P07-threat-model.md`.
The report summarizes the read-only advisory analysis in three analysis sections followed by a separate Academy target identity
binding. The target stays byte-identical from the prepared commit to the final commit.

The current verdicts are `PROCEED` (no open gap), `PROCEED-WITH-CONSTRAINTS` (named gaps and owners), and `STOP` (a critical, exploitable, unmitigated threat). None authorizes a code change.

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

The learner-owned report must be strict UTF-8 with LF line endings and one final newline. Keep it at or below 12
KiB. Its analysis sections are Surface, Threats, and Verdict. Surface identifies the proposed flow, controlled input, repository-root boundary, and containment before write.

The native skill returns advisory analysis. For the learner-owned Academy record, summarize it in a six-row table, one row per STRIDE category, using columns Threat, Category, Likelihood, Impact, Control. Use H/M/L ratings and `PRESENT:`, `PLANNED:`, `GAP:`, or justified `N/A:` control descriptions. Put gaps first rather than sorting by category. This table is an Academy exercise format, not a required native output template.

Use concrete controls in the report: keep destination resolution under the selected repository root
before creating or copying a file. Reject absolute, traversal, symlink, and Windows reparse-point
ancestors in archive destinations. Fail closed on a different drive or an unrepresentable containment
path before any write.

The next learner request creates the report from the advisory analysis and prepared scenario values, validates its binding, stages only that report, and stops for your review before the commit gate.

{{action:P07-write-binding}}

After Verdict, add `## Academy Target-SHA256/identity binding` with the exact target path, prepared
blob, head blob, and SHA-256 values from the prepared scenario. Do not mix `Academy-Target-` labels
into analysis sections. Do not add a secret, a generic governance event, another changed path, or a
claim that a host command was invoked.

{{action:P07-commit-report}}

{{action:P07-inspect-commit}}

## Recognize success

The final branch has one report-only commit after Prepare. The report has the three analysis sections
in order, the separate Academy Target-SHA256/identity binding, and a permitted advisory Verdict.
The final target object and raw SHA-256 match the prepared target. `git status --short` is empty.

## Check

{{action:P07-check}}

Check proves the committed report grammar and bytes, prepared and final target identity, allowed Git
ordering, report-only path scope, and clean final worktree. It does not prove that a host command was
invoked. It does not prove that the agent drafted first. It does not prove that you reviewed the
draft. It does not prove the review happened in any particular order. Those are learner and team
practices, not final-state facts that this verifier can authenticate.

## Recover or continue

If Surface is generic, STRIDE rows are missing or duplicated, Academy labels mix into analysis fields, a target value
is stale, the target changed, or Check names a failed predicate, preserve the attempt. Do not amend,
rebase, force-reset, or alter `academy_engine/paths.py` to fit an old digest.

**Hint 1.** Trace one untrusted archive-member or overlay-destination value from normalization through resolved
containment to the extraction root. State what the code must establish before it creates or copies a
destination.

**Hint 2.** The Threat cells need real outcomes. A row that only says "Tampering" does not say what an attacker
can change or which containment failure would permit it.

**Hint 3.** Academy target identity is verifier evidence, not native threat-model prose. Keep it after Verdict
and copy the prepared values exactly. A passing Check does not turn this review into authorization to
implement controls.

{{action:P07-reset}}

After Check passes, leave the completed branch intact and continue to P08. Do not substitute
unpublished source exercises for a released lesson.

## Understand the mechanism

`$ca-threat-model` is read-only advisory analysis: it writes no report. Threat modeling connects an untrusted input to a concrete boundary, then the learner-owned Academy record preserves threats and controls that matter at that boundary. STRIDE supplies coverage categories, not a substitute for specific reasoning. The Academy binding freezes which source bytes were reviewed without pretending it proves the live conversation, command invocation, or implementation authority.

**Use this in your own project.** Threat-model a concrete flow: input, trust boundary, sensitive operation, failure outcome, and control. Ask which controls already exist and which still need work. An advisory verdict is not permission to expand the task or a claim that the controls were implemented.
