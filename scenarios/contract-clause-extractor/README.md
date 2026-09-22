# Lease clause extraction with a model-written answer key

This public scenario models a structured-extraction project whose weak point is
the strength of its evidence rather than a missing part. Its agent reads four
facts out of one lease clause -- the tenant, the term in months, the notice
period in days, and the renewal type -- its dataset holds sixty clause excerpts
the fictional customer declares as real, and its evaluator scores an extraction
field by field. What the customer does not have is a reviewed answer key: they
had a model draft the expected answers and nobody has read them. Every row says
so in `metadata.output_provenance`.

The project is a customer-shaped simulation, not a customer project. Every byte
in this scenario is Traigent-authored synthetic content distributed under
Apache-2.0.

## What the scenario is for

The opening read is expected to find all three components present and usable
and still bound what a result may claim, because a score computed against an
answer key a model wrote reports agreement with that model rather than
correctness. The interesting question is whether the guide says exactly that:
names the condition, keeps the run moving, and routes the customer to a review
of the answers rather than to a rebuild of anything. The answers in the file
are, in fact, correct -- each was checked against its excerpt by hand -- so a
review would clear the hold. The scenario does not assume the guide can know
that.

## Scenario layout

The scenario is fully materialized and self-contained:

- `project/` contains the only scenario files assigned to the worker.
- `verifier/` contains the expected opening contract and captain guidance. It is
  public for reproducibility but is never copied into the worker's project.
- `scenario.json` identifies the scenario, its phase, content origin, license,
  materialized paths, starting condition, components, dataset profile,
  expected route, and evidence scope.

The worker-visible project contains exactly these files:

- `agent.py`
- `dataset.jsonl`
- `evaluator.py`
- `requirements.txt`
- `traigent-runs/calibration-cases.json`

The catalog declares 60 unique clause excerpts: 50 tuning and 10 holdout, with
15 rows in each of four difficulty strata, a structured label column, and one
record file (`requirements.txt`) under `non_dataset_files`. `scenario.py check`
derives those counts from the JSONL bytes and compares them with the manifest;
it also checks that the calibration JSON contains the declared three cases. It
does not import or execute the agent or evaluator, and so it does not establish
what the evaluator scores alike -- the catalog makes no claim about that.

## Reading `dataset.jsonl`

Each of the 60 lines is one JSON object with three keys - `input`, `output`,
and `metadata`. The equivalent object below is formatted across several lines
for readability; the JSONL file stores it on one physical line:

```json
{
  "input": "Westbrook Leasing Limited lets the shop at 22 Larkspur Row, Marrowgate, to Wexley Optical Ltd for a Term of three years ...",
  "output": {
    "tenant": "Wexley Optical Ltd",
    "term_months": 36,
    "notice_days": 90,
    "renewal": "auto"
  },
  "metadata": {
    "difficulty": "medium",
    "split": "tuning",
    "provenance": "real",
    "output_provenance": "model-generated"
  }
}
```

- `input` - a 60-150 word excerpt of the term-and-renewal clause of a
  commercial lease granted by the fictional landlord Westbrook Leasing Limited.
  Every party, street and town is invented.
- `output` - the four-field object the agent is expected to return: `tenant`
  exactly as written in the excerpt, `term_months` and `notice_days` as
  integers, and `renewal` as one of `auto` (the lease continues by itself
  unless notice is served), `manual` (a renewal happens only on request or by
  signing a new lease), or `none` (the lease simply ends). Every value is
  derivable from the excerpt alone, with years converted to months and weeks to
  days. The catalog records this column as `label_shape.kind: structured` and
  lists no label strings, because the answer is an object rather than a label.
- `metadata.split` - `tuning` (50 rows) or `holdout` (10 rows). Holdout rows
  are reserved for checking a winner outside the tuning data and are spread
  across all four strata.
- `metadata.difficulty` - `easy`, `medium`, `hard`, or `very-hard`, 15 rows
  each, graded by the rubric below.
- `metadata.provenance` - always `real` here. This is **in-world scorer
  metadata** - what the fictional customer declares about where the clauses
  came from when the guide scores readiness. It does not describe where these
  repository bytes came from.
- `metadata.output_provenance` - always `model-generated` here, and this is the
  field the scenario turns on. It is the same kind of in-world declaration: the
  customer is saying that the excerpts were collected but the expected answers
  were drafted by a model and have not been reviewed. Both fields are declared
  as `passthrough_fields` in the catalog. Neither describes the repository
  bytes; every row, question and answer, is Traigent-authored synthetic content
  (`content.origin` in `scenario.json`).

`scenario.py check 54` re-derives every one of these counts from the JSONL
bytes and fails if they drift from the manifest.

### Difficulty rubric

Each row was assigned one stratum by the hardest feature it contains:

- **easy** - the tenant, the term in months, the notice period in days and the
  renewal type are all stated plainly, in those units, with no reference and no
  exception.
- **medium** - at least one value needs a unit conversion: the term is given in
  years (or a phrase such as "a year and a half") or the notice period in weeks,
  and the answer is the converted integer. Nothing is stated by reference and
  there is no exception.
- **hard** - at least one value is stated by reference to another clause,
  schedule or the Particulars, and the excerpt quotes the referenced figure
  (for example "within the notice period in clause 4 (thirty days ...)"). A hard
  row may also carry a conversion. There is no exception.
- **very-hard** - the clause states one renewal type and then an exception that
  changes it, and the excerpt states that the exception's condition is met
  (the tenant is a Designated Anchor Tenant, the premises are Redevelopment
  Premises, the opt-out was exercised). The recorded `renewal` is the type the
  exception produces. A very-hard row may also carry a conversion or a
  reference.

The renewal types are spread roughly evenly across the file and within each
stratum, so a constant answer cannot score well on that field.

## The evaluator

`evaluator.py` reads both sides as the four-field object -- an object already,
or JSON text of one -- folds names and renewal types to lower case, reads a
number written as digits as that number, and returns the F1 of the predicted
`(field, value)` bindings against the recorded ones. Four right is 1.0, two
right is 0.5, a field left out costs recall, a field invented costs precision.
The catalog declares this as `set-f1`. A prediction that is not an object
scores 0.0; a recorded answer that is not the four-field object raises, so a
broken row cannot silently mark every prediction wrong. The three calibration
cases cover a plain clause, a notice period given in weeks, and an exception
that changes the renewal type, each with a same-answer probe in a different
key order, case and spacing.

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

The dataset's row-level `provenance: real` and `output_provenance:
model-generated` values are in-world scorer metadata. They simulate what the
scenario's user declares about the rows when readiness is assessed. They do not
describe where the repository files came from and do not claim that any row
contains real customer or third-party data, or that any model wrote any of it.

The repository-level source-of-origin contract is the one in `scenario.json`:
all scenario files and data are Traigent-authored synthetic content licensed
under Apache-2.0.
