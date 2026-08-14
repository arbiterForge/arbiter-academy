"""Fail closed when an Arbiter Academy Preview artifact is not self-contained."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(_REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPOSITORY_ROOT))

from academy_engine.lesson_actions import validate_action_resource_href


_SHA = re.compile(r"^[0-9a-f]{40}$")
OPERATING_SYSTEMS = frozenset({"windows", "macos", "linux"})
HOSTS = frozenset({"claude-code", "codex", "pi"})
_CSS_URL = re.compile(r"url\(\s*[\"']?([^\"')]+)")
_CSS_IMPORT = re.compile(
    r"@import\s+(?:url\(\s*)?(?:[\"']([^\"']+)[\"']|([^\"'()\s;]+))\s*\)?",
    re.IGNORECASE,
)
_EXTERNAL_URLS = {
    "https://codearbiter.dev/",
    "https://arbiterforge.github.io/codeArbiter/getting-started/choose-your-host/",
}


def _is_approved_external_url(target: str) -> bool:
    if target in _EXTERNAL_URLS:
        return True
    try:
        validate_action_resource_href(target)
    except ValueError:
        return False
    return True
_ASSET_SHA256 = {
    Path("assets/academy.css"): "ecd327758ad2d08529fabe942f8c3e27a55720a0187a46fcf5039b97977688b0",
    Path("assets/academy.js"): "92f31b44830bb18efb9e0176b048ea28b8344ad46eff85add4de8843627405dd",
    Path("assets/favicon.svg"): "49e2ee37ad5d86b700a4d10f74bd9586afe5dcd8dfbe8823a23a9c0f0088b018",
    Path("assets/fonts/jetbrains-mono-latin-wght-normal.woff2"): (
        "18be452724bfdc236c074ca94a249a7f41a86752c7d04ab258ce9ed5651f6a7e"
    ),
    Path("assets/fonts/manrope-latin-wght-normal.woff2"): (
        "a30ddcd349703aff7464c34bef3fffdff405ee50c113440d7c8693c02d210972"
    ),
    Path("assets/gate-mark.svg"): "ff6446d218cc0367141765bafd2840ed0ea703773f5d05c7ed36a9cb14ba6330",
    Path("assets/hero-gates.webp"): "95893d3b7dac3a84cb9641145509b10b0290587d5b9da456b27f85dd649b43be",
    Path("assets/logo.svg"): "4553873806ba21a9de652105d3330626b1301eefe50eb7d61a1f3f7efacb768a",
}
_ALLOWED_HTML_ATTRIBUTES = {
    "html": {"lang"},
    "head": set(),
    "meta": {"charset", "name", "content"},
    "title": set(),
    "link": {"rel", "href"},
    "body": set(),
    "a": {"class", "href", "aria-label", "rel"},
    "img": {"class", "src", "alt", "width", "height"},
    "header": {"class"},
    "div": {"class", "role", "aria-labelledby", "data-os", "data-host", "data-surface", "hidden"},
    "span": {"class", "aria-hidden"},
    "nav": {"class", "aria-label"},
    "main": {"id", "tabindex"},
    "footer": {"class"},
    "p": {"id", "class", "role", "aria-live"},
    "section": {"class", "aria-labelledby", "data-action-id"},
    "article": {"class"},
    "aside": {"class", "aria-label"},
    "h1": {"id"},
    "h2": {"id"},
    "h3": {"id"},
    "code": {"id", "class", "tabindex"},
    "pre": set(),
    "ol": {"class"},
    "li": {"class"},
    "strong": set(),
    "small": set(),
    "ul": {"class"},
    "table": set(),
    "thead": set(),
    "tbody": set(),
    "tr": set(),
    "th": set(),
    "td": set(),
    "button": {"type", "class", "data-os", "data-host", "data-copy-target", "aria-describedby", "aria-pressed"},
    "script": {"type", "src"},
    "svg": {"width", "height", "viewbox", "fill", "stroke", "stroke-width", "stroke-linecap", "stroke-linejoin", "aria-hidden"},
    "path": {"d"},
    "circle": {"cx", "cy", "r"},
}
_LABS = (
    "F01-fork-clone-doctor",
    "F02-orient-to-state",
    "F03-work-the-board",
    "F04-fix-with-evidence",
    "P01-feature-through-plan",
    "P02-commit-review-pr",
    "P03-record-an-adr",
    "P04-review-a-dependency",
    "P05-checkpoint-remediation",
    "P06-context-drift-recovery",
    "P07-threat-model",
    "P08-repository-hygiene",
    "U01-autonomous-sprint",
    "U02-override-audit-metrics",
    "U03-refactor-chore-release",
    "U04-initialize-projects",
    "U05-debug-spike-conflict",
    "U06-preview-and-advanced-surfaces",
    "U07-capstone",
)
_COMING_NEXT: tuple[str, ...] = ()
_RUNNABLE_LINK_LABELS = (
    "F01 \u2014 Fork, clone, and Doctor safety",
    "F02 \u2014 Orient to live governance state",
    "F03: Work the governed board",
    "F04 — Fix with evidence",
    "P01 - Feature through a user-approved spec and derived plan",
    "P02: Review, commit, push, and record an offline-local receipt",
    "P03 - Record an accepted ADR",
    "P04 - Review a dependency without installing it",
    "P05 - Remediate a checkpoint finding",
    "P06 - Recover context drift without losing unrelated work",
    "P07 - Threat-model the path-handling boundary",
    "P08: Classify repository hygiene without destructive cleanup",
    "U01: Govern an autonomous sprint without outsourcing approval",
    "U02: Observe an audit guard without changing the audit trail",
    "U03: Refactor, chore, and local release evidence",
    "U04: Initialize a greenfield and a brownfield project",
    "U05: Debug, spike, and conflict without inventing evidence",
    "U06: Preview a bounded change without turning advice into authority",
    "U07: Complete a bounded feature capstone",
)
_COMING_NEXT_ENTRIES: tuple[tuple[str, bool], ...] = ()
_PUBLIC_PREREQUISITES = (
    "A GitHub account that can create a personal fork.",
    "Git 2.39 or newer.",
    "Python 3.11 or newer.",
    "A supported CodeArbiter host: Claude Code, Codex, or Pi.",
    "Complete Academy Home setup steps 1-5 before starting F01.",
)
_KNOWN_LIMITS = (
    "F01-F04, P01-P08, and U01-U07 are the guided lessons published in Preview 0.21.",
    "Graduation is available after all 19 Academy Checks pass in the same repository.",
)
_EXPECTED_ACTION_IDS = {
    Path("index.html"): (
        "home-fork",
        "home-clone",
        "home-enter-clone",
        "home-install",
        "home-doctor",
    ),
    Path("recovery/index.html"): (
        "recovery-inspect",
        "recovery-return-attempt",
        "recovery-repair-remotes",
        "recovery-check",
        "recovery-reset",
        "recovery-return-base",
    ),
    Path("labs/F01-fork-clone-doctor/index.html"): (
        "F01-prepare",
        "F01-inspect-remotes",
        "F01-repair-origin",
        "F01-set-upstream",
        "F01-disable-upstream-push",
        "F01-select-push-default",
        "F01-host-doctor",
        "F01-academy-doctor",
        "F01-inspect-report",
        "F01-stage-report",
        "F01-review-commit-boundary",
        "F01-commit-report",
        "F01-confirm-clean",
        "F01-check",
        "F01-return-base",
        "F01-reset-retry",
    ),
    Path("labs/F02-orient-to-state/index.html"): (
        "F02-prepare",
        "F02-run-status",
        "F02-read-context",
        "F02-follow-context-links",
        "F02-hash-context",
        "F02-write-orientation",
        "F02-inspect-orientation",
        "F02-stage-orientation",
        "F02-review-commit-boundary",
        "F02-run-commit-gate",
        "F02-confirm-clean",
        "F02-check",
        "F02-return-base",
        "F02-reset-retry",
    ),
    Path("labs/F03-work-the-board/index.html"): (
        "F03-prepare",
        "F03-read-target-task",
        "F03-start-task",
        "F03-inspect-started-task",
        "F03-complete-task",
        "F03-inspect-final-diff",
        "F03-stage-board",
        "F03-review-commit-boundary",
        "F03-run-commit-gate",
        "F03-confirm-clean",
        "F03-check",
        "F03-reset-retry",
        "F03-return-base",
    ),
    Path("labs/F04-fix-with-evidence/index.html"): (
        "F04-prepare", "F04-inspect-defect", "F04-confirm-baseline", "F04-start-fix",
        "F04-request-regression", "F04-run-red-regression", "F04-inspect-test-boundary",
        "F04-stage-regression", "F04-review-regression-boundary", "F04-commit-regression",
        "F04-prove-red-commit", "F04-request-repair", "F04-prove-repair",
        "F04-inspect-repair-boundary", "F04-stage-repair", "F04-review-repair-boundary",
        "F04-commit-repair", "F04-inspect-history", "F04-check", "F04-reset-retry",
        "F04-return-base",
    ),
    Path("labs/P01-feature-through-plan/index.html"): (
        "P01-prepare", "P01-draft-spec", "P01-read-spec", "P01-solo-review",
        "P01-discussion-review", "P01-revise-spec", "P01-proceed", "P01-check",
        "P01-return-base", "P01-reset-retry",
    ),
    Path("labs/P02-commit-review-pr/index.html"): (
        "P02-read-boundary", "P02-prepare", "P02-enter-and-guard",
        "P02-inspect-change", "P02-stage-work", "P02-request-review", "P02-run-review",
        "P02-run-work-commit", "P02-prove-and-push", "P02-record-receipt",
        "P02-stage-receipt", "P02-run-receipt-commit", "P02-confirm-clean",
        "P02-check", "P02-reset",
    ),
    Path("labs/P03-record-an-adr/index.html"): (
        "P03-read-boundary", "P03-identity-boundary", "P03-prepare",
        "P03-inspect-decision-context", "P03-request-decision-analysis", "P03-run-adr",
        "P03-run-commit-gate", "P03-confirm-native-evidence", "P03-check", "P03-reset",
    ),
    Path("labs/P04-review-a-dependency/index.html"): (
        "P04-prepare", "P04-read-boundary", "P04-read-candidate-set",
        "P04-inspect-project-boundary", "P04-inspect-wheel-metadata", "P04-verify-wheel-hashes",
        "P04-read-licenses", "P04-assess-provenance", "P04-compare-stdlib", "P04-draft-review",
        "P04-review-draft", "P04-select-reject", "P04-stage-review", "P04-commit-review",
        "P04-confirm-no-install", "P04-check", "P04-reset-retry",
    ),
    Path("labs/P05-checkpoint-remediation/index.html"): (
        "P05-prerequisite", "P05-prepare", "P05-guard-attempt", "P05-read-prepared-boundary",
        "P05-surface-finding", "P05-inspect-finding", "P05-record-finding",
        "P05-verify-finding-commit", "P05-add-red-regression", "P05-observe-red",
        "P05-commit-red", "P05-apply-green-repair", "P05-commit-green", "P05-record-receipt",
        "P05-commit-receipt", "P05-confirm-clean", "P05-check", "P05-reset-retry",
    ),
    Path("labs/P06-context-drift-recovery/index.html"): (
        "P06-prepare", "P06-inspect-evidence", "P06-run-context-audit", "P06-select-rescout",
        "P06-apply-correction", "P06-review-correction-boundary", "P06-commit-correction",
        "P06-write-handoff", "P06-stage-handoff", "P06-review-handoff-boundary",
        "P06-commit-handoff", "P06-check", "P06-return-base", "P06-reset-retry",
    ),
    Path("labs/P07-threat-model/index.html"): (
        "P07-read-boundary", "P07-prepare", "P07-read-target", "P07-request-draft",
        "P07-review-model", "P07-write-binding", "P07-commit-report", "P07-inspect-commit",
        "P07-check", "P07-reset",
    ),
    Path("labs/P08-repository-hygiene/index.html"): (
        "P08-prepare", "P08-inventory-native", "P08-inventory-harness-shell", "P08-run-standup",
        "P08-request-report-draft", "P08-review-report", "P08-stage-report",
        "P08-review-commit-boundary", "P08-run-commit-gate", "P08-confirm-clean", "P08-check",
        "P08-return-base", "P08-reset-retry",
    ),
    Path("labs/U01-autonomous-sprint/index.html"): (
        "U01-confirm-fork-boundary", "U01-prepare-attempt", "U01-inspect-scenario",
        "U01-run-sprint", "U01-approve-or-decline-spec", "U01-inspect-artifacts",
        "U01-check-status", "U01-return-base", "U01-reset-retry",
    ),
    Path("labs/U02-override-audit-metrics/index.html"): (
        "U02-read-boundary", "U02-prepare", "U02-inspect-baseline",
        "U02-attempt-guarded-restore", "U02-record-observation",
        "U02-review-observation-boundary", "U02-stage-observation",
        "U02-commit-observation", "U02-check", "U02-reset",
    ),
    Path("labs/U03-refactor-chore-release/index.html"): (
        "U03-read-boundary", "U03-prepare", "U03-confirm-prepared", "U03-review-sealed-brief",
        "U03-run-refactor", "U03-inspect-refactor", "U03-review-refactor", "U03-stage-refactor",
        "U03-commit-refactor", "U03-run-chore", "U03-inspect-chore", "U03-review-chore",
        "U03-stage-chore", "U03-commit-chore", "U03-run-release", "U03-review-release",
        "U03-inspect-tag", "U03-check", "U03-reset",
    ),
    Path("labs/U04-initialize-projects/index.html"): (
        "U04-confirm-private-boundary", "U04-prepare-attempt", "U04-inspect-root",
        "U04-inspect-greenfield", "U04-run-greenfield-init", "U04-run-greenfield-decompose",
        "U04-read-greenfield-plans", "U04-choose-greenfield-reconciliation",
        "U04-run-greenfield-reconcile", "U04-record-greenfield-adr",
        "U04-accept-greenfield-adr", "U04-inspect-greenfield-changes",
        "U04-stage-greenfield-changes", "U04-review-greenfield-commit-boundary",
        "U04-run-greenfield-commit-gate", "U04-confirm-greenfield-clean",
        "U04-inspect-brownfield", "U04-run-brownfield-init",
        "U04-run-brownfield-create-context", "U04-inspect-brownfield-changes",
        "U04-stage-brownfield-changes", "U04-review-brownfield-commit-boundary",
        "U04-run-brownfield-commit-gate", "U04-confirm-brownfield-clean",
        "U04-inspect-project-evidence", "U04-write-binding-report", "U04-inspect-report",
        "U04-stage-report", "U04-review-commit-boundary", "U04-run-commit-gate",
        "U04-confirm-clean", "U04-check-status", "U04-reset-retry",
    ),
    Path("labs/U05-debug-spike-conflict/index.html"): (
        "U05-confirm-readiness", "U05-prepare-attempt", "U05-read-observation",
        "U05-run-debug", "U05-review-debug-board", "U05-commit-debug-board",
        "U05-run-spike", "U05-confirm-spike-question", "U05-transfer-findings",
        "U05-review-findings", "U05-commit-findings", "U05-delete-spike",
        "U05-halt-for-conflict", "U05-check-status", "U05-reset-retry",
    ),
    Path("labs/U06-preview-and-advanced-surfaces/index.html"): (
        "U06-confirm-public-boundary", "U06-prepare-attempt", "U06-inspect-scenario",
        "U06-inspect-seeded-candidate", "U06-create-contained-diff", "U06-inspect-preview-input",
        "U06-run-read-only-preview", "U06-assess-preview-output", "U06-stage-candidate",
        "U06-commit-candidate", "U06-classify-advanced-surfaces", "U06-write-binding-report",
        "U06-inspect-binding-report", "U06-stage-report", "U06-commit-report", "U06-confirm-clean",
        "U06-check-status", "U06-reset-retry",
    ),
    Path("labs/U07-capstone/index.html"): (
        "U07-prepare", "U07-run-feature", "U07-open-pr", "U07-check", "U07-reset-retry",
    ),
}
_GUIDED_STATUS = "Guided lesson"
_REFERENCE_STATUS = "Reference lesson \u00b7 guided rewrite pending"
_EXPECTED_FILES = {
    Path("assets/academy.css"),
    Path("assets/academy.js"),
    Path("assets/favicon.svg"),
    Path("assets/fonts/jetbrains-mono-latin-wght-normal.woff2"),
    Path("assets/fonts/manrope-latin-wght-normal.woff2"),
    Path("assets/gate-mark.svg"),
    Path("assets/hero-gates.webp"),
    Path("assets/logo.svg"),
    Path("index.html"),
    Path("recovery/index.html"),
    Path("release.json"),
    *(Path("labs") / lab_id / "index.html" for lab_id in _LABS),
}


class _LinkCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.targets: list[tuple[str, str, str | None]] = []
        self.ids: list[str] = []
        self.id_references: list[tuple[str, str, str]] = []
        self.academy_releases: list[str] = []
        self.copy_bindings: list[tuple[str, str]] = []
        self.id_contracts: dict[str, tuple[str, dict[str, str | None]]] = {}
        self.script_sources: list[str] = []
        self.action_ids: list[str] = []
        self.anchor_texts: list[tuple[str, str]] = []
        self.coming_next_entries: list[tuple[str, bool]] = []
        self.publication_statuses: list[str] = []
        self._anchor_target: str | None = None
        self._anchor_text_parts: list[str] | None = None
        self._coming_next = False
        self._coming_next_item_has_link = False
        self._coming_next_item_parts: list[str] | None = None
        self._publication_status_parts: list[str] | None = None
        self._script_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        allowed = _ALLOWED_HTML_ATTRIBUTES.get(tag)
        if allowed is None:
            raise ValueError(f"disallowed HTML element: {tag}")
        names = [name for name, _ in attrs]
        if len(names) != len(set(names)):
            raise ValueError(f"disallowed HTML duplicate attribute on {tag}")
        attributes = dict(attrs)
        for name, value in attrs:
            if name not in allowed or (value is None and name != "hidden"):
                raise ValueError(f"disallowed HTML attribute on {tag}: {name}")
            if name == "hidden":
                if tag == "div" and attributes.get("class") == "command-variant":
                    raise ValueError("command variant must remain visible without JavaScript")
                if not (
                    tag == "div" and attributes.get("class") == "academy-command-preferences"
                ):
                    raise ValueError("hidden is reserved for Academy command preferences")
            if name == "href":
                self.targets.append((tag, value, attributes.get("rel")))
            if name == "src":
                self.targets.append((tag, value, None))
            if name == "id":
                self.ids.append(value)
                self.id_contracts[value] = (tag, attributes)
            if name in {"aria-labelledby", "aria-describedby"}:
                references = value.split()
                if not references:
                    raise ValueError(f"empty {name} reference on {tag}")
                self.id_references.extend((tag, name, reference) for reference in references)
        if "data-action-id" in attributes and not (
            tag == "section" and attributes.get("class") == "lesson-action"
        ):
            raise ValueError("data-action-id is reserved for exact lesson-action sections")
        if tag == "html" and attributes != {"lang": "en"}:
            raise ValueError("disallowed HTML attributes on html")
        if tag == "link" and attributes.get("rel") not in {"stylesheet", "icon"}:
            raise ValueError("disallowed HTML link relationship")
        if tag == "meta" and attributes.get("name") == "academy-release":
            self.academy_releases.append(attributes.get("content", ""))
        if tag == "section" and attributes.get("class") == "lesson-action":
            action_id = attributes.get("data-action-id")
            if action_id:
                self.action_ids.append(action_id)
        if tag == "a":
            self._anchor_target = str(attributes["href"])
            self._anchor_text_parts = []
            if self._coming_next_item_parts is not None:
                self._coming_next_item_has_link = True
        if tag == "ul" and attributes.get("class") == "coming-next":
            self._coming_next = True
        if tag == "li" and self._coming_next:
            self._coming_next_item_parts = []
            self._coming_next_item_has_link = False
        if tag == "p" and attributes.get("class") == "lesson-publication-status":
            self._publication_status_parts = []
        if tag == "code" and str(attributes.get("id", "")).startswith("command-"):
            if attributes.get("tabindex") != "0":
                raise ValueError("command code is not focusable")
        if tag == "div" and attributes.get("class") == "command-variant":
            if "hidden" in attributes:
                raise ValueError("command variant must remain visible without JavaScript")
            if (
                attributes.get("data-os") not in {"all", "windows", "macos", "linux"}
                or attributes.get("data-host") not in {"none", "claude-code", "codex", "pi"}
                or attributes.get("data-surface") not in {
                    "browser", "native-terminal", "harness", "academy-console"
                }
            ):
                raise ValueError("disallowed HTML command-variant contract")
        if tag == "div" and attributes.get("class") == "academy-command-preferences":
            if (
                "hidden" not in attributes
                or attributes.get("aria-labelledby") != "academy-command-preferences-heading"
            ):
                raise ValueError("preference controls must be hidden until JavaScript binds")
            if set(attributes) != {"class", "hidden", "aria-labelledby"}:
                raise ValueError("disallowed exact preference-container contract")
        if tag == "script" and set(attributes.items()) != {
            ("type", "module"),
            ("src", attributes.get("src")),
        }:
            raise ValueError("disallowed HTML script contract")
        if tag == "script":
            self.script_sources.append(attributes["src"])
            self._script_depth += 1
        if tag == "button" and attributes.get("class") == "command-copy":
            if (
                attributes.get("type") != "button"
                or not attributes.get("data-copy-target")
                or not attributes.get("aria-describedby")
            ):
                raise ValueError("disallowed HTML copy-button contract")
            self.copy_bindings.append(
                (attributes["data-copy-target"], attributes["aria-describedby"])
            )
        elif tag == "button":
            preference_kind = (
                "os" if attributes.get("class") == "academy-os-choice" else
                "host" if attributes.get("class") == "academy-host-choice" else None
            )
            expected_data = f"data-{preference_kind}" if preference_kind else None
            if (
                preference_kind is None
                or attributes.get("type") != "button"
                or attributes.get("aria-pressed") != "false"
                or not attributes.get(expected_data)
            ):
                raise ValueError("disallowed HTML preference-button contract")
            allowed_values = OPERATING_SYSTEMS if preference_kind == "os" else HOSTS
            if attributes[expected_data] not in allowed_values:
                raise ValueError("disallowed HTML preference-button value")

    def handle_endtag(self, tag: str) -> None:
        if tag not in _ALLOWED_HTML_ATTRIBUTES:
            raise ValueError(f"disallowed HTML element: {tag}")
        if tag == "script":
            self._script_depth -= 1
        if tag == "a" and self._anchor_text_parts is not None:
            self.anchor_texts.append(
                (
                    str(self._anchor_target),
                    " ".join("".join(self._anchor_text_parts).split()),
                )
            )
            self._anchor_target = None
            self._anchor_text_parts = None
        if tag == "li" and self._coming_next_item_parts is not None:
            self.coming_next_entries.append(
                (
                    " ".join("".join(self._coming_next_item_parts).split()),
                    self._coming_next_item_has_link,
                )
            )
            self._coming_next_item_parts = None
            self._coming_next_item_has_link = False
        if tag == "ul" and self._coming_next:
            self._coming_next = False
        if tag == "p" and self._publication_status_parts is not None:
            self.publication_statuses.append(
                " ".join("".join(self._publication_status_parts).split())
            )
            self._publication_status_parts = None

    def handle_data(self, data: str) -> None:
        if self._script_depth and data.strip():
            raise ValueError("disallowed inline JavaScript")
        if self._anchor_text_parts is not None:
            self._anchor_text_parts.append(data)
        if self._coming_next_item_parts is not None:
            self._coming_next_item_parts.append(data)
        if self._publication_status_parts is not None:
            self._publication_status_parts.append(data)

    def handle_decl(self, decl: str) -> None:
        if decl.lower() != "doctype html":
            raise ValueError(f"disallowed HTML declaration: {decl}")

    def handle_pi(self, data: str) -> None:
        raise ValueError("disallowed HTML processing instruction")


def _is_symlink_or_reparse(path: Path) -> bool:
    try:
        details = path.lstat()
    except FileNotFoundError:
        return False
    except OSError as error:
        raise ValueError(f"could not inspect artifact path {path}: {error}") from error
    attributes = getattr(details, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return stat.S_ISLNK(details.st_mode) or bool(attributes & reparse_flag)


def _reject_unsafe_lexical_components(path: Path) -> None:
    absolute = Path(os.path.abspath(path))
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        try:
            details = current.lstat()
        except FileNotFoundError:
            break
        except OSError as error:
            raise ValueError(f"could not inspect artifact path {current}: {error}") from error
        attributes = getattr(details, "st_file_attributes", 0)
        reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
        if stat.S_ISLNK(details.st_mode) or bool(attributes & reparse_flag):
            raise ValueError(
                "preview artifact root must be a real directory; "
                f"artifact path contains a symlink or reparse point: {current}"
            )


def _artifact_files(root: Path) -> set[Path]:
    found: set[Path] = set()
    for path in root.rglob("*"):
        if _is_symlink_or_reparse(path):
            raise ValueError(
                f"artifact contains a symlink or reparse point: {path.relative_to(root).as_posix()}"
            )
        if path.is_file():
            found.add(path.relative_to(root))
    return found


def _resolve_local(
    root: Path,
    source: Path,
    target: str,
    *,
    allow_external: bool = False,
) -> Path | None:
    parsed = urlsplit(target)
    if parsed.scheme or parsed.netloc:
        if not allow_external or not _is_approved_external_url(target):
            raise ValueError(f"unapproved external URL in {source.relative_to(root).as_posix()}: {target}")
        return None
    path = unquote(parsed.path)
    if not path:
        return source if parsed.fragment else None
    if path.startswith("/") or "\\" in path:
        raise ValueError(f"project-unsafe root-relative URL in {source.relative_to(root).as_posix()}: {target}")
    candidate = (source.parent / path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as error:
        raise ValueError(f"internal link escapes artifact root: {target}") from error
    if not candidate.is_file():
        raise ValueError(
            f"broken internal link in {source.relative_to(root).as_posix()}: {target}"
        )
    return candidate


def _check_release(root: Path) -> str:
    try:
        data = json.loads((root / "release.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"release.json is unreadable: {error}") from error
    if (
        not isinstance(data, dict)
        or set(data) != {
            "release", "commit", "lesson_contract_version", "catalog_sha256",
            "available_labs", "runnable_labs", "guided_labs", "coming_next",
            "prerequisites", "known_limits", "discussion_url",
        }
        or data.get("release") != "preview-0.21"
        or type(data.get("lesson_contract_version")) is not int
        or data.get("lesson_contract_version") != 1
        or not isinstance(data.get("commit"), str)
        or not _SHA.fullmatch(data["commit"])
        or not isinstance(data.get("catalog_sha256"), str)
        or not re.fullmatch(r"[0-9a-f]{64}", data["catalog_sha256"])
        or data.get("available_labs") != list(_LABS)
        or data.get("runnable_labs") != list(_LABS)
        or data.get("guided_labs") != list(_LABS)
        or data.get("coming_next") != list(_COMING_NEXT)
        or data.get("prerequisites") != list(_PUBLIC_PREREQUISITES)
        or data.get("known_limits") != list(_KNOWN_LIMITS)
        or data.get("discussion_url") != "https://github.com/arbiterForge/arbiter-academy/discussions"
    ):
        raise ValueError("release.json does not contain the exact Preview 0.21 provenance contract")
    return data["release"]


def _check_asset_digests(root: Path) -> None:
    for relative, expected in _ASSET_SHA256.items():
        try:
            actual = hashlib.sha256((root / relative).read_bytes()).hexdigest()
        except OSError as error:
            raise ValueError(f"reviewed runtime asset is unreadable: {relative.as_posix()}: {error}") from error
        if actual != expected:
            raise ValueError(f"runtime asset digest mismatch: {relative.as_posix()}")


def _check_stylesheet_dependencies(root: Path, stylesheet: Path, css: str) -> None:
    for quoted, unquoted in _CSS_IMPORT.findall(css):
        _resolve_local(root, stylesheet, quoted or unquoted)
    for target in _CSS_URL.findall(css):
        _resolve_local(root, stylesheet, target)


def _check_publication_truth(root: Path, pages: dict[Path, _LinkCollector]) -> None:
    home = root / "index.html"
    home_collector = pages[home]
    expected_lab_pages = tuple(root / "labs" / lab_id / "index.html" for lab_id in _LABS)
    runnable_links = tuple(
        (resolved, label)
        for target, label in home_collector.anchor_texts
        if (resolved := _resolve_local(root, home, target, allow_external=True))
        in expected_lab_pages
    )
    expected_runnable_links = tuple(zip(expected_lab_pages, _RUNNABLE_LINK_LABELS, strict=True))
    if runnable_links != expected_runnable_links:
        raise ValueError("home runnable lab links do not match the exact guided Preview 0.21 inventory")
    if tuple(home_collector.coming_next_entries) != _COMING_NEXT_ENTRIES:
        raise ValueError("home coming-next entries do not match the exact Preview 0.21 guided-rewrite sequence")

    for page, collector in pages.items():
        relative = page.relative_to(root)
        expected_actions = _EXPECTED_ACTION_IDS.get(relative, ())
        if tuple(collector.action_ids) != expected_actions:
            raise ValueError(
                f"generated action IDs do not match the exact Preview 0.21 contract: {relative.as_posix()}"
            )

        if relative.parts[:1] != ("labs",):
            expected_statuses: tuple[str, ...] = ()
        elif relative in {
            Path("labs/F01-fork-clone-doctor/index.html"),
            Path("labs/F02-orient-to-state/index.html"),
            Path("labs/F03-work-the-board/index.html"),
            Path("labs/F04-fix-with-evidence/index.html"),
            Path("labs/P01-feature-through-plan/index.html"),
            Path("labs/P02-commit-review-pr/index.html"),
            Path("labs/P03-record-an-adr/index.html"),
            Path("labs/P04-review-a-dependency/index.html"),
            Path("labs/P05-checkpoint-remediation/index.html"),
            Path("labs/P06-context-drift-recovery/index.html"),
            Path("labs/P07-threat-model/index.html"),
            Path("labs/P08-repository-hygiene/index.html"),
            Path("labs/U01-autonomous-sprint/index.html"),
            Path("labs/U02-override-audit-metrics/index.html"),
            Path("labs/U03-refactor-chore-release/index.html"),
            Path("labs/U04-initialize-projects/index.html"),
            Path("labs/U05-debug-spike-conflict/index.html"),
            Path("labs/U06-preview-and-advanced-surfaces/index.html"),
            Path("labs/U07-capstone/index.html"),
        }:
            expected_statuses = (_GUIDED_STATUS,)
        else:
            expected_statuses = (_REFERENCE_STATUS,)
        if tuple(collector.publication_statuses) != expected_statuses:
            raise ValueError(
                "generated publication status does not match the exact Preview 0.21 contract: "
                f"{relative.as_posix()}"
            )


def check_preview_site(site_root: Path) -> None:
    _reject_unsafe_lexical_components(site_root)
    root = site_root.resolve()
    if not root.is_dir():
        raise ValueError("preview artifact root must be a real directory")
    actual = _artifact_files(root)
    if actual != _EXPECTED_FILES:
        missing = sorted(path.as_posix() for path in _EXPECTED_FILES - actual)
        unexpected = sorted(path.as_posix() for path in actual - _EXPECTED_FILES)
        raise ValueError(
            "preview artifact inventory mismatch; "
            f"missing={missing or 'none'}; unexpected={unexpected or 'none'}"
        )

    release = _check_release(root)
    _check_asset_digests(root)
    pages: dict[Path, _LinkCollector] = {}
    for relative in sorted(path for path in actual if path.suffix == ".html"):
        page = root / relative
        try:
            text = page.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            raise ValueError(f"generated HTML is unreadable: {relative.as_posix()}: {error}") from error
        collector = _LinkCollector()
        collector.feed(text)
        duplicate_ids = sorted(
            identifier for identifier in set(collector.ids) if collector.ids.count(identifier) > 1
        )
        if duplicate_ids:
            raise ValueError(
                f"duplicate HTML id in {relative.as_posix()}: {', '.join(duplicate_ids)}"
            )
        if collector.academy_releases != [release]:
            raise ValueError(
                f"HTML release identity mismatch in {relative.as_posix()}"
            )
        pages[page] = collector

    for page, collector in pages.items():
        for tag, target, relationship in collector.targets:
            resolved = _resolve_local(
                root,
                page,
                target,
                allow_external=tag == "a",
            )
            if tag == "link":
                expected = root / "assets" / (
                    "academy.css" if relationship == "stylesheet" else "favicon.svg"
                )
                if resolved != expected:
                    raise ValueError(f"unapproved linked asset URL: {target}")
            if tag == "script" and resolved != root / "assets" / "academy.js":
                raise ValueError(f"unapproved script asset URL: {target}")
            fragment = unquote(urlsplit(target).fragment)
            if fragment:
                target_collector = pages.get(resolved) if resolved is not None else None
                if target_collector is None or fragment not in target_collector.ids:
                    raise ValueError(
                        f"broken HTML fragment in {page.relative_to(root).as_posix()}: {target}"
                    )
        page_ids = set(collector.ids)
        if len(collector.script_sources) != 1:
            raise ValueError(
                f"generated page must load exactly one reviewed module: {page.relative_to(root).as_posix()}"
            )
        for target, status in collector.copy_bindings:
            target_contract = collector.id_contracts.get(target)
            status_contract = collector.id_contracts.get(status)
            if (
                target_contract is None
                or target_contract[0] != "code"
                or target_contract[1].get("tabindex") != "0"
            ):
                raise ValueError(
                    "broken copy target in "
                    f"{page.relative_to(root).as_posix()} on button: {target}"
                )
            if status_contract is None or status_contract[0] != "p" or (
                status_contract[1].get("role") != "status"
                or status_contract[1].get("aria-live") != "polite"
            ):
                raise ValueError(
                    "broken copy status in "
                    f"{page.relative_to(root).as_posix()} on button: {status}"
                )
        for tag, attribute, reference in collector.id_references:
            if reference not in page_ids:
                raise ValueError(
                    f"broken {attribute} reference in "
                    f"{page.relative_to(root).as_posix()} on {tag}: {reference}"
                )

    _check_publication_truth(root, pages)

    stylesheet = root / "assets/academy.css"
    try:
        css = stylesheet.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise ValueError(f"generated stylesheet is unreadable: {error}") from error
    _check_stylesheet_dependencies(root, stylesheet, css)


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("site_root", type=Path)
    options = parser.parse_args(arguments)
    try:
        check_preview_site(options.site_root)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
