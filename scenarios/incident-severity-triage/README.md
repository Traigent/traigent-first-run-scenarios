# Optimization-ready incident severity triage

This public scenario models a well-prepared incident-triage project. Its agent
classifies inbound reports into four severity levels, its labeled dataset covers
a range of incident difficulty, and its evaluator normalizes equivalent labels
used by different ticketing systems.

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

The catalog declares 120 unique labeled reports: 100 tuning and 20 holdout,
with 30 rows in each of four difficulty strata, and it lists the 12 distinct
label strings the rows carry with the number of rows carrying each.
`scenario.py check` derives those counts from the JSONL bytes and compares them
with the manifest; it also checks that the calibration JSON contains the
declared two cases. It does not import or execute the agent or evaluator to do
so, and so it does not establish which of those 12 spellings the evaluator
scores alike -- the catalog makes no claim about that.

## Reading `dataset.jsonl`

Each of the 120 lines is one JSON object with three keys - `input`, `output`,
and `metadata`. The equivalent object below is formatted across several lines
for readability; the JSONL file stores it on one physical line:

```json
{
  "input": "Every checkout attempt has returned a 502 for the last eleven minutes.",
  "output": "SEV1",
  "metadata": { "difficulty": "easy", "split": "tuning", "provenance": "real" }
}
```

- `input` - the incident-report text the agent classifies.
- `output` - the expected label, written as one of 12 **surface labels**
  (`SEV1`-`SEV4`, `P1`-`P4`, `Critical`, `High`, `Medium`, `Low`). Different
  fictional ticketing systems use different vocabularies. The shipped
  `evaluator.py` normalizes them before comparing, so `SEV1`, `P1`, and
  `Critical` all count as the same class -- that is a statement about what that
  file does when it runs, and you can read its table directly. The catalog does
  not restate it: `check` never imports or executes a scenario file, so it
  cannot establish what an evaluator distinguishes, and a claim it cannot check
  is one it does not make. What the catalog does record, and verify against the
  shipped rows, is `label_shape.label_counts` -- every distinct label string
  with the number of rows carrying it.
- `metadata.split` - `tuning` (100 rows) or `holdout` (20 rows). Holdout rows
  are reserved for checking a winner outside the tuning data.
- `metadata.difficulty` - `easy`, `medium`, `hard`, or `very-hard`, 30 rows
  each.
- `metadata.provenance` - always `real` here, and this is the one field that
  means less than it looks: it is **in-world scorer metadata** - what the
  fictional customer declares about their rows when the guide scores readiness.
  It does not describe where these repository bytes came from. Every byte in
  this scenario is Traigent-authored synthetic content (`content.origin` in
  `scenario.json`).

`scenario.py check 46` re-derives every one of these counts from the JSONL
bytes and fails if they drift from the manifest.

## What the published opening rests on

`verifier/expected-opening.json` is what the guide returned for this project's
bytes at the pinned revision, and two of its inputs are committed beside it under
`verifier/measurement/`: the read of the agent's settings, and the row review.

The guide withholds its top two bands until a read of the expected answers has
entered, so this scenario's band depends on that review. It covers 5 of the
120 rows -- the five the opening asks for, drawn at random with the seed the
document records -- and the guide's own card says what that means: *a sample, so
unreviewed answers are assumed sound rather than verified*.

One of the five is recorded `unsure` rather than `yes`: line 52 labels a checklist
showing a step as done when it is not, at the bottom severity. An `unsure` is never
scored, so it does not bound this contract -- but a `no` there would have, and the
reader should know the undecided row exists rather than meet an uncapped
`EXCELLENT` with no sign of it.

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
