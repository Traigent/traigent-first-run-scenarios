# Guide

Use this guide to inspect a public scenario or captain one reproducible Phase A
opening run. It does not authorize a credentialed optimization.

In this guide, **captain** means the human test operator who prepares the run,
controls the worker handoff and stop point, and retains evidence.

The repository releases thirteen scenarios, each with its expected opening
contract, as reviewed, versioned files — not recorded worker results. Until a
fresh run is captured and verified, describe an opening as **expected**, not
**verified**. Every step below works the same way for any scenario
`scenario.py list` shows; case `46` is the one the commands show, and an
output path is named after the scenario you run.

## 1. Create two clean checkouts

Use a disposable directory outside any customer production repository, and
outside any workspace an existing coding-agent session already has as context
— the worker must later open the prepared copy with none of these
repositories in its supplied context. The scenario workflow supports Python 3.11 through 3.13. The selected first-run
guide must be a local checkout so the run can identify exactly which guide
bytes were used.

```bash
git clone https://github.com/Traigent/traigent-first-run-scenarios.git
git clone https://github.com/Traigent/traigent-first-run.git
cd traigent-first-run-scenarios
```

Record both revisions before the run:

```bash
git rev-parse HEAD
git -C ../traigent-first-run rev-parse HEAD
```

Do not add credentials or customer data to either checkout.

## 2. Inspect and check the catalog

```bash
python scenario.py list
python scenario.py show 46
python scenario.py check 46
python scenario.py check
```

`list` discovers the released scenarios. `show` prints one validated manifest,
including its starting condition, component states, dataset profiles, expected
route, limitations, and evidence scope. `check CASE` validates those declared
facts against the materialized paths and data, then validates the strict
structure and ranges of its expected opening contract. `check` applies the same
validation to the entire catalog. These commands inspect files as data only.
They do not execute scenario or verifier code.

If a command fails, stop and report its complete output. Do not download,
generate, or substitute missing scenario data.

## 3. Prepare an isolated worker project

Choose a new output path whose parent exists but which does not itself exist:

```bash
python scenario.py prepare 46 \
  --guide-src ../traigent-first-run \
  --output ../incident-triage-run
```

`prepare` requires both this scenario repository and the guide source to be Git
checkout roots with committed `HEAD` revisions. It requires the stage-zero
index for every selected path to match that recorded commit, rejects tracked
changes in the selected scenario manifest, selected project, and allowlisted
guide paths, and rechecks both sources before success. It also rejects symbolic
links and non-regular input, and excludes untracked and ignored source files. It
then creates:

```text
incident-triage-run/
  customer-project/              Assigned to the worker
    agent.py
    dataset.jsonl
    evaluator.py
    traigent-runs/
    traigent-first-run/          Allowlisted guide files
  run.json                       Captain-side identity and content hashes
```

Only recorded Git blobs for tracked selected-project and allowlisted guide files
are copied. The allowlisted guide root includes `GUIDE.md`, `README.md`,
`LICENSE`, `NOTICE`, and `AGENTS.md` when tracked, plus the required first-run
skill tree. The worker project does not contain the scenario manifest, public
verifier, expected opening, previous results, or unrelated scenarios. `run.json`
records the scenario identity, phase, exact handoff, both committed revisions,
and deterministic inventories and content hashes for the worker project,
captain-only contract, and guide bundle. It contains no timestamp or absolute
source path.

Preparation copies inert bytes and invokes local Git read-only. It does not run
scenario code, guide code, a shell, a worker, or a network request. It also does
not create an operating system sandbox. Use the isolation required by the
customer-PC runbook.

On success, the command prints the prepared scenario, worker directory, captain
record, and fresh-agent handoff. Use those printed paths rather than inferring a
different layout.

## 4. Start one fresh worker

Start a new coding-agent conversation with its working directory set to:

```text
../incident-triage-run/customer-project
```

Give it only the handoff printed by `prepare`, unchanged:

```text
Help me run my first Traigent optimization.
Use the Traigent first-run checkout at ./traigent-first-run and follow ./traigent-first-run/GUIDE.md.
```

Do not mention the case number, expected band, verifier, grading contract, or
previous attempts. Do not place this repository or `run.json` in the worker's
supplied context.

