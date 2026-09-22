# Optimization-ready handbook question answering

This public scenario models a well-prepared retrieval-augmented
question-answering project. Its agent answers staff questions from a
20-document employee handbook by retrieving the best-matching paragraphs and
asking a model for a short answer; its labeled dataset covers a range of
question difficulty; and its evaluator compares the answer with the recorded
one after normalizing spelling, with a list of accepted aliases per question.

The project is a customer-shaped simulation, not a customer project. Every
byte in this scenario -- the handbook, the questions and the code -- is
Traigent-authored synthetic content distributed under Apache-2.0. The company
in the handbook, Marrowfield Logistics, its sites, teams and policies are
fictional.

## Scenario layout

The scenario is fully materialized and self-contained:

- `project/` contains the only scenario files assigned to the worker.
- `verifier/` contains the expected opening contract and captain guidance. It is
  public for reproducibility but is never copied into the worker's project.
- `scenario.json` identifies the scenario, its phase, content origin, license,
  materialized paths, starting condition, components, dataset profile,
  expected route, evidence scope, and the handbook files as
  `non_dataset_files`.

The worker-visible project contains exactly these files:

- `agent.py`
- `dataset.jsonl`
- `evaluator.py`
- `requirements.txt`
- `knowledge/*.md` (20 handbook documents)
- `traigent-runs/calibration-cases.json`

The catalog declares 90 unique labeled questions: 75 tuning and 15 holdout,
with 23, 23, 22 and 22 rows across the four difficulty strata, and records
that the rows carry 69 distinct answer strings without listing them
(`label_shape.kind: unmapped-labels`). `scenario.py check` derives those
counts from the JSONL bytes and compares them with the manifest; it also
checks that the calibration JSON contains the declared three cases and that
every file under `project/` is named. It does not import or execute the
agent or evaluator, and so it does not establish what the evaluator accepts
-- the catalog makes no claim about that.

## The agent and its settings

`agent.py` is a small retrieval-augmented answerer. It splits every handbook
file into paragraphs, ranks them by stemmed keyword overlap with the question,
and places the top four in the prompt (`TOP_K` is a fixed constant, not a
setting). Four settings are read from the configuration mapping and reach the
request: `model` (three Anthropic model ids, all of which accept a sampling
temperature), `context_format` (how the model is told to read the passages:
as verbatim quotations, as a list of separate facts, or as ordinary
paragraphs), `prompt_style` (answer directly, or state the rule first and put
the answer on the last line) and `temperature` (`0.0` or `0.5`). Each
text-shaped setting is one table entry selected whole into the prompt, which
is the shape a static read can follow from the table to the request; the
passages themselves are always rendered as labelled paragraphs. The reply is
parsed to its last line and trimmed, so the evaluator sees a short answer
whichever style produced it.

## Reading `dataset.jsonl`

Each of the 90 lines is one JSON object with three keys - `input`, `output`,
and `metadata`. The equivalent object below is formatted across several lines
for readability; the JSONL file stores it on one physical line:

```json
{
  "input": "How many weeks of maternity leave are paid at full pay?",
  "output": "16 weeks",
  "metadata": {
    "difficulty": "easy",
    "split": "tuning",
    "provenance": "real",
    "aliases": ["16", "sixteen weeks", "the first 16 weeks"]
  }
}
```

- `input` - the staff question the agent answers.
- `output` - the recorded short answer: a number, a name, a phrase or
  `yes`/`no`. Every answer is literally supported by the shipped handbook;
  the authoring check that confirms this is not part of the repository.
- `metadata.aliases` - the other spellings the fictional People team accepts
  for that answer. The shipped `evaluator.py` normalizes both sides and
  scores 1.0 when the answer equals the recorded one or any alias, and 0.0
  otherwise. That is a statement about what the file does when it runs; the
  catalog names the column as a passthrough field and claims nothing about
  how it is used.
- `metadata.split` - `tuning` (75 rows) or `holdout` (15 rows, 4/4/4/3
  across the strata). Holdout rows are reserved for checking a winner outside
  the tuning data.
- `metadata.difficulty` - `easy`, `medium`, `hard`, or `very-hard`, graded by
  the rubric below.
- `metadata.provenance` - always `real` here, and this is the one field that
  means less than it looks: it is **in-world scorer metadata** - what the
  fictional customer declares about their rows when the guide scores
  readiness. It does not describe where these repository bytes came from.

`scenario.py check 48` re-derives every one of these counts from the JSONL
bytes and fails if they drift from the manifest.

## Difficulty rubric

Each row is graded by what it takes to answer it from the handbook:

- **easy** - the answer is a number or phrase in one sentence of one
  document, and the question uses that sentence's own words.
- **medium** - the answer is one value, but the question paraphrases the
  handbook or the value has to be joined with a condition stated in a
  neighbouring sentence of the same document.
- **hard** - the answer needs two documents (one policy refers to another, or
  both state a part of the rule), or an exception clause that overrides the
  general rule.
- **very-hard** - the question describes a situation and the answer requires
  applying a rule: comparing a figure with a threshold, a date with a
  deadline, or a grade with an eligibility line.

The rubric was applied while writing each row, and each row records the
sentence or sentences that support it in the authoring source; those quotes
were checked against the shipped documents and against the agent's own
retrieval, so that every supporting sentence is among the four paragraphs the
agent places in its prompt. That check says nothing about whether a model
answers correctly from them.

## What the published opening rests on

`verifier/expected-opening.json` is what the guide returned for this project's
bytes at the pinned revision, and two of its inputs are committed beside it under
`verifier/measurement/`: the read of the agent's settings, and the row review.

The guide withholds its top two bands until a read of the expected answers has
entered, so this scenario's band depends on that review. It covers 5 of the
90 rows -- the five the opening asks for, drawn at random with the seed the
document records -- and the guide's own card says what that means: *a sample, so
unreviewed answers are assumed sound rather than verified*.

`scripts/reproduce_openings.py` re-runs the measurement from those files and
compares the result with the contract.

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
published opening contract for this scenario; it does not demonstrate a live
optimization or a general performance claim.

## Content origin and row provenance

The dataset's row-level `provenance: real` values are in-world scorer metadata.
They simulate what the scenario's user declares about the rows when readiness
is assessed. They do not describe where the repository files came from and do
not claim that any row contains real customer or third-party data.

The repository-level source-of-origin contract is the one in `scenario.json`:
all scenario files and data are Traigent-authored synthetic content licensed
under Apache-2.0.
