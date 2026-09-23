# Opening verifier contract

`expected-opening.json` is the public semantic contract for this scenario's
Phase A opening result. Keep this directory outside the worker's assigned
project and run verification only after the worker has returned its result.

Semantic verification compares these fields exactly:

- `band`
- `status`
- `recommended_action`
- `caps` - each cap's condition, ceiling, blocks and asks

`intended-opening.json` is the hand-written answer beside the contract. It
names no cap, and it was written with this contract's band, status and action
already in view, so its agreement with the contract is not an independent check;
`docs/methodology.md` says what it can show. `verify` notes whether a result
agrees with it; a `PASS` still means the measured contract matched.

The `display` section records the expected scorecard values for an honest
customer-facing rendering. It does not broaden the semantic pass criteria and
must be labeled as expected until a recorded run has been verified. Missing or
unverified run evidence must never be presented as a completed result.

This contract is limited to `phase-a-opening`. A match is not evidence of a
credentialed service call, managed optimization, or end-to-end value-path run.
