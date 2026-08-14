# Arbiter Academy

Real, fork-first training for [codeArbiter](https://codearbiter.dev/).

Arbiter Academy is a practice repository and a guided course. You work through
real Git history, repository state, tasks, decisions, reviews, and recovery
without risking one of your own projects. The website is the course; this
README records the release boundary and points you to the right starting place.

## Preview 0.23

Preview 0.23 publishes all nineteen guided labs:

- **F01 is guided and runnable.** Its lesson provides the complete novice path,
  including fork, clone, Doctor, safe remotes, evidence, Check, and recovery.
- **F02 is guided and runnable.** Its lesson turns live CodeArbiter state into a
  bounded, committed orientation record without changing the context it proves.
- **F03 is guided and runnable.** Its lesson teaches one governed board lifecycle
  and a board-only evidence commit without implementing the listed feature.
- **F04 is guided and runnable.** Its lesson carries a real red-to-green repair
  through two reviewable commits, ending in an independent Check.
- **P01 is guided and runnable.** Its lesson turns an approved feature specification
  into a reviewable plan, bounded repair, and preserved evidence branch.
- **P02 is guided and runnable.** Its lesson rehearses bounded review, two governed
  commits, origin-only push evidence, and an offline-local receipt.
- **P03 is guided and runnable.** Its lesson records a learner-approved ADR and
  matching append-only decision-log entry with externally checked Git evidence.
- **P04 is guided and runnable.** Its lesson reviews a frozen offline dependency
  candidate and records a bounded no-adoption decision with exact evidence.
- **P05 is guided and runnable.** Its lesson turns a checkpoint finding into a
  reviewable finding, RED regression, GREEN repair, and receipt history.
- **P06 is guided and runnable.** Its lesson restores one source-contradicted
  context claim while preserving unrelated work byte-for-byte.
- **P07 is guided and runnable.** Its lesson builds a bounded, target-specific
  STRIDE report without modifying the reviewed production path.
- **P08 is guided and runnable.** Its lesson classifies live Git refs and
  worktrees without authorizing destructive cleanup.
- **U01 is guided and runnable.** Its lesson governs a real CodeArbiter sprint
  in the learner's fork: the learner approves scope, the sprint opens a fork
  pull request after its commit gate, and it never self-merges.
- **U02 is guided and runnable.** Its lesson records one narrow override, keeps
  the real audit packet as evidence, and treats the read-only metrics glance as
  advice rather than a fabricated receipt.
- **U03 is guided and runnable.** Its lesson carries a behavior-preserving
  refactor, a docs-only chore, and a real local annotated release without
  claiming a remote tag or hosted publication.
- **U04 is guided and runnable.** Its lesson initializes separate greenfield
  and brownfield child projects, commits each through CodeArbiter, then writes
  a canonical parent binding report from their committed state.
- **U05 is guided and runnable.** Its lesson records a real no-action debug
  note, transfers only committed spike findings to the parent branch, then
  deletes the disposable spike without merging it.
- **U06 is guided and runnable.** Its lesson keeps CodeArbiter preview advice
  separate from durable repository evidence and does not fabricate telemetry.
- **U07 is guided and runnable.** Its capstone follows the real feature lane,
  preserves local behavior evidence, and opens a real hosted pull request.

All 19 Academy lessons through U07 are public in Preview 0.23. Graduation is
available after all 19 Academy Checks pass in the same repository.

## Start the course

- [Open Arbiter Academy](https://arbiterforge.github.io/arbiter-academy/)
- [Begin F01 after Home setup - Fork, clone, and Doctor safety](https://arbiterforge.github.io/arbiter-academy/labs/F01-fork-clone-doctor/)
- [Continue to F02 - Orient to live governance state](https://arbiterforge.github.io/arbiter-academy/labs/F02-orient-to-state/)
- [Continue to F03 - Work the governed board](https://arbiterforge.github.io/arbiter-academy/labs/F03-work-the-board/)
- [Continue to F04 - Fix with executable evidence](https://arbiterforge.github.io/arbiter-academy/labs/F04-fix-with-evidence/)
- [Continue to P01 - Feature through an approved specification](https://arbiterforge.github.io/arbiter-academy/labs/P01-feature-through-plan/)
- [Continue to P02 - Review, commit, push, and record an offline-local receipt](https://arbiterforge.github.io/arbiter-academy/labs/P02-commit-review-pr/)
- [Continue to P03 - Record an accepted ADR](https://arbiterforge.github.io/arbiter-academy/labs/P03-record-an-adr/)
- [Continue to P04 - Review a dependency without adopting it](https://arbiterforge.github.io/arbiter-academy/labs/P04-review-a-dependency/)
- [Continue to P05 - Remediate a checkpoint finding](https://arbiterforge.github.io/arbiter-academy/labs/P05-checkpoint-remediation/)
- [Continue to P06 - Recover context drift without losing unrelated work](https://arbiterforge.github.io/arbiter-academy/labs/P06-context-drift-recovery/)
- [Continue to P07 - Threat-model the path-handling boundary](https://arbiterforge.github.io/arbiter-academy/labs/P07-threat-model/)
- [Continue to P08 - Classify repository hygiene without destructive cleanup](https://arbiterforge.github.io/arbiter-academy/labs/P08-repository-hygiene/)
- [Continue to U01 - Govern an autonomous sprint without outsourcing approval](https://arbiterforge.github.io/arbiter-academy/labs/U01-autonomous-sprint/)
- [Continue to U02 - Record a scoped override with local audit evidence](https://arbiterforge.github.io/arbiter-academy/labs/U02-override-audit-metrics/)
- [Continue to U03 - Refactor, chore, and cut a local release](https://arbiterforge.github.io/arbiter-academy/labs/U03-refactor-chore-release/)
- [Continue to U04 - Initialize a greenfield and a brownfield project](https://arbiterforge.github.io/arbiter-academy/labs/U04-initialize-projects/)
- [Continue to U05 - Debug, spike, and stop for a real conflict](https://arbiterforge.github.io/arbiter-academy/labs/U05-debug-spike-conflict/)
- [Continue to U06 - Preview a bounded change without turning advice into authority](https://arbiterforge.github.io/arbiter-academy/labs/U06-preview-and-advanced-surfaces/)
- [Complete U07 - Complete a bounded feature capstone](https://arbiterforge.github.io/arbiter-academy/labs/U07-capstone/)
- [Open Recovery guidance](https://arbiterforge.github.io/arbiter-academy/recovery/)

Start on the Academy Home page even if you have never forked a repository. It
explains each prerequisite, shows the reviewed install path, distinguishes the
Browser, Native terminal, and active CodeArbiter harness, and gives copyable
commands for your operating system and host. The website remains the course. A
narrow operations TUI for setup, Check, reset, and lesson changes will be
published only after it clears its own acceptance evidence. Lesson commands and
recovery instructions live in the versioned course rather than being duplicated
here. The local Academy runtime requires Python 3.11 or newer.

Questions and Preview feedback belong in
[Academy GitHub Discussions](https://github.com/arbiterForge/arbiter-academy/discussions).

## Authority model

The installed Academy verifier and its installer-managed source form the local
trust anchor. The learner checkout and its Git/artifact data are untrusted
inputs. An in-checkout `check` or `graduate` run is never presented as
authoritative.

This model assumes the initial canonical fetch, Git, Python, and local machine
have not been replaced by a malicious operator. Academy receipts are
deterministic, tamper-evident local evidence; they are not cryptographically
signed credentials.

## Maintainer verification

The serial `python -m unittest discover -v` command remains the canonical test
inventory. Maintainers can run the same inventory as eight dependency-free
concurrent shards with exact-once result evidence:

```text
python scripts/run_test_shards.py --all --evidence-dir .superpowers/shard-evidence --timeout-seconds 5400
```
