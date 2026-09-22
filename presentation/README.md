# Customer Presentation

This directory builds one customer-facing story from one validated semantic source:

- a self-contained HTML presentation for a browser; and
- an editable PowerPoint presentation with native text, shapes, and speaker
  notes.

The presentation explains the public scenario contract and the boundary between
catalog validation, a Phase A opening, and a separately approved Phase B live
optimization. The current content does not claim that a fresh worker run has
been recorded or verified.

The first 9 slides form the presales/CTO core story. The remaining 17 slides
are a clearly marked technical appendix with stage detail, scoring mechanics,
the scenario families, and a two-slide index of the thirteen-scenario bank.

## Source of truth

`src/content.ts` is the canonical slide content. It reads every published
scenario manifest and expected-opening contract under `scenarios/` - thirteen
today, cases 46 to 58 - and derives one catalog entry per scenario from those
files. The manifest schema accepts only the slugs in the bank table at the top
of the module, and a manifest whose case number disagrees with that table fails
the build. Case 46, the ready reference, is the worked example the walkthrough
slides focus on; the model requires it to be a catalog entry and requires every
catalog entry to appear on exactly one index slide. `src/model.ts` validates the
complete presentation before either renderer uses it.

Both HTML and PowerPoint consume the same parsed `presentation` object. Do not
maintain separate claims for the two formats, and do not hand-edit generated
files under `dist/`.

