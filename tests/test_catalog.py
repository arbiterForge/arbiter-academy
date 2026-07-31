from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from academy_engine.catalog import Catalog, CatalogError, load_manifest, load_manifest_file


class CatalogTests(unittest.TestCase):
    def write_catalog(self, payload: object) -> Path:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "catalog.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_catalog_requires_known_keys_unique_ids_and_track_order(self) -> None:
        catalog = {
            "schema_version": 1,
            "labs": [
                {"id": "F01-fork-clone-doctor", "track": "foundations", "order": 1,
                 "manifest": "academy/scenarios/F01-fork-clone-doctor/manifest.json",
                 "checkpoint": "academy/checkpoints/F01-fork-clone-doctor.json",
                 "prerequisites": [], "requires_push_safe_setup": False, "extra": True},
            ],
        }
        with self.assertRaisesRegex(CatalogError, "unknown"):
            Catalog.load(self.write_catalog(catalog))

        catalog["labs"][0].pop("extra")
        catalog["labs"].append(dict(catalog["labs"][0]))
        with self.assertRaisesRegex(CatalogError, "duplicate"):
            Catalog.load(self.write_catalog(catalog))

    def test_catalog_rejects_unsafe_and_noncanonical_paths(self) -> None:
        catalog = {
            "schema_version": 1,
            "labs": [{"id": "F01-fork-clone-doctor", "track": "foundations", "order": 1,
                      "manifest": "academy\\scenarios\\bad.json", "checkpoint": "x",
                      "prerequisites": [], "requires_push_safe_setup": False}],
        }
        with self.assertRaisesRegex(CatalogError, "path"):
            Catalog.load(self.write_catalog(catalog))

    def test_manifest_rejects_parent_paths_collisions_and_unknown_keys(self) -> None:
        baseline = {
            "schema_version": 1, "id": "F01-fork-clone-doctor", "files": [], "removals": [],
            "starting_task": "F01", "checkpoint": "academy/checkpoints/F01-fork-clone-doctor.json",
            "requires_push_safe_setup": False,
        }
        invalid = dict(baseline, files=[{"source": "x", "destination": "../escape"}])
        with self.assertRaisesRegex(CatalogError, "outside"):
            load_manifest(invalid)
        invalid = dict(baseline, files=[{"source": "one", "destination": "a"}, {"source": "two", "destination": "a/b"}])
        with self.assertRaisesRegex(CatalogError, "overlap"):
            load_manifest(invalid)
        invalid = dict(baseline, unexpected=True)
        with self.assertRaisesRegex(CatalogError, "unknown"):
            load_manifest(invalid)

    def test_repository_catalog_has_exact_ordered_track_inventory(self) -> None:
        catalog = Catalog.load(Path(__file__).parents[1] / "academy" / "catalog.json")
        self.assertEqual([lab.id for lab in catalog.labs[:4]], [
            "F01-fork-clone-doctor", "F02-orient-to-state", "F03-work-the-board", "F04-fix-with-evidence",
        ])
        self.assertEqual(len([lab for lab in catalog.labs if lab.track == "foundations"]), 4)
        self.assertEqual(len([lab for lab in catalog.labs if lab.track == "practitioner"]), 8)
        self.assertEqual(len([lab for lab in catalog.labs if lab.track == "power-user"]), 7)

    def test_catalog_rejects_missing_or_misrouted_exact_lab_artifact(self) -> None:
        source = Path(__file__).parents[1] / "academy" / "catalog.json"
        payload = json.loads(source.read_text(encoding="utf-8"))
        payload["labs"].pop()
        with self.assertRaisesRegex(CatalogError, "exact"):
            Catalog.load(self.write_catalog(payload))
        payload = json.loads(source.read_text(encoding="utf-8"))
        payload["labs"][0]["checkpoint"] = "academy/checkpoints/not-f01.json"
        with self.assertRaisesRegex(CatalogError, "mapping"):
            Catalog.load(self.write_catalog(payload))

    def test_manifest_rejects_every_protected_control_surface_before_resolution(self) -> None:
        baseline = {
            "schema_version": 1, "id": "F01-fork-clone-doctor", "files": [], "removals": [],
            "starting_task": "F01", "checkpoint": "academy/checkpoints/F01-fork-clone-doctor.json",
            "requires_push_safe_setup": False,
        }
        for unsafe in (".git/config", ".academy/progress.json", ".codearbiter/CONTEXT.md", "academy/catalog.json"):
            with self.subTest(unsafe=unsafe), self.assertRaisesRegex(CatalogError, "protected"):
                load_manifest(dict(baseline, removals=[unsafe]))

    def test_repository_catalog_maps_every_exact_manifest_and_checkpoint(self) -> None:
        root = Path(__file__).parents[1]
        catalog = Catalog.load(root / "academy" / "catalog.json")
        for lab in catalog.labs:
            manifest = load_manifest_file(root / lab.manifest)
            self.assertEqual(manifest.id, lab.id)
            self.assertEqual(manifest.checkpoint, lab.checkpoint)
            self.assertTrue((root / lab.manifest).parent.joinpath("files", ".gitkeep").is_file())
