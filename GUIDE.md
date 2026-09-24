# Guide

Use this guide to inspect a public scenario or captain one reproducible Phase A
opening run. It does not authorize a credentialed optimization.

In this guide, **captain** means the human test operator who prepares the run,
controls the worker handoff and stop point, and retains evidence.

The repository releases thirteen scenarios, each with its expected opening
contract, as reviewed, versioned files — not recorded worker results. Until a
fresh run is captured and verified, describe an opening as **expected**, not
**verified**. Every step below works the same way for any scenario
`scenario.py list` shows; case `46` is the one the commands show, and an
output path is named after the scenario you run.

## 1. Create two clean checkouts

Use a disposable directory outside any customer production repository, and
outside any workspace an existing coding-agent session already has as context
— the worker must later open the prepared copy with none of these
repositories in its supplied context. The scenario workflow supports Python 3.11 through 3.13. The selected first-run
guide must be a local checkout so the run can identify exactly which guide
bytes were used.

```bash
git clone https://github.com/Traigent/traigent-first-run-scenarios.git
git clone https://github.com/Traigent/traigent-first-run.git
cd traigent-first-run-scenarios
```

Record both revisions before the run:

```bash
git rev-parse HEAD
git -C ../traigent-first-run rev-parse HEAD
```

Do not add credentials or customer data to either checkout.

## 2. Inspect and check the catalog

```bash
python scenario.py list
python scenario.py show 46
python scenario.py check 46
python scenario.py check
```

`list` discovers the released scenarios. `show` prints one validated manifest,
including its starting condition, component states, dataset profiles, expected
route, limitations, and evidence scope. `check CASE` validates those declared
facts against the materialized paths and data, then validates the strict
structure and ranges of its expected opening contract. `check` applies the same
validation to the entire catalog. These commands inspect files as data only.
They do not execute scenario or verifier code.

If a command fails, stop and report its complete output. Do not download,
generate, or substitute missing scenario data.

## 3. Prepare an isolated worker project

Choose a new output path whose parent exists but which does not itself exist:

```bash
python scenario.py prepare 46 \
  --guide-src ../traigent-first-run \
  --output ../incident-triage-run
```

`prepare` requires both this scenario repository and the guide source to be Git
checkout roots with committed `HEAD` revisions. It requires the stage-zero
index for every selected path to match that recorded commit, rejects tracked
changes in the selected scenario manifest, selected project, and allowlisted
guide paths, and rechecks both sources before success. It also rejects symbolic
links and non-regular input, and excludes untracked and ignored source files. It
then creates:

```text
incident-triage-run/
  customer-project/              Assigned to the worker
    agent.py
    dataset.jsonl
    evaluator.py
    traigent-runs/
    traigent-first-run/          Allowlisted guide files
  run.json                       Captain-side identity and content hashes
```

Only recorded Git blobs for tracked selected-project and allowlisted guide files
are copied. The allowlisted guide root includes `GUIDE.md`, `README.md`,
`LICENSE`, `NOTICE`, and `AGENTS.md` when tracked, plus the required first-run
skill tree. The worker project does not contain the scenario manifest, public
verifier, expected opening, previous results, or unrelated scenarios. `run.json`
records the scenario identity, phase, exact handoff, both committed revisions,
and deterministic inventories and content hashes for the worker project,
captain-only contract, and guide bundle. It contains no timestamp or absolute
source path.

Preparation copies inert bytes and invokes local Git read-only. It does not run
scenario code, guide code, a shell, a worker, or a network request. It also does
not create an operating system sandbox. Use the isolation required by the
customer-PC runbook.

On success, the command prints the prepared scenario, worker directory, captain
record, and fresh-agent handoff. Use those printed paths rather than inferring a
different layout.

## 4. Start one fresh worker

Start a new coding-agent conversation with its working directory set to:

```text
../incident-triage-run/customer-project
```

Give it only the handoff printed by `prepare`, unchanged:

```text
Help me run my first Traigent optimization.
Use the Traigent first-run checkout at ./traigent-first-run and follow ./traigent-first-run/GUIDE.md.
```

Do not mention the case number, expected band, verifier, grading contract, or
previous attempts. Do not place this repository or `run.json` in the worker's
supplied context.

