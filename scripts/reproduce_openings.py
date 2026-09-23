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

A scenario whose opening turns on what a reader of its answers found declares a
second contract for a read that found nothing wrong (`expected_route.
read_dependent` in its manifest). Both are measured, each with its own read:
`row-review.json` for the published contract and `row-review-sound-read.json`
for the other.

Every field a contract publishes is compared: band, status, recommended action,
caps, and the displayed overall and per-pillar scores and confidences.

What it needs: a clean `traigent-first-run` checkout on the revision every
`invocation.json` names, passed as $GUIDE.

    GUIDE=~/code/traigent-first-run python3 scripts/reproduce_openings.py

Exit 0 when every published contract reproduces, 1 when any disagrees, 2 when a
contract could not be measured at all -- including when the checkout cannot be
trusted to be the recorded revision. A disagreement outranks a contract that
could not be read, since it is the more specific finding; both are printed.
"""

import atexit
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, NoReturn

REPO = Path(__file__).resolve().parent.parent

# Where each recorded step writes. The later steps name these files through
# $MEASURE, so a step is only replayable if its output has a name here.
STEP_OUTPUTS = {
    "preflight": "02-preflight.json",
    "calibration": "03-calibration.json",
    "readiness": "05-readiness.json",
}
PLACEHOLDER = re.compile(r"\$[A-Z_]+")
SOUND_READ_SUFFIX = "-sound-read"


def fail(reason: str) -> NoReturn:
    """Could not run at all: exits 2, never a traceback."""
    print(f"cannot reproduce: {reason}", file=sys.stderr)
    raise SystemExit(2)


class CouldNotMeasure(Exception):
    """One contract could not be measured; the others still are."""


_root = os.environ.get("GUIDE")
if not _root:
    fail("set GUIDE to a traigent-first-run checkout")
GUIDE = Path(_root).expanduser().resolve()
if not (GUIDE / "skills/traigent-first-run/scripts/readiness.py").is_file():
    fail(f"no skills/traigent-first-run/scripts/readiness.py under {GUIDE}")

_home = tempfile.mkdtemp()
atexit.register(shutil.rmtree, _home, True)
ENV = {
    "HOME": _home,
    "LANG": "C.UTF-8",
    "LC_ALL": "C.UTF-8",
    "PATH": os.environ.get("PATH", ""),
    "PYTHONDONTWRITEBYTECODE": "1",
    "PYTHONHASHSEED": "0",
    "PYTHONNOUSERSITE": "1",
}


def run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=cwd, env=ENV, capture_output=True, text=True)


def guide_revision() -> str:
    """The revision $GUIDE sits on, refusing a checkout that differs from it."""
    head = run(["git", "-C", str(GUIDE), "rev-parse", "HEAD"], REPO)
    if head.returncode != 0:
        fail(f"{GUIDE} is not a git checkout, so its revision cannot be established")
    status = run(["git", "-C", str(GUIDE), "status", "--porcelain"], REPO)
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
    """Run the recorded steps once and return the readiness JSON."""
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
        written: set[str] = set()
        steps = invocation.get("steps")
        if not isinstance(steps, dict) or "readiness" not in steps:
            raise CouldNotMeasure("invocation.json records no readiness step")
        refusals = invocation.get("refusals", {})
        if not isinstance(refusals, dict) or not set(refusals) <= set(steps):
            raise CouldNotMeasure(
                "invocation.json names a refusal for no recorded step"
            )
        read_later = {
            STEP_OUTPUTS[name]: any(
                f"$MEASURE/{STEP_OUTPUTS[name]}" in argument
                for later in list(steps.values())[index + 1 :]
                for argument in later
            )
            for index, name in enumerate(steps)
            if name in STEP_OUTPUTS
        }
        for name, recorded in steps.items():
            if name not in STEP_OUTPUTS:
                raise CouldNotMeasure(f"step {name!r} has no known output file")
            cmd: list[str] = []
            for argument in recorded:
                for token in PLACEHOLDER.findall(argument):
                    if token not in bound:
                        raise CouldNotMeasure(f"step {name!r} uses unbound {token}")
                for token, value in bound.items():
                    argument = argument.replace(token, value)
                if argument.startswith(str(measure) + "/"):
                    needed = argument[len(str(measure)) + 1 :]
                    if needed not in written:
                        raise CouldNotMeasure(
                            f"step {name!r} reads $MEASURE/{needed}, "
                            "which no earlier step writes"
                        )
                cmd.append(argument)
            done = run(cmd, project)
            output = STEP_OUTPUTS[name]
            wrote = bool(done.stdout.strip())
            # A non-zero exit with a payload is a step reporting findings. A step
            # nothing reads is recorded because it refused -- the readiness
            # command then carries that refusal as a flag -- and the record names
            # the refusal, so the replay must refuse the same way. Any other
            # failure, a crash included, is not that refusal.
            if name in refusals:
                if read_later[output]:
                    raise CouldNotMeasure(
                        f"{name} is recorded as refusing, yet a later step reads its "
                        "output"
                    )
                if wrote or done.returncode == 0 or refusals[name] not in done.stderr:
                    raise CouldNotMeasure(
                        f"{name} was recorded refusing with {refusals[name]!r} and "
                        f"now does not (rc={done.returncode}): {last_line(done.stderr)}"
                    )
                continue
            if name != "readiness" and not read_later[output]:
                raise CouldNotMeasure(
                    f"no recorded step reads what {name} writes, and the record "
                    "names no refusal for it"
                )
            if not wrote:
                raise CouldNotMeasure(
                    f"{name} wrote nothing (rc={done.returncode}): "
                    + last_line(done.stderr)
                )
            (measure / output).write_text(done.stdout)
            written.add(output)
        result: dict[str, Any] = json.loads(
            (measure / STEP_OUTPUTS["readiness"]).read_text()
        )
        return result
    finally:
        shutil.rmtree(work, ignore_errors=True)


def published_fields(contract: dict[str, Any]) -> dict[str, Any]:
    display = contract["display"]
    return {
        "band": contract["band"],
        "status": contract["status"],
        "recommended_action": contract["recommended_action"],
        "caps": sorted(contract["caps"]),
        "overall": display["overall"],
        "pillars": display["pillars"],
    }


def measured_fields(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "band": result["band"],
        "status": result["status"],
        "recommended_action": result["recommended_action"],
        "caps": sorted(cap["condition"] for cap in result["caps"]),
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
rows: list[tuple[str, str, str]] = []
for manifest in sorted(REPO.glob("scenarios/*/scenario.json")):
    scenario = manifest.parent
    for label, contract_path, row_review in contracts(scenario):
        try:
            invocation = json.loads(
                (scenario / "verifier/measurement/invocation.json").read_text()
            )
            if not isinstance(invocation, dict):
                raise CouldNotMeasure("invocation.json is not a JSON object")
            if invocation.get("guide_revision") != AT:
                raise CouldNotMeasure(
                    f"measured at {str(invocation.get('guide_revision'))[:8]}, "
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
        except CouldNotMeasure as reason:
            rows.append((label, "COULD NOT READ", str(reason)))
        except (AttributeError, OSError, KeyError, TypeError, ValueError) as failure:
            rows.append(
                (label, "COULD NOT READ", f"{type(failure).__name__}: {failure}")
            )

if not rows:
    fail("no scenario was found, so nothing was checked")
print(f"  guide {AT[:8]}, clean checkout\n")
width = max(len(row[0]) for row in rows)
for label, verdict, detail in rows:
    print(f"  {label:{width}}  {verdict:14} {detail}")
matched = sum(1 for row in rows if row[1] == "MATCH")
differs = sum(1 for row in rows if row[1] == "DIFFERS")
unread = len(rows) - matched - differs
print(f"\n  matched: {matched} of {len(rows)} contracts")
if differs:
    raise SystemExit(1)
if unread:
    print(f"  could not measure: {unread}", file=sys.stderr)
    raise SystemExit(2)
