"""Canonical Academy graduation receipts and deterministic catalog exports."""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from academy_engine.catalog import Catalog
from academy_engine.checkpoints import (
    LAB_INVENTORY,
    CheckpointResult,
    canonical_json,
    evaluate_checkpoint,
    load_contracts,
)
from academy_engine.command import run_git

_EMAIL = re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}")
_TOKEN = re.compile(
    r"(?:gh[pousr]_\w{16,}|github_pat_\w{16,}|sk-(?:proj-)?[\w-]{16,}|"
    r"xox[a-z]-[\w-]{10,}|AKIA[0-9A-Z]{16}|-----BEGIN)",
    re.I,
)
_CREDENTIAL_URL = re.compile(r"://[^/\s:@]+:[^/\s@]+@")
_WINDOWS_PATH = re.compile(r"^(?:[A-Za-z]:\\|\\\\[^\\/]+\\)")
_POSIX_ABSOLUTE = re.compile(r"^/(?:[^/\x00]+/)*[^/\x00]*$")
_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class ReceiptPrivacyError(ValueError):
    """A receipt contains private or secret-shaped data."""


@dataclass(frozen=True)
class GraduationReceipt:
    data: dict[str, object]
    digest: str
    path: Path


@dataclass(frozen=True)
class CatalogExport:
    data: dict[str, object]
    digest: str


