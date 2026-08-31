---
name: traigent-first-run-scenarios
description: Inspect, prepare, and verify Traigent's public first-run scenarios. Use when asked to list or explain a simulated starting point, validate the public catalog, prepare a context-isolated Phase A worker project, or compare captured opening JSON with a published scenario contract. Do not use it as evidence of a live optimization.
---

# Traigent First Run Scenarios

Use this skill from the root of the public scenario repository. Act as the
captain, not as the worker whose result will be evaluated.

## Choose the requested layer

For catalog inspection:

```bash
python scenario.py list
python scenario.py show CASE
python scenario.py check CASE
python scenario.py check
```

`check` also validates the expected opening's strict structure and value ranges.
Report a catalog check as package validation only. It runs no worker and proves
no onboarding behavior.

For a Phase A opening run, require:

- a listed scenario slug or legacy identifier;
- a committed scenario-repository `HEAD` with clean selected files;
- a reviewed local `traigent-first-run` checkout;
- a new output path whose parent exists but which does not itself exist; and
- an approved disposable execution environment.

Then run:

```bash
python scenario.py prepare CASE --guide-src PATH --output PATH
```

Preparation requires committed `HEAD` revisions for both checkouts, refuses
tracked changes in the selected scenario manifest, selected project, and
allowlisted guide paths, and copies only tracked selected-project and
allowlisted guide files into `PATH/customer-project/`. It keeps the verifier and
expected result out of that directory and records both revisions and
deterministic captain evidence in `PATH/run.json`. It invokes local Git
read-only and executes no scenario or guide code.

## Dispatch one fresh worker

Start a new agent context with its working directory set to
`PATH/customer-project`. Give it only the exact handoff printed by `prepare`:

```text
Help me run my first Traigent optimization.
Use the Traigent first-run checkout at ./traigent-first-run and follow ./traigent-first-run/GUIDE.md.
```

Do not reveal the case identifier, source scenario directory, manifest,
verifier, expected band, prior results, or `run.json`. Do not add test-specific
coaching. If no facility for a genuinely fresh worker is available, return the
prepared path and handoff to the user instead of running as the worker in this
already informed context.

Stop the Phase A run at the first question or decision that belongs to the
human. Do not provide credentials, approve paid or remote product/provider
calls, expose customer data, mutate production, establish a baseline, or run an
optimization. A local deterministic evaluator calibration is allowed only when
the first-run guide's safety gate admits that exact path.

The scenario is public. The worker receives the project's evaluator, but the
captain keeps the expected opening, semantic verifier, and earlier results out
of the supplied context. This makes the run expected-result-blinded, but not
resistant to deliberate public lookup or broader machine access. Do not call it
a secret, held-out, tamper-proof, or operating-system-contained benchmark.

## Verify captured opening JSON

Keep the exact machine-readable opening result outside the worker project and
run:

```bash
python scenario.py verify CASE --run-record RUN_JSON --result FILE
```

Verification binds the contract to the scenario Git revision in `run.json`,
then compares `band`, `status`, `recommended_action`, and `caps`. It never
executes verifier code. Report every mismatch and retain the complete
output and final status.

A successful comparison may be called **Verified run evidence** only when the
report also identifies both repository revisions, `run.json`, worker and
environment, exact handoff, captured result, and stop point. Otherwise use
**Expected scenario contract**. Anything beyond the opening is **Not
demonstrated**.

Phase B is a separate live exercise and requires explicit human approval for
all applicable credential, account, network, installation, data-egress, cost,
mutation, and optimization boundaries. Never upgrade a Phase A match into a
Phase B claim.

## Real-project handoff

When the user wants Traigent on their own project rather than a public scenario,
open the coding agent in that project and give it exactly:

```text
Help me run my first Traigent optimization.
Clone https://github.com/Traigent/traigent-first-run and follow GUIDE.md.
```

That journey follows the real project's human decisions and approvals. Do not
grade it with a scenario verifier.

## Read before customer use

- Workflow: [GUIDE.md](../../GUIDE.md)
- Customer-machine controls: [docs/customer-pc-runbook.md](../../docs/customer-pc-runbook.md)
- Claims and isolation model: [docs/methodology.md](../../docs/methodology.md)
- Contribution contract: [CONTRIBUTING.md](../../CONTRIBUTING.md)
- Private security reporting: [SECURITY.md](../../SECURITY.md)
