# Returns-desk reply drafting with no expected outputs and no evaluator

This public scenario models a project that is missing the material an
optimization needs to score anything. A fictional outdoor-gear retailer,
Pellworth Outdoor, has a working agent that drafts replies to inbound
returns-desk emails, and it has 150 of those emails logged. It has nothing
else: no reply it would call correct for any of them, no evaluator, and no
calibration record. The opening therefore has an agent with usable settings
and a dataset with inputs only, and it must say so rather than proceed.

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
- `requirements.txt`

There is no `evaluator.py` and no `traigent-runs/` directory, on purpose. The
catalog declares the evaluator `missing` with a null path, a null method and an
empty calibration record, and `scenario.py check` refuses any shipped file
under `project/` whose bytes read as Python source other than the agent, so the
gap cannot be papered over by a renamed scorer. `requirements.txt` is a record
rather than task data and is named in `non_dataset_files`.

## What the agent is

`agent.py` calls the Anthropic Messages API to draft one reply per email. Four
settings reach the request or the prompt: `model` (a tuple of two model ids),
`tone` (three instruction texts), `length` (two instruction texts), and
`temperature` (two literal values passed on the request). The returns policy is
a fixed paragraph in the file that every prompt includes, so the drafts can be
judged against a policy the reader can see. The agent returns the draft text as
written. Nothing in the project says what a good draft looks like; that is the
gap.

## Reading `dataset.jsonl`

Each of the 150 lines is one JSON object with two keys - `input` and
`metadata`. The equivalent object below is formatted across several lines for
readability; the JSONL file stores it on one physical line:

```json
{
  "input": "Hi, I ordered the Corrie down jacket in navy under order PW-418205 and it arrived last Tuesday. ...",
  "metadata": { "provenance": "real" }
}
```

- `input` - the inbound customer email the agent drafts a reply to. Every row
  is unique, between 30 and 120 words, and written in the customer's own
  voice. The emails cover the situations a returns desk meets: refund requests,
  exchanges, items that arrived damaged, returns outside the 30-day window,
  warranty claims on older gear, gifts returned by the recipient, and wrong
  sizes. Order numbers all take one shape (`PW-` and six digits) and no two
  emails share one. No email carries a postal address, an email address, a
  phone number or a real brand.
- There is **no `output`**. The customer never recorded which reply they would
  have sent, so `label_field` is null and `label_shape.kind` is `absent`.
  `scenario.py check` enforces that declaration against the bytes: under an
  absent shape any column whose values are a small repeating set of short
  strings is refused as a disguised label, so nothing in `metadata` can carry an
  answer key.
- There is **no `split`** and **no `difficulty`**. Both dimensions are declared
  with a null field and empty counts. A holdout line is something the first run
  would have to draw, and there is no difficulty rubric because there is no
  answer to grade difficulty against - a difficulty stratum is a claim about how
  hard a row is to get right, and this project has not yet said what right is.
- `metadata.provenance` - always `real` here, and this is the one field that
  means less than it looks: it is **in-world scorer metadata** - what the
  fictional customer declares about their rows when the guide scores readiness.
  It does not describe where these repository bytes came from. Every byte in
  this scenario is Traigent-authored synthetic content (`content.origin` in
  `scenario.json`). It is the only column besides `input` that a row carries,
  it is named in `passthrough_fields`, and it has one spelling across all 150
  rows, which is why the disguised-label scan does not read it as a label.

`scenario.py check 55` re-derives the row count and the unique-input count
from the JSONL bytes and fails if they drift from the manifest.

## What the opening should do

This scenario exists to exercise the route where the material is missing rather
than wrong. The agent is real and its settings can be read; the dataset is real
inputs a customer plausibly has; but with no expected outputs and no evaluator
there is nothing a configuration can be scored against, and no first run should
spend a provider call before that is fixed. The expected opening is a blocked
card whose first remedy is to produce expected replies for the rows the
customer already holds, and whose second is to connect an evaluator that can
grade a free-text draft - a rubric judge, most likely, since two correct
replies to the same email will never match string-for-string. The exact
band, status, action and caps are in `verifier/expected-opening.json`; this
README does not restate them.

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
