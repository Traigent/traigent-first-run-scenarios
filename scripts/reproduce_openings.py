# SPDX-License-Identifier: Apache-2.0
"""Re-measure every published opening by replaying the commands recorded beside it.

This reads. It never writes into the repository, and it has no mode that does: a
checker that cannot write cannot overwrite the evidence it exists to protect.
When a contract needs replacing, a person runs the guide and edits the file, and
this says whether the result agrees.

Each scenario's `verifier/measurement/invocation.json` records the preflight,
calibration and readiness commands its opening was measured with. They are
replayed as recorded -- every flag, in order -- with only the placeholders bound:
$PYTHON to this interpreter, $GUIDE to the checkout, $PROJECT to a scratch copy
of the scenario's `project/`, $SCENARIO to the scenario's directory here,
$MEASURE to a scratch directory, and $ROW_REVIEW to the committed read that goes
with the contract being checked. A step writes its JSON to the $MEASURE file the
later steps name for it. Replaying the record rather than rebuilding the commands
is the point: a flag the record carries and this script forgot would otherwise
produce a disagreement that is this script's own mistake. A step the record says
refused (`refusals`, the step and the message it refuses with) must refuse with
that message again; nothing else counts as the same refusal.

Replaying a record runs the scenario's own code: calibration calls its
evaluator. So nothing is run before the record has passed the validator
`scenario.py check` uses (`read_invocation`), which allows the guide's three
first-run scripts and only the flags each is replayed with, and before the
scenario has been walked for links, which would let the project copy reach a
file outside the scenario. Each step runs with an empty home of its own, as
the leader of a process group of its own, under a deadline derived from the
guide's own calibration budget; when it ends, finished or past that deadline,
every process still in its group is killed. A process that leaves the group
(`setsid()`) is not reached. None of that is a sandbox -- the evaluator runs as
the user who runs this -- which is why a contribution is replayed with trunk's
copy of this script and `scenario.py`, and why CI replays with no secrets
(CONTRIBUTING.md, "Replaying a contribution").

A scenario whose opening turns on what a reader of its answers found declares a
second contract for a read that found nothing wrong (`expected_route.
read_dependent` in its manifest). Both are measured, each with its own read:
`row-review.json` for the published contract and `row-review-sound-read.json`
for the other.

Every field a contract publishes is compared: the readiness schema version it
was measured at, band, status, recommended action, every cap's condition,
ceiling, blocks and asks, and the displayed overall and per-pillar scores and
confidences.

What it needs: a clean `traigent-first-run` checkout on the revision every
`invocation.json` names, passed as $GUIDE.

    GUIDE=~/code/traigent-first-run python3 scripts/reproduce_openings.py

Exit 0 when every published contract reproduces, 1 when any disagrees, 2 when a
contract could not be measured at all -- including when the checkout cannot be
trusted to be the recorded revision. A disagreement outranks a contract that
could not be read, since it is the more specific finding; both are printed.

`--against-head` replays against a checkout on any revision -- the head of the
guide's default branch, weekly in `.github/workflows/guide-drift.yml`. What the
guide did is labelled MATCH or DRIFT: a measurement that differs, or a step
that ran and produced none. What stopped before the guide ran -- a refused
record, a link, a missing read -- stays COULD NOT READ, as against the pin.
Exit 1 on any drift, else 2 on anything unread. Drift against a moved guide is
a warning that the guide has moved, not a defect in a scenario; the pinned
replay is what vouches for the scenarios.
"""

import argparse
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, NoReturn

REPO = Path(__file__).resolve().parent.parent
# The record validator lives with the rest of the bank's checks, so the runner
# and `scenario.py check` cannot disagree about what a record may run.
sys.path.insert(0, str(REPO))
from scenario import (  # noqa: E402
    CALIBRATION_TIMEOUT_CEILING_SECONDS,
    INVOCATION_RECORD,
    REPLAY_STEPS,
    ScenarioError,
    read_invocation,
    regular_files_without_links,
)

PLACEHOLDER = re.compile(r"\$[A-Z_]+")
SOUND_READ_SUFFIX = "-sound-read"

