from __future__ import annotations

import json
import re
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

    def test_p01_can_declare_only_the_reviewed_board_control_state_seed(self) -> None:
        """Catches generic overlays gaining authority to write protected control state."""
        payload = {
            "schema_version": 1,
            "id": "P01-feature-through-plan",
            "files": [{"source": "scenario.json", "destination": "training_scenarios/P01.json"}],
            "control_state_seed": {
                "source": "open-tasks.md",
                "destination": ".codearbiter/open-tasks.md",
            },
            "removals": [],
            "starting_task": "P01",
            "checkpoint": "academy/checkpoints/P01-feature-through-plan.json",
            "requires_push_safe_setup": False,
        }
        try:
            manifest = load_manifest(payload)
        except CatalogError:
            manifest = None

        self.assertIsNotNone(manifest)
        self.assertEqual(
            (manifest.control_state_seed.source, manifest.control_state_seed.destination),
            ("open-tasks.md", ".codearbiter/open-tasks.md"),
        )

    def test_control_state_seed_rejects_other_labs_protected_sources_and_overlap(self) -> None:
        """Catches the P01 exception broadening generic scenario write authority."""
        baseline = {
            "schema_version": 1,
            "id": "P01-feature-through-plan",
            "files": [{"source": "scenario.json", "destination": "training_scenarios/P01.json"}],
            "control_state_seed": {
                "source": "open-tasks.md",
                "destination": ".codearbiter/open-tasks.md",
            },
            "removals": [],
            "starting_task": "P01",
            "checkpoint": "academy/checkpoints/P01-feature-through-plan.json",
            "requires_push_safe_setup": False,
        }
        cases = (
            (
                "wrong-lab",
                {**baseline, "id": "F01-fork-clone-doctor"},
            ),
            (
                "wrong-target",
                {**baseline, "control_state_seed": {"source": "open-tasks.md", "destination": ".codearbiter/CONTEXT.md"}},
            ),
            (
                "protected-source",
                {**baseline, "control_state_seed": {"source": ".codearbiter/open-tasks.md", "destination": ".codearbiter/open-tasks.md"}},
            ),
            (
                "duplicate-source",
                {**baseline, "files": [{"source": "open-tasks.md", "destination": "training_scenarios/P01.json"}]},
            ),
            (
                "overlap",
                {**baseline, "files": [{"source": "scenario.json", "destination": ".codearbiter/open-tasks.md"}]},
            ),
            (
                "removal-overlap",
                {**baseline, "removals": [".codearbiter/open-tasks.md"]},
            ),
        )
        for label, payload in cases:
            with self.subTest(label=label), self.assertRaises(CatalogError):
                load_manifest(payload)

    def test_repository_catalog_maps_every_exact_manifest_and_checkpoint(self) -> None:
        root = Path(__file__).parents[1]
        catalog = Catalog.load(root / "academy" / "catalog.json")
        for lab in catalog.labs:
            manifest = load_manifest_file(root / lab.manifest)
            self.assertEqual(manifest.id, lab.id)
            self.assertEqual(manifest.checkpoint, lab.checkpoint)
            self.assertTrue((root / lab.manifest).parent.joinpath("files", ".gitkeep").is_file())

    def test_catalog_schema_literally_pins_the_exact_ordered_artifact_map(self) -> None:
        root = Path(__file__).parents[1]
        schema = json.loads((root / "academy" / "catalog.schema.json").read_text(encoding="utf-8"))
        catalog = json.loads((root / "academy" / "catalog.json").read_text(encoding="utf-8"))
        labs_schema = schema["properties"]["labs"]
        self.assertEqual(labs_schema["minItems"], 19)
        self.assertEqual(labs_schema["maxItems"], 19)
        self.assertFalse(labs_schema["items"])
        self.assertEqual(len(labs_schema["prefixItems"]), 19)
        for item, pinned in zip(catalog["labs"], labs_schema["prefixItems"], strict=True):
            constants = pinned["properties"]
            for field in ("id", "track", "order", "manifest", "checkpoint"):
                self.assertEqual(constants[field]["const"], item[field])

    def test_schema_path_patterns_reject_dot_components_and_control_paths(self) -> None:
        root = Path(__file__).parents[1]
        catalog_schema = json.loads((root / "academy" / "catalog.schema.json").read_text(encoding="utf-8"))
        scenario_schema = json.loads((root / "academy" / "scenario.schema.json").read_text(encoding="utf-8"))
        generic_patterns = [catalog_schema["$defs"]["path"]["pattern"], scenario_schema["$defs"]["path"]["pattern"]]
        for pattern in generic_patterns:
            expression = re.compile(pattern)
            for unsafe in ("../x", "a/./b", "a/../b", "a\\b"):
                with self.subTest(pattern=pattern, unsafe=unsafe):
                    self.assertIsNone(expression.fullmatch(unsafe))
            self.assertIsNotNone(expression.fullmatch("academy/scenarios/F01-fork-clone-doctor/manifest.json"))
        scenario_expression = re.compile(scenario_schema["$defs"]["scenario_path"]["pattern"])
        for unsafe in ("../x", "a/./b", "a/../b", ".git/config", ".academy/progress.json", ".codearbiter/CONTEXT.md", "academy/catalog.json", "a\\b"):
            with self.subTest(unsafe=unsafe):
                self.assertIsNone(scenario_expression.fullmatch(unsafe))
        self.assertIsNotNone(scenario_expression.fullmatch("exercise/seed.txt"))

    def test_catalog_schema_positional_contract_rejects_swapped_missing_and_extra_rows(self) -> None:
        root = Path(__file__).parents[1]
        schema = json.loads((root / "academy" / "catalog.schema.json").read_text(encoding="utf-8"))
        catalog = json.loads((root / "academy" / "catalog.json").read_text(encoding="utf-8"))
        prefix_items = schema["properties"]["labs"]["prefixItems"]

        def accepts(payload: list[dict[str, object]]) -> bool:
            if len(payload) != len(prefix_items) or schema["properties"]["labs"]["items"] is not False:
                return False
            for row, position in zip(payload, prefix_items, strict=True):
                for field in ("id", "track", "order", "manifest", "checkpoint"):
                    if row.get(field) != position["properties"][field]["const"]:
                        return False
            return True

        self.assertTrue(accepts(catalog["labs"]))
        swapped = list(catalog["labs"])
        swapped[0], swapped[1] = swapped[1], swapped[0]
        self.assertFalse(accepts(swapped))
        self.assertFalse(accepts(catalog["labs"][:-1]))
        self.assertFalse(accepts(catalog["labs"] + [catalog["labs"][0]]))
