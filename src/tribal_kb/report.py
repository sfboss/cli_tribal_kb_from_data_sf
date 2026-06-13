from __future__ import annotations

import html
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from tribal_kb.models import AnalysisResult, ConfigurationError, RuleResult


BUILTIN_TEMPLATES = ("executive", "midnight", "blueprint", "field-notes", "signal-board")
MERGE_FIELD = re.compile(r"{{\s*([a-z][a-z0-9_]*)\s*}}")


def write_html_report(
    result: AnalysisResult, output_path: Path, template: str | Path = "executive"
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_html_report(result, template), encoding="utf-8")


def write_json_report(result: AnalysisResult, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")


def render_html_report(result: AnalysisResult, template: str | Path = "executive") -> str:
    template_name, template_text = load_template(template)
    counts = result.counts
    ordered_rules = sorted(
        result.rules,
        key=lambda item: (
            status_rank(item.status),
            severity_rank(item.severity),
            item.category,
            item.title,
        ),
    )
    source_chips = "".join(
        f'<span class="source-chip"><strong>{escape(name)}</strong>{count:,} rows</span>'
        for name, count in result.source_summary.items()
    )
    fields = {
        "report_title": escape(result.report_title),
        "report_subtitle": escape(result.report_subtitle),
        "generated_at": escape(result.generated_at),
        "as_of": escape(result.as_of),
        "record_count": f"{sum(result.source_summary.values()):,}",
        "source_count": f"{len(result.source_summary):,}",
        "rule_count": f"{len(result.rules):,}",
        "finding_count": f"{counts['finding']:,}",
        "pass_count": f"{counts['pass']:,}",
        "skipped_count": f"{counts['skipped']:,}",
        "error_count": f"{counts['error']:,}",
        "summary_text": escape(summary_text(result)),
        "source_chips": source_chips,
        "rule_cards": "".join(render_rule_card(rule) for rule in ordered_rules),
        "category_rows": render_category_rows(result.rules),
        "template_name": escape(template_name),
    }

    unknown = sorted(set(MERGE_FIELD.findall(template_text)) - fields.keys())
    if unknown:
        raise ConfigurationError(
            f"Template '{template_name}' contains unknown merge fields: {', '.join(unknown)}"
        )
    return MERGE_FIELD.sub(lambda match: fields[match.group(1)], template_text)


def load_template(template: str | Path) -> tuple[str, str]:
    candidate = Path(template)
    if candidate.exists():
        if candidate.suffix.casefold() != ".html":
            raise ConfigurationError(f"Custom report template must be an HTML file: {candidate}")
        return candidate.stem, candidate.read_text(encoding="utf-8")

    name = str(template)
    if name not in BUILTIN_TEMPLATES:
        raise ConfigurationError(
            f"Unknown report template '{name}'. Built-ins: {', '.join(BUILTIN_TEMPLATES)}"
        )
    path = Path(__file__).with_name("templates") / f"{name}.html"
    return name, path.read_text(encoding="utf-8")


def summary_text(result: AnalysisResult) -> str:
    counts = result.counts
    finding_label = "finding" if counts["finding"] == 1 else "findings"
    pass_label = "healthy signal" if counts["pass"] == 1 else "healthy signals"
    return (
        f"{counts['finding']} deterministic {finding_label} and {counts['pass']} {pass_label} "
        f"were produced by {len(result.rules)} rules across "
        f"{sum(result.source_summary.values())} records from {len(result.source_summary)} objects."
    )


def render_category_rows(rules: list[RuleResult]) -> str:
    categories: dict[str, Counter[str]] = {}
    for rule in rules:
        categories.setdefault(rule.category, Counter())[rule.status] += 1
    return "".join(
        "<tr>"
        f"<td>{escape(category)}</td>"
        f"<td>{counts['finding']}</td>"
        f"<td>{counts['pass']}</td>"
        f"<td>{counts['skipped']}</td>"
        f"<td>{counts['error']}</td>"
        "</tr>"
        for category, counts in sorted(categories.items())
    )


def render_rule_card(rule: RuleResult) -> str:
    evidence = render_evidence(rule.evidence)
    recommendation = (
        f'<p class="recommendation"><strong>Operator note:</strong> {escape(rule.recommendation)}</p>'
        if rule.recommendation
        else ""
    )
    description = (
        f'<p class="description">{escape(rule.description)}</p>' if rule.description else ""
    )
    basis = (
        '<details class="basis"><summary>Deterministic basis</summary>'
        f"<pre>{escape(json.dumps({'calculation': rule.calculation, 'threshold': rule.threshold}, indent=2))}</pre>"
        "</details>"
    )
    details = (
        '<details class="context"><summary>Review details and evidence</summary>'
        f'<div class="detail-body">{description}{recommendation}{evidence}{basis}</div></details>'
    )
    return f"""
<article class="rule {escape(rule.status)} severity-{escape(rule.severity)}" data-status="{escape(rule.status)}" data-category="{escape(rule.category)}">
  <div class="rule-main">
    <div>
      <div class="labels"><span class="pill {escape(rule.status)}">{escape(rule.status)}</span><span class="pill">{escape(rule.severity)}</span><span class="pill">{escape(rule.category)}</span></div>
      <h3>{escape(rule.title)}</h3>
      <p class="message">{escape(rule.message)}</p>
    </div>
    <div class="metric">{escape(rule.formatted_value)}</div>
  </div>
  {details}
</article>"""


def render_evidence(evidence: list[dict[str, Any]]) -> str:
    if not evidence:
        return '<p class="no-evidence">No row-level evidence was requested for this rule.</p>'
    fields = list(evidence[0].keys())
    head = "".join(f"<th>{escape(field)}</th>" for field in fields)
    rows = "".join(
        "<tr>" + "".join(f"<td>{escape(row.get(field, ''))}</td>" for field in fields) + "</tr>"
        for row in evidence
    )
    return f'<div class="table-wrap"><table><thead><tr>{head}</tr></thead><tbody>{rows}</tbody></table></div>'


def escape(value: Any) -> str:
    return html.escape(str(value))


def severity_rank(severity: str) -> int:
    return {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}.get(severity, 5)


def status_rank(status: str) -> int:
    return {"finding": 0, "error": 1, "pass": 2, "skipped": 3}.get(status, 4)
