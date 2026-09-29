# Opening verifier contract

`expected-opening.json` is the public semantic contract for this scenario's
Phase A opening result. Keep this directory outside the worker's assigned
project and run verification only after the worker has returned its result.

Semantic verification compares these fields exactly:

- `band`
- `status`
- `recommended_action`
- `caps` - each cap's condition, ceiling, blocks and asks

`intended-opening.json` is the hand-written answer beside the contract. At
this guide revision, the SQL text-comparison mismatch opens an evaluator-fit
ask, holds the band at WORKABLE and routes `review-evaluator-fit`. It does not
create a score cap or stop the run. The old declared divergence was resolved by
the guide; `divergence` is now null. As explained in `docs/methodology.md`, this
agreement alone is not an independent correctness proof: the author saw the
measured result and checked the task-fit semantics against the guide.

The `display` section records the expected scorecard values for an honest
customer-facing rendering. It does not broaden the semantic pass criteria and
must be labeled as expected until a recorded run has been verified. Missing or
unverified run evidence must never be presented as a completed result.

This contract is limited to `phase-a-opening`. A match is not evidence of a
credentialed service call, managed optimization, or end-to-end value-path run.
