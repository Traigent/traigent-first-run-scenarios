# Opening verifier contract

`expected-opening.json` is the public semantic contract for this scenario's
Phase A opening result. Keep this directory outside the worker's assigned
project and run verification only after the worker has returned its result.

Semantic verification compares these fields exactly:

- `band`
- `status`
- `recommended_action`
- `caps` - each cap's condition, ceiling, blocks and asks

`intended-opening.json` is the hand-written answer beside the contract, written
with this contract's band, status and action already in view. It departs from
the measurement, and says so under `divergence`, naming the two fields that
differ with both values: the guide's evaluation reference treats a scorer that
compares SQL as text as a finding to repair, and its readiness script at
`d07b62cd` has no cap or ask for it, so the measured opening proceeds with
neither. The intended cap, `evaluator-task-mismatch`, is this repository's name
for that finding. Whether it asks or blocks follows the evaluation reference
and `SKILL.md` section 2; its ceiling is null because neither the guide's
documentation nor `readiness.py` gives the finding a number - a choice, not a
reading. No public guide issue has been filed. `docs/methodology.md` says what
the file can show. `verify` notes whether a result agrees with it; a `PASS`
still means the measured contract matched.

The `display` section records the expected scorecard values for an honest
customer-facing rendering. It does not broaden the semantic pass criteria and
must be labeled as expected until a recorded run has been verified. Missing or
unverified run evidence must never be presented as a completed result.

This contract is limited to `phase-a-opening`. A match is not evidence of a
credentialed service call, managed optimization, or end-to-end value-path run.
