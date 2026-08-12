---
id: P03-record-an-adr
track: practitioner
order: 3
title: Record an accepted ADR
outcome: Choose and record the Workshop Queue summary-format boundary in accepted ADR-0004 and its matching append-only decision-log entry.
prerequisites: P02-commit-review-pr
estimated_minutes: 35
scenario_command: arbiter-academy --repository <learner-repository> prepare P03-record-an-adr
checkpoint_command: arbiter-academy --repository <learner-repository> check P03-record-an-adr
next_lab: P04-review-a-dependency
---

# P03 - Record an accepted ADR

## Know before you begin

P03 is a public guided and runnable lesson in Preview 0.11 (`preview-0.11`). It uses the shared Markdown-plus-action-manifest renderer and the installed Preview 0.11 Prepare, Check, and Reset commands. The immutable scenario, checkpoint, and action contract ID stay `P03-record-an-adr`.

Keep a native terminal at the clone root and one CodeArbiter harness at the same clone. Native terminal commands never begin with `!`; host-native CodeArbiter commands and harness requests never begin with `!` either.

Academy accepts a prepared author name only when it has 1–80 Unicode scalar values. It captures `%an`, never echo a rejected name, and keeps no learner email. No learner email is retained, rendered, or required. The prepared decision log is an append-only byte prefix.

## What you will prove

You will record ADR-0004 for the Workshop Queue summary-format boundary. The learner chooses and approves the ADR/log boundary. The agent may analyze and draft, but it cannot choose, replace, or broaden the decision.

The two allowed learner choices are stable text and structured JSON. The committed evidence is an accepted `.codearbiter/decisions/0004-academy-lab.md` and a matching append to `.codearbiter/decisions/decision-log.md`; ADR-0003 remains untouched. The permitted history is one commit or two linear commits, with the ADR before the log when split.

## Prepare safely

{{action:P03-read-boundary}}

{{action:P03-identity-boundary}}

{{action:P03-prepare}}

Do not invent an attempt number, branch, or source-checkout substitute; use the installed Preview 0.11 action.

## Practice the decision

{{action:P03-inspect-decision-context}}

{{action:P03-request-decision-analysis}}

Read the analysis, select one exact learner choice, then explicitly approve the ADR/log draft before the agent runs the ADR command. Review the draft against that choice, then explicitly approve its committed form before the agent runs the commit gate.

{{action:P03-run-adr}}

{{action:P03-run-commit-gate}}

## Recognize success

{{action:P03-confirm-native-evidence}}

Success is an accepted ADR-0004 and matching decision-log append on the prepared branch. The record carries the learner-approved choice, attribution, alternatives, consequences, and risks; the worktree is clean.

## Check

{{action:P03-check}}

Check proves only final-state evidence: a clean worktree; 1–2 linear commits; only ADR/log paths; ADR before log if split; commit date/name; artifact format/choice; and the append-only log prefix. It cannot prove human acceptance, host command use, reasoning quality, chronology, or independent review.

## Recover or continue

If evidence is wrong or Check names a failed predicate, preserve the attempt. Do not amend, rebase, overwrite ADR-0003, rewrite the log prefix, or manufacture a generic governance event.

{{action:P03-reset}}

Continue to P04, the next public guided Academy lesson in Preview 0.11.

### Hint 1

Read ADR-0003 before drafting. Its occupied number and verifier-trust boundary explain why this exercise allocates ADR-0004.

### Hint 2

The record needs consequences: explain what callers, automation, compatibility, and future schema evolution gain or lose under the learner-approved choice.

### Hint 3

Check reconstructs committed facts. It can reject mismatched or rewritten artifacts, but it cannot recover deliberation or prove human approval.

## Understand the mechanism

An ADR makes a consequential choice durable: context explains why it matters, alternatives preserve the trade-off, the decision records the approved boundary, and consequences guide future maintainers. The append-only log makes that lifecycle discoverable; Check reconstructs the committed boundary from Git rather than trusting a transcript.
