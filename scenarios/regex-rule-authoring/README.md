# Log-redaction rule authoring with a disputed answer key

This public scenario models a code-authoring project whose weak point is an
answer key nobody had read until this run read five rows of it. Its agent writes
one Python regular expression from a described shape, for the fictional
Ferrowick logging desk's redaction rule file. Its dataset holds thirty-two
descriptions the fictional customer declares as collected from that file, each
with a hand-written expression beside it. Its evaluator compares the expression
the agent returns with the recorded one as normalized text.

The project is a customer-shaped simulation, not a customer project. Every byte
in this scenario is Traigent-authored synthetic content distributed under
Apache-2.0.

## What the scenario is for

Two things, and the second is why the scenario exists.

The first is the `code` task kind. It is one of the ten kinds the guide knows,
and before this scenario no public case in this repository exercised it: the
two SQL cases are `code-sql`, which the guide treats separately.

The second is what a customer's own reading of their answers does to the
opening. The guide asks for five rows drawn at random, and it is the reader's
verdicts -- not a scan of the file -- that decide whether the answer key is
credited. Four of the thirty-two answers do not answer their own question
(lines 13, 16, 21 and 24). A read that marks one of them `no` bounds the
opening: the cap is `dataset-unsound-expected-outputs`, the routed action is
`review-answer-key`, and the run is not stopped. The scenario is the only case
in either repository where that cap is reached, and the only way to reach it is
for something to have actually read a row -- which is the property the cap is
there to have.

Line 13 is the plainest of the four. Its description says "a comma-separated
list of one or more numbers, no spaces. A single number is a list of one", and
its recorded rule is `\d+,\d+`, which requires a comma and so never matches `1`
at all. The row's own `must_reject` of `"1"` is the mistake written down rather
than caught. Line 24 is the same shape: "in any mix of upper and lower case",
recorded as the lower-case literal `password`, with `PASSWORD` under
`must_reject`. Nothing in this repository edits any of them.

### Two contracts, because the draw decides

Five rows drawn from thirty-two miss all four unsound answers a little under
half the time (C(28,5)/C(32,5) is about 0.49 for a uniform draw). A faithful
read of such a draw can find nothing wrong, and the guide then opens at `STRONG`
with `proceed`. That is not a failed run, so this scenario publishes both
openings, each measured from a committed read:

| The worker's read | Contract | Band / action / caps |
|---|---|---|
| marks some answer `no` | `verifier/expected-opening.json` | `WORKABLE` / `review-answer-key` / `dataset-unsound-expected-outputs`, `dataset-coarse-resolution` |
| marks no answer `no` | `verifier/expected-opening-sound-read.json` | `STRONG` / `proceed` / `dataset-coarse-resolution` |

Every published field, scores included, depends on that one fact and nothing
else about the read: reads with one, two and four `no` verdicts, and reads with
one or two `unsure`, were each measured and land on one of these two rows.

Which contract applies is decided by the read, so the read is graded too.
`verifier/row-verdicts.json` gives a verdict for every row with its reason:
`unsound` rows a faithful read must mark `no`, `sound` rows it must not, and
`contestable` rows careful readers settle either way. Line 14 is one: its
description stops at the drive letter and colon while its rule also demands a
backslash, and nothing in the row says which the desk meant. The key reads every
rule the way the desk uses it -- as a masking rule searched over a log line --
and says so in its `convention`.

The published read (`verifier/measurement/row-review.json`) is a seeded draw
that reached line 13 and line 14; the sound read
(`verifier/measurement/row-review-sound-read.json`) is chosen rather than
drawn, five rows the key marks sound, one per difficulty stratum and one held
out. `scenario.py check` grades both against the key and fails if the published
read marks nothing `no` or the sound read marks any answer `no`.

## Scenario layout

The scenario is fully materialized and self-contained:

- `project/` contains the only scenario files assigned to the worker.
- `verifier/` contains the expected opening contracts, the verdict for every
  row, the measurement records the published openings were produced from, and
  captain guidance. It is public
  for reproducibility but is never copied into the worker's project.
- `scenario.json` identifies the scenario, its phase, content origin, license,
  materialized paths, starting condition, components, dataset profile,
  expected route, and evidence scope.

The worker-visible project contains exactly these files:

- `agent.py`
- `dataset.jsonl`
- `evaluator.py`
- `requirements.txt`
- `traigent-runs/calibration-cases.json`

The catalog declares 32 unique descriptions: 24 tuning and 8 holdout, with 8
rows in each of four difficulty strata, a free-text label column, and one record
file (`requirements.txt`) under `non_dataset_files`. `scenario.py check` derives
those counts from the JSONL bytes and compares them with the manifest; it also
checks that the calibration JSON contains the declared three cases. It does not
import or execute the agent or evaluator, and so it does not establish what the
evaluator scores alike -- the catalog makes no claim about that.

## Reading `dataset.jsonl`

Each of the 32 lines is one JSON object with three keys - `input`, `output`,
and `metadata`. The equivalent object below is formatted across several lines
for readability; the JSONL file stores it on one physical line:

```json
{
  "input": "An ISO date, four-digit year, two-digit month, two-digit day, hyphen separated.",
  "output": "\\d{4}-\\d{2}-\\d{2}",
  "metadata": {
    "difficulty": "medium",
    "split": "tuning",
    "provenance": "real",
    "must_match": ["2024-03-09"],
    "must_reject": ["24-03-09"]
  }
}
```

- `input` - one sentence describing the shape the desk wants masked, in the
  words an engineer would write on the ticket.
- `output` - one Python regular expression, as source text. The catalog records
  this column as `label_shape.kind: free-text` and lists no label strings,
  because the answer is an expression rather than a label.