# How long each replayed step may run before it is stopped, whole. Calibration
# is the one step that runs the scenario's own code, and the guide bounds it
# itself: CALIBRATION_TIMEOUT_CEILING_SECONDS is the longest the guide's
# calibrate_evaluator.py budgets a calibration for (line 103 at d07b62cd), and
# `check` refuses a recorded `--timeout` above it. The margin covers starting
# the interpreter and writing the record after the guide's own deadline fires.
# Preflight and readiness only read files -- preflight.py's docstring: it
# "never imports user modules, executes an agent or evaluator" -- and the guide
# gives them no budget, so they get the margin alone; the whole bank replays in
# well under a minute.
REPLAY_MARGIN_SECONDS = 60
STEP_TIMEOUT_SECONDS = {
    "preflight": REPLAY_MARGIN_SECONDS,
    "calibration": CALIBRATION_TIMEOUT_CEILING_SECONDS + REPLAY_MARGIN_SECONDS,
    "readiness": REPLAY_MARGIN_SECONDS,
}


def fail(reason: str) -> NoReturn:
    """Could not run at all: exits 2, never a traceback."""
    print(f"cannot reproduce: {reason}", file=sys.stderr)
    raise SystemExit(2)


class CouldNotMeasure(Exception):
    """One contract could not be measured; the others still are."""


class StepFailed(CouldNotMeasure):
    """The guide ran and did not produce a measurement.

    Everything checked before the first step runs -- the record, links, the
    committed read, the placeholders -- is about the scenario. This is about the
    guide, so against a moved guide it is drift rather than an unread record.
    """


if set(STEP_TIMEOUT_SECONDS) != set(REPLAY_STEPS):
    fail("every replayable step needs a deadline in STEP_TIMEOUT_SECONDS")

_parser = argparse.ArgumentParser(
    description="Re-measure every published opening against a guide checkout."
)
_parser.add_argument(
    "--against-head",
    action="store_true",
    help=(
        "replay against a guide checkout on any revision, such as the head of "
        "its default branch, and report what the guide measured as MATCH or "
        "DRIFT"
    ),
)
AGAINST_HEAD: bool = _parser.parse_args().against_head

_root = os.environ.get("GUIDE")
if not _root:
    fail("set GUIDE to a traigent-first-run checkout")
GUIDE = Path(_root).expanduser().resolve()
if not (GUIDE / "skills/traigent-first-run/scripts/readiness.py").is_file():
    fail(f"no skills/traigent-first-run/scripts/readiness.py under {GUIDE}")

# Every command also gets a HOME of its own; see `run`.
ENV = {
    "LANG": "C.UTF-8",
    "LC_ALL": "C.UTF-8",
    "PATH": os.environ.get("PATH", ""),
    "PYTHONDONTWRITEBYTECODE": "1",
    "PYTHONHASHSEED": "0",
    "PYTHONNOUSERSITE": "1",
}


def run(cmd: list[str], cwd: Path, timeout: float) -> subprocess.CompletedProcess[str]:
    """Run one command in a fresh empty home, and leave nothing of it running.

    The command leads a session, and so a process group, of its own. When it
    ends -- finished, or past the deadline -- every process still in that group
    is killed, so a child a step started, detached or not, does not outlive it:
    calibration runs the scorer in children. A process that calls `setsid()`
    leaves the group and is not reached; that residual is stated in
    CONTRIBUTING.md. The home is removed afterwards. Raises
    `subprocess.TimeoutExpired`.
    """
    with tempfile.TemporaryDirectory(
        prefix="replay-home-", ignore_cleanup_errors=True
    ) as home:
        with subprocess.Popen(
            cmd,
            cwd=cwd,
            env={**ENV, "HOME": home},
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        ) as process:
            try:
                stdout, stderr = process.communicate(timeout=timeout)
            finally:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()
    return subprocess.CompletedProcess(cmd, process.returncode, stdout, stderr)


def git(*arguments: str) -> subprocess.CompletedProcess[str]:
    """Ask git about $GUIDE; a git that hangs or is missing cannot run at all."""
    try:
        return run(["git", "-C", str(GUIDE), *arguments], REPO, REPLAY_MARGIN_SECONDS)
    except subprocess.TimeoutExpired:
        fail(
            f"git {arguments[0]} in {GUIDE} did not answer within "
            f"{REPLAY_MARGIN_SECONDS} seconds"
        )
    except OSError as error:
        fail(f"cannot run git for {GUIDE}: {error}")


def guide_revision() -> str:
    """The revision $GUIDE sits on, refusing a checkout that differs from it."""
    head = git("rev-parse", "HEAD")
    if head.returncode != 0:
        fail(f"{GUIDE} is not a git checkout, so its revision cannot be established")
    status = git("status", "--porcelain")
    if status.returncode != 0:
        fail(f"cannot read the working-tree state of {GUIDE}")
    if status.stdout.strip():
        fail(
            f"{GUIDE} has local changes, so it is not the revision it names: "
            + "; ".join(status.stdout.strip().splitlines()[:5])
        )
    return head.stdout.strip()


