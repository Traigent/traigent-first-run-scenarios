# SPDX-License-Identifier: Apache-2.0
"""Every recorded opening, run for real in a prepared project, passes `verify`.

`verify --project-dir` holds a worker's project to what the guide's opening
writes. Tests that build a project by hand only check what their author
thought the guide writes, so this one runs the guide itself: each scenario is
prepared from a `traigent-first-run` checkout named by `GUIDE`, its recorded
preflight, calibration and readiness commands run in the prepared project
against the guide copy `prepare` made - as a worker's would, with Python left
free to write bytecode, as the guide leaves it - and `verify` must then pass
with `--project-dir`. Skipped without `GUIDE`; CI's re-measure job sets it to
the pinned revision.

Like `scripts/reproduce_openings.py`, this runs each scenario's own evaluator.
"""

from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY))

import scenario  # noqa: E402

# Where the opening keeps each scoring's evidence (component-creation.md,
# "Opening readiness procedure"); the recorded steps write their JSON there.
STAMP = "traigent-runs/readiness/20260923T120000Z"


@unittest.skipUnless(os.environ.get("GUIDE"), "set GUIDE to a guide checkout")
class RecordedOpeningInPreparedProjectTests(unittest.TestCase):
    def setUp(self) -> None:
        self.guide = Path(os.environ["GUIDE"]).resolve()
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        # `prepare` reads a scenario from committed Git content, so the bank is
        # committed into a repository of this test's own.
        self.repository = self.root / "repository"
        shutil.copytree(
            REPOSITORY / "scenarios",
            self.repository / "scenarios",
            ignore=shutil.ignore_patterns("__pycache__"),
        )
        for arguments in (
            ["init", "-q"],
            ["add", "scenarios"],
            [
                "-c",
                "user.name=Scenario Tests",
                "-c",
                "user.email=scenario-tests@example.invalid",
                "commit",
                "-qm",
                "Copy the bank",
            ],
        ):
            subprocess.run(["git", "-C", str(self.repository), *arguments], check=True)

    def cli(self, *arguments: str) -> tuple[int, str]:
        output = io.StringIO()
        status = scenario.main(
            list(arguments),
            scenarios_dir=self.repository / "scenarios",
            repository_root=self.repository,
            output=output,
            error=output,
        )
        return status, output.getvalue()

    def run_recorded_opening(self, slug: str) -> tuple[Path, Path, dict[str, object]]:
        """Prepare `slug` and run its recorded steps in the project, as recorded.

        Returns the run record, the readiness result and the invocation record.
        """
        root = self.repository / "scenarios" / slug
        output_path = self.root / f"run-{slug}"
        status, output = self.cli(
            "prepare",
            slug,
            "--guide-src",
            str(self.guide),
            "--output",
            str(output_path),
        )
        self.assertEqual(0, status, output)
        project = output_path / scenario.PREPARED_PROJECT_DIRECTORY
        invocation = scenario.read_invocation(
            root / "verifier" / scenario.INVOCATION_RECORD, slug
        )
        measure = project / STAMP
        measure.mkdir(parents=True)
        bound = {
            "$PYTHON": sys.executable,
            "$GUIDE": str(project / scenario.PREPARED_GUIDE_DIRECTORY),
            "$PROJECT": str(project),
            "$SCENARIO": str(root),
            "$MEASURE": str(measure),
            "$ROW_REVIEW": str(root / "verifier" / "measurement" / "row-review.json"),
        }
        # Nothing here turns bytecode off: the guide runs its calibration
        # without `-B`, and so does the recorded command.
        environment = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith("PYTHON")
        }
        refusals = invocation.get("refusals", {})
        for name, recorded in invocation["steps"].items():
            command = []
            for argument in recorded:
                for token, value in bound.items():
                    argument = argument.replace(token, value)
                command.append(argument)
            done = subprocess.run(
                command,
                cwd=project,
                env=environment,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=scenario.CALIBRATION_TIMEOUT_CEILING_SECONDS + 60,
            )
            if name in refusals:
                self.assertIn(refusals[name], done.stderr, f"{slug} {name}")
                continue
            self.assertTrue(done.stdout.strip(), f"{slug} {name}: {done.stderr}")
            (measure / scenario.REPLAY_STEPS[name].output).write_text(
                done.stdout, encoding="utf-8"
            )
        result = measure / scenario.REPLAY_STEPS["readiness"].output
        return output_path / "run.json", result, invocation

    def test_every_recorded_opening_passes_verify_with_its_project(self) -> None:
        bytecode = (
            f"{scenario.PREPARED_GUIDE_DIRECTORY}/skills/traigent-first-run/scripts/"
            f"__pycache__/preflight.{sys.implementation.cache_tag}.pyc"
        )
        scenarios = self.repository / "scenarios"
        slugs = sorted(path.parent.name for path in scenarios.glob("*/scenario.json"))
        self.assertEqual(13, len(slugs))
        for slug in slugs:
            with self.subTest(slug=slug):
                run_record, result, invocation = self.run_recorded_opening(slug)
                project = run_record.parent / scenario.PREPARED_PROJECT_DIRECTORY
                steps = invocation["steps"]
                assert isinstance(steps, dict)
                if "calibration" in steps:
                    # Calibration loads the guide's preflight.py through
                    # importlib, so Python wrote its bytecode into the copy.
                    self.assertTrue((project / bytecode).is_file(), slug)
                manifest = json.loads(
                    (scenarios / slug / "scenario.json").read_text(encoding="utf-8")
                )
                extra = []
                if "read_dependent" in manifest["catalog"]["expected_route"]:
                    review = scenarios / slug / "verifier/measurement/row-review.json"
                    extra = ["--row-review", str(review)]
                status, output = self.cli(
                    "verify",
                    slug,
                    "--run-record",
                    str(run_record),
                    "--result",
                    str(result),
                    "--project-dir",
                    str(project),
                    *extra,
                )
                self.assertEqual(0, status, output)
                self.assertIn("its project matches the prepared inventory", output)


if __name__ == "__main__":
    unittest.main()