The worker is not told this is a scenario run; only the captain knows the
case identity. The worker is deliberately
blinded so that it behaves like a real customer's coding agent: give it
nothing beyond the prepared project and the printed handoff, and its opening
reflects what a fresh agent would actually do.

The captain observes the run and stops it at the first question or decision
that belongs to the human. Where the guide declines to calibrate an
evaluator whose path would execute candidate code or SQL, it discloses the
declined check on the readiness card and continues; that disclosure is part
of the opening, not a stop. For this Phase A opening:

- do not provide a Traigent or model-provider credential;
- do not approve a paid or remote Traigent or model-provider call;
- do not send customer data or permit production mutation;
- do not install software unless a separate authorized procedure permits it;
- allow only local inspection and the exact deterministic evaluator calibration
  admitted by the first-run guide's safety gate; and
- do not continue into a baseline or optimization merely because the next step
  is available.

The coding-agent service itself may be remote. Obtain the customer's approval
for that service and limit the context it receives.

## 5. Capture and verify the opening

Retain the worker response according to the customer's evidence policy. When
the guide writes or returns its machine-readable opening readiness object, keep
the exact JSON file outside the worker project and run:

```bash
python scenario.py verify 46 \
  --run-record ../incident-triage-run/run.json \
  --result /path/to/opening-result.json
```

`verify` reads strict JSON, loads the contract from the scenario Git revision
recorded in `run.json`, and compares these top-level semantic fields:

- `band`
- `status`
- `recommended_action`
- `caps`

One scenario, `regex-rule-authoring` (58), publishes two contracts because its
opening turns on what the worker's read of its answers found. For it, also pass
the row review the worker gave readiness as `--row-review FILE`: `verify` grades
that read against the scenario's verdict for every row, then compares the
result with the contract for the read the worker gave. `--row-review` is
refused for every other scenario.

Expected `caps` are condition slugs. When captured readiness contains full cap
objects, verification compares their `condition` fields and ignores
display-only cap details. It reports every mismatch and never imports or
executes verifier code. A match supports only this statement:

> The four supplied opening fields matched the published Phase A contract at
> the scenario revision recorded in `run.json`, and the recorded scenario
> project and contract inventories matched that revision.

It does not establish that a worker produced the result, that the recorded
guide or isolation conditions were used, that a baseline or optimization ran,
that quality or cost improved, or that another project will receive the same
result.

A successful comparison prints `PASS` and names the four matched fields. A
failure prints `FAIL` and every mismatched field; retain the full result rather
than summarizing only the exit status.

## 6. Report the evidence boundary

Record:

- scenario slug and legacy identifier;
- scenario-repository and guide revisions;
- prepared `run.json`;
- worker, session, environment, and isolation-boundary description;
- exact handoff and worker response;
- the verified JSON bytes;
- complete command output and exit statuses, including verifier output; and
- the stop point.

Use one of the presentation evidence labels consistently:

- **Guide contract · no recorded run** for behavior pinned to an exact public
  guide revision, without a referenced captured run;
- **Scenario contract · no recorded run** for published scenario facts or
  expectations, without a referenced captured run;
- **Verified run evidence** only when every Phase A report item above is
  retained and referenced, and semantic verification passed; or
- **Not demonstrated in this deck** for any later behavior or outcome that was
  not exercised.

A run record, result JSON, and `PASS` alone are insufficient. Without the
complete retained report, keep the public result at **Scenario contract · no
recorded run**.

## 7. Keep Phase B separate

Phase B is a later human-guided run of the live value path. It begins only after
an authorized person reviews and explicitly approves every applicable
credential, network, installation, data-egress, cost, mutation, and
optimization boundary. Phase A never transitions to Phase B automatically.

Use [docs/customer-pc-runbook.md](docs/customer-pc-runbook.md) for the operating
checklist and [docs/methodology.md](docs/methodology.md) for the claims model.

## Run Traigent on a real project

The prepared handoff above refers to a guide already copied into the simulated
project. On a real customer project, open the coding agent in that project and
give it exactly:

```text
Help me run my first Traigent optimization.
Clone https://github.com/Traigent/traigent-first-run and follow GUIDE.md.
```

That real-project journey is not a scenario verification run. The human should
review the guide's decisions and approval gates in the actual environment.
