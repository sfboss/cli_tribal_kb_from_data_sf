from __future__ import annotations

import unittest
from pathlib import Path

from tribal_kb.data import DataCatalog, load_json
from tribal_kb.rules import RuleEngine, validate_rules_document


ROOT = Path(__file__).resolve().parents[1]


class RuleEngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = DataCatalog.load(ROOT / "examples/objects.json", ROOT / "examples/data")
        cls.rules_document = load_json(ROOT / "examples/rules.json")
        cls.engine = RuleEngine(cls.catalog)

    def test_example_rules_are_valid(self) -> None:
        self.assertEqual(validate_rules_document(self.rules_document), [])
        results = self.engine.evaluate_all(self.rules_document["rules"])
        self.assertFalse([result for result in results if result.status == "error"])

    def test_ratio_calculation(self) -> None:
        expression = {
            "operator": "divide",
            "operands": [
                {
                    "aggregate": "count",
                    "object": "Contact",
                    "where": {"field": "Email", "operator": "is_blank"},
                },
                {"aggregate": "count", "object": "Contact"},
            ],
        }
        self.assertAlmostEqual(self.engine.evaluate_expression(expression), 0.6)

    def test_cross_object_relationship_count(self) -> None:
        expression = {
            "aggregate": "count",
            "object": "Account",
            "where": {
                "relationship": {
                    "object": "Contact",
                    "local_field": "Id",
                    "remote_field": "AccountId",
                },
                "operator": "eq",
                "value": 0,
            },
        }
        self.assertEqual(self.engine.evaluate_expression(expression), 1)

    def test_evidence_is_returned_for_findings(self) -> None:
        result = self.engine.evaluate_rule(self.rules_document["rules"][0])
        self.assertEqual(result.status, "finding")
        self.assertEqual(len(result.evidence), 3)


if __name__ == "__main__":
    unittest.main()