The worker is not told this is a scenario run; only the captain knows the
case identity. The worker is deliberately
blinded so that it behaves like a real customer's coding agent: give it
nothing beyond the prepared project and the printed handoff, and its opening
reflects what a fresh agent would actually do.

The captain observes the run and stops it at the first question or decision
that belongs to the human. Where the guide declines to calibrate an
evaluator whose path would execute candidate code or SQL, it discloses the
declined check on the readiness card and continues; that disclosure is part
of the opening, not a stop. For this Phase A opening:

- do not provide a Traigent or model-provider credential;
- do not approve a paid or remote Traigent or model-provider call;
- do not send customer data or permit production mutation;
- do not install software unless a separate authorized procedure permits it;
- allow only local inspection and the exact deterministic evaluator calibration
  admitted by the first-run guide's safety gate; and
- do not continue into a baseline or optimization merely because the next step
  is available.

The coding-agent service itself may be remote. Obtain the customer's approval
for that service and limit the context it receives.

## 5. Capture and verify the opening

Retain the worker response according to the customer's evidence policy. When
the guide writes or returns its machine-readable opening readiness object, keep
the exact JSON file outside the worker project and run:

```bash
python scenario.py verify 46 \
  --run-record ../incident-triage-run/run.json \
  --result /path/to/opening-result.json
```

`verify` reads strict JSON, loads the contract from the scenario Git revision
recorded in `run.json`, requires the result's readiness `schema_version` to be
the one the contract was measured at, and compares these top-level semantic
fields:

- `band`
- `status`
- `recommended_action`
- `caps`

One scenario, `regex-rule-authoring` (58), publishes two contracts because its
opening turns on what the worker's read of its answers found. For it, also pass
the row review the worker gave readiness as `--row-review FILE`: `verify` grades
that read against the scenario's verdict for every row, then compares the
result with the contract for the read the worker gave. `--row-review` is
refused for every other scenario.

Expected `caps` record each cap whole: its `condition`, its `ceiling` (null for
a cap that discloses and bounds nothing), and whether it `blocks` the run or
`asks` first. Verification compares those four fields of every captured cap
object, in any order, and ignores the cap's wording (`reason`) and the routing
derived from its condition (`action_kind`). A run record naming a revision
whose contract predates this (contract schema 1) is compared on conditions
only, and `verify` says so. It reports every mismatch and never imports or
executes verifier code.

Three more options grade the run beyond the measured contract. Each is
optional and works alone, with the others, and with `--row-review`; each adds
its own clause to the `PASS` line, and none changes what the four fields are
compared with:

- `--agent-read FILE` - the agent read the worker gave readiness as
  `--agent-knobs`. Its setting names are compared with the settings the
  scenario's manifest declares by hand, `catalog.components.agent.controls` at
  the recorded revision: a name the manifest does not declare fails, and so
  does a declared one the read left out. Names only - never values, source
  lines or evidence - and a name counts as a setting only because the manifest
  lists it. For a scenario with no agent any read fails, because the guide
  gives readiness no agent read where it found no agent.
- `--project-dir DIR` - the worker's `customer-project/`. Every file `prepare`
  copied is re-hashed against the inventory it recorded in `run.json`: a
  modified or deleted file fails, and so does any added file other than the
  guide's documented opening writes -
  `traigent-runs/readiness/<YYYYMMDDTHHMMSSZ>/*`,
  `traigent-runs/calibration-cases.json` (rewriting a shipped one is reported,
  not failed), `traigent-runs/calibration-results.json`,
  `traigent-runs/calibration.log`, `traigent-runs/run-plan.md`,
  `traigent-runs/run-log.jsonl`, and, only where the project sits inside a Git
  work tree, a `.gitignore` holding just `/traigent-runs/`. Python's bytecode
  of a prepared module - `<dir>/__pycache__/<stem>.<tag>.pyc` beside a
  prepared `<dir>/<stem>.py` - is reported, not failed: the guide runs its
  calibration without `-B`, and the calibration imports the scorer and the
  guide's own `preflight.py`, so Python writes it. Such a file passes only as
  bytecode: the cache tag of a CPython the guide runs on (3.11 to 3.13), no
  optimization level but 1 or 2, that version's header over the prepared
  source's size, a body after the header, and - where `verify` runs that same
  version - a body that opens on marshal's code type and reads as one code
  object with nothing after it; a body that fails to read, out of memory
  included, is reported, never raised. The header's modification time is not
  compared: `run.json` records none to compare it with. A directory
  `prepare` did not create fails too, empty or not, unless it is
  `traigent-runs/`, its `readiness/`, a stamped directory in that, or such a
  `__pycache__/`. A directory it cannot read is an error, never a skip.
