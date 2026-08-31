# Traigent First Run Scenarios

Public, reproducible simulated-project scenarios for demonstrating how a coding
agent begins the [Traigent Guided First Run](https://github.com/Traigent/traigent-first-run)
from a realistic starting point.

The first published scenario is an optimization-ready incident-severity triage
project. It contains a synthetic agent, labeled rows, a deterministic evaluator,
and the public contract for the expected opening assessment. The repository does
not include a recorded worker run, so the current result is labeled **Expected
scenario contract**, not **Verified run evidence**.

The Guided First Run is intended to route every supported component-readiness
state toward optimization. Ready projects advance to the baseline approval;
incomplete projects create, repair, or review what is missing; invalid
measurement stops before paid work; and unsafe code/SQL execution routes to
manual containment. This is a governed path toward optimization, not a promise
that every project can optimize immediately or earn an Excellent opening.

## Published scenario catalog

The catalog currently contains one released scenario. Other starting
conditions may be described as coverage targets, but they are not published
scenarios until their complete directory and validated manifest exist here.

| Scenario | Starting condition | Components | Expected route | Evidence scope |
| --- | --- | --- | --- | --- |
| `incident-severity-triage` (46) | All required components ready | Agent, dataset, and evaluator are present; four agent controls | Proceed, because the required components are ready | Expected Phase A opening contract; no captured worker run or live optimization |

Its primary dataset is declared and checked as data rather than presentation
copy:

| Dataset | Task | Shape | Splits | Difficulty | Important limits |
| --- | --- | --- | --- | --- | --- |
| `incident-reports` | Closed-label classification | 120 unique inputs; 12 observed surface labels mapped to 4 normalized severity classes | 100 tuning / 20 holdout | 30 each: easy, medium, hard, very hard | Traigent-authored synthetic data; no customer data or observed model performance |

These facts come from the scenario's strict `scenario.json` catalog. `check`
compares its declared paths, row and unique-input counts, split and difficulty
counts, label coverage, normalized classes, and evaluator calibration count
with the materialized files. The presentation can render those facts, but it
does not own a second copy of them.

See [Scenario and dataset coverage](docs/scenario-coverage.md) for the current
public case, the explicitly not-yet-published coverage roadmap, dataset-origin
rules, and the claim supported by each test layer.

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

## Three distinct proof layers

| Layer | What happens | What a pass means |
| --- | --- | --- |
| Catalog check | `list`, `show`, and `check` inspect public files | The package and expected opening contract are structurally valid and fully materialized |
| Phase A opening | A fresh worker receives only the prepared project and exact handoff | The captured opening fields match the declared scenario contract |
| Phase B live optimization | A human separately approves credentials, services, data movement, cost, and mutations | Only the explicitly approved live path was exercised |

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

## Presales presentation

[`presentation/`](presentation/README.md) renders one validated semantic story
as a self-contained HTML file and an editable PowerPoint with speaker notes.
Both formats use the same content and evidence labels. The current deck shows
the expected scenario contract and marks the live path as not demonstrated; it
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
