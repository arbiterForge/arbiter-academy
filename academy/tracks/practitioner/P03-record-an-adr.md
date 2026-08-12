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

P03 is a private, source-only guided lesson. The current public release is Preview 0.8: it publishes
F01 through F04, lists P03 as `coming_next`, and does not permit P03 Prepare, Check, or Reset. There is no
released P03 path to invoke. The Academy operation cards below are future published execution
contracts, not commands for learners to run now. They become executable only after a later installed
release lists P03 in both `runnable_labs` and `guided_labs`.

Private maintainers may cold-read and locally test the authoring contract without representing that
work as a learner attempt. In the future published flow, keep a native terminal at the clone root and
one CodeArbiter harness open at that same clone. Native terminal commands go directly into the
terminal and never begin with `!`. CodeArbiter commands and agent requests go into the selected
harness and never begin with `!`.

Academy accepts a prepared author name only when it has 1–80 Unicode scalar values and follows its
display-safe rules. No learner email is retained, rendered, or required. Academy captures `%an`,
never echo a rejected name, and treats the prepared decision log as an append-only byte prefix.
The action contract is named `P03-adr-decision-log.json`; that name does not change P03's immutable
scenario and checkpoint ID, `P03-record-an-adr`.

## What you will prove

You will preserve an accepted ADR-0004 for one real architecture choice: whether the Workshop Queue
summary uses stable text or structured JSON. Both choices are valid. You choose; the agent analyzes
the consequences and records the option you accept.

The final evidence is an accepted `.codearbiter/decisions/0004-academy-lab.md` plus a matching,
later-or-co-committed append to `.codearbiter/decisions/decision-log.md`. You may use one commit or two linear commits; if there are two, the ADR comes before the log. ADR-0003 remains untouched.

## Prepare safely

{{action:P03-read-boundary}}

{{action:P03-identity-boundary}}

{{action:P03-prepare}}

In a future published release, Academy will print the attempt number and own the prepared branch.
Until that release exists, do not invent `ATTEMPT_NUMBER`, create a learner attempt manually, or use
repository source as a substitute for the installed external verifier.

## Practice the decision

{{action:P03-read-decision-context}}

{{action:P03-request-analysis}}

Read the comparison, then make the decision yourself. Stable text favors a durable, readable caller
boundary. Structured JSON favors explicit automation and future schema evolution. Neither is the
secret answer. The agent may analyze and draft; it may not select or replace your decision.

{{action:P03-make-choice}}

{{action:P03-author-adr}}

The generic `ca-adr` command starts the sanctioned lifecycle; it does not by itself produce accepted
P03 Check evidence. The actual lifecycle first writes a learner-attributed proposed draft and a
proposed append. This private contract then checks P03's exact fixed path and shape.

{{action:P03-inspect-proposed-adr}}

Only after the proposed ADR and log match your exact choice may you give explicit learner acceptance.
Silence, a draft, a review, or a commit request is not acceptance.

{{action:P03-accept-proposed-adr}}

After explicit learner acceptance, inspect the status transition once more. The accepted ADR and log
must preserve the proposed decision, attribution, consequences, risks, and append boundary before a
commit is authorized.

{{action:P03-commit-accepted-decision}}

{{action:P03-inspect-committed-evidence}}

## Recognize success

For future published execution, the completed attempt has accepted ADR-0004 and its matching
decision-log entry on the prepared branch. The ADR records the exact learner-owned choice, immutable
number/date/title, alternatives considered, consequences, and risks. The log has not rewritten its
prepared prefix; it only adds the accepted DECISION-0004 suffix. The final worktree is clean.

## Check

{{action:P03-check}}

In the future published flow, Check will inspect the exact
`.codearbiter/decisions/0004-academy-lab.md` path; front matter for `status`, `date`, `title`,
`decided-by`, `supersedes: none`, and `governs: workshop_queue/cli.py`; ordered `Status`, `Context`,
`Decision`, `Alternatives considered`, `Consequences`, and `Risks` headings; and the matching
`## DECISION-0004 — ADR-0004 — Choose the Workshop Queue summary-format boundary` append. That log
entry must carry `**Date:**`, `**Status:** accepted`, `**Supersedes:** none`, `**Decided by:**`,
`**Decision category:** architecture`, and `**Artifact-section-hash:** n/a`, followed by ordered
`Variance summary`, `Decision`, `SMARTS rationale`, and `Implementation implication` sections. Its
variance must include `Status type: open-decision-closure`.

The semantic verifier can also inspect the prepared baseline, final Git history, permitted one- or
two-commit ordering, exact accepted choice, attribution, and clean worktree. It does not prove that
you personally chose stable text or structured JSON. It does not prove that a host command ran. It
does not prove that anyone reviewed the ADR or supplied explicit learner acceptance. Those are honest
learner and team practices, not claims a final-state verifier can authenticate.

## Recover or continue

During private authoring, a failed focused test means revise the source contract; it does not mean a
learner ran Check. In future published execution, if the number is wrong, alternatives are shallow,
the log prefix was rewritten, attribution differs, or Check names a failed predicate, preserve the
attempt. Do not amend, rebase, overwrite ADR-0003, or manufacture a generic governance event.

### Hint 1

ADR-0003 is already occupied by the verifier-trust boundary. Reading it first tells you why this
exercise must allocate ADR-0004 rather than renumbering or replacing existing history.

### Hint 2

Do not write "JSON is better" or "text is simpler" and stop. State what callers, automation,
compatibility, and future schema changes gain or lose under the option you accept.

### Hint 3

Check derives committed facts. It can reject a mismatched or rewritten record, but cannot recover
your private deliberation or prove a human approval. Keep those distinctions clear in the ADR.

{{action:P03-reset}}

No P03 learner Check can pass on Preview 0.8. After a future published Check actually passes, leave
the completed branch intact. Continue to P04 only when its own guided rewrite is published; do not
substitute unpublished source exercises for a released lesson.

## Understand the mechanism

An ADR makes a consequential choice durable: context explains why it mattered, alternatives expose
the trade-off, the decision records the accepted path, and consequences keep future maintainers from
rediscovering it blindly. The append-only decision log makes that lifecycle easy to find. Academy
Check then reconstructs the committed boundary from Git rather than trusting a pasted transcript or
a claim that somebody approved it.
