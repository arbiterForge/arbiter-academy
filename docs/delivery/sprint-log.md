# Arbiter Academy delivery sprint log

This is the append-only delivery record for the public `arbiterForge/arbiter-academy`
repository. It records real maintainership decisions. It is deliberately separate from
`.codearbiter/sprint-log.md`, which is a fictional Workshop Queue teaching fixture.

## SD-ACA-001 - Bind F02 orientation evidence to one preserved attempt - confidence: high

- Date: 2026-08-11
- Point: Whether F02 should describe the existing permissive orientation checkpoint or
  strengthen the checkpoint before the lesson becomes public.
- Options: preserve the permissive checkpoint and narrow the lesson; require only a
  valid orientation record; require one orientation-record commit, an unchanged prepared
  context blob, and a clean worktree.
- SMARTS: Security, Maintainability, Reviewability, Testability, and Safety favor the
  bounded attempt. A public lesson must prove the evidence boundary it teaches, preserve
  a failed attempt for recovery, and reject unrelated or post-orientation state.
- Chosen: strengthen F02 before publication. Check will require exactly the orientation
  record in the learner evidence commit, the prepared context bytes unchanged, and a
  clean worktree at verification time.

## SD-ACA-002 - Publish each guided slice as an immutable preview - confidence: high

- Date: 2026-08-11
- Point: Whether F02 may change the already published Preview 0.4 release identity or
  should receive a new immutable preview release.
- Options: mutate Preview 0.4; delay F02 until the complete course; publish F02 as
  Preview 0.5 with refreshed checked-in installers and release assets.
- SMARTS: Security and Safety reject mutable installer bytes under an existing release
  identity. Maintainability and Reviewability favor a small, named public slice that
  maps one publication manifest to one verified asset set. Testability remains bounded
  because F02 promotion can prove its own route and verifier without waiting for F03.
- Chosen: publish F02 only as a new immutable Preview 0.5 release after its guided
  page, verifier, assets, and hosted exact-head checks are accepted.

## SD-ACA-005 - Verify the immutable release from its tagged source - confidence: high

- Date: 2026-08-11
- Point: Whether post-release Academy lesson work should rebuild Preview 0.5 installer assets from the mutable candidate, or whether Pages should verify the already-published tagged source while rendering the reviewed candidate site.
- Options: regenerate Preview 0.5 installer checksums from every candidate; keep the candidate-versus-tag release-bound path block; verify the immutable tagged source and public release assets exactly, while allowing later reviewed candidates whose public manifest still exposes only accepted lessons.
- SMARTS: Safety and Security favor retaining tag ancestry, immutable-release state, authenticated and public asset downloads, checksum validation, and byte-for-byte reproduction from the detached tag source. Maintainability favors one authority for a published release rather than a mutable checkout. Reviewability favors tests that materialize the tag and prove candidate-source rebuilding cannot return. Simplicity and Speed favor removing the overbroad post-tag path denylist so accepted non-routable lesson work can land without claiming a new release.
- Chosen: Pages verifies Preview 0.5 from its immutable tag source and assets. The candidate must descend from that tag, but later Academy source changes do not retarget released installers or alter their byte identity.

## SD-ACA-007 - Keep private candidate work separate from immutable release assets - confidence: high

- Date: 2026-08-12
- Point: Whether a non-routable Academy lesson change must rebuild the current preview installer bytes, after PR #19 correctly showed that a candidate wheel has a different bundle digest while Preview 0.6 remains immutable.
- Options: require a new preview for every packaged source change; weaken the builder digest check; reproduce the already published preview from its immutable tag while separately proving that a private candidate has not entered the public manifest.
- SMARTS: Safety and Security retain immutable tag ancestry, byte-for-byte asset reproduction, and the builder's exact installer digest check. Maintainability and Speed let reviewed private guided content merge without release churn. Reviewability and Testability require one tagged-source fixture, a private-candidate mutation regression, and a fresh preview whenever public routes or installable bytes change.
- Chosen: published-release asset and installer-behavior tests materialize the current immutable tag. Candidate builder tests remain fail-closed. A new preview is required for any public manifest route, installer, or installable-payload change; non-routable guided content may merge only while the candidate manifest still keeps it unavailable.

## SD-ACA-008 - Clarify candidate drift versus published release payload - confidence: high

