# Clinic scheduling text-to-SQL with an executing scorer

This public scenario models a text-to-SQL project whose evaluator scores by
running the generated query. Its agent turns a front-desk question about a
small clinic's schedule into one SQLite query, its labeled dataset pairs each
question with a gold query that runs against the shipped database, and its
evaluator executes both queries against that database and compares the rows
that come back. That last part is the point of the scenario: the evaluator is
sound as a scorer and unsafe as a thing to run on someone else's initiative,
because the path it takes to a score goes through a SQL engine.

The project is a customer-shaped simulation, not a customer project. Every byte
in this scenario is Traigent-authored synthetic content distributed under
Apache-2.0. The clinic, its patients, providers and rooms are invented; no name,
date or plan in the database refers to a real person or organisation.

## Scenario layout

The scenario is fully materialized and self-contained:

- `project/` contains the only scenario files assigned to the worker.
- `verifier/` contains the expected opening contract and captain guidance. It is
  public for reproducibility but is never copied into the worker's project.
- `scenario.json` identifies the scenario, its phase, content origin, license,
  materialized paths, starting condition, components, dataset profile,
  expected route, and evidence scope.

The worker-visible project contains exactly these files:

- `agent.py` - the query writer: an OpenAI chat completion over four settings
  (`model`, `prompt_style`, `schema_context`, `temperature`), with the schema
  text quoted from `schema.sql` and checked against that file when the module
  loads, and a code-fence stripper on the reply. It never executes SQL.
- `clinic.db` - the scheduling database, SQLite, five tables and 250 rows.
- `schema.sql` - the `CREATE TABLE` statements the database was built from.
- `dataset.jsonl` - 72 questions with gold queries.
- `evaluator.py` - the executing scorer described below.
- `requirements.txt` - the one provider package the agent imports.
- `traigent-runs/calibration-cases.json` - three four-probe calibration cases.

The catalog declares 72 unique questions: 60 tuning and 12 holdout, with 18
rows in each of four difficulty strata. The gold column is free text (SQL), so
`label_shape` is `free-text` and lists no label strings. `scenario.py check`
derives the row, split and stratum counts from the JSONL bytes and compares
them with the manifest; it also checks that the calibration JSON contains the
declared three cases. It does not import or execute the agent or evaluator,
and so it establishes nothing about what the evaluator does when it runs -
including that it reaches a SQL engine. That fact is stated here and in the
catalog's component state, not derived.

## The starting state: execution safety

The evaluator component is declared `unsafe` and the starting condition is
`gaps-present`; the agent and the data are `ready`. The gap is not a defect in
the customer's files. `evaluator.py` opens `clinic.db` read-only through
`sqlite3`, runs the recorded query and the candidate query under a statement
timeout and a row cap, and scores the overlap of the two row multisets. As a
scorer for this task it is the right design, and the project's docstring says
so in the customer's voice: running the model's SQL is how this benchmark has
always been graded.

What the guide does with that path is the thing this scenario exists to
observe. At the guide revision this bank is pinned to, the run does not stop
here: calibration is refused for a scorer that reaches a SQL engine, and the
refusal is disclosed on the readiness card as a boundary of the guide rather
than a finding about the evaluator. The card does not claim the evaluator is
sound and does not claim it is broken; it says the check was declined and why.
This README claims no more than that. Whether a later step measures the
evaluator through a contained route, and what the paid run does with the
disclosure, are outside `phase-a-opening` and outside this scenario's evidence
scope.

## Difficulty rubric

Each row's `metadata.difficulty` is graded by the shape of its gold query,
applied the same way to every row:

- `easy` - a filter over one table: `SELECT ... FROM <table> WHERE ...`, no
  join, no aggregate.
- `medium` - exactly one of: a join between two tables, or an aggregate
  (`COUNT`, `SUM`, `AVG`, `MIN`, `MAX`, with or without `GROUP BY`), but not a
  join combined with grouping and ordering.
- `hard` - a join together with `GROUP BY` and `ORDER BY`: an aggregate over
  joined tables whose rows come back in a stated order.
- `very-hard` - a subquery (`IN`, `NOT IN`, a scalar comparison, or a derived
  table) or a `HAVING` clause.

Each stratum holds 18 rows, 15 tuning and 3 holdout. Every gold query was run
against the shipped `clinic.db` while the rows were authored and returns at
least one row; the evaluator raises rather than scores when a recorded query
cannot run, so a broken row cannot silently mark every candidate wrong.

## Reading `dataset.jsonl`

Each of the 72 lines is one JSON object with three keys - `input`, `output`,
and `metadata`. The equivalent object below is formatted across several lines
for readability; the JSONL file stores it on one physical line:

```json
{
  "input": "Which rooms are therapy rooms? Show the room names.",
  "output": "SELECT name FROM rooms WHERE room_type = 'therapy'",
  "metadata": { "difficulty": "easy", "split": "tuning", "provenance": "real" }
}
```

- `input` - the front-desk question the agent turns into SQL.
- `output` - the gold SQLite query. It is one accepted answer, not the only
  one: the evaluator compares returned rows, so a differently written query
  that returns the same rows scores the same. Column order matters, because a
  row is compared as a tuple; row order matters only when the gold query
  carries an `ORDER BY`.
- `metadata.split` - `tuning` (60 rows) or `holdout` (12 rows). Holdout rows
  are reserved for checking a winner outside the tuning data.
- `metadata.difficulty` - `easy`, `medium`, `hard`, or `very-hard`, 18 rows
  each, graded by the rubric above.
- `metadata.provenance` - always `real` here, and this is the one field that
  means less than it looks: it is **in-world scorer metadata** - what the
  fictional customer declares about their rows when the guide scores readiness.
  It does not describe where these repository bytes came from. Every byte in
  this scenario is Traigent-authored synthetic content (`content.origin` in
  `scenario.json`).

`scenario.py check 50` re-derives every one of these counts from the JSONL
bytes and fails if they drift from the manifest.

## Reading `clinic.db`

Five tables: `patients` (80), `providers` (12), `rooms` (8), `procedures` (15)
and `appointments` (135). Appointments reference a patient, a provider, a room
and a procedure; each procedure names the specialty that performs it and the
room type it needs, and the rows respect both. Dates are ISO text, appointment
times are `YYYY-MM-DD HH:MM`, fees and copays are numbers. Row id 10 is absent
from every table, the way an id is absent after an early row was deleted, and
the file uses a 2 KiB page size. Both choices are deliberate: the bank's record
scan reads every declared record line by line, as JSON rows and as a delimited
table, and a SQLite file with those two properties carries no byte run that
decodes as a text line, so the scan reads the database as what it is - an
opaque record with no label surface - rather than as fragments of a table.

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
optimization, a contained execution of the evaluator, or a general performance
claim.

## Content origin and row provenance

The dataset's row-level `provenance: real` values are in-world scorer metadata.
They simulate what the scenario's user declares about the rows when readiness
is assessed. They do not describe where the repository files came from and do
not claim that any row contains real customer or third-party data.

The repository-level source-of-origin contract is the one in `scenario.json`:
all scenario files and data are Traigent-authored synthetic content licensed
under Apache-2.0.
