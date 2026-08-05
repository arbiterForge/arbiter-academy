"""Structured curriculum loading and local source-contract verification."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from academy_engine.catalog import Catalog, load_manifest_file
from academy_engine.checkpoints import load_contracts


class CurriculumError(ValueError):
    """A learner-facing lab source is incomplete or inconsistent."""


@dataclass(frozen=True)
class CurriculumLab:
    id: str
    track: str
    order: int
    title: str
    outcome: str
    prerequisites: tuple[str, ...]
    estimated_minutes: int
    scenario_command: str
    checkpoint_command: str
    host_commands: dict[str, str]
    hints: tuple[str, ...]
    success_evidence: str
    recovery: str
    next_lab: str


@dataclass(frozen=True)
class CurriculumTrack:
    id: str
    labs: tuple[CurriculumLab, ...]


@dataclass(frozen=True)
class TrackVerification:
    track: str
    lab_count: int
    matrix_cells: int
    issues: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not self.issues

    def render(self) -> str:
        label = self.track.replace("-", " ").title()
        state = "passed" if self.passed else "failed"
        lines = [
            f"{label}: {self.lab_count} labs; {self.matrix_cells} matrix cells; structural verification {state}.",
            "This verifies curriculum/source contracts only; learner checkpoints remain authoritative only through an external verifier.",
        ]
        lines.extend(f"- {issue}" for issue in self.issues)
        return "\n".join(lines)


_FRONT_KEYS = {
    "id",
    "track",
    "order",
    "title",
    "outcome",
    "prerequisites",
    "estimated_minutes",
    "scenario_command",
    "checkpoint_command",
    "next_lab",
}
_REQUIRED_SECTIONS = (
    "Why this mechanism matters",
    "Start the scenario",
    "Use your host",
    "Do the work",
    "Hints",
    "Success evidence",
    "Recovery",
    "Next lab",
)
_HOST_HEADINGS = {
    "Claude Code": "claude-code",
    "Codex": "codex",
    "Pi (Feature Forge preview)": "pi",
}
_FOUNDATIONS_SCENARIOS = {
    "F01-fork-clone-doctor": ("remote_configuration", "git-config", "fork-routing-unverified"),
    "F02-orient-to-state": ("context_orientation", ".codearbiter/CONTEXT.md", "orientation-not-recorded"),
    "F03-work-the-board": ("task_transition", "academy.feature.0001", "queued"),
    "F04-fix-with-evidence": ("regression_first_fix", "workshop_queue/service.py", "defect-staged"),
}
_PRACTITIONER_SCENARIOS = {
    "P01-feature-through-plan": ("feature_spec_plan", "workshop_queue/cli.py", "approval-required"),
    "P02-commit-review-pr": ("commit_review_pr", "learner-fork", "review-required"),
    "P03-record-an-adr": ("architecture_decision", "ADR-0004", "decision-open"),
    "P04-review-a-dependency": (
        "dependency_review",
        "python-dateutil==2.9.0.post0",
        "install-blocked",
    ),
    "P05-checkpoint-remediation": (
        "finding_remediation",
        "workshop-queue-finding",
        "finding-open",
    ),
    "P06-context-drift-recovery": (
        "provenance_recovery",
        ".codearbiter/CONTEXT.md",
        "context-stale",
    ),
    "P07-threat-model": ("stride_model", "academy_engine/paths.py", "model-absent"),
    "P08-repository-hygiene": (
        "ref_classification",
        "local-refs",
        "classification-absent",
    ),
}
_INSTALLED_PREPARE_LABS = (
    "P01-feature-through-plan",
    "P02-commit-review-pr",
    "P03-record-an-adr",
    "P04-review-a-dependency",
    "P05-checkpoint-remediation",
    "P06-context-drift-recovery",
    "P07-threat-model",
    "P08-repository-hygiene",
)
_SCENARIO_COMMANDS = {
    lab_id: f"arbiter-academy --repository <learner-repository> prepare {lab_id}"
    for lab_id in _INSTALLED_PREPARE_LABS
}
_MATRIX_CASES = {
    "F01-fork-clone-doctor": (
        "untouched",
        "partial",
        "wrong",
        "intended",
        "equivalent",
        "official-origin",
        "missing-upstream",
        "unsafe-push-url",
        "copied-report",
        "wrong-attempt-branch",
        "dirty-worktree",
        "report-not-changed",
    ),
    "F02-orient-to-state": (
        "untouched",
        "partial",
        "wrong",
        "intended",
        "equivalent",
        "stale-digest",
        "stale-stage",
        "wrong-context-path",
        "rendered-prose-hash",
        "context-changed-after-record",
        "uncommitted-record",
    ),
    "F03-work-the-board": (
        "untouched",
        "partial",
        "wrong",
        "intended",
        "equivalent",
        "checkbox-only",
        "malformed-date",
        "wrong-task",
        "unrelated-board-edit",
        "uncommitted-board",
    ),
    "F04-fix-with-evidence": (
        "untouched",
        "partial",
        "wrong",
        "intended",
        "equivalent",
        "no-failing-regression",
        "same-commit",
        "code-only",
        "test-only",
        "unrelated-test",
        "test-after-code",
        "unchanged-defect",
        "overbroad-repair",
        "unreachable-repair",
        "disconnected-regression",
        "overbroad-then-decoy-repair",
    ),
    **{
        lab_id: ("untouched", "partial", "wrong", "intended", "equivalent")
        for lab_id in _PRACTITIONER_SCENARIOS
    },
}


def _front_matter(text: str, path: Path) -> tuple[dict[str, str], str]:
    lines = text.splitlines()
    if len(lines) < 3 or lines[0] != "---":
        raise CurriculumError(f"{path.name} must begin with front matter.")
    try:
        end = lines.index("---", 1)
    except ValueError as error:
        raise CurriculumError(f"{path.name} front matter is not closed.") from error
    data: dict[str, str] = {}
    for line in lines[1:end]:
        key, separator, value = line.partition(":")
        if not separator or not key or not value.strip():
            raise CurriculumError(f"{path.name} front matter contains a malformed field.")
        if key in data:
            raise CurriculumError(f"{path.name} front matter contains a duplicate field.")
        data[key] = value.strip()
    if set(data) != _FRONT_KEYS:
        raise CurriculumError(f"{path.name} front matter has missing or unknown fields.")
    return data, "\n".join(lines[end + 1 :]).strip() + "\n"


def _sections(body: str, path: Path) -> dict[str, str]:
    matches = list(re.finditer(r"(?m)^## ([^\n]+)\n", body))
    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        name = match.group(1).strip()
        if name in sections:
            raise CurriculumError(f"{path.name} repeats section {name}.")
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        sections[name] = body[match.end() : end].strip()
    missing = [name for name in _REQUIRED_SECTIONS if not sections.get(name)]
    if missing:
        raise CurriculumError(f"{path.name} is missing required section(s): {', '.join(missing)}.")
    empty_visible = [
        name
        for name in _REQUIRED_SECTIONS
        if not _has_learner_visible_content(sections[name])
    ]
    if empty_visible:
        raise CurriculumError(
            f"{path.name} required section(s) lack learner-visible content: {', '.join(empty_visible)}."
        )
    return sections


def _has_learner_visible_content(text: str) -> bool:
    return bool(re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL).strip())


def _subsections(text: str, path: Path, label: str) -> dict[str, str]:
    matches = list(re.finditer(r"(?m)^### ([^\n]+)\n", text))
    result: dict[str, str] = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        name = match.group(1).strip()
        if name in result:
            raise CurriculumError(f"{path.name} repeats {label} subsection {name}.")
        result[name] = text[match.end() : end].strip()
    return result


def _one_command_block(text: str, label: str, path: Path) -> str:
    matches = re.findall(r"(?ms)^```(?:text|powershell)?\n(.+?)\n```$", text)
    if len(matches) != 1:
        raise CurriculumError(f"{path.name} must provide one copyable {label} command block.")
    lines = tuple(line.strip() for line in matches[0].splitlines() if line.strip())
    if not lines:
        raise CurriculumError(f"{path.name} {label} command block is empty.")
    return "\n".join(lines)


def _parse_lab(path: Path) -> CurriculumLab:
    data, body = _front_matter(path.read_text(encoding="utf-8"), path)
    sections = _sections(body, path)
    hosts = _subsections(sections["Use your host"], path, "host")
    if set(hosts) != set(_HOST_HEADINGS):
        raise CurriculumError(f"{path.name} must provide all three canonical host forms.")
    host_commands = {
        key: _one_command_block(hosts[heading], heading, path)
        for heading, key in _HOST_HEADINGS.items()
    }
    if any(not line.startswith("/ca:") for line in host_commands["claude-code"].splitlines()):
        raise CurriculumError(f"{path.name} Claude Code form is invalid.")
    if any(not line.startswith("$ca-") for line in host_commands["codex"].splitlines()):
        raise CurriculumError(f"{path.name} Codex form is invalid.")
    if any(not line.startswith("/ca-") for line in host_commands["pi"].splitlines()) or "/skill:ca-" not in hosts["Pi (Feature Forge preview)"]:
        raise CurriculumError(f"{path.name} Pi preview form or fallback is invalid.")
    if "project trust" not in hosts["Pi (Feature Forge preview)"].casefold():
        raise CurriculumError(f"{path.name} must state Pi's project-trust prerequisite.")
    hints = _subsections(sections["Hints"], path, "hint")
    expected_hints = {"Hint 1", "Hint 2", "Hint 3"}
    if set(hints) != expected_hints:
        raise CurriculumError(f"{path.name} must provide exactly three progressive hints.")
    empty_hints = [
        name for name in sorted(expected_hints) if not _has_learner_visible_content(hints[name])
    ]
    if empty_hints:
        raise CurriculumError(
            f"{path.name} progressive hint(s) lack learner-visible content: "
            + ", ".join(empty_hints)
            + "."
        )
    try:
        order = int(data["order"])
        estimated = int(data["estimated_minutes"])
    except ValueError as error:
        raise CurriculumError(f"{path.name} order and duration must be integers.") from error
    prerequisites = () if data["prerequisites"] == "none" else tuple(
        value.strip() for value in data["prerequisites"].split(",") if value.strip()
    )
    return CurriculumLab(
        data["id"],
        data["track"],
        order,
        data["title"],
        data["outcome"],
        prerequisites,
        estimated,
        data["scenario_command"],
        data["checkpoint_command"],
        host_commands,
        tuple(hints[f"Hint {index}"] for index in range(1, 4)),
        sections["Success evidence"],
        sections["Recovery"],
        data["next_lab"],
    )


def load_track(root: Path, track_id: str) -> CurriculumTrack:
    repository = Path(root)
    catalog = Catalog.load(repository / "academy/catalog.json")
    catalog_labs = tuple(lab for lab in catalog.labs if lab.track == track_id)
    if not catalog_labs:
        raise CurriculumError("track is not present in the Academy catalog.")
    index_path = repository / f"academy/tracks/{track_id}/index.md"
    try:
        index_text = index_path.read_text(encoding="utf-8")
    except OSError as error:
        raise CurriculumError(f"{track_id} track index is missing.") from error
    if not _has_learner_visible_content(index_text):
        raise CurriculumError(f"{track_id} track index lacks learner-visible content.")
    labs = tuple(
        _parse_lab(repository / f"academy/tracks/{track_id}/{lab.id}.md")
        for lab in catalog_labs
    )
    for expected, actual in zip(catalog_labs, labs, strict=True):
        if (
            actual.id != expected.id
            or actual.track != expected.track
            or actual.order != expected.order
            or actual.prerequisites != expected.prerequisites
        ):
            raise CurriculumError(f"{actual.id} source disagrees with the canonical catalog.")
        expected_next = (
            catalog.labs[catalog.labs.index(expected) + 1].id
            if catalog.labs.index(expected) + 1 < len(catalog.labs)
            else "graduation"
        )
        if actual.next_lab != expected_next:
            raise CurriculumError(f"{actual.id} next_lab disagrees with catalog order.")
        expected_scenario = _SCENARIO_COMMANDS.get(
            actual.id, f"python scripts/academy.py prepare {actual.id}"
        )
        if actual.scenario_command != expected_scenario:
            raise CurriculumError(f"{actual.id} scenario command is noncanonical.")
        expected_check = f"arbiter-academy --repository <learner-repository> check {actual.id}"
        if actual.checkpoint_command != expected_check:
            raise CurriculumError(f"{actual.id} checkpoint command is noncanonical.")
    return CurriculumTrack(track_id, labs)


def verify_track(root: Path, track_id: str, *, matrix: bool = False) -> TrackVerification:
    repository = Path(root)
    issues: list[str] = []
    try:
        track = load_track(repository, track_id)
        catalog_labs = {
            lab.id: lab for lab in Catalog.load(repository / "academy/catalog.json").labs
        }
        contracts = {contract.id: contract for contract in load_contracts(repository)}
        for lab in track.labs:
            contract = contracts.get(lab.id)
            if contract is None:
                issues.append(f"{lab.id}: curriculum contract is missing")
                continue
            manifest = load_manifest_file(repository / f"academy/scenarios/{lab.id}/manifest.json")
            catalog_lab = catalog_labs.get(lab.id)
            if (
                catalog_lab is None
                or manifest.id != lab.id
                or manifest.checkpoint != contract.checkpoint_path
                or manifest.checkpoint != catalog_lab.checkpoint
                or manifest.requires_push_safe_setup
                != catalog_lab.requires_push_safe_setup
                or manifest.starting_task != lab.id.split("-", 1)[0]
            ):
                issues.append(f"{lab.id}: scenario manifest binding is noncanonical")
            scenario_path = repository / "academy/scenarios" / lab.id / "files/scenario.json"
            scenario = json.loads(scenario_path.read_text(encoding="utf-8"))
            if not isinstance(scenario, dict):
                issues.append(f"{lab.id}: scenario input must be an object")
                continue
            if set(scenario) != {"schema_version", "lab_id", "operation", "target", "starting_condition"}:
                issues.append(f"{lab.id}: scenario input shape is not canonical")
            if scenario.get("schema_version") != 1 or scenario.get("lab_id") != lab.id:
                issues.append(f"{lab.id}: scenario input identity is invalid")
            expected_scenario = {
                **_FOUNDATIONS_SCENARIOS,
                **_PRACTITIONER_SCENARIOS,
            }.get(lab.id)
            observed_scenario = (
                scenario.get("operation"),
                scenario.get("target"),
                scenario.get("starting_condition"),
            )
            if expected_scenario is not None and observed_scenario != expected_scenario:
                issues.append(f"{lab.id}: scenario semantics are noncanonical")
            destinations = {item.destination for item in manifest.files}
            if contract.scenario_path not in destinations:
                issues.append(f"{lab.id}: scenario overlay does not materialize its contract path")
            if not (repository / contract.checkpoint_path).is_file():
                issues.append(f"{lab.id}: checkpoint is missing")
        if track_id == "foundations":
            f04 = load_manifest_file(repository / "academy/scenarios/F04-fix-with-evidence/manifest.json")
            destinations = {item.destination for item in f04.files}
            if not {"workshop_queue/service.py", "tests/test_service.py"}.issubset(destinations):
                issues.append("F04-fix-with-evidence: deterministic defect/test overlay is incomplete")
    except (CurriculumError, OSError, ValueError, json.JSONDecodeError) as error:
        issues.append(str(error))
        track = CurriculumTrack(track_id, ())
    cells = sum(len(_MATRIX_CASES.get(lab.id, ())) for lab in track.labs) if matrix else 0
    return TrackVerification(track_id, len(track.labs), cells, tuple(issues))