- Date: 2026-08-12
- Point: Whether SD-ACA-007's payload boundary could be read to require a new preview for a private lesson edit that changes only a hypothetical future candidate wheel.
- Options: treat every candidate bundle-digest change as published-payload drift; allow an ambiguous exception; distinguish the immutable published release payload from mutable candidate source payload.
- SMARTS: Safety and Security keep installer digest checks fail-closed for the published tag and require a new preview for any released installer, release bundle, or public route change. Maintainability and Speed permit private non-routable source development without pretending its future wheel is already public. Reviewability and Testability bind Preview 0.6 to its reviewed tag commit, reject missing or retargeted tags, and prove a private candidate mutation remains outside the public manifest.
- Chosen: a private source edit may change a candidate-only future wheel without release churn while it remains non-routable. A new preview is required before any change becomes part of the published release payload, installer bytes, or public lesson catalog.

## SD-ACA-009 - Release F03 as the next coherent public slice - confidence: high

- Date: 2026-08-12
- Point: Whether to wait for the private practitioner drafts or publish F03 once its guided action contract and clean-worktree Check are accepted.
- Options: wait for the whole Foundation and Practitioner tracks; publish F03 with a fresh immutable preview while F04 and P01-P08 remain status-only; expose private drafts before their prerequisite closure is ready.
- SMARTS: Safety and Security keep unfinished lessons non-routable and bind F03 to one exact board-only commit with no non-ignored worktree state. Reliability and Testability favor a separately verified action contract, causal board-boundary tests, and a fresh immutable release identity. Maintainability and Simplicity keep one release manifest authoritative for available, runnable, guided, and coming-next lessons. Availability and Speed give learners a complete F01 to F03 path now instead of withholding accepted training behind unrelated drafts.
- Chosen: promote only F01, F02, and F03 in Preview 0.7 after exact-head review and hosted CI. F04 and P01-P08 remain explicit non-linking coming-next status until each has a complete guided contract and accepted prerequisite chain.

## SD-ACA-004 - Encode F04 as an executable evidence sequence - confidence: high

- Date: 2026-08-11
- Point: Whether F04 should remain a prose walkthrough or use the Academy action contract to guide and verify a real red-to-green, two-commit fix.
- Options: retain raw prose; make the operations TUI the primary lesson surface; publish a website-first structured lesson with terminal, harness, and CodeArbiter actions explicitly separated.
- SMARTS: Safety and Security favor an isolated prepared attempt, a test-only commit before the repair, a service-only repair commit, and a Check that rejects broad or unreachable changes. Maintainability and Testability favor one manifest shared by the rendered guide and contract tests. Reviewability favors visible actor, surface, expected result, evidence, and recovery fields for every learner action. Simplicity and Speed keep the TUI limited to attempt lifecycle operations rather than a second instructional interface.
- Chosen: author F04 as a website-first, structured twenty-one-action lesson; native terminal commands, harness prompts, and agent CodeArbiter commands are unambiguous, while the TUI remains limited to attempt lifecycle operations.

## SD-ACA-012 - Make verified installer execution the sole beginner route - confidence: high

- Date: 2026-08-12
- Point: Whether the public Academy entry page should keep a direct remote-script pipe for speed, present verification as optional reference material, or require checksum verification before every first-run installer execution.
- Options: keep `irm | iex` and `curl | sh`; offer verification beside a fast default; download the immutable installer and its checksum, verify the bytes locally, then execute that local file.
- SMARTS: Security and Safety favor binding first-run code to an immutable release checksum before execution. Reliability and Testability favor one explicit action sequence that fails before code runs on a mismatch. Maintainability and Simplicity favor the same action-card contract and recovery wording on all supported operating systems. Reviewability lets a newcomer inspect the exact versioned source and preserve a failing verification result.
- Chosen: the Home installer action now downloads the Preview 0.8 installer and its checksum, verifies the downloaded bytes, and only then executes the local installer. Direct remote-script piping is not a beginner Academy command.

## SD-ACA-013 - Bind beginner installer bootstrap to the immutable Git release tag - confidence: high

- Date: 2026-08-12
- Point: Whether the first-run route can trust an installer checksum fetched through the
  same arbitrary redirect path as the installer, or must establish the existing
  immutable release tag as its source boundary before execution.
- Options: keep two generic HTTPS downloads; embed redirect-following shell clients in
  every beginner command; fetch the canonical immutable source through Git and extract
  the reviewed installer locally before execution.
- SMARTS: Security and Safety reject a checksum that can be redirected with the payload.
  Reliability keeps the familiar Git prerequisite and its standard TLS transport.
  Maintainability and Simplicity reuse one tag-and-local-file shape on every platform
  rather than duplicating an HTTP redirect validator in learner commands. Reviewability
  and Testability retain an inspectable tagged source, a local extraction boundary, and
  rendered action-card checks. The immutable release workflow supplies the tag
  authority, while the installer independently verifies the released bundle.
- Chosen: the Home route fetches only the canonical immutable Preview 0.8 tag with Git,
  extracts the installer to a local temporary folder, and only then executes it. The
  release installer retains its own bounded redirect and bundle verification controls.

