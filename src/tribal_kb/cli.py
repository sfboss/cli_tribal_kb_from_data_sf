from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from tribal_kb import __version__
from tribal_kb.data import DataCatalog, load_json
from tribal_kb.models import AnalysisResult, TribalKBError
from tribal_kb.report import write_html_report, write_json_report
from tribal_kb.rules import RuleEngine, utc_now_iso, validate_rules_document


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tribal-kb",
        description="Generate tribal knowledge reports from Salesforce CSV exports.",
    )
    parser.add_argument("--version", action="version", version=__version__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    analyze = subparsers.add_parser("analyze", help="Evaluate rules and generate a report.")
    add_common_arguments(analyze)
    analyze.add_argument("-o", "--output", type=Path, default=Path("reports/tribal-knowledge.html"))
    analyze.add_argument("--json-output", type=Path, help="Also write machine-readable results.")
    analyze.add_argument("--evidence-limit", type=int, default=8)
    analyze.set_defaults(handler=run_analyze)

    validate = subparsers.add_parser("validate", help="Validate configs and evaluate rules.")
    add_common_arguments(validate)
    validate.set_defaults(handler=run_validate)
    return parser


def add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--data-dir", type=Path, required=True, help="Directory containing CSV exports.")
    parser.add_argument("--objects", type=Path, required=True, help="JSON object-to-CSV mapping.")
    parser.add_argument("--rules", type=Path, required=True, help="JSON rules document.")


def run_analyze(args: argparse.Namespace) -> int:
    catalog, rules_document = load_inputs(args)
    engine = RuleEngine(catalog, evidence_limit=args.evidence_limit)
    results = engine.evaluate_all(rules_document["rules"])
    report = rules_document.get("report", {})
    analysis = AnalysisResult(
        report_title=report.get("title", "Tribal Knowledge Report"),
        report_subtitle=report.get(
            "subtitle",
            "Signals, risks, and operating knowledge inferred from Salesforce data.",
        ),
        generated_at=utc_now_iso(),
        source_summary=catalog.summary(),
        rules=results,
    )
    write_html_report(analysis, args.output)
    if args.json_output:
        write_json_report(analysis, args.json_output)
    counts = analysis.counts
    print(
        f"Wrote {args.output} "
        f"({counts['finding']} findings, {counts['pass']} passes, {counts['error']} errors)"
    )
    if args.json_output:
        print(f"Wrote {args.json_output}")
    return 1 if counts["error"] else 0


def run_validate(args: argparse.Namespace) -> int:
    catalog, rules_document = load_inputs(args)
    results = RuleEngine(catalog).evaluate_all(rules_document["rules"])
    errors = [result for result in results if result.status == "error"]
    if errors:
        for result in errors:
            print(f"ERROR {result.id}: {result.message}", file=sys.stderr)
        return 1
    print(
        f"Valid: {len(results)} rules evaluated across "
        f"{sum(catalog.summary().values())} records."
    )
    return 0


def load_inputs(args: argparse.Namespace) -> tuple[DataCatalog, dict]:
    rules_document = load_json(args.rules)
    errors = validate_rules_document(rules_document)
    if errors:
        raise TribalKBError("\n".join(errors))
    catalog = DataCatalog.load(args.objects, args.data_dir)
    return catalog, rules_document


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.handler(args))
    except TribalKBError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())

