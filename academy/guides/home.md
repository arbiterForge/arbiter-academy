# Start here

Arbiter Academy is a practice course for codeArbiter. You work in a real Git repository that belongs to you, so every lesson can produce real commits and evidence without sending changes to the official Academy repository.

Before F01, you need a GitHub account, Git, Python 3.11 or newer, a supported codeArbiter host, and an internet connection. [Choose and install your CodeArbiter host](https://arbiterforge.github.io/codeArbiter/getting-started/choose-your-host/) first, then return here to create your practice fork. Choose Claude Code, Codex, or Pi (Feature Forge preview). Pi requires project trust; if direct `/ca-*` dispatch is unavailable, use the documented `/skill:ca-*` fallback. Use a Browser to create the GitHub copy. Use a Native terminal for Git and installation. The website remains the course. A narrow operations TUI for setup, Check, reset, and lesson changes will be published only after it clears its own acceptance evidence.

## Complete these five setup steps before F01

Complete these steps in order before Prepare in F01:

1. [Create your practice fork](#create-your-practice-fork).
2. [Clone it to your computer](#clone-it-to-your-computer).
3. [Enter the cloned repository](#enter-the-cloned-repository).
4. [Verify and install the Academy tools](#verify-and-install-the-academy-tools).
5. [Run readiness checks](#run-readiness-checks).

## What the Academy changes

A repository is a project's files plus its Git history. The official repository belongs to arbiterForge and stays read-only for learners. A fork is your account's copy of that repository on GitHub. A clone is the working copy stored on your computer.

Git gives remote repositories short names. In this course, `origin` points to your fork. `upstream` points to `arbiterForge/arbiter-academy`. You push only to `origin`. You use `upstream` to compare your fork with the reviewed Academy source.

## Create your practice fork

{{action:home-fork}}

## Clone it to your computer

Choose a folder where you keep projects, open a Native terminal there, and use the command for your operating system. Replace `your-account` with the GitHub account that owns your fork.

{{action:home-clone}}

The clone command creates a new `arbiter-academy` folder but leaves the Native terminal in its current folder. Enter the clone before running any Academy command.

## Enter the cloned repository

{{action:home-enter-clone}}

## Verify and install the Academy tools

Change the Native terminal's current directory to the clone before installing. The verified installer stores the reviewed Academy tools outside the learner repository. The clone remains lesson input rather than part of the verifier.

{{action:home-install}}

## Run readiness checks

Run the installed Academy Doctor command once to inspect this checkout. It reports the Python and Git versions, repository root, clean or detached Git state, remotes, effective push remote, upstream push protection, and whether codeArbiter is activated and initialized. It cannot verify GitHub fork lineage offline.

{{action:home-doctor}}

## Choose your first lesson

Doctor does not need to pass before F01 when its only failures are the expected fresh-clone remote findings. A new fork clone may report a missing `upstream`; F01 teaches the remote repair. Before Prepare, you do need clean `main`, an `origin` whose fetch and push target your non-official `arbiter-academy` repository, and effective push routing to `origin`.

Start with F01, Fork, clone, and Doctor. Read the complete F01 page in the Browser and follow its ordered actions. Do not repair the remaining F01 evidence steps from this page. Keep the website open as the lesson surface and run its copyable installed Academy commands in the Native terminal.

## Course status

**Current release inventory.** The runnable lesson catalog below is generated from the exact public release manifest. Every listed lesson has an explicit actor, surface, expected result, recovery path, and evidence boundary.

**Course boundary.** U01-U07 are published in this release. Graduation is available after all 19 Academy Checks pass in the same repository.

## Get help

Stop when the observed result differs from the lesson. Recovery guidance helps you preserve the attempt and choose a safe next action. Questions and course feedback belong in Academy GitHub Discussions.
