# SPDX-License-Identifier: Apache-2.0
"""The replay record validator that `check` and the re-measurement share.

A record is a list of commands the re-measurement runs, one of which calls the
scenario's own evaluator, so the validator is a boundary: the committed records
must pass it, and a record reaching for anything but the guide's first run must
not -- with a refusal naming the scenario, the step and the token.
"""

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path
from typing import Any, Callable

import scenario

SCENARIOS = scenario.REPOSITORY_ROOT / "scenarios"
LABEL = "scenario 'demo'"
REVISION = "d07b62cd4abb6ecb6d2edcdcb2d535f02bb2c199"


def committed_records() -> dict[str, Path]:
    return {
        manifest.parent.name: manifest.parent
        / "verifier"
        / "measurement"
        / "invocation.json"
        for manifest in sorted(SCENARIOS.glob("*/scenario.json"))
    }


def guide(script: str) -> str:
    return f"$GUIDE/skills/traigent-first-run/scripts/{script}"


def base_record() -> dict[str, Any]:
    """A record of the shape the bank publishes, calibration included."""
    return {
        "guide_revision": REVISION,
        "note": "placeholders only",
        "steps": {
            "preflight": [
                "$PYTHON",
                "-S",
                guide("preflight.py"),
                "--json",
                "--dataset",
                "dataset.jsonl",
                "--evaluator",
                "evaluator.py",
            ],
            "calibration": [
                "$PYTHON",
                "-S",
                guide("calibrate_evaluator.py"),
                "--scorer",
                "evaluator.py:score",
                "--cases",
                "@traigent-runs/calibration-cases.json",
                "--allow-execution",
                "--timeout",
                "60",
                "--json",
            ],
            "readiness": [
                "$PYTHON",
                "-S",
                guide("readiness.py"),
                "--json",
                "--preflight",
                "$MEASURE/02-preflight.json",
                "--calibration",
                "$MEASURE/03-calibration.json",
                "--agent-knobs",
                "$SCENARIO/verifier/measurement/agent-read.json",
                "--selected-agent",
                "$PROJECT/agent.py",
                "--row-review",
                "$ROW_REVIEW",
            ],
        },
    }


def setting(step: str, index: int, value: str) -> Callable[[dict[str, Any]], None]:
    def change(record: dict[str, Any]) -> None:
        record["steps"][step][index] = value

    return change


def appending(step: str, *tokens: str) -> Callable[[dict[str, Any]], None]:
    def change(record: dict[str, Any]) -> None:
        record["steps"][step].extend(tokens)

    return change


def removing(step: str, index: int) -> Callable[[dict[str, Any]], None]:
    def change(record: dict[str, Any]) -> None:
        del record["steps"][step][index]

    return change


