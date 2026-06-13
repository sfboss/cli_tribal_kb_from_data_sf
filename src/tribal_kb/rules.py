from __future__ import annotations

import math
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from typing import Any

from tribal_kb.data import DataCatalog
from tribal_kb.models import ConfigurationError, RuleEvaluationError, RuleResult


SEVERITIES = {"info", "low", "medium", "high", "critical"}
COMPARISONS = {
    "eq": lambda left, right: left == right,
    "ne": lambda left, right: left != right,
    "gt": lambda left, right: left > right,
    "gte": lambda left, right: left >= right,
    "lt": lambda left, right: left < right,
    "lte": lambda left, right: left <= right,
}


class RuleEngine:
    def __init__(self, catalog: DataCatalog, evidence_limit: int = 8):
        self.catalog = catalog
        self.evidence_limit = evidence_limit

    def evaluate_all(self, rules: list[dict[str, Any]]) -> list[RuleResult]:
        return [self.evaluate_rule(rule) for rule in rules]

    def evaluate_rule(self, rule: dict[str, Any]) -> RuleResult:
        try:
            value = self.evaluate_expression(rule["calculation"])
            is_finding = self.compare(value, rule["threshold"])
            evidence = self.collect_evidence(rule.get("evidence")) if is_finding else []
            status = "finding" if is_finding else "pass"
            message_template = rule.get(
                "message",
                "{title}: {formatted_value}",
            )
            formatted = format_value(value, rule.get("format", "number"))
            message = message_template.format(
                title=rule["title"],
                value=value,
                formatted_value=formatted,
            )
            return RuleResult(
                id=rule["id"],
                title=rule["title"],
                description=rule.get("description", ""),
                category=rule.get("category", "General"),
                severity=rule.get("severity", "medium"),
                status=status,
                value=value,
                formatted_value=formatted,
                message=message,
                recommendation=rule.get("recommendation", ""),
                evidence=evidence,
                calculation=rule["calculation"],
                threshold=rule["threshold"],
            )
        except Exception as exc:
            if isinstance(exc, (ConfigurationError, RuleEvaluationError)):
                error = str(exc)
            else:
                error = f"{type(exc).__name__}: {exc}"
            return RuleResult(
                id=str(rule.get("id", "unknown")),
                title=str(rule.get("title", "Invalid rule")),
                description=str(rule.get("description", "")),
                category=str(rule.get("category", "General")),
                severity=str(rule.get("severity", "medium")),
                status="error",
                value=None,
                formatted_value="Error",
                message=error,
                recommendation="Correct the rule definition and run the analysis again.",
                calculation=rule.get("calculation", {}),
                threshold=rule.get("threshold", {}),
            )

    def evaluate_expression(self, expression: Any) -> float | int:
        if isinstance(expression, (int, float)):
            return expression
        if not isinstance(expression, dict):
            raise RuleEvaluationError("Calculation expression must be a number or object.")

        if "aggregate" in expression:
            return self.evaluate_aggregate(expression)

        operation = expression.get("operator")
        operands = expression.get("operands", [])
        values = [self.evaluate_expression(operand) for operand in operands]
        if operation == "add":
            return sum(values)
        if operation == "subtract" and len(values) == 2:
            return values[0] - values[1]
        if operation == "multiply":
            return math.prod(values)
        if operation == "divide" and len(values) == 2:
            return 0 if values[1] == 0 else values[0] / values[1]
        raise RuleEvaluationError(f"Unsupported calculation operator '{operation}'.")

    def evaluate_aggregate(self, expression: dict[str, Any]) -> float | int:
        object_name = required_string(expression, "object")
        aggregate = required_string(expression, "aggregate")
        rows = self.filter_rows(object_name, expression.get("where"))
        field = expression.get("field")

        if aggregate == "count":
            return len(rows)
        if aggregate == "distinct_count":
            require_field(field, aggregate)
            return len({row.get(field, "") for row in rows if not is_blank(row.get(field))})
        if aggregate == "sum":
            require_field(field, aggregate)
            return sum(as_number(row.get(field)) for row in rows if not is_blank(row.get(field)))
        if aggregate == "average":
            require_field(field, aggregate)
            values = [as_number(row.get(field)) for row in rows if not is_blank(row.get(field))]
            return sum(values) / len(values) if values else 0
        if aggregate == "largest_group_share":
            require_field(field, aggregate)
            values = [row.get(field, "") for row in rows if not is_blank(row.get(field))]
            counts = Counter(values)
            return max(counts.values()) / len(values) if values else 0
        raise RuleEvaluationError(f"Unsupported aggregate '{aggregate}'.")

    def filter_rows(
        self, object_name: str, predicate: dict[str, Any] | None
    ) -> list[dict[str, str]]:
        rows = self.catalog.get_rows(object_name)
        if not predicate:
            return list(rows)
        return [row for row in rows if self.matches(row, object_name, predicate)]

    def matches(self, row: dict[str, str], object_name: str, predicate: dict[str, Any]) -> bool:
        if "all" in predicate:
            return all(self.matches(row, object_name, item) for item in predicate["all"])
        if "any" in predicate:
            return any(self.matches(row, object_name, item) for item in predicate["any"])
        if "not" in predicate:
            return not self.matches(row, object_name, predicate["not"])
        if "relationship" in predicate:
            return self.matches_relationship(row, predicate)

        field = required_string(predicate, "field")
        operator = required_string(predicate, "operator")
        return compare_field(row.get(field, ""), operator, predicate.get("value"))

    def matches_relationship(self, row: dict[str, str], predicate: dict[str, Any]) -> bool:
        relationship = predicate["relationship"]
        related_object = required_string(relationship, "object")
        local_field = required_string(relationship, "local_field")
        remote_field = required_string(relationship, "remote_field")
        rows = self.catalog.related_rows(row, related_object, local_field, remote_field)
        where = relationship.get("where")
        if where:
            rows = [item for item in rows if self.matches(item, related_object, where)]
        aggregate = relationship.get("aggregate", "count")
        if aggregate != "count":
            raise RuleEvaluationError("Relationship predicates currently support only count.")
        return self.compare(len(rows), predicate)

    def compare(self, value: Any, condition: dict[str, Any]) -> bool:
        operator = required_string(condition, "operator")
        target = condition.get("value")
        if operator not in COMPARISONS:
            raise RuleEvaluationError(f"Unsupported comparison operator '{operator}'.")
        return COMPARISONS[operator](coerce_comparable(value), coerce_comparable(target))

    def collect_evidence(self, evidence: dict[str, Any] | None) -> list[dict[str, Any]]:
        if not evidence:
            return []
        object_name = required_string(evidence, "object")
        rows = self.filter_rows(object_name, evidence.get("where"))
        fields = evidence.get("fields") or list(rows[0].keys())[:5] if rows else []
        limit = min(int(evidence.get("limit", self.evidence_limit)), self.evidence_limit)
        return [{field: row.get(field, "") for field in fields} for row in rows[:limit]]