The Stage 2 scoring and cap slides are a reviewed snapshot of the public
Guided First Run scorer at revision
[`d07b62cd`](https://github.com/Traigent/traigent-first-run/blob/d07b62cd4abb6ecb6d2edcdcb2d535f02bb2c199/skills/traigent-first-run/scripts/readiness.py).
Their evidence footer records that revision. Re-check the source constants,
check display names, confidence behavior, and cap semantics whenever the guide
changes; do not adjust a number merely to improve slide layout.

## Reproduction contract behind the deck

The presentation's evidence wording follows the public CLI contract:

The commands below use case 46; every case number in the bank takes the same
three commands.

- `scenario.py check 46` validates the fully materialized package and the
  strict expected-opening structure and ranges. It does not run an agent.
- `scenario.py prepare 46 --guide-src PATH --output PATH` copies only clean,
  tracked selected-project and allowlisted guide files. Its captain-side
  `run.json` records the exact scenario project, captain-only contract, and guide
  Git revisions, aggregate content hashes, sorted file records, and worker handoff. Preparation executes
  no scenario or guide code and makes no network request.
- `scenario.py verify 46 --run-record RUN_JSON --result FILE` validates the
  recorded contract against its Git revision, reads strict JSON, and compares
  only `band`, `status`, `recommended_action`, and `caps`. It executes no
  verifier code.

The current deck has the published expectation for each of the thirteen
scenarios but no referenced captured worker result for any of them. An expected
opening is a captain measurement of the guide's own scripts over the project
bytes at the pinned guide revision: a contract to verify a run against, not a
recorded run. A successful catalog check or a copied expected-opening file must
not be presented as verified run evidence, and no scenario may be described as
having passed.

## Requirements

- Node.js 20.19 or newer
- npm with the committed lockfile
- Google Chrome or Chromium on `PATH`, or `CHROME_BIN` pointing to it, for
  the two-pass, isolated 1366x768 and 1600x900 browser-fit gate

Install locked dependencies and run the complete validation and build:

```bash
cd presentation
npm ci
npm run check
```

`npm run check` runs TypeScript checks, formatting validation, tests, semantic
content validation, and both presentation builds. Each gate identifies itself
by canonical path, so a gate invoked through a symbolic link runs instead of
exiting silently, and a gate that cannot place its own entry point fails rather
than reporting success. The browser-fit gate reads its verdict from the
attribute the in-page measurement wrote on the document element, so deck copy
that quotes that attribute cannot answer for a slide.

For focused work:

```bash
npm run dev          # local browser preview
npm run validate     # validate semantic content and claims
npm run build:web    # build the self-contained HTML
npm run build:pptx   # build the editable PowerPoint
npm run build:bundle # assemble the customer handoff bundle
npm run fit:browser  # render every slide at both required browser sizes
```

Run `npm run build` when the validated final outputs are needed together.

## Generated outputs

```text
dist/
  index.html
  traigent-first-run-scenarios.pptx
  customer-bundle/
    LICENSE
    NOTICE
    presentation.html
    presentation.pptx
    build-manifest.json
    checksums.txt
    THIRD_PARTY_NOTICES.txt
```

`dist/index.html` is a single self-contained file and can be opened directly in
an approved modern browser without a web server. The PowerPoint keeps slide text
and shapes editable and includes the presenter notes from the semantic source.

The customer bundle gives the two formats stable names and includes the
repository's Apache-2.0 `LICENSE` and `NOTICE`, a build manifest, transfer
checksums, and notices for third-party runtime software.

The manifest and checksums cover both repository legal files. The manifest
records every slide's evidence state and the exact source revision for each
guide-contract slide; the current manifest therefore makes the absence of
verified-run slides explicit.

The manifest's `offline` block is recorded from the checks that produced it and
carries a `verified_by` object stating what those checks establish. The scanned
set is the files the deck can actually reach: the walk of `src/` closed over the
imports those files declare, because the content module already imports scenario
data from outside the presentation tree, and a module placed beside it would
otherwise be compiled into the artifact without ever being opened. An extension
the scanner does not know is a build failure, not a file it skips. The built HTML
is then read as markup, so its external references, style declarations, and the
scripts the browser will run are each inspected, and deck copy that quotes a tag
or names a network API stays text. Neither check runs the deck:
`browser_execution_observed` is `false`, and the block records what the artifact
contains rather than what a browser was seen to do. In the built artifact a
request is reported when its address is visible, because bundled third-party code
may call `fetch` for local reasons; the first-party scan is the stricter of the
two and reports the capability itself.

Bundle creation fails without replacing an existing bundle when either
repository legal file is missing, empty, outside the repository, or a symbolic
link. Verify the checksums after copying the bundle to another machine using the
customer's approved tooling.

## Evidence labels

Every slide must contain at least one evidence reference, at least one speaker
note, and exactly one evidence state:

| Label                                   | Use                                                                           |
| --------------------------------------- | ----------------------------------------------------------------------------- |
| **Guide contract · no recorded run**    | Guide behavior pinned to an exact 40-character public guide revision          |
| **Scenario contract · no recorded run** | Published scenario facts or expected values without a referenced recorded run |
| **Verified run evidence**               | Complete retained Phase A report plus successful semantic verification        |
| **Not demonstrated in this deck**       | A live path, improvement, or other outcome that was not exercised             |

The current deck uses guide-contract, scenario-contract, and not-demonstrated
states. Do not change a slide to verified-run merely because its expected
values look correct. A run record, result JSON, and `PASS` alone are
insufficient. A verified claim requires both the matching semantic verification
and a retained report identifying the revisions, worker and session,
environment and isolation boundary, exact handoff and response, captured JSON,
complete commands, output and final statuses, verifier output, and stop point.

The validator currently rejects every verified-run slide until that evidence
has a strict retained schema and validator. This is an intentional fail-closed
boundary, not a missing checkbox that prose can satisfy.

Content validation rejects unsupported live-value and improvement claims. It
also prevents an absent result from becoming an implied green outcome. An
Excellent expected band is the published grade for one scenario's opening
contract; it is not a universal grade for the coding agent or proof of a live
optimization. A BLOCKED expected status is likewise a routing outcome the
scenario exists to check, not a failed test. The claim scan reads every string the content model carries, so a
claim is caught wherever it renders - slide body, footer evidence, speaker
notes, catalog card, or deck subtitle - and a field added to the schema is
covered without editing a list. Two things are not claims: a sentence that
denies its own claim, and the `Not proven` and `Does not prove` fields, whose
heading already states that the deck asserts nothing there. A denial in one
sentence does not cover a claim in the next.

## Updating the story

1. Update `src/content.ts` and, only when the contract itself changes,
   `src/model.ts`.
2. Keep scenario facts derived from the checked-in manifests and verifiers
   rather than duplicating them as manually maintained claims. A new scenario
   needs a row in the bank table in `src/content.ts` and a place on an index
   slide; the validator refuses a catalog entry no slide renders.
3. Give each new slide an evidence state, evidence reference, and useful speaker
   note.
4. Run `npm run check`.
5. Inspect both `dist/index.html` and the generated PowerPoint before customer
   use.

See [the repository guide](../GUIDE.md),
[customer-PC runbook](../docs/customer-pc-runbook.md), and
[methodology](../docs/methodology.md) for the operating and evidence boundaries.
