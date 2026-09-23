# Methodology

## Purpose and current claim

Traigent First Run Scenarios provides public, customer-shaped starting points
for observing how a fresh coding agent begins the Guided First Run. The
repository separates the files needed for reproducibility from the information
withheld from the worker during an individual run.

The current release publishes thirteen scenarios, each with its expected
Phase A opening contract. Every contract was measured by running the public
guide's own preflight, calibration, and readiness scripts offline over that
scenario's project bytes at the pinned guide revision; that is a captain
measurement of the guide's scripts over the bytes, not a worker run. The
release does not include a captured, verified worker run. Its values may be
presented as **Scenario contract · no recorded run**, never as a completed
result.

## Three evidence layers

| Layer                     | Subject                              | Required evidence                                                                           | Limit                                                 |
| ------------------------- | ------------------------------------ | ------------------------------------------------------------------------------------------- | ----------------------------------------------------- |
| Catalog check             | Public package                       | Successful `list`, `show`, and `check` output                                               | No worker behavior was observed                       |
| Phase A opening           | Fresh worker in the prepared project | Complete Phase A report defined below plus successful semantic verification                 | No baseline, managed service, or optimization claim   |
| Phase B live optimization | Human-approved real value path       | Explicit approvals plus the complete credentialed run record                                | Supports only the path and outcomes actually measured |

Evidence does not flow upward automatically. A structurally valid package is
not a Phase A pass, and a Phase A match is not proof of a Phase B optimization.

## Structured released-scenario catalog

Every released scenario owns one strict `scenario.json` catalog. It records
stable facts rather than slide prose:

- the starting-condition identifier;
- agent, data, and evaluator states and local paths;
- the agent's tunable settings (`controls` in `scenario.json`) visible at the
  starting point;
- each dataset's task, format, fields, row and unique-input counts, available
  split and difficulty dimensions, output shape, and limitations;
- evaluator method and calibration-file count;
- the rationale identifier and path for the expected route; and
- what the scenario contract demonstrates and explicitly does not demonstrate.

Unavailable facts remain explicit. A missing component uses a null path, an
agent with no usable tunable settings uses an empty `controls` list, and an
unavailable split or difficulty dimension uses a null field with empty counts. Output
profiles distinguish mapped labels, unmapped labels, free text, numeric values,
structured values, and absent labels. This allows later scenarios to describe
gaps without inventing replacement data or forcing every task into a
classification shape.

The manifest does not repeat `band`, `status`, `recommended_action`, or `caps`.
Those case-specific semantics remain authoritative in the referenced verifier
contract. Presentation wording is derived from these two data sources and does
not become a parallel source of scenario facts.

`scenario.py check` verifies declared local files without importing them. For a
present JSONL dataset it strictly parses every row and compares row count,
canonical unique inputs, available split and difficulty counts, and the label
strings the rows carry with their declared per-label row counts, in both
directions. It also checks the declared evaluator calibration count against a
strict JSON array. Unsupported profile kinds and undeclared or unreadable files
fail loudly.

Because it never runs a scenario file, it establishes nothing about what the
shipped evaluator does at run time: whether it distinguishes the classes a
scenario is built around, and what a constant answer would score against it,
are properties no manifest key claims. Establishing them means executing the
evaluator under isolation, or diffing a checked-in witness produced by a real
run.

## Roles and information boundaries

Each Phase A run has four logical roles:

- The **customer owner** approves the machine, agent service, and evidence
  policy.
- The **captain (test operator)** selects the scenario, prepares the run root,
  controls the worker handoff, enforces the stop point, and retains evidence.
- The **worker** is a fresh coding-agent context that receives only the
  prepared customer project and exact handoff.
- The **verifier** performs a data-only semantic comparison after the worker
  returns.

`scenario.py prepare` creates a captain-owned run root with two parts:

```text
<run-root>/
  customer-project/   Worker-visible scenario project and allowlisted guide
  run.json            Captain-side scenario identity, handoff, and file hashes
```

