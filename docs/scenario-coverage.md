# Scenario and dataset coverage

## Current public release

This repository currently publishes one scenario:

| Public scenario | Starting state | Dataset | Evaluator | Expected Phase A route |
| --- | --- | --- | --- | --- |
| `incident-severity-triage` (legacy case 46) | Agent, labeled data, evaluator, and four varying controls are present | 120 Traigent-authored synthetic incident reports; 100 tuning / 20 holdout; four balanced difficulty strata; 12 distinct label strings with their row counts | Deterministic table lookup, declared as normalized exact match, with two supplied calibration probes; the catalog describes it and does not verify it | Explain the ready state and stop at the human's baseline approval |

Case 46 is a complete reference for the ready-components route. Its expected
`EXCELLENT / OK / proceed / no caps` opening is a case-specific contract, not a
target or promise for another project. The repository includes no captured
worker run, baseline, managed optimization, or result improvement.

The number 46 is retained as a stable numeric alias for
`incident-severity-triage`. It does not mean that 46 scenarios are public here.

## What a scenario varies

Each released scenario must make five things explicit in `scenario.json`:

1. **Starting condition** - which useful, limited, missing, invalid, or unsafe
   material the fictional customer brings.
2. **Agent state** - the selected agent path and tunable settings (`controls`
   in `scenario.json`) that can meaningfully vary.
3. **Dataset profile** - task, format, fields, size, uniqueness, splits,
   difficulty dimensions, output shape, origin, and limitations.
4. **Evaluator state** - method, path, supplied calibration material, and the
   safety boundary for any execution.
5. **Expected route and evidence scope** - what the fresh worker should do next
   and what a matching result would still not prove.

The files remain fully materialized inside each scenario. A run never assembles
selected fragments from a hidden shared dataset.

## Planned public coverage

The following rows are a release roadmap, not public test results. A family
becomes published only after a complete scenario directory, redistribution
review, strict manifest, materialized dataset checks, and case-specific
verifier contract are present in this repository.

| Planned family         | Material and dataset archetype                                                                                                                     | Behavior to exercise                                                                                                                                                               | Status                          |
| ---------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------- |
| Missing material       | Agent, dataset, expected outputs, or evaluator absent while other material remains usable                                                          | Preserve what exists; ask only for an unresolved human or domain choice; create or repair only a required dependency; otherwise disclose the limitation; re-check before paid work | Planned; not released or passed |
| Dataset integrity      | Malformed or unknown row shape, missing labels, empty or overlapping splits, duplicates, or leakage                                                | Repair invalid comparison material; do not optimize against evidence that cannot support the claim                                                                                 | Planned; not released or passed |
| Evidence strength      | Small, synthetic, undeclared, or mixed-provenance rows; model-generated answer key; small comparison sets or coarse outcome resolution             | Label a bounded demonstration honestly, request human review where required, and limit the claim                                                                                   | Planned; not released or passed |
| Evaluator quality      | A present evaluator is unvalidated, opaque, inconsistent, invalid on known cases, or timing out                                                    | Calibrate it, inspect and repair or replace it, or pause for a bounded timeout decision; do not call a slow evaluator broken                                                       | Planned; not released or passed |
| Execution safety       | Inspection identifies that the resolved evaluator path would execute candidate code or SQL, shell out with it, or submit it to an execution engine | End this guide run before candidate output executes; any containment and restart procedure is separate and human-governed                                                          | Planned; not released or passed |
| Search-space readiness | The agent has no meaningful varying tunable settings, or declared settings are not wired into requests                                             | Establish and verify real variation before requesting approval for paid search                                                                                                     | Planned; not released or passed |

In every family except execution safety, the exercised behavior is a waypoint
on the same route, not an ending: once the gap is closed and the human
approves, the run continues toward baseline, optimization, and results.

"Planned" describes a roadmap theme for public, context-isolated scenario
tests, not the guide behavior itself. A theme can require multiple cases or
subcases when its conditions lead to different actions; passing one case does
not pass the theme. The routing in the "Behavior to exercise"
column is implemented at public guide revision
[`6ec2b9c1`](https://github.com/Traigent/traigent-first-run/tree/6ec2b9c161400cd91faea9c8cdb1c4e00d21c8d9).
The guide's offline, isolated behavioral suite exercises missing, weak,
invalid, no-usable-component-anchor, and execution-safety stop contracts.
Those are code and contract tests, not public context-isolated coding-agent
scenario runs, so no
planned theme may be described as passed. The six planned rows here, plus the
published ready-reference scenario above, are a maintained coverage model, not
an exhaustive taxonomy of every project condition.

In this document, **invalid evaluator** means an evaluator that cannot make a
trustworthy comparison, for example because it does not distinguish known-good
and known-bad calibration answers. **Unsafe evaluator path** means inspection
identified a resolved path that executes or imports candidate output as code,
shells out with it, or submits it to a code or SQL engine. The current Guided
First Run supports
non-executing comparison evaluators such as classification, extraction, and
short-answer QA. An executing code/SQL path ends this guide run before candidate
output executes. Any containment and restart procedure is separate and is not
supplied by this guide.

## Dataset origin rules

Every public scenario must distinguish repository origin from in-world scorer
metadata:

- `scenario.json` records who authored the published bytes and the license that
  permits redistribution.
- A row-level value such as `provenance: real` simulates what the fictional user
  declares to the readiness scorer. It does not claim that the repository row
  came from a customer or third party.
- Third-party content must not be copied merely because a dataset name or
  provenance label appears in an earlier test. Use Traigent-authored clean-room
  material when it preserves the intended starting condition and evaluator
  behavior.

For the current release, all case-46 scenario bytes are Traigent-authored
synthetic content under Apache-2.0 and contain no customer or third-party
dataset.

## What a pass means

Coverage and evidence are separate:

| Layer             | A pass supports                                                                                        | It does not prove                                              |
| ----------------- | ------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------- |
| Catalog check     | Published files and the semantic contract are structurally valid and match declared materialized facts | Worker behavior or live value                                  |
| Phase A opening   | The captured opening fields matched the public contract in that recorded, context-isolated run         | Paid baseline or managed optimization                          |
| Phase B live path | Evidence for the explicitly approved baseline, search, and result that actually ran                    | A universal outcome, another environment, or production safety |

The onboarding goal is to route every supported starting state as far toward
optimization as its evidence and human approvals permit. Missing foundations
loop through creation or repair. Limited evidence constrains the claim. Invalid
measurement stops before paid work. Unsafe execution ends this guide run; any
containment design and restart are separately reviewed and approved outside it.
For supported non-executing paths, optimization can proceed only after the
necessary foundations are valid and the human approves the next boundary.
