import tempfile
import unittest
from pathlib import Path
from academy_engine.receipt import export_catalog


class CatalogExportTests(unittest.TestCase):
    def test_export_rejects_missing_checkpoint_mapping(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "academy").mkdir()
            (root / "academy" / "catalog.json").write_text('{"schema_version":1,"labs":[]}', encoding="utf-8")
            with self.assertRaises(ValueError): export_catalog(root, root / "catalog-export.json")
