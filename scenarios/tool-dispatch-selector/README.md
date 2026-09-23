# Voice-request tool dispatch with nothing to tune

This public scenario models a working project that has no search space. Its
agent turns one spoken request to a fictional smart-home hub ("Quillon Home")
into one of seven tool calls, its labeled dataset covers requests from the
obvious to the deliberately misleading, and its evaluator compares the chosen
tool and its arguments after normalizing both sides. What the project lacks is anything to vary: the
agent names one model as a plain constant, sends one fixed instruction, passes
no temperature, and accepts a `config` argument it never reads. The data and
the evaluator are ready; the agent is real and correct and still offers the
opening nothing to search.

The project is a customer-shaped simulation, not a customer project. Every byte
in this scenario is Traigent-authored synthetic content distributed under
Apache-2.0.

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

The catalog declares 90 unique labeled requests: 75 tuning and 15 holdout,
with 23, 23, 22 and 22 rows across the four difficulty strata. The label is
structured -- a tool call object rather than a label string -- so the catalog
lists no label strings and no per-label counts. `scenario.py check` derives
the row, split and stratum counts from the JSONL bytes and compares them with
the manifest; it also checks that the calibration JSON contains the declared
two cases. It does not import or execute the agent or evaluator to do so.

## What the agent is, and why its control list is empty

`agent.py` is a legitimate dispatcher a customer could run today. It declares
the hub's seven tools in a `TOOLS` tuple, renders them into one fixed
instruction, sends the request to one model named by the `MODEL` constant, and
parses the reply as a tool call, raising on anything that is not one. Nothing
about the request varies from call to call: there is no model table, no
alternative prompt wording, no temperature, and no worked examples. The
`config` argument the entry point accepts is unread, and the file says so in
the customer's own words.

The catalog records the agent as `limited` with an empty `controls` list. That
is the honest reading rather than a gap in the file: a control is a setting the
agent reads and routes into its request, and this agent has none. The dataset
and evaluator are `ready`, so the starting condition is `gaps-present` with the
gap on the agent alone. The expected opening therefore reports a search space
of one configuration and asks for settings that change the request before any
comparison can mean anything.

## Reading `dataset.jsonl`

Each of the 90 lines is one JSON object with three keys - `input`, `output`,
and `metadata`. The equivalent object below is formatted across several lines
for readability; the JSONL file stores it on one physical line:

```json
{
  "input": "It's freezing in the nursery, make it 22.",
  "output": { "tool": "set_thermostat", "args": { "room": "nursery", "degrees_c": 22 } },
  "metadata": { "difficulty": "medium", "split": "tuning", "provenance": "real" }
}
```

- `input` - the spoken request, as the hub's transcriber hands it over.
- `output` - the tool call the request determines: the tool's name and exactly
  the arguments that tool takes. Rooms, doors, scenes and days are the
  speaker's own words in lower case; relative days stay relative
  (`"tomorrow"`, `"saturday"`); temperatures are numbers; a reminder's `text`
  is the bare thing to do and its `when` is the time phrase as spoken; a media
  title keeps its capitalisation. The instruction in `agent.py` states the same
  conventions to the model, so every label is one the agent's own contract
  makes determinable. The shipped `evaluator.py` compares the two calls with
  strings stripped and case-folded and numbers compared numerically, so
  `"Nursery "` and `22.0` still match; that is a statement about what that file
  does when it runs, and the catalog does not restate it.
- `metadata.split` - `tuning` (75 rows) or `holdout` (15 rows). Holdout rows
  are reserved for checking a winner outside the tuning data, and are spread
  across all four strata and all seven tools.
- `metadata.difficulty` - `easy`, `medium`, `hard`, or `very-hard`, graded by
  the rubric below.
- `metadata.provenance` - always `real` here, and this is the one field that
  means less than it looks: it is **in-world scorer metadata** - what the
  fictional customer declares about their rows when the guide scores readiness.
  It does not describe where these repository bytes came from. Every byte in
  this scenario is Traigent-authored synthetic content (`content.origin` in
  `scenario.json`).

The seven tools each appear between 11 and 16 times across the file.

### Difficulty rubric

- **easy** - the tool is named outright or is the only plausible reading, and
  the request carries one argument stated in a slot phrase ("Lock the front
  door.").
- **medium** - a two-argument tool, with at least one argument read from
  context rather than from a slot phrase: a room from where the speaker says
  they are, a time from a leading or trailing clause, a temperature spelled
  out in words ("It's freezing in the nursery, make it 22.").
- **hard** - the wording borrows a verb or noun from a different tool's name
  or description, so the surface form points at the wrong tool ("Lock in the
  movie night scene." is a scene, not a lock; "Put on the forecast for
  Saturday." is weather, not media).
- **very-hard** - the request carries a distractor clause naming a room, door,
  day, temperature or tool that must not become an argument ("Lock the back
  door, the front one's already done."; "Remind me at 8 pm to lock the front
  door." is a reminder, not a lock).

Each row's label is the call a careful listener would produce under the
conventions the agent's instruction states.

`scenario.py check 52` re-derives every one of these counts from the JSONL
bytes and fails if they drift from the manifest.

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
