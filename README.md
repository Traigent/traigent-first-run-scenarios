# Traigent First Run Scenarios

Public, reproducible simulated-project scenarios for demonstrating how a coding
agent begins the [Traigent Guided First Run](https://github.com/Traigent/traigent-first-run)
from a realistic starting point.

**How the pieces fit.** Three things carry the name Traigent here:

- [`Traigent/traigent-first-run`](https://github.com/Traigent/traigent-first-run) -
  the **guide**: the workflow a coding agent follows on a customer's own
  project, announced to the user as five stages (Inspect, Readiness, Baseline,
  Optimize, Results).
- **This repository** - simulated customer-shaped projects plus a CLI to check
  them, prepare a context-isolated copy, and compare supplied opening fields
  with a published contract at a pinned scenario revision.
- The **Traigent SDK and managed service** - the product the guide routes
  toward; licensed separately and not included here (see
  [Content origin and licensing](#content-origin-and-licensing)).

**Phase A** is the guide's opening: the coding agent inspects what exists,
explains the readiness state, and stops at the first question or decision that
belongs to the human. It needs no Traigent access code, project model-provider
credential, project-provider call, Traigent paid call, or optimization. The
approved coding-agent service may itself be remote or billed and receives the
project context supplied to it; that service is a separate customer boundary.
**Phase B** is the later human-approved live path (baseline, managed
optimization, results). Phase A never becomes Phase B automatically. Case `46`
in the commands below is a stable numeric alias for
`incident-severity-triage`, not a count of published scenarios.

The testing instructions call the human test operator the **captain**. This is
the person who prepares the isolated project, gives the coding agent its exact
handoff, enforces the stop point, and retains evidence; it is not a product
role.

The first published scenario is an optimization-ready incident-severity triage
project. It contains a synthetic agent, labeled rows, a deterministic evaluator,
and the public contract for the expected opening assessment. The repository does
not include a recorded worker run, so the current result is labeled **Scenario
contract · no recorded run**, not **Verified run evidence**.

At public guide revision
[`6ec2b9c1`](https://github.com/Traigent/traigent-first-run/tree/6ec2b9c161400cd91faea9c8cdb1c4e00d21c8d9),
the Guided First Run implements the route families summarized below: a ready
project advances to baseline approval; incomplete material is preserved,
created, repaired, or reviewed with the required human decisions; invalid
measurement stops before paid work; and, when inspection identifies an
evaluator path that would execute candidate code or SQL, this guide run ends
before that output executes. This repository tracks public, context-isolated
scenario coverage for those route families. One public test case is published
today. This is a governed path toward
optimization, not a promise that every project can optimize immediately or
earn an Excellent opening; the full claims model is in
[docs/methodology.md](docs/methodology.md).

## Published scenario catalog

The catalog currently contains one released scenario. Other starting
conditions may be described as coverage targets, but they are not published
scenarios until their complete directory and validated manifest exist here.

| Scenario                        | Starting condition            | Components                                                       | Expected route                                     | Evidence scope                                                                 |
| ------------------------------- | ----------------------------- | ---------------------------------------------------------------- | -------------------------------------------------- | ------------------------------------------------------------------------------ |
| `incident-severity-triage` (46) | All required components ready | Agent, dataset, and evaluator are present; four tunable settings | Proceed, because the required components are ready | Expected Phase A opening contract; no captured worker run or live optimization |

Its primary dataset is declared and checked as data rather than presentation
copy:

| Dataset            | Task                        | Shape                                                                                 | Splits                  | Difficulty                             | Important limits                                                                 |
| ------------------ | --------------------------- | ------------------------------------------------------------------------------------- | ----------------------- | -------------------------------------- | -------------------------------------------------------------------------------- |
| `incident-reports` | Closed-label classification | 120 unique inputs; 12 observed surface labels mapped to 4 normalized severity classes | 100 tuning / 20 holdout | 30 each: easy, medium, hard, very hard | Traigent-authored synthetic data; no customer data or observed model performance |

These facts come from the scenario's strict `scenario.json` catalog. `check`
compares its declared paths, row and unique-input counts, split and difficulty
counts, label coverage, normalized classes, and evaluator calibration count
with the materialized files. The presentation can render those facts, but it
does not own a second copy of them. Field-by-field meaning, with a sample row:
[reading the dataset](scenarios/incident-severity-triage/README.md#reading-datasetjsonl).

See [Scenario and dataset coverage](docs/scenario-coverage.md) for the current
public case, the explicitly not-yet-published coverage roadmap, dataset-origin
rules, and the claim supported by each test layer.

### Scenario families

The pinned public guide implements the route families summarized below. This
is a coverage model, not a claim that seven rows exhaust every project
condition. The rows are roadmap themes for public, context-isolated scenario
tests. A theme can require multiple cases or subcases when its conditions lead
to materially different actions; passing one case does not pass the theme. One
theme has a published reference case; the other six are planned coverage, not
test results.

| Family                 | Starting state the customer brings                                                                                                                 | What the Guided First Run does                                                                                                                                                     | Public case today                                                                      |
| ---------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------- |
| Ready reference        | Agent, labeled data, evaluator, and four varying tunable settings are all present                                                                  | Explain the ready state and stop at the human's baseline approval                                                                                                                  | `incident-severity-triage` (case 46) - expected Phase A contract only; no captured run |
| Missing material       | Agent, dataset, expected outputs, or evaluator absent while other material remains usable                                                          | Preserve what exists; ask only for an unresolved human or domain choice; create or repair only a required dependency; otherwise disclose the limitation; re-check before paid work | Planned                                                                                |
| Dataset integrity      | Malformed or unknown row shape, missing labels, empty or overlapping splits, duplicates, or leakage                                                | Repair invalid comparison material; do not optimize against evidence that cannot support the claim                                                                                 | Planned                                                                                |
| Evidence strength      | Small, synthetic, undeclared, or mixed-provenance rows; model-generated answer key; small comparison sets or coarse outcome resolution             | Label a bounded demonstration honestly, request human review where required, and limit the claim                                                                                   | Planned                                                                                |
| Evaluator quality      | A present evaluator is unvalidated, opaque, inconsistent, invalid on known cases, or timing out                                                    | Calibrate it, inspect and repair or replace it, or pause for a bounded timeout decision; do not call a slow evaluator broken                                                       | Planned                                                                                |
| Execution safety       | Inspection identifies that the resolved evaluator path would execute candidate code or SQL, shell out with it, or submit it to an execution engine | End this guide run before candidate output executes; any containment and restart procedure is separate and human-governed                                                          | Planned                                                                                |
| Search-space readiness | The agent has no meaningful varying tunable settings, or declared settings are not wired into requests                                             | Establish and verify real variation before requesting approval for paid search                                                                                                     | Planned                                                                                |

## What you can do here

```bash
git clone https://github.com/Traigent/traigent-first-run-scenarios.git
cd traigent-first-run-scenarios

python scenario.py list
python scenario.py show 46
python scenario.py check 46
python scenario.py check
```

These commands inspect and validate the published files, including the expected
opening contract. They do not launch an agent or execute scenario code.

To prepare a context-isolated Phase A opening run, first clone the public guide
beside this repository, then choose a new output path whose parent already
exists:

```bash
git clone https://github.com/Traigent/traigent-first-run ../traigent-first-run
python scenario.py prepare 46 \
  --guide-src ../traigent-first-run \
  --output ../incident-triage-run
```

`prepare` validates both Git checkouts and copies only the recorded Git blobs
for the tracked worker-visible project and allowlisted guide files into
`../incident-triage-run/customer-project/`. It requires each stage-zero index
entry to match the recorded `HEAD`, rechecks both sources before success, and
records captain-side hashes and both revisions in
`../incident-triage-run/run.json`. It invokes local Git read-only, but does not
run scenario code, guide code, a shell, a worker, or a network request.

After a fresh worker returns its machine-readable opening result, save those
exact JSON bytes outside the worker project and compare them with the public
semantic contract:

```bash
python scenario.py verify 46 \
  --run-record ../incident-triage-run/run.json \
  --result /path/to/opening-result.json
```

`verify` binds the result to the scenario contract and Git revision recorded in
`run.json`, then compares `band`, `status`, `recommended_action`, and `caps`. It
reads JSON as data and never executes verifier code. Expected `caps` are
condition slugs; when captured readiness contains full cap objects, `verify`
compares their `condition` fields and ignores display-only cap details. Follow
[GUIDE.md](GUIDE.md) for
the complete workflow and [the customer-PC runbook](docs/customer-pc-runbook.md)
before using a customer-controlled machine.

### The reproduction flow at a glance

```mermaid
flowchart TD
    A["Clone both repos side by side:<br/>traigent-first-run-scenarios + traigent-first-run"] --> B["scenario.py check 46<br/>validate catalog + expected opening contract<br/>(reads files as data; runs nothing)"]
    B --> C["scenario.py prepare 46<br/>--guide-src ../traigent-first-run --output ../incident-triage-run"]
    C --> D["customer-project/ from tracked Git blobs only,<br/>plus a generated run.json; the verifier, expected opening,<br/>and scenario manifest stay outside"]
    D --> E["One fresh coding-agent session opened in customer-project/,<br/>given only the handoff printed by prepare"]
    E --> F["The operator stops the run at the first question<br/>or decision that belongs to the human"]
    F --> G["Save the session's opening readiness JSON<br/>outside the project copy"]
    G --> H["scenario.py verify 46<br/>--run-record run.json --result opening-result.json"]
    H -->|"band, status, recommended_action, caps all match"| I["PASS - the captured Phase A opening<br/>matched the published contract"]
    H -->|"any mismatch"| J["FAIL - every mismatched field reported"]
    I -.->|"never automatic - separate human approvals"| K["Phase B: live optimization"]
```

## Three distinct proof layers

| Layer                     | What happens                                                                          | What a pass means                                                                       |
| ------------------------- | ------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------- |
| Catalog check             | `list`, `show`, and `check` inspect public files                                      | The package and expected opening contract are structurally valid and fully materialized |
| Phase A opening           | A fresh worker receives only the prepared project and exact handoff                   | The captured opening fields match the declared scenario contract                        |
| Phase B live optimization | A human separately approves credentials, services, data movement, cost, and mutations | Only the explicitly approved live path was exercised                                    |

A catalog check is not an agent run. A Phase A match is not a live optimization
or end-to-end result. Phase B is never an automatic continuation of Phase A.

## Public scenario, context-isolated run

The scenario definition and verifier are public so customers can inspect and
reproduce the test. During a documented run, the captain gives the worker only
the prepared `customer-project/` and the handoff printed by `prepare`. The
scenario manifest, verifier, expected result, captain record, and previous
results remain outside the worker's supplied context.

This makes the run expected-result-blinded within the supplied context. The
worker receives the project's evaluator because it is part of the starting
state, but it does not receive the captain-side semantic verifier, expected
opening, or prior result. It is not a secret or adversarial benchmark, and it
is not operating-system containment.
A worker that deliberately searches the public repository or unrelated machine
files invalidates the run; this repository does not claim to prevent that
behavior.

## Repository map

```text
scenario.py                         Catalog, preparation, and verification CLI
scenarios/<slug>/scenario.json      Public scenario identity and content terms
scenarios/<slug>/project/           Files copied into the worker project
scenarios/<slug>/verifier/          Captain-side expected opening contract
schema/scenario.schema.json         Scenario manifest schema
docs/customer-pc-runbook.md         Customer-machine operating procedure
docs/methodology.md                 Claims, isolation, and evidence model
skills/traigent-first-run-scenarios Bundled agent skill for this repository
presentation/                       Shared browser and PowerPoint presentation
```

Each scenario is fully materialized. A run never assembles fragments from a
hidden shared dataset. This keeps each published starting point independently
reviewable, resettable, and reproducible.

## Customer presentation

[`presentation/`](presentation/README.md) renders one validated semantic story
as a self-contained HTML file and an editable PowerPoint with speaker notes.
Both formats use the same content and evidence labels. The current deck shows
which claims come from the pinned public guide and which come from the
published scenario contract; both are marked as having no recorded run. It
does not present a simulated result as a recorded run.

```bash
cd presentation
npm ci
npm run check
```

## Try Traigent on your own project

The public scenario workflow is for a reproducible demonstration. For a real
project, open your coding agent in that project and give it exactly:

```text
Help me run my first Traigent optimization.
Clone https://github.com/Traigent/traigent-first-run and follow GUIDE.md.
```

The guide asks the human to confirm decisions and approvals that should not be
made automatically.

## Content origin and licensing

`scenario.json` records the structured scenario catalog plus the origin and
license of the files published here.
That is distinct from a row-level `provenance` value inside the simulated
project. For example, `provenance: real` models what a fictional user declares
to the readiness scorer; it does not claim that the row came from a real
customer or third-party dataset.

Everything in this repository, including scenario data, documentation, and
supporting tools, is licensed under the [Apache License 2.0](LICENSE). See
[CONTRIBUTING.md](CONTRIBUTING.md) before proposing content and
[SECURITY.md](SECURITY.md) for private vulnerability reporting.

The `traigent` SDK is offered separately under
[AGPL-3.0-only](https://github.com/Traigent/Traigent/blob/main/LICENSE) or a
[Traigent commercial license](https://github.com/Traigent/Traigent/blob/main/COMMERCIAL-LICENSE.md)
under a separate written agreement. Nothing in this repository includes,
licenses, or grants rights to the SDK.
