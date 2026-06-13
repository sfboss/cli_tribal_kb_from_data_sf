# Tribal KB

`tribal-kb` is a Python CLI that ingests Salesforce CSV exports, evaluates a
reviewable library of declarative rules, and produces an elegant, self-contained
HTML tribal knowledge report.

The scaffold is intentionally dependency-light:

- Standard-library CSV ingestion
- JSON object mappings and rules
- Multi-object relationship checks, such as `Account.Id -> Contact.AccountId`
- Aggregate formulas and nested predicates without unsafe `eval`
- Shareable HTML report plus optional machine-readable JSON
- Validation command and an end-to-end sample

## Quick start

Requires Python 3.10 or newer.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .

tribal-kb validate \
  --data-dir examples/data \
  --objects examples/objects.json \
  --rules examples/rules.json

tribal-kb analyze \
  --data-dir examples/data \
  --objects examples/objects.json \
  --rules examples/rules.json \
  --output reports/sample-report.html \
  --json-output reports/sample-report.json
```

Open `reports/sample-report.html` in any browser. The file contains its own CSS
and JavaScript, so it can be shared without a server.

Without installing the package, prepend commands with `PYTHONPATH=src python -m
tribal_kb`.

## Configuration

`objects.json` maps logical Salesforce object names to CSV files:

```json
{
  "objects": {
    "Account": { "file": "accounts.csv", "primary_key": "Id" },
    "Contact": { "file": "contacts.csv", "primary_key": "Id" }
  }
}
```

The rules document contains report metadata and a list of rules. This example
calculates the ratio of Contacts without email addresses:

```json
{
  "id": "contact-email-coverage",
  "title": "Contact email coverage is weak",
  "severity": "high",
  "calculation": {
    "operator": "divide",
    "operands": [
      {
        "aggregate": "count",
        "object": "Contact",
        "where": { "field": "Email", "operator": "is_blank" }
      },
      { "aggregate": "count", "object": "Contact" }
    ]
  },
  "threshold": { "operator": "gt", "value": 0.2 },
  "format": "percent",
  "message": "{formatted_value} of contacts have no email address."
}
```

See [docs/rules-reference.md](docs/rules-reference.md) for the full rule syntax
and [examples/rules.json](examples/rules.json) for practical examples.

## Project structure

```text
src/tribal_kb/       CLI, ingestion, rules engine, and report renderer
examples/data/       Small representative Salesforce CSV exports
examples/rules.json  Example same-object and cross-object rules
docs/                Rule-authoring reference
tests/               Standard-library unittest suite
```

## Tests

```bash
PYTHONPATH=src python -m unittest discover -v
```

## Intended next extensions

The current expression tree gives an existing rules list a stable format to
conform to. Likely next additions are named/reusable predicates, richer
relationship aggregates such as related sums, schema/type declarations, and
direct Salesforce extraction. These can be added without changing the CLI or
report result model.