- `--response FILE` - the worker's final message, graded against the ask rules
  the guide's `SKILL.md` states, in two tiers divided by one principle: a
  finding, which fails, may turn only on the message's structure - its route
  labels (lines that open on a label such as `A.`, `**B.**` or `(C)`, and
  inline labels run A, B, C), its blank lines and indentation - and on the
  two tokens the guide defines for an ask, the mark `(recommended` and
  `I have it`. Beyond those label forms, `Option A:` among them, and the
  standing line's own words - `I have it` after "reply", and "Or reply
  `I have it`" at a route's opening - a word may hold a finding back as a note
  but never raise one, and a route's text never ends where a sentence does.
  The findings:
  - the message is empty;
  - a list read as routes whose labels do not run A, B, C from A: numbered,
    roman or lower-case labels on a marked list, a gap, or a repeat (a
    second `A` starts a list of its own);
  - two routes carrying the `(recommended...)` mark, or none carrying it in a
    message that never says "recommend" in any form. "(not recommended)" and
    "less recommended" are not the mark;
  - a route whose text opens on the standing line - `I have it`, "Reply
    `I have it`" or "Or reply `I have it`", the standing exit lettered as a
    route - and `I have it` offered only above the last route;
  - no "I have it" anywhere where the opening stops on the one ask for every
    gap: it is blocked, or a cap asks whose question the guide puts on that
    ask (a dataset top-up, coarse resolution, repeated rows, a split drawn by
    task family, an absent dataset). A cap whose question the guide puts
    elsewhere, such as the evaluator connection question it keeps for the
    pre-spend approval, does not require it;
  - and, as the grader's own fail-closed policy rather than a guide rule, a
    message with no route, no `?`, no recommendation, no reply to give
    (`Reply` and a backticked answer) and no "I have it", since an ask it
    cannot read is not a pass.

  One miss raises one finding: a route that opens on the standing line is that
  finding alone. A label line's shape is its frame - table cell, heading
  level, `(A)` or `Option A` form and separator - and its emphasis - bullet,
  list number, bold, backticks. A label line joins the list above it in the
  list's shape, or with only its emphasis different when its label is of the
  same sequence and its line comes directly under the list's last label line
  or across blank lines, so routes rendered with mixed emphasis, line under
  line, are graded as one list. A list is read as routes when it has two or
  more labels starting at A, or a route in it carries the mark, a single label
  line only when its label starts a sequence; a single label line that does
  not, a numbered list that marks nothing (files searched, rows cited by
  number) and options in another shape, such as keycap-emoji numbering,
  bullets or bold words, are not routes. No label line joins a list whose last
  label it comes more than three after, since the guide offers at most three
  choices on one question, so quoted `Q:`/`A:` rows are not routes however
  many there are; and a line that joins nothing and starts no sequence leaves
  the list above it open to the line after it, unless its label comes between
  the two, when it is the route in another form. The lines after such a route
  are not graded with the list above it - a gap, either mark rule, a route
  opening on the standing line and `I have it` offered above the last route go
  unfound after it - and the note on that route is what prompts a person to
  read them; so `### A.`, a prose line opening `B.`, `### C.` is read as A and
  C apart, with B noted, not as a gap. A route runs to the next label or the
  end of its paragraph, and stops at a later line, indented no deeper than its
  label's, that opens on `I have it` or on "Or reply `I have it`". The last
  route's mark is looked for in its paragraph, in the paragraph after it when
  its label line is a paragraph of its own (a heading or a bold title), and in
  paragraphs indented under it, up to `I have it`.

  Everything else is a note, printed as `response note:` on a `PASS` and on a
  `FAIL`, and never changing either: a question or decision phrase above the
  routes other than the one they answer, inside a route, between the routes
  and `I have it`, or after it; text following the `I have it` paragraph;
  `I have it` inside a route's text anywhere but at its opening, and a route
  opening on "I have it" in another spelling; a `(recommended)` mark outside
  every route, and a bullet that recommends an option; a recommendation in
  words where no route carries the mark, and a second route that also says
  recommended; an earlier list that recommends a route; lines labelled in a
  list not read as routes ("lines labelled ... are not read as routes") where
  the message asks or recommends something; a label line left out of a list
  only because its form differs, where its label would continue it ("route B
  is written in another form from route A"), and one of a list's own form kept
  out of a list that starts at `A` only by coming more than three after its
  last label ("label E comes more than 3 after label A"); a capital and full
  stop that breaks a run of inline routes; "I have it" only in another
  spelling; `I have it` offered twice; and a yes/no question on an ask with no
  routes. So a worker who quotes a customer's rows that are questions, as the
  pre-spend card requires, gets a note to read, not a failure. The rules are
  read from the `SKILL.md` that `prepare` copied, hashed against `run.json`
  first.
  `scripts/check_ask_shape.py` runs the same grade on its own, and lists what
  it grades, what it notes and what it leaves alone - among the last, two
  shapes with no note: an unmarked lower-case list split by form (`a.` then
  `b)`), and a label in another form more than three past a list's last
  (`A.`, `B.`, then `F)`). It is held to
  `tests/data/asks/`: messages that must pass with no note, pass with a named
  note, or fail with a named finding - among them every ask that
  `component-creation.md`, `run-safety.md` and `evaluation-and-dataset.md`
  print in quoted, backticked or lettered form, held verbatim, and for each
  rule it grades or notes, messages that break it.

Every contract also has a hand-written intended opening beside it; how it was
written, and what it can and cannot show, is in
[the methodology](docs/methodology.md#hand-written-answers). `verify` prints
whether the result agrees with it. That line is information: `PASS` still
means the measured contract matched.

A match supports only this statement:

> The four supplied opening fields matched the published Phase A contract at
> the scenario revision recorded in `run.json`, and the recorded scenario
> project and contract inventories matched that revision.

Each additional grade that passes adds one statement and no more: the supplied
agent read named exactly the settings the manifest declares; the supplied
project directory held every prepared file unchanged, apart from the guide's
documented opening writes; the supplied final message raised no hard finding
on the ask rules of the prepared guide's `SKILL.md`, which turn on its label
lines, the `(recommended)` mark and `I have it`.

None of this establishes that a worker produced the result, that the recorded
guide or isolation conditions were used, that a baseline or optimization ran,
that quality or cost improved, or that another project will receive the same
result.

A successful comparison prints `PASS`, names the matched fields and each
additional grade that ran, then the intended-opening line. A failure prints
`FAIL` and every mismatch, each grade's under its own prefix; retain the full
result rather than summarizing only the exit status.

## 6. Report the evidence boundary

Record:

- scenario slug and legacy identifier;
- scenario-repository and guide revisions;
- prepared `run.json`;
- worker, session, environment, and isolation-boundary description;
- exact handoff and worker response;
- the verified JSON bytes;
- complete command output and exit statuses, including verifier output; and
- the stop point.

Use one of the presentation evidence labels consistently:

- **Guide contract · no recorded run** for behavior pinned to an exact public
  guide revision, without a referenced captured run;
- **Scenario contract · no recorded run** for published scenario facts or
  expectations, without a referenced captured run;
- **Verified run evidence** only when every Phase A report item above is
  retained and referenced, and semantic verification passed; or
- **Not demonstrated in this deck** for any later behavior or outcome that was
  not exercised.

A run record, result JSON, and `PASS` alone are insufficient. Without the
complete retained report, keep the public result at **Scenario contract · no
recorded run**.

## 7. Keep Phase B separate

Phase B is a later human-guided run of the live value path. It begins only after
an authorized person reviews and explicitly approves every applicable
credential, network, installation, data-egress, cost, mutation, and
optimization boundary. Phase A never transitions to Phase B automatically.

Use [docs/customer-pc-runbook.md](docs/customer-pc-runbook.md) for the operating
checklist and [docs/methodology.md](docs/methodology.md) for the claims model.

## Run Traigent on a real project

The prepared handoff above refers to a guide already copied into the simulated
project. On a real customer project, open the coding agent in that project and
give it exactly:

```text
Help me run my first Traigent optimization.
Clone https://github.com/Traigent/traigent-first-run and follow GUIDE.md.
```

That real-project journey is not a scenario verification run. The human should
review the guide's decisions and approval gates in the actual environment.
