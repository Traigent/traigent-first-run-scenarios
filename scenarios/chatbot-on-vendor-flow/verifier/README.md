# Opening verifier contract

`expected-opening.json` is the public semantic contract for this scenario's
Phase A opening result. Keep this directory outside the worker's assigned
project and run verification only after the worker has returned its result.

Semantic verification compares these fields exactly:

- `band`
- `status`
- `recommended_action`
- `caps`

The `display` section records the expected scorecard values for an honest
customer-facing rendering. It does not broaden the semantic pass criteria and
must be labeled as expected until a recorded run has been verified. Missing or
unverified run evidence must never be presented as a completed result.

This scenario ships no agent: the customer's routing runs on a hosted vendor
flow, and the project holds a flow export and a project note in the place an
agent would occupy. The contract therefore expects the opening to hold on the
agent pillar. A match is evidence that the guide reported that absence
honestly; it is not evidence that the flow was driven, measured, or optimized.

This contract is limited to `phase-a-opening`. A match is not evidence of a
credentialed service call, managed optimization, or end-to-end value-path run.
