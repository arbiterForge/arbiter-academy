"""Canonical Academy graduation receipts and exports."""
from __future__ import annotations
import hashlib, json, re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from academy_engine.catalog import Catalog
from academy_engine.checkpoints import CheckpointError, canonical_json, evaluate_checkpoint
from academy_engine.command import run_git

_PRIVATE = re.compile(r"(?:[A-Za-z]:\\|\\\\[^\\/]+\\|/(?:[^\s/]+/)+|[\w.+-]+@[\w.-]+|(?:gh[pousr]_\w{16,}|github_pat_\w{16,}|sk-(?:proj-)?[\w-]{16,}|xox[a-z]-[\w-]{10,}|AKIA[0-9A-Z]{16})|://[^/\s:@]+:[^/\s@]+@|-----BEGIN)", re.I)
class ReceiptPrivacyError(ValueError): pass
@dataclass(frozen=True)
class GraduationReceipt: data: dict[str, object]; digest: str
@dataclass(frozen=True)
class CatalogExport: data: dict[str, object]; digest: str
def validate_receipt_value(value: object) -> None:
    if isinstance(value, str) and _PRIVATE.search(value): raise ReceiptPrivacyError("receipt value is private or secret-shaped.")
    if isinstance(value, dict):
        for key, item in value.items(): validate_receipt_value(key); validate_receipt_value(item)
    if isinstance(value, (list, tuple)):
        for item in value: validate_receipt_value(item)
def _digest(data: object) -> str: return hashlib.sha256(canonical_json(data)).hexdigest()
def _catalog(root: Path) -> tuple[Catalog, str]:
    try:
        payload = json.loads((root / "academy" / "catalog.json").read_text(encoding="utf-8"))
        return Catalog.load(root / "academy" / "catalog.json"), _digest(payload)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("Academy catalog could not be read.") from error
def export_catalog(root: Path, output: Path) -> CatalogExport:
    catalog, catalog_digest = _catalog(root)
    labs=[]
    for lab in catalog.labs:
        manifest = root / lab.manifest; checkpoint = root / lab.checkpoint
        if not manifest.is_file() or not checkpoint.is_file(): raise ValueError("catalog artifact mapping is missing.")
        try:
            definition = json.loads(checkpoint.read_text(encoding="utf-8")); manifest_data=json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error: raise ValueError("catalog artifact mapping is invalid.") from error
        if definition.get("id") != lab.id or manifest_data.get("id") != lab.id or manifest_data.get("checkpoint") != lab.checkpoint: raise ValueError("catalog artifact mapping is inconsistent.")
        labs.append({"id":lab.id,"track":lab.track,"order":lab.order,"manifest_sha256":_digest(manifest_data),"checkpoint_sha256":_digest(definition)})
    data={"schema_version":1,"catalog_sha256":catalog_digest,"labs":labs}; validate_receipt_value(data); output.write_bytes(canonical_json(data)); return CatalogExport(data, _digest(data))
def graduate(root: Path) -> GraduationReceipt:
    catalog, catalog_digest = _catalog(root); results=[]
    for lab in catalog.labs:
        result=evaluate_checkpoint(root, lab.id); results.append(result)
    failed=[f"{item.lab_id}: {', '.join(item.failed_predicates)}" for item in results if not item.passed]
    if failed: raise ValueError("graduation blocked: " + "; ".join(failed))
    capstone = "academy/U07-capstone/1"
    try:
        base = run_git(root,["merge-base","main",capstone]).stdout.strip()
        head = run_git(root,["rev-parse",capstone]).stdout.strip()
    except Exception as error:
        raise ValueError("graduation blocked: U07-capstone prepared attempt is unavailable.") from error
    data={"schema_version":1,"source_commit":head,"catalog_sha256":catalog_digest,"checkpoints":[{"id":item.lab_id,"digest":item.digest} for item in results],"capstone_commit_range":{"from":base,"to":head},"host_labels":["local-git"],"completion_date":datetime.now(timezone.utc).date().isoformat()}
    validate_receipt_value(data); return GraduationReceipt(data,_digest(data))
