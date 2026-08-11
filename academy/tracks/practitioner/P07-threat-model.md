---
id: P07-threat-model
track: practitioner
order: 7
title: Threat-model the path-handling boundary
outcome: Preserve the complete native threat-model conversation and add a separately labeled Academy identity and SHA-256 binding for academy_engine/paths.py.
prerequisites: P06-context-drift-recovery
estimated_minutes: 30
scenario_command: arbiter-academy --repository <learner-repository> prepare P07-threat-model
checkpoint_command: arbiter-academy --repository <learner-repository> check P07-threat-model
next_lab: P08-repository-hygiene
---

# P07 — Threat-model the path-handling boundary

## Why this mechanism matters

Threat modeling is an opt-in and read-only design review, not automatic authorization to change a
security control. The codeArbiter conversation has four native fields: Scope, a complete six-row
STRIDE table, Recommended controls before implementation, and Clearance. Academy needs additional
deterministic target evidence, so you preserve those fields and add a clearly separate Academy
target identity/SHA-256 section. The resulting report is Academy evidence; it is not native or
canonical `ca-threat-model` output.

## Start the scenario

Run this from the learner checkout. Preserved P02 verifier records require the installed command for
every later Practitioner transition, even though the original GitHub remotes are already restored.
Prepare the archive-import path request:

```powershell
$learnerRepository = (Resolve-Path -LiteralPath '.').Path
arbiter-academy --repository $learnerRepository prepare P07-threat-model
```

The bounded target is `academy_engine/paths.py`. Preparation materializes the frozen scenario descriptor
without prewriting a threat model or weakening containment. The installed verifier later recomputes
the target blob identity and raw SHA-256 from the prepared and head committed Git objects.

## Use your host

Invoke the opt-in lightweight STRIDE pass for the exact target and request.

### Claude Code

```text
/ca:threat-model "academy_engine/paths.py archive-import containment boundary"
```

### Codex

```text
$ca-threat-model "academy_engine/paths.py archive-import containment boundary"
```

### Pi (Feature Forge preview)

Pi is the supported Feature Forge preview and requires project trust. Its documented fallback is
`/skill:ca-threat-model "academy_engine/paths.py archive-import containment boundary"`.

```text
/ca-threat-model "academy_engine/paths.py archive-import containment boundary"
```

## Do the work

Create `.codearbiter/reports/academy/P07-threat-model.md` as strict UTF-8 with LF line endings and
one final newline. Keep it at or below 12 KiB. Use this exact section order and no extra sections:

```text
# P07 Threat Model - Archive import containment boundary

## Scope
<one to six nonempty lines>

## STRIDE findings
| Threat | Category | Likelihood | Impact | Control |
| --- | --- | --- | --- | --- |
| <unique archive-import threat> | S | H, M, or L | H, M, or L | PRESENT:, PLANNED:, GAP:, or N/A: with a concrete reason |
| <unique archive-import threat> | T | H, M, or L | H, M, or L | PRESENT:, PLANNED:, GAP:, or N/A: with a concrete reason |
| <unique archive-import threat> | R | H, M, or L | H, M, or L | PRESENT:, PLANNED:, GAP:, or N/A: with a concrete reason |
| <unique archive-import threat> | I | H, M, or L | H, M, or L | PRESENT:, PLANNED:, GAP:, or N/A: with a concrete reason |
| <unique archive-import threat> | D | H, M, or L | H, M, or L | PRESENT:, PLANNED:, GAP:, or N/A: with a concrete reason |
| <unique archive-import threat> | E | H, M, or L | H, M, or L | PRESENT:, PLANNED:, GAP:, or N/A: with a concrete reason |

## Recommended controls before implementation
- Keep destination resolution under the selected repository root before creating or copying a file.
- Reject absolute, traversal, symlink, and Windows reparse-point ancestors in archive destinations.
- Fail closed on a different drive or an unrepresentable containment path before any write.

## Clearance
CLEAR TO IMPLEMENT
```

