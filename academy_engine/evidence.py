"""Canonical, privacy-safe persisted checkpoint evidence."""
from __future__ import annotations
import json
from pathlib import Path
from academy_engine.checkpoints import CheckpointResult, canonical_json

def record_checkpoint(progress_path: Path, result: CheckpointResult) -> None:
    entries = []
    try:
        current = json.loads(progress_path.read_text(encoding="utf-8")); entries = current.get("checkpoints", []) if isinstance(current, dict) else []
    except (OSError, UnicodeDecodeError, json.JSONDecodeError): pass
    safe = [item for item in entries if isinstance(item, dict) and set(item) == {"id", "digest"} and isinstance(item["id"], str) and isinstance(item["digest"], str) and len(item["digest"]) == 64 and item["id"] != result.lab_id]
    safe.append({"id": result.lab_id, "digest": result.digest})
    payload = {"schema_version": 1, "checkpoints": sorted(safe, key=lambda item: item["id"])}
    progress_path.parent.mkdir(parents=True, exist_ok=True); progress_path.write_bytes(canonical_json(payload))
