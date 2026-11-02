# Keep lessons aligned with Arbiter

Academy teaches the installed plugin's workflow. Its exercise-specific paths,
report formats, and commit counts are explained as training constraints, not rules
for a learner's own project.

## Review after a plugin change

1. Fetch `origin` in both repositories. Record the Academy baseline, plugin source
   commit, and released host versions. Read plugin files from that commit rather
   than a dirty local checkout.
2. Run `python scripts/check_lesson_source_review.py --codearbiter-root PATH`.
   It compares `academy/lesson-source-review.json` with the producer's
   `origin/main` and prints each affected lesson. It also fails when an action card
   names a codeArbiter command that no longer exists there. The scheduled and PR
   workflows run this check, and the daily `codeArbiter Drift` workflow keeps one
   open issue while it or the compatibility check fails. A matching hash is not
   semantic review.
3. For every affected lesson, read the command owner and its loaded references.
   Review the guide and **every field** of each action card: instruction,
   rationale, command, expected result, recovery, and evidence limits.
4. Walk through Prepare, the real owner workflow, Check, and recovery. If the
   current owner cannot pass Check, fix the exercise and verifier together. Add a
   failing behavioral regression before changing executable checks. Do not ask a
   learner to manufacture old plans, approval records, or failing-test commits.
5. Check that the learner can explain the result and apply it elsewhere. State
   what they do, where they do it, what success looks like, and how to recover.
   Native HTML plans belong in the feature and sprint workflows. Let the agent
   operate the native writer; learners should review outcomes and rendered plans.
6. Obtain independent curriculum and executable-boundary review. Update source
   hashes only after reviewing the actual behavior. Include new downstream
   procedures when a command routes to another owner.
7. Build the site and run its contract check, affected semantic tests, publication
   checks, and offline asset checks. A changed verifier needs a new Academy
   candidate; preserve historical publication manifests. Release and publication
   remain separate from preparing the candidate.

The source map is an explicit dependency list. It detects changes to mapped files;
it cannot discover every new dependency or prove that a lesson is understandable.

## Native planning verification

P01 and U01 now produce `.html` specification/plan pairs through Arbiter. Their
Academy Check actions ask the current host to supply `--plugin-root` from its loaded
external installation. Graduation must receive that same option because it
rechecks these lessons. Use the installed Academy executable with
`--repository PATH graduate --plugin-root INSTALLED_PLUGIN_ROOT`.

The Academy Python package uses the standard library. These two checks also use
the already installed, first-party native artifact producer from the reviewed
plugin cohort. No package is downloaded or installed by Check. The root must be
absolute and outside the learner checkout. The bridge, Git helper, release
manifest, and selected native executable are hash-pinned. The worker uses a
private verified producer snapshot and disposable copies of committed HTML.
Learner Python modules and learner-supplied helper paths are never executed.

Native `ready` validation establishes artifact structure, bindings, and coverage;
it does not establish approval, completed tests, independent review, or live host
enforcement. The lesson checker separately examines the bounded committed work.
An incompatible installation fails closed and needs a reviewed cohort update.

For local producer integration tests, set `ARBITER_ACADEMY_TEST_PLUGIN_ROOT` to
the reviewed installed plugin before running `tests.test_native_planning`,
`tests.test_current_governance_records`, and
`tests.test_task8e_p01_semantics`, plus the native end-to-end test in
`tests.test_power_user_u01`. Without that variable, the explicitly marked
installed-producer tests skip. Ordinary CI source tests do not establish native
host qualification; qualify each supported host before publishing a new cohort.

## November 2026 lesson review

Baseline Academy: `7ed625c973f4d7484efea0321ddd15b13ebc293b`.
Reviewed plugin source and released producer cohort:
`27e6cb12eb0195bc89b4e91ee7d8d8093ac490fa` (Claude 3.8.3, Codex 0.26.3, Pi 0.27.3).
Preview 0.33 remains a source candidate, not a publication claim.

The drift check flagged 18 lessons. Each changed source was diffed against
`0badb588` and its effect checked against every affected guide and action card.
Where a lane now writes files, the real 3.8.3 helpers were run against prepared
attempts instead of inferring the behavior from the skill text.

| Lesson | Finding | Correction |
| --- | --- | --- |
| F04, P05 | The fix lane records an authorized repair as one fix work item: a queued board row that commit-gate keeps in the repair commit. | Check also accepts exactly that row in the repair commit; the guides say to leave it queued. |
| P01 | The feature lane may record its own feature item bound to the spec and plan, beside the taught start of `academy.feature.0002`. | Check also accepts that one queued row when its Spec ID and Plan ID name the committed native pair. |
| U01 | The sprint records its deliverable as one work item. | Check accepts one queued feature or chore row bound to the committed native pair; the prompt asks for it. |
| U04 | `init` now defaults to HTML knowledge with no task board. | Both children ask for `--format markdown`, which keeps the Markdown context and greenfield plans this Check reads. |
| U06 | `/preview` was retired in codeArbiter 3.3.0. | The lesson reviews its bounded diff with read-only `ca-review`; the Check contract is unchanged. |
| P04 | `/btw` was retired. | The no-install context question is asked of the agent directly. |
| U02 | `/metrics` was retired; the H-05 refusal line is byte-identical (run). | Prose no longer mentions metrics output. |
| F03 | The originless dotted row still uses the task-writer compatibility path; the 3.8.3 start flip is unchanged (run). | None. |
| F01, F02, P02, P06, P07, P08, U03, U05, U07 | Policy preambles, HTML-knowledge alternates, and removed `/btw` pointers. | None. |