class InvocationRecordTests(unittest.TestCase):
    def test_every_committed_record_is_accepted(self) -> None:
        records = committed_records()
        self.assertGreaterEqual(len(records), 13, "no committed record was found")
        for slug, path in records.items():
            with self.subTest(scenario=slug):
                record = scenario.read_invocation(path, f"scenario {slug!r}")
                self.assertIn("readiness", record["steps"])

    def test_every_flag_the_table_allows_is_one_a_committed_record_uses(
        self,
    ) -> None:
        """A flag nobody records is a flag nobody needs a replay to run."""
        used: dict[str, set[str]] = {name: set() for name in scenario.REPLAY_STEPS}
        for path in committed_records().values():
            record = json.loads(path.read_text(encoding="utf-8"))
            for name, argv in record["steps"].items():
                used[name] |= {token for token in argv if token.startswith("--")}
        for name, step in scenario.REPLAY_STEPS.items():
            with self.subTest(step=name):
                self.assertEqual(sorted(step.flags), sorted(used[name]))

    def test_the_base_record_is_accepted(self) -> None:
        steps = scenario.validate_invocation(base_record(), LABEL)
        self.assertEqual(["preflight", "calibration", "readiness"], list(steps))

    def test_a_record_reaching_past_the_first_run_is_refused_by_name(self) -> None:
        cases: tuple[tuple[str, Callable[[dict[str, Any]], None], str, str], ...] = (
            (
                "an unknown executable",
                setting("preflight", 0, "/usr/bin/touch"),
                "steps.preflight[0]",
                "'/usr/bin/touch'",
            ),
            (
                "an interpreter flag the records do not use",
                setting("calibration", 1, "-c"),
                "steps.calibration[1]",
                "'-c'",
            ),
            (
                "the interpreter without its recorded flag",
                removing("preflight", 1),
                "steps.preflight[1]",
                "preflight.py",
            ),
            (
                "another step's script",
                setting("preflight", 2, guide("readiness.py")),
                "steps.preflight[2]",
                "readiness.py",
            ),
            (
                "an unknown script",
                setting("calibration", 2, guide("evil.py")),
                "steps.calibration[2]",
                "evil.py",
            ),
            (
                "a script outside the guide's scripts",
                setting("readiness", 2, "$GUIDE/../readiness.py"),
                "steps.readiness[2]",
                "'$GUIDE/../readiness.py'",
            ),
            (
                "a flag the guide accepts and the replay does not",
                appending("readiness", "--report", "report.md"),
                "steps.readiness[14]",
                "'--report'",
            ),
            (
                "a flag written with its value",
                appending("preflight", "--evaluator-method=exact"),
                "steps.preflight[8]",
                "'--evaluator-method=exact'",
            ),
            (
                "a flag with no value",
                appending("preflight", "--evaluator-method"),
                "steps.preflight[8]",
                "--evaluator-method is given no value",
            ),
            (
                "a flag given twice",
                appending("preflight", "--dataset", "other.jsonl"),
                "steps.preflight[8]",
                "--dataset is given twice",
            ),
            (
                "an absolute path",
                setting("preflight", 5, "/etc/passwd"),
                "steps.preflight[5]",
                "'/etc/passwd' after --dataset",
            ),
            (
                "a path climbing out of the project",
                setting("preflight", 7, "../evaluator.py"),
                "steps.preflight[7]",
                "'../evaluator.py' after --evaluator",
            ),
            (
                "a scorer outside the project",
                setting("calibration", 4, "/tmp/scorer.py:score"),
                "steps.calibration[4]",
                "'/tmp/scorer.py:score' after --scorer",
            ),
            (
                "cases outside the project",
                setting("calibration", 6, "@../cases.json"),
                "steps.calibration[6]",
                "'@../cases.json' after --cases",
            ),
            (
                "a placeholder the runner does not bind",
                setting("readiness", 11, "$HOME/agent.py"),
                "steps.readiness[11]",
                "'$HOME/agent.py' after --selected-agent",
            ),
            (
                "a bound placeholder with a path climbing out of it",
                setting("readiness", 11, "$PROJECT/../agent.py"),
                "steps.readiness[11]",
                "'$PROJECT/../agent.py' after --selected-agent",
            ),
            (
                "a measurement input outside the measurement",
                setting("readiness", 9, "$SCENARIO/scenario.json"),
                "steps.readiness[9]",
                "'$SCENARIO/scenario.json' after --agent-knobs",
            ),
            (
                "another step's output",
                setting("readiness", 5, "$MEASURE/03-calibration.json"),
                "steps.readiness[5]",
                "'$MEASURE/03-calibration.json' after --preflight",
            ),
            (
                "a calibration budget past the guide's ceiling",
                setting("calibration", 9, "901"),
                "steps.calibration[9]",
                "--timeout 901 exceeds",
            ),
            (
                "a calibration budget of nothing",
                setting("calibration", 9, "0"),
                "steps.calibration[9]",
                "'0' after --timeout",
            ),
        )
        for label, change, field, token in cases:
            with self.subTest(case=label):
                record = copy.deepcopy(base_record())
                change(record)
                with self.assertRaises(scenario.BankError) as raised:
                    scenario.validate_invocation(record, LABEL)
                message = str(raised.exception)
                self.assertIn(LABEL, message)
                self.assertIn("verifier/measurement/invocation.json", message)
                self.assertIn(field, message)
                self.assertIn(token, message)

    def test_a_record_whose_steps_do_not_hang_together_is_refused(self) -> None:
        def reorder(record: dict[str, Any]) -> None:
            steps = record["steps"]
            record["steps"] = {
                "calibration": steps["calibration"],
                "preflight": steps["preflight"],
                "readiness": steps["readiness"],
            }

        def extra_step(record: dict[str, Any]) -> None:
            record["steps"] = {"setup": ["$PYTHON"], **record["steps"]}

        def no_readiness(record: dict[str, Any]) -> None:
            del record["steps"]["readiness"]

        def unread(record: dict[str, Any]) -> None:
            del record["steps"]["readiness"][6:8]

        def refused_and_read(record: dict[str, Any]) -> None:
            record["refusals"] = {"calibration": "Refusing to calibrate:"}

        def refused_readiness(record: dict[str, Any]) -> None:
            record["refusals"] = {"readiness": "Refusing"}

        def unknown_key(record: dict[str, Any]) -> None:
            record["environment"] = {"PATH": "/tmp"}

        def short_revision(record: dict[str, Any]) -> None:
            record["guide_revision"] = REVISION[:8]

        cases: tuple[tuple[str, Callable[[dict[str, Any]], None], str], ...] = (
            ("steps out of order", reorder, "must run in the order"),
            ("a step the replay does not run", extra_step, "steps.setup"),
            ("no readiness step", no_readiness, "records a readiness step"),
            ("an output nobody reads", unread, "names no refusal for it"),
            ("a refused step that is read", refused_and_read, "yet a later step"),
            ("a refused readiness step", refused_readiness, "refusals.readiness"),
            ("an unknown key", unknown_key, "unknown keys ['environment']"),
            ("a short revision", short_revision, "40-character commit id"),
        )
        for label, change, reason in cases:
            with self.subTest(case=label):
                record = copy.deepcopy(base_record())
                change(record)
                with self.assertRaises(scenario.BankError) as raised:
                    scenario.validate_invocation(record, LABEL)
                self.assertIn(LABEL, str(raised.exception))
                self.assertIn(reason, str(raised.exception))


if __name__ == "__main__":
    unittest.main()