## SD-ACA-014 - Supersede the Preview 0.8 checksum-bootstrap record - confidence: high

- Date: 2026-08-12
- Point: Whether SD-ACA-012's initial checksum-download route remains an accurate
  description after security review identified that the checksum and installer shared
  one redirect path.
- Options: rewrite the earlier append-only decision; leave an inaccurate final route;
  retain SD-ACA-012 as historical context and explicitly supersede it with SD-ACA-013.
- SMARTS: Security and Accuracy require the public route to describe the immutable tag
  boundary actually used. Maintainability and Reviewability preserve the original audit
  record and attach one unambiguous correction rather than silently editing history.
- Chosen: SD-ACA-013 supersedes SD-ACA-012's chosen checksum-download route. Preview
  0.8 fetches the canonical immutable Git tag, extracts the installer locally, and then
  executes that local file; it does not download a checksum alongside the installer.

## SD-ACA-010 - Give P01 a bounded specification revision path - confidence: high

- Date: 2026-08-12
- Point: Whether a learner who finds a weak P01 draft specification should infer an informal recovery, restart the whole lesson, or receive a visible revision action that preserves the review boundary.
- Options: retain prose-only recovery; reset every imperfect draft; add one copyable learner-to-agent revision action that changes only the draft specification and stops for review.
- SMARTS: Safety and Security favor an explicit stop before planning, task transition, tests, production edits, or commits. Reliability and Testability favor one typed action contract with actor, surface, expected result, recovery, and evidence assertions. Maintainability and Simplicity preserve the existing final-state verifier and avoid a new TUI workflow. Reviewability and Availability give a first-time learner a concrete correction path without inventing approval evidence or waiting for Discussion feedback.
- Chosen: prepare P01 for Preview 0.9 with a bounded specification-revision action and explicit planned-release commands. It remains private until F04 is released and the complete Preview 0.9 manifest, installer, immutable tag, assets, and hosted verification are accepted.

## SD-ACA-011 - Keep P01 review branches inside the shared lesson contract - confidence: high

- Date: 2026-08-12
- Point: Whether P01's optional draft-revision path should receive bespoke visual treatment or remain a semantically explicit sequence of shared action cards.
- Options: introduce a P01-only diagram, artwork, or layout; leave the revision and proceed actions visually adjacent without branch labels; add short decision headings above the existing shared cards and lock their order in the course contract.
- SMARTS: Maintainability and Simplicity favor one renderer and action-card system across every lesson. Reviewability and Availability favor clear learner-facing conditions for revision versus proceed. Safety and Testability preserve the stop-before-planning boundary and prove the rendered source order without falsely treating either review path as authenticated approval. Speed avoids a visual subsystem that only one lesson needs.
- Chosen: P01 uses the shared guide and typed-action renderer. Its Practice section labels the concrete-correction and acceptable-draft branches before the existing revision and proceed cards; no bespoke art, diagram, animation, or lesson-specific layout is introduced.

## SD-ACA-015 - Publish P01 as the next immutable guided slice - confidence: high

- Date: 2026-08-12
- Point: Whether to keep P01 private until the remaining Practitioner track is complete, publish it through a one-off page, or promote it with F01-F04 as Preview 0.9 using the shared course contract.
- Options: wait for P02-P08; add a bespoke P01 public page; publish P01 as the fifth guided lab in a fresh immutable Preview 0.9 release while P02-P08 remain explicit coming-next lessons.
- SMARTS: Safety and Security require a fresh tag, installer digest, release asset set, and exact public manifest rather than altering Preview 0.8. Reliability and Availability favor releasing the complete F01-F04-to-P01 prerequisite path now. Maintainability and Simplicity keep one Markdown/action-manifest renderer, one responsive command-card pattern, and one visual baseline contract. Reviewability and Testability bind P01's actor, surface, review, recovery, and Check limits to rendered cards, deterministic screenshots, static artifact validation, and hosted exact-head verification.
- Chosen: publish F01-F04 plus P01 only in Preview 0.9 after the immutable tag, six release assets, hosted verification, and Pages deployment succeed. P02-P08 remain non-routable until their guided prerequisite closure is accepted.

## SD-ACA-016 - Promote the coherent P02 and P03 prerequisite closure - confidence: high

