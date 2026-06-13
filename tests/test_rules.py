from __future__ import annotations

import unittest
from datetime import date
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
        self.assertAlmostEqual(self.engine.evaluate_expression(expression), 1 / 3)

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

    def test_normalized_duplicate_grouping(self) -> None:
        expression = {
            "aggregate": "duplicate_row_count",
            "object": "Account",
            "field": "Name",
            "normalize": "company_name",
        }
        self.assertEqual(self.engine.evaluate_expression(expression), 2)

    def test_relationship_can_compare_related_field_to_root_field(self) -> None:
        rule = next(
            rule
            for rule in self.rules_document["rules"]
            if rule["id"] == "account-opportunity-owner-mismatch"
        )
        self.assertEqual(self.engine.evaluate_rule(rule).value, 3)

    def test_weighted_group_concentration(self) -> None:
        expression = {
            "aggregate": "largest_group_sum_share",
            "object": "Opportunity",
            "group_by": "OwnerId",
            "field": "Amount",
            "where": {"field": "IsWon", "operator": "is_true"},
        }
        self.assertEqual(self.engine.evaluate_expression(expression), 1.0)

    def test_missing_optional_requirements_skip_rule(self) -> None:
        rule = {
            "id": "lead-only-rule",
            "title": "Lead-only rule",
            "requires": {"objects": ["Lead"]},
            "calculation": {"aggregate": "count", "object": "Lead"},
            "threshold": {"operator": "gt", "value": 0},
        }
        result = self.engine.evaluate_rule(rule)
        self.assertEqual(result.status, "skipped")
        self.assertIn("object Lead", result.message)

    def test_relative_date_rules_use_explicit_as_of_date(self) -> None:
        engine = RuleEngine(self.catalog, as_of=date(2026, 1, 1))
        expression = {
            "aggregate": "count",
            "object": "Opportunity",
            "where": {"field": "CloseDate", "operator": "older_than_days", "value": 90},
        }
        self.assertEqual(engine.evaluate_expression(expression), 2)


if __name__ == "__main__":
    unittest.main()
