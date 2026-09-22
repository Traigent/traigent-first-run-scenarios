# SPDX-License-Identifier: Apache-2.0
"""Re-measure every published opening from the artifacts committed beside it.

This reads. It never writes into the repository, and it has no mode that does.
The sibling builder's sweep carries a `--publish` flag and has twice destroyed
the evidence it exists to protect; a checker that cannot write cannot do that,
which is the whole reason this is a verifier rather than a publisher. When a
contract needs replacing, a person runs the guide and edits the file, and this
says whether the result agrees.

What it needs: a `traigent-first-run` checkout sitting on the revision each
scenario's `verifier/measurement/invocation.json` names, passed as $GUIDE. What
it uses from this repository: the manifest's declared `guide_task_kind` and
`guide_evaluator_method`, and the scenario's committed `agent-read.json` and
`row-review.json`. Nothing else, on purpose -- if it needed anything a reader
does not have, the contracts would not be re-derivable and this would be
theatre.

    GUIDE=~/code/traigent-first-run python3 scripts/reproduce_openings.py

Exit 0 when every published contract reproduces, 1 when any does not, 2 when it
could not run at all. The three are different answers and a reader acts on them
differently, so they are not collapsed.
"""

import atexit
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import NoReturn

REPO = Path(__file__).resolve().parent.parent


def fail(reason: str) -> NoReturn:
    """Could not run: a different answer from "ran and disagreed", and it exits 2.

    The three exit codes are three different answers a reader acts on
    differently, so every way of not being able to start comes through here
    rather than out of a traceback.
    """
    print(f"cannot reproduce: {reason}", file=sys.stderr)
    raise SystemExit(2)


_root = os.environ.get("GUIDE")
if not _root:
    fail("set GUIDE to a traigent-first-run checkout")
GUIDE = Path(_root).expanduser()
G = GUIDE / "skills/traigent-first-run/scripts"
if not (G / "readiness.py").is_file():
    fail(f"no readiness.py under {G}")

_home = tempfile.mkdtemp()
atexit.register(shutil.rmtree, _home, True)
ENV = {
    "HOME": _home,
    "LANG": "C.UTF-8",
    "LC_ALL": "C.UTF-8",
    "PATH": os.environ.get("PATH", ""),
    "PYTHONHASHSEED": "0",
    "PYTHONNOUSERSITE": "1",
}


def run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=cwd, env=ENV, capture_output=True, text=True)


def guide_revision() -> str:
    """The revision $GUIDE sits on. Refuses rather than guessing."""
    found = run(["git", "-C", str(GUIDE), "rev-parse", "HEAD"], REPO)
    if found.returncode != 0:
        fail(f"{GUIDE} is not a git checkout, so its revision cannot be established")
    return found.stdout.strip()


AT = guide_revision()
_declared = {
    json.loads(path.read_text(encoding="utf-8"))["guide_revision"]
    for path in REPO.glob("scenarios/*/verifier/measurement/invocation.json")
}
if not _declared:
    fail("no scenario records the revision it was measured at")
if _declared != {AT}:
    fail(
        f"GUIDE is on {AT[:8]} and these openings were measured at "
        + ", ".join(sorted(r[:8] for r in _declared))
        + "; comparing against a different revision of the guide answers a "
        "different question from the one this script asks"
    )
print(f"  guide {AT[:8]}, which is what every invocation.json records\n")

