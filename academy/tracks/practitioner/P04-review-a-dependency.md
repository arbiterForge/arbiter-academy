---
id: P04-review-a-dependency
track: practitioner
order: 4
title: Review a real dependency before installation
outcome: Make a complete SMARTS-backed accept or reject decision for python-dateutil 2.9.0.post0 before any installation or permitted manifest change.
prerequisites: P03-record-an-adr
estimated_minutes: 35
scenario_command: arbiter-academy --repository <learner-repository> prepare P04-review-a-dependency
checkpoint_command: arbiter-academy --repository <learner-repository> check P04-review-a-dependency
next_lab: P05-checkpoint-remediation
---

# P04 — Review a real dependency before installation

## Why this mechanism matters

A package name is a proposal, not authorization to install. Dependency review must establish exact
candidate identity, provenance, license, maintenance and supply-chain facts, compatibility, and
alternatives before project state changes. The intended solution rejects this package for a narrow
date-parsing need. An accepted equivalent is valid only with a complete reviewed runtime closure;
the Academy candidate wrapper is evidence about one direct wheel, not that environment lock.

## Start the scenario

Run this from the learner checkout. Preserved P02 verifier records require the installed command for
every later Practitioner transition, even though the original GitHub remotes are already restored.
Prepare the offline candidate review:

```powershell
$learnerRepository = (Resolve-Path -LiteralPath '.').Path
arbiter-academy --repository $learnerRepository prepare P04-review-a-dependency
```

The scenario requests `python-dateutil==2.9.0.post0` for legacy date input and supplies stable
candidate metadata. Read the immutable offline set at
`academy/candidates/P04-review-a-dependency/candidate-set.json`; its policy is
`review-only-never-install`. It does not install, vendor, pre-approve, or add the package to project
files.

## Use your host

Invoke the dependency-review lane before running any installer or editing a manifest.

### Claude Code

```text
/ca:add-dep "python-dateutil==2.9.0.post0 for the legacy-date parser"
```

### Codex

```text
$ca-add-dep "python-dateutil==2.9.0.post0 for the legacy-date parser"
```

### Pi (Feature Forge preview)

Pi is the supported Feature Forge preview and requires project trust. Its documented fallback is
`/skill:ca-add-dep "python-dateutil==2.9.0.post0 for the legacy-date parser"`.

```text
/ca-add-dep "python-dateutil==2.9.0.post0 for the legacy-date parser"
```

## Do the work

Review the exact candidate and prepared project digest. Record provenance, license, supply-chain
signals, compatibility, the bounded stdlib alternative, rationale, all SMARTS lenses, and reviewer
outcome in `.codearbiter/reports/academy/P04-dependency-review.md` before any other project change.

Use the native report labels exactly: `Academy-Schema-Version`, `Project-SHA256`, `Candidate`,
`Candidate-Artifact`, `Candidate-SHA256`, `Closure-Requirement`, `Closure-Package`,
`Closure-Artifact`, `Closure-SHA256`, and `Install-Policy`. The policy label is:

```text
Install-Policy: no-install-in-p04
```

Then add these H2 sections in order: Candidate, Provenance, License, Maintenance, Known
vulnerabilities, Supply chain, Compatibility, Alternatives, SMARTS, Decision. State that maintenance
and vulnerability statements are the frozen **2026-07-31** review snapshot, not live registry truth.
The supply-chain section records pure-Python universal wheels, no sdist, no resolver-selected
artifact, and **no install during P04**. License evidence names the two wheel-derived LICENSE files
and `Apache-2.0.txt`; there is **No NOTICE** or patent payload to invent.

Your SMARTS table compares the bounded standard-library parser with the two-wheel closure on every
lens. The intended decision says `Decision: reject` after selecting the bounded stdlib parser. A
valid accepting review must explain why the broader parsing surface is required and that external
installation remains deferred.

For the intended rejection, choose the bounded stdlib parser and leave `pyproject.toml`,
`requirements.lock`, and `.codearbiter/reports/academy/P04-approved-dependency.lock.json` absent or
unchanged. Install nothing.

For the documented accepted equivalent, first complete an accepting review. Then, in one later
governed commit, add exactly `python-dateutil==2.9.0.post0` to the learner attempt's
`pyproject.toml`; add a complete `requirements.lock` containing exactly these two UTF-8,
LF-terminated physical lines in this order; and add the separate Academy wrapper:

```text
python-dateutil==2.9.0.post0 --hash=sha256:a8b2bc7bffae282281c8140a97d3aa9c14da0b136dfe83f850eea9a5f7470427 # artifact=python_dateutil-2.9.0.post0-py2.py3-none-any.whl
six==1.17.0 --hash=sha256:4721f391ed90541fddacab5acf947aa0d3dc7d27b2e1e8eda2be8970586c3274 # artifact=six-1.17.0-py2.py3-none-any.whl
```

The `artifact=` comments are Academy verifier grammar while the hash options remain pip-compatible.
Use no index directive, editable reference, environment marker, alternate hash, or extra package.
The wrapper is exactly:

```json
{"schema_version":1,"name":"python-dateutil","version":"2.9.0.post0","artifact":"python_dateutil-2.9.0.post0-py2.py3-none-any.whl","sha256":"a8b2bc7bffae282281c8140a97d3aa9c14da0b136dfe83f850eea9a5f7470427","install_policy":"later-only-after-review"}
```

Commit manifest, environment lock, and wrapper together only after review, in **one later governed
commit**. Do not install a package in either variant; an external installation is separate future
evidence and P04 never claims to prove whether an unrelated global installation occurred.

## Hints

### Hint 1

Separate the requested capability from the proposed package. Test whether the Workshop Queue input
formats can be handled by a bounded standard-library parser first.

### Hint 2

Bind the review to the prepared project SHA-256 and exact candidate/version. Cover provenance,
license, maintenance, supply-chain risk, compatibility, alternatives, and every SMARTS lens.

### Hint 3

If accepting, distinguish the two locks: `requirements.lock` covers the complete direct-plus-`six`
runtime closure; the Academy JSON wrapper binds only the reviewed direct candidate wheel for later
evidence. Neither authorizes an install in P04.

## Success evidence

The intended path has a complete pre-install review rejecting the exact candidate and proves the
manifest and both lock surfaces stayed unchanged. The equivalent path has an earlier accepting
review and a later co-commit of the exact manifest entry, complete hash-pinned transitive
environment lock, and separately labeled direct-candidate wrapper using reviewed artifact bytes.
Pre-review edits, invented hashes, incomplete closure, or any installation fail.

```powershell
$learnerRepository = (Resolve-Path -LiteralPath '.').Path
arbiter-academy --repository $learnerRepository check P04-review-a-dependency
```

## Recovery

If any install or premature manifest/lock edit occurred, do not delete evidence to hide it. Preserve
the attempt and reset:

```powershell
$learnerRepository = (Resolve-Path -LiteralPath '.').Path
arbiter-academy --repository $learnerRepository reset P04-review-a-dependency
```

Begin the retry from clean prepared project state and review before changing anything.

## Next lab

P05 is not available in Academy Preview 0.1. Keep your passing P04 evidence; the Preview site will
identify **P05 — Remediate a checkpoint finding** when it enters verification.
