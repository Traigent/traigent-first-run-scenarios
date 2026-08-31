# Recorded runs

A fresh agent, given only this scenario's blinded project and the guide, produced the answer
`../expected-opening.json` says it should. Until this directory existed the repository published
only the expectation -- it could say "here is what this scenario is designed to expect" and not
"here is what it said when we ran it".

## Re-check it yourself

```bash
python scenario.py verify 46 \
  --run-record scenarios/incident-severity-triage/verifier/recorded-runs/2026-09-01-run-record.json \
  --result     scenarios/incident-severity-triage/verifier/recorded-runs/2026-09-01-opening-result.json
```

The verifier re-reads `expected-opening.json` out of the Git object store at the revision named in
the run record, so the target cannot be moved to fit the result.

That revision is `b6c94bc`, which is on `main`. This matters: an earlier attempt pinned a branch
commit, and a squash or rebase merge would have minted a new SHA and left the command above
failing with `cannot load the scenario revision recorded by the captain run record`. Evidence that
verifies under only one of three merge buttons is not evidence.

## What matched

| Field | Expected | Recorded |
|---|---|---|
| `band` | `EXCELLENT` | `EXCELLENT` |
| `status` | `OK` | `OK` |
| `recommended_action` | `proceed` | `proceed` |
| `caps` | `[]` | `[]` |

Those four are what `verify` compares. The scorecard agreed as well and is **not** checked by
anything, so treat it as reporting rather than as a guarantee: overall 92 at confidence 0.95,
agent 70, dataset 98, evaluation 100.

## Blinding: what is proven, and what is attested

These are two different claims and it is worth not blurring them.

**Proven by the artifact.** `inputs.scenario_project.files` enumerates exactly what was
materialised into the worker's directory -- `agent.py`, `dataset.jsonl`, `evaluator.py`,
`traigent-runs/calibration-cases.json` -- each pinned by sha256, and `verify` re-derives that list
from Git. No verifier file is among them. `prepare` copies only the project and guide inventories;
the contract inventory is recorded in `run.json` and never copied.

**Attested by the captain, not provable from the artifact.** That the prepared run root contained
no `verifier/` directory and no occurrence of the expected band, and that the agent was instructed
not to search outside its project for anyone's expectations of it. The run record has no field
distinguishing "handed to the worker" from "held back", so this rests on the process, not on the
file.

## What the agent changed while working

It added two calibration cases (2 -> 4) covering severity levels the existing pair missed, keeping
both originals byte-for-byte. **That happened in the disposable run root, not in this repository**
-- the committed `calibration-cases.json` still holds two cases.

So what this run demonstrates is *published starting state, plus one guide-driven repair* ->
EXCELLENT. Not *published starting state* -> EXCELLENT. The readiness scores above were computed
after that repair. It is the guide doing its job, and it is the honest reading of the result.

## What this is evidence of, and what it is not

The **free opening** -- inspect and readiness -- reaching the published contract on this scenario.
The agent stopped at the provider-credential gate: no provider call, nothing spent.

It is not evidence of a paid run, an optimization result, or anything about a different starting
state. This scenario is the **ready** one, the case where nothing caps the score, so it is the
weakest possible basis for generalising to a project that arrives incomplete.

Two limits of the record worth stating rather than leaving to be found:

- `inputs.guide_bundle.git_sha` names a revision in a different repository, so no check a reader
  runs here can confirm which guide produced this result.
- The contract carries `schema_version: 1` and the result `schema_version: 2`; `verify` compares
  neither, and the contract's `scope` field has no counterpart in the result.
