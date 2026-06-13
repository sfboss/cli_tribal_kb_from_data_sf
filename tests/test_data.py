from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tribal_kb.data import DataCatalog
from tribal_kb.models import ConfigurationError


class DataCatalogTests(unittest.TestCase):
    def test_direct_object_filename_is_resolved_case_insensitively(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "aCcOuNt.CSV").write_text("Id,Name\n001A,Acme\n", encoding="utf-8")
            config = root / "objects.json"
            config.write_text(json.dumps({"objects": {"Account": {}}}), encoding="utf-8")
            catalog = DataCatalog.load(config, root)
            self.assertEqual(catalog.get_rows("account")[0]["Name"], "Acme")
            self.assertEqual(catalog.objects["Account"].file, "aCcOuNt.CSV")

    def test_nonmatching_filename_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "accounts.csv").write_text("Id,Name\n001A,Acme\n", encoding="utf-8")
            config = root / "objects.json"
            config.write_text(
                json.dumps({"objects": {"Account": {"file": "accounts.csv"}}}),
                encoding="utf-8",
            )
            with self.assertRaises(ConfigurationError):
                DataCatalog.load(config, root)


if __name__ == "__main__":
    unittest.main()
