# Booking assistant next-action with a leaky holdout split

This public scenario models a conversational-assistant project that is one
repair away from being optimization-ready. Its agent reads the booking chat of
a fictional ferry operator, Harbourline Ferries, and names the single action the
assistant should take next; its evaluator compares that action name exactly;
and its review set is labelled, balanced and calibrated. The one thing wrong
with it is the split: six tuning transcripts are written into the file a second
time, byte for byte, with `split: holdout`, so the set held back to check the
winner already contains rows the winner was tuned on.

The project is a customer-shaped simulation, not a customer project. Every byte
in this scenario is Traigent-authored synthetic content distributed under
Apache-2.0. Harbourline Ferries, its ports, its sailings and its booking
references are invented.

## What the scenario is for

A leaky split is the quiet failure: nothing is missing, every row parses and is
labelled, the evaluator grades cleanly, and the held-out score at the end is
flattered rather than wrong-looking. The opening read has to find the overlap
from row identities, say that the number the run would report cannot be
trusted, and route the customer to redrawing the line rather than to
proceeding or to collecting more data. It should do that without discarding the
material: the rows are good, the split is not.

The transcript is deliberately plain text rather than a message list. Each
`input` is two to five lines prefixed `User:` or `Assistant:`, ending on a
`User:` line, so the opening read sees an ordinary text column and nothing in
the row shape announces the task as conversational.

## Scenario layout

The scenario is fully materialized and self-contained:

- `project/` contains the only scenario files assigned to the worker.
- `verifier/` contains the expected opening contract and captain guidance. It is
  public for reproducibility but is never copied into the worker's project.
- `scenario.json` identifies the scenario, its phase, content origin, license,
  materialized paths, starting condition, components, dataset profile,
  expected route, and evidence scope.

The worker-visible project contains exactly these files:

- `agent.py`
- `dataset.jsonl`
- `evaluator.py`
- `requirements.txt`
- `traigent-runs/calibration-cases.json`

The catalog declares 100 rows over 94 unique inputs: 83 tuning and 17 holdout,
with 25 rows in each of four difficulty strata, and it lists the eight action
names the rows carry with the number of rows carrying each. `scenario.py check`
derives those counts from the JSONL bytes and compares them with the manifest;
it also checks that the calibration JSON contains the declared two cases. It
does not import or execute the agent or evaluator, and it does not decide which
of the 100 rows are the repeated ones - the catalog records the counts, and the
opening read is what has to find the overlap.

## The agent

`agent.py` calls the Anthropic Messages API and exposes five settings, each a
module-level literal table that `run(input_text, config)` reads through
`config.get(...)` and indexes:

- `model` - one of two model ids in `MODELS`.
- `history_window` - how many trailing turns of the transcript the model is
  shown, one of `HISTORY_WINDOWS = (1, 3, 8)`, sliced by code. A window of 1
  shows only the last customer line, which is enough for the easy rows and,
  by construction, not for the medium and hard ones; a window of 8 shows every
  turn of every transcript in the file.
- `prompt_style` - the instruction that leads the prompt. `direct` names the
  task; `precedence` spells out the ordering rules below.
- `output_format` - a bare action name or a JSON object `{"action": ...}`.
- `temperature` - one of `(0.0, 0.4)`, passed straight to the request.

The reply is parsed into one of the eight action names and anything else is
raised.

## Reading `dataset.jsonl`

Each of the 100 lines is one JSON object with three keys - `input`, `output`
and `metadata`. The equivalent object below is formatted across several lines
for readability; the JSONL file stores it on one physical line, with the
transcript's line breaks written as `\n`:

```json
{
  "input": "User: Hello.\nAssistant: Hello, welcome to Harbourline Ferries. How can I help?\nUser: What is your policy on taking a dog on the Sallow Island crossing?",
  "output": "explain_policy",
  "metadata": { "difficulty": "easy", "split": "tuning", "provenance": "real" }
}
```

- `input` - the chat so far, as the widget hands it over.
- `output` - the action the assistant should take next, one of eight:
  `ask_dates`, `ask_passengers`, `quote_fare`, `confirm_booking`,
  `offer_alternative`, `explain_policy`, `escalate_to_agent`,
  `cancel_booking`. The shipped `evaluator.py` strips and casefolds both sides
  before comparing, so `Cancel_Booking` and `cancel_booking` are the same
  answer - that is a statement about what the file does when it runs, and the
  catalog does not restate it. What the catalog does record, and verify against
  the shipped rows, is `label_shape.label_counts`.