- `metadata.split` - `tuning` (24 rows) or `holdout` (8 rows). Holdout rows are
  reserved for checking a winner outside the tuning data and are spread across
  all four strata, two per stratum.
- `metadata.difficulty` - `easy`, `medium`, `hard`, or `very-hard`, 8 rows each,
  graded by the rubric below.
- `metadata.provenance` - always `real` here. This is **in-world scorer
  metadata** - what the fictional customer declares about where the rules came
  from when the guide scores readiness. It does not describe where these
  repository bytes came from.
- `metadata.must_match` and `metadata.must_reject` - one or more example
  strings the recorded expression is claimed to find, and one or more it is
  claimed not to find. They are the customer's own note about what they meant,
  they are declared as `passthrough_fields` in the catalog, and **nothing in the
  guided run reads them**: the evaluator compares expression text and never
  compiles anything.

  On two of the four unsound rows the note contradicts the recorded rule, which
  makes the finding mechanical: search a log line with the rule, give it the
  row's own `must_reject` string, and it matches. `ERROR` (line 16) is written
  without word boundaries so it finds `ERRORS`, and the stack-frame rule (line
  21) is written without a `^` so it finds `  at ` in the middle of a line. On
  lines 13 and 24 the note agrees with the rule - `\d+,\d+` really does reject
  `"1"`, and `password` really does reject `PASSWORD` - and both are wrong
  against their own *sentence*, which is why only a reader finds them, and why
  the row review is the thing that raises the cap.

`scenario.py check 58` re-derives every one of these counts from the JSONL bytes
and fails if they drift from the manifest.

### Difficulty rubric

Each row was assigned one stratum by the hardest feature its answer needs:

- **easy** - one character class and one quantifier, or a literal with one
  class after it. `\d{4}`, `SID\d{8}`.
- **medium** - two or more parts joined in sequence, or one optional group.
  `\d{2}:\d{2}(?::\d{2})?`, `[^@\s]+@[^@\s]+\.[^@\s]+`.
- **hard** - an alternation inside a group, a negated class carrying the work,
  or an anchor the description only implies. `\[(?:DEBUG|INFO|WARN|ERROR)\]`,
  `</?[a-zA-Z][a-zA-Z0-9]*>`.
- **very-hard** - a capturing group whose position is part of the answer, a
  backreference, or an escaping rule that has to be got right in the expression
  text itself. `"token"\s*:\s*"([^"]*)"`, `\b(\w+) \1\b`,
  `"(?:[^"\\]|\\.)*"`.

## The evaluator

`evaluator.py` compares the expression the agent returned with the recorded one
as text, after the tidying its docstring lists and nothing more: it strips
surrounding whitespace, reads `[0-9]` as `\d` and `[A-Za-z0-9_]` (in either
letter order) as `\w`, drops
a `{1}` repeat, and drops one redundant outer group - a `(?:...)` always, and a
plain `(...)` only when nothing inside it captures, because wrapping a rule that
captures its value moves that value to another group. It returns 1.0 for equal
and 0.0 for not. It does not remove a markdown code fence and does not touch
whitespace inside the expression. The catalog declares this as
`normalized-exact`.

**It never compiles either side, and that is deliberate.** Compiling a
candidate expression would execute a pattern this repository did not write
against strings it did not choose, which is a different and much larger promise
than scoring a first run needs; and matching it against `must_match` would score
the row against the customer's note rather than against their answer. The
refusal is written in the evaluator's own docstring so that a reader who wants
the other behaviour meets the reason first.

The cost of the refusal is real and the scenario states it: an expression that
is correct by a route the tidying does not cover scores 0.0. `a|b` is not `[ab]`
here, and `\[(?:INFO|DEBUG|WARN|ERROR)\]` - the four levels in another order -
is not line 17's rule. The limit is written where a reader meets it, in the
evaluator's docstring and here. It is not on the calibration record, and cannot
be: the guide's calibration requires the `equivalent_good` probe to score what
`good` scores, so a probe built to show the limit would read as a broken
evaluator rather than a stated one.

The three calibration cases cover what the tidying does accept: a class written
the long way (`[0-9]{4}` for `\d{4}`), a redundant outer group, and an
alternation inside a group with stray whitespace around it.

Calibration also raises a seam advisory worth reading: the evaluator alone
scores a fenced answer 0.0 even when the expression inside the fence is right.
The agent's `parse_reply` strips the fence before the evaluator sees it, so the
pair is sound as shipped -- but the advisory is correct that the evaluator would
not survive being handed a raw model reply, and the agent's `flavour` knob can
ask for exactly that reply. It is on the record for the same reason.

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

Verifying a run needs the read as well as the result, because the read decides
which contract applies. Collect the row review the worker passed to
`readiness.py --row-review` and give it to `verify`:

```bash
python scenario.py verify 58 \
  --run-record ../regex-rule-run/run.json \
  --result /path/to/opening-result.json \
  --row-review /path/to/row-review.json
```

`verify` fails a read that leaves an unsound row unmarked, marks a sound row
`no`, or reads other than five rows; otherwise it compares the result with the
contract for the read the worker gave.

The declared scope is `phase-a-opening`. A matching result demonstrates the
published opening contract for this scenario; it does not demonstrate a live
optimization or a general performance claim.

## Content origin and row provenance

The dataset's row-level `provenance: real` values are in-world scorer metadata.
They simulate what the scenario's user declares about the rows when readiness is
assessed. They do not describe where the repository files came from and do not
claim that any row contains real customer or third-party data.

The repository-level source-of-origin contract is the one in `scenario.json`:
all scenario files and data are Traigent-authored synthetic content licensed
under Apache-2.0.
