# Customer PC Runbook

This runbook is for a presales engineer or customer representative reproducing
the public Phase A opening scenario on a customer-controlled computer.

It covers package validation, preparation, a context-isolated worker run, and
semantic verification. It does not authorize the later credentialed
optimization path.

## Roles

- The **customer owner** approves the machine, coding-agent service, evidence
  retention, and any later live boundaries.
- The **captain** prepares the project, gives the worker the exact handoff,
  enforces the stop point, and retains evidence.
- The **worker** is a fresh coding-agent conversation that receives only the
  prepared project and printed handoff.
- The **verifier** is the local data-only comparison performed after the worker
  returns.

One person may act as customer owner and captain, but the information boundary
between worker and verifier remains the same.

## 1. Agree on the boundary

Before touching the machine, confirm:

- the disposable directory approved for both public checkouts and run output;
- whether GitHub access and Python 3.11 through 3.13 are permitted;
- which coding-agent service may be used and what context it may receive;
- whether a container, virtual machine, or restricted account is required;
- where command output and agent transcripts may be retained;
- which directories, repositories, services, and data are out of scope; and
- who can authorize a separate Phase B exercise.

Phase A requires no Traigent access code, model-provider key, customer dataset,
paid service, or product account. The coding-agent service itself may be remote
or billed, so approve that service separately.

If local policy does not permit any required step, stop and use an approved
environment.

## 2. Create clean public checkouts

Clone into the approved disposable area, not into a production repository or a
directory containing customer data:

```bash
git clone https://github.com/Traigent/traigent-first-run-scenarios.git
git clone https://github.com/Traigent/traigent-first-run.git
cd traigent-first-run-scenarios
python --version
git rev-parse HEAD
git -C ../traigent-first-run rev-parse HEAD
```

Record both revisions. Do not copy credentials or customer files into either
checkout.

## 3. Validate the published package

```bash
python scenario.py list
python scenario.py show 46
python scenario.py check 46
python scenario.py check
```

Retain the complete output and final status of each command. Confirm the
scenario title, starting condition, component states and paths, dataset profile
and limitations, expected route, evidence scope, phase, content origin, and
license. A green catalog check confirms the declared dataset row, unique-input,
split, difficulty, per-label, and calibration counts against the published
files. It also confirms that the expected opening has valid strict structure
and value ranges. It still proves package integrity only, not agent or
evaluator behavior: nothing is imported or executed, so what the shipped
evaluator scores alike is not among the things a green check has confirmed.

If any command fails, stop. Do not repair the published scenario on the
customer machine or substitute other data.

## 4. Prepare a new run root

Choose an approved output path whose parent exists but which does not itself
exist:

```bash
python scenario.py prepare 46 \
  --guide-src ../traigent-first-run \
  --output ../incident-triage-run
```

The command requires both checkout roots to have committed Git `HEAD`
revisions. It verifies that the stage-zero index for the selected scenario
manifest, project, verifier, and the allowlisted guide paths matches those revisions,
copies the recorded blobs, and rechecks both sources before success. It then
creates:

- `../incident-triage-run/customer-project/`, containing the simulated project
  and an allowlisted local guide checkout; and
- `../incident-triage-run/run.json`, containing scenario identity, phase, exact
  handoff, both committed revisions, sorted worker-project, captain-contract,
  and guide-bundle inventories, and deterministic SHA-256 hashes.

Only tracked selected-project and allowlisted guide files are copied; untracked
and ignored files from either source are excluded. Preparation invokes local Git
read-only. It does not execute project or guide code, start a shell or worker,
or contact a network service. It refuses dirty selected inputs, existing or
symbolic-link output paths, unsafe source entries, nested source/output
relationships, and incomplete inputs.

On success, use the worker directory, captain record, and handoff printed by the
command. Do not infer or rewrite those values.

## 5. Confirm worker isolation

Before starting the worker, check all of the following:

- The worker receives `customer-project/`, not the scenario checkout.
- `run.json`, `scenario.json`, `verifier/`, `expected-opening.json`, prior
  results, and presentation material are not in its supplied context.
- The coding-agent conversation is fresh and contains no earlier discussion of
  this scenario.
- Production repositories, credentials, private datasets, and unrelated home
  directories are outside the approved scope.
- Network and tool permissions match the Phase A boundary.

For stronger machine isolation, expose only `customer-project/` to a disposable
container, virtual machine, or restricted account. Starting a worker in that
directory under the same operating-system user is useful context isolation, but
it does not prevent deliberate access to other readable files.

Because the scenario is public, this protocol is expected-result-blinded
within the supplied context, not a secret held-out benchmark. The worker gets
the project's evaluator but not the captain-side semantic verifier, expected
opening, or prior result. A worker that deliberately looks up those excluded
materials makes the run ineligible.

## 6. Run the Phase A opening

Start the fresh worker with its working directory set to
`../incident-triage-run/customer-project`. Paste only the exact handoff printed
by `prepare`:

```text
Help me run my first Traigent optimization.
Use the Traigent first-run checkout at ./traigent-first-run and follow ./traigent-first-run/GUIDE.md.
```

Do not add the case number, expected band, anticipated remedies, test framing,
or coaching.

The captain may allow local inspection and the deterministic evaluator
calibration only when the first-run guide admits the exact path through its
safety gate. During Phase A, do not:

- provide a Traigent or provider credential;
- approve a paid or remote Traigent/provider request;
- install packages without a separate approved procedure;
- expose customer data;
- change production files or services; or
- continue into a baseline or optimization.

Stop at the first question or decision that belongs to the human. Retain the
worker's response and the exact machine-readable opening object according to
the agreed evidence policy.

## 7. Verify outside the worker project

Save the exact opening readiness JSON outside `customer-project/`, then run:

```bash
python scenario.py verify 46 \
  --run-record ../incident-triage-run/run.json \
  --result /path/to/opening-result.json
```

Verification reads JSON as data, validates the contract inventory against the
scenario Git revision in `run.json`, and compares only `band`, `status`,
`recommended_action`, and `caps` with that recorded expected opening. Expected
caps are condition slugs; full captured cap objects are compared by their
`condition` fields. It reports every mismatch and does not execute the verifier.

A matching result may be labeled **Verified run evidence** only when the report
also identifies the captured result, both repository revisions, `run.json`, the
worker, environment, handoff, and stop point. Without that evidence, the public
values remain an **Expected scenario contract**.

## 8. Retain and remove evidence deliberately

Retain only what the customer approved:

- scenario and guide revisions;
- scenario slug and legacy identifier;
- `run.json`;
- environment and worker description;
- complete commands, output, and final statuses;
- exact handoff and worker response;
- opening-result JSON and verifier output; and
- explicit approvals if a later Phase B run occurs.

Remove secrets and customer data before sharing. Retain or delete the disposable
directories according to the customer's policy; do not silently leave them on
the machine.

## 9. Authorize Phase B separately

Phase B exercises a live value path. Before it begins, write down and obtain
approval for every applicable item:

| Boundary | Required decision |
| --- | --- |
| Credentials | Which account and secret may be used, and how it is supplied without entering chat or logs |
| Network | Which hosts and services may be contacted |
| Installation | Which packages or tools may modify the environment |
| Data | Which files may be read, transformed, or sent off the machine |
| Cost | Which provider or platform charges are allowed and their limit |
| Mutation | Which files, repositories, services, or records may change |
| Optimization | The candidate space, evaluation, trial, and stopping boundaries |

An approval for Phase A is not approval for Phase B. If any boundary is unclear,
stop and ask the authorized human. Report Phase B evidence separately; never use
a Phase A match as proof of a live optimization or business improvement.