- `metadata.split` - `tuning` (83 rows) or `holdout` (17 rows). Of the 17
  holdout rows, 11 are transcripts that appear nowhere else in the file and 6
  are exact copies of tuning rows with only the split changed. The catalog
  declares `rows: 100` and `unique_inputs: 94` for that reason, and the data
  component is `needs-repair`.
- `metadata.difficulty` - `easy`, `medium`, `hard` or `very-hard`, 25 rows
  each, counted over the 100 lines. The six repeated rows fall two in `easy`,
  one in `medium`, one in `hard` and two in `very-hard`, so every stratum is
  touched by the defect.
- `metadata.provenance` - always `real` here, and this is the one field that
  means less than it looks: it is **in-world scorer metadata** - what the
  fictional customer declares about their rows when the guide scores readiness.
  It does not describe where these repository bytes came from. Every byte in
  this scenario is Traigent-authored synthetic content (`content.origin` in
  `scenario.json`).

`scenario.py check 51` re-derives every one of these counts from the JSONL
bytes and fails if they drift from the manifest.

## How the labels were decided

Every label follows the booking rules below. They are the rules the fictional
operator's assistant works to, and the `precedence` prompt style states the
same rules to the model.

**What each action means.**

- `ask_dates` - a quote or booking is wanted and no travel date is settled.
- `ask_passengers` - the date is settled and the passenger count is not.
- `quote_fare` - date and passengers are settled, the customer wants a price
  or a booking, and no fare has yet been quoted for what they now want.
- `confirm_booking` - the customer accepts a fare the assistant has quoted.
- `offer_alternative` - the sailing the customer wants is unavailable, or the
  customer rejects the quoted option and asks for another.
- `explain_policy` - the customer asks about a rule: pets, refunds, check-in,
  vehicle limits, missed sailings, infants, bicycles and the like.
- `escalate_to_agent` - the request is outside the assistant's authority: the
  customer asks for a person; makes a complaint; needs a medical or
  accessibility arrangement; disputes a payment; is a party of ten or more
  (the groups desk owns those bookings and their prices); reports lost
  property; or gives a booking reference the assistant cannot find after the
  customer has checked it.
- `cancel_booking` - the customer holds a booking reference and asks for it to
  be cancelled.

**Precedence when a transcript carries two needs**, highest first:

1. `escalate_to_agent` - anything a person has to handle is handed over before
   anything else is done.
2. `cancel_booking` - an existing booking is cancelled before a new one is
   priced, made or asked about.
3. `explain_policy` - a rule question is answered before a price or a
   confirmation, because the answer may change whether the customer books.
4. Missing details - `ask_dates` before `ask_passengers`.
5. `confirm_booking` before `quote_fare` or `offer_alternative` - an accepted
   fare is booked before anything new is priced.

**Contradictions.** When the last turn conflicts with an earlier one:

- an unacknowledged conflict on a booking detail - the customer names a
  different date or headcount without saying it has changed - re-opens that
  detail (`ask_dates`, `ask_passengers`), because a booking made on a guessed
  number is worse than a question;
- a stated correction ("sorry, I meant", "make that") replaces the earlier
  value and the assistant continues with it;
- a reversal of intent (book it / don't; keep it / cancel it; no person / a
  person) follows the latest turn.

## Difficulty rubric

Applied per row from the transcript alone:

- **easy** - the last `User:` line alone decides the label; nothing earlier
  changes it.
- **medium** - the label depends on an earlier turn: an assistant question the
  customer answers sideways, a quote the customer accepts with "go on then", a
  sailing the assistant has already said is full.
- **hard** - the last turn contradicts an earlier one, and the contradiction
  rules above decide the label.
- **very-hard** - the last turn carries two needs, and the precedence ladder
  decides which is served first.

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
optimization, a repaired split, or a general performance claim.

## Content origin and row provenance

The dataset's row-level `provenance: real` values are in-world scorer metadata.
They simulate what the scenario's user declares about the rows when readiness
is assessed. They do not describe where the repository files came from and do
not claim that any row contains real customer or third-party data.

The repository-level source-of-origin contract is the one in `scenario.json`:
all scenario files and data are Traigent-authored synthetic content licensed
under Apache-2.0.