rows: list[tuple[str, str, str]] = []
for manifest in sorted(REPO.glob("scenarios/*/scenario.json")):
    slug = manifest.parent.name
    work: Path | None = None
    # One scenario that cannot be read is one row of the report, not a
    # traceback that abandons the other eleven and carries a temp path out
    # with it. The directory is removed on every path, not only the one
    # that finished.
    try:
        cat = json.loads(manifest.read_text())["catalog"]
        meas = manifest.parent / "verifier" / "measurement"
        work = Path(tempfile.mkdtemp())
        shutil.copytree(manifest.parent / "project", work / "project")
        proj = work / "project"

        ds = (cat.get("datasets") or [{}])[0]
        ev = cat["components"].get("evaluator") or {}
        ag = cat["components"].get("agent") or {}
        method = ev.get("guide_evaluator_method")
        kind = ds.get("guide_task_kind")

        pf = [
            sys.executable,
            str(G / "preflight.py"),
            "--project-root",
            str(proj),
            "--json",
        ]
        if ds.get("path"):
            pf += ["--dataset", ds["path"].split("project/", 1)[-1]]
        if ev.get("path"):
            pf += ["--evaluator", ev["path"].split("project/", 1)[-1]]
        if method:
            pf += ["--evaluator-method", method]
        p = run(pf, proj)
        # preflight signals FINDINGS with a non-zero exit and still writes its JSON.
        # A run is only failed when there is no payload to read.
        if not p.stdout.strip():
            rows.append(
                (
                    slug,
                    "preflight failed",
                    f"rc={p.returncode} "
                    + (
                        (
                            p.stderr.strip() or p.stdout.strip() or "(silent)"
                        ).splitlines()
                        or ["(silent)"]
                    )[-1][:70],
                )
            )
            continue
        (work / "pf.json").write_text(p.stdout)

        cal = None
        probes = (ev.get("calibration") or {}).get("path")
        if probes and not (ev.get("state") == "unsafe"):
            c = [
                sys.executable,
                str(G / "calibrate_evaluator.py"),
                "--scorer",
                f'{ev["path"].split("project/",1)[-1]}:score',
                "--cases",
                "@" + probes.split("project/", 1)[-1],
                "--allow-execution",
                "--json",
            ]
            if kind:
                c += ["--task-kind", kind]
            pc = run(c, proj)
            if pc.stdout.strip():
                (work / "cal.json").write_text(pc.stdout)
                cal = work / "cal.json"

        rd = [
            sys.executable,
            str(G / "readiness.py"),
            "--preflight",
            str(work / "pf.json"),
            "--json",
        ]
        if method:
            rd += ["--evaluator-method", method]
        if kind:
            rd += ["--task-kind", kind]
        if cal:
            rd += ["--calibration", str(cal)]
        review = meas / "row-review.json"
        if review.is_file():
            rd += ["--row-review", str(review)]
        knobs = meas / "agent-read.json"
        if knobs.is_file():
            rd += ["--agent-knobs", str(knobs)]
            doc = json.loads(knobs.read_text())
            if any(
                isinstance(v, dict) and v.get("source_lines")
                for v in (doc.get("knobs") or {}).values()
            ):
                rd += [
                    "--agent-source-root",
                    str(proj),
                    "--selected-agent",
                    str(proj / doc["source"]),
                    "--selected-agent-callable",
                    "run",
                ]
        pr = run(rd, proj)
        if not pr.stdout.strip():
            rows.append(
                (
                    slug,
                    "readiness failed",
                    (pr.stderr.strip().splitlines() or ["(no stderr)"])[-1][:70],
                )
            )
            continue
        got = json.loads(pr.stdout)
        pub = json.loads(
            (manifest.parent / "verifier" / "expected-opening.json").read_text()
        )

        def shape(band: str, action: str, caps: list[str]) -> str:
            """Every compared field, so a caps-only difference is not printed as a pair
            of identical strings -- which is what the first version did, leaving a
            reader with nothing to act on."""
            return f"{band}/{action}/[{','.join(sorted(caps)) or '-'}]"

        same = all(
            [
                got["band"] == pub["band"],
                got["status"] == pub["status"],
                got["recommended_action"] == pub["recommended_action"],
                sorted(c["condition"] for c in got.get("caps", []))
                == sorted(pub.get("caps") or []),
            ]
        )
        difference = (
            ""
            if same
            else "got "
            + shape(
                got["band"],
                got["recommended_action"],
                [c["condition"] for c in got.get("caps", [])],
            )
            + " against published "
            + shape(pub["band"], pub["recommended_action"], list(pub.get("caps") or []))
        )
        rows.append((slug, "MATCH" if same else "DIFFERS", difference))
    except Exception as failure:  # noqa: BLE001 - reported, never swallowed
        rows.append((slug, "COULD NOT READ", f"{type(failure).__name__}: {failure}"))
    finally:
        if work is not None:
            shutil.rmtree(work, ignore_errors=True)

if not rows:
    print("no scenario was read, so nothing was checked", file=sys.stderr)
    raise SystemExit(2)
w = max(len(r[0]) for r in rows)
for slug, verdict, detail in rows:
    print(f"  {slug:{w}}  {verdict:16} {detail}")
matched = sum(1 for r in rows if r[1] == "MATCH")
print()
print(f"  matched: {matched} of {len(rows)}")
raise SystemExit(0 if matched == len(rows) else 1)
