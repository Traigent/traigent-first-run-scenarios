# Security Policy

## Report vulnerabilities privately

Do not disclose a suspected vulnerability, exploit, credential, or customer
detail in a public issue or pull request.

Use this repository's **Security** tab to submit a private vulnerability
report. If private reporting is unavailable, contact Traigent through your
established private support channel and include a link to this repository.
Provide only the minimum reproduction material needed, with all secrets and
customer data removed.

## Understand the execution boundary

The catalog commands treat scenario and verifier files as data:

```bash
python scenario.py list
python scenario.py show CASE
python scenario.py check CASE
python scenario.py check
python scenario.py prepare CASE --guide-src PATH --output PATH
python scenario.py verify CASE --run-record RUN_JSON --result FILE
```

They do not import scenario or verifier modules. `check` also parses the public
expected opening contract strictly and validates its structure and numeric
ranges. `prepare` invokes local Git with fixed arguments to read both committed
revisions, their immutable trees, stage-zero index entries, and recorded blobs.
It requires the index entries to match the recorded commits, copies those blobs,
and rechecks source revisions, indexes, and tracked cleanliness before writing a
deterministic captain record. It does not invoke a shell, worker, guide script,
scenario script, or network service. `verify` validates that record against the
recorded Git tree, parses strict JSON, and compares four fields without
executing verifier code.

Preparation rejects an existing output path, symbolic links, special or
unreadable input entries, an output nested inside either source, incomplete
guide or scenario content, either source without a committed `HEAD`, tracked
changes in the selected scenario manifest, project, or verifier, and tracked
changes in allowlisted guide paths. It copies only tracked selected-project and
allowlisted guide files, excluding untracked and ignored material. It records a
separate hash inventory for the captain-only manifest and verifier. Symbolic-link entries,
Git links, unmerged index entries, and unsupported index modes are rejected.
Executable status comes from the committed Git index mode rather than mutable
host permissions. If preparation fails after creating its output, it removes
only that newly created output.

These safeguards make copying and comparison fail closed. They do not make the
prepared directory an operating-system sandbox.

## Run a worker only in an approved boundary

The prepared project contains Python source and a local copy of the public
first-run guide. Treat all worker-visible files as untrusted input even though
they are published here.

- Use a disposable directory, container, virtual machine, or separately
  restricted account appropriate to the customer's policy.
- Keep production repositories, unrelated files, credentials, and private
  datasets outside the worker's accessible scope.
- Start a fresh worker with only `customer-project/` and the exact handoff
  printed by `prepare`.
- Keep `run.json`, `scenario.json`, `verifier/`, expected results, and previous
  outputs outside the worker's supplied context.
- Do not provide Traigent or provider credentials during Phase A.
- Do not approve paid calls, private-data egress, production writes, or a live
  optimization during Phase A.
- Permit local evaluator calibration only when the first-run guide has applied
  its declared safety gate to the exact evaluator path. Do not generalize that
  approval to arbitrary scenario code or subprocesses.
- Stop at the first question or decision that belongs to the human.

A remote coding-agent service is a separate data boundary. Obtain customer
approval for that service and limit the files and conversation it receives.

## Context isolation is not containment

The scenario and verifier are public. The normal protocol keeps the
captain-side verifier, expected opening, and prior result out of the worker's
assigned project and prompt, so the run is expected-result-blinded within its
supplied context. The worker still receives the project's evaluator because it
is part of the starting state. A worker running as the same operating-system
user may still search elsewhere on the machine, and a public case may already
be known to it.

Do not describe this protocol as tamper-proof, secret, adversarially held out,
or operating-system containment. Deliberately looking up the verifier or prior
result invalidates the run.

## Phase B requires separate approval

Phase B exercises a live value path. Before it begins, an authorized person
must approve every applicable credential, account, network, installation,
data-egress, provider, cost, mutation, and optimization boundary. An approval
for Phase A is not approval for Phase B. See
[docs/customer-pc-runbook.md](docs/customer-pc-runbook.md).

## Sensitive content in contributions

Never commit:

- API keys, tokens, passwords, private keys, or connection strings;
- real customer records or proprietary customer project files;
- private service names, operational details, or non-public links;
- third-party dataset content not admitted by the repository's origin and
  licensing contract; or
- Git history, deleted material, or inherited metadata from another repository.

If sensitive material is committed, stop distributing the affected revision
and report it privately. Deleting a file in a later commit does not remove it
from Git history.
