"""The re-measurement script, run as it runs in CI, against a stand-in guide.

The stand-in's three scripts print fixed JSON, so each test controls exactly
what the guide returns and can check that the script reports it: a match, a
disagreement, and every way of not being able to measure, each with its own
exit status. The stand-in answers only to flags the replay allows, because a
record carrying any other flag is refused before anything runs.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from git_fixtures import init_quiet_repository

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "reproduce_openings.py"

# Records the home it was given, and what was already in it, then leaves a
# file there for a later step to find if homes were shared.
PREFLIGHT = """import json, os, pathlib
home = pathlib.Path(os.environ["HOME"])
log = pathlib.Path(__file__).resolve().parents[4] / "homes.jsonl"
with log.open("a") as out:
    out.write(json.dumps({"home": str(home), "held": sorted(os.listdir(home))}) + "\\n")
(home / "left-by-preflight").write_text("x")
print('{"ok": true}')
"""
# Keyed on the task kind, a flag the replay allows: `code-sql` refuses as the
# guide refuses a scorer that reaches a database, `numeric` crashes, and
# `extraction` starts a child that writes a file three seconds later and then
# outlives the step's budget, the way a scorer that hangs would. `routing`
# starts a detached child in the step's process group that writes a file three
# seconds later, and then finishes normally.
CALIBRATE = """import subprocess, sys, time
kind = sys.argv[sys.argv.index("--task-kind") + 1] if "--task-kind" in sys.argv else ""
if kind == "code-sql":
    print("Refusing to calibrate: the scorer reaches a database", file=sys.stderr)
    raise SystemExit(2)
if kind == "numeric":
    raise RuntimeError("the scorer crashed")
if kind == "extraction":
    sentinel = __import__("pathlib").Path(__file__).resolve().parents[4] / "outlived"
    subprocess.Popen([sys.executable, "-c",
        "import pathlib, sys, time; time.sleep(3); "
        "pathlib.Path(sys.argv[1]).write_text('outlived')", str(sentinel)])
    time.sleep(30)
if kind == "routing":
    sentinel = __import__("pathlib").Path(__file__).resolve().parents[4] / "lingered"
    subprocess.Popen([sys.executable, "-c",
        "import pathlib, sys, time; time.sleep(3); "
        "pathlib.Path(sys.argv[1]).write_text('lingered')", str(sentinel)],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL)
print('{"calibrated": true}')
"""
# Opens STRONG unless the read it is given marks an answer `no`.
READINESS = """import json, os, pathlib, sys
home = pathlib.Path(os.environ["HOME"])
log = pathlib.Path(__file__).resolve().parents[4] / "homes.jsonl"
with log.open("a") as out:
    out.write(json.dumps({"home": str(home), "held": sorted(os.listdir(home))}) + "\\n")
arguments = sys.argv[1:]
flagged = False
if "--report" in arguments:
    open(arguments[arguments.index("--report") + 1], "w").write("report")
if "--row-review" in arguments:
    read = json.load(open(arguments[arguments.index("--row-review") + 1]))
    flagged = any(row["verdict"] == "no" for row in read["rows"])
