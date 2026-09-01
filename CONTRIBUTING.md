# Contributing

Contributions should keep every scenario safe to publish, easy to inspect, and
deterministic to reproduce.

## Scenario standard

A scenario represents one useful starting point in the Traigent first-run
journey without containing real customer material. Confirm that:

- every published file is Traigent-authored and can be distributed under
  Apache-2.0;
- no secret, private link, private operational name, customer identifier, or
  claim about a real customer event is present;
- the starting state and expected opening behavior are stated precisely;
- `project/` contains the complete customer-shaped input and does not assemble
  fragments from a shared data area at run time; and
- `verifier/` is sufficient for captain-side comparison but unnecessary to the
  worker.

Authoring helpers may reduce maintenance duplication. Their checked-in output
must still be fully materialized so a reviewer can understand and reproduce one
scenario without reconstructing it from another.

## Required layout and manifest

```text
scenarios/<slug>/
  README.md
  scenario.json
  project/
  verifier/
    README.md
    expected-opening.json
```

The manifest follows `schema/scenario.schema.json` and includes:

- `schema_version: 1`;
- a stable `slug` and `legacy_id`;
- a customer-facing `title` and `summary`;
- `phase: phase-a-opening`;
- `paths.project: project` and `paths.verifier: verifier`;
- `content.origin: traigent-authored`; and
- `content.license: Apache-2.0`; and
- a required `catalog` containing the starting condition, component states and
  paths, agent controls, dataset profiles and limitations, evaluator method and
  calibration facts, expected-route reference, and bounded evidence scope. Two
  optional catalog keys account for content the task does not use:
  `datasets[].passthrough_fields` and `catalog.non_dataset_files`.

Catalog values are stable machine-readable identifiers and facts, not sales
copy. Put narrative explanation in the scenario README and presentation
speaker notes. Do not repeat `band`, `status`, `recommended_action`, or `caps`
in the catalog; the referenced `verifier/expected-opening.json` owns those
values.

Represent gaps explicitly instead of fabricating substitutes. Missing paths are
null, an agent with no usable controls has an empty control list, and an
unavailable split or difficulty dimension has a null field with empty counts.
Choose the output shape that matches the materialized rows rather than forcing
free-text, numeric, structured, or unlabeled data into a labelled profile.
For a present JSONL dataset, declared rows, unique inputs, dimensions, label
strings and per-label row counts must match the checked-in bytes exactly.

## What the catalog may claim

Every catalog fact this repository checks is a fact about bytes that ship.
`scenario.py` never imports or executes a scenario file -- shipped Python is
parsed for syntax and nothing more -- so it cannot establish what a program
does when it runs, and the contract does not ask a manifest to state it.

That is why `label_shape` describes the label column and not the evaluator:

- `mapped-labels` lists every distinct label string the rows carry, mapped to
  the number of rows carrying it, in `label_counts`. `surface_label_count` is
  the number of entries. Both are compared with the file.
- `unmapped-labels` declares `surface_label_count` and leaves `label_counts`
  empty, for a dataset whose spellings are too many to list.
- `absent`, `free-text`, `numeric` and `structured` declare a zero count and an
  empty `label_counts`.

Two spellings of the same severity are two label strings here, because two
strings are what the file carries. Whether an evaluator folds them together is
a property of the evaluator at run time; it is not asserted, so it cannot be
forged. `components.evaluator.method` is carried as a description of the
scenario and checked only for being one of `exact-match` or
`normalized-exact-match`; no count and no gate is derived from it.

**Not established here, on purpose:** whether the shipped evaluator actually
distinguishes the classes a scenario is built around, and what a constant answer
would score against it. Establishing that means running the evaluator, or
diffing a checked-in witness produced by a real run. Until one of those exists,
no manifest key claims it.

A declaration that switches a check off is itself checked against the bytes:

- Every column a row carries must be named by the catalog, down to the leaf:
  `input_field`, `label_field`, a dimension field, or `passthrough_fields` for
  the columns the task does not use. A column path is spelled the way the
  catalog spells one, so a `metadata` object holding `split` is described by
  `metadata.split`; naming a field describes its whole subtree, so a structured
  input column is named once rather than one key at a time. An empty object
  sitting where declared leaves live carries none of them, and no column
  either, so it needs no naming of its own. This holds for
  every label shape, so `label_shape.kind: absent` cannot claim rows carry no
  label while an undescribed column ships. A `passthrough_fields` entry no row
  carries is refused, so the declaration cannot outlive what it described.
  The walk goes at most `4` object levels deep, and it fails closed at the
  edge: a row nesting objects deeper is refused as unenumerable rather than
  waved through, and a declared field path deeper than the walk can reach is
  refused when the manifest is read.
- Under an `absent` shape, any column whose values across the rows are a small
  repeating set of short strings is a label surface whatever the catalog calls
  it -- including a column nested inside a described object. Only the input
  field and the two dimension fields are exempt: the first is what the model
  reads, and the other two are declared label-shaped columns already. A label
  at `metadata.severity` is a label, not an invisible key inside a `metadata`
  root the catalog happened to mention.
- Every file that ships under `project/` must be named by the catalog: a
  component path, a dataset profile, the calibration record, or
  `catalog.non_dataset_files` for content that is a record rather than task
  data. Nothing about a file's bytes decides whether it needs *naming*, because
  a check that decides that from the bytes is a check a file can be dressed to
  slip past. Each `non_dataset_files` entry must name a file that is there, and
  a declared record whose rows carry a closed label surface is refused: naming
  a dataset a record does not stop it being one. That scan reads the file both
  as a JSON row stream and as a delimited table -- each line goes to the
  reading it parses under, and the two answers are joined -- counting the rows
  each reading finds rather than letting the first line it cannot parse, a
  stray row of the other spelling, or a note above the table's header answer
  for the file.
- A component slot names bytes that read as Python source. `agent.path` and
  `evaluator.path` used to be checked only for naming a regular file under
  `project/`, which a byte-identical copy of the labelled dataset satisfied.
  The bytes are read with `ast.parse` -- never imported, never executed -- and
  a document of literals is data, not a component.
- A calibration case has to be a calibration case: a non-empty `probes` object
  over a case that records a non-empty `expected` label. A case without probes
  used to be skipped, which made the slot accept any array of objects, a
  labelled dataset included.
- A component declared `missing` may not ship its own source. `missing` forces
  the component's `path` to null, so the shipped files under `project/` are
  what the check reads: with a component declared missing, the only file whose
  bytes read as Python source is the source a component that is present names.
  The file's suffix decides nothing -- renaming `evaluator.py` to
  `evaluator.txt` does not make the evaluator absent.
- The sweeps read the Git index rather than the directory, because `prepare`
  copies recorded blobs: an untracked scratch file never reaches a worker.
  Outside a Git work tree -- and inside a foreign one, where the listing comes
  back empty -- every regular file is swept instead, which covers more rather
  than fewer.
- Published Python is parsed for syntax. It is never imported or executed.

**What these checks do not establish.** Each is a statement about bytes, and
the limits are worth stating rather than leaving to be discovered:

- Calibration `probes` are checked for being named, non-empty labels under a
  case that records one, and for nothing else. What they say about the
  evaluator -- that `equivalent_good` scores like the recorded label and `bad`
  does not -- is a run-time property, so `bad` equal to `expected`, every probe
  equal to `expected`, an `equivalent_good` naming the opposite severity, and
  probes naming labels no row carries are all accepted. The cross-check an
  earlier version ran here was removed with the forgeable label claim, because
  it compared the manifest with a partition the manifest declared about itself.
  Establishing any of it means running the evaluator, which this module does
  not do.
- The label-surface scan reads a record as JSON rows and as a delimited table.
  A record that is neither -- free-form prose carrying `INC-001: SEV1` on every
  line, say -- is reported as carrying no closed label surface. That is the one
  place left where "I could not establish this is a label surface" is answered
  as "it is not one", and it is stated here rather than implied.
