# Meeting summaries graded by an evaluator nobody can run

This public scenario models a summarization project whose agent and data are in
good shape and whose evaluator is not. The agent turns an engineering-meeting
transcript into a short summary of decisions and owners, the labeled dataset
covers four grades of meeting difficulty, and the evaluator delegates every
score to an in-house grading package -- `notesqa` -- that is not in the project
and cannot be installed from anywhere. The file parses, the docstring says
exactly what the grader does, and no score can ever come out of it.

The project is a customer-shaped simulation, not a customer project. Every byte
in this scenario is Traigent-authored synthetic content distributed under
Apache-2.0.

## What this scenario is for

Every earlier scenario with an evaluator ships one that runs. This one ships an
evaluator that *reads* as finished -- a rubric, a docstring in the team's voice,
the standard `score(output, expected, input_data, metadata)` signature -- and
fails on the first call with a missing import. The opening has to tell an
evaluator whose method is declared from one whose behaviour has been observed,
and it has to do so without being able to observe anything. The catalog records
the evaluator as `needs-repair` with method `llm-judge-rubric` (what the
docstring says the shared grader is) and no calibration record, because none
ships and none could be produced.

The agent and dataset are deliberately unremarkable so that whatever the opening
says about this project is about the evaluator.

## Scenario layout

The scenario is fully materialized and self-contained:

- `project/` contains the only scenario files assigned to the worker.
- `verifier/` contains the expected opening contract and captain guidance. It is
  public for reproducibility but is never copied into the worker's project.
- `scenario.json` identifies the scenario, its phase, content origin, license,
  materialized paths, starting condition, components, dataset profile,
  expected route, and evidence scope.

The worker-visible project contains exactly these files:

- `agent.py` -- LiteLLM through OpenRouter; three `openrouter/...` model ids,
  two summary lengths, two styles (prose or bullets), two temperatures. Every
  setting is a module-level literal table that `run(input_text, config)` reads
  through `config.get(...)` and either indexes into the prompt or passes to the
  request.
- `dataset.jsonl` -- 40 transcripts with reference summaries.
- `evaluator.py` -- the rubric, and a `score()` that imports `notesqa.grading`
  and delegates to it. Nothing else.
- `requirements.txt` -- the LiteLLM pin the agent needs. It does not name
  `notesqa`, because the customer installs that from an internal index the
  project does not describe.

There is no `traigent-runs/` directory: the customer has never calibrated this
evaluator, and the scenario ships no probes.

## Reading `dataset.jsonl`

Each of the 40 lines is one JSON object with three keys - `input`, `output`,
and `metadata`. The equivalent object below is formatted across several lines
for readability; the JSONL file stores it on one physical line, with the
transcript's speaker turns separated by `\n`:

```json
{
  "input": "Priya: Quick one before we close. The nightly Magpie ingest ...\nTomasz: I looked at it yesterday. ...",
  "output": "The nightly Magpie ingest is slow because ... Tomasz will add the partition key back ...",
  "metadata": { "difficulty": "easy", "split": "tuning", "provenance": "real" }
}
```

- `input` - a 150-300 word transcript of an engineering meeting at Corvid
  Analytics, a fictional analytics company, with three speakers named by first
  name only. Every transcript contains at least one decision with an owner and
  one or two digressions (badge readers, cake, a lost umbrella) that a summary
  must leave out. Product names (Magpie, Kestrel, Rookery, Perch, Talon) are
  the company's own components and recur across rows.
- `output` - the reference summary: two or three sentences naming every
  decision and its owner, no digression, and, where the meeting reversed
  itself, only the final position. This is free text, so the catalog's
  `label_shape` is `free-text` with a zero surface-label count -- there are no
  label strings to enumerate.
- `metadata.split` - `tuning` (34 rows) or `holdout` (6 rows). Holdout rows are
  reserved for checking a winner outside the tuning data, and no input appears
  in both.
- `metadata.difficulty` - `easy`, `medium`, `hard`, or `very-hard`, 10 rows
  each. The rubric:
  - **easy** -- one decision, one owner, one digression. The summary is the
    decision, its owner, and nothing else.
  - **medium** -- two distinct decisions with two distinct owners, plus a
    digression. A summary that drops either decision or swaps an owner is
    wrong.
  - **hard** -- a decision is made early in the meeting and reversed later,
    usually after someone brings evidence. The reference summary reports only
    the final position and the follow-up that replaced the abandoned one;
    reporting the first decision as adopted is the failure this stratum is
    built to catch.
  - **very-hard** -- two topics interleaved across the meeting, each with its
    own decision and owner, plus a red herring: a proposal that sounds like a
    decision but is explicitly parked, deferred or rejected. The reference
    names both real decisions and states that the red herring was not decided.
- `metadata.provenance` - always `real` here, and this is the one field that
  means less than it looks: it is **in-world scorer metadata** - what the
  fictional customer declares about their rows when the guide scores readiness.
  It does not describe where these repository bytes came from. Every byte in
  this scenario is Traigent-authored synthetic content (`content.origin` in
  `scenario.json`).

`scenario.py check 53` re-derives the row count, unique-input count, split
counts and stratum counts from the JSONL bytes and fails if they drift from the
manifest. It parses `agent.py` and `evaluator.py` for syntax and nothing more,
so it does not -- and cannot -- establish that the evaluator fails on its first
call. That is a run-time fact, and the whole point of this scenario is that the
opening has to reckon with it without a run.

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
optimization or a general performance claim. The expected band, status, action
and caps live in `verifier/expected-opening.json` and are not restated here.

## Content origin and row provenance

The dataset's row-level `provenance: real` values are in-world scorer metadata.
They simulate what the scenario's user declares about the rows when readiness
is assessed. They do not describe where the repository files came from and do
not claim that any row contains real customer or third-party data.

The repository-level source-of-origin contract is the one in `scenario.json`:
all scenario files and data are Traigent-authored synthetic content licensed
under Apache-2.0.
