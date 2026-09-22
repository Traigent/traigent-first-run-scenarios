# Optimization-ready helpdesk queue router

This public scenario models a well-prepared support-desk routing project. Its
agent sends each inbound ticket to one of the six queues a fictional B2B payroll
product's desk runs, its labeled dataset covers a range of routing difficulty,
and its evaluator folds together the queue spellings of three different
ticketing tools.

The project is a customer-shaped simulation, not a customer project. Every byte
in this scenario is Traigent-authored synthetic content distributed under
Apache-2.0. The company ("Larkspur Payroll"), the ticketing tools, and every
product the tickets mention as an integration are invented for this scenario.

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

The catalog declares 96 unique labeled tickets: 80 tuning and 16 holdout, with
24 rows in each of four difficulty strata, and it lists the 18 distinct label
strings the rows carry with the number of rows carrying each. `scenario.py
check` derives those counts from the JSONL bytes and compares them with the
manifest; it also checks that the calibration JSON contains the declared three
cases. It does not import or execute the agent or evaluator to do so, and so it
does not establish which of those 18 spellings the evaluator scores alike --
the catalog makes no claim about that.

## The six queues

The desk routes every ticket to exactly one queue:

| Queue id | What belongs there |
|---|---|
| `billing` | Invoices, charges, seat counts, plan changes, refunds and credits. |
| `access-and-login` | Sign-in, password reset, MFA, SSO redirects, invitations, roles and permissions, locked accounts. |
| `integrations` | Any connection to another system: an accounting sync, an HR or timesheet feed, a bank file connector, a key, a mapping table, a webhook. |
| `data-export` | A report, download or generated file that is wrong, empty, missing a column or unavailable. |
| `outage` | The service failing for everyone, or a platform component down for all users. |
| `feature-request` | A wish for a capability the product does not have. |

The boundaries that matter most: a file the customer downloads and handles by
hand is `data-export`, while the same file pushed through a connector is
`integrations`; a fault that affects one person or one role is
`access-and-login`, while the same symptom for every user is `outage`; and an
unsupported capability is `feature-request` even when the ticket calls it a
bug.

## Reading `dataset.jsonl`

Each of the 96 lines is one JSON object with three keys - `input`, `output`,
and `metadata`. The equivalent object below is formatted across several lines
for readability; the JSONL file stores it on one physical line:

```json
{
  "input": "Every page in the app returns a 503 for all of our admins right now.",
  "output": "Outage",
  "metadata": { "difficulty": "easy", "split": "tuning", "provenance": "real" }
}
```

- `input` - the ticket text the agent routes.
- `output` - the expected queue, written as one of 18 **surface labels**. The
  desk's history spans three fictional ticketing tools, and each spells the
  queues its own way. These spellings mean the same queue:

  | Queue | Current desk tool | Older tracker | Legacy short code |
  |---|---|---|---|
  | `billing` | `Billing` | `billing-payments` | `BILL` |
  | `access-and-login` | `Access & Login` | `access` | `ACC` |
  | `integrations` | `Integrations` | `integrations-api` | `INTG` |
  | `data-export` | `Data Export` | `data-export` | `EXPT` |
  | `outage` | `Outage` | `outage-incident` | `OUT` |
  | `feature-request` | `Feature Request` | `feature-request` | `FEAT` |

  The shipped `evaluator.py` resolves both sides through its `QUEUE_IDS` table
  before comparing, so `Billing`, `billing-payments` and `BILL` all count as
  the same queue -- that is a statement about what that file does when it
  runs, and you can read its table directly. The catalog does not restate it:
  `check` never imports or executes a scenario file, so it cannot establish
  what an evaluator distinguishes, and a claim it cannot check is one it does
  not make. What the catalog does record, and verify against the shipped rows,
  is `label_shape.label_counts` -- every distinct label string with the number
  of rows carrying it.
- `metadata.split` - `tuning` (80 rows) or `holdout` (16 rows), four holdout
  rows in each difficulty stratum. Holdout rows are reserved for checking a
  winner outside the tuning data.
- `metadata.difficulty` - `easy`, `medium`, `hard`, or `very-hard`, 24 rows
  each, four per queue in each stratum. The rubric is below.
- `metadata.provenance` - always `real` here, and this is the one field that
  means less than it looks: it is **in-world scorer metadata** - what the
  fictional customer declares about their rows when the guide scores readiness.
  It does not describe where these repository bytes came from. Every byte in
  this scenario is Traigent-authored synthetic content (`content.origin` in
  `scenario.json`).

`scenario.py check 47` re-derives every one of these counts from the JSONL
bytes and fails if they drift from the manifest.

## Difficulty rubric

Every row was graded against this rubric, and the same rubric applies to any
row added later:

- **easy** - one obvious signal. The ticket names the problem class in plain
  words and nothing in it points at another queue.
- **medium** - two plausible queues, one decisive detail. The ticket mentions
  something from a second queue (a login, an invoice, a connector) but one
  detail settles it: a permission message routes to access, "for everyone"
  routes to outage, a mapping table routes to integrations.
- **hard** - the surface words point at the wrong queue. The ticket leads with
  vocabulary from one queue ("export", "outage", "password reset", "feature
  request") and describes a fault that belongs to another.
- **very-hard** - a multi-issue ticket. The ticket raises two or more items
  from different queues, and the label follows the precedence rule below.

## Precedence rule for multi-issue tickets

When one ticket raises more than one open issue, it goes to the
highest-precedence queue among them, in this order:

1. `outage`
2. `access-and-login`
3. `billing`
4. `integrations`
5. `data-export`
6. `feature-request`

Only open issues count. Something the ticket describes as already resolved,
already being handled, or needing no action is context rather than an issue.
A feature request therefore wins only when every other item in the ticket is
context. The rule follows the desk's own reasoning: an outage blocks everyone,
a locked-out customer cannot act on anything else, money in motion has a
deadline, a broken connection stops a feed, a wrong report can be re-run, and
a wish never outranks a fault. The agent's `precedence` prompt style states the
same rule to the model; the `plain` and `rules` styles do not.

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
