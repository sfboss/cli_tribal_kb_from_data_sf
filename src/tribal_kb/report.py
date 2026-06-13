from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from tribal_kb.models import AnalysisResult, RuleResult


def write_html_report(result: AnalysisResult, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_html_report(result), encoding="utf-8")


def write_json_report(result: AnalysisResult, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")


def render_html_report(result: AnalysisResult) -> str:
    counts = result.counts
    findings = sorted(
        result.rules,
        key=lambda item: (
            item.status != "finding",
            severity_rank(item.severity),
            item.title,
        ),
    )
    source_chips = "".join(
        f'<span class="source-chip"><strong>{escape(name)}</strong>{count:,} rows</span>'
        for name, count in result.source_summary.items()
    )
    cards = "".join(render_rule_card(rule) for rule in findings)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(result.report_title)}</title>
  <style>
    :root {{
      --ink: #17233d; --muted: #62708a; --paper: #f6f4ef; --card: #fffefa;
      --line: #e4dfd4; --navy: #12233f; --blue: #406f8f; --gold: #c99b45;
      --critical: #a22b35; --high: #c55038; --medium: #ba7c20;
      --low: #47798c; --info: #68738a; --pass: #3f775a; --shadow: 0 18px 50px rgba(32,38,52,.09);
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; color: var(--ink); background: var(--paper); font: 15px/1.55 Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    header {{ color: #fff; background: radial-gradient(circle at 80% 5%, #355d76 0, transparent 38%), linear-gradient(135deg, #0d1d35, #182b49 68%, #243a55); padding: 72px 24px 90px; }}
    .wrap {{ width: min(1120px, calc(100% - 36px)); margin: 0 auto; }}
    .eyebrow {{ color: #e0be77; text-transform: uppercase; letter-spacing: .18em; font-size: 11px; font-weight: 800; }}
    h1 {{ max-width: 780px; margin: 13px 0 10px; font-family: Georgia, serif; font-size: clamp(38px, 7vw, 72px); line-height: .98; font-weight: 500; letter-spacing: -.045em; }}
    .subtitle {{ max-width: 720px; margin: 0; color: #c9d3df; font-size: 17px; }}
    .meta {{ margin-top: 34px; color: #9fb0c3; font-size: 12px; letter-spacing: .04em; }}
    main {{ margin-top: -45px; padding-bottom: 70px; }}
    .summary {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; }}
    .stat {{ background: var(--card); border: 1px solid var(--line); border-radius: 18px; padding: 21px 24px; box-shadow: var(--shadow); }}
    .stat strong {{ display: block; font-family: Georgia, serif; font-size: 34px; line-height: 1; }}
    .stat span {{ display: block; margin-top: 8px; color: var(--muted); font-size: 11px; text-transform: uppercase; letter-spacing: .13em; font-weight: 800; }}
    .section-head {{ display: flex; align-items: end; justify-content: space-between; gap: 18px; margin: 50px 0 18px; }}
    h2 {{ margin: 0; font: 500 31px/1.1 Georgia, serif; letter-spacing: -.02em; }}
    .filters {{ display: flex; flex-wrap: wrap; gap: 7px; }}
    button {{ border: 1px solid var(--line); color: var(--muted); background: #fff; border-radius: 99px; padding: 8px 12px; font: inherit; font-size: 12px; font-weight: 700; cursor: pointer; }}
    button.active {{ color: #fff; border-color: var(--navy); background: var(--navy); }}
    .rule-grid {{ display: grid; gap: 14px; }}
    .rule {{ background: var(--card); border: 1px solid var(--line); border-left: 5px solid var(--info); border-radius: 16px; overflow: hidden; box-shadow: 0 8px 30px rgba(32,38,52,.045); }}
    .rule.finding.severity-critical {{ border-left-color: var(--critical); }}
    .rule.finding.severity-high {{ border-left-color: var(--high); }}
    .rule.finding.severity-medium {{ border-left-color: var(--medium); }}
    .rule.finding.severity-low {{ border-left-color: var(--low); }}
    .rule.pass {{ border-left-color: var(--pass); }}
    .rule.error {{ border-left-color: var(--critical); }}
    .rule-main {{ display: grid; grid-template-columns: 1fr auto; gap: 18px; padding: 23px 25px; }}
    .labels {{ display: flex; flex-wrap: wrap; align-items: center; gap: 7px; margin-bottom: 8px; }}
    .pill {{ border-radius: 99px; padding: 4px 8px; background: #eef0f1; color: var(--muted); font-size: 10px; font-weight: 850; letter-spacing: .08em; text-transform: uppercase; }}
    .pill.finding {{ color: #8a4e13; background: #f9ead2; }}
    .pill.pass {{ color: #326146; background: #e3f0e8; }}
    .pill.error {{ color: #8b2730; background: #f7e3e3; }}
    h3 {{ margin: 0; font-size: 18px; line-height: 1.3; }}
    .message {{ margin: 8px 0 0; color: var(--muted); }}
    .metric {{ min-width: 120px; align-self: center; text-align: right; font: 500 27px/1 Georgia, serif; color: var(--navy); }}
    details {{ border-top: 1px solid var(--line); }}
    summary {{ padding: 13px 25px; cursor: pointer; color: var(--muted); font-size: 12px; font-weight: 800; }}
    .detail-body {{ padding: 3px 25px 22px; }}
    .recommendation {{ margin: 0 0 16px; padding: 13px 15px; border-radius: 10px; background: #f3f0e8; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
    th, td {{ max-width: 280px; padding: 9px 10px; border-bottom: 1px solid var(--line); text-align: left; overflow-wrap: anywhere; }}
    th {{ color: var(--muted); font-size: 10px; text-transform: uppercase; letter-spacing: .08em; }}
    .sources {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 15px; }}
    .source-chip {{ display: flex; gap: 8px; border: 1px solid var(--line); border-radius: 99px; padding: 7px 11px; color: var(--muted); background: #fff; font-size: 11px; }}
    footer {{ color: var(--muted); padding: 20px 0 45px; font-size: 11px; }}
    @media (max-width: 700px) {{
      header {{ padding-top: 50px; }} .summary {{ grid-template-columns: 1fr; }} .section-head {{ align-items: start; flex-direction: column; }}
      .rule-main {{ grid-template-columns: 1fr; }} .metric {{ text-align: left; }}
    }}
    @media print {{ button {{ display: none; }} body {{ background: #fff; }} header {{ padding-top: 35px; }} .rule {{ break-inside: avoid; }} }}
  </style>
</head>
<body>
  <header><div class="wrap">
    <div class="eyebrow">Salesforce Data Intelligence</div>
    <h1>{escape(result.report_title)}</h1>
    <p class="subtitle">{escape(result.report_subtitle)}</p>
    <div class="meta">Generated {escape(result.generated_at)} · {sum(result.source_summary.values()):,} records analyzed</div>
  </div></header>
  <main class="wrap">
    <section class="summary">
      <div class="stat"><strong>{counts["finding"]}</strong><span>Findings</span></div>
      <div class="stat"><strong>{counts["pass"]}</strong><span>Healthy Signals</span></div>
      <div class="stat"><strong>{counts["error"]}</strong><span>Rule Errors</span></div>
    </section>
    <section>
      <div class="section-head">
        <div><div class="eyebrow" style="color:var(--gold)">Analysis</div><h2>What the data is telling you</h2></div>
        <div class="filters">
          <button class="active" data-filter="all">All</button>
          <button data-filter="finding">Findings</button>
          <button data-filter="pass">Healthy</button>
          <button data-filter="error">Errors</button>
        </div>
      </div>
      <div class="rule-grid">{cards}</div>
    </section>
    <section>
      <div class="section-head"><div><div class="eyebrow" style="color:var(--gold)">Coverage</div><h2>Sources analyzed</h2></div></div>
      <div class="sources">{source_chips}</div>
    </section>
  </main>
  <footer class="wrap">Generated by Tribal KB. This report is self-contained and can be shared as a single HTML file.</footer>
  <script>
    document.querySelectorAll("button[data-filter]").forEach(button => button.addEventListener("click", () => {{
      document.querySelectorAll("button[data-filter]").forEach(item => item.classList.remove("active"));
      button.classList.add("active");
      const filter = button.dataset.filter;
      document.querySelectorAll(".rule").forEach(card => card.hidden = filter !== "all" && !card.classList.contains(filter));
    }}));
  </script>
</body>
</html>"""


def render_rule_card(rule: RuleResult) -> str:
    evidence = render_evidence(rule.evidence)
    details = ""
    if rule.recommendation or evidence:
        recommendation = (
            f'<p class="recommendation"><strong>Recommended action:</strong> {escape(rule.recommendation)}</p>'
            if rule.recommendation
            else ""
        )
        details = f"<details><summary>Review context and evidence</summary><div class=\"detail-body\">{recommendation}{evidence}</div></details>"
    return f"""
<article class="rule {escape(rule.status)} severity-{escape(rule.severity)}">
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
        return ""
    fields = list(evidence[0].keys())
    head = "".join(f"<th>{escape(field)}</th>" for field in fields)
    rows = "".join(
        "<tr>" + "".join(f"<td>{escape(row.get(field, ''))}</td>" for field in fields) + "</tr>"
        for row in evidence
    )
    return f"<table><thead><tr>{head}</tr></thead><tbody>{rows}</tbody></table>"


def escape(value: Any) -> str:
    return html.escape(str(value))


def severity_rank(severity: str) -> int:
    return {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}.get(severity, 5)
