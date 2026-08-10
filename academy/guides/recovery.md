# Recovery guidance

Use this page when the Academy console refuses an operation or a lesson result differs from what the page describes. Diagnose first. Preserve the branch, committed evidence, uncommitted work, and console report until the next safe action is clear.

## Repository not found or not Git

**Stop:** Do not create files or start a lesson in the selected folder. **Observe:** The Academy console reports that it cannot find the repository or its Git metadata. **Safe action:** Return to the Academy Home page, locate the clone created from your fork, and open the console from that folder. **Preserved:** The folder you selected remains unchanged.

## Dirty worktree

**Stop:** Do not reset or switch branches. **Observe:** Inspect reports the changed and untracked paths. **Safe action:** Identify which paths are lesson evidence, commit the evidence that is ready, and leave unrelated work on its current branch. **Preserved:** Every changed file and the current branch remain available for review.

## Wrong branch or detached HEAD

**Stop:** Do not begin another attempt. **Observe:** Inspect reports the current branch or says that HEAD is detached. **Safe action:** Keep the current state, record any completed evidence, and return to the numbered attempt branch named by the lesson before continuing. **Preserved:** Existing commits and the detached commit remain reachable.

## Unsafe or missing remotes

**Stop:** Do not push. **Observe:** Inspect reports that `origin` is missing, does not belong to your GitHub account, or that `upstream` does not point to `arbiterForge/arbiter-academy`. **Safe action:** Correct the remote addresses so `origin` is your fork and `upstream` is the official read-only repository, then inspect again. **Preserved:** Local branches, commits, and working files do not change when remote addresses are corrected.

{{action:recovery-inspect}}

## No prepared attempt

**Stop:** Do not manufacture an attempt branch by hand. **Observe:** Check reports that no numbered attempt is prepared for the selected lesson. **Safe action:** Return to that lesson page and use the Academy console's Prepare action once. **Preserved:** Existing branches and evidence remain untouched.

## Failed Check with clean committed evidence

**Stop:** Do not rewrite the evidence commit. **Observe:** Check names the unmet requirement while Inspect reports a clean worktree. **Safe action:** Keep the report with the attempt, read the lesson's expected result and recovery text, then make the smallest new correction on the same attempt branch. **Preserved:** The failed commit and Check report remain part of the evidence trail.

{{action:recovery-check}}

## Retry

**Stop:** Do not retry until the current evidence is committed and Inspect reports safe remotes plus a clean worktree. **Observe:** Check still fails after the documented correction, or the lesson explicitly directs a fresh attempt. **Safe action:** Use Reset once. Reset archives the current attempt and prepares the next numbered attempt, so do not run Prepare afterward. **Preserved:** The prior attempt branch and its committed evidence remain available.

{{action:recovery-reset}}

## Return to main

**Stop:** Do not leave an attempt while it has uncommitted work. **Observe:** Inspect reports a clean worktree and committed evidence on the numbered attempt branch. **Safe action:** Use Return to base, then confirm that the console reports `main` with no local changes. **Preserved:** The attempt branch, its commits, and its Check evidence remain intact.

{{action:recovery-return-base}}