- Date: 2026-08-12
- Point: Whether P02 and P03 should remain private until all later Practitioner lessons are complete, ship independently in separate previews, or close their shared prerequisite chain together in Preview 0.10.
- Options: defer P02-P08 as one future block; publish P02 and P03 separately across two preview identities; publish F01-F04 plus P01-P03 as one coherent Preview 0.10 slice while P04-P08 remain explicit non-routable coming-next lessons.
- SMARTS: Safety and Security preserve immutable Preview 0.9 history and require a fresh release identity, installer digest, exact asset inventory, and no route for P04-P08. Maintainability and Simplicity preserve 0.x preview sequencing and use the shared Markdown/action-manifest renderer, responsive card system, and visual test loop without bespoke HTML, CSS, or JavaScript. Reliability and Availability favor closing P02's review-and-receipt workflow together with its P03 ADR prerequisite rather than exposing an incomplete handoff. Reviewability and Testability bind both public lessons to installed Preview 0.10 paths, canonical P03 manifest identity, exact route and package assertions, deterministic desktop/mobile snapshots, and static artifact checks.
- Chosen: publish exactly F01-F04 plus P01, P02, and P03 as available, runnable, and guided in Preview 0.10. Preserve Preview 0.9 as immutable history, keep shared rendering and release integrity intact, and defer P04-P08 as non-routable coming-next lessons.

## SD-ACA-017 - Promote the coherent P04 and P05 prerequisite closure - confidence: high

- Date: 2026-08-12
- Point: Whether to hold P04 and P05 until P06-P08 are complete, publish either lesson as an isolated route, or promote their complete prerequisite closure in one fresh preview.
- Options: defer P04-P08 as one final block; release P04 or P05 alone; publish F01-F04 plus P01-P05 in Preview 0.11 while P06-P08 remain explicit non-routable coming-next lessons.
- SMARTS: Safety and Security preserve immutable Preview 0.10 history and require a fresh tag, installer digests, exact asset inventory, and no P06-P08 route. Reliability and Availability favor releasing the complete usable P01-P05 chain now rather than withholding accepted learner practice. Maintainability and Simplicity keep Markdown content, typed action manifests, one renderer, and shared responsive cards as the only public lesson system. Reviewability and Testability bind the expanded route inventory to parser, rendered-site, static-artifact, and Linux browser visual baselines at desktop and narrow widths.
- Chosen: publish exactly F01-F04 plus P01-P05 as available, runnable, and guided in Preview 0.11 after independent review, hosted exact-head verification, an immutable tag, release assets, and Pages deployment succeed. Keep P06-P08 private and non-routable until their prerequisite closure is accepted.

## SD-ACA-018 - Integrate the P06 handoff privately before release - confidence: high

- Date: 2026-08-12
- Point: Whether P06 should retain agent-authored canonical JSON, be promoted before its public release boundary is complete, or gain a private local helper while Preview 0.11 remains unchanged.
- Options: retain the agent-authored handoff prompt; publish P06 with Preview 0.11; integrate a local helper and its guided action contract privately until the next accepted release.
- SMARTS: Safety and Security favor a helper that derives its candidate only from clean, committed Git objects; rejects a noncanonical two-commit recovery; never overwrites, stages, or commits learner evidence; and preserves the public publication gate. Reliability and Testability favor direct helper, CLI, action-contract, curriculum, renderer, and no-route regressions. Maintainability and Simplicity keep the shared Markdown and typed action-manifest renderer while limiting the TUI to command-line lifecycle support. Availability and Speed prepare the next coherent lesson without exposing an incomplete route, manifest, installer, or release identity.
- Chosen: integrate P06's handoff helper and current private action cards on top of Preview 0.11, but keep P06 non-routable and unavailable to the public release manifest until its later promotion gate is accepted.

## SD-ACA-019 - Publish the complete guided Practitioner closure - confidence: high

- Date: 2026-08-12
- Point: Whether to leave P06-P08 private, release them as isolated routes, or publish their accepted prerequisite closure in one fresh immutable preview.
- Options: defer P06-P08 while retaining Preview 0.11; publish P06, P07, and P08 across separate preview identities; publish F01-F04 and P01-P08 together in Preview 0.12 with no coming-next route.
- SMARTS: Safety and Security preserve immutable Preview 0.11 history and require a new tag, rebuilt installer digest, exact six-asset inventory, and a manifest that refuses unpublished Power User routes. Reliability and Availability favor the complete P01-P08 progression over three partial releases that interrupt a learner's prerequisite chain. Maintainability and Simplicity retain the shared Markdown-plus-typed-action-manifest renderer and derive page chrome, route inventory, and release label from the one Preview manifest rather than adding P06-P08-specific UI. Reviewability and Testability bind every promoted lesson to action-card, static-site, release-builder, checksum, and hosted browser evidence; the distinct UTC release epoch 1786838400 makes the immutable Preview 0.12 build reproducible without changing earlier release bytes.
- Chosen: publish exactly F01-F04 and P01-P08 as available, runnable, and guided in Preview 0.12 after focused cross-layer verification, one independent review, exact-head hosted CI, an immutable release, and Pages deployment. Keep U01-U07 non-routable and graduation unavailable until the full 19-lab course exists.
