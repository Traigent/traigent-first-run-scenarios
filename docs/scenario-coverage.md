# Scenario and dataset coverage

## Current public release

This repository publishes thirteen scenarios, legacy cases 46 through 58. Every
expected opening below is the contract in that scenario's
`verifier/expected-opening.json`: the four fields `verify` compares, as
measured by running the public guide's own preflight, calibration, and
readiness scripts offline over the scenario's project bytes at guide revision
[`d07b62cd`](https://github.com/Traigent/traigent-first-run/tree/d07b62cd4abb6ecb6d2edcdcb2d535f02bb2c199)
(readiness `schema_version` 6). That is a captain measurement of the guide's
scripts over the bytes, not a worker run. Each is a case-specific contract,
not a target or promise for another project. The repository includes no
captured worker run, baseline, managed optimization, or result improvement.

| Public scenario | Family | Starting state | Dataset | Evaluator | Expected Phase A opening |
| --- | --- | --- | --- | --- | --- |
| `incident-severity-triage` (46) | Ready reference | Agent, labeled data, evaluator, and four varying controls are present | 120 synthetic incident reports; 100 tuning / 20 holdout; four balanced difficulty strata; 12 distinct label strings with their row counts | Deterministic table lookup, declared as normalized exact match, with two supplied calibration cases | `EXCELLENT` / `OK` / `proceed` / no caps |
| `helpdesk-queue-router` (47) | Ready reference | Agent, labeled data, evaluator, and four varying controls are present | 96 synthetic support tickets across six queues; 80 / 16; four balanced strata; 18 distinct label strings (three ticketing tools' spellings) | Deterministic queue lookup that folds the three tools' spellings together, declared as normalized exact match, with three calibration cases | `EXCELLENT` / `OK` / `proceed` / no caps |
| `policy-handbook-rag` (48) | Ready reference | Agent, labeled data, evaluator, and four varying controls are present; a 20-document synthetic handbook ships as records | 90 synthetic short-answer questions; 75 / 15; four near-balanced strata; 69 distinct answer strings, counted but not listed | Deterministic normalized match with per-question accepted aliases, with three calibration cases | `EXCELLENT` / `OK` / `proceed` / no caps |
| `warehouse-text-to-sql` (49) | Evaluator quality | Agent and data ready; the evaluator is declared `limited` because it compares SQL as normalized text, the wrong kind of check for a task where different queries return the same rows | 80 synthetic stock questions with one gold SQLite query each; 66 / 14; four balanced strata; free text | Deterministic normalized text comparison of two queries, with four calibration cases; a shipped SQLite database and its schema are records | `EXCELLENT` / `OK` / `proceed` / no caps; the task-fit mismatch is a finding on the card, which `verify` does not compare |
| `clinic-scheduling-sql-exec` (50) | Execution safety | Agent and data ready; the evaluator is declared `unsafe` because it scores by executing the generated query against the shipped database | 72 synthetic scheduling questions with one gold SQLite query each; 60 / 12; four balanced strata; free text | Executes both queries against the shipped database and compares the returned rows; declared method `execution`, with three calibration cases the guide declines to run on the original | `WORKABLE` / `OK` / `confirm-evaluator-connection` / `evaluator-calibration-refused` |
| `booking-assistant-next-action` (51) | Dataset integrity | Agent and evaluator ready; the data is declared `needs-repair` because six tuning transcripts appear a second time, byte for byte, as holdout rows | 100 rows over 94 unique synthetic chat transcripts; 83 / 17 as written; four balanced strata; 8 distinct action labels | Deterministic action-name comparison, declared as normalized exact match, with two calibration cases | `PARTIAL` / `BLOCKED` / `resplit-dataset` / `dataset-tune-holdout-overlap`, `dataset-repeated-rows` |
| `tool-dispatch-selector` (52) | Search-space readiness | Data and evaluator ready; the agent is declared `limited` with an empty control list because one model and one fixed instruction are all it sends | 90 synthetic spoken requests mapped to one of seven tool calls; 75 / 15; four near-balanced strata; structured | Deterministic tool-call comparison, declared as normalized exact match, with two calibration cases | `PARTIAL` / `BLOCKED` / `vary-knobs` / `agent-no-varying-knobs` |
| `meeting-notes-summarizer` (53) | Evaluator quality | Agent and data ready; the evaluator is declared `needs-repair` because every score is delegated to a package that is not in the project and cannot be installed | 40 synthetic meeting transcripts with one reference summary each; 34 / 6; four balanced strata; free text | Declared `llm-judge-rubric` from its docstring; no calibration record ships because none could be produced | `PARTIAL` / `BLOCKED` / `repair-evaluator` / `evaluator-unresolved` |
| `contract-clause-extractor` (54) | Evidence strength | Agent and evaluator ready; the data is declared `limited` because its expected answers were drafted by a model and never reviewed | 60 synthetic lease-clause excerpts with four-field expected extractions; 50 / 10; four balanced strata; structured | Deterministic field-level set-F1, with three calibration cases | `WORKABLE` / `OK` / `review-answer-key` / `dataset-generated-answer-key` |
| `returns-email-replies` (55) | Missing material | Agent ready; the data is declared `limited` because it holds inputs only, and the evaluator is declared `missing` | 150 synthetic inbound emails with no expected reply, no split, and no difficulty strata; label shape `absent` | None ships; no calibration record | `PARTIAL` / `BLOCKED` / `label-data` / `dataset-no-expected-outputs`, `evaluator-absent` |
| `freight-quote-estimator` (56) | Evidence strength | Agent and evaluator ready; the data is declared `limited` because 20 tuning rows make a coarse comparison | 24 synthetic worked quotes; 20 / 4; four balanced strata of six; numeric | Deterministic numeric tolerance, with two calibration cases | `STRONG` / `OK` / `add-examples` / `dataset-coarse-resolution` |
| `chatbot-on-vendor-flow` (57) | Missing material | Data and evaluator ready; the agent is declared `missing` because routing runs on a hosted vendor flow that nothing in the project can call; a flow export and a project note ship as records | 90 synthetic first messages; 75 / 15; four near-balanced strata; 6 distinct intent labels | Deterministic intent comparison, declared as normalized exact match, with two calibration cases | `NOT READY` / `BLOCKED` / `connect-agent` / `agent-absent` |
| `regex-rule-authoring` (58) | Dataset integrity | Agent and evaluator ready; the data is declared `limited` because three of its thirty-two answers do not answer their own question, and the published read of five found one of them | 32 synthetic redaction-rule descriptions with one hand-written regular expression each; 24 / 8; four balanced strata of eight; free text | Deterministic normalized text comparison that never compiles either side, with three calibration cases | `WORKABLE` / `OK` / `review-answer-key` / `dataset-unsound-expected-outputs`, `dataset-coarse-resolution`; for a read that finds every answer sound, `STRONG` / `OK` / `proceed` / `dataset-coarse-resolution` |

Splits read tuning / holdout. Every dataset is Traigent-authored synthetic
content; the catalog describes each evaluator and does not verify it. The
legacy numbers are stable aliases for the slugs; they are not a count of
public scenarios.

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

## Coverage by family

The families below are the coverage model this bank is organized around. A
family is released when at least one complete scenario directory,
redistribution review, strict manifest, materialized dataset checks, and
case-specific verifier contract for it are present in this repository. Every
family now has at least one released scenario. A released scenario is an
expected Phase A contract; it is not a test result, and no scenario here is
described as passed.

| Family                 | Material and dataset archetype                                                                                                                     | Behavior to exercise                                                                                                                                                                                                       | Released scenarios                                                                        |
| ---------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| Ready reference        | Agent, labeled data, evaluator, and varying tunable settings are all present                                                                       | Explain the ready state and stop at the human's baseline approval                                                                                                                                                          | `incident-severity-triage` (46), `helpdesk-queue-router` (47), `policy-handbook-rag` (48) |
| Missing material       | Agent, dataset, expected outputs, or evaluator absent while other material remains usable                                                          | Preserve what exists; ask only for an unresolved human or domain choice; create or repair only a required dependency; otherwise disclose the limitation; re-check before paid work                                         | `returns-email-replies` (55), `chatbot-on-vendor-flow` (57)                               |
| Dataset integrity      | Malformed or unknown row shape, missing labels, empty or overlapping splits, duplicates, or leakage                                                | Repair invalid comparison material; do not optimize against evidence that cannot support the claim                                                                                                                         | `booking-assistant-next-action` (51), `regex-rule-authoring` (58)          |
| Evidence strength      | Small, synthetic, undeclared, or mixed-provenance rows; model-generated answer key; small comparison sets or coarse outcome resolution             | Label a bounded demonstration honestly, request human review where required, and limit the claim                                                                                                                           | `contract-clause-extractor` (54), `freight-quote-estimator` (56)                          |
| Evaluator quality      | A present evaluator is unvalidated, opaque, inconsistent, invalid on known cases, timing out, or the wrong kind of check for the task              | Calibrate it, inspect and repair or replace it, or pause for a bounded timeout decision; do not call a slow evaluator broken                                                                                               | `warehouse-text-to-sql` (49), `meeting-notes-summarizer` (53)                             |
| Execution safety       | Inspection identifies that the resolved evaluator path would execute candidate code or SQL, shell out with it, or submit it to an execution engine | Decline to calibrate the customer's original evaluator, record a containment warning, disclose the declined check on the readiness card, and continue; the guide's copied-actor route may calibrate a copy against a bounded target | `clinic-scheduling-sql-exec` (50)                                                         |
| Search-space readiness | The agent has no meaningful varying tunable settings, or declared settings are not wired into requests                                             | Establish and verify real variation before requesting approval for paid search                                                                                                                                             | `tool-dispatch-selector` (52)                                                             |

In every family, the exercised behavior is a waypoint on the same route, not
an ending: once the gap is closed and the human approves, the run continues
toward baseline, optimization, and results.

A family describes a theme for public, context-isolated scenario tests, not
the guide behavior itself. A theme can require multiple cases or subcases when
its conditions lead to different actions; a contract for one case is not a
contract for the theme, and two scenarios in one family exercise two
conditions, not the family twice. The routing in the "Behavior to exercise"
column is implemented at public guide revision
[`d07b62cd`](https://github.com/Traigent/traigent-first-run/tree/d07b62cd4abb6ecb6d2edcdcb2d535f02bb2c199).
The guide's own offline, isolated behavioral suite exercises missing, weak,
invalid, and no-usable-component-anchor contracts, and its unit tests cover
the execution-evaluator refusal. Those are code and contract tests, not public
context-isolated coding-agent scenario runs, so no family may be described as
passed on their account. The seven rows here are a maintained coverage model,
not an exhaustive taxonomy of every project condition.

In this document, **invalid evaluator** means an evaluator that cannot make a
trustworthy comparison, for example because it does not distinguish known-good
and known-bad calibration answers. **Unsafe evaluator path** means inspection
identified a resolved path that executes or imports candidate output as code,
shells out with it, or submits it to a code or SQL engine. The current Guided
First Run supports non-executing comparison evaluators such as classification,
extraction, and short-answer QA. For an executing code/SQL path it declines to
calibrate the customer's original evaluator on its own initiative, records a
containment warning, and discloses the declined check on the readiness card
as `evaluator-calibration-refused`, a cap that does not block; the run
continues on that disclosure. The guide's copied-actor route may calibrate a
copy of the evaluator against a bounded copy of its target. Any further
containment design and review is separate and is not supplied by the guide.

## What the published contracts assume

Each `verifier/expected-opening.json` is what the guide's own scripts returned for
that project's bytes at `d07b62cd`, measured by a captain rather than produced by a
worker run. Two inputs shape it that the project files do not contain, and both are
part of the opening the guide asks a worker to perform:

- **The agent read.** The guide is given a statement of the agent's settings
  (`--agent-knobs`). Without one the agent pillar reads 0 and every contract here is
  wrong -- a reproduction that omits it gets `NOT READY` / `connect-agent` on a ready
  project.
- **The row review.** `readiness.py` withholds STRONG and EXCELLENT until a read of
  the expected answers has entered (`--row-review`); `SKILL.md` lists writing that
  review among the opening's own steps for any project that has rows. The four
  contracts that publish EXCELLENT are readings taken WITH that review, because the
  rows behind them were in fact read. A reproduction that skips it gets the same
  scores and a held band -- `WORKABLE` with `review-answer-key` -- which is the hold
  doing its job, not a mismatch.

Both are committed, per scenario, under `verifier/measurement/`:

- `agent-read.json` — the statement of the agent's settings, with the source
  lines and the evidence for each. Authored, as the guide requires: it is a read
  of the agent, and another honest read could move a pillar by a few points.
- `row-review.json` — the five rows the opening asks for, actually read, with a
  per-row sentence saying why the expected output is or is not sensible, and the
  draw's seed and method recorded so a redraw is not invisible. It also records
  `reviewed` against `provided`: on case 46 that is 5 of 120, and the guide's
  own card says so — *"the coding assistant sampled 5 of 120 provided rows … a
  sample, so unreviewed answers are assumed sound rather than verified."* Four
  scenarios publish `caps: []`, and that sentence is what bounds it. Of the
  thirty reviewed rows, twenty-seven are recorded `yes`, two `unsure` and one
  `no`. The guide never scores an `unsure`, so case 46's line 52 costs that
  contract nothing and case 58's line 14 costs its contract nothing either; the
  one `no`, case 58's line 13, is what raises
  `dataset-unsound-expected-outputs` on that scenario and caps it at 70. The
  verdicts are recorded where the reader meets the scenario as well as here,
  because the cheapest available answer and the recorded answer being the same
  answer is a thing a reader should be told rather than left to discover.
- `invocation.json` — the commands the measurement ran, with this machine's
  paths replaced by `$PYTHON`, `$GUIDE`, `$PROJECT`, `$SCENARIO` and
  `$MEASURE`, the committed read bound as `$ROW_REVIEW`, and any step the
  measurement recorded refusing named under `refusals` with its message.

Six scenarios ship a review, because those are the six whose published contract
cannot be re-derived without one; the other seven record that none was passed.
Five of the six publish a band above the answer-key hold, which the guide
withholds until a read of the answers enters. The sixth is case 58, whose band
is below the hold and whose `caps` carry
`dataset-unsound-expected-outputs` -- a cap `readiness.py` builds out of the
review's own verdicts and out of nothing else. Measured rather than assumed:
the same inputs without `--row-review` return the same band, status and action,
and drop that cap.

Case 58 also publishes the opening for a read that finds every answer sound,
because five rows drawn from its thirty-two miss all three unsound answers
about three times in five: `verifier/expected-opening-sound-read.json`,
`STRONG` / `OK` / `proceed` / `dataset-coarse-resolution`, measured with
`row-review-sound-read.json`. `verify` grades the worker's read against the
scenario's verdict for every row (`verifier/row-verdicts.json`) and compares
the result with the contract for that read; the scenario's README gives the
detail.

`scripts/reproduce_openings.py` re-measures every published contract, fourteen
across the thirteen scenarios, by replaying each `invocation.json` as recorded
with only its placeholders bound, and compares every field a contract
publishes - the readiness schema version, band, status, action, every cap's
condition, ceiling, blocks and asks, and the displayed scores and
confidences. It refuses a guide checkout with local changes, and a recorded
step it cannot replay is reported as not measured rather than as a match.
Replaying runs each scenario's evaluator, so before anything runs it holds every
record to the guide commands a replay may run -- the validator `scenario.py
check` applies -- and refuses a scenario containing a link, and each step runs
under a deadline derived from the guide's own calibration ceiling. It reads and
never writes, and it has no mode that does. CI runs it against the pinned guide
revision, and weekly against the head of the guide's default branch with
`--against-head`, where a DRIFT row is a warning that the guide has moved rather
than a defect in a scenario.

    GUIDE=~/code/traigent-first-run python3 scripts/reproduce_openings.py

## Where two scenarios read the same

The opening contract this repository publishes is four fields -- band, status,
recommended action and caps, each cap with its ceiling and routing -- so
scenarios that differ in every other way can land on the same one. Four of the
thirteen do:

- `incident-severity-triage` (46), `helpdesk-queue-router` (47),
  `policy-handbook-rag` (48) and `warehouse-text-to-sql` (49) all read
  `EXCELLENT` / `OK` / `proceed` / no caps.

That is not four copies of one scenario. They are a closed-label classifier, a
routing agent, a retrieval agent over a twenty-document handbook, and a
text-to-SQL agent over a shipped SQLite database -- four agent types, four
datasets, four evaluators. What they share is the one reading the guide gives a
project with nothing that caps it, and there is only one of those. Case 49
carries a task-fit warning on its card that the contract does not compare,
which is why it sits in a different family from the other three.

It is written down here because a reader comparing four identical right-hand
cells cannot otherwise tell a deliberate coincidence from a copy-paste, and
because a new scenario landing on an existing contract should be a
decision rather than an accident. `tests/test_scenario.py` pins the set.

## Dataset origin rules

Every public scenario must distinguish repository origin from in-world scorer
metadata:

- `scenario.json` records who authored the published bytes and the license that
  permits redistribution.
- A row-level value such as `provenance: real` simulates what the fictional user
  declares to the readiness scorer. It does not claim that the repository row
  came from a customer or third party.
- In-world prose in a shipped project document - `project/PROJECT.md` calling
  its rows "90 real first messages from the last quarter", for instance - is
  the fictional customer's own declaration and stands on the same footing as a
  row-level `provenance` value. It says what that customer believes about their
  data; it makes no claim about the repository bytes.
- Third-party content must not be copied merely because a dataset name or
  provenance label appears in an earlier test. Use Traigent-authored clean-room
  material when it preserves the intended starting condition and evaluator
  behavior.

For the current release, every byte of all thirteen scenarios is
Traigent-authored synthetic content under Apache-2.0 and contains no customer
or third-party dataset. The companies, people, database rows, handbook pages,
transcripts, and emails in them are invented for the scenario.

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
measurement stops before paid work. An executing evaluator path is disclosed
rather than calibrated on the original, and the run continues on that
disclosure; any containment design beyond the guide's copied-actor route is
separately reviewed and approved outside it. Optimization can proceed only
after the necessary foundations are valid and the human approves the next
boundary.
