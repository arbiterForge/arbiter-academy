"""Fresh, canonical, non-sensitive checkpoint progress documents."""
from __future__ import annotations

from pathlib import Path

from academy_engine.checkpoints import CheckpointResult, LAB_CONTRACT, canonical_json, evaluate_checkpoint


def _digest(value: object) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError("checkpoint result has an invalid bound digest.")
    return value


def record_checkpoint(progress_path: Path, result: CheckpointResult) -> None:
    """Replace, never merge, progress with one fully-bound catalog result."""
    if progress_path.name != "progress.json" or progress_path.parent.name != ".academy":
        raise ValueError("progress path must be the canonical Academy progress document.")
    if result.lab_id not in LAB_CONTRACT:
        raise ValueError("checkpoint result is not a known Academy lab.")
    recomputed = evaluate_checkpoint(progress_path.parent.parent, result.lab_id)
    if recomputed != result:
        raise ValueError("checkpoint result is not fresh repository evidence.")
    entry = {
        "id": result.lab_id,
        "catalog_sha256": _digest(result.catalog_digest),
        "definition_sha256": _digest(result.definition_digest),
        "manifest_sha256": _digest(result.manifest_digest),
        "source_sha256": _digest(result.source_digest),
        "contract_sha256": _digest(result.contract_digest),
        "result_sha256": _digest(result.digest),
    }
    payload = {"schema_version": 1, "checkpoints": [entry]}
    progress_path.parent.mkdir(parents=True, exist_ok=True)
    progress_path.write_bytes(canonical_json(payload))
