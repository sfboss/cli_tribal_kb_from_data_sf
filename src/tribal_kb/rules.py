from __future__ import annotations

import math
import re
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
    def __init__(
        self,
        catalog: DataCatalog,
        evidence_limit: int = 8,
        as_of: date | None = None,
    ):
        self.catalog = catalog
        self.evidence_limit = evidence_limit
        self.as_of = as_of or date.today()

    def evaluate_all(self, rules: list[dict[str, Any]]) -> list[RuleResult]:
        return [self.evaluate_rule(rule) for rule in rules]

    def evaluate_rule(self, rule: dict[str, Any]) -> RuleResult:
        try:
            missing = self.missing_requirements(rule.get("requires"))
            if missing:
                return RuleResult(
                    id=rule["id"],
                    title=rule["title"],
                    description=rule.get("description", ""),
                    category=rule.get("category", "General"),
                    severity=rule.get("severity", "medium"),
                    status="skipped",
                    value=None,
                    formatted_value="Skipped",
                    message=f"Skipped because required inputs are missing: {', '.join(missing)}.",
                    recommendation=rule.get("recommendation", ""),
                    calculation=rule["calculation"],
                    threshold=rule["threshold"],
                )
            value = self.evaluate_expression(rule["calculation"])
            is_finding = self.compare(value, rule["threshold"])
            evidence = (
                self.collect_evidence(rule.get("evidence"), rule.get("calculation"))
                if is_finding
                else []
            )
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

    def missing_requirements(self, requirements: Any) -> list[str]:
        if not requirements:
            return []
        if not isinstance(requirements, dict):
            raise ConfigurationError("Rule 'requires' must be an object.")
        missing: list[str] = []
        for object_name in requirements.get("objects", []):
            if not self.catalog.has_object(str(object_name)):
                missing.append(f"object {object_name}")
        fields = requirements.get("fields", {})
        if not isinstance(fields, dict):
            raise ConfigurationError("Rule 'requires.fields' must be an object.")
        for object_name, required_fields in fields.items():
            if not self.catalog.has_object(object_name):
                missing.append(f"object {object_name}")
                continue
            for field in self.catalog.validate_fields(object_name, required_fields):
                missing.append(f"field {object_name}.{field}")
        return missing

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
            return len(
                {
                    normalize_value(row.get(field, ""), expression.get("normalize"))
                    for row in rows
                    if not is_blank(row.get(field))
                }
            )
        if aggregate == "sum":
            require_field(field, aggregate)
            return sum(as_number(row.get(field)) for row in rows if not is_blank(row.get(field)))
        if aggregate == "average":
            require_field(field, aggregate)
            values = [as_number(row.get(field)) for row in rows if not is_blank(row.get(field))]
            return sum(values) / len(values) if values else 0
        if aggregate == "largest_group_share":
            require_field(field, aggregate)
            values = [
                normalize_value(row.get(field, ""), expression.get("normalize"))
                for row in rows
                if not is_blank(row.get(field))
            ]
            counts = Counter(values)
            return max(counts.values()) / len(values) if values else 0
        if aggregate == "largest_group_sum_share":
            require_field(field, aggregate)
            group_by = required_string(expression, "group_by")
            totals: Counter[str] = Counter()
            for row in rows:
                group = normalize_value(row.get(group_by, ""), expression.get("normalize"))
                if not is_blank(group) and not is_blank(row.get(field)):
                    totals[group] += as_number(row.get(field))
            total = sum(totals.values())
            return max(totals.values()) / total if total else 0
        if aggregate in {"duplicate_group_count", "duplicate_row_count"}:
            keys = group_keys(rows, expression)
            counts = Counter(keys)
            minimum_size = int(expression.get("minimum_size", 2))
            if aggregate == "duplicate_group_count":
                return sum(1 for count in counts.values() if count >= minimum_size)
            return sum(count for count in counts.values() if count >= minimum_size)
        raise RuleEvaluationError(f"Unsupported aggregate '{aggregate}'.")

    def filter_rows(
        self, object_name: str, predicate: dict[str, Any] | None
    ) -> list[dict[str, str]]:
        rows = self.catalog.get_rows(object_name)
        if not predicate:
            return list(rows)
        return [row for row in rows if self.matches(row, object_name, predicate, row, object_name)]

    def matches(
        self,
        row: dict[str, str],
        object_name: str,
        predicate: dict[str, Any],
        root_row: dict[str, str] | None = None,
        root_object: str | None = None,
    ) -> bool:
        if "all" in predicate:
            return all(
                self.matches(row, object_name, item, root_row, root_object)
                for item in predicate["all"]
            )
        if "any" in predicate:
            return any(
                self.matches(row, object_name, item, root_row, root_object)
                for item in predicate["any"]
            )
        if "not" in predicate:
            return not self.matches(row, object_name, predicate["not"], root_row, root_object)
        if "relationship" in predicate:
            return self.matches_relationship(
                row,
                object_name,
                predicate,
                root_row or row,
                root_object or object_name,
            )

        field = required_string(predicate, "field")
        operator = required_string(predicate, "operator")
        return compare_field(
            row.get(field, ""),
            operator,
            predicate.get("value"),
            row=row,
            root_row=root_row or row,
            normalize=predicate.get("normalize"),
            case_sensitive=bool(predicate.get("case_sensitive", False)),
            as_of=self.as_of,
        )

    def matches_relationship(
        self,
        row: dict[str, str],
        object_name: str,
        predicate: dict[str, Any],
        root_row: dict[str, str],
        root_object: str,
    ) -> bool:
        relationship = predicate["relationship"]
        related_object = required_string(relationship, "object")
        local_field = required_string(relationship, "local_field")
        remote_field = required_string(relationship, "remote_field")
        rows = self.catalog.related_rows(row, related_object, local_field, remote_field)
        where = relationship.get("where")
        if where:
            rows = [
                item
                for item in rows
                if self.matches(item, related_object, where, root_row, root_object)
            ]
        aggregate = relationship.get("aggregate", "count")
        if aggregate == "count":
            value: float | int = len(rows)
        elif aggregate == "distinct_count":
            field = required_string(relationship, "field")
            value = len(
                {
                    normalize_value(item.get(field, ""), relationship.get("normalize"))
                    for item in rows
                    if not is_blank(item.get(field))
                }
            )
        elif aggregate == "sum":
            field = required_string(relationship, "field")
            value = sum(
                as_number(item.get(field)) for item in rows if not is_blank(item.get(field))
            )
        else:
            raise RuleEvaluationError(f"Unsupported relationship aggregate '{aggregate}'.")
        return self.compare(value, predicate)

    def compare(self, value: Any, condition: dict[str, Any]) -> bool:
        operator = required_string(condition, "operator")
        target = condition.get("value")
        if operator not in COMPARISONS:
            raise RuleEvaluationError(f"Unsupported comparison operator '{operator}'.")
        return COMPARISONS[operator](coerce_comparable(value), coerce_comparable(target))

    def collect_evidence(
        self,
        evidence: dict[str, Any] | None,
        calculation: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        if not evidence:
            return []
        object_name = required_string(evidence, "object")
        where = evidence.get("where")
        if (
            where is None
            and isinstance(calculation, dict)
            and calculation.get("aggregate")
            and str(calculation.get("object", "")).casefold() == object_name.casefold()
        ):
            where = calculation.get("where")
        rows = self.filter_rows(object_name, where)
        fields = evidence.get("fields") or (list(rows[0].keys())[:5] if rows else [])
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


def compare_field(
    raw_value: Any,
    operator: str,
    target: Any,
    *,
    row: dict[str, str] | None = None,
    root_row: dict[str, str] | None = None,
    normalize: Any = None,
    case_sensitive: bool = False,
    as_of: date | None = None,
) -> bool:
    if operator == "is_blank":
        return is_blank(raw_value)
    if operator == "is_not_blank":
        return not is_blank(raw_value)
    if operator == "is_true":
        return str(raw_value).strip().casefold() in {"1", "true", "yes"}
    if operator == "is_false":
        return str(raw_value).strip().casefold() in {"0", "false", "no", ""}
    if operator in {"eq_field", "ne_field"}:
        if row is None:
            raise RuleEvaluationError(f"Operator '{operator}' requires row context.")
        target = row.get(str(target), "")
        operator = "eq" if operator == "eq_field" else "ne"
    if operator in {"eq_root_field", "ne_root_field"}:
        if root_row is None:
            raise RuleEvaluationError(f"Operator '{operator}' requires root row context.")
        target = root_row.get(str(target), "")
        operator = "eq" if operator == "eq_root_field" else "ne"
    raw_value = normalize_value(raw_value, normalize)
    if isinstance(target, list):
        target = [normalize_value(value, normalize) for value in target]
    else:
        target = normalize_value(target, normalize)
    if operator == "contains":
        return comparable_text(target, case_sensitive) in comparable_text(raw_value, case_sensitive)
    if operator == "not_contains":
        return comparable_text(target, case_sensitive) not in comparable_text(raw_value, case_sensitive)
    if operator in {"contains_any", "contains_all"}:
        if not isinstance(target, list):
            raise RuleEvaluationError(f"Operator '{operator}' requires a list value.")
        haystack = comparable_text(raw_value, case_sensitive)
        matches = [comparable_text(value, case_sensitive) in haystack for value in target]
        return any(matches) if operator == "contains_any" else all(matches)
    if operator == "starts_with":
        return comparable_text(raw_value, case_sensitive).startswith(
            comparable_text(target, case_sensitive)
        )
    if operator == "ends_with":
        return comparable_text(raw_value, case_sensitive).endswith(
            comparable_text(target, case_sensitive)
        )
    if operator in {"matches_regex", "not_matches_regex"}:
        flags = 0 if case_sensitive else re.IGNORECASE
        matched = re.search(str(target), str(raw_value), flags=flags) is not None
        return matched if operator == "matches_regex" else not matched
    if operator == "in":
        return comparable_text(raw_value, case_sensitive) in {
            comparable_text(value, case_sensitive) for value in target
        }
    if operator == "not_in":
        return comparable_text(raw_value, case_sensitive) not in {
            comparable_text(value, case_sensitive) for value in target
        }
    if operator == "email_domain_in":
        domain = str(raw_value).rsplit("@", 1)[-1].casefold() if "@" in str(raw_value) else ""
        return domain in {str(value).casefold() for value in target}
    if operator == "length_gt":
        return len(str(raw_value)) > int(target)
    if operator == "length_gte":
        return len(str(raw_value)) >= int(target)
    if operator == "older_than_days":
        parsed = parse_date(raw_value)
        return bool(parsed and parsed < (as_of or date.today()) - timedelta(days=int(target)))
    if operator == "newer_than_days":
        parsed = parse_date(raw_value)
        return bool(parsed and parsed >= (as_of or date.today()) - timedelta(days=int(target)))
    if operator not in COMPARISONS:
        raise RuleEvaluationError(f"Unsupported field operator '{operator}'.")
    return COMPARISONS[operator](coerce_comparable(raw_value), coerce_comparable(target))


def group_keys(rows: list[dict[str, str]], expression: dict[str, Any]) -> list[Any]:
    fields = expression.get("fields")
    if fields is None:
        field = expression.get("field")
        require_field(field, expression.get("aggregate", "group"))
        fields = [field]
    if not isinstance(fields, list) or not fields or not all(isinstance(field, str) for field in fields):
        raise RuleEvaluationError("Grouping requires a non-empty 'field' or 'fields' list.")
    normalizer = expression.get("normalize")
    keys: list[Any] = []
    for row in rows:
        key = tuple(normalize_value(row.get(field, ""), normalizer) for field in fields)
        if expression.get("include_blank", False) or any(not is_blank(value) for value in key):
            keys.append(key)
    return keys


def normalize_value(value: Any, normalizer: Any) -> Any:
    if not normalizer:
        return value
    text = str(value or "").strip()
    if normalizer in {"casefold", "lower", "email"}:
        return text.casefold()
    if normalizer == "alphanumeric":
        return re.sub(r"[^a-z0-9]+", "", text.casefold())
    if normalizer == "text":
        return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", text.casefold())).strip()
    if normalizer == "company_name":
        normalized = re.sub(r"[^a-z0-9]+", " ", text.casefold()).strip()
        suffixes = r"(?:incorporated|inc|corporation|corp|company|co|llc|ltd|limited|plc)"
        return re.sub(rf"\s+{suffixes}$", "", normalized).strip()
    raise RuleEvaluationError(f"Unsupported normalizer '{normalizer}'.")


def comparable_text(value: Any, case_sensitive: bool) -> str:
    text = str(value)
    return text if case_sensitive else text.casefold()


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