def validate_receipt_value(value: object) -> None:
    if isinstance(value, str) and (
        _EMAIL.search(value)
        or _TOKEN.search(value)
        or _CREDENTIAL_URL.search(value)
        or _WINDOWS_PATH.search(value)
        or _POSIX_ABSOLUTE.fullmatch(value)
    ):
        raise ReceiptPrivacyError("receipt value is private or secret-shaped.")
    if isinstance(value, dict):
        for key, item in value.items():
            validate_receipt_value(key)
            validate_receipt_value(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            validate_receipt_value(item)


def _digest(value: object) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def _catalog(root: Path) -> tuple[Catalog, bytes, str]:
    try:
        raw = (root / "academy" / "catalog.json").read_bytes()
        payload = json.loads(raw.decode("utf-8"))
        catalog = Catalog.load(root / "academy" / "catalog.json")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("Academy catalog could not be read.") from error
    return catalog, raw, hashlib.sha256(raw).hexdigest()


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _tracked_blob(root: Path, source_commit: str, path: str) -> bytes:
    result = run_git(root, ["show", f"{source_commit}:{path}"], check=False)
    if result.returncode:
        raise ValueError("catalog artifact mapping is untracked.")
    return result.stdout.encode("utf-8", "surrogateescape")


def _source_inventory(
    root: Path, source_commit: str
) -> tuple[Catalog, tuple[object, ...], bytes, bytes]:
    catalog_raw = _tracked_blob(root, source_commit, "academy/catalog.json")
    contract_raw = _tracked_blob(root, source_commit, "academy/contracts.json")
    with tempfile.TemporaryDirectory(prefix="academy-export-source-") as directory:
        snapshot = Path(directory)
        (snapshot / "academy" / "checkpoints").mkdir(parents=True)
        (snapshot / "academy" / "catalog.json").write_bytes(catalog_raw)
        (snapshot / "academy" / "contracts.json").write_bytes(contract_raw)
        for lab_id in LAB_INVENTORY:
            checkpoint_path = f"academy/checkpoints/{lab_id}.json"
            (snapshot / checkpoint_path).write_bytes(
                _tracked_blob(root, source_commit, checkpoint_path)
            )
        catalog = Catalog.load(snapshot / "academy" / "catalog.json")
        contracts = load_contracts(snapshot)
    return catalog, contracts, catalog_raw, contract_raw


def export_catalog(root: Path, output: Path) -> CatalogExport:
    repository = Path(root).resolve()
    source_commit = run_git(repository, ["rev-parse", "HEAD"]).stdout.strip()
    if not _SHA40.fullmatch(source_commit):
        raise ValueError("catalog source commit is invalid.")
    catalog, contracts, catalog_raw, contract_raw = _source_inventory(
        repository, source_commit
    )
    catalog_digest = hashlib.sha256(catalog_raw).hexdigest()
    labs: list[dict[str, object]] = []
    for lab, contract in zip(catalog.labs, contracts, strict=True):
        manifest_raw = _tracked_blob(repository, source_commit, lab.manifest)
        checkpoint_raw = _tracked_blob(repository, source_commit, contract.checkpoint_path)
        try:
            manifest = json.loads(manifest_raw)
            checkpoint = json.loads(checkpoint_raw)
        except json.JSONDecodeError as error:
            raise ValueError("catalog artifact mapping is invalid.") from error
        if (
            manifest.get("id") != lab.id
            or manifest.get("checkpoint") != contract.checkpoint_path
            or checkpoint.get("id") != lab.id
        ):
            raise ValueError("catalog artifact mapping is inconsistent.")
        source_result = run_git(
            repository, ["show", f"{source_commit}:{contract.source_path}"], check=False
        )
        source_raw = (
            source_result.stdout.encode("utf-8", "surrogateescape")
            if source_result.returncode == 0
            else None
        )
        labs.append(
            {
                "id": lab.id,
                "track": lab.track,
                "order": lab.order,
                "manifest_path": lab.manifest,
                "manifest_sha256": hashlib.sha256(manifest_raw).hexdigest(),
                "checkpoint_path": contract.checkpoint_path,
                "checkpoint_sha256": hashlib.sha256(checkpoint_raw).hexdigest(),
                "contract_path": "academy/contracts.json",
                "contract_sha256": hashlib.sha256(contract_raw).hexdigest(),
                "source_path": contract.source_path,
                "source_status": "authored" if source_raw is not None else "pending",
                "source_sha256": hashlib.sha256(source_raw).hexdigest() if source_raw is not None else None,
            }
        )
    data: dict[str, object] = {
        "schema_version": 2,
        "source_commit": source_commit,
        "catalog_path": "academy/catalog.json",
        "catalog_sha256": catalog_digest,
        "contract_path": "academy/contracts.json",
        "contract_sha256": hashlib.sha256(contract_raw).hexdigest(),
        "labs": labs,
    }
    validate_receipt_value(data)
    _atomic_write(output, canonical_json(data))
    return CatalogExport(data, _digest(data))


def _checkpoint_entry(result: CheckpointResult) -> dict[str, object]:
    return {
        "id": result.lab_id,
        "attempt": result.attempt,
        "attempt_head": result.head_commit,
        "prepared_commit": result.prepared_commit,
        "base_commit": result.base_commit,
        "catalog_sha256": result.catalog_digest,
        "definition_sha256": result.definition_digest,
        "manifest_sha256": result.manifest_digest,
        "source_sha256": result.source_digest,
        "contract_sha256": result.contract_digest,
        "result_sha256": result.digest,
    }


def validate_graduation_receipt(data: object) -> None:
    if not isinstance(data, dict):
        raise ValueError("graduation receipt must be an object.")
    expected = {
        "schema_version",
        "source_commit",
        "catalog_sha256",
        "checkpoints",
        "capstone_commit_range",
        "host_labels",
        "completion_date",
    }
    if set(data) != expected or type(data["schema_version"]) is not int or data["schema_version"] != 2:
        raise ValueError("graduation receipt schema is invalid.")
    if not _SHA40.fullmatch(str(data["source_commit"])) or not _SHA256.fullmatch(str(data["catalog_sha256"])):
        raise ValueError("graduation receipt source identity is invalid.")
    checkpoints = data["checkpoints"]
    if not isinstance(checkpoints, list) or len(checkpoints) != len(LAB_INVENTORY):
        raise ValueError("graduation receipt checkpoint inventory is invalid.")
    identifiers: set[str] = set()
    for expected_id, item in zip(LAB_INVENTORY, checkpoints, strict=True):
        if not isinstance(item, dict) or set(item) != {
            "id", "attempt", "attempt_head", "prepared_commit", "base_commit", "catalog_sha256",
            "definition_sha256", "manifest_sha256", "source_sha256",
            "contract_sha256", "result_sha256",
        }:
            raise ValueError("graduation receipt checkpoint entry is invalid.")
        if item["id"] != expected_id or item["id"] in identifiers:
            raise ValueError("graduation receipt checkpoint IDs must be exact and unique.")
        identifiers.add(item["id"])
        if not _ATTEMPT_FOR(expected_id).fullmatch(str(item["attempt"])):
            raise ValueError("graduation receipt attempt is invalid.")
        if (
            not _SHA40.fullmatch(str(item["attempt_head"]))
            or not _SHA40.fullmatch(str(item["prepared_commit"]))
            or not _SHA40.fullmatch(str(item["base_commit"]))
        ):
            raise ValueError("graduation receipt commit identity is invalid.")
        for field in (
            "catalog_sha256", "definition_sha256", "manifest_sha256",
            "source_sha256", "contract_sha256", "result_sha256",
        ):
            if not _SHA256.fullmatch(str(item[field])):
                raise ValueError("graduation receipt digest is invalid.")
        if item["catalog_sha256"] != data["catalog_sha256"]:
            raise ValueError("graduation receipt checkpoint catalog digest is inconsistent.")
    commit_range = data["capstone_commit_range"]
    if not isinstance(commit_range, dict) or set(commit_range) != {"from", "to"}:
        raise ValueError("graduation receipt capstone range is invalid.")
    if not all(_SHA40.fullmatch(str(commit_range[field])) for field in ("from", "to")):
        raise ValueError("graduation receipt capstone range is invalid.")
    capstone = checkpoints[-1]
    if commit_range != {"from": capstone["base_commit"], "to": capstone["attempt_head"]}:
        raise ValueError("graduation receipt capstone range is not bound to the exact attempt.")
    if data["source_commit"] != commit_range["from"]:
        raise ValueError("graduation receipt source commit is not the prepared Academy base.")
    if data["host_labels"] != ["local-git"]:
        raise ValueError("graduation receipt host labels are invalid.")
    if not isinstance(data["completion_date"], str) or not re.fullmatch(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}", data["completion_date"]
    ):
        raise ValueError("graduation receipt completion date is invalid.")
    validate_receipt_value(data)