def validate_rules_document(document: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    rules = document.get("rules")
    if not isinstance(rules, list) or not rules:
        return ["Rules config must contain a non-empty 'rules' list."]
    seen: set[str] = set()
    for index, rule in enumerate(rules):
        prefix = f"rules[{index}]"
        if not isinstance(rule, dict):
            errors.append(f"{prefix} must be an object.")
            continue
        for key in ("id", "title", "calculation", "threshold"):
            if key not in rule:
                errors.append(f"{prefix} is missing '{key}'.")
        rule_id = rule.get("id")
        if rule_id in seen:
            errors.append(f"Duplicate rule id '{rule_id}'.")
        if isinstance(rule_id, str):
            seen.add(rule_id)
        severity = rule.get("severity", "medium")
        if severity not in SEVERITIES:
            errors.append(f"{prefix} has invalid severity '{severity}'.")
    return errors


def compare_field(raw_value: Any, operator: str, target: Any) -> bool:
    if operator == "is_blank":
        return is_blank(raw_value)
    if operator == "is_not_blank":
        return not is_blank(raw_value)
    if operator == "contains":
        return str(target).casefold() in str(raw_value).casefold()
    if operator == "not_contains":
        return str(target).casefold() not in str(raw_value).casefold()
    if operator == "in":
        return str(raw_value) in {str(value) for value in target}
    if operator == "not_in":
        return str(raw_value) not in {str(value) for value in target}
    if operator == "older_than_days":
        parsed = parse_date(raw_value)
        return bool(parsed and parsed < date.today() - timedelta(days=int(target)))
    if operator == "newer_than_days":
        parsed = parse_date(raw_value)
        return bool(parsed and parsed >= date.today() - timedelta(days=int(target)))
    if operator not in COMPARISONS:
        raise RuleEvaluationError(f"Unsupported field operator '{operator}'.")
    return COMPARISONS[operator](coerce_comparable(raw_value), coerce_comparable(target))


def coerce_comparable(value: Any) -> Any:
    if isinstance(value, (int, float)):
        return value
    if value is None:
        return ""
    text = str(value).strip()
    try:
        return float(text.replace(",", ""))
    except ValueError:
        return text.casefold()


def as_number(value: Any) -> float:
    try:
        return float(str(value).replace(",", "").strip())
    except ValueError as exc:
        raise RuleEvaluationError(f"Expected a numeric value, got '{value}'.") from exc


def parse_date(value: Any) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized).date()
    except ValueError:
        try:
            return date.fromisoformat(text[:10])
        except ValueError as exc:
            raise RuleEvaluationError(f"Expected an ISO date, got '{value}'.") from exc


def is_blank(value: Any) -> bool:
    return value is None or str(value).strip() == ""


def format_value(value: float | int, style: str) -> str:
    if style == "percent":
        return f"{float(value):.1%}"
    if style == "currency":
        return f"${float(value):,.0f}"
    if isinstance(value, float) and not value.is_integer():
        return f"{value:,.2f}"
    return f"{int(value):,}"


def required_string(document: dict[str, Any], key: str) -> str:
    value = document.get(key)
    if not isinstance(value, str) or not value:
        raise RuleEvaluationError(f"Expected non-empty string '{key}'.")
    return value


def require_field(field: Any, aggregate: str) -> None:
    if not isinstance(field, str) or not field:
        raise RuleEvaluationError(f"Aggregate '{aggregate}' requires a field.")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

