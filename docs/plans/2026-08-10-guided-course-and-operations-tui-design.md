# Arbiter Academy guided course and operations TUI design

> Historical design record. The current public contract is the versioned publication manifest and
> the checked-in lesson actions. The local operations TUI remains deferred; its only approved future
> boundary is setup, Check, reset/retry, and lesson change. Do not treat older console examples in
> companion planning files as a shipped public interface.

**Date:** 2026-08-10
**Status:** approved
**Decision owner:** project owner
**Scope:** learner-facing Academy site, lesson contract, bootstrap, and local operations TUI

## Outcome

Arbiter Academy teaches a newcomer from an unfamiliar fork through real CodeArbiter work without requiring them to infer who acts, where a command belongs, or what success looks like. The website is the course. A narrow local TUI makes repository setup and lesson-state operations safer and easier; it does not duplicate the course.

The first redesigned public slice is Home, Recovery, and F01. Preview 0.4 keeps F02–P07 runnable as explicitly labeled reference lessons while guided migration proceeds in dependency order: F02–F04, then P01–P07. A runnable verifier never by itself makes a lab guided.

## Product boundary

### Website: the teaching surface

The site owns:

- concepts, prerequisites, explanations, and lesson prose;
- numbered actions and explicit stop points;
- actor and execution-surface labels;
- host and operating-system command variants;
- copy controls, expected results, checkpoints, and recovery guidance;
- links that open the matching website lesson and describe supported non-interactive commands;
- truthful availability sourced only from the reviewed publication manifest.

The website cannot launch a local full-screen process. It does not publish a TUI launch command until the integrated TUI provides that parser-supported route. Browser-to-TUI custom protocols, localhost daemons, and deep links are explicitly out of scope. The TUI may open a fixed website lesson URL.

### Academy TUI: the operational surface

The full-screen TUI V1 owns exactly four learner actions:

- setup: select the repository and published lab, present Doctor/readiness state, and prepare the selected lab;
- Check: verify evidence and show the bounded result;
- reset/retry: preserve the current attempt and prepare the next safe attempt;
- lesson change: select another published lesson and open its matching website page.

Inspect remains part of the read-only Doctor snapshot rather than a separate operation. Update, progress, arbitrary commands, and return-to-base remain non-interactive CLI responsibilities and are not exposed as TUI actions.

The first TUI release excludes installer self-management, arbitrary shell execution, lesson prose, Markdown rendering, free-form command entry, return-to-base, and whole-tool teardown. Installer-managed teardown follows only after its lifecycle contract is proven.

Within the course, setup means selecting a repository and lesson, reading the Doctor snapshot, and preparing an attempt. Check and reset/retry own the evidence and preservation lifecycle. Lesson change moves between published lessons without owning their prose. Leaving an attempt through return-to-base stays in the non-interactive CLI. Installing or deleting the Academy executable is a separate bootstrap lifecycle and cannot safely be owned entirely by the running TUI.

### Existing CLI: the automation and recovery surface

Existing non-interactive commands remain supported. The CLI and TUI both call a shared typed `AcademyOperations` layer. UI event handlers do not call low-level Git helpers or recreate authority decisions.

## Lesson contract

Every actionable step is structured data with these fields:

- stable step identity and sequence;
- actor: `learner`, `academy`, or `agent`;
- surface: `browser`, `native-terminal`, `harness`, or `academy-tui`;
- supported host and operating-system variants;
- instruction and optional rationale;
- command payload and copy policy, when applicable;
- expected observable result;
- recovery action or safe stop condition;
- evidence/checkpoint relationship.

Rendered steps use human labels such as `You · Browser`, `You · Native terminal`, `You · Codex harness`, `Academy TUI`, and `Agent`. Native-terminal commands and harness passthrough commands are separate variants. A shell command shown for a harness begins with the required `!`; a `$ca-*` command never does.

The renderer must reject ambiguous action content. A fenced command cannot be called “copyable” unless its actor, surface, command, and copy policy are declared. Numbered actions are supported and required for runnable lesson flow.

Each lesson keeps explanatory Markdown and adds one versioned JSON action manifest. Markdown references stable action IDs; the generator requires a one-to-one match between references and manifest actions. This keeps prose pleasant to author while making actor, surface, command variants, expected results, and recovery machine-verifiable without introducing a YAML or Markdown runtime dependency.

## Lesson page anatomy

Each lesson follows one educational rhythm:

1. **Know before you begin** — only prerequisites already taught or explained in place.
2. **What you will prove** — one concrete learner outcome.
3. **Prepare safely** — installed Academy operation with expected repository state.
4. **Practice** — numbered steps with actor/surface badges and selected host/OS variants.
5. **Recognize success** — visible outputs and evidence, not “it should work” prose.
6. **Check** — installed Academy verification and bounded failure guidance.
7. **Recover or continue** — reset/retry in the TUI, return to base through the non-interactive CLI, and use lesson change to open the next website lesson.
8. **Understand the mechanism** — optional deeper implementation detail after the core exercise.

Command cards provide a copy button, accessible copied/error status, keyboard focus, wrapping or bounded horizontal scroll, and no hidden command mutation. Expected output is visually distinct from input and is never copyable as a command.

Host and operating-system selection is a progressive enhancement. The page initially renders every applicable variant with clear labels. Local JavaScript may remember the learner's selection in browser-local storage and collapse the other variants, but the complete lesson remains usable when JavaScript, clipboard permission, or local storage is unavailable. Copying uses the Clipboard API when permitted and a visible manual-selection fallback otherwise. Scripts are committed local assets with no inline handlers and no runtime network calls.

## Home, Recovery, and F01 vertical slice

The first slice proves the whole system before broad rewriting:

- explain a GitHub fork in plain language and show the exact browser action;
- explain `origin` and `upstream` before asking the learner to inspect or repair them;
- offer one reviewed PowerShell installer and one reviewed POSIX installer, each with a visible source-review link and a safer download/verify alternative;
- defer the Academy TUI launch card until the integrated parser route exists;
- guide repository setup, Doctor presentation, F01 preparation, remote repair, Check, reset/retry, lesson change, and the separate non-interactive return-to-base handoff;
- show native-terminal and selected-harness variants with correct `!` passthrough;
- provide exact expected states and reversible recovery at every risky transition;
- ensure a first-time learner never needs knowledge not taught by the current or earlier step.

F01's required evidence lifecycle is explicit and cannot be collapsed into a generic “check” action:

1. prepare the numbered `academy/F01-fork-clone-doctor/<attempt>` branch;
2. inspect and repair `origin`, `upstream`, disabled upstream push, and `remote.pushDefault`;
3. invoke the selected CodeArbiter host's Doctor so the learner sees host-level diagnosis;
4. run Academy Doctor for F01, which writes `.codearbiter/reports/academy/F01-doctor.json`;
5. inspect the bounded report, stage it, and commit it on the attempt branch;
6. require a clean worktree and run the externally installed Academy Check;
7. show the accepted evidence or route the learner to the exact failed precondition.

The page teaches why the learner commit is evidence, who creates the report, and which commands the learner runs. Before preparation the learner is on clean `main`; after preparation and evidence commit they are on the numbered attempt branch with a clean worktree. Doctor failure does not authorize a commit. Check failure preserves the committed attempt for diagnosis.

Recovery becomes an operational decision tree rather than generic advice. It diagnoses dirty state, unsafe remotes, wrong branches, and existing attempts, then offers only bounded reversible actions. It never tells a novice merely to “make the repository clean.”

## Operations architecture

`AcademyOperations` is the only application-facing orchestration boundary. It returns typed state and result objects suitable for both text rendering and TUI rendering. It delegates to the existing trusted modules for Doctor, publication, scenario preparation/reset, and checkpoint evaluation. Inspect composes those read-only state objects for the Doctor presentation rather than adding an operation.

The TUI layout is intentionally restrained:

- left pane: published labs grouped by track, selection, and prepared-attempt marker;
- right pane: repository readiness, current branch, available actions, and last bounded result;
- footer: keyboard help and current context;
- narrow terminal: one-pane layout;
- below the tested minimum dimensions: readable non-interactive fallback instead of clipped UI.

The TUI trusts installed verifier authority and the installed publication manifest. It never uses the learner checkout as the source of lab eligibility, titles, commands, or lesson URLs. Lesson change resolves from a fixed Academy origin plus an installed manifest path, not learner-controlled content.

“Return to course base” is a bounded non-interactive CLI operation: from a clean canonical Academy attempt, switch to `main` while preserving the attempt branch. It is not reset, does not discard work, and is not a TUI action.

Only one mutating TUI operation may run at a time. While an operation is active, incompatible actions are disabled with a visible reason. Setup/prepare and reset/retry require a preflight result immediately before mutation. Destructive-looking actions require a confirmation that names the repository, current branch, resulting branch, and any archive ref; cancellation performs no writes. The non-interactive return-to-base command enforces its own equivalent preflight outside the TUI.

