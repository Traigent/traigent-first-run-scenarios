# Freight quote estimator with a small worked-quote history

This public scenario models a numeric-estimation project at a fictional
road-freight broker, Tamsin Freight. Its agent reads a plain-English shipment
description and returns the quoted price under the broker's tariff, its
evaluator scores a quote as right or wrong within a stated tolerance, and its
dataset holds only 24 worked quotes -- the desk has few jobs it is willing to
vouch for. That last fact is the point of the scenario: every component is in
place and working, and the opening still has to say how much a comparison on
this many rows can claim.

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

- `agent.py`
- `dataset.jsonl`
- `evaluator.py`
- `requirements.txt`
- `traigent-runs/calibration-cases.json`

The catalog declares 24 unique shipment descriptions: 20 tuning and 4 holdout,
with 6 rows in each of four difficulty strata, and a numeric label shape with no
label strings to list. `scenario.py check` derives those counts from the JSONL
bytes and compares them with the manifest; it also checks that the calibration
JSON contains the declared two cases and that `requirements.txt` is named as a
record rather than task data. It does not import or execute the agent or
evaluator, and so it establishes nothing about the tolerance the evaluator
applies -- the catalog makes no claim about that.

## The agent

`project/agent.py` calls the model through LiteLLM's `completion` with
OpenRouter model ids, so one `OPENROUTER_API_KEY` reaches all three models in
`MODELS`. Four settings shape each call and every one of them is a module-level
literal table that `run(input_text, config)` reads through `config.get` and
indexes:

- `model` -- one of the three OpenRouter ids in `MODELS`.
- `prompt_style` -- `direct` (the number alone) or `worked` (show the working,
  then the number on the last line), from `PROMPT_STYLES`.
- `units_hint` -- `plain` (no symbol, no separator, no decimals) or `reminder`
  (name the units and say when to round), from `UNITS_HINTS`.
- `temperature` -- `0.0` or `0.3`, from `TEMPERATURES`, passed as
  `temperature=` on the request.

Every call sends the tariff verbatim from `TARIFF` as its first system
message, followed by the chosen style and units lines and then the shipment as
the user message, so the model is never asked to know the broker's prices; it
is asked to apply them. The reply is read for its last number, which is where
both prompt styles put the quote, and a reply with no number in it raises
rather than returning a guess.

## The tariff

The same text is in `agent.py` as `TARIFF`, and every `output` in the dataset
follows it exactly:

1. Base fee: 45 per shipment.
2. Dimensional weight in kg = length x width x height in cm, divided by 5000,
   rounded up to the next whole kilogram. Chargeable weight is the greater of
   the actual weight and the dimensional weight.
3. Weight charge: 0.90 per chargeable kilogram.
4. Distance charge: 0.35 per kilometre.
5. Subtotal = base fee + weight charge + distance charge.
6. Service class multiplier on the subtotal: standard x 1.0, express x 1.5.
7. Surcharges, applied after the class multiplier and in this order: hazardous
   goods add 20% of the class-adjusted amount; residential delivery then adds
   a flat 30.
8. Round the final figure to the nearest whole unit (halves round up). That
   whole number is the quote.

No row's exact figure lands on a half, so the tie-break clause never decides a
label. A worked example, from the first hard row: 150 x 120 x 100 cm is
1,800,000 cubic cm, which is 360 kg dimensional against 40 kg actual, so the
chargeable weight is 360; 45 + 0.90 x 360 + 0.35 x 180 = 432; standard class
and no surcharge leave it there, and the quote is 432.

## The evaluator

`project/evaluator.py` reads both the quote and the recorded price as numbers
and scores 1.0 when they differ by no more than the larger of one whole unit
and two percent of the recorded price, else 0.0. Numeric strings are accepted
on either side. A quote that is not a number scores 0.0 -- a failed quote is a
wrong quote -- while a recorded price that is not a number raises, because
grading against it would mark every prediction wrong without saying why.

The two calibration cases are binary. Their `partial` probes are quotes about
five percent out: inside a looser band, outside this one, and scored 0.0 on
purpose, because the desk would have to correct such a quote with the customer.
The case names say so.

## Difficulty rubric

Every row is graded by the tariff clauses it exercises, and the grade is
applied the same way to every row:

- `easy` -- standard service, no surcharge, and the actual weight is at least
  the dimensional weight. The price is base fee, weight and distance.
- `medium` -- still weight-based, plus exactly one of: express service, the
  hazardous surcharge, or the residential surcharge.
- `hard` -- the dimensional weight exceeds the actual weight, so the chargeable
  weight has to be computed rather than read; either service class; no
  surcharge.
- `very-hard` -- the dimensional weight exceeds the actual weight and both
  surcharges apply, so the percentage and the flat fee have to be applied in
  the stated order after the class multiplier.

Each stratum holds six rows: five tuning and one holdout.

## Reading `dataset.jsonl`

Each of the 24 lines is one JSON object with three keys - `input`, `output`,
and `metadata`. The equivalent object below is formatted across several lines
for readability; the JSONL file stores it on one physical line:

```json
{
  "input": "Foam packaging inserts, light but bulky: 40 kg, 150 x 120 x 100 cm, 180 km, standard service to a packing plant.",
  "output": 432,
  "metadata": { "difficulty": "hard", "split": "tuning", "provenance": "real" }
}
```

- `input` - the shipment description the agent quotes from. Every description
  states the weight in kg, the three dimensions in cm, the distance in km and
  the service class, and names any surcharge condition in words.
- `output` - the quoted price as a JSON number in whole currency units,
  computed from the tariff above. The catalog records the label shape as
  `numeric` with no label strings to count.
- `metadata.split` - `tuning` (20 rows) or `holdout` (4 rows). Holdout rows are
  reserved for checking a winner outside the tuning data, one per stratum.
- `metadata.difficulty` - `easy`, `medium`, `hard`, or `very-hard`, 6 rows
  each.
- `metadata.provenance` - always `real` here, and this is the one field that
  means less than it looks: it is **in-world scorer metadata** - what the
  fictional customer declares about their rows when the guide scores readiness.
  It does not describe where these repository bytes came from. Every byte in
  this scenario is Traigent-authored synthetic content (`content.origin` in
  `scenario.json`).

`scenario.py check 56` re-derives every one of these counts from the JSONL
bytes and fails if they drift from the manifest.

## Why the dataset is declared `limited`

Twenty tuning rows is a real comparison and a coarse one: a single row is five
percent of the tuning score, so a small gap between two configurations may be
chance. The data component is declared `limited` and the starting condition
`gaps-present` for that reason alone -- the rows are correct, unique, labelled
and split, and nothing in them needs repair. What the opening is expected to do
with that is the verifier's business; this README does not restate the
contract's values.

## What the published opening rests on

`verifier/expected-opening.json` is what the guide returned for this project's
bytes at the pinned revision, and two of its inputs are committed beside it under
`verifier/measurement/`: the read of the agent's settings, and the row review.

The guide withholds its top two bands until a read of the expected answers has
entered, so this scenario's band depends on that review. It covers 5 of the
24 rows -- the five the opening asks for, drawn at random with the seed the
document records -- and the guide's own card says what that means: *a sample, so
unreviewed answers are assumed sound rather than verified*.

`scripts/reproduce_openings.py` re-runs the measurement from those files and
compares the result with the contract.

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
