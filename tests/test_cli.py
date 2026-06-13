from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tribal_kb.cli import main


ROOT = Path(__file__).resolve().parents[1]


class CliTests(unittest.TestCase):
    def test_analyze_writes_html_and_json(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            html_path = Path(directory) / "report.html"
            json_path = Path(directory) / "report.json"
            code = main(
                [
                    "analyze",
                    "--data-dir",
                    str(ROOT / "examples/data"),
                    "--objects",
                    str(ROOT / "examples/objects.json"),
                    "--rules",
                    str(ROOT / "examples/rules.json"),
                    "--output",
                    str(html_path),
                    "--json-output",
                    str(json_path),
                ]
            )
            self.assertEqual(code, 0)
            self.assertIn("What the data is telling you", html_path.read_text(encoding="utf-8"))
            self.assertTrue(json_path.exists())


if __name__ == "__main__":
    unittest.main()

