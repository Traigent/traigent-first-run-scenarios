# Scenario and dataset coverage

## Current public release

This repository currently publishes one scenario:

| Public scenario | Starting state | Dataset | Evaluator | Expected Phase A route |
| --- | --- | --- | --- | --- |
| `incident-severity-triage` (legacy case 46) | Agent, labeled data, evaluator, and four varying controls are present | 120 Traigent-authored synthetic incident reports; 100 tuning / 20 holdout; four balanced difficulty strata; 12 surface labels mapped to four severity classes | Deterministic, non-executing normalized exact match with two supplied calibration probes | Explain the ready state and stop at the human's baseline approval |

Case 46 is a complete control for the ready-components route. Its expected
`EXCELLENT / OK / proceed / no caps` opening is a case-specific contract, not a
target or promise for another project. The repository includes no captured
worker run, baseline, managed optimization, or result improvement.

The number 46 is retained as a stable numeric alias for
`incident-severity-triage`. It does not mean that 46 scenarios are public here.

## What a scenario varies

Each released scenario must make five things explicit in `scenario.json`:

1. **Starting condition** - which useful, limited, missing, invalid, or unsafe
   material the fictional customer brings.
2. **Agent state** - the selected agent path and controls that can meaningfully
   vary.
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

| Planned family | Material and dataset archetype | Behavior to exercise | Status |
| --- | --- | --- | --- |
| Missing material | Agent, dataset, expected outputs, or evaluator absent while other material remains usable | Preserve what exists; ask once; create or repair only a dependency the selected task requires; otherwise disclose the limitation; re-check before paid work | Planned; not released or passed |
| Dataset integrity | Malformed or unknown row shape, missing labels, empty or overlapping splits, duplicates, or leakage | Repair invalid comparison material; do not optimize against evidence that cannot support the claim | Planned; not released or passed |
| Evidence strength | Small, synthetic, undeclared, or mixed-provenance rows; model-generated answer key; small comparison sets or coarse outcome resolution | Label a bounded demonstration honestly, request human review where required, and limit the claim | Planned; not released or passed |
| Ruler quality | Missing, slow, opaque, inconsistent, or invalid evaluator | Validate or repair the ruler before relying on its measurements | Planned; not released or passed |
| Execution safety and search space | Evaluator path executes candidate code/SQL, or the agent has no meaningful varying controls or has unwired settings | Stop for manual containment when execution is unsafe; otherwise establish real variation before paid search | Planned; not released or passed |

In this document, **invalid evaluator** means a ruler that cannot make a
trustworthy comparison, for example because it does not distinguish known-good
and known-bad calibration answers. **Unsafe evaluator path** means a resolved
path that executes or imports candidate output as code, shells out with it, or
submits it to a code or SQL engine. The current Guided First Run supports
non-executing comparison evaluators such as classification, extraction, and
short-answer QA; an executing code/SQL path is a stop and manual-containment
route, not another automatic onboarding branch.

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

| Layer | A pass supports | It does not prove |
| --- | --- | --- |
| Catalog check | Published files and the semantic contract are structurally valid and match declared materialized facts | Worker behavior or live value |
| Phase A opening | The captured opening fields matched the public contract in that recorded, context-isolated run | Paid baseline or managed optimization |
| Phase B live path | Evidence for the explicitly approved baseline, search, and result that actually ran | A universal outcome, another environment, or production safety |

The onboarding goal is to route every supported starting state as far toward
optimization as its evidence and human approvals permit. Missing foundations
loop through creation or repair. Limited evidence constrains the claim. Invalid
measurement stops before paid work. Unsafe execution routes to containment.
Optimization resumes only after the necessary foundations are valid and the
human approves the next boundary.
