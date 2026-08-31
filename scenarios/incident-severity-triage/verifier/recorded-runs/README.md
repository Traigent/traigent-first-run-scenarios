# Recorded runs

Evidence that a fresh agent, given only this scenario's blinded project and the guide, produced
the answer `../expected-opening.json` says it should.

Until this directory existed, the repository published only the expectation. It could say
"here is what this scenario is designed to expect" and not "here is what it said when we ran it".

## What is here

| File | What it is |
|---|---|
| `2026-09-01-opening-result.json` | the readiness JSON the agent emitted |
| `2026-09-01-run-record.json` | the record `scenario.py prepare` wrote: both Git revisions and the captain-side hashes of every file handed over |

Re-check it yourself, from the repository root:

```bash
python scenario.py verify 46 \
  --run-record scenarios/incident-severity-triage/verifier/recorded-runs/2026-09-01-run-record.json \
  --result     scenarios/incident-severity-triage/verifier/recorded-runs/2026-09-01-opening-result.json
```

## How the run was blinded

The agent received `customer-project/` and the handoff sentence, and nothing else. It never saw
`expected-opening.json`, the `verifier/` directory, or any statement of how the scenario is
supposed to score -- verified before it started: the prepared run root contained no `verifier/`
directory and no occurrence of the expected band anywhere in it. It was asked not to look outside
the project or search for anyone's expectations of it.

It was also told to stop at the readiness stage. It did, at the provider-credential gate: no
model provider was called and nothing was spent.

## What matched

The verifier compares four fields exactly, and all four matched:

| Field | Expected | Recorded |
|---|---|---|
| `band` | `EXCELLENT` | `EXCELLENT` |
| `status` | `OK` | `OK` |
| `recommended_action` | `proceed` | `proceed` |
| `caps` | `[]` | `[]` |

The scorecard values agreed too, though they are not part of the pass criteria: overall 92 at
confidence 0.95, agent 70, dataset 98, evaluation 100.

## What this is evidence of, and what it is not

It is evidence that the **free opening** -- inspect and readiness -- reaches the published
contract on this scenario. It is not evidence of a paid run, a provider call, an optimization
result, or anything about a different starting state. This scenario is the READY one, the case
where nothing caps the score, so it is the weakest possible basis for generalizing to a project
that arrives incomplete.

One honest detail worth recording rather than hiding: the agent extended the scenario's
calibration cases from two to four while working. That is the guide doing its job -- filling a
gap it found -- and it is why a recorded run is worth having at all. The result still had to match
a contract written before the run.
