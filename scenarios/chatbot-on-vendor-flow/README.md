# Intent routing on a hosted vendor flow with no local agent

This public scenario models a customer who arrives with everything except an
agent. A fictional insurer, Ilex Mutual Insurance, runs its claims-intake
chatbot on a hosted conversation-flow product ("Conversa Flows"). The customer
can export the flow definition and re-import a changed one, but the classifier
that routes a customer's first message is the vendor's model behind the
vendor's prompt, and nothing in the project can call it. The customer has
labeled first messages, a deterministic intent evaluator, and calibration
probes; what they do not have is a program the guide can run.

The project is a customer-shaped simulation, not a customer project. Every byte
in this scenario is Traigent-authored synthetic content distributed under
Apache-2.0.

## What the scenario is for

The opening read should find a ready dataset and a ready, calibratable
evaluator, and report honestly that no agent reached it -- rather than reading
`flow-export.json` as one, inventing a thin adapter and presenting it as the
customer's agent, or scoring the two records as if they were source. The
customer's own note (`project/PROJECT.md`) asks to be told plainly when
something cannot be measured from what is there, and the expected route is the
guide saying exactly that.

## Scenario layout

The scenario is fully materialized and self-contained:

- `project/` contains the only scenario files assigned to the worker.
- `verifier/` contains the expected opening contract and captain guidance. It is
  public for reproducibility but is never copied into the worker's project.
- `scenario.json` identifies the scenario, its phase, content origin, license,
  materialized paths, starting condition, components, dataset profile,
  expected route, and evidence scope.

The worker-visible project contains exactly these files:

- `PROJECT.md` - the customer's note: what the bot is, that it runs on the
  vendor's hosted flow, that the flow export is what they have, and what they
  want improved.
- `flow-export.json` - a plausible export of the hosted flow: a flow id and
  version, ten nodes (`message`, `intent_classifier`, `collect`, `lookup`,
  `handoff`), the classifier prompt, the six intents with example utterances,
  a confidence threshold, and the precedence order for two-intent messages.
  It is a record, not a component: it ships under `non_dataset_files` and no
  Python ships beside the evaluator.
- `dataset.jsonl`
- `evaluator.py`
- `traigent-runs/calibration-cases.json`

The catalog declares the agent component `missing` with a null path and no
controls, the data and evaluator components `ready`, and
`starting_condition: gaps-present`. `scenario.py check` derives every dataset
count from the JSONL bytes, checks that the calibration JSON holds the declared
two cases, reads both records for a hidden label surface, and confirms that no
file other than the named evaluator reads as Python source. It does not import
or execute the evaluator, and it makes no claim about what the evaluator
distinguishes.

## Reading `dataset.jsonl`

Each of the 90 lines is one JSON object with three keys - `input`, `output`,
and `metadata`. The equivalent object below is formatted across several lines
for readability; the JSONL file stores it on one physical line:

```json
{
  "input": "I'd like to start a new claim for water damage in my kitchen.",
  "output": "new_claim",
  "metadata": { "difficulty": "easy", "split": "tuning", "provenance": "real" }
}
```

- `input` - the customer's first message to the chatbot. Every input is
  unique. Names, addresses and claim references are invented.
- `output` - the intent the fictional intake team would route the message to:
  one of `new_claim`, `claim_status`, `policy_question`, `update_details`,
  `complaint`, `human_agent`, 15 rows each. The rows use the flow export's
  spelling throughout. The shipped `evaluator.py` also folds the two other
  spellings the customer's records use (`New Claim`, `new-claim`) onto the same
  key -- that is a statement about what that file does when it runs, and the
  catalog does not restate it. What the catalog does record, and verify
  against the shipped rows, is `label_shape.label_counts`.
- `metadata.split` - `tuning` (75 rows) or `holdout` (15 rows). Holdout rows
  are spread across the four strata and reserved for checking a change
  outside the tuning data.
- `metadata.difficulty` - `easy`, `medium`, `hard`, or `very-hard`, graded by
  the rubric below: 23, 23, 22 and 22 rows.
- `metadata.provenance` - always `real` here, and this is the one field that
  means less than it looks: it is **in-world scorer metadata** - what the
  fictional customer declares about their rows when the guide scores readiness.
  It does not describe where these repository bytes came from. Every byte in
  this scenario is Traigent-authored synthetic content (`content.origin` in
  `scenario.json`).

`scenario.py check 57` re-derives every one of these counts from the JSONL
bytes and fails if they drift from the manifest.

## Difficulty rubric

Each row was graded against one question: how much of the routing decision is
in the words the customer chose?

- **easy** - the intent is stated. The message names the action in plain
  words ("make a claim", "status of my claim", "question about my policy",
  "update my address", "make a complaint", "speak to a person").
- **medium** - the intent is implied by a detail, never named. A storm
  damaged the roof last night (`new_claim`); the assessor came two weeks ago
  and nothing since (`claim_status`); a son just passed his driving test
  (`policy_question`); the car was sold and replaced (`update_details`); the
  assessor was rude and left mud in the hallway (`complaint`); a hearing
  difficulty makes written contact with staff easier (`human_agent`).
- **hard** - the wording resembles another intent while the ask is single.
  The message carries a rival intent's vocabulary, often to disclaim it ("not
  a complaint, but...", "I'm not making a new claim, I'm asking about...",
  "I don't need a person, just a straight answer..."), and the label is the
  one ask the message actually makes.
- **very-hard** - the message asks for two things, and the label follows the
  precedence rule the customer's flow applies. From highest to lowest:
  `human_agent`, `complaint`, `new_claim`, `update_details`, `claim_status`,
  `policy_question`. A request for a person is honoured before anything else;
  a dissatisfied customer reaches the complaints team before anything else is
  handled; a new loss is opened before a record is changed; a record is
  changed before a claim is looked up, so the lookup reads the corrected
  record; a policy question is answered last because it is self-service. The
  rule is stated in `flow-export.json` (`routing_rules`) and in the
  classifier node's prompt, so the worker can read it where the customer's
  intake team did.

One consequence of the rule is stated rather than hidden: `policy_question` is
the lowest rung, so it never labels a two-intent message. Its 15 rows sit in
the other three strata (five each), and the very-hard stratum is shared by
the five intents that can win a precedence contest.

## Context-isolated execution

For a recorded run, start a fresh worker with only a materialized copy of
`project/`, the selected Traigent first-run guide, and the standard
customer-visible handoff. Do not include this README, `scenario.json`, the
`verifier/` directory, expected results, or previous run evidence in the
worker's context.

This protocol provides context isolation on an honour-system basis. Because the
scenario is public, it is reproducible rather than hidden: deliberate external
lookup or prior knowledge invalidates a run but is not prevented by this
repository.

The declared scope is `phase-a-opening`. A matching result demonstrates the
published opening contract for this scenario; it does not demonstrate that the
hosted flow was driven, measured, or optimized, and it does not demonstrate a
general performance claim.

## Content origin and row provenance

The dataset's row-level `provenance: real` values are in-world scorer metadata.
They simulate what the scenario's user declares about the rows when readiness
is assessed. They do not describe where the repository files came from and do
not claim that any row contains real customer or third-party data.

The vendor product name, the insurer, the people, addresses and claim
references in the messages are invented. The repository-level source-of-origin
contract is the one in `scenario.json`: all scenario files and data are
Traigent-authored synthetic content licensed under Apache-2.0.
