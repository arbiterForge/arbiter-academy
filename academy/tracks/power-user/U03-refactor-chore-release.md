---
lesson_id: U03-refactor-chore-release
scenario_command: {{action:U03-prepare}}
checkpoint_command: {{action:U03-check}}
---

# U03: Refactor, chore, and local release evidence

This source lesson is written for the Academy website. The Power User track remains private, so it does not create a public U03 route or change Preview 0.15.

## Know before you begin

Read the boundary before running anything. Preview 0.15 refuses U03 prepare, check, and reset unchanged. That is correct: this release has no runnable U03 attempt.

{{action:U03-read-boundary}}

## What you will prove

The future private contract is deliberately narrow. It can observe a sealed refactor of `workshop_queue/store.py`, a later docs-only `README.md` commit, the generated `CHANGELOG.md` release commit, unchanged pre-existing `tests/test_store.py`, a clean worktree, and annotated local `academy-v0.0.1` at the attempt head. Its tag body reproduces the generated 0.0.1 changelog section followed by the matching `Released-at` date.

It does not prove behavioral parity, human approval, CodeArbiter command execution, tag push, or publication.

## Prepare safely

Use the current public commands only to see their refusal and confirm that they leave no partial state. Do not make files that imitate a future U03 attempt.

{{action:U03-prepare}}

{{action:U03-confirm-refusal}}

## Practice

The following cards describe a future private prepared attempt. Use them only after its sealed brief supplies the exact approved values. The website remains the teaching surface; commands appear only in their action cards.

{{action:U03-review-future-brief}}

{{action:U03-run-refactor}}

{{action:U03-inspect-refactor}}

{{action:U03-review-refactor}}

{{action:U03-stage-refactor}}

{{action:U03-commit-refactor}}

{{action:U03-run-chore}}

{{action:U03-inspect-chore}}

{{action:U03-review-chore}}

{{action:U03-stage-chore}}

{{action:U03-commit-chore}}

{{action:U03-run-release}}

{{action:U03-review-release}}

{{action:U03-inspect-tag}}

## Recognize success

For the future private contract, success is limited to the observed local boundary: three ordered commits (refactor, docs chore, generated changelog), the named paths, an unchanged pre-existing test file, a clean worktree, and an annotated `academy-v0.0.1` tag at the attempt head. The tag body must reproduce the generated changelog section and matching `Released-at` date exactly. It is not a claim about a remote, a release page, or published software.

## Check

Preview 0.15 cannot validate this private contract. Its refusal is the current public result.

{{action:U03-check}}

## Recover or continue

Do not destroy a failed future attempt to make it look clean. Preserve the state and use the private reset rules only when that future release supplies them. Preview 0.15 has no U03 attempt to reset.

{{action:U03-reset}}

## Understand the mechanism

The guide and its action manifest are one shared renderer contract. Every command card names who acts and where. Native terminal commands never use `!`. CodeArbiter commands use the selected host directly. A future verifier can compare repository state, but it cannot infer a learner's judgment or an external release event.