def _ATTEMPT_FOR(lab_id: str) -> re.Pattern[str]:
    return re.compile(rf"^academy/{re.escape(lab_id)}/[1-9][0-9]*$")


def graduate(root: Path) -> GraduationReceipt:
    repository = Path(root).resolve()
    results = [evaluate_checkpoint(repository, lab_id) for lab_id in LAB_INVENTORY]
    failed = [
        f"{item.lab_id}: {', '.join(item.failed_predicates)}"
        for item in results
        if not item.passed
    ]
    if failed:
        raise ValueError("graduation blocked: " + "; ".join(failed))
    capstone = results[-1]
    if capstone.lab_id != "U07-capstone":
        raise ValueError("graduation blocked: capstone inventory is invalid.")
    if run_git(
        repository,
        ["merge-base", "--is-ancestor", capstone.prepared_commit, capstone.head_commit],
        check=False,
    ).returncode:
        raise ValueError("graduation blocked: capstone range is invalid.")
    catalog_digests = {result.catalog_digest for result in results}
    if len(catalog_digests) != 1 or not next(iter(catalog_digests), ""):
        raise ValueError("graduation blocked: checkpoint catalog identities disagree.")
    catalog_digest = next(iter(catalog_digests))
    source_commit = capstone.base_commit
    data: dict[str, object] = {
        "schema_version": 2,
        "source_commit": source_commit,
        "catalog_sha256": catalog_digest,
        "checkpoints": [_checkpoint_entry(item) for item in results],
        "capstone_commit_range": {
            "from": capstone.base_commit,
            "to": capstone.head_commit,
        },
        "host_labels": ["local-git"],
        "completion_date": datetime.now(timezone.utc).date().isoformat(),
    }
    validate_graduation_receipt(data)
    path = repository / "academy-graduation.json"
    _atomic_write(path, canonical_json(data))
    return GraduationReceipt(data, _digest(data), path)