`BLOCKED - resolve findings first` is the other permitted Clearance line. Both outcomes are
advisory; neither authorizes a P07 code change.

Your Scope must make two affirmative relationships clear: the review covers
`academy_engine/paths.py` handling learner-controlled archive-member or overlay-destination input
beneath the selected repository root, and the boundary proves containment or rejects an escape
before a destination write. Negated versions, including `not`, `n't` contractions, and
`fail`/`fails`/`failed`/`failing` predicates, and unordered keyword lists fail.

Give the six rows unique threats in exact `S`, `T`, `R`, `I`, `D`, `E` order. Each Threat cell must
state a concrete modal relationship and category-specific outcome, such as spoofing identity,
overwriting a destination, disputing attribution, disclosing a location, exhausting resources, or
crossing into privilege. A bare category keyword is not a threat. `N/A:` is permitted only when its
Control explains why that category is not applicable at this local boundary; `NONE`, blank rows,
reordered categories, repeated threats, and generic boilerplate fail. Required Scope and STRIDE
meaning must be learner-visible; HTML comments and inline HTML markup, Markdown link metadata, and
Markdown decoration such as struck-through or emphasized threat verbs are rejected rather than
counted as evidence. Non-ASCII characters (including lookalikes) are also rejected. A Control
cannot supply missing Threat semantics. First-person native prose and realized success claims are
not invocation evidence and are rejected without trying to enumerate every possible action or tool
noun. Other host/tool clauses are accepted only when their hypothetical, uncertain, threat, or
rejection context is explicit; they never prove invocation.

After Clearance, add this separate Academy section with these exact labels and values:

```text
## Academy Target-SHA256/identity binding
Academy-Target-Path: academy_engine/paths.py
Academy-Target-Prepared-Blob: b36801add4eb375f796d1107ee63dd604d08a034
Academy-Target-Head-Blob: b36801add4eb375f796d1107ee63dd604d08a034
Academy-Target-SHA256: e40a7655ce6ba6cde58a91ae10a714f10046c055ac90dcbc58f0696c39133a5d
```

Do not put an `Academy-Target-` label in a native field, repeat a native heading inside the Academy
section, claim a host command was invoked, include a secret, or edit `academy_engine/paths.py`.
Commit only the report after prepare. This lab assesses controls; it never implements them.

## Hints

### Hint 1

Draw the boundary from untrusted archive path/member input through normalization and resolved
containment to the intended extraction root before enumerating threats.

### Hint 2

Traversal and extraction concerns usually require concrete Tampering, Information Disclosure, and
Denial of Service analysis. Give every other STRIDE row an explicit applicable or justified
not-applicable disposition.

### Hint 3

Hash the exact tracked target bytes at the wrapper commit. Keep the Academy identity and digest out
of the four native conversational fields and verify the target never changes afterward.

## Success evidence

Success is one report-only commit after the prepared commit, a clean worktree, and byte-identical
prepared/head target objects matching the frozen blob and SHA-256. The committed report must match
the ordered native grammar and separate Academy binding above. Missing fields, generic or reordered
rows, mixed metadata, stale identity, target mutation, another changed path, or extra history fails.

```powershell
$learnerRepository = (Resolve-Path -LiteralPath '.').Path
arbiter-academy --repository $learnerRepository check P07-threat-model
```

The check cannot prove that a host command was invoked. It proves only the committed report,
prepared/head target identity, exact bytes, and Git ordering.

## Recovery

For a wrong target, incomplete model, or stale digest, use the installed reset command:

```powershell
$learnerRepository = (Resolve-Path -LiteralPath '.').Path
arbiter-academy --repository $learnerRepository reset P07-threat-model
```

Reset archives the failed attempt, returns to the immutable base, and uses that base to prepare an
independent retry. It does not delete learner history. Do not alter `academy_engine/paths.py` merely
to fit an old digest or copy a model from another attempt.

## Next lab

P08 is not available in Academy Preview 0.3. Keep your passing P07 evidence until repository hygiene
enters a later release.