The worker's supplied context excludes the source scenario checkout,
`scenario.json`, `verifier/`, expected values, `run.json`, previous transcripts,
and unrelated scenarios.

## Public scenario and expected-result-blinded run

The scenario and verifier are public so a customer can inspect, reproduce, and
challenge the contract. Public availability describes the artifact.

Context isolation describes the individual execution. The captain starts a
fresh worker with only `customer-project/` and the standard handoff. Within that
supplied context, the run is expected-result-blinded: the worker receives the
project evaluator that belongs to the starting state, but it is not given the
expected outcome, captain-side semantic verifier, or earlier result. The
handoff does not frame the project as a test or reveal its case identity.

These statements do not imply secrecy or operating-system containment. A
worker with broader file access can deliberately search for the public
verifier, and a model may have prior knowledge of a published case. Such a
lookup invalidates the run, but this protocol does not claim to prevent it. A
secret adversarial benchmark would require separately held-out material.

## Catalog and preparation safety

`list`, `show`, and `check` inspect manifests and materialized files without
importing scenario code. `check` validates the structured catalog against the
materialized data, then strictly parses the expected opening and validates its
structure and value ranges. `prepare` validates the selected scenario and local
guide checkout before copying inert bytes. It requires both
Git checkout roots to have committed `HEAD` revisions, requires each selected
stage-zero index entry to match the recorded commit tree, rejects tracked
changes in the selected scenario manifest, selected project, selected verifier,
and allowlisted guide paths, copies the recorded worker-visible blobs, and rechecks both sources before
success. It also rejects links, special or unreadable entries, an existing
output, an output nested in a source, and missing required content.

The prepared guide bundle contains its required `GUIDE.md` and
`skills/traigent-first-run/` tree, plus only the explicitly allowed tracked
top-level `README.md`, `LICENSE`, `NOTICE`, and `AGENTS.md` files that are
present.
Untracked and ignored files are excluded from both inputs. Symbolic links, Git
links, unmerged index entries, and unsupported modes are rejected. The worker
project contains no verifier.

`run.json` records:

- schema version and Phase A scope;
- scenario slug and legacy identifier;
- worker directory and exact handoff;
- both committed source revisions;
- sorted scenario-project, captain-contract, and guide-bundle file inventories; and
- file and aggregate SHA-256 hashes.

Each input has exactly `git_sha`, aggregate `sha256`, and `files`. Each sorted
file record has `path`, `sha256`, `size`, and `executable`. Executable status is
derived from the committed Git index mode, not mutable host permissions, so the
record remains stable across machines.

It deliberately records no timestamp or absolute source path. Preparation
invokes local Git read-only, but runs no scenario code, guide code, shell,
worker, or network operation. It provides a deterministic content boundary, not
a runtime sandbox.

## Phase A opening

Phase A observes the first useful readiness opening and stops at the first
question or decision that belongs to the human. It tests whether the worker can
inspect what already exists, explain the readiness state, and surface the next
governed choice without being coached toward the expected result.

The worker may use the first-run guide's static local checks. It may run the
exact deterministic evaluator calibration only after the guide's safety gate
admits that specific local path; where that gate declines the path because
the evaluator would execute candidate code or SQL, the guide records the
declined check on the readiness card and continues, and the worker calibrates
nothing on the original. This narrow allowance does not authorize
arbitrary project code, dependencies, additional project-originated remote
services, credentials, project-provider or Traigent paid calls, customer-data
egress, production mutation, a baseline, or an optimization. The separately
approved coding-agent service may itself be remote or billed and receives the
context supplied to it.

A successful semantic comparison supports only this claim:

> The four supplied opening fields matched the published semantic contract at
> the scenario revision recorded in `run.json`, and the recorded scenario
> project and contract inventories matched that revision.

It does not establish that a worker produced the result or used the recorded
guide, environment, handoff, or isolation boundary. A complete Phase A report
may make a bounded execution claim only when it also retains the worker and
session identity, environment and isolation boundary, exact handoff and worker
response, captured JSON bytes, complete commands, output and final statuses,
verifier output, both repository revisions, and stop point.