def last_line(text: str) -> str:
    lines = text.strip().splitlines()
    return lines[-1][:120] if lines else "(no output)"


def replay(
    invocation: dict[str, Any], scenario: Path, row_review: Path | None
) -> dict[str, Any]:
    """Run the recorded steps once and return the readiness JSON.

    The record has already passed `read_invocation`, so every step is a guide
    script with allowed flags, and every output a later step reads is written
    by an earlier one that the record does not name as refusing.
    """
    try:
        regular_files_without_links(scenario, scenario.name)
    except ScenarioError as refusal:
        raise CouldNotMeasure(str(refusal)) from refusal
    work = Path(tempfile.mkdtemp())
    try:
        project = work / "project"
        measure = work / "measure"
        shutil.copytree(scenario / "project", project)
        measure.mkdir()
        bound = {
            "$PYTHON": sys.executable,
            "$GUIDE": str(GUIDE),
            "$PROJECT": str(project),
            "$SCENARIO": str(scenario),
            "$MEASURE": str(measure),
        }
        if row_review is not None:
            bound["$ROW_REVIEW"] = str(row_review)
        refusals = invocation.get("refusals", {})
        # Every command is bound before any runs, so a record that cannot be
        # bound is refused before the guide has done anything.
        commands: dict[str, list[str]] = {}
        for name, recorded in invocation["steps"].items():
            cmd: list[str] = []
            for argument in recorded:
                for token in PLACEHOLDER.findall(argument):
                    if token not in bound:
                        raise CouldNotMeasure(f"step {name!r} uses unbound {token}")
                for token, value in bound.items():
                    argument = argument.replace(token, value)
                cmd.append(argument)
            commands[name] = cmd
        for name, cmd in commands.items():
            budget = STEP_TIMEOUT_SECONDS[name]
            try:
                done = run(cmd, project, budget)
            except subprocess.TimeoutExpired as expired:
                raise StepFailed(
                    f"step {name!r} was still running after its {budget}-second "
                    "replay budget and was stopped"
                ) from expired
            wrote = bool(done.stdout.strip())
            # A non-zero exit with a payload is a step reporting findings. A step
            # recorded as refusing is one nothing reads -- the readiness command
            # then carries that refusal as a flag -- and the record names the
            # refusal, so the replay must refuse the same way. Any other
            # failure, a crash included, is not that refusal.
            if name in refusals:
                if wrote or done.returncode == 0 or refusals[name] not in done.stderr:
                    raise StepFailed(
                        f"{name} was recorded refusing with {refusals[name]!r} and "
                        f"now does not (rc={done.returncode}): {last_line(done.stderr)}"
                    )
                continue
            if not wrote:
                raise StepFailed(
                    f"{name} wrote nothing (rc={done.returncode}): "
                    + last_line(done.stderr)
                )
            (measure / REPLAY_STEPS[name].output).write_text(done.stdout)
        try:
            result: dict[str, Any] = json.loads(
                (measure / REPLAY_STEPS["readiness"].output).read_text()
            )
            measured_fields(result)
        except (AttributeError, KeyError, TypeError, ValueError) as unreadable:
            raise StepFailed(
                f"readiness wrote no readable result: {type(unreadable).__name__}: "
                f"{unreadable}"
            ) from unreadable
        return result
    finally:
        shutil.rmtree(work, ignore_errors=True)


