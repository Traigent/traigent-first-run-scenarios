"""The re-measurement script, run as it runs in CI, against a stand-in guide.

The stand-in's three scripts print fixed JSON, so each test controls exactly
what the guide returns and can check that the script reports it: a match, a
disagreement, and every way of not being able to measure, each with its own
exit status.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "reproduce_openings.py"

PREFLIGHT = "print('{\"ok\": true}')\n"
CALIBRATE = """import sys
if "--refuse" in sys.argv:
    print("Refusing to calibrate: the scorer reaches a database", file=sys.stderr)
    raise SystemExit(2)
print('{"calibrated": true}')
"""
# Opens STRONG unless the read it is given marks an answer `no`.
READINESS = """import json, sys
arguments = sys.argv[1:]
flagged = False
if "--row-review" in arguments:
    read = json.load(open(arguments[arguments.index("--row-review") + 1]))
    flagged = any(row["verdict"] == "no" for row in read["rows"])
print(json.dumps({
    "band": "WORKABLE" if flagged else "STRONG",
    "status": "OK",
    "recommended_action": "review-answer-key" if flagged else "proceed",
    "caps": [{"condition": "dataset-coarse-resolution"}],
    "overall": 70 if flagged else 82,
    "confidence": 0.86,
    "pillars": [{"name": "dataset", "score": 84, "confidence": 0.8}],
}))
"""


def opening(band: str = "STRONG", action: str = "proceed", overall: int = 82) -> dict:
    return {
        "schema_version": 1,
        "scope": "phase-a-opening",
        "band": band,
        "status": "OK",
        "recommended_action": action,
        "caps": ["dataset-coarse-resolution"],
        "display": {
            "overall": {"score": overall, "confidence": 0.86},
            "pillars": {"dataset": {"score": 84, "confidence": 0.8}},
        },
    }


# Every recorded readiness step reads the preflight output; the script refuses
# a record in which a step's output is neither read nor recorded as refused.
READS_PREFLIGHT = ("--preflight", "$MEASURE/02-preflight.json")


def step(script: str, *arguments: str) -> list[str]:
    return ["$PYTHON", f"$GUIDE/skills/traigent-first-run/scripts/{script}", *arguments]


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
        subprocess.run([*git, "init", "-q"], check=True)
        subprocess.run([*git, "add", "."], check=True)
        subprocess.run(
            [*git, "-c", "user.name=t", "-c", "user.email=t@example.invalid"]
            + ["commit", "-qm", "guide"],
            check=True,
        )
        self.revision = subprocess.run(
            [*git, "rev-parse", "HEAD"], check=True, capture_output=True, text=True
        ).stdout.strip()

        self.repository = root / "repository"
        (self.repository / "scripts").mkdir(parents=True)
        shutil.copy(SCRIPT, self.repository / "scripts" / SCRIPT.name)
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

    def write_invocation(self, steps: object, **extra: object) -> None:
        record = {"guide_revision": self.revision, **extra, "steps": steps}
        (self.scenario / "verifier" / "measurement" / "invocation.json").write_text(
            json.dumps(record)
        )

    def write_read(self, name: str, verdict: str) -> None:
        read = {"reviewer": "assistant", "rows": [{"id": "line-1", "verdict": verdict}]}
        (self.scenario / "verifier" / "measurement" / name).write_text(json.dumps(read))

    def run_script(self, guide: Path | None = None) -> tuple[int, str]:
        environment = {
            key: value for key, value in os.environ.items() if key != "GUIDE"
        }
        if guide is not None:
            environment["GUIDE"] = str(guide)
        done = subprocess.run(
            [sys.executable, str(self.repository / "scripts" / SCRIPT.name)],
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
        for field, value in (("band", "EXCELLENT"), ("overall", 81)):
            with self.subTest(field=field):
                contract = opening()
                if field == "overall":
                    contract["display"]["overall"]["score"] = value
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
            ([], "not a JSON object"),
            ({"readiness": step("readiness.py", "$NOPE")}, "unbound $NOPE"),
            (
                {"readiness": step("readiness.py", "--calibration", "$MEASURE/x.json")},
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
            "calibration": step("calibrate_evaluator.py", "--refuse"),
            "readiness": step("readiness.py", *READS_PREFLIGHT),
        }
        marker = {"calibration": "Refusing to calibrate:"}
        self.write_invocation(refusing, refusals=marker)
        status, output = self.run_script(self.guide)
        self.assertEqual(0, status, output)

        for label, calibration in (
            ("now measures", step("calibrate_evaluator.py")),
            ("crashes", step("no_such_script.py")),
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


if __name__ == "__main__":
    unittest.main()