Neither the semantic match nor a complete Phase A report establishes general
coding-agent quality, readiness of another project, a live Traigent connection,
or an improvement in quality, cost, speed, or any business metric.

## Semantic verification

The captain saves the exact machine-readable opening object returned or written
by the guide outside the worker project. `scenario.py verify` validates the
project and contract inventories against the scenario Git revision recorded in
`run.json`, reads that revision's `verifier/expected-opening.json` (for
`regex-rule-authoring`, the contract for the read the worker gave, after grading
that read against the scenario's row verdicts), parses the
captured result as strict JSON, and compares four top-level fields:

- `band`
- `status`
- `recommended_action`
- `caps`

The public contract records each cap whole - its condition, its ceiling, and
whether it blocks the run or asks first - because two caps with one condition
can route a run differently. A captured readiness payload carries cap objects;
verification compares those four fields of each, order-independent, and
requires the payload's `schema_version` to be the readiness schema the contract
was measured at. A contract recorded before this (schema 1) is compared on
conditions only, and the output says so. All mismatches are reported. The
verifier never imports or executes scenario or verifier code. Display scores in
the expected contract support an honest preview of the scenario's intended
opening; they do not broaden the semantic match and are not recorded-run
evidence.

## Phase B live value path

Phase B is a separate human-guided exercise of the real value path. It begins
only after an authorized person inspects the actual environment and approves
every applicable credential, account, network, installation, data-egress,
provider, cost, mutation, and optimization boundary.

Phase A never transitions into Phase B automatically. Phase B evidence must
identify the approvals, exact configuration, data boundary, services, spend,
trials, stop condition, and measured outcome. Behavior not exercised remains
**Not demonstrated in this deck**.

## Materialization and deterministic identity

Every checked-in scenario is complete in its own directory. `project/` contains
the customer-shaped starting files. `verifier/` contains only captain-side
expectations and guidance. A run never selects fragments from a shared hidden
dataset or falls back to generated, random, downloaded, or default content.

The same checked-out scenario and guide revisions produce the same prepared
inventories and aggregate hashes. A complete Phase A report identifies both
revisions, `run.json`, the worker and session, environment and isolation
boundary, exact handoff and worker response, captured opening JSON, verifier
output, complete command output, final statuses, and stop point.

## Content origin and in-world provenance

`scenario.json` declares authorship and redistribution terms for files in this
repository. Current scenario files are Traigent-authored synthetic content
licensed under Apache-2.0.

Some simulated rows contain a `provenance` field used by the readiness scorer.
That in-world value represents what the fictional user declares about a row. A
row with `provenance: real` is still a Traigent-authored test double; it is not a
claim that the repository copied customer or third-party data.

| Contract                                        | Meaning                                              |
| ----------------------------------------------- | ---------------------------------------------------- |
| Manifest `content.origin` and `content.license` | Authorship and terms for published files             |
| In-world row `provenance`                       | Simulated user declaration used by readiness scoring |

## History-free publication

Approved content enters this repository as a curated copy of current files and
new public commits. It does not retain another repository's Git history,
branches, tags, deleted material, commit messages, `.git` data, or unrelated
context. The public repository revision and `run.json` hashes become the
reproducible identity of the published scenario.

## Presentation evidence labels

The browser presentation and editable PowerPoint use the same semantic content
and one of four labels on every slide:

- **Guide contract · no recorded run**: guide behavior pinned to an exact
  40-character public guide revision, without a referenced captured run.
- **Scenario contract · no recorded run**: published scenario facts or
  expectations, without a referenced captured run.
- **Verified run evidence**: a claim supported by the complete retained Phase A
  report described above and successful semantic verification. A run record,
  result JSON, and `PASS` alone are insufficient.
- **Not demonstrated in this deck**: a path or outcome that was not exercised.

Presentation rendering never changes verification semantics. Missing evidence
must remain visibly unverified rather than becoming an implied green result.