The source map drops the deleted `commands.md`, `preview.md` and `metrics.md` and
adds the work facade for the lanes above, `review.md` for U06, and the init
scaffolder and Markdown decomposition reference for U04. The native planning pins
take the artifact bridge and release manifest from the published 3.8.3 payloads.

Evidence limits: the board shapes are produced by the real 3.8.3 work facade and
task writer, and the native suites ran against the published Codex 0.26.3
payload. Whether a live agent working through commit-gate produces those exact
shapes is not qualified here. commit-gate's legacy board classifier rejects an
`attach` on an existing row and a start-then-complete in one commit
(arbiterForge/codeArbiter#1089), so the Checks accept only the shapes it keeps today.

## October 2026 lesson review

Baseline Academy: `c8e5f0a4c58df0997ba079fafbbe5768974c3bff`.
Reviewed plugin source: `0badb588dc1179b06e13db1ca5322590962b586a`.
Released producer cohort: `849a3cf6fa6f4fdf3256cd3095c92499e9c4ec77`
(Claude 3.2.6, Codex 0.20.6, Pi 0.21.6).
Preview 0.33 is a source candidate, not a publication claim.

| Lesson | Reviewed learning outcome and correction |
| --- | --- |
| F01 | Own a safe practice fork; distinguish Academy readiness from plugin Doctor. |
| F02 | Read current state and its sources; distinguish state from an assertion of freshness. |
| F03 | Start a task through its owner and commit the work with the board change. |
| F04 | Observe a meaningful failing regression, repair it, and commit test plus code only after GREEN. |
| P01 | Turn a concrete feature outcome into native HTML specification and plan, then deliver the bounded change. |
| P02 | Read the diff and commit evidence; distinguish offline practice receipts from a real hosted PR. |
| P03 | Make a real architectural choice; retain attribution and the current separate source-bound acceptance ledger. |
| P04 | Examine a frozen dependency candidate without installing it or claiming current package safety. |
| P05 | Take one checkpoint finding through a GREEN repair and a receipt that does not invent a RED commit. |
| P06 | Reinspect contradicted context and adopt/update its provenance through the native writer; preserve unrelated work. |
| P07 | Threat-model a proposed flow; prioritize gaps and use current advisory verdicts with named constraint owners. |
| P08 | Inspect repository hygiene and preserve unique work; distinguish fetch from destructive cleanup. |
| U01 | Run a bounded sprint from native HTML plans under the original request; record actual material decisions only. |
| U02 | Observe a real guard refusal and the preserved audit trail; do not infer enforcement from a report alone. |
| U03 | Distinguish refactor, chore, and local release evidence from publication authority. |
| U04 | Initialize isolated greenfield and brownfield children; inspect or resume the current initialization owner. |
| U05 | Diagnose without manufacturing state changes; keep only useful spike findings and honor a real conflict stop. |
| U06 | Treat preview as advisory; distinguish historical labels and separately installed capabilities from actual commands. |
| U07 | Deliver a known defect through the fix lane and a real PR to the learner's fork. |

Every lesson includes a practical purpose and a transfer prompt for the learner's
own project. Recovery now distinguishes live configuration from invalid committed
history: preserve a failed exact-history attempt and use numbered Reset.

## Greenfield decomposition format

codeArbiter now records greenfield decomposition as HTML knowledge by default, and
`init` creates HTML context with no task board. The Markdown route remains supported
through `--format markdown` and the decompose skill's Markdown reference, which
still produces the three Markdown plans U04 checks. U04 therefore asks for the
Markdown format explicitly. Moving U04 to the HTML default needs a Check that
reads the knowledge and decomposition HTML; that is a separate Academy change.

## Validation of this candidate

Local validation used Windows, Python 3.14, and the installed Codex 0.20.6
producer. The focused suites passed: 228 curriculum/publication checks;
155 rendered-site/action checks; 15 workflow-boundary checks; 15 sprint/debug
checks, including U01 through the public checkpoint evaluator; and nine current
ADR/context/source-drift checks. These suites overlap and their counts should not
be added. Native feature/sprint reader tests and the current threat-model
exercise also passed.

Four additional producer-integrity tests independently altered disposable external
copies of the bridge, Git helper, release manifest, and native binary. Each was
rejected before worker execution. Disabling each corresponding digest check in an
isolated in-memory module made its test fail; all four focused mutants were caught.
The installed producer and production source were unchanged by these probes.

The final bundle was built twice with identical bytes. Its installer checksums
matched, and the isolated Windows installation/Doctor test passed. The preview
site built and passed its static contract check. Python syntax/indentation checks,
Git whitespace checks, and credential rules over changed working files passed.

Independent curriculum review covered all 19 lessons. Executable-boundary review
and follow-up checks covered the native reader, current governance records, and
source-drift mechanism; the final instructional remediation had no findings.
This is focused local evidence. Full repository test discovery, hosted CI,
cross-host qualification, and publication have not been completed for this
candidate. No release tag or hosted site was changed.