## Bootstrap and lifecycle

The initial installer must remain outside the TUI because an uninstalled application cannot launch itself. Both platform scripts:

- are pinned to a named Academy release and reviewed hashes;
- install into a user-owned Academy tools directory;
- install only manifest-owned files;
- fail closed on pre-existing conflicting paths;
- roll back partial installation;
- install from a reviewed offline wheel set;
- finish by launching Doctor; a TUI launch is added only with the integrated parser-supported route;
- have committed tests that execute the documented commands.

The fast path is an immutable release-asset URL piped to PowerShell or POSIX shell, with the exact script source linked beside it for review. It does not claim to verify its own hash. The verify-first path downloads the script and checksum separately, validates the pinned digest locally, then executes the verified file. Redirects, mutable branch URLs, and package-index resolution are rejected.

Whole-tool teardown is deferred. On Windows, a running process cannot safely delete its own executable. A future TUI action may write a validated teardown plan, exit, and hand control to the installer-owned launcher, which removes only manifest-owned paths.

The first-release TUI provides Check and reset/retry while preserving the attempt branch. Return-to-base remains a non-interactive CLI handoff. Neither path equates leaving a lesson with deleting learner work.

Reset/retry is enabled only on the matching clean canonical attempt branch. Uncommitted work is not archived. If the worktree is dirty, the TUI disables reset and explains that the learner must either commit the intended work through the lesson's governed path or cancel and inspect the read-only Doctor snapshot; the TUI does not offer a discard shortcut. Confirmation names the old attempt, archive ref, and new attempt branch. A failed reset rolls back its owned mutations or stops with the original ref reachable. The separate return-to-base CLI command requires the same clean/current-attempt preflight, preserves the attempt branch without creating an archive, and switches only to the validated course `main`.

## TUI dependency decision

Use a pinned `prompt_toolkit` release, subject to `$ca-add-dep` review and explicit reconciliation of the current standard-library-only runtime contract. Its narrow full-screen primitives, Windows support, resize handling, and deterministic input/output test harness fit this TUI better than a bespoke raw-terminal implementation.

The accepted cost is one direct dependency plus its pinned `wcwidth` dependency, offline wheels, license/provenance evidence, and Windows CI. Textual is not selected because its larger rendering and Markdown-oriented stack solves problems the website already owns. Stdlib `curses` or raw VT handling is not selected because cross-platform input, resizing, alternate-screen behavior, and Windows support would become Academy-maintained infrastructure.

If dependency review fails, implementation stops at the shared operations layer and existing CLI; it does not silently fall back to a custom terminal renderer.

Implementation of the prompt-toolkit TUI remains blocked until `$ca-add-dep` accepts both `prompt_toolkit` and `wcwidth`, `$ca-adr` records the user-attributed runtime-policy change, and the accepted ADR is reconciled into `.codearbiter/tech-stack.md`, security controls, packaging, and the offline wheelhouse. Approval of this product design is not a dependency or ADR bypass.

## Supported command matrix

Version 1 supports these explicit variants:

- operating systems: Windows with PowerShell 7+, macOS with POSIX shell, and Linux with POSIX shell;
- CodeArbiter hosts: Claude Code (`/ca:*`), Codex (`$ca-*`), and Pi (`/ca-*`, with the documented `/skill:ca-*` fallback when direct dispatch is unavailable);
- native shell commands: raw command text in the native-terminal card;
- harness shell passthrough: the same shell command prefixed by exactly one `!` in the matching host card;
- CodeArbiter invocations: host-native syntax with no `!` prefix.

Every command-bearing action declares which cells of this matrix it supports. The generator rejects missing variants, a shell command in a harness card without `!`, a host-native command with `!`, or commands whose copied bytes differ from their visible bytes.

## Publication truth model

The publication manifest gains a versioned lesson contract and separate states:

- `runnable_labs`: installed verifiers and scenarios accepted for the release;
- `guided_labs`: the subset whose public lesson passes the current `lesson_contract_version`;
- `coming_next`: verifier or curriculum work not runnable in the release.

