# Rule Authoring Reference

Rules are declarative JSON. They never execute arbitrary Python, which keeps a
shared rules library reviewable and safe.

## Rule shape

```json
{
  "id": "unique-rule-id",
  "title": "Human-readable finding",
  "description": "What this detects and why it matters.",
  "category": "Pipeline hygiene",
  "severity": "high",
  "calculation": {},
  "threshold": { "operator": "gt", "value": 0.2 },
  "format": "percent",
  "message": "{formatted_value} of records need attention.",
  "recommendation": "The action an operator should take.",
  "evidence": {}
}
```

`severity` can be `info`, `low`, `medium`, `high`, or `critical`. `format` can
be `number`, `percent`, or `currency`.

## Calculations

Count matching records:

```json
{
  "aggregate": "count",
  "object": "Contact",
  "where": { "field": "Email", "operator": "is_blank" }
}
```

Other aggregates are `sum`, `average`, `distinct_count`, and
`largest_group_share`. All except `count` require a `field`.

Build formulas with `add`, `subtract`, `multiply`, or `divide`:

```json
{
  "operator": "divide",
  "operands": [
    { "aggregate": "count", "object": "Contact", "where": { "field": "Email", "operator": "is_blank" } },
    { "aggregate": "count", "object": "Contact" }
  ]
}
```

Division by zero returns zero.

## Predicates

Field predicates support:

- `eq`, `ne`, `gt`, `gte`, `lt`, `lte`
- `is_blank`, `is_not_blank`
- `contains`, `not_contains`
- `in`, `not_in`
- `older_than_days`, `newer_than_days` for ISO-formatted Salesforce dates

Compose predicates using `all`, `any`, or `not`:

```json
{
  "all": [
    { "field": "StageName", "operator": "not_in", "value": ["Closed Won", "Closed Lost"] },
    { "field": "CloseDate", "operator": "older_than_days", "value": 90 }
  ]
}
```

## Cross-object relationships

Relationship predicates currently count records joined by a local and remote
field. This example identifies Accounts that have no Contacts:

```json
{
  "relationship": {
    "object": "Contact",
    "local_field": "Id",
    "remote_field": "AccountId",
    "aggregate": "count"
  },
  "operator": "eq",
  "value": 0
}
```

The relationship can contain its own `where` predicate. For example, count only
Contacts with a nonblank email by adding:

```json
{
  "where": { "field": "Email", "operator": "is_not_blank" }
}
```

## Evidence

Evidence uses the same object and predicate syntax and adds selected fields:

```json
{
  "object": "Contact",
  "where": { "field": "Email", "operator": "is_blank" },
  "fields": ["Id", "Name", "AccountId", "Title"],
  "limit": 8
}
```

Evidence is included only when the threshold produces a finding.

