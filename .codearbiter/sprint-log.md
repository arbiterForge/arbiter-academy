# Sprint log - Workshop Queue Academy fixture

Append-only. Historical records below are fictional Academy fixtures. Entries show
the SMARTS rationale learners inspect; they do not describe a live sprint.

## SD-01 - Keep assignment evidence local and linked - confidence: high
- Date: 2026-07-18 (fixture)
- Point: Whether assignment should simulate a remote queue or remain a local JSON workflow.
- Options: local JSON fixture; simulated remote service; defer the exercise.
- SMARTS: Reliable, Available, and Securable favor local JSON because it is
  inspectable offline and introduces no credentials or network boundary.
- Chosen: local JSON fixture, recorded in [ADR-0001](decisions/0001-json-storage-boundary.md).

## SD-02 - Use an explicit lifecycle - confidence: high
- Date: 2026-07-19 (fixture)
- Point: Whether assignment implies ticket state or state remains a visible field.
- SMARTS: Testable and Maintainable favor a visible state machine.
- Chosen: explicit states, recorded in [ADR-0002](decisions/0002-explicit-ticket-state-machine.md).
## SD-03 - Reconcile fixture chronology - confidence: high
- Date: 2026-07-30 (fixture record)
- Point: SD-01 and SD-02 retain their reset-scenario dates while their governing ADRs
  were formally recorded on 2026-07-30.
- SMARTS: Reliable and Reviewable favor preserving the original scenario records and
  appending their recorded-date relationship instead of rewriting append-only history.
- Chosen: The scenario dates remain teaching metadata; all formal decision, spec,
  plan, checkpoint, report, and done-task records use 2026-07-30.

## SD-ACA-007 - Bound U01 to an autonomous documentation sprint - confidence: high
- Date: 2026-08-12
- Point: Whether U01 should remain a private guide with no completion proof or gain a deterministic
  first verifier while the broader Power User route remains private.
- Options: keep the false-returning profile; accept arbitrary sprint artifacts; require one bounded
  documentation packet with a prepared brief, exact path boundary, append-only log, and clean history.
- SMARTS: Reliable and Testable favor the bounded packet because it proves durable repository facts
  without inventing approval or host telemetry. Maintainable favors the existing shared scenario,
  action-manifest, and Check layers. Available and Securable favor a local documentation change with
  no network, dependency, credential, or push requirement.
- Chosen: implement the bounded U01 source contract now and keep it private until packaging, routing,
  browser, and hosted-release acceptance establish a public lesson boundary.


## SD-ACA-008 - Promote U06 with repository-fact evidence only - confidence: high
- Date: 2026-08-13
- Point: Whether the public U06 lesson should preserve hand-authored preview telemetry or bind only durable repository facts after the real read-only ca-preview advisory step.
- Options: retain invented reviewer/scan fields; keep U06 private; publish the accepted two-commit candidate and Academy binding record while explicitly excluding invocation and telemetry claims.
- SMARTS: Reliable, Testable, and Securable favor the bounded repository record because it can be reproduced from committed state without claiming a host result. Available and Maintainable favor the existing installed Prepare/Check/Reset lifecycle and explicit public package inventory.
- Chosen: publish U06 in Preview 0.19 with real host-native ca-preview guidance, a public route, deterministic package assets, and U07 as the sole non-linking coming-next lesson.

## SD-ACA-009 - Promote the accepted U07 capstone as the complete course - confidence: high
- Date: 2026-08-13
- Point: Whether Preview 0.20 should keep U07 non-routable or publish the accepted real feature capstone and enable the complete course boundary.
- Options: keep a false unavailable status; expose a synthetic local PR receipt; publish U07 with the real feature lane, browser PR evidence, local-only Check boundary, and the immutable 19-lab release.
- SMARTS: Reliable and Testable favor the accepted guide, scenario, semantic Check, and public route because Check validates only durable repository facts while the guide labels the hosted PR as browser evidence. Available favors shipping the completed course without a new service. Securable favors fork-first remotes, preserved retries, and no fabricated hosted telemetry. Maintainable favors one versioned manifest and deterministic release assets.
- Chosen: publish U07 in Preview 0.20, make all 19 labs guided and runnable, enable graduation only after all 19 Checks pass in one repository, and preserve Preview 0.19 as immutable history.

## SD-ACA-010 - Rebind the complete course to an immutable maintenance release - confidence: high
- Date: 2026-08-14
- Point: Whether the Preview 0.20 copy correction should remain undeployed under a stale immutable tag or receive a new release identity with reproduced assets.
- Options: weaken the existing tag gate; leave current main unavailable; publish an exact Preview 0.21 release with the unchanged 19-lab inventory and deterministic installers.
- SMARTS: Reliable and Testable favor a new annotated tag because the release gate can compare its exact commit and six assets with a clean rebuild. Available favors making the corrected learner-facing copy installable. Securable favors preserving immutable 0.20 bytes and the existing authenticated asset verification. Maintainable favors one current release identity across manifests, commands, installers, tests, and site metadata.
- Chosen: publish Preview 0.21 with the existing accepted inventory, a new manifest, canonical bundle digest, and no runtime dependency or command-surface expansion.

## SD-ACA-011 - Publish visual and successor-guidance maintenance as a new immutable Preview - confidence: high
- Date: 2026-08-14
- Point: Whether to leave the accepted mobile navigation and successor-guidance fixes only on main or publish them under a new immutable Academy Preview identity.
- Options: repoint Preview 0.22; defer learners to the stale artifact; publish Preview 0.23 with unchanged 19-lab inventory and reproduced offline installers.
- SMARTS: Reliable and Testable favor a new tag because the exact commit, manifest, archive, installer checksums, and Pages output can be reproduced together. Available favors promptly exposing the accepted learner fixes. Securable favors retaining the immutable Preview 0.22 artifact and its pinned digest. Maintainable favors one current identity across the site, command cards, package data, workflow, and installer paths.
- Chosen: publish Preview 0.23 as the immutable maintenance release with the unchanged accepted inventory, no runtime network dependency, and preserved Preview 0.22 history.