def cap_tuples(caps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Each cap as the four fields readiness routes it on, in condition order."""
    return sorted(
        (
            {field: cap[field] for field in ("condition", "ceiling", "blocks", "asks")}
            for cap in caps
        ),
        key=lambda cap: str(cap["condition"]),
    )


def published_fields(contract: dict[str, Any]) -> dict[str, Any]:
    display = contract["display"]
    return {
        "readiness_schema_version": contract["readiness_schema_version"],
        "band": contract["band"],
        "status": contract["status"],
        "recommended_action": contract["recommended_action"],
        "caps": cap_tuples(contract["caps"]),
        "overall": display["overall"],
        "pillars": display["pillars"],
    }


def measured_fields(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "readiness_schema_version": result["schema_version"],
        "band": result["band"],
        "status": result["status"],
        "recommended_action": result["recommended_action"],
        "caps": cap_tuples(result["caps"]),
        "overall": {"score": result["overall"], "confidence": result["confidence"]},
        "pillars": {
            pillar["name"]: {
                "score": pillar["score"],
                "confidence": pillar["confidence"],
            }
            for pillar in result["pillars"]
        },
    }


def contracts(scenario: Path) -> list[tuple[str, Path, Path | None]]:
    """(label, contract, the read it was measured with) for each contract."""
    verifier = scenario / "verifier"
    review = verifier / "measurement" / "row-review.json"
    found = [
        (
            scenario.name,
            verifier / "expected-opening.json",
            review if review.is_file() else None,
        )
    ]
    route = json.loads((scenario / "scenario.json").read_text())["catalog"][
        "expected_route"
    ]
    dependent = route.get("read_dependent")
    if dependent is not None:
        contract = scenario / dependent["sound_read_contract"]
        found.append(
            (
                f"{scenario.name} (sound read)",
                contract,
                verifier / "measurement" / f"row-review{SOUND_READ_SUFFIX}.json",
            )
        )
    return found


AT = guide_revision()
pins: set[str] = set()
rows: list[tuple[str, str, str]] = []
for manifest in sorted(REPO.glob("scenarios/*/scenario.json")):
    scenario = manifest.parent
    for label, contract_path, row_review in contracts(scenario):
        try:
            try:
                invocation = read_invocation(
                    scenario / "verifier" / INVOCATION_RECORD,
                    f"scenario {scenario.name!r}",
                )
            except ScenarioError as refusal:
                raise CouldNotMeasure(str(refusal)) from refusal
            pins.add(invocation["guide_revision"])
            if invocation["guide_revision"] != AT and not AGAINST_HEAD:
                raise CouldNotMeasure(
                    f"measured at {invocation['guide_revision'][:8]}, "
                    f"GUIDE is on {AT[:8]}"
                )
            if row_review is not None and not row_review.is_file():
                raise CouldNotMeasure(f"no committed read at {row_review.name}")
            got = measured_fields(replay(invocation, scenario, row_review))
            want = published_fields(json.loads(contract_path.read_text()))
            differing = [key for key in want if got[key] != want[key]]
            detail = "; ".join(
                f"{key} got {got[key]!r} published {want[key]!r}" for key in differing
            )
            rows.append((label, "DIFFERS" if differing else "MATCH", detail))
        except StepFailed as reason:
            rows.append(
                (label, "DRIFT" if AGAINST_HEAD else "COULD NOT READ", str(reason))
            )
        except CouldNotMeasure as reason:
            rows.append((label, "COULD NOT READ", str(reason)))
        except (AttributeError, OSError, KeyError, TypeError, ValueError) as failure:
            rows.append(
                (label, "COULD NOT READ", f"{type(failure).__name__}: {failure}")
            )

if not rows:
    fail("no scenario was found, so nothing was checked")
if AGAINST_HEAD:
    # Against a moving guide, what the guide did can drift: a measurement that
    # differs, or a step that ran and produced none. What stopped before the
    # guide ran -- a refused record, a link, a missing read -- is about the
    # scenario, and stays COULD NOT READ as it does against the pin.
    rows = [
        (label, "DRIFT" if verdict == "DIFFERS" else verdict, detail)
        for label, verdict, detail in rows
    ]
    pinned = ", ".join(pin[:8] for pin in sorted(pins)) or "no record read"
    print(f"  guide {AT}, clean checkout; the scenarios are pinned at {pinned}\n")
else:
    print(f"  guide {AT[:8]}, clean checkout\n")
width = max(len(row[0]) for row in rows)
for label, verdict, detail in rows:
    print(f"  {label:{width}}  {verdict:14} {detail}")
matched = sum(1 for row in rows if row[1] == "MATCH")
print(f"\n  matched: {matched} of {len(rows)} contracts")
differs = sum(1 for row in rows if row[1] in ("DIFFERS", "DRIFT"))
unread = len(rows) - matched - differs
if AGAINST_HEAD and differs:
    if any(pin != AT for pin in pins):
        print(
            f"  drifted: {differs} of {len(rows)} contracts at guide {AT[:8]}. This "
            "is a warning that the guide has moved since the scenarios were "
            "measured, not a defect in a scenario: the pinned replay in CI is what "
            "vouches for them. Re-measure at the new revision to move the pin.",
            file=sys.stderr,
        )
    else:
        print(
            f"  drifted: {differs} of {len(rows)} contracts at guide {AT[:8]}, "
            "which is the pinned revision, so the guide has not moved: the "
            "pinned replay fails the same way.",
            file=sys.stderr,
        )
if unread:
    print(f"  could not measure: {unread}", file=sys.stderr)
if differs:
    raise SystemExit(1)
if unread:
    raise SystemExit(2)
