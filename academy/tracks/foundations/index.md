# Foundations

Foundations turns an ordinary fork into a governed Academy workspace. The four labs are sequential:
each starts from the clean `main` branch, creates a numbered attempt branch, leaves the preparation
commit intact, and ends with at least one learner commit.

| Lab | You will prove | Typical time |
|---|---|---:|
| F01 | Your fork cannot accidentally push to the official Academy repository | 20 minutes |
| F02 | You can orient from live repository governance state | 15 minutes |
| F03 | You can move a real task through the sanctioned board lifecycle | 15 minutes |
| F04 | You can preserve regression-first history while repairing a real defect | 30 minutes |

Use repository-local `python scripts/academy.py` only for preparation, reset, update, and local
diagnostics. Run every authoritative checkpoint through an `arbiter-academy` installation outside
the learner checkout and select the target explicitly. That verifier produces deterministic,
tamper-evident local evidence; it is not a signed credential and cannot defend against replacing the
installed verifier itself.

If an attempt goes sideways, commit or discard only unrelated scratch work, then run the lab's
`reset` command. Reset archives the attempt and creates a new numbered branch. It never deletes the
old branch, force-resets history, or force-pushes.
