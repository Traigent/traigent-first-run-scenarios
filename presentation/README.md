# Customer Presentation

This directory builds one customer-facing story from one validated semantic source:

- a self-contained HTML presentation for a browser; and
- an editable PowerPoint presentation with native text, shapes, and speaker
  notes.

The presentation explains the public scenario contract and the boundary between
catalog validation, a Phase A opening, and a separately approved Phase B live
optimization. The current content does not claim that a fresh worker run has
been recorded or verified.

## Source of truth

`src/content.ts` is the canonical slide content. It reads the published scenario
manifest and expected opening contract. `src/model.ts` validates the complete
presentation before either renderer uses it.

Both HTML and PowerPoint consume the same parsed `presentation` object. Do not
maintain separate claims for the two formats, and do not hand-edit generated
files under `dist/`.

The Stage 2 scoring and cap slides are a reviewed snapshot of the public
Guided First Run scorer at revision
[`6ec2b9c1`](https://github.com/Traigent/traigent-first-run/blob/6ec2b9c161400cd91faea9c8cdb1c4e00d21c8d9/skills/traigent-first-run/scripts/readiness.py).
Their evidence footer records that revision. Re-check the source constants,
check display names, confidence behavior, and cap semantics whenever the guide
changes; do not adjust a number merely to improve slide layout.

## Reproduction contract behind the deck

The presentation's evidence wording follows the public CLI contract:

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

The current deck has the published expectation but no referenced captured
worker result. A successful catalog check or a copied expected-opening file must
not be presented as verified run evidence.

## Requirements

- Node.js 20.19 or newer
- npm with the committed lockfile

Install locked dependencies and run the complete validation and build:

```bash
cd presentation
npm ci
npm run check
```

`npm run check` runs TypeScript checks, formatting validation, tests, semantic
content validation, and both presentation builds.

For focused work:

```bash
npm run dev          # local browser preview
npm run validate     # validate semantic content and claims
npm run build:web    # build the self-contained HTML
npm run build:pptx   # build the editable PowerPoint
npm run build:bundle # assemble the customer handoff bundle
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
checksums, and notices for third-party runtime software. The manifest and
checksums cover both repository legal files. Bundle creation fails without
replacing an existing bundle when either repository legal file is missing,
empty, outside the repository, or a symbolic link. Verify the checksums after
copying the bundle to another machine using the customer's approved tooling.

## Evidence labels

Every slide must contain at least one evidence reference, at least one speaker
note, and exactly one evidence state:

| Label                             | Use                                                                                        |
| --------------------------------- | ------------------------------------------------------------------------------------------ |
| **Expected scenario contract**    | Published scenario facts or expected opening values without a referenced recorded run      |
| **Verified run evidence**         | A claim directly supported by a supplied retained run artifact and successful verification |
| **Not demonstrated in this deck** | A live path, improvement, or other outcome that was not exercised                          |

The current deck uses only expected-contract and not-demonstrated states. Do not
change a slide to verified-run merely because its expected values look correct.
A verified claim requires the referenced run evidence and the matching semantic
verification result.

Content validation rejects unsupported live-value and improvement claims. It
also prevents an absent result from becoming an implied green outcome. An
Excellent expected band is the published grade for this scenario's opening
contract; it is not a universal grade for the coding agent or proof of a live
optimization.

## Updating the story

1. Update `src/content.ts` and, only when the contract itself changes,
   `src/model.ts`.
2. Keep scenario facts derived from the checked-in manifest and verifier rather
   than duplicating them as manually maintained claims.
3. Give each new slide an evidence state, evidence reference, and useful speaker
   note.
4. Run `npm run check`.
5. Inspect both `dist/index.html` and the generated PowerPoint before customer
   use.

See [the repository guide](../GUIDE.md),
[customer-PC runbook](../docs/customer-pc-runbook.md), and
[methodology](../docs/methodology.md) for the operating and evidence boundaries.
