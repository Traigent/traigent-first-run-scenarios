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
- `traigent-runs/calibration-cases.json`

The catalog declares 120 unique labeled reports: 100 tuning and 20 holdout,
with 30 rows in each of four difficulty strata. The 12 surface labels present
in the rows map to four normalized severity classes. `scenario.py check`
derives those counts from the JSONL bytes and compares them with the manifest;
it also checks that the calibration JSON contains the declared two cases. It
does not import or execute the agent or evaluator to do so.

## Reading `dataset.jsonl`

Each of the 120 lines is one JSON object with three keys - `input`, `output`,
and `metadata`:

```json
{"input": "Every checkout attempt has returned a 502 for the last eleven minutes.",
 "output": "SEV1",
 "metadata": {"difficulty": "easy", "split": "tuning", "provenance": "real"}}
```

- `input` - the incident-report text the agent classifies.
- `output` - the expected label, written as one of 12 **surface labels**
  (`SEV1`-`SEV4`, `P1`-`P4`, `Critical`, `High`, `Medium`, `Low`). Different
  fictional ticketing systems use different vocabularies; the evaluator
  normalizes them, so `SEV1`, `P1`, and `Critical` all count as the same class,
  `severity-1`. The full 12-to-4 map is `label_shape.normalization_map` in
  `scenario.json`.
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
