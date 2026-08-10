# Recovery guidance

Use this page when the Academy console refuses an operation or a lesson result differs from what the page describes. Diagnose first. Preserve the branch, committed evidence, uncommitted work, and console report until the next safe action is clear.

Run this read-only observation before choosing a branch below.

{{action:recovery-inspect}}

## Repository not found or not Git

**Stop:** Do not create files or start a lesson in the selected folder. **Observe:** The Academy console reports that it cannot find the repository or its Git metadata. **Safe action:** Return to the Academy Home page, locate the clone created from your fork, and open the console from that folder. **Preserved:** The folder you selected remains unchanged.

## Dirty worktree

**Stop:** Do not reset or switch branches. **Observe:** Inspect reports the changed and untracked paths. **Safe action:** Identify which paths are lesson evidence, commit the evidence that is ready, and leave unrelated work on its current branch. **Preserved:** Every changed file and the current branch remain available for review.

## Wrong branch or detached HEAD

**Stop:** Do not begin another attempt. **Observe:** The Inspect report names the numbered attempt branch or says that HEAD is detached. **Safe action:** Copy the exact attempt-branch name from Inspect into the action below and switch to it; if Inspect names no attempt branch, stop and return to the lesson page instead. **Preserved:** Existing commits and the detached commit remain reachable.

{{action:recovery-return-attempt}}

## Unsafe or missing remotes

**Stop:** Do not push. **Observe:** The Inspect report shows any mismatch from this contract: `origin` fetch and push target your fork, `upstream` fetches the official repository, `remote.upstream.pushurl` is `DISABLED`, and effective push routing resolves to `origin`. **Safe action:** Replace `YOUR-GITHUB-ACCOUNT` in the action below, run the command for your operating system, and Inspect again before pushing. **Preserved:** Local branches, commits, and working files do not change when remote configuration is corrected.

{{action:recovery-repair-remotes}}

Use Check only after Inspect identifies the intended numbered attempt. Its report is the observation used by the next two branches.

{{action:recovery-check}}

## No prepared attempt

**Stop:** Do not manufacture an attempt branch by hand. **Observe:** Check reports that no numbered attempt is prepared for the selected lesson. **Safe action:** Return to that lesson page and use the Academy console's Prepare action once. **Preserved:** Existing branches and evidence remain untouched.

## Failed Check with clean committed evidence

**Stop:** Do not rewrite the evidence commit. **Observe:** Check names the unmet requirement while Inspect reports a clean worktree. **Safe action:** Keep the report with the attempt, read the lesson's expected result and recovery text, then make the smallest new correction on the same attempt branch. **Preserved:** The failed commit and Check report remain part of the evidence trail.

## Retry

**Stop:** Do not retry until the current evidence is committed and Inspect reports safe remotes plus a clean worktree. **Observe:** Check still fails after the documented correction, or the lesson explicitly directs a fresh attempt. **Safe action:** Use Reset once. Reset archives the current attempt and prepares the next numbered attempt, so do not run Prepare afterward. **Preserved:** The prior attempt branch and its committed evidence remain available.

{{action:recovery-reset}}

## Return to main

**Stop:** Do not leave an attempt while it has uncommitted work. **Observe:** Inspect reports a clean worktree and committed evidence on the numbered attempt branch. **Safe action:** Use Return to base, then confirm that the console reports `main` with no local changes. **Preserved:** The attempt branch, its commits, and its Check evidence remain intact.

{{action:recovery-return-base}}
