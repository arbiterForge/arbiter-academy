"""Privacy-safe branch-derived Academy progress."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from academy_engine.command import run_git


@dataclass(frozen=True)
class ProgressEntry:
    lab_id: str
    attempt: int
    status: str


@dataclass(frozen=True)
class ProgressReport:
    entries: tuple[ProgressEntry, ...]

    def render(self) -> str:
        if not self.entries:
            return "Academy progress: no prepared attempts."
        lines = ["Academy progress:"]
        lines.extend(f"- {item.lab_id} attempt {item.attempt}: {item.status}" for item in self.entries)
        return "\n".join(lines)


def inspect_progress(root: Path) -> ProgressReport:
    """Derive local progress from Academy refs without recording personal data."""
    names = run_git(root, ["for-each-ref", "--format=%(refname:short)", "refs/heads/academy/"]).stdout.splitlines()
    entries: list[ProgressEntry] = []
    for name in names:
        parts = name.split("/")
        if len(parts) == 3 and parts[0] == "academy" and parts[2].isdigit() and int(parts[2]) > 0:
            entries.append(ProgressEntry(parts[1], int(parts[2]), "prepared"))
    return ProgressReport(tuple(sorted(entries, key=lambda item: (item.lab_id, item.attempt))))
