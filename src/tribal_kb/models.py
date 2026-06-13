from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


class TribalKBError(Exception):
    """Base exception for errors that should be shown cleanly by the CLI."""


class ConfigurationError(TribalKBError):
    """Raised when object or rule configuration is invalid."""


class RuleEvaluationError(TribalKBError):
    """Raised when a rule cannot be evaluated."""


@dataclass(frozen=True)
class ObjectConfig:
    name: str
    file: str
    primary_key: str = "Id"


@dataclass
class RuleResult:
    id: str
    title: str
    description: str
    category: str
    severity: str
    status: str
    value: float | int | str | None
    formatted_value: str
    message: str
    recommendation: str
    evidence: list[dict[str, Any]] = field(default_factory=list)
    calculation: dict[str, Any] = field(default_factory=dict)
    threshold: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AnalysisResult:
    report_title: str
    report_subtitle: str
    generated_at: str
    source_summary: dict[str, int]
    rules: list[RuleResult]

    @property
    def counts(self) -> dict[str, int]:
        counts = {"finding": 0, "pass": 0, "error": 0}
        for rule in self.rules:
            counts[rule.status] = counts.get(rule.status, 0) + 1
        return counts

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["counts"] = self.counts
        return result

