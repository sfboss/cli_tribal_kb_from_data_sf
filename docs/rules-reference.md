# Rule Authoring Reference

Rules are declarative JSON. They never execute arbitrary Python.

## Rule Shape

```json
{
  "id": "unique-rule-id",
  "title": "Human-readable observation",
  "description": "The exact behavior being measured.",
  "category": "Pipeline knowledge",
  "severity": "high",
  "requires": {
    "objects": ["Opportunity"],
    "fields": { "Opportunity": ["Id", "OwnerId", "Amount"] }
  },
  "calculation": {},
  "threshold": { "operator": "gt", "value": 0.2 },
  "format": "percent",
  "message": "{formatted_value} of records match.",
  "evidence": {}
}
```

`severity` is `info`, `low`, `medium`, `high`, or `critical`. `format` is
`number`, `percent`, or `currency`. A missing `requires` input produces a
`skipped` result. An invalid rule or value produces an `error`.

Message fields are `{title}`, `{value}`, and `{formatted_value}`.

## Calculations

### Formulas

Formulas recursively combine numbers or aggregate expressions:

- `add`
- `subtract` with exactly two operands
- `multiply`
- `divide` with exactly two operands; division by zero returns zero

```json
{
  "operator": "divide",
  "operands": [
    {
      "aggregate": "count",
      "object": "Contact",
      "where": { "field": "Email", "operator": "is_blank" }
    },
    { "aggregate": "count", "object": "Contact" }
  ]
}
```

### Aggregates

| Aggregate | Required fields | Result |
|---|---|---|
| `count` | none | Matching row count |
| `distinct_count` | `field` | Nonblank distinct values |
| `sum` | `field` | Sum of nonblank numeric values |
| `average` | `field` | Average of nonblank numeric values |
| `largest_group_share` | `field` | Largest value group's row share |
| `largest_group_sum_share` | `group_by`, `field` | Largest group's share of summed numeric values |
| `duplicate_group_count` | `field` or `fields` | Number of groups meeting `minimum_size`, default 2 |
| `duplicate_row_count` | `field` or `fields` | Number of rows in groups meeting `minimum_size`, default 2 |

All aggregates accept `object` and optional `where`. Distinct/group aggregates
also accept `normalize`.

```json
{
  "aggregate": "largest_group_sum_share",
  "object": "Opportunity",
  "group_by": "OwnerId",
  "field": "Amount",
  "where": { "field": "IsWon", "operator": "is_true" }
}
```

## Normalizers

| Normalizer | Behavior |
|---|---|
| `casefold`, `lower`, `email` | Unicode-aware lowercase |
| `alphanumeric` | Lowercase and remove non-alphanumeric characters |
| `text` | Lowercase, replace punctuation with spaces, collapse whitespace |
| `company_name` | Text normalization plus removal of common trailing legal suffixes |

```json
{
  "aggregate": "duplicate_row_count",
  "object": "Account",
  "field": "Name",
  "normalize": "company_name"
}
```

## Predicates

Compose predicates with `all`, `any`, or `not`.

### Field Operators

- Comparisons: `eq`, `ne`, `gt`, `gte`, `lt`, `lte`
- Blank/boolean: `is_blank`, `is_not_blank`, `is_true`, `is_false`
- Text: `contains`, `not_contains`, `contains_any`, `contains_all`,
  `starts_with`, `ends_with`
- Sets: `in`, `not_in`, `email_domain_in`
- Pattern/length: `matches_regex`, `not_matches_regex`, `length_gt`, `length_gte`
- Dates: `older_than_days`, `newer_than_days`
- Same row: `eq_field`, `ne_field`
- Relationship root row: `eq_root_field`, `ne_root_field`

Text and set comparisons are case-insensitive by default. Add
`"case_sensitive": true` where case is part of the rule.

Date predicates use the CLI `--as-of` date.

```json
{
  "all": [
    { "field": "IsClosed", "operator": "is_false" },
    { "field": "CloseDate", "operator": "older_than_days", "value": 90 }
  ]
}
```

## Cross-Object Relationships

Relationship predicates join the current row to another object. Relationship
aggregates are `count`, `distinct_count`, and `sum`.

Accounts with no Contacts:

```json
{
  "relationship": {
    "object": "Contact",
    "local_field": "Id",
    "remote_field": "AccountId"
  },
  "operator": "eq",
  "value": 0
}
```

Accounts with at least two distinct Task owners:

```json
{
  "relationship": {
    "object": "Task",
    "local_field": "Id",
    "remote_field": "WhatId",
    "aggregate": "distinct_count",
    "field": "OwnerId"
  },
  "operator": "gte",
  "value": 2
}
```

Accounts with related Opportunities owned by someone other than the Account
owner:

```json
{
  "relationship": {
    "object": "Opportunity",
    "local_field": "Id",
    "remote_field": "AccountId",
    "where": {
      "field": "OwnerId",
      "operator": "ne_root_field",
      "value": "OwnerId"
    }
  },
  "operator": "gt",
  "value": 0
}
```

`ne_root_field` compares the related Opportunity field to the original Account
row, not to another Opportunity field.

## Thresholds

Threshold operators are `eq`, `ne`, `gt`, `gte`, `lt`, and `lte`.

The calculation is always evaluated first. If the threshold comparison is true,
the result is a `finding`; otherwise it is a `pass`.

## Evidence

Evidence uses the same object and predicate syntax:

```json
{
  "object": "Contact",
  "where": { "field": "Email", "operator": "is_blank" },
  "fields": ["Id", "Name", "AccountId", "Title"],
  "limit": 8
}
```

Evidence is included only for findings. If evidence uses the same object as a
top-level aggregate and omits `where`, the aggregate's `where` filter is
inherited automatically. The CLI `--evidence-limit` sets the maximum rows any
rule can expose.

## Optional Inputs

Use `requires` for a rule pack intended to run against exports with different
object coverage:

```json
{
  "requires": {
    "objects": ["Case", "User"],
    "fields": {
      "Case": ["OwnerId", "Subject"],
      "User": ["Id", "IsActive"]
    }
  }
}
```

Missing requirements produce a factual `skipped` result instead of an engine
error.
