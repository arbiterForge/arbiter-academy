---
id: P04-review-a-dependency
track: practitioner
order: 4
title: Review a dependency without installing it
outcome: Review python-dateutil 2.9.0.post0 against frozen evidence, select the bounded standard-library alternative for finite legacy date formats, and preserve a no-install rejection record.
prerequisites: P03-record-an-adr
estimated_minutes: 35
scenario_command: arbiter-academy --repository <learner-repository> prepare P04-review-a-dependency
checkpoint_command: arbiter-academy --repository <learner-repository> check P04-review-a-dependency
next_lab: P05-checkpoint-remediation
---

# P04 - Review a dependency without installing it

## Know before you begin

P04 is a guided, runnable Academy lesson in Preview 0.11. Its shared action cards are the public course route.

Complete P03 in the same Academy fork and clone. Keep a native terminal at the clone root for Academy operations and file inspection. Keep one CodeArbiter harness open at that same clone for agent work. Native-terminal commands are entered directly and never begin with `!`. A shell command inside a harness begins with exactly one `!`. CodeArbiter commands and agent messages belong in the harness and never begin with `!`.

The website is the primary lesson surface. Academy CLI only handles Prepare, Check, and Reset. It does not replace these guided decisions.

This is a review lesson, not a package-adoption lesson. The candidate set is committed offline evidence. It is not a live package-registry lookup, and its maintenance and vulnerability statements are a frozen 2026-07-31 snapshot rather than current registry or CVE truth.

Its policy is `review-only-never-install`. The report still records **Known vulnerabilities** and
**Supply chain** as named review sections, but calls neither live truth. The prepared set has **No NOTICE** payload; no install during P04 means neither archive enters the exercise environment.

## What you will prove

You will preserve one reviewed report for `python-dateutil==2.9.0.post0` and its `six` closure. The beginner path rejects the candidate because finite legacy date formats can use a bounded `datetime.strptime` parser: explicit formats, a length limit, deterministic timezone and default rules, and fail-closed trailing-content behavior.

The agent drafts the evidence. You inspect it, review the tradeoff, and select `Decision: reject`. The resulting commit contains only the review report. It does not change a dependency declaration, environment lock, or Academy approval wrapper. The existing checkpoint can still recognize its pre-existing equivalent acceptance topology, but that is not an instruction path in this lesson.

## Prepare safely

{{action:P04-prepare}}

{{action:P04-read-boundary}}

{{action:P04-read-candidate-set}}

{{action:P04-inspect-project-boundary}}

## Practice

{{action:P04-inspect-wheel-metadata}}

{{action:P04-verify-wheel-hashes}}

{{action:P04-read-licenses}}

{{action:P04-assess-provenance}}

{{action:P04-compare-stdlib}}

{{action:P04-draft-review}}

{{action:P04-review-draft}}

{{action:P04-select-reject}}

{{action:P04-stage-review}}

{{action:P04-commit-review}}

{{action:P04-confirm-no-install}}

## Recognize success

The final descendant commit changes only `.codearbiter/reports/academy/P04-dependency-review.md`. Its report names the candidate and closure archives, their SHA-256 values, wheel-derived licenses and Apache text, frozen review date, supply-chain limits, compatibility boundary, bounded alternative, every SMARTS lens, and `Install-Policy: no-install-in-p04`. The report ends with `Decision: reject`.

`pyproject.toml` is unchanged. `requirements.lock` and `.codearbiter/reports/academy/P04-approved-dependency.lock.json` remain absent or unchanged. No package enters the exercise environment.

The checker retains a pre-existing equivalent acceptance topology for regression coverage. That path
is not taught here: it would require one later governed adoption boundary, complete closure evidence,
and remains separate from external installation. This beginner lesson never edits that surface.

## Check

{{action:P04-check}}

Check recomputes frozen candidate bytes, report grammar, prepared project digest, allowed commit paths, unchanged dependency surfaces, and clean worktree. It does not prove that you ran a host command, does not authenticate your review or selection, and cannot turn the frozen snapshot into live external truth.

## Recover or continue

If evidence is incomplete, unsupported, or Check fails, preserve the attempt and start a new numbered one. Do not erase failed evidence to make a later decision look cleaner.

### Hint 1

Read `candidate-set.json` before accepting an agent summary. A package name is not an artifact identity, and a candidate artifact is not installation permission.

### Hint 2

Keep the requirement bounded: finite formats, a length limit, deterministic defaults, and a parser that fails closed. Broader requirements deserve their own decision.

### Hint 3

The report records review evidence and selected rejection. Check can inspect final state; it cannot reconstruct who read the draft or when a host command ran.

{{action:P04-reset-retry}}

After Check passes, leave the completed branch intact and return to `main` when ready. Continue to P05 when you are ready to practice a bounded checkpoint remediation.

## Understand the mechanism

Dependency governance separates proposal, evidence, decision, and adoption. This lesson stops at a reviewed rejection because the bounded standard library parser meets the stated need with no new runtime closure. The stored report makes that tradeoff inspectable; it does not invent live facts, delegate the learner decision, or silently promote review evidence into installation authority.
