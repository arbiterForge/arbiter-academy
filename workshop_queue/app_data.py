"""Resolve writable application data and initialize its ticket store."""

from __future__ import annotations

import os
import tempfile
from importlib.resources import files
from pathlib import Path
from typing import Callable, Mapping

from .store import StoreWriteError


def _source_checkout_data_root(package_directory: Path) -> Path | None:
    package_directory = package_directory.resolve()
    project_root = package_directory.parent
    data_root = project_root / "data"
    if package_directory.name == "workshop_queue" and (project_root / "pyproject.toml").is_file():
        return data_root.resolve()
    return None


def resolve_data_root(
    override: Path | str | None,
    *,
    package_directory: Path | None = None,
    environ: Mapping[str, str] | None = None,
    platform_name: str | None = None,
    home: Path | None = None,
) -> Path:
    """Return the explicit, checkout-local, or platform user-data root."""

    if override is not None:
        return Path(override).expanduser().resolve()

    package_directory = package_directory or Path(__file__).resolve().parent
    checkout_root = _source_checkout_data_root(package_directory)
    if checkout_root is not None:
        return checkout_root

    environment = os.environ if environ is None else environ
    platform_name = os.name if platform_name is None else platform_name
    home = Path.home() if home is None else home
    if platform_name == "nt":
        local_app_data = environment.get("LOCALAPPDATA")
        candidate = Path(local_app_data) if local_app_data else None
        base = candidate if candidate is not None and candidate.is_absolute() else home / "AppData" / "Local"
        return (base / "ArbiterAcademy" / "WorkshopQueue").expanduser().resolve()

    xdg_data_home = environment.get("XDG_DATA_HOME")
    candidate = Path(xdg_data_home) if xdg_data_home else None
    base = candidate if candidate is not None and candidate.is_absolute() else home / ".local" / "share"
    return (base / "arbiter-academy" / "workshop-queue").expanduser().resolve()


def bundled_seed_bytes() -> bytes:
    try:
        return files("workshop_queue").joinpath("seed", "tickets.json").read_bytes()
    except OSError as exc:
        raise StoreWriteError("could not read bundled ticket seed") from exc


def initialize_ticket_store(
    path: Path | str,
    *,
    seed: bytes | None = None,
    link: Callable[[Path, Path], object] = os.link,
) -> None:
    """Atomically create a missing store from the immutable package seed."""

    destination = Path(path)
    if destination.exists():
        return

    temporary_path: Path | None = None
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            return
        seed_bytes = bundled_seed_bytes() if seed is None else seed
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f"{destination.name}.",
            suffix=".tmp",
            dir=destination.parent,
        )
        temporary_path = Path(temporary_name)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(seed_bytes)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            link(temporary_path, destination)
        except FileExistsError:
            pass
    except StoreWriteError:
        raise
    except OSError as exc:
        raise StoreWriteError(f"could not initialize ticket store {destination}") from exc
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass
