# Warehouse text-to-SQL with a text-comparing evaluator

This public scenario models a text-to-SQL project whose only gap is the quality
of its scorer. A fictional wholesaler, Fennel & Co Wholesale, ships a small
SQLite stock database, an agent that turns a desk question into one SQLite
query, eighty labeled questions with their gold queries, and an evaluator that
grades a generated query by comparing its text with the recorded one. The
evaluator is deterministic, calibrated, and honest about what it does - and
what it does is the wrong kind of check for SQL, where two differently written
queries can return the same rows.

The project is a customer-shaped simulation, not a customer project. Every byte
in this scenario is Traigent-authored synthetic content distributed under
Apache-2.0.

## Scenario layout

The scenario is fully materialized and self-contained:

- `project/` contains the only scenario files assigned to the worker.
- `verifier/` contains the expected opening contract and captain guidance. It is
  public for reproducibility but is never copied into the worker's project.
- `scenario.json` identifies the scenario, its phase, content origin, license,
  materialized paths, starting condition, components, dataset profile,
  expected route, and evidence scope.

The worker-visible project contains exactly these files:

- `agent.py` - reads `schema.sql`, builds a prompt from its four settings,
  calls OpenRouter through LiteLLM, strips a markdown code fence from the
  reply, and returns the SQL as text. It never executes a query.
- `dataset.jsonl` - 80 questions with gold SQLite queries.
- `evaluator.py` - normalized text comparison; it never executes a query.
- `traigent-runs/calibration-cases.json` - four calibration cases.
- `warehouse.db` - the SQLite database the gold queries were written against
  (six tables, 319 rows, about 40 KB).
- `schema.sql` - the `CREATE TABLE` text for that database, one statement per
  line, as the SQLite shell prints it. The agent's "one line per table" schema
  rendering is cut from this file at import time.
- `requirements.txt` - the LiteLLM pin the agent needs.

The catalog declares 80 unique labeled questions: 66 tuning and 14 holdout,
with 20 rows in each of four difficulty strata. The labels are SQL queries, one
per question and no two alike, so the catalog records the label column as
`free-text` rather than listing them. `scenario.py check` derives the row,
split and stratum counts from the JSONL bytes and compares them with the
manifest; it also checks that the calibration JSON contains the declared four
cases. It does not import or execute the agent, the evaluator or the database,
so it establishes nothing about what the evaluator scores alike - the catalog
makes no claim about that, and the section below is where the claim lives.

## What the scenario is for

The starting condition is `gaps-present`, and the gap is the evaluator's
method, not its presence. `components.evaluator.state` is `limited` and its
`method` is `normalized-exact-match`: the scorer lower-cases keywords and
identifiers, collapses whitespace, drops a trailing semicolon and makes string
quotes uniform, then asks whether the two queries are the same string. That
folds together the ways one statement gets typed differently. It does not
fold together two statements that return the same rows - a different join
order, a table alias, a subquery in place of a join - and scores every one of
those 0.0. The dataset limitation `one-gold-query-per-question` says the same
thing from the data's side: each question records one query, and the scorer
accepts that one.

A first run that reads the project honestly should notice this: the evaluator
passes its calibration (the probes are surface variants, which is exactly what
it handles), and its declared method is still the wrong kind of check for a
`code-sql` task. The interesting question for the opening is whether the run
reports that mismatch as a limitation on what the score can mean, rather than
either treating the calibration pass as a clean bill of health or silently
replacing the customer's scorer. The scorer ships as the customer wrote it.

The agent side is deliberately unremarkable. Its four settings are module-level
literal tables consumed by `run`; three of them (`model`, `prompt_style`,
`temperature`) are written in the shape a static read can follow to the
request. The fourth, `schema_context`, selects among three renderings of
`schema.sql`, two of which are built from the file when the module loads, so
that table is not literal text and a static read records the setting without
crediting it. That is a true statement about this agent and is left as it is.

## Difficulty rubric

Each question was graded on the shape of its gold query, and the grade was
applied consistently across the file:

- `easy` - one table, one `WHERE` filter, no join and no aggregate.
- `medium` - exactly one join or one aggregate function (`COUNT`, `SUM`, `AVG`,
  `MIN`, `MAX`); a filter may ride along.
- `hard` - a join plus `GROUP BY` plus `ORDER BY` and/or `LIMIT`.
- `very-hard` - a subquery, a `HAVING` clause, or three or more tables joined.

Every gold query executes against `warehouse.db` and returns at least one row.
Where a question asks for a single top item, the data was checked so that the
answer is not tied at the cut-off.

## Reading `dataset.jsonl`

Each of the 80 lines is one JSON object with three keys - `input`, `output`,
and `metadata`. The equivalent object below is formatted across several lines
for readability; the JSONL file stores it on one physical line:

```json
{
  "input": "Which shipments are currently delayed?",
  "output": "SELECT * FROM shipments WHERE status = 'delayed';",
  "metadata": { "difficulty": "easy", "split": "tuning", "provenance": "real" }
}
```

- `input` - the question a member of the sales desk would ask.
- `output` - the gold SQLite query, written one way. The shipped
  `evaluator.py` compares a generated query with this text after
  normalizing case, whitespace, quotes and the trailing semicolon, and with
  nothing else.
- `metadata.split` - `tuning` (66 rows) or `holdout` (14 rows), with the
  holdout rows spread across the four strata. Holdout rows are reserved for
  checking a winner outside the tuning data.
- `metadata.difficulty` - `easy`, `medium`, `hard`, or `very-hard`, 20 rows
  each, graded by the rubric above.
- `metadata.provenance` - always `real` here, and this is the one field that
  means less than it looks: it is **in-world scorer metadata** - what the
  fictional customer declares about their rows when the guide scores readiness.
  It does not describe where these repository bytes came from. Every byte in
  this scenario is Traigent-authored synthetic content (`content.origin` in
  `scenario.json`).

`scenario.py check 49` re-derives every one of these counts from the JSONL
bytes and fails if they drift from the manifest.

## The database

`warehouse.db` holds six tables for a fictional wholesaler: `suppliers` (10),
`products` (40), `stock_levels` (80, one row per product per warehouse),
`shipments` (30), `orders` (45) and `order_lines` (114). Identifiers are
numbered from a per-table base (suppliers from 201, products from 2001,
shipments from 3001, orders from 4001), the way the stock system's forms print
them. Every supplier, product and customer name is invented. The database was
generated deterministically from a fixed seed by a build script kept outside
this repository; the shipped file is the artifact, and `schema.sql` is its
DDL.

## Context-isolated execution

For a recorded run, start a fresh worker with only a materialized copy of
`project/`, the selected Traigent first-run guide, and the standard
customer-visible handoff. Do not include this README, `scenario.json`, the
`verifier/` directory, expected results, or previous run evidence in the
worker's context.

This protocol provides context isolation on an honour-system basis. Because the
scenario is public, it is reproducible rather than hidden: deliberate external
lookup or prior knowledge invalidates a run but is not prevented by this
repository.

The declared scope is `phase-a-opening`. A matching result demonstrates the
published opening contract for this scenario; it does not demonstrate a live
optimization or a general performance claim.

## Content origin and row provenance

The dataset's row-level `provenance: real` values are in-world scorer metadata.
They simulate what the scenario's user declares about the rows when readiness
is assessed. They do not describe where the repository files came from and do
not claim that any row contains real customer or third-party data.

The repository-level source-of-origin contract is the one in `scenario.json`:
all scenario files and data are Traigent-authored synthetic content licensed
under Apache-2.0.
