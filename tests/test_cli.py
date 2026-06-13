from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from tribal_kb.cli import main
from tribal_kb.report import BUILTIN_TEMPLATES


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
            rendered = html_path.read_text(encoding="utf-8")
            self.assertIn("Deterministic observations", rendered)
            self.assertIn("Deterministic basis", rendered)
            self.assertTrue(json_path.exists())
            self.assertEqual(json.loads(json_path.read_text(encoding="utf-8"))["as_of"], str(date.today()))

    def test_all_builtin_templates_render(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            for template in BUILTIN_TEMPLATES:
                html_path = Path(directory) / f"{template}.html"
                code = main(
                    [
                        "analyze",
                        "--data-dir",
                        str(ROOT / "examples/data"),
                        "--objects",
                        str(ROOT / "examples/objects.json"),
                        "--rules",
                        str(ROOT / "examples/rules.json"),
                        "--as-of",
                        "2026-06-13",
                        "--template",
                        template,
                        "--output",
                        str(html_path),
                    ]
                )
                self.assertEqual(code, 0)
                self.assertNotIn("{{", html_path.read_text(encoding="utf-8"))

    def test_custom_merge_field_template_renders(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            template = root / "custom.html"
            output = root / "custom-report.html"
            template.write_text(
                "<h1>{{report_title}}</h1><p>{{as_of}}</p><strong>{{finding_count}}</strong>",
                encoding="utf-8",
            )
            code = main(
                [
                    "analyze",
                    "--data-dir",
                    str(ROOT / "examples/data"),
                    "--objects",
                    str(ROOT / "examples/objects.json"),
                    "--rules",
                    str(ROOT / "examples/rules.json"),
                    "--as-of",
                    "2026-06-13",
                    "--template",
                    str(template),
                    "--output",
                    str(output),
                ]
            )
            self.assertEqual(code, 0)
            self.assertIn("2026-06-13", output.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
