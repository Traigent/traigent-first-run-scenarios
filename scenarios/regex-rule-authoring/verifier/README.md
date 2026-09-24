# Opening verifier contract

This scenario publishes two semantic contracts for its Phase A opening, because
the opening turns on what the worker's read of the answers found:

- `expected-opening.json` applies when the worker's five-row read marks any
  answer `no`.
- `expected-opening-sound-read.json` applies when it marks none.

`row-verdicts.json` classes every row of the dataset `sound`, `unsound` or
`contestable`, with a reason. `scenario.py verify --row-review` grades the
worker's read against it - an unsound row must be marked `no`, a sound row must
not be - and then compares the result with the contract for that read. The
reads each contract was measured with are under `measurement/`.

Keep this directory outside the worker's assigned project and run verification
only after the worker has returned its result.

Semantic verification compares these fields exactly:

- `band`
- `status`
- `recommended_action`
- `caps` - each cap's condition, ceiling, blocks and asks

`intended-opening.json` is the hand-written answer beside the contract. It was
written with this contract's band, status, action and cap conditions already in
view. Each cap's ceiling was read off the guide's `readiness.py` constants, and
whether it blocks or asks from the guide's routing reference together with
`readiness.py`'s comments on its cap type. So its agreement on ceilings is the
code agreeing with itself, and on blocks and asks only partly an independent
check; `docs/methodology.md` says what it can show. `verify` notes whether a
result agrees with it; a `PASS` still means the measured contract matched.

Each of the two contracts has its own intended opening:
`intended-opening-sound-read.json` answers `expected-opening-sound-read.json`.

The `display` section records the expected scorecard values for an honest
customer-facing rendering. It does not broaden the semantic pass criteria and
must be labeled as expected until a recorded run has been verified. Missing or
unverified run evidence must never be presented as a completed result.

Both contracts are limited to `phase-a-opening`. A match is not evidence of a
credentialed service call, managed optimization, or end-to-end value-path run.
