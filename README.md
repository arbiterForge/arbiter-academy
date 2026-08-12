# Arbiter Academy

Real, fork-first training for [codeArbiter](https://codearbiter.dev/).

Arbiter Academy is a practice repository and a guided course. You work through
real Git history, repository state, tasks, decisions, reviews, and recovery
without risking one of your own projects. The website is the course; this
README records the release boundary and points you to the right starting place.

## Preview 0.10

Preview 0.10 publishes seven guided labs:

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
- **P04-P08 are coming next.** They are not public lesson routes until each
  guided rewrite and its acceptance evidence are complete.

The Power User track is outside Preview 0.10. Graduation is not available
in Preview 0.10; it remains unavailable until the complete 19-lab course through
U07 is published.

## Start the course

- [Open Arbiter Academy](https://arbiterforge.github.io/arbiter-academy/)
- [Begin F01 after Home setup - Fork, clone, and Doctor safety](https://arbiterforge.github.io/arbiter-academy/labs/F01-fork-clone-doctor/)
- [Continue to F02 - Orient to live governance state](https://arbiterforge.github.io/arbiter-academy/labs/F02-orient-to-state/)
- [Continue to F03 - Work the governed board](https://arbiterforge.github.io/arbiter-academy/labs/F03-work-the-board/)
- [Continue to F04 - Fix with executable evidence](https://arbiterforge.github.io/arbiter-academy/labs/F04-fix-with-evidence/)
- [Continue to P01 - Feature through an approved specification](https://arbiterforge.github.io/arbiter-academy/labs/P01-feature-through-plan/)
- [Continue to P02 - Review, commit, push, and record an offline-local receipt](https://arbiterforge.github.io/arbiter-academy/labs/P02-commit-review-pr/)
- [Continue to P03 - Record an accepted ADR](https://arbiterforge.github.io/arbiter-academy/labs/P03-record-an-adr/)
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