- "Reads as Python source" means the bytes parse and are not purely literals.
  It does not mean the file is a working agent or evaluator; nothing here runs
  one.

The current schema admits only that origin and license pair. Adding another
origin, license, or third-party work requires a schema and licensing review
before the content is proposed.

The manifest's `content` object describes files distributed by this repository.
It does not describe in-world readiness metadata. A synthetic row may declare
`provenance: real` to model what a fictional user tells the scorer while the
repository bytes remain Traigent-authored synthetic content.

## Expected opening contract

`verifier/expected-opening.json` is a public semantic expectation, not evidence
that a run occurred. Keep the comparison narrow and machine-readable. The
current verifier compares:

- `band`
- `status`
- `recommended_action`
- `caps`

The contract itself must contain `schema_version: 1`,
`scope: phase-a-opening`, non-empty strings for the three verdict fields, and a
unique array of non-empty strings for `caps`. `display` must contain an
`overall` score and at least one named pillar. Every display score is finite and
between 0 and 100; every confidence is finite and between 0 and 1. Pillar names
are scenario-defined rather than hard-coded by the catalog.
Unknown top-level, `display`, and scorecard keys are rejected for schema version
1.

Any display scores must remain explicitly informational until a referenced run
artifact has been captured and verified. Never turn an expected value into a
completed-result claim by changing presentation wording alone.

## History-free imports

When approved material originates in another working repository, copy only the
reviewed current files into a new branch here and commit them as new work.

Do not use a fork, subtree, filtered history, cherry-pick, copied `.git`
directory, historical branch or tag, deleted file, or inherited commit message.
The public scenario receives a new identity in this repository. Source history
and unrelated context do not travel with it.

## Validate the final change

For every scenario change, run:

```bash
python -m pip install -r requirements-dev.txt
black --check scenario.py scripts tests
ruff check scenario.py scripts tests
mypy --strict scenario.py scripts/check_public_surface.py
python scenario.py list
python scenario.py show CASE
python scenario.py check CASE
python scenario.py check
python -m unittest discover -s tests -p 'test_*.py' -v
python scripts/check_public_surface.py
```

`check` validates catalog paths and declared dataset/calibration facts, then the
strict expected-opening structure and value ranges. Fix the contract rather
than weakening validation or substituting a different result.

If preparation behavior or worker-visible content changed, use a reviewed local
guide checkout and a new output path after committing the final selected
scenario files. `prepare` intentionally refuses dirty tracked inputs:

```bash
python scenario.py prepare CASE --guide-src /path/to/traigent-first-run --output /new/output/path
```

Inspect `customer-project/` and `run.json`, then verify an independently
captured opening object:

```bash
python scenario.py verify CASE \
  --run-record /path/to/run.json \
  --result /path/to/opening-result.json
```

Keep complete command output and final exit statuses. Do not use a successful
catalog check as evidence that a worker run passed.

If presentation content changes, also run from `presentation/`:

```bash
npm ci
npm run check
```

`npm run check` ends with the browser-fit gate, which requires Google Chrome
or Chromium (set `CHROME_BIN` if it is not on the default path); see
`presentation/README.md` → Requirements.

Edit the shared semantic source in `presentation/src/`; do not hand-edit build
artifacts.

## Pull request checklist

- [ ] The scenario is fully materialized and deterministic.
- [ ] All published bytes have confirmed authorship and redistribution rights.
- [ ] No customer data, secret, private name, or machine-specific path appears.
- [ ] Worker-visible files are limited to `project/` and the prepared guide.
- [ ] The manifest and expected opening contract match the implementation.
- [ ] Catalog, focused scenario, tests, and public-surface checks pass.
- [ ] Any Phase A evidence is labeled separately from Phase B.
- [ ] Presentation claims have the required evidence label and source.
- [ ] No source-repository history or metadata was retained.

Security findings belong in the private channel described by
[SECURITY.md](SECURITY.md), not in a public pull request.

Unless explicitly stated otherwise, contributions are submitted under the
repository's [Apache License 2.0](LICENSE).
