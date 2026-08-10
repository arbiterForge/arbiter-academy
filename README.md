# Arbiter Academy

Real, fork-first training for [codeArbiter](https://codearbiter.dev/).

Arbiter Academy is a practice repository and a guided course. You work through
real Git history, repository state, tasks, decisions, reviews, and recovery
without risking one of your own projects. The website is the course; this
README records the release boundary and points you to the right starting place.

## Preview 0.3

Preview 0.3 publishes eleven runnable labs:

- **F01 is guided and runnable.** Its lesson provides the complete novice path,
  including fork, clone, Doctor, safe remotes, evidence, Check, and recovery.
- **F02-F04 and P01-P07 are runnable reference lessons.** Their verifiers are
  available, while their guided rewrites are still in progress.

P08 and the Power User track are outside Preview 0.3. Graduation is not available
in Preview 0.3; it remains unavailable until the complete 19-lab course through
U07 is published.

## Start the course

- [Open Arbiter Academy](https://arbiterforge.github.io/arbiter-academy/)
- [Begin F01 - Fork, clone, and Doctor safety](https://arbiterforge.github.io/arbiter-academy/labs/F01-fork-clone-doctor/)
- [Open Recovery guidance](https://arbiterforge.github.io/arbiter-academy/recovery/)

Start on the Academy Home page even if you have never forked a repository. It
explains each prerequisite, shows the reviewed install path, distinguishes the
browser, native terminal, CodeArbiter harness, and Academy console, and gives
copyable commands for your operating system and host. Lesson commands and
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