print(json.dumps({
    "schema_version": 6,
    "band": "WORKABLE" if flagged else "STRONG",
    "status": "OK",
    "recommended_action": "review-answer-key" if flagged else "proceed",
    "caps": [{"condition": "dataset-coarse-resolution", "ceiling": 89,
              "blocks": False, "asks": False, "reason": "coarse",
              "action_kind": "add-examples"}],
    "overall": 70 if flagged else 82,
    "confidence": 0.86,
    "pillars": [{"name": "dataset", "score": 84, "confidence": 0.8}],
}))
"""


def opening(band: str = "STRONG", action: str = "proceed", overall: int = 82) -> dict:
    return {
        "schema_version": 2,
        "readiness_schema_version": 6,
        "scope": "phase-a-opening",
        "band": band,
        "status": "OK",
        "recommended_action": action,
        "caps": [
            {
                "condition": "dataset-coarse-resolution",
                "ceiling": 89,
                "blocks": False,
                "asks": False,
            }
        ],
        "display": {
            "overall": {"score": overall, "confidence": 0.86},
            "pillars": {"dataset": {"score": 84, "confidence": 0.8}},
        },
    }


# Every recorded readiness step reads the preflight output; the script refuses
# a record in which a step's output is neither read nor recorded as refused.
READS_PREFLIGHT = ("--preflight", "$MEASURE/02-preflight.json")


def step(script: str, *arguments: str) -> list[str]:
    return [
        "$PYTHON",
        "-S",
        f"$GUIDE/skills/traigent-first-run/scripts/{script}",
        *arguments,
    ]


class ReproduceOpeningsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.guide = root / "guide"
        scripts = self.guide / "skills" / "traigent-first-run" / "scripts"
        scripts.mkdir(parents=True)
        for name, source in (
            ("preflight.py", PREFLIGHT),
            ("calibrate_evaluator.py", CALIBRATE),
            ("readiness.py", READINESS),
        ):
            (scripts / name).write_text(source, encoding="utf-8")
        git = ["git", "-C", str(self.guide)]
        init_quiet_repository(self.guide)
        subprocess.run([*git, "add", "."], check=True)
        subprocess.run(
            [*git, "-c", "user.name=t", "-c", "user.email=t@example.invalid"]
            + ["commit", "-qm", "guide"],
            check=True,
        )
        self.revision = subprocess.run(
            [*git, "rev-parse", "HEAD"], check=True, capture_output=True, text=True
        ).stdout.strip()

        self.root = root
        self.repository = root / "repository"
        (self.repository / "scripts").mkdir(parents=True)
        shutil.copy(SCRIPT, self.repository / "scripts" / SCRIPT.name)
        # The script validates a record with the bank's own validator.
        shutil.copy(ROOT / "scenario.py", self.repository / "scenario.py")
        self.scenario = self.repository / "scenarios" / "demo"
        (self.scenario / "project").mkdir(parents=True)
        (self.scenario / "project" / "dataset.jsonl").write_text("{}\n")
        (self.scenario / "verifier" / "measurement").mkdir(parents=True)
        self.write_manifest()
        self.write_contract(opening())
        self.write_invocation(
            {
                "preflight": step("preflight.py"),
                "calibration": step("calibrate_evaluator.py"),
                "readiness": step(
                    "readiness.py",
                    *READS_PREFLIGHT,
                    "--calibration",
                    "$MEASURE/03-calibration.json",
                ),
            }
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write_manifest(self, read_dependent: bool = False) -> None:
        route: dict = {"rationale": "demo", "verifier_contract": "x"}
        if read_dependent:
            route["read_dependent"] = {
                "row_verdicts": "verifier/row-verdicts.json",
                "sound_read_contract": "verifier/expected-opening-sound-read.json",
            }
        manifest = {"catalog": {"expected_route": route}}
        (self.scenario / "scenario.json").write_text(json.dumps(manifest))

    def write_contract(self, value: dict, name: str = "expected-opening.json") -> None:
        (self.scenario / "verifier" / name).write_text(json.dumps(value))

    def write_invocation(
        self, steps: object, revision: str | None = None, **extra: object
    ) -> None:
        record = {"guide_revision": revision or self.revision, **extra, "steps": steps}
        (self.scenario / "verifier" / "measurement" / "invocation.json").write_text(
            json.dumps(record)
        )

    def write_read(self, name: str, verdict: str) -> None:
        read = {"reviewer": "assistant", "rows": [{"id": "line-1", "verdict": verdict}]}
        (self.scenario / "verifier" / "measurement" / name).write_text(json.dumps(read))

    def run_script(self, guide: Path | None = None, *arguments: str) -> tuple[int, str]:
        environment = {
            key: value for key, value in os.environ.items() if key != "GUIDE"
        }
        if guide is not None:
            environment["GUIDE"] = str(guide)
        done = subprocess.run(
            [
                sys.executable,
                str(self.repository / "scripts" / SCRIPT.name),
                *arguments,
            ],
            capture_output=True,
            text=True,
            env=environment,
        )
        return done.returncode, done.stdout + done.stderr

    def test_a_contract_the_guide_reproduces_matches(self) -> None:
        status, output = self.run_script(self.guide)
        self.assertEqual(0, status, output)
        self.assertIn("matched: 1 of 1 contracts", output)

    def test_every_published_field_is_compared(self) -> None:
        for field, value in (
            ("band", "EXCELLENT"),
            ("overall", 81),
            ("readiness_schema_version", 5),
            ("caps", "asks"),
            ("caps", "blocks"),
            ("caps", "ceiling"),
        ):
            with self.subTest(field=field, value=value):
                contract = opening()
                if field == "overall":
                    contract["display"]["overall"]["score"] = value
                elif field == "caps":
                    cap = contract["caps"][0]
                    cap[value] = None if value == "ceiling" else not cap[value]
                else:
                    contract[field] = value
                self.write_contract(contract)
                status, output = self.run_script(self.guide)
                self.assertEqual(1, status, output)
                self.assertIn("DIFFERS", output)
                self.assertIn(field, output)

    def test_a_guide_that_cannot_be_trusted_is_refused(self) -> None:
        status, output = self.run_script(None)
        self.assertEqual(2, status)
        self.assertIn("set GUIDE", output)
        (self.guide / "stray.py").write_text("")
        status, output = self.run_script(self.guide)
        self.assertEqual(2, status)
        self.assertIn("has local changes", output)

    def test_a_record_the_script_cannot_replay_is_not_measured(self) -> None:
        cases = (
            ([], "must be a JSON object"),
            (
                {"readiness": step("readiness.py", "--row-review", "$ROW_REVIEW")},
                "unbound $ROW_REVIEW",
            ),
            (
                {
                    "readiness": step(
                        "readiness.py", "--calibration", "$MEASURE/03-calibration.json"
                    )
                },
                "which no earlier step writes",
            ),
            (
                {
                    "calibration": step("calibrate_evaluator.py"),
                    "readiness": step("readiness.py"),
                },
                "names no refusal",
            ),
        )
        for steps, reason in cases:
            with self.subTest(reason=reason):
                (
                    self.scenario / "verifier" / "measurement" / "invocation.json"
                ).write_text(
                    json.dumps(steps)
                    if isinstance(steps, list)
                    else json.dumps({"guide_revision": self.revision, "steps": steps})
                )
                status, output = self.run_script(self.guide)
                self.assertEqual(2, status, output)
                self.assertIn("COULD NOT READ", output)
                self.assertIn(reason, output)

    def test_a_recorded_refusal_must_repeat_as_recorded(self) -> None:
        refusing = {
            "preflight": step("preflight.py"),
            "calibration": step("calibrate_evaluator.py", "--task-kind", "code-sql"),
            "readiness": step("readiness.py", *READS_PREFLIGHT),
        }
        marker = {"calibration": "Refusing to calibrate:"}
        self.write_invocation(refusing, refusals=marker)
        status, output = self.run_script(self.guide)
        self.assertEqual(0, status, output)

        for label, calibration in (
            ("now measures", step("calibrate_evaluator.py")),
            ("crashes", step("calibrate_evaluator.py", "--task-kind", "numeric")),
        ):
            with self.subTest(label=label):
                self.write_invocation(
                    {**refusing, "calibration": calibration}, refusals=marker
                )
                status, output = self.run_script(self.guide)
                self.assertEqual(2, status, output)
                self.assertIn("was recorded refusing", output)

    def test_a_read_dependent_scenario_measures_both_contracts(self) -> None:
        self.write_manifest(read_dependent=True)
        self.write_contract(opening("WORKABLE", "review-answer-key", 70))
        self.write_contract(opening(), "expected-opening-sound-read.json")
        self.write_read("row-review.json", "no")
        self.write_read("row-review-sound-read.json", "yes")
        self.write_invocation(
            {"readiness": step("readiness.py", "--row-review", "$ROW_REVIEW")}
        )
        status, output = self.run_script(self.guide)
        self.assertEqual(0, status, output)
        self.assertIn("matched: 2 of 2 contracts", output)

        self.write_read("row-review-sound-read.json", "no")
        status, output = self.run_script(self.guide)
        self.assertEqual(1, status, output)
        self.assertIn("demo (sound read)", output)

    def test_a_record_that_could_run_anything_else_is_refused_before_it_runs(
        self,
    ) -> None:
        """Each of these ran, before the record was held to the replay's table.

        The sentinel is what makes the case: a refusal reported after the
        command has already run is not a refusal.
        """
        sentinel = self.root / "ran"
        outside = self.root / "host-file.json"
        outside.write_text("{}")
        evil = self.guide / "skills" / "traigent-first-run" / "scripts" / "evil.py"
        evil.write_text(
            f"open({str(sentinel)!r}, 'w').write('ran')\n" + READINESS,
            encoding="utf-8",
        )
        git = ["git", "-C", str(self.guide)]
        subprocess.run([*git, "add", "."], check=True)
        subprocess.run(
            [*git, "-c", "user.name=t", "-c", "user.email=t@example.invalid"]
            + ["commit", "-qm", "evil"],
            check=True,
        )
        revision = subprocess.run(
            [*git, "rev-parse", "HEAD"], check=True, capture_output=True, text=True
        ).stdout.strip()
        readiness = step("readiness.py", *READS_PREFLIGHT)
        cases = (
            (
                "an unknown executable",
                {
                    "preflight": ["/usr/bin/touch", str(sentinel)],
                    "readiness": readiness,
                },
                "steps.preflight[0]",
                "'/usr/bin/touch'",
            ),
            (
                "an unknown script",
                {
                    "preflight": step("preflight.py"),
                    "readiness": step("evil.py", *READS_PREFLIGHT),
                },
                "steps.readiness[2]",
                "evil.py",
            ),
            (
                "an unknown flag",
                {
                    "preflight": step("preflight.py"),
                    "readiness": [*readiness, "--report", str(sentinel)],
                },
                "steps.readiness[5]",
                "'--report'",
            ),
            (
                "a path outside the placeholders",
                {
                    "preflight": step("preflight.py"),
                    "readiness": [*readiness, "--agent-knobs", str(outside)],
                },
                "steps.readiness[6]",
                repr(str(outside)),
            ),
            (
                "a path climbing out of the project",
                {
                    "preflight": step("preflight.py", "--dataset", "../../ran"),
                    "readiness": readiness,
                },
                "steps.preflight[4]",
                "'../../ran'",
            ),
        )
        for label, steps, field, token in cases:
            with self.subTest(label=label):
                self.write_invocation(steps, revision=revision)
                status, output = self.run_script(self.guide)
                self.assertEqual(2, status, output)
                self.assertIn("COULD NOT READ", output)
                self.assertIn("scenario 'demo'", output)
                self.assertIn(field, output)
                self.assertIn(token, output)
                self.assertFalse(sentinel.exists(), f"{label} ran: {output}")

    def test_a_step_past_its_budget_is_stopped_with_everything_it_started(
        self,
    ) -> None:
        """The deadlines are shrunk in the copies this test runs, not in the repo."""
        for path, old, new in (
            (
                self.repository / "scenario.py",
                "CALIBRATION_TIMEOUT_CEILING_SECONDS = 900\n",
                "CALIBRATION_TIMEOUT_CEILING_SECONDS = 1\n",
            ),
            (
                self.repository / "scripts" / SCRIPT.name,
                "REPLAY_MARGIN_SECONDS = 60\n",
                "REPLAY_MARGIN_SECONDS = 1\n",
            ),
        ):
            source = path.read_text(encoding="utf-8")
            self.assertEqual(1, source.count(old), f"{path.name} has no {old!r}")
            path.write_text(source.replace(old, new), encoding="utf-8")
        self.write_invocation(
            {
                "preflight": step("preflight.py"),
                "calibration": step(
                    "calibrate_evaluator.py", "--task-kind", "extraction"
                ),
                "readiness": step(
                    "readiness.py",
                    *READS_PREFLIGHT,
                    "--calibration",
                    "$MEASURE/03-calibration.json",
                ),
            }
        )
        started = time.monotonic()
        status, output = self.run_script(self.guide)
        self.assertLess(time.monotonic() - started, 20, output)
        self.assertEqual(2, status, output)
        self.assertIn(
            "step 'calibration' was still running after its 2-second replay "
            "budget and was stopped",
            output,
        )
        # The stand-in's child writes three seconds after it starts; stopping
        # the step alone would leave it to do so.
        time.sleep(4)
        self.assertFalse((self.root / "outlived").exists(), output)

    def test_a_step_that_finishes_leaves_nothing_of_its_group_running(
        self,
    ) -> None:
        self.write_invocation(
            {
                "preflight": step("preflight.py"),
                "calibration": step("calibrate_evaluator.py", "--task-kind", "routing"),
                "readiness": step(
                    "readiness.py",
                    *READS_PREFLIGHT,
                    "--calibration",
                    "$MEASURE/03-calibration.json",
                ),
            }
        )
        status, output = self.run_script(self.guide)
        self.assertEqual(0, status, output)
        # The stand-in's detached child writes three seconds after it starts.
        time.sleep(4)
        self.assertFalse((self.root / "lingered").exists(), output)

    def test_every_step_gets_a_fresh_empty_home_that_is_removed(self) -> None:
        status, output = self.run_script(self.guide)
        self.assertEqual(0, status, output)
        records = [
            json.loads(line)
            for line in (self.root / "homes.jsonl").read_text().splitlines()
        ]
        self.assertEqual(2, len(records), records)
        homes = [record["home"] for record in records]
        self.assertEqual(2, len(set(homes)), "the steps shared a home")
        for record in records:
            self.assertEqual([], record["held"], "a step's home was not empty")
            self.assertFalse(Path(record["home"]).exists(), "a home outlived its step")

    def test_a_guide_checkout_git_cannot_answer_for_is_refused(self) -> None:
        script = self.repository / "scripts" / SCRIPT.name
        source = script.read_text(encoding="utf-8")
        old = "REPLAY_MARGIN_SECONDS = 60\n"
        self.assertEqual(1, source.count(old))
        script.write_text(source.replace(old, "REPLAY_MARGIN_SECONDS = 1\n"))
        fake = self.root / "bin"
        fake.mkdir()
        (fake / "git").write_text("#!/bin/sh\nsleep 30\n")
        (fake / "git").chmod(0o755)
        environment = {**os.environ, "GUIDE": str(self.guide)}
        environment["PATH"] = f"{fake}{os.pathsep}{environment.get('PATH', '')}"
        started = time.monotonic()
        done = subprocess.run(
            [sys.executable, str(script)],
            capture_output=True,
            text=True,
            env=environment,
        )
        output = done.stdout + done.stderr
        self.assertLess(time.monotonic() - started, 20, output)
        self.assertEqual(2, done.returncode, output)
        self.assertIn("did not answer within 1 seconds", output)
        self.assertNotIn("Traceback", output)

    def test_a_link_in_the_scenario_is_refused_before_the_copy(self) -> None:
        outside = self.root / "host-file.txt"
        outside.write_text("private\n")
        review = self.scenario / "verifier" / "measurement" / "row-review.json"
        self.write_read("row-review.json", "yes")
        for label, link, target in (
            ("in the project", self.scenario / "project" / "notes.txt", outside),
            ("in the measurement", review, outside),
        ):
            with self.subTest(label=label):
                if link.exists():
                    link.unlink()
                link.symlink_to(target)
                status, output = self.run_script(self.guide)
                link.unlink()
                self.assertEqual(2, status, output)
                self.assertIn("contains a symbolic link", output)
                self.assertIn(str(link), output)

    def test_against_head_replays_any_revision_and_calls_a_difference_drift(
        self,
    ) -> None:
        pinned = "0" * 40
        self.write_invocation(
            {
                "preflight": step("preflight.py"),
                "readiness": step("readiness.py", *READS_PREFLIGHT),
            },
            revision=pinned,
        )
        status, output = self.run_script(self.guide)
        self.assertEqual(2, status, output)
        self.assertIn("measured at 00000000", output)

        status, output = self.run_script(self.guide, "--against-head")
        self.assertEqual(0, status, output)
        self.assertIn(f"guide {self.revision}, clean checkout", output)
        self.assertIn("pinned at 00000000", output)
        self.assertIn("MATCH", output)
        self.assertNotIn("DRIFT", output)

        self.write_contract(opening(band="EXCELLENT"))
        status, output = self.run_script(self.guide, "--against-head")
        self.assertEqual(1, status, output)
        self.assertIn("DRIFT", output)
        self.assertIn("band got 'STRONG' published 'EXCELLENT'", output)
        self.assertIn("not a defect in a scenario", output)

    def test_against_head_reports_what_stopped_before_the_guide_ran_as_unread(
        self,
    ) -> None:
        """Only what the guide did can drift; a refused record is not the guide."""
        outside = self.root / "host-file.txt"
        outside.write_text("private\n")
        link = self.scenario / "project" / "notes.txt"
        readiness = step("readiness.py", *READS_PREFLIGHT)
        for label, prepare, reason in (
            (
                "a refused record",
                lambda: self.write_invocation(
                    {
                        "preflight": step("preflight.py"),
                        "readiness": [*readiness, "--report", "report.md"],
                    }
                ),
                "'--report' is not a flag",
            ),
            ("a link", lambda: link.symlink_to(outside), "contains a symbolic link"),
        ):
            with self.subTest(label=label):
                prepare()
                status, output = self.run_script(self.guide, "--against-head")
                if link.is_symlink():
                    link.unlink()
                self.write_invocation(
                    {"preflight": step("preflight.py"), "readiness": readiness}
                )
                self.assertEqual(2, status, output)
                self.assertIn("COULD NOT READ", output)
                self.assertIn(reason, output)
                self.assertNotIn("DRIFT", output)
                self.assertNotIn("has moved", output)

    def test_against_head_calls_a_guide_that_fails_after_starting_drift(
        self,
    ) -> None:
        self.write_invocation(
            {
                "preflight": step("preflight.py"),
                "calibration": step("calibrate_evaluator.py", "--task-kind", "numeric"),
                "readiness": step(
                    "readiness.py",
                    *READS_PREFLIGHT,
                    "--calibration",
                    "$MEASURE/03-calibration.json",
                ),
            },
            revision="0" * 40,
        )
        status, output = self.run_script(self.guide, "--against-head")
        self.assertEqual(1, status, output)
        self.assertIn("DRIFT", output)
        self.assertIn("calibration wrote nothing", output)
        self.assertIn("the guide has moved", output)

    def test_against_head_on_the_pinned_revision_does_not_say_the_guide_moved(
        self,
    ) -> None:
        self.write_contract(opening(band="EXCELLENT"))
        status, output = self.run_script(self.guide, "--against-head")
        self.assertEqual(1, status, output)
        self.assertIn("DRIFT", output)
        self.assertIn(f"pinned at {self.revision[:8]}", output)
        self.assertNotIn("has moved", output)
        self.assertIn("the pinned revision", output)
        self.assertIn("the pinned replay fails the same way", output)

    def test_against_head_still_refuses_a_checkout_with_local_changes(self) -> None:
        (self.guide / "stray.py").write_text("")
        status, output = self.run_script(self.guide, "--against-head")
        self.assertEqual(2, status, output)
        self.assertIn("has local changes", output)

    def test_an_unknown_argument_is_refused(self) -> None:
        status, output = self.run_script(self.guide, "--against-pin")
        self.assertEqual(2, status, output)
        self.assertIn("unrecognized arguments: --against-pin", output)


if __name__ == "__main__":
    unittest.main()
