# P01 guided lesson design

## Purpose

Rewrite P01 so a learner can complete the feature-through-plan exercise without
confusing learner actions with work performed by their CodeArbiter agent. The
website is the primary course interface. The Academy command-line tool only
prepares, checks, resets, and changes lesson state.

## Learner paths

P01 teaches two honest ways to handle the specification review checkpoint.

### Solo practice

The learner is the reviewer in their isolated fork. They inspect the drafted
specification with a concrete checklist, then explicitly tell their agent to
continue. This is review rehearsal, not an externally authenticated approval.

### Collaborative practice

The learner requests or uses feedback in the Arbiter Academy GitHub Discussion,
then relays that feedback before telling their agent to continue. If feedback is
not available, the lesson directs the learner to the Solo practice path. It
never asks them to fabricate feedback or save an approval record that the
repository cannot prove.

## Guided action contract

The rewrite adds an action manifest for P01 and replaces the raw command blocks
with the established rendered action format. Every learner action has an actor,
surface, operating-system or host variant, copyable command where applicable,
expected result, recovery instruction, and durable evidence statement.

The guide uses the required eight headings: Know before you begin, What you
will prove, Prepare safely, Practice, Recognize success, Check, Recover or
continue, and Understand the mechanism. Native-terminal commands never begin
with an exclamation mark. Harness shell commands begin with exactly one. Agent
messages and CodeArbiter commands never do.

The agent first drafts the specification and stops. The learner chooses a
review path. Only after the learner sends a separate proceed instruction does
the agent derive the plan, start the staged task, write the regression, repair
the bounded behavior, and invoke the commit gate. The learner runs the listed
native-terminal verification commands and Academy Check.

## Evidence boundary

Check validates one final descendant commit with the required spec, derived
plan, task transition, focused regression, and bounded production repair. It
also validates the exact specification and plan shape, the regression and
repair data contract, and a clean worktree. It does not authenticate a human
approval, a GitHub Discussion response, or the order in which an agent ran
RED and GREEN commands. The lesson states that limit at the checkpoint rather
than implying a claim the verifier cannot support.

## Scope and promotion

P01 source material may be completed and reviewed now, but it remains
unpublished until its F03 and F04 prerequisites are accepted. Its publication
slice updates the preview manifest and exact generated-site inventories only
after that prerequisite chain is available. The known CodeArbiter taskwriter
lock issue remains an upstream promotion dependency, not a reason to weaken
the Academy Check.

## Acceptance checks

- The P01 guide is action-backed and has no raw learner command fences.
- Every command identifies its actor and surface, and copyable variants render
  for the supported hosts and operating systems.
- Both review paths are explicit before the continue instruction.
- The guide distinguishes review process from durable Check evidence.
- Existing P01 scenario and checkpoint semantics stay unchanged.
- Curriculum and rendered-site tests cover the new guide and action contract.