During migration, F02–P07 may remain runnable while explicitly labeled “reference lesson · guided rewrite pending.” F01 is the first guided lab. The site and TUI must show the distinction and must not use a runnable verifier as evidence of guided readiness. Transitional manifests require `available_labs == runnable_labs`, `guided_labs ⊆ runnable_labs`, and disjoint runnable/coming-next sets. All site and TUI labels derive from the installed authoritative manifest. After all currently published lessons migrate, the compatibility `available_labs` field may be removed only through a versioned schema change.

## Accessibility and visual standard

The Academy adopts the codeArbiter design-system contract without coupling builds or copying page structure. The visual direction is evidence-led, editorial, and calm:

- typography and spacing establish learning hierarchy before decoration;
- custom illustration is used only where it explains a real mechanism;
- no generic dashboard card grids, ornamental gradients, fake terminal output, or decorative status metrics;
- actor/surface roles are distinguishable without relying on color;
- all controls have keyboard and visible-focus behavior;
- copied/error/live statuses use appropriate accessible announcements;
- reduced motion, high zoom, narrow screens, and long commands are tested;
- local fonts and local assets only at learner runtime.

Training media is optional enhancement, never a substitute for steps. Any GIF or video must be captured from the real Academy and CodeArbiter workflow, include captions or a transcript, disclose the exact version shown, and have a text-complete lesson beneath it. Simulated or decorative fake terminal sessions are prohibited.

## Verification strategy

Implementation proceeds test-first in these cells:

1. characterize existing CLI authority and publication behavior;
2. extract `AcademyOperations` with exact CLI parity;
3. add lesson-schema validation and renderer RED tests;
4. ship Home + Recovery + F01 with copy, host/OS, actor/surface, expected-result, responsive, and accessibility tests;
5. pass a novice-path usability review using only knowledge taught in the slice;
6. vet and package `prompt_toolkit` and `wcwidth` through `$ca-add-dep`;
7. implement pure TUI state/reducer tests, then real-repository operation tests;
8. add prompt-toolkit setup/Check/reset/lesson-change navigation, confirmation, cancellation, resize, and non-TTY tests, plus separate non-interactive update, progress, and return-to-base coverage;
9. add adversarial authority, unsafe remote/config, dirty state, URL tampering, path escape, and interrupted-operation tests;
10. add Windows and Ubuntu Python 3.11/3.12 hosted cells;
11. migrate remaining published lessons in dependency order;
12. publish the next preview only from exact-head green evidence.

Every public slice receives visual checks at desktop, narrow/mobile, 200% zoom, keyboard-only, and reduced motion. Generated HTML validation proves command/button identity and rejects unavailable lab links.

The novice-path review is a scripted cold-read from the public home page through accepted F01 evidence. Two independent reviewers receive only the prerequisite statement and must identify every action's actor and surface, complete every step without an unstated command, and explain every introduced term before first use. Any unexplained prerequisite, ambiguous actor/surface, incorrect copy payload, or missing expected result is a release blocker.

Visual acceptance records screenshots at 1440×900, 1024×768, 390×844, and 320×568; repeats the lesson at 200% browser zoom; traverses all controls keyboard-only; and tests reduced-motion behavior. Review compares the evidence against the codeArbiter design-system contract and explicitly rejects clipping, overlap, inaccessible focus, generic dashboard/card repetition, fake terminal content, and decorative hierarchy that competes with the lesson.

## SMARTS rationale

The website-first split scores best because it gives the learner one authoritative teaching surface, keeps operational state close to the repository, preserves scriptable recovery, and avoids embedding a second content renderer in the terminal. The strongest alternative—a TUI-first course—would improve local continuity but duplicate content, accessibility, linkability, and visual systems while making screenshots and browser concepts awkward. A raw-terminal implementation saves a dependency but transfers substantially more cross-platform and security surface into the project. The approved design accepts the smaller vetted dependency in exchange for a narrow, testable UI and keeps all richer teaching in the site.

## Release acceptance

The redesign may publish when a new learner can, using only the public site and installed Academy tooling:

- understand and create a fork;
- clone and identify `origin`/`upstream` safely;
- install with one reviewed command or the documented verify-first alternative;
- launch Doctor and select/prepare F01;
- distinguish browser, native terminal, harness, Academy, and agent actions;
- copy the correct command variant, including required harness `!` passthrough;
- recognize expected state and failure state;
- check evidence, understand that only committed clean attempts can be archived, reset/retry with the old commit reachable, use the non-interactive CLI to return to base, and resume later;
- identify exactly which labs are guided and runnable, runnable with a reference lesson whose guided rewrite is pending, or only coming next.

No later lab becomes public merely because its verifier has merged.
