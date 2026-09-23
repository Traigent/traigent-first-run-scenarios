# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import hashlib
import importlib.util
import io
import itertools
import json
import marshal
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import tracemalloc
import unittest
from pathlib import Path
from unittest import mock

from jsonschema import Draft202012Validator

import scenario

TEST_DATASET_ROW = (
    json.dumps(
        {
            "input": "example",
            "output": "A",
            "metadata": {"split": "tuning", "difficulty": "easy"},
        }
    )
    + "\n"
)

# A fixture scenario ships an evaluator because a customer-shaped project has
# one, and because `check` parses every shipped Python file for syntax. Nothing
# in the catalog contract is derived from what this source says: the shape of
# its table, and whether it has one at all, are deliberately not read.
EVALUATOR_SOURCE = (
    "# SPDX-License-Identifier: Apache-2.0\n"
    '"""A deterministic label evaluator for fixture scenarios."""\n'
    "\n"
    "\n"
    "def score(output, expected, input_data=None, metadata=None):\n"
    "    return 1.0 if output == expected else 0.0\n"
)

# A component slot names a file whose bytes read as Python source, so the
# fixture agent is Python rather than the dataset the fixture used to point the
# agent slot at. That fixture was the hole in miniature: `agent.path` accepted
# any regular file under project/, so it accepted the labelled dataset.
AGENT_SOURCE = (
    "# SPDX-License-Identifier: Apache-2.0\n"
    '"""A configurable agent for fixture scenarios."""\n'
    "\n"
    "\n"
    'def run(report, model="small"):\n'
    "    return report.strip()\n"
)


def valid_manifest(slug: str, legacy_id: int) -> dict[str, object]:
    return {
        "schema_version": 1,
        "slug": slug,
        "legacy_id": legacy_id,
        "title": f"Scenario {legacy_id}",
        "summary": "A fully materialized first-run scenario.",
        "phase": "phase-a-opening",
        "content": {
            "origin": "traigent-authored",
            "license": "Apache-2.0",
        },
        "paths": {"project": "project", "verifier": "verifier"},
        "catalog": {
            "starting_condition": "all-components-ready",
            "components": {
                "agent": {
                    "state": "ready",
                    "path": "project/agent.py",
                    "controls": ["model"],
                },
                "data": {
                    "state": "ready",
                    "paths": ["project/input.txt"],
                },
                "evaluator": {
                    "state": "ready",
                    "path": "project/evaluator.py",
                    "method": "normalized-exact-match",
                    "calibration": {"path": None, "case_count": 0},
                },
            },
            "datasets": [
                {
                    "id": "primary",
                    "state": "ready",
                    "path": "project/input.txt",
                    "task": "closed-label-classification",
                    "guide_task_kind": "closed-label",
                    "format": "jsonl",
                    "input_field": "input",
                    "label_field": "output",
                    "rows": 1,
                    "unique_inputs": 1,
                    "splits": {
                        "field": "metadata.split",
                        "counts": {"tuning": 1},
                    },
                    "difficulty_strata": {
                        "field": "metadata.difficulty",
                        "counts": {"easy": 1},
                    },
                    "label_shape": {
                        "kind": "mapped-labels",
                        "surface_label_count": 1,
                        "label_counts": {"A": 1},
                    },
                    "limitations": ["traigent-authored-synthetic"],
                }
            ],
            "expected_route": {
                "rationale": "all-required-components-ready",
                "verifier_contract": "verifier/expected-opening.json",
            },
            "evidence": {
                "demonstrates": ["catalog-contract"],
                "does_not_demonstrate": ["live-optimization"],
            },
        },
        "tags": ["onboarding"],
    }


def expected_opening() -> dict[str, object]:
    return {
        "schema_version": 2,
        "readiness_schema_version": 6,
        "scope": "phase-a-opening",
        "band": "EXCELLENT",
        "status": "OK",
        "recommended_action": "proceed",
        "caps": [],
        "display": {
            "overall": {"score": 92, "confidence": 0.95},
            "pillars": {
                "custom-pillar": {"score": 73.5, "confidence": 0.8},
            },
        },
    }


def intended_opening(
    contract: dict[str, object], divergence: object = None
) -> dict[str, object]:
    """A fixture's intended opening: the contract's four fields, written down."""
    return {
        "schema_version": 1,
        "band": contract["band"],
        "status": contract["status"],
        "recommended_action": contract["recommended_action"],
        "caps": contract["caps"],
        "divergence": divergence,
    }


def readiness_result(contract: dict[str, object]) -> dict[str, object]:
    """The readiness payload a worker would capture for this contract.

    Carries what readiness adds and `verify` does not compare - each cap's
    reason and action kind, a score - so a match is a match on the compared
    fields rather than on a copy of the contract.
    """
    caps = contract["caps"]
    assert isinstance(caps, list)
    return {
        "schema_version": contract["readiness_schema_version"],
        "band": contract["band"],
        "status": contract["status"],
        "recommended_action": contract["recommended_action"],
        "caps": [
            {**cap, "reason": "measured", "action_kind": "remedy"} for cap in caps
        ],
        "overall": 90,
    }


# A schema 2 cap, whose condition the leak scan reads as a tell.
SYNTHETIC_CAP = {
    "condition": "dataset-fully-synthetic",
    "ceiling": 65,
    "blocks": False,
    "asks": False,
}


# The guide withholds these two bands until a read of the answers enters, so a
# scenario published on one of them was measured with a review.
BANDS_ABOVE_THE_ANSWER_KEY_HOLD = ("STRONG", "EXCELLENT")

# The one cap `readiness.py` builds out of a row review's verdicts. Its share
# test runs over what the reviewer read, so no other input can raise it, and a
# published opening carrying it was measured with a review whatever its band.
REVIEW_DERIVED_CAP = "dataset-unsound-expected-outputs"

# A stand-in SKILL.md stating the ask rules `verify --response` implements, in
# the guide's own sentences and wrapped the way the guide wraps them.
SKILL_WITH_ASK_RULES = (
    "# Skill\n\n"
    "- Named routes are lettered from `A`, exactly one marked recommended, and\n"
    "  answerable by reply. No route carries a decision of its own. Keep the\n"
    "  question last; a route list is never compressed into yes/no. `I have it`\n"
    "  is unnumbered, last, and only on material questions.\n\n"
    "Always end with `I have it` and a path as an unnumbered\nalternative.\n"
)

# Written for these tests in the shape the guide teaches: two lettered routes,
# one marked, and the standing line last.
WELL_SHAPED_ASK = (
    "Your rows are here, and the evaluator returns one score for every answer.\n"
    "\n"
    "A. **I build a working evaluator (recommended)** in a copy under\n"
    "traigent-runs/, then carry on.\n"
    "B. Pause, and I list the checks a corrected evaluator has to pass.\n"
    "\n"
    "Or reply `I have it` with a path, and I will use yours.\n"
)


# A scenario README's difficulty rubric: its heading at either level the bank
# uses, and a stratum bullet in either spelling the bank uses. A heading that
# mentions the rubric in any other form is reported, never skipped, so a new
# spelling cannot take a scenario out of the check without a word.
RUBRIC_HEADING = re.compile(r"^(#{2,3}) Difficulty rubric[ \t]*$", re.MULTILINE)
RUBRIC_BULLET = re.compile(r"^- (?:\*\*([\w-]+)\*\*|`([\w-]+)`)")
# A bullet's closing list of worked examples: backticked items, comma
# separated, ending the bullet. Every item in such a list must name a row.
RUBRIC_EXAMPLE_LIST = re.compile(r"(?:^|(?<=\. ))((?:`[^`]+`,\s*)*`[^`]+`)\.$")


def _rubric_findings(repository: Path) -> tuple[list[str], int, int]:
    """Check every README difficulty rubric against its manifest and dataset.

    Returns the problems, the number of rubrics read and the number of worked
    examples compared. A rubric must define exactly the strata its manifest
    declares. A backticked answer that names exactly one row is a worked
    example of that row's stratum and must sit under that stratum's bullet;
    an answer many rows share is a label, which names a class rather than a
    row, and illustrates nothing. A closing example list must name rows only,
    so a typo or an escaping slip cannot drop an example out of the check.
    """
    problems: list[str] = []
    read = compared = 0
    for manifest_path in sorted((repository / "scenarios").glob("*/scenario.json")):
        slug = manifest_path.parent.name
        readme = manifest_path.parent / "README.md"
        text = readme.read_text(encoding="utf-8") if readme.is_file() else ""
        heading = RUBRIC_HEADING.search(text)
        if heading is None:
            problems.extend(
                f"{slug}: rubric heading {line!r} is not in a recognised form"
                for line in text.splitlines()
                if line.startswith("#") and "difficulty rubric" in line.lower()
            )
            continue
        read += 1
        rest = text[heading.end() :]
        end = re.search(rf"^#{{1,{len(heading.group(1))}}} ", rest, re.MULTILINE)
        section = rest[: end.start()] if end else rest
        dataset = json.loads(manifest_path.read_text(encoding="utf-8"))["catalog"][
            "datasets"
        ][0]
        declared = set(dataset["difficulty_strata"]["counts"])
        rows_with: dict[str, list[str]] = {}
        for line in (
            (manifest_path.parent / dataset["path"]).read_text(encoding="utf-8")
        ).splitlines():
            if line.strip():
                row = json.loads(line)
                if isinstance(row["output"], str):
                    rows_with.setdefault(row["output"], []).append(
                        row["metadata"]["difficulty"]
                    )
        stratum_of = {
            answer: rows[0] for answer, rows in rows_with.items() if len(rows) == 1
        }

        bullets: dict[str, str] = {}
        current: str | None = None
        for line in section.splitlines():
            bullet = RUBRIC_BULLET.match(line)
            if bullet:
                current = bullet.group(1) or bullet.group(2)
                bullets[current] = line[bullet.end() :]
            elif current is not None and line.startswith("  "):
                bullets[current] += " " + line.strip()
            else:
                current = None
        if set(bullets) != declared:
            problems.append(
                f"{slug}: the rubric defines {sorted(bullets)} and the manifest "
                f"declares {sorted(declared)}"
            )
        for name, body in bullets.items():
            for example in re.findall(r"`([^`]+)`", body):
                stratum = stratum_of.get(example)
                if stratum is None:
                    continue
                compared += 1
                if stratum != name:
                    problems.append(
                        f"{slug}: the rubric illustrates {name!r} with {example!r}, "
                        f"which the dataset labels {stratum!r}"
                    )
            examples = RUBRIC_EXAMPLE_LIST.search(body.strip())
            if examples:
                problems.extend(
                    f"{slug}: {name!r} lists {example!r} as an example, and no "
                    "single row of the dataset has that answer"
                    for example in re.findall(r"`([^`]+)`", examples.group(1))
                    if example not in stratum_of
                )
    return problems, read, compared


def _opening_needs_a_row_review(opening: dict[str, object]) -> bool:
    """Whether this published opening is one a review has to be committed for.

    Asked of the contract rather than of a list, so the answer follows the bank
    instead of being maintained beside it.
    """
    caps = opening.get("caps") or []
    assert isinstance(caps, list)
    conditions = {cap["condition"] for cap in caps}
    return (
        opening["band"] in BANDS_ABOVE_THE_ANSWER_KEY_HOLD
        or REVIEW_DERIVED_CAP in conditions
    )


def tell_at(offset: int, token: str) -> str:
    """Evaluator source with `token` starting `offset` bytes into the file.

    The leak scan reads a block at a time, so an offset near a multiple of the
    block size splits the token across two reads.
    """
    padding = offset - len(EVALUATOR_SOURCE) - 2
    return EVALUATOR_SOURCE + "#" + "x" * padding + " " + token + "\n"


# Tells in the forms a project writes them, the prose and names that must not
# count, and tokens longer than the scan's carry.
TELL_SNIPPETS = (
    "told-apart",
    "TOLD_APART",
    "toldApart",
    "untold-apart",
    "told-apartment",
    "told" + "_" * 60 + "apart",
    "datasetFullySynthetic",
    "expectedOpening",
    "expected_opening_balance",
    "expected opening",
    "unexpected-opening",
    "verifier/x",
    "=verifier/x",
    "(verifier/x)",
    "sql_verifier/x",
    "averifier/x",
    "x",
    "",
    "x" + "told-apart" + "-" + "_" * 80,
    "sql_verifier/" + "-" * 80,
    # A tell after a letter, then text, then only separators. Once the carry
    # has cut text, reads that fold into its trailing hyphen leave a window no
    # longer than the carry; that must not make its start the file's start.
    # The run of letters moves the cut across the tell's first byte.
    *("x" + "told-apart" + "-" + "y" * run + "-" + "_" * 20 for run in range(28, 44)),
    *("xexpectedOpening" + "y" * run + "." * 20 for run in range(24, 40)),
)


class TellStreamTests(unittest.TestCase):
    """The block-at-a-time leak scan names what folding the whole file names."""

    def test_the_stream_agrees_with_the_whole_file(self) -> None:
        patterns = scenario._tell_patterns(("told-apart", "dataset-fully-synthetic"))
        checked = 0
        disagreements: list[str] = []
        # A block of one byte moves every snippet across every block boundary.
        # The carry only cuts once more than it holds has been read, so the
        # long tail keeps the file going until the cut has crossed every
        # position of every snippet too.
        for block_size in (1, 2, 3, 5, 7, 11):
            for pad in range(48):
                for snippet in TELL_SNIPPETS:
                    for tail in ("", " end", "s", " " * 60):
                        content = (" " * pad + snippet + tail).encode()
                        whole = scenario._fold_tells(content)
                        expected = {
                            name
                            for name, pattern in patterns.items()
                            if pattern.search(whole)
                        }
                        got = scenario._tells_in_stream(
                            io.BytesIO(content), patterns, block_size
                        )
                        checked += 1
                        if got != expected:
                            disagreements.append(
                                f"block {block_size}, {content!r}: streamed "
                                f"{sorted(got)}, whole {sorted(expected)}"
                            )
        self.assertGreater(checked, 50000)
        self.assertEqual(
            [], disagreements[:5], f"{len(disagreements)} of {checked} disagree"
        )

    def test_a_cap_that_folds_longer_than_it_is_written_is_still_carried(
        self,
    ) -> None:
        """A cap is any non-empty string; every hump in it folds to a hyphen."""
        cap = "aB" * 30
        patterns = scenario._tell_patterns(("told-apart", cap))
        self.assertGreater(len(scenario._fold_tells(cap.encode())), len(cap))
        checked = 0
        disagreements: list[str] = []
        for block_size in (1, 3, 7):
            for pad in range(48):
                for snippet in (cap, "x" + cap, cap + "-" + "_" * 20):
                    for tail in ("", " end", " " * 120):
                        content = (" " * pad + snippet + tail).encode()
                        whole = scenario._fold_tells(content)
                        expected = {
                            name
                            for name, pattern in patterns.items()
                            if pattern.search(whole)
                        }
                        got = scenario._tells_in_stream(
                            io.BytesIO(content), patterns, block_size
                        )
                        checked += 1
                        if got != expected:
                            disagreements.append(
                                f"block {block_size}, pad {pad}, {snippet[:6]!r}: "
                                f"streamed {sorted(got)}, whole {sorted(expected)}"
                            )
        self.assertGreater(checked, 1000)
        self.assertEqual(
            [], disagreements[:5], f"{len(disagreements)} of {checked} disagree"
        )


class ScenarioBankTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.repository_root = Path(self.temporary_directory.name)
        self.scenarios_dir = self.repository_root / "scenarios"
        self.scenarios_dir.mkdir()
        self.guide_counter = 0
        subprocess.run(
            ["git", "init", "-q", os.fspath(self.repository_root)], check=True
        )

    def commit_repository_paths(self, *paths: Path, message: str) -> None:
        relative_paths = [
            os.fspath(path.relative_to(self.repository_root)) for path in paths
        ]
        subprocess.run(
            [
                "git",
                "-C",
                os.fspath(self.repository_root),
                "add",
                "--",
                *relative_paths,
            ],
            check=True,
        )
        subprocess.run(
            [
                "git",
                "-C",
                os.fspath(self.repository_root),
                "-c",
                "user.name=Scenario Tests",
                "-c",
                "user.email=scenario-tests@example.invalid",
                "commit",
                "-qm",
                message,
            ],
            check=True,
        )

    def remove_repository_paths(self, *paths: Path, message: str) -> None:
        relative_paths = [
            os.fspath(path.relative_to(self.repository_root)) for path in paths
        ]
        subprocess.run(
            [
                "git",
                "-C",
                os.fspath(self.repository_root),
                "rm",
                "-q",
                "--",
                *relative_paths,
            ],
            check=True,
        )
        subprocess.run(
            [
                "git",
                "-C",
                os.fspath(self.repository_root),
                "-c",
                "user.name=Scenario Tests",
                "-c",
                "user.email=scenario-tests@example.invalid",
                "commit",
                "-qm",
                message,
            ],
            check=True,
        )

    def create_scenario(
        self,
        slug: str,
        legacy_id: int,
        *,
        manifest: dict[str, object] | None = None,
        materialized: bool = True,
    ) -> Path:
        root = self.scenarios_dir / slug
        root.mkdir()
        (root / "project").mkdir()
        (root / "verifier").mkdir()
        (root / "scenario.json").write_text(
            json.dumps(
                manifest if manifest is not None else valid_manifest(slug, legacy_id)
            ),
            encoding="utf-8",
        )
        if materialized:
            (root / "project" / "input.txt").write_text(
                TEST_DATASET_ROW,
                encoding="utf-8",
            )
            (root / "project" / "agent.py").write_text(
                AGENT_SOURCE,
                encoding="utf-8",
            )
            (root / "project" / "evaluator.py").write_text(
                EVALUATOR_SOURCE,
                encoding="utf-8",
            )
            (root / "verifier" / "expected-opening.json").write_text(
                json.dumps(expected_opening()) + "\n", encoding="utf-8"
            )
            (root / "verifier" / "intended-opening.json").write_text(
                json.dumps(intended_opening(expected_opening())) + "\n",
                encoding="utf-8",
            )
        self.commit_repository_paths(root, message=f"Create {slug}")
        return root

    def create_guide_source(self, skill_text: str = "# Skill\n") -> Path:
        self.guide_counter += 1
        root = Path(self.temporary_directory.name) / f"guide-{self.guide_counter}"
        skill = root / "skills" / "traigent-first-run"
        (skill / "scripts").mkdir(parents=True)
        (root / "GUIDE.md").write_text("# First run\n", encoding="utf-8")
        (root / "README.md").write_text("read me\n", encoding="utf-8")
        (root / "LICENSE").write_text("license\n", encoding="utf-8")
        (root / "NOTICE").write_text(
            "Test guide\nCopyright 2026 Traigent Ltd\n", encoding="utf-8"
        )
        (root / "AGENTS.md").write_text("agent rules\n", encoding="utf-8")
        (skill / "SKILL.md").write_text(skill_text, encoding="utf-8")
        script = skill / "scripts" / "readiness.py"
        script.write_text("print('inert')\n", encoding="utf-8")
        script.chmod(0o755)
        (root / ".env").write_text("MUST_NOT_COPY=1\n", encoding="utf-8")
        (root / "private-notes.md").write_text("not allowlisted\n", encoding="utf-8")
        ignored_cache = skill / "scripts" / "__pycache__"
        ignored_cache.mkdir()
        (ignored_cache / "readiness.pyc").write_bytes(b"untracked cache")
        subprocess.run(["git", "init", "-q", os.fspath(root)], check=True)
        subprocess.run(
            [
                "git",
                "-C",
                os.fspath(root),
                "add",
                "GUIDE.md",
                "README.md",
                "LICENSE",
                "NOTICE",
                "AGENTS.md",
                "skills/traigent-first-run/SKILL.md",
                "skills/traigent-first-run/scripts/readiness.py",
            ],
            check=True,
        )
        subprocess.run(
            [
                "git",
                "-C",
                os.fspath(root),
                "update-index",
                "--chmod=+x",
                "--",
                "skills/traigent-first-run/scripts/readiness.py",
            ],
            check=True,
        )
        subprocess.run(
            [
                "git",
                "-C",
                os.fspath(root),
                "-c",
                "user.name=Scenario Tests",
                "-c",
                "user.email=scenario-tests@example.invalid",
                "commit",
                "-qm",
                "Create test guide",
            ],
            check=True,
        )
        return root

    def write_result(
        self,
        value: object,
        *,
        name: str = "opening-result.json",
    ) -> Path:
        path = Path(self.temporary_directory.name) / name
        path.write_text(json.dumps(value) + "\n", encoding="utf-8")
        return path

    def run_cli(self, *arguments: str) -> tuple[int, str, str]:
        output = io.StringIO()
        error = io.StringIO()
        status = scenario.main(
            list(arguments),
            scenarios_dir=self.scenarios_dir,
            repository_root=self.repository_root,
            output=output,
            error=error,
        )
        return status, output.getvalue(), error.getvalue()

    def prepare_run_record(
        self,
        reference: str,
        *,
        name: str,
        skill_text: str = "# Skill\n",
    ) -> Path:
        guide_source = self.create_guide_source(skill_text)
        output_path = Path(self.temporary_directory.name) / name
        status, _, error = self.run_cli(
            "prepare",
            reference,
            "--guide-src",
            str(guide_source),
            "--output",
            str(output_path),
        )
        self.assertEqual(0, status, error)
        return output_path / "run.json"

    def test_discovers_valid_scenario_and_resolves_slug_or_legacy_id(self) -> None:
        self.create_scenario("incident-triage", 46)
        bank = scenario.ScenarioBank(
            self.scenarios_dir, repository_root=self.repository_root
        )

        discovered = bank.discover()

        self.assertEqual(1, len(discovered))
        self.assertEqual("incident-triage", discovered[0].slug)
        self.assertIs(discovered[0], bank.resolve("incident-triage", discovered))
        self.assertIs(discovered[0], bank.resolve("046", discovered))

        status, output, error = self.run_cli("check", "46")
        self.assertEqual(0, status)
        self.assertIn("OK: incident-triage", output)
        self.assertEqual("", error)

    def test_list_allows_empty_bank_but_check_refuses_false_green(self) -> None:
        list_status, list_output, list_error = self.run_cli("list")
        check_status, check_output, check_error = self.run_cli("check")

        self.assertEqual(0, list_status)
        self.assertEqual("No scenarios found.\n", list_output)
        self.assertEqual("", list_error)
        self.assertNotEqual(0, check_status)
        self.assertEqual("", check_output)
        self.assertIn("refusing to report a successful check", check_error)

    def test_rejects_malformed_manifest_and_unknown_keys(self) -> None:
        root = self.create_scenario("malformed", 1)
        (root / "scenario.json").write_text(
            '{"schema_version": 1, "schema_version": 1}', encoding="utf-8"
        )

        status, output, error = self.run_cli("list")

        self.assertNotEqual(0, status)
        self.assertEqual("", output)
        self.assertIn("duplicate object key", error)

        (root / "scenario.json").write_text(
            json.dumps({**valid_manifest("malformed", 1), "unexpected": True}),
            encoding="utf-8",
        )
        status, _, error = self.run_cli("list")
        self.assertNotEqual(0, status)
        self.assertIn("unknown key(s): unexpected", error)

    def test_rejects_whitespace_text_and_unstable_tags(self) -> None:
        root = self.create_scenario("bad-text", 2)
        for field, value, expected in (
            ("title", " \t", "only whitespace"),
            ("summary", "\n", "only whitespace"),
            ("tags", ["Not-Stable"], "lowercase letters"),
        ):
            with self.subTest(field=field):
                manifest = valid_manifest("bad-text", 2)
                manifest[field] = value
                (root / "scenario.json").write_text(
                    json.dumps(manifest), encoding="utf-8"
                )
                status, _, error = self.run_cli("list")
                self.assertNotEqual(0, status)
                self.assertIn(expected, error)

    def test_rejects_unexpected_file_in_scenarios_directory(self) -> None:
        (self.scenarios_dir / "archive.json").write_text("{}\n", encoding="utf-8")

        status, output, error = self.run_cli("check")

        self.assertNotEqual(0, status)
        self.assertEqual("", output)
        self.assertIn("unexpected non-directory scenario entry", error)

    def test_rejects_duplicate_legacy_ids(self) -> None:
        self.create_scenario("first", 7)
        self.create_scenario("second", 7)

        status, output, error = self.run_cli("check")

        self.assertNotEqual(0, status)
        self.assertEqual("", output)
        self.assertIn("duplicate legacy_id 7", error)
        self.assertIn("'first'", error)
        self.assertIn("'second'", error)

    def test_reports_ambiguous_and_missing_case_references(self) -> None:
        self.create_scenario("46", 99)
        self.create_scenario("another-case", 46)
        bank = scenario.ScenarioBank(
            self.scenarios_dir, repository_root=self.repository_root
        )
        discovered = bank.discover()

        with self.assertRaisesRegex(scenario.CaseLookupError, "ambiguous"):
            bank.resolve("46", discovered)
        with self.assertRaisesRegex(scenario.CaseLookupError, "was not found"):
            bank.resolve("missing-case", discovered)

        status, output, error = self.run_cli("show", "46")
        self.assertNotEqual(0, status)
        self.assertEqual("", output)
        self.assertIn("ambiguous", error)

        oversized_reference = "9" * 5000
        status, output, error = self.run_cli("show", oversized_reference)
        self.assertNotEqual(0, status)
        self.assertEqual("", output)
        self.assertIn("numeric scenario reference", error)

    def test_json_schema_contract_matches_runtime_constants(self) -> None:
        manifest_schema = json.loads(
            (scenario.REPOSITORY_ROOT / "schema" / "scenario.schema.json").read_text(
                encoding="utf-8"
            )
        )
        properties = manifest_schema["properties"]
        definitions = manifest_schema["$defs"]
        catalog_schema = properties["catalog"]
        catalog_properties = catalog_schema["properties"]
        component_schema = catalog_properties["components"]
        component_properties = component_schema["properties"]
        dataset_schema = definitions["dataset"]
        dataset_properties = dataset_schema["properties"]

        Draft202012Validator.check_schema(manifest_schema)

        self.assertEqual(scenario.REQUIRED_KEYS, set(manifest_schema["required"]))
        self.assertEqual(scenario.SCHEMA_VERSION, properties["schema_version"]["const"])
        self.assertEqual(scenario.SLUG_PATTERN.pattern, properties["slug"]["pattern"])
        self.assertEqual(scenario.MAX_SLUG_LENGTH, properties["slug"]["maxLength"])
        self.assertEqual(scenario.MAX_TITLE_LENGTH, properties["title"]["maxLength"])
        self.assertEqual(
            scenario.MAX_SUMMARY_LENGTH, properties["summary"]["maxLength"]
        )
        self.assertEqual(scenario.PHASE, properties["phase"]["const"])
        self.assertEqual(
            scenario.CONTENT_ORIGIN,
            properties["content"]["properties"]["origin"]["const"],
        )
        self.assertEqual(
            scenario.CONTENT_LICENSE,
            properties["content"]["properties"]["license"]["const"],
        )
        self.assertEqual(scenario.MAX_TAGS, properties["tags"]["maxItems"])
        self.assertEqual(
            scenario.MAX_TAG_LENGTH, properties["tags"]["items"]["maxLength"]
        )
        self.assertEqual(
            scenario.CATALOG_KEYS,
            set(catalog_schema["required"]),
        )
        self.assertEqual(
            scenario.COMPONENT_KEYS,
            set(component_schema["required"]),
        )
        self.assertEqual(
            scenario.AGENT_COMPONENT_KEYS,
            set(component_properties["agent"]["required"]),
        )
        self.assertEqual(
            scenario.DATA_COMPONENT_KEYS,
            set(component_properties["data"]["required"]),
        )
        self.assertEqual(
            scenario.EVALUATOR_COMPONENT_KEYS,
            set(component_properties["evaluator"]["required"]),
        )
        self.assertEqual(
            scenario.CALIBRATION_KEYS,
            set(
                component_properties["evaluator"]["properties"]["calibration"][
                    "required"
                ]
            ),
        )
        self.assertEqual(scenario.DATASET_KEYS, set(dataset_schema["required"]))
        for optional_key in scenario.OPTIONAL_DATASET_KEYS:
            self.assertIn(optional_key, dataset_properties)
            self.assertNotIn(optional_key, dataset_schema["required"])
        for optional_key in scenario.OPTIONAL_CATALOG_KEYS:
            self.assertIn(optional_key, catalog_properties)
            self.assertNotIn(optional_key, catalog_schema["required"])
        self.assertEqual(
            scenario.COUNT_DIMENSION_KEYS,
            set(definitions["countDimension"]["required"]),
        )
        self.assertEqual(
            scenario.LABEL_SHAPE_KEYS,
            set(definitions["labelShape"]["required"]),
        )
        self.assertEqual(
            scenario.EXPECTED_ROUTE_KEYS,
            set(catalog_properties["expected_route"]["required"]),
        )
        self.assertEqual(
            scenario.EVIDENCE_KEYS,
            set(catalog_properties["evidence"]["required"]),
        )
        self.assertEqual(
            scenario.STARTING_CONDITIONS,
            set(catalog_properties["starting_condition"]["enum"]),
        )
        self.assertEqual(
            scenario.COMPONENT_STATES,
            set(definitions["componentState"]["enum"]),
        )
        self.assertEqual(
            scenario.LABEL_SHAPES,
            set(definitions["labelShape"]["properties"]["kind"]["enum"]),
        )
        self.assertEqual(
            scenario.EVALUATOR_METHODS,
            set(definitions["evaluatorMethod"]["enum"]),
            "the evaluator method decides how many labels a catalog may claim, "
            "so the schema and the runtime must offer the same closed set",
        )
        self.assertEqual(
            scenario.MAPPED_LABEL_SHAPE,
            "mapped-labels",
        )
        self.assertEqual(
            scenario.DATASET_FORMATS,
            {
                value
                for value in dataset_properties["format"]["enum"]
                if value is not None
            },
        )
        self.assertEqual(
            scenario.SCENARIO_PATH_PATTERN.pattern,
            definitions["relativePath"]["pattern"],
        )
        self.assertEqual(
            scenario.EXPECTED_VERIFIER_CONTRACT,
            catalog_properties["expected_route"]["properties"]["verifier_contract"][
                "const"
            ],
        )

    def test_json_schema_and_runtime_share_portable_manifest_rules(self) -> None:
        manifest_schema = json.loads(
            (scenario.REPOSITORY_ROOT / "schema" / "scenario.schema.json").read_text(
                encoding="utf-8"
            )
        )
        validator = Draft202012Validator(manifest_schema)
        scenario_root = self.repository_root / "parity-case"
        manifest_path = scenario_root / "scenario.json"
        base = valid_manifest("parity-case", 90)
        cases: list[tuple[str, dict[str, object], bool]] = []

        def clone() -> dict[str, object]:
            return json.loads(json.dumps(base))

        cases.append(("ready base", clone(), True))

        spaced_path = clone()
        spaced_path["catalog"]["components"]["agent"][
            "path"
        ] = "project/agent fixtures/分类.py"
        cases.append(("normalized path with spaces and Unicode", spaced_path, True))

        control_path = clone()
        control_path["catalog"]["components"]["agent"][
            "path"
        ] = "project/agent\nname.py"
        cases.append(("path containing a control character", control_path, False))

        missing_agent = clone()
        missing_agent["catalog"]["starting_condition"] = "gaps-present"
        missing_agent["catalog"]["components"]["agent"] = {
            "state": "missing",
            "path": None,
            "controls": [],
        }
        cases.append(("missing agent", missing_agent, True))

        missing_agent_with_path = json.loads(json.dumps(missing_agent))
        missing_agent_with_path["catalog"]["components"]["agent"][
            "path"
        ] = "project/agent.py"
        cases.append(("missing agent with a path", missing_agent_with_path, False))

        ready_agent_without_controls = clone()
        ready_agent_without_controls["catalog"]["components"]["agent"]["controls"] = []
        cases.append(
            ("ready agent without controls", ready_agent_without_controls, False)
        )

        missing_evaluator = clone()
        missing_evaluator["catalog"]["starting_condition"] = "gaps-present"
        missing_evaluator["catalog"]["components"]["evaluator"] = {
            "state": "missing",
            "path": None,
            "method": None,
            "calibration": {"path": None, "case_count": 0},
        }
        cases.append(("missing evaluator", missing_evaluator, True))

        inconsistent_calibration = clone()
        inconsistent_calibration["catalog"]["components"]["evaluator"][
            "calibration"
        ] = {"path": "project/calibration.json", "case_count": 0}
        cases.append(
            ("calibration path with zero cases", inconsistent_calibration, False)
        )

        missing_dataset = clone()
        missing_dataset["catalog"]["starting_condition"] = "gaps-present"
        missing_dataset["catalog"]["components"]["data"] = {
            "state": "missing",
            "paths": [],
        }
        missing_dataset["catalog"]["datasets"][0].update(
            {
                "state": "missing",
                "path": None,
                "format": None,
                "label_field": None,
                "rows": 0,
                "unique_inputs": 0,
                "splits": {"field": None, "counts": {}},
                "difficulty_strata": {"field": None, "counts": {}},
                "label_shape": {
                    "kind": "absent",
                    "surface_label_count": 0,
                    "label_counts": {},
                },
            }
        )
        cases.append(("missing dataset", missing_dataset, True))

        missing_dataset_with_rows = json.loads(json.dumps(missing_dataset))
        missing_dataset_with_rows["catalog"]["datasets"][0]["rows"] = 1
        cases.append(("missing dataset with rows", missing_dataset_with_rows, False))

        missing_dataset_with_passthrough = json.loads(json.dumps(missing_dataset))
        missing_dataset_with_passthrough["catalog"]["datasets"][0][
            "passthrough_fields"
        ] = ["ghost_column"]
        cases.append(
            (
                "missing dataset with a passthrough declaration",
                missing_dataset_with_passthrough,
                False,
            )
        )

        present_dataset_without_rows = clone()
        present_dataset_without_rows["catalog"]["datasets"][0]["rows"] = 0
        cases.append(
            ("present dataset without rows", present_dataset_without_rows, False)
        )

        counts_without_field = clone()
        counts_without_field["catalog"]["datasets"][0]["splits"]["field"] = None
        cases.append(("counts without a field", counts_without_field, False))

        gaps_without_a_gap = clone()
        gaps_without_a_gap["catalog"]["starting_condition"] = "gaps-present"
        cases.append(
            ("gaps-present with all components ready", gaps_without_a_gap, False)
        )

        ready_data_with_limited_dataset = clone()
        ready_data_with_limited_dataset["catalog"]["datasets"][0]["state"] = "limited"
        cases.append(
            (
                "ready data component with limited dataset",
                ready_data_with_limited_dataset,
                False,
            )
        )

        for label, candidate, expected_acceptance in cases:
            with self.subTest(label=label):
                schema_errors = list(validator.iter_errors(candidate))
                try:
                    scenario._validate_manifest(
                        manifest_path,
                        scenario_root,
                        self.repository_root,
                        candidate,
                    )
                except scenario.ManifestError:
                    runtime_accepts = False
                else:
                    runtime_accepts = True

                self.assertEqual(
                    expected_acceptance,
                    not schema_errors,
                    [error.message for error in schema_errors],
                )
                self.assertEqual(expected_acceptance, runtime_accepts)

    def test_catalog_is_required_and_nested_objects_are_strict(self) -> None:
        root = self.create_scenario("strict-catalog", 80)

        missing_catalog = valid_manifest("strict-catalog", 80)
        del missing_catalog["catalog"]
        (root / "scenario.json").write_text(
            json.dumps(missing_catalog),
            encoding="utf-8",
        )
        status, _, error = self.run_cli("list")
        self.assertNotEqual(0, status)
        self.assertIn("missing required key(s): catalog", error)

        unknown_nested = valid_manifest("strict-catalog", 80)
        unknown_nested["catalog"]["components"]["agent"]["sales_copy"] = "ready"
        (root / "scenario.json").write_text(
            json.dumps(unknown_nested),
            encoding="utf-8",
        )
        status, _, error = self.run_cli("list")
        self.assertNotEqual(0, status)
        self.assertIn("unknown key(s): sales_copy", error)

        wrong_contract = valid_manifest("strict-catalog", 80)
        wrong_contract["catalog"]["expected_route"][
            "verifier_contract"
        ] = "verifier/another-contract.json"
        (root / "scenario.json").write_text(
            json.dumps(wrong_contract),
            encoding="utf-8",
        )
        status, _, error = self.run_cli("list")
        self.assertNotEqual(0, status)
        self.assertIn("must equal 'verifier/expected-opening.json'", error)

    def test_catalog_can_describe_explicit_gap_dimensions(self) -> None:
        root = self.create_scenario("limited-data", 81)
        manifest = valid_manifest("limited-data", 81)
        catalog = manifest["catalog"]
        catalog["starting_condition"] = "gaps-present"
        catalog["components"]["agent"]["state"] = "needs-repair"
        catalog["components"]["agent"]["controls"] = []
        catalog["components"]["data"]["state"] = "limited"
        dataset = catalog["datasets"][0]
        dataset["state"] = "limited"
        dataset["splits"] = {"field": None, "counts": {}}
        dataset["difficulty_strata"] = {"field": None, "counts": {}}
        # Dropping the split and difficulty dimensions leaves the rows' metadata
        # column described by nothing, which is what passthrough_fields is for.
        dataset["passthrough_fields"] = ["metadata"]
        dataset["label_shape"] = {
            "kind": "free-text",
            "surface_label_count": 0,
            "label_counts": {},
        }
        (root / "scenario.json").write_text(
            json.dumps(manifest),
            encoding="utf-8",
        )

        status, output, error = self.run_cli("check", "limited-data")

        self.assertEqual(0, status, error)
        self.assertIn("OK: limited-data", output)

        # Declaring the data missing means the rows stop shipping: `prepare`
        # hands a worker every tracked file under project/, so a dataset that
        # stays in the checkout is one the worker finds.
        self.remove_repository_paths(
            root / "project" / "input.txt",
            message="Stop shipping the dataset",
        )
        catalog["components"]["data"] = {"state": "missing", "paths": []}
        dataset.update(
            {
                "state": "missing",
                "path": None,
                "format": None,
                "label_field": None,
                "rows": 0,
                "unique_inputs": 0,
                "label_shape": {
                    "kind": "absent",
                    "surface_label_count": 0,
                    "label_counts": {},
                },
                # A missing dataset ships no rows, so a passthrough describing
                # its columns would describe nothing and is refused.
                "passthrough_fields": [],
            }
        )
        (root / "scenario.json").write_text(
            json.dumps(manifest),
            encoding="utf-8",
        )

        status, output, error = self.run_cli("check", "limited-data")

        self.assertEqual(0, status, error)
        self.assertIn("OK: limited-data", output)

    def write_dataset(self, root: Path, *labels: str) -> None:
        rows = "".join(
            json.dumps(
                {
                    "input": f"example-{index}",
                    "output": label,
                    "metadata": {"split": "tuning", "difficulty": "easy"},
                }
            )
            + "\n"
            for index, label in enumerate(labels)
        )
        (root / "project" / "input.txt").write_text(rows, encoding="utf-8")

    def labelled_manifest(
        self,
        slug: str,
        legacy_id: int,
        *,
        rows: int,
        label_counts: dict[str, int],
    ) -> dict[str, object]:
        manifest = valid_manifest(slug, legacy_id)
        catalog = manifest["catalog"]
        assert isinstance(catalog, dict)
        dataset = catalog["datasets"][0]
        dataset.update(
            {
                "rows": rows,
                "unique_inputs": rows,
                "splits": {"field": "metadata.split", "counts": {"tuning": rows}},
                "difficulty_strata": {
                    "field": "metadata.difficulty",
                    "counts": {"easy": rows},
                },
                "label_shape": {
                    "kind": "mapped-labels",
                    "surface_label_count": len(label_counts),
                    "label_counts": label_counts,
                },
            }
        )
        return manifest

    def write_evaluator(self, root: Path, source: str) -> None:
        (root / "project" / "evaluator.py").write_text(source, encoding="utf-8")

    def write_manifest(self, root: Path, manifest: dict[str, object]) -> None:
        (root / "scenario.json").write_text(json.dumps(manifest), encoding="utf-8")

    def test_declared_label_counts_must_match_the_rows_that_ship(self) -> None:
        """The catalog's label facts are facts about the bytes, checked against them."""

        root = self.create_scenario("counted-labels", 90)
        self.write_dataset(root, "SEV1", "SEV1", "SEV2")
        self.write_manifest(
            root,
            self.labelled_manifest(
                "counted-labels",
                90,
                rows=3,
                label_counts={"SEV1": 1, "SEV2": 2},
            ),
        )

        status, output, error = self.run_cli("check", "counted-labels")

        self.assertNotEqual(0, status, output)
        self.assertEqual("", output)
        self.assertIn("declares {'SEV1': 1, 'SEV2': 2}", error)
        self.assertIn("carries {'SEV1': 2, 'SEV2': 1}", error)

        self.write_manifest(
            root,
            self.labelled_manifest(
                "counted-labels",
                90,
                rows=3,
                label_counts={"SEV1": 2, "SEV2": 1},
            ),
        )

        status, output, error = self.run_cli("check", "counted-labels")

        self.assertEqual(0, status, error)
        self.assertIn("OK: counted-labels", output)

    def test_a_label_string_the_catalog_does_not_list_is_refused(self) -> None:
        root = self.create_scenario("unlisted-label", 91)
        self.write_dataset(root, "SEV1", "SEV9")
        self.write_manifest(
            root,
            self.labelled_manifest(
                "unlisted-label",
                91,
                rows=2,
                label_counts={"SEV1": 2},
            ),
        )

        status, output, error = self.run_cli("check", "unlisted-label")

        self.assertNotEqual(0, status, output)
        self.assertEqual("", output)
        self.assertIn("does not cover observed label 'SEV9'", error)

    def test_spellings_that_differ_only_in_case_are_separate_label_strings(
        self,
    ) -> None:
        """The catalog counts strings, because strings are what the rows carry.

        Whether an evaluator folds ``SEV1`` and ``sev1`` together is a fact
        about the evaluator at run time. It is not asserted here, so it cannot
        be forged here, and the catalog describes the twelve-or-so spellings a
        reader would find by opening the file.
        """

        root = self.create_scenario("case-varied-labels", 92)
        self.write_dataset(root, "SEV1", "sev1", "Sev-1")
        self.write_manifest(
            root,
            self.labelled_manifest(
                "case-varied-labels",
                92,
                rows=3,
                label_counts={"SEV1": 1, "sev1": 1, "Sev-1": 1},
            ),
        )

        status, output, error = self.run_cli("check", "case-varied-labels")

        self.assertEqual(0, status, error)
        self.assertIn("OK: case-varied-labels", output)

    def test_the_manifest_contract_carries_no_claim_about_the_evaluator(self) -> None:
        """The forgeable claim is removed from the contract, not merely unchecked.

        ``normalization_map`` and ``normalized_class_count`` said which
        spellings the evaluator scores alike, which is a property of the
        evaluator when it runs. Nothing that never runs it can establish that,
        so the contract no longer has the words for it.
        """

        self.assertEqual(
            {"kind", "label_counts", "surface_label_count"},
            scenario.LABEL_SHAPE_KEYS,
        )

        removed_keys = ("normalization_map", "normalized_class_count")
        for index, removed in enumerate(removed_keys):
            with self.subTest(key=removed):
                slug = f"legacy-claim-{index}"
                root = self.create_scenario(slug, 93 + index)
                manifest = valid_manifest(slug, 93 + index)
                catalog = manifest["catalog"]
                assert isinstance(catalog, dict)
                catalog["datasets"][0]["label_shape"][removed] = {}
                self.write_manifest(root, manifest)

                status, output, error = self.run_cli("check", slug)
                self.write_manifest(root, valid_manifest(slug, 93 + index))

                self.assertNotEqual(0, status, output)
                self.assertIn(removed, error)

    def test_what_an_evaluator_tells_apart_is_never_read_from_its_source(self) -> None:
        """A published evaluator is customer-shaped code, not a declaration.

        Reading a dict literal out of it and calling that literal the
        evaluator's table was forgeable in two lines and refused honest
        evaluators in seven shapes at once. None of these sources says anything
        the catalog is checked against, so all of them are accepted -- and a
        collapsed table is neither caught nor claimed.
        """

        root = self.create_scenario("evaluator-shapes", 94)
        self.write_dataset(root, "SEV1", "SEV1", "SEV2", "SEV2")
        self.write_manifest(
            root,
            self.labelled_manifest(
                "evaluator-shapes",
                94,
                rows=4,
                label_counts={"SEV1": 2, "SEV2": 2},
            ),
        )
        head = "# SPDX-License-Identifier: Apache-2.0\n"
        tail = (
            "\n\ndef score(output, expected, input_data=None, metadata=None):\n"
            "    return 1.0 if output == expected else 0.0\n"
        )
        shapes: tuple[tuple[str, str], ...] = (
            (
                "no table at all",
                head + "def score(output, expected):\n    return 0.0\n",
            ),
            (
                "two module-level tables",
                head + 'FIRST = {"sev1": 1}\nSECOND = {"sev1": 2}\n' + tail,
            ),
            (
                "a second dict beside the table",
                head
                + 'LEVELS = {"sev1": 1, "sev2": 2}\nMODES = {"binary": 1.0}\n'
                + tail,
            ),
            (
                "an annotated second dict",
                head
                + 'LEVELS = {"sev1": 1, "sev2": 2}\n'
                + 'BOARD: dict[str, str] = {"owner": "review-board"}\n'
                + tail,
            ),
            (
                "a table built by a call",
                head + "LEVELS = dict(sev1=1, sev2=2)\n" + tail,
            ),
            (
                "table values written int(1)",
                head + 'LEVELS = {"sev1": int(1), "sev2": int(2)}\n' + tail,
            ),
            (
                "an if/elif scorer",
                head
                + "def _level(label):\n"
                + '    if label == "SEV1":\n        return 1\n'
                + '    if label == "SEV2":\n        return 2\n'
                + "    return None\n"
                + tail,
            ),
            (
                "a table on a class, the idiom the SDK uses",
                head
                + "class Grader:\n"
                + '    LEVELS = {"sev1": 1, "sev2": 2}\n'
                + tail,
            ),
            (
                "a table collapsed to one class after it is written",
                head
                + 'LEVELS = {"sev1": 1, "sev2": 2}\n'
                + "LEVELS = dict.fromkeys(LEVELS, 1)\n"
                + tail,
            ),
        )
        for name, source in shapes:
            with self.subTest(evaluator=name):
                self.write_evaluator(root, source)
                self.commit_repository_paths(root, message=f"Ship {name}")

                status, output, error = self.run_cli("check", "evaluator-shapes")

                self.assertEqual(0, status, error)
                self.assertIn("OK: evaluator-shapes", output)

    def test_a_component_declared_missing_may_not_ship_its_own_source(self) -> None:
        """`state` cannot deny a component whose source lands in the checkout.

        ``missing`` forces the component's ``path`` to null, so a check keyed on
        the declared path checks nothing at all here -- which is how the
        declaration used to switch off its own contradiction. The files that
        ship are asked instead.
        """

        cases: tuple[tuple[str, str, bool], ...] = (
            ("needs-repair", "needs-repair", True),
            ("limited", "limited", True),
            ("missing", "missing", False),
        )
        for index, (name, state, accepted) in enumerate(cases):
            with self.subTest(state=name):
                slug = f"evaluator-{name}"
                root = self.create_scenario(slug, 180 + index)
                manifest = valid_manifest(slug, 180 + index)
                catalog = manifest["catalog"]
                assert isinstance(catalog, dict)
                catalog["starting_condition"] = "gaps-present"
                evaluator = catalog["components"]["evaluator"]
                evaluator["state"] = state
                if state == "missing":
                    evaluator["path"] = None
                    evaluator["method"] = None
                self.write_manifest(root, manifest)

                status, output, error = self.run_cli("check", slug)

                if accepted:
                    self.assertEqual(0, status, error)
                    self.assertIn(f"OK: {slug}", output)
                else:
                    self.assertNotEqual(
                        0,
                        status,
                        "the evaluator source still reaches the worker, so a "
                        "catalog that denies the component is contradicted by "
                        "its own bytes",
                    )
                    self.assertIn("project/evaluator.py", error)

    def test_a_missing_component_cannot_be_laundered_as_a_non_dataset_file(
        self,
    ) -> None:
        """Naming the source under another key does not make the component absent."""

        root = self.create_scenario("laundered-evaluator", 184)
        manifest = valid_manifest("laundered-evaluator", 184)
        catalog = manifest["catalog"]
        assert isinstance(catalog, dict)
        catalog["starting_condition"] = "gaps-present"
        catalog["components"]["evaluator"].update(
            {"state": "missing", "path": None, "method": None}
        )
        catalog["non_dataset_files"] = ["project/evaluator.py"]
        self.write_manifest(root, manifest)

        status, output, error = self.run_cli("check", "laundered-evaluator")

        self.assertNotEqual(0, status, output)
        self.assertIn("declares this component missing", error)
        self.assertIn("project/evaluator.py", error)

    def test_a_dataset_that_claims_no_label_surface_needs_no_label_counts(
        self,
    ) -> None:
        """A gap scenario models a broken evaluator; it owes no label list."""

        root = self.create_scenario("free-text-task", 161)
        self.write_evaluator(
            root,
            "def score(output, expected):\n    raise NotImplementedError\n",
        )
        manifest = valid_manifest("free-text-task", 161)
        catalog = manifest["catalog"]
        assert isinstance(catalog, dict)
        catalog["datasets"][0]["label_shape"] = {
            "kind": "free-text",
            "surface_label_count": 0,
            "label_counts": {},
        }
        self.write_manifest(root, manifest)
        self.commit_repository_paths(root, message="Ship an unimplemented evaluator")

        status, output, error = self.run_cli("check", "free-text-task")

        self.assertEqual(0, status, error)
        self.assertIn("OK: free-text-task", output)

    def test_an_unmapped_label_surface_declares_a_count_and_not_a_list(self) -> None:
        root = self.create_scenario("unmapped-labels", 163)
        self.write_dataset(root, "SEV1", "SEV2", "SEV2")
        manifest = self.labelled_manifest(
            "unmapped-labels", 163, rows=3, label_counts={"SEV1": 1, "SEV2": 2}
        )
        catalog = manifest["catalog"]
        assert isinstance(catalog, dict)
        catalog["datasets"][0]["label_shape"] = {
            "kind": "unmapped-labels",
            "surface_label_count": 3,
            "label_counts": {},
        }
        self.write_manifest(root, manifest)

        status, output, error = self.run_cli("check", "unmapped-labels")

        self.assertNotEqual(0, status, output)
        self.assertIn("carries 2 distinct label strings", error)

        catalog["datasets"][0]["label_shape"]["surface_label_count"] = 2
        self.write_manifest(root, manifest)

        status, output, error = self.run_cli("check", "unmapped-labels")

        self.assertEqual(0, status, error)
        self.assertIn("OK: unmapped-labels", output)

    def write_calibration(self, root: Path, *cases: dict[str, object]) -> None:
        (root / "project" / "calibration.json").write_text(
            json.dumps(list(cases), indent=2) + "\n", encoding="utf-8"
        )

    def calibrated_manifest(
        self,
        slug: str,
        legacy_id: int,
        *,
        case_count: int,
    ) -> dict[str, object]:
        manifest = self.labelled_manifest(
            slug,
            legacy_id,
            rows=3,
            label_counts={"SEV1": 1, "P1": 1, "SEV2": 1},
        )
        catalog = manifest["catalog"]
        assert isinstance(catalog, dict)
        catalog["components"]["evaluator"]["calibration"] = {
            "path": "project/calibration.json",
            "case_count": case_count,
        }
        return manifest

    def test_calibration_probes_must_be_named_non_empty_labels(self) -> None:
        """What the calibration file's own bytes settle is still checked."""

        malformed: tuple[tuple[str, dict[str, object], str], ...] = (
            (
                "probes are not an object",
                {"expected": "SEV1", "probes": ["good"]},
                "must be a JSON object",
            ),
            (
                "no recorded label to probe against",
                {"probes": {"good": "SEV1"}},
                "needs a non-empty 'expected' label",
            ),
            (
                "a blank probe label",
                {"expected": "SEV1", "probes": {"good": "   "}},
                "must be a non-empty string",
            ),
            (
                "a probe name this contract does not know",
                {"expected": "SEV1", "probes": {"nearly_good": "P1"}},
                "declares probes this contract does not know",
            ),
        )
        for index, (name, case, expected_error) in enumerate(malformed):
            with self.subTest(case=name):
                slug = f"calibration-{index}"
                root = self.create_scenario(slug, 100 + index)
                self.write_dataset(root, "SEV1", "P1", "SEV2")
                self.write_calibration(root, case)
                self.write_manifest(
                    root, self.calibrated_manifest(slug, 100 + index, case_count=1)
                )
                self.commit_repository_paths(root, message=f"Ship {slug}")

                status, output, error = self.run_cli("check", slug)

                self.assertNotEqual(0, status, output)
                self.assertEqual("", output)
                self.assertIn(expected_error, error)

    def test_a_probe_may_name_a_spelling_no_row_carries(self) -> None:
        """A probe states what the evaluator does, and it is never run here.

        The published calibration file relies on exactly this: it probes
        ``equivalent_good: "sev4"`` against a recorded ``"Low"``. Whether those
        two score alike is the evaluator's business at run time, so tying the
        probe to the dataset's spellings would refuse an honest file to enforce
        a claim this check cannot make.
        """

        root = self.create_scenario("calibration-ok", 110)
        self.write_dataset(root, "SEV1", "P1", "SEV2")
        self.write_calibration(
            root,
            {
                "expected": "SEV1",
                "probes": {
                    "good": "SEV1",
                    "equivalent_good": "sev1",
                    "partial": "SEV2",
                    "bad": "Low",
                },
            },
        )
        self.write_manifest(
            root, self.calibrated_manifest("calibration-ok", 110, case_count=1)
        )
        self.commit_repository_paths(root, message="Ship a calibration file")

        status, output, error = self.run_cli("check", "calibration-ok")

        self.assertEqual(0, status, error)
        self.assertIn("OK: calibration-ok", output)

    def test_absent_label_shape_must_match_the_rows_that_ship(self) -> None:
        root = self.create_scenario("denied-labels", 120)
        manifest = valid_manifest("denied-labels", 120)
        catalog = manifest["catalog"]
        assert isinstance(catalog, dict)
        dataset = catalog["datasets"][0]
        dataset.update(
            {
                "label_field": None,
                "label_shape": {
                    "kind": "absent",
                    "surface_label_count": 0,
                    "label_counts": {},
                },
            }
        )
        self.write_manifest(root, manifest)

        status, output, error = self.run_cli("check", "denied-labels")

        self.assertNotEqual(0, status)
        self.assertEqual("", output)
        self.assertIn("claims this dataset carries no labels", error)
        self.assertIn("also carries output", error)

        (root / "project" / "input.txt").write_text(
            json.dumps(
                {
                    "input": "example",
                    "metadata": {"split": "tuning", "difficulty": "easy"},
                }
            )
            + "\n",
            encoding="utf-8",
        )

        status, output, error = self.run_cli("check", "denied-labels")

        self.assertEqual(0, status, error)
        self.assertIn("OK: denied-labels", output)

    def write_rows(self, root: Path, rows: list[dict[str, object]]) -> None:
        (root / "project" / "input.txt").write_text(
            "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
        )

    def test_a_column_the_task_does_not_use_can_be_declared(self) -> None:
        """An unlabeled dataset may still carry an ordinary row_id column."""

        root = self.create_scenario("unlabeled-row-id", 170)
        self.write_rows(
            root,
            [
                {
                    "input": "example",
                    "row_id": 1,
                    "metadata": {"split": "tuning", "difficulty": "easy"},
                }
            ],
        )
        manifest = valid_manifest("unlabeled-row-id", 170)
        catalog = manifest["catalog"]
        assert isinstance(catalog, dict)
        dataset = catalog["datasets"][0]
        dataset["label_field"] = None
        dataset["label_shape"] = {
            "kind": "absent",
            "surface_label_count": 0,
            "label_counts": {},
        }
        self.write_manifest(root, manifest)

        status, output, error = self.run_cli("check", "unlabeled-row-id")

        self.assertNotEqual(0, status, output)
        self.assertIn("which the catalog does not describe", error)

        dataset["passthrough_fields"] = ["row_id"]
        self.write_manifest(root, manifest)

        status, output, error = self.run_cli("check", "unlabeled-row-id")

        self.assertEqual(
            0,
            status,
            "a column the catalog names is a column a captain can see, which is "
            f"what this check is for: {error}",
        )
        self.assertIn("OK: unlabeled-row-id", output)

    def test_every_label_kind_accounts_for_the_columns_its_rows_carry(self) -> None:
        """The same undeclared column must not pass merely because labels are mapped."""

        root = self.create_scenario("mapped-row-id", 171)
        self.write_rows(
            root,
            [
                {
                    "input": "example",
                    "output": "A",
                    "row_id": 1,
                    "source_tool": "legacy",
                    "metadata": {"split": "tuning", "difficulty": "easy"},
                }
            ],
        )

        status, output, error = self.run_cli("check", "mapped-row-id")

        self.assertNotEqual(
            0,
            status,
            "a mapped-labels dataset receives the same undeclared columns an "
            "unlabeled one does, so it cannot be held to a looser rule",
        )
        self.assertIn("row_id, source_tool", error)

        manifest = valid_manifest("mapped-row-id", 171)
        catalog = manifest["catalog"]
        assert isinstance(catalog, dict)
        catalog["datasets"][0]["passthrough_fields"] = ["row_id", "source_tool"]
        self.write_manifest(root, manifest)

        status, output, error = self.run_cli("check", "mapped-row-id")

        self.assertEqual(0, status, error)
        self.assertIn("OK: mapped-row-id", output)

    def test_a_declared_passthrough_column_must_be_one_the_rows_carry(self) -> None:
        root = self.create_scenario("stale-passthrough", 172)
        manifest = valid_manifest("stale-passthrough", 172)
        catalog = manifest["catalog"]
        assert isinstance(catalog, dict)
        catalog["datasets"][0]["passthrough_fields"] = ["row_id"]
        self.write_manifest(root, manifest)

        status, output, error = self.run_cli("check", "stale-passthrough")

        self.assertNotEqual(0, status, output)
        self.assertIn("which no row carries", error)

    def test_a_passthrough_column_may_not_hide_a_closed_label_surface(self) -> None:
        """`passthrough_fields` names content the task does not use, not the label.

        This vocabulary was added in the same change that stopped a dataset
        declaring itself unlabeled while labelled rows shipped, and it reopened
        that hole: name the label column a passthrough and the claim stood
        again. A column whose values are a small repeating set of strings is a
        label surface whatever the catalog calls it.
        """

        root = self.create_scenario("hidden-labels", 177)
        manifest = valid_manifest("hidden-labels", 177)
        catalog = manifest["catalog"]
        assert isinstance(catalog, dict)
        dataset = catalog["datasets"][0]
        dataset.update(
            {
                "label_field": None,
                "label_shape": {
                    "kind": "absent",
                    "surface_label_count": 0,
                    "label_counts": {},
                },
                "passthrough_fields": ["output"],
                "rows": 8,
                "unique_inputs": 8,
                "splits": {"field": "metadata.split", "counts": {"tuning": 8}},
                "difficulty_strata": {
                    "field": "metadata.difficulty",
                    "counts": {"easy": 8},
                },
            }
        )
        self.write_manifest(root, manifest)
        self.write_rows(
            root,
            [
                {
                    "input": f"example-{index}",
                    "output": "SEV1" if index % 2 else "SEV2",
                    "metadata": {"split": "tuning", "difficulty": "easy"},
                }
                for index in range(8)
            ],
        )

        status, output, error = self.run_cli("check", "hidden-labels")

        self.assertNotEqual(
            0,
            status,
            "declaring the label column a passthrough is the same false claim "
            "the absent shape used to make on its own",
        )
        self.assertEqual("", output)
        self.assertIn("the shape of a label", error)

        self.write_rows(
            root,
            [
                {
                    "input": f"example-{index}",
                    "output": f"ticket-{index}",
                    "metadata": {"split": "tuning", "difficulty": "easy"},
                }
                for index in range(8)
            ],
        )

        status, output, error = self.run_cli("check", "hidden-labels")

        self.assertEqual(
            0,
            status,
            "a column whose value is different in every row is an identifier, "
            f"which is exactly what a passthrough column is for: {error}",
        )
        self.assertIn("OK: hidden-labels", output)

    def test_a_row_shaped_file_that_is_not_task_data_can_be_declared(self) -> None:
        """A run record under project/ is not a dataset, and saying so is honest."""

        root = self.create_scenario("run-records", 173)
        records = root / "project" / "traigent-runs" / "events.jsonl"
        records.parent.mkdir()
        records.write_text(
            "".join(
                json.dumps({"event": name, "sequence": index}) + "\n"
                for index, name in enumerate(("started", "scored", "finished"))
            ),
            encoding="utf-8",
        )
        self.commit_repository_paths(records, message="Ship a run record")

        status, output, error = self.run_cli("check", "run-records")

        self.assertNotEqual(0, status, output)
        self.assertIn("catalog.non_dataset_files", error)

        manifest = valid_manifest("run-records", 173)
        catalog = manifest["catalog"]
        assert isinstance(catalog, dict)
        catalog["non_dataset_files"] = ["project/traigent-runs/events.jsonl"]
        self.write_manifest(root, manifest)

        status, output, error = self.run_cli("check", "run-records")

        self.assertEqual(
            0,
            status,
            "declaring the file is the workaround the catalog should have had; "
            f"calling it a dataset would have been the wrong one: {error}",
        )
        self.assertIn("OK: run-records", output)

    def test_a_declared_non_dataset_file_must_be_one_that_ships(self) -> None:
        root = self.create_scenario("stale-non-dataset", 174)
        manifest = valid_manifest("stale-non-dataset", 174)
        catalog = manifest["catalog"]
        assert isinstance(catalog, dict)
        catalog["non_dataset_files"] = ["project/traigent-runs/events.jsonl"]
        self.write_manifest(root, manifest)

        status, output, error = self.run_cli("check", "stale-non-dataset")

        self.assertNotEqual(0, status, output)
        self.assertIn("catalog.non_dataset_files[0]", error)

        catalog["non_dataset_files"] = ["project/input.txt"]
        self.write_manifest(root, manifest)

        status, output, error = self.run_cli("check", "stale-non-dataset")

        self.assertNotEqual(
            0,
            status,
            "a file cannot be a dataset and not a dataset at the same time",
        )
        self.assertIn("also declared as dataset paths", error)

    def test_a_shipped_file_the_catalog_does_not_name_is_refused(self) -> None:
        """Every file a worker receives is named, whatever its bytes look like.

        The sweep this replaces classified a file first and asked for a
        declaration only for the ones it judged to be dataset rows. Each
        dressing below walked a labelled row stream past that judgement: a blank
        line, a leading comment, a byte-order mark, rows written as JSON arrays,
        and one line too long for the reader to hold. Nothing here reads the
        bytes, so there is nothing to dress.
        """

        root = self.create_scenario("undeclared-files", 121)
        rows = [
            json.dumps({"input": f"example-{index}", "output": "A"})
            for index in range(3)
        ]
        body = ("\n".join(rows) + "\n").encode("utf-8")
        arrays = "".join(
            json.dumps(list(json.loads(row).items())) + "\n" for row in rows
        ).encode("utf-8")
        oversized = (
            b'{"pad": "' + b"x" * (2 * scenario.MAX_DATASET_ROW_BYTES) + b'"}\n' + body
        )
        variants: tuple[tuple[str, str, bytes], ...] = (
            ("a verbatim copy", "project/copy.jsonl", body),
            (
                "a blank line inside",
                "project/spaced.jsonl",
                ("\n".join(rows[:1] + [""] + rows[1:]) + "\n").encode("utf-8"),
            ),
            ("a trailing blank line", "project/trailing.jsonl", body + b"\n"),
            ("a leading blank line", "project/leading.jsonl", b"\n" + body),
            ("a foreign suffix", "project/renamed.txt", body),
            ("a byte-order mark", "project/marked.jsonl", b"\xef\xbb\xbf" + body),
            ("a leading comment", "project/commented.jsonl", b"# scratch\n" + body),
            ("rows written as JSON arrays", "project/arrays.jsonl", arrays),
            ("one line too long to read", "project/oversized.jsonl", oversized),
            ("bytes that are not text", "project/payload.bin", b"\x00\xff" * 16),
            ("prose", "project/notes.md", b"# notes\n"),
        )
        for name, relative, content in variants:
            with self.subTest(dressing=name):
                shipped = root / Path(relative)
                shipped.write_bytes(content)
                self.commit_repository_paths(shipped, message=f"Ship {relative}")

                status, output, error = self.run_cli("check", "undeclared-files")

                self.assertNotEqual(0, status, output)
                self.assertEqual("", output)
                self.assertIn("ships files the catalog does not name", error)
                self.assertIn(relative, error)

                shipped.unlink()
                self.commit_repository_paths(root, message=f"Withdraw {relative}")

        status, output, error = self.run_cli("check", "undeclared-files")

        self.assertEqual(0, status, error)
        self.assertIn("OK: undeclared-files", output)

    def test_shipped_files_nested_below_the_project_directory_are_swept(self) -> None:
        """`prepare` copies the whole project tree, not only its top level."""

        root = self.create_scenario("nested-file", 134)
        nested = root / "project" / "extra" / "rows.jsonl"
        nested.parent.mkdir()
        nested.write_text(
            "".join(
                json.dumps({"input": f"example-{index}", "output": "A"}) + "\n"
                for index in range(2)
            ),
            encoding="utf-8",
        )
        self.commit_repository_paths(nested, message="Ship nested rows")

        status, output, error = self.run_cli("check", "nested-file")

        self.assertNotEqual(0, status, output)
        self.assertIn("ships files the catalog does not name", error)
        self.assertIn("project/extra/rows.jsonl", error)

    def test_untracked_scratch_files_are_not_refused(self) -> None:
        """`prepare` copies recorded Git blobs, so a worker never sees these."""

        root = self.create_scenario("scratch-file", 135)
        scratch = root / "project" / "scratch.jsonl"
        scratch.write_text(
            "".join(
                json.dumps({"input": f"example-{index}", "output": "A"}) + "\n"
                for index in range(2)
            ),
            encoding="utf-8",
        )

        status, output, error = self.run_cli("check", "scratch-file")

        self.assertEqual(0, status, error)
        self.assertIn("OK: scratch-file", output)

        self.commit_repository_paths(scratch, message="Track the scratch rows")

        status, output, error = self.run_cli("check", "scratch-file")

        self.assertNotEqual(
            0,
            status,
            "tracking the same bytes puts them in the worker's checkout, so the "
            "sweep that was right to ignore them must now refuse them",
        )
        self.assertIn("project/scratch.jsonl", error)

    def test_a_bank_inside_a_foreign_work_tree_keeps_its_sweeps(self) -> None:
        """Unpacking the bank inside someone else's repository must not
        silently disable the shipped-file sweeps.

        There `git ls-files` succeeds with no output; reading that as "nothing
        ships" would make every sweep vacuously green, so trackedness falls
        back to keeping every regular file instead.
        """

        root = self.create_scenario("foreign-tree", 136)
        planted = root / "project" / "rows.jsonl"
        planted.write_text(
            "".join(
                json.dumps({"input": f"example-{index}", "output": "SEV1"}) + "\n"
                for index in range(2)
            ),
            encoding="utf-8",
        )
        self.commit_repository_paths(planted, message="Ship undeclared rows")

        status, _, error = self.run_cli("check", "foreign-tree")
        self.assertNotEqual(0, status, "sanity: refused in its own repository")
        self.assertIn("ships files the catalog does not name", error)

        with tempfile.TemporaryDirectory() as outer_name:
            outer = Path(outer_name)
            subprocess.run(["git", "init", "-q", os.fspath(outer)], check=True)
            foreign_root = outer / "unpacked-bank"
            shutil.copytree(
                self.repository_root,
                foreign_root,
                ignore=shutil.ignore_patterns(".git"),
            )
            output = io.StringIO()
            foreign_error = io.StringIO()
            status = scenario.main(
                ["check", "foreign-tree"],
                scenarios_dir=foreign_root / "scenarios",
                repository_root=foreign_root,
                output=output,
                error=foreign_error,
            )

        self.assertNotEqual(0, status, output.getvalue())
        self.assertIn("ships files the catalog does not name", foreign_error.getvalue())

    def test_a_declared_record_may_not_be_a_labelled_row_stream(self) -> None:
        """Naming a dataset a record is not a way to ship it undeclared."""

        root = self.create_scenario("named-dataset", 175)
        records = root / "project" / "traigent-runs" / "events.jsonl"
        records.parent.mkdir()
        labelled = [
            {"input": f"example-{index}", "output": "SEV1" if index % 2 else "SEV2"}
            for index in range(8)
        ]
        manifest = valid_manifest("named-dataset", 175)
        catalog = manifest["catalog"]
        assert isinstance(catalog, dict)
        catalog["non_dataset_files"] = ["project/traigent-runs/events.jsonl"]
        self.write_manifest(root, manifest)

        for name, payload in (
            (
                "rows as objects",
                "".join(json.dumps(row) + "\n" for row in labelled),
            ),
            (
                "rows as arrays",
                "".join(
                    json.dumps([row["input"], row["output"]]) + "\n" for row in labelled
                ),
            ),
        ):
            with self.subTest(shape=name):
                records.write_text(payload, encoding="utf-8")
                self.commit_repository_paths(root, message=f"Ship {name}")

                status, output, error = self.run_cli("check", "named-dataset")

                self.assertNotEqual(0, status, output)
                self.assertIn("carry a closed label surface", error)

        records.write_text(
            "".join(
                json.dumps({"event": f"step-{index}", "sequence": index}) + "\n"
                for index in range(8)
            ),
            encoding="utf-8",
        )
        self.commit_repository_paths(root, message="Ship a real run record")

        status, output, error = self.run_cli("check", "named-dataset")

        self.assertEqual(
            0,
            status,
            "a record whose columns are identifiers and numbers is what a run "
            f"log looks like, and declaring it is honest: {error}",
        )
        self.assertIn("OK: named-dataset", output)

    # The scenarios whose published contract is identical to another's, recorded so
    # the set is a claim the suite checks rather than four identical table cells a
    # reader has to interpret. `docs/scenario-coverage.md` says why they coincide.
    SHARED_OPENING_CONTRACTS = (
        (
            "helpdesk-queue-router",
            "incident-severity-triage",
            "policy-handbook-rag",
            "warehouse-text-to-sql",
        ),
    )

    def test_the_recorded_invocation_agrees_with_the_manifest(self) -> None:
        """The two disagreeing is exactly how case 52 published a wrong number.

        `83d2d03` measured case 52 with `--evaluator-method exact`; a later
        review commit corrected the catalog's declared method and did not
        re-measure, so the manifest described one run and the contract recorded
        another. The argv comes from the run and the manifest from an editor,
        which is what makes this comparison worth making rather than a
        tautology.
        """

        checked = 0
        for manifest_path in sorted(
            (scenario.REPOSITORY_ROOT / "scenarios").glob("*/scenario.json")
        ):
            slug = manifest_path.parent.name
            invocation_path = (
                manifest_path.parent / "verifier" / "measurement" / "invocation.json"
            )
            self.assertTrue(invocation_path.is_file(), f"{slug} records no invocation")
            invocation = json.loads(invocation_path.read_text(encoding="utf-8"))
            readiness = invocation["steps"].get("readiness") or []
            catalog = json.loads(manifest_path.read_text(encoding="utf-8"))["catalog"]
            evaluator = catalog["components"].get("evaluator") or {}
            profile = (catalog.get("datasets") or [{}])[0]
            for flag, declared in (
                ("--evaluator-method", evaluator.get("guide_evaluator_method")),
                ("--task-kind", profile.get("guide_task_kind")),
            ):
                passed = (
                    readiness[readiness.index(flag) + 1] if flag in readiness else None
                )
                with self.subTest(scenario=slug, flag=flag):
                    self.assertEqual(
                        declared,
                        passed,
                        f"{slug}: the manifest says {declared!r} and the recorded "
                        f"invocation passed {passed!r}",
                    )
                    checked += 1
        self.assertGreaterEqual(checked, 24, "no invocation was compared")

    def test_a_committed_row_review_names_rows_that_exist(self) -> None:
        """A review of rows that are not there is the defect guide #391 filed.

        `preflight.py` added row-id digests because a review "could name forty-
        eight rows that do not exist and be counted as a read of forty-eight
        rows that do". The ids here are positional, so they are checkable
        against the dataset's own line count, and the draw is recorded so a
        redraw after an inconvenient verdict is not invisible.
        """

        reviewed = 0
        for review_path in sorted(
            (scenario.REPOSITORY_ROOT / "scenarios").glob(
                "*/verifier/measurement/row-review.json"
            )
        ):
            slug = review_path.parents[2].name
            review = json.loads(review_path.read_text(encoding="utf-8"))
            lines = [
                line
                for line in (review_path.parents[2] / "project" / "dataset.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
                if line.strip()
            ]
            with self.subTest(scenario=slug):
                self.assertEqual("assistant", review["reviewer"])
                draw = review["draw"]
                self.assertEqual(len(review["rows"]), draw["reviewed"])
                self.assertEqual(len(lines), draw["provided"])
                self.assertIn("method", draw)
                # The seed is checked by REPRODUCING the draw, not by being
                # present. A recorded seed that does not yield the recorded rows
                # means they were chosen some other way, which is the thing the
                # record exists to rule out.
                generator = random.Random(draw["seed"])
                self.assertEqual(
                    sorted(
                        generator.sample(range(1, len(lines) + 1), draw["reviewed"])
                    ),
                    sorted(
                        int(str(row["id"]).removeprefix("line-"))
                        for row in review["rows"]
                    ),
                    f"{slug}: the recorded seed does not yield the recorded rows",
                )
                for row in review["rows"]:
                    number = int(str(row["id"]).removeprefix("line-"))
                    self.assertTrue(
                        1 <= number <= len(lines),
                        f"{slug}: {row['id']} is not a line of the dataset",
                    )
                    self.assertGreater(
                        len(row["note"]), 40, f"{slug}: {row['id']} has no real note"
                    )
                notes = {row["note"] for row in review["rows"]}
                self.assertEqual(
                    len(notes),
                    len(review["rows"]),
                    f"{slug}: repeated notes are a tally, not a read",
                )
                reviewed += 1
        # Not "at least one". The rule is that a scenario commits a review
        # exactly when its published opening cannot be reproduced without one,
        # and a floor of one cannot see four of them go missing -- deleting a
        # load-bearing review was green in every gate this repository runs.
        # Derived from the contracts rather than written down, so it follows the
        # bank.
        #
        # Two ways an opening depends on a review, and both are compared fields:
        #
        # - the band sits above the guide's answer-key hold, which withholds
        #   STRONG and EXCELLENT until a read of the answers enters;
        # - the caps carry the one condition only a reader can produce.
        #   `readiness.py` builds `dataset-unsound-expected-outputs` from the
        #   review's own verdicts and from nothing else, so a scenario that
        #   publishes it and ships no review publishes a cap it cannot re-derive.
        #   Measured on regex-rule-authoring rather than assumed: the same
        #   inputs without `--row-review` return the same band, status and
        #   action, and drop that cap.
        needs_review = sorted(
            manifest_path.parent.name
            for manifest_path in (scenario.REPOSITORY_ROOT / "scenarios").glob(
                "*/scenario.json"
            )
            if _opening_needs_a_row_review(
                json.loads(
                    (
                        manifest_path.parent / "verifier" / "expected-opening.json"
                    ).read_text(encoding="utf-8")
                )
            )
        )
        shipping = sorted(
            review_path.parents[2].name
            for review_path in (scenario.REPOSITORY_ROOT / "scenarios").glob(
                "*/verifier/measurement/row-review.json"
            )
        )
        self.assertEqual(
            needs_review,
            shipping,
            "the scenarios shipping a row review are not the ones whose opening "
            "needs one",
        )
        self.assertGreater(reviewed, 0, "no committed row review was read")

    def test_the_scenarios_sharing_a_contract_are_the_ones_written_down(self) -> None:
        """A new scenario landing on an existing contract is a decision.

        The contract is four fields, each cap with its ceiling and routing, so
        two scenarios that differ in agent type,
        dataset and evaluator can still read the same. Four of the thirteen do,
        on purpose -- "nothing is wrong with this project" is one reading and
        there is only one of it. An accidental fifth should not look the same as
        those four.
        """

        by_contract: dict[tuple[object, ...], list[str]] = {}
        for manifest_path in sorted(
            (scenario.REPOSITORY_ROOT / "scenarios").glob("*/scenario.json")
        ):
            slug = manifest_path.parent.name
            contract = json.loads(
                (manifest_path.parent / "verifier" / "expected-opening.json").read_text(
                    encoding="utf-8"
                )
            )
            key = (
                contract["band"],
                contract["status"],
                contract["recommended_action"],
                tuple(
                    sorted(
                        (cap["condition"], cap["ceiling"], cap["blocks"], cap["asks"])
                        for cap in contract["caps"]
                    )
                ),
            )
            by_contract.setdefault(key, []).append(slug)
        self.assertGreaterEqual(len(by_contract), 1, "no contract was read")
        found = sorted(
            tuple(sorted(slugs)) for slugs in by_contract.values() if len(slugs) > 1
        )
        self.assertEqual(
            sorted(tuple(sorted(g)) for g in self.SHARED_OPENING_CONTRACTS),
            found,
            "the scenarios sharing a published contract are not the recorded ones",
        )

    def test_a_readme_rubric_illustrates_a_stratum_with_a_row_from_it(self) -> None:
        """A worked example in prose is a claim about the data beside it.

        `scenario.py check` pins every COUNT a README states and pins no
        example, so a rubric could define `easy` and illustrate it with a rule
        the same rubric calls `hard`, four lines apart, with every gate green.
        That shipped once in case 58. Every rubric in the bank is read - a
        rubric the parser cannot place is a finding, not a skip - and each must
        define exactly its manifest's strata.
        """

        problems, read, compared = _rubric_findings(scenario.REPOSITORY_ROOT)
        self.assertEqual([], problems)
        headed = sum(
            1
            for readme in (scenario.REPOSITORY_ROOT / "scenarios").glob("*/README.md")
            if any(
                line.startswith("#") and "difficulty rubric" in line.lower()
                for line in readme.read_text(encoding="utf-8").splitlines()
            )
        )
        self.assertGreater(headed, 0, "no scenario README carries a rubric")
        self.assertEqual(headed, read, "a rubric the check did not read")
        self.assertGreater(compared, 0, "no worked example was compared")

    def test_every_scenario_table_lists_the_bank_as_published(self) -> None:
        """A table of scenarios is a claim about the bank; it is derived here.

        The README's scenario table once listed twelve rows under a sentence
        announcing thirteen, and nothing compared the two. Each table is now
        read against the bank: every scenario exactly once, under the family
        the deck's `SCENARIO_BANK` gives it, and - in the README - with the
        band, status, action and caps its published contract carries.
        """

        root = scenario.REPOSITORY_ROOT
        bank_source = (root / "presentation" / "src" / "content.ts").read_text(
            encoding="utf-8"
        )
        family_of = {
            f"{slug} ({legacy_id})": family
            for slug, legacy_id, family in re.findall(
                r'slug: "([\w-]+)",\s*legacyId: (\d+),\s*family: "([^"]+)"',
                bank_source,
            )
        }
        manifests = sorted((root / "scenarios").glob("*/scenario.json"))
        self.assertEqual(
            {
                f"{path.parent.name} ({json.loads(path.read_text())['legacy_id']})"
                for path in manifests
            },
            set(family_of),
            "the deck's SCENARIO_BANK and the scenarios directory disagree",
        )

        def rows(document: str) -> dict[str, list[list[str]]]:
            found: dict[str, list[list[str]]] = {}
            for line in (root / document).read_text(encoding="utf-8").splitlines():
                cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
                named = re.fullmatch(r"`([\w-]+)` \((\d+)\)", cells[0])
                if line.startswith("|") and named:
                    found.setdefault(f"{named[1]} ({named[2]})", []).append(cells)
            return found

        for document in ("README.md", "docs/scenario-coverage.md"):
            with self.subTest(document=document):
                table = rows(document)
                self.assertEqual(set(family_of), set(table), "rows are not the bank")
                for case, found in table.items():
                    self.assertEqual(1, len(found), f"{case} is listed twice")
                    self.assertEqual(family_of[case], found[0][1], case)
                family_rows = {
                    family: set(re.findall(r"`([\w-]+)` \((\d+)\)", cells[-1]))
                    for line in (root / document)
                    .read_text(encoding="utf-8")
                    .splitlines()
                    if line.startswith("|")
                    for cells in [
                        [c.strip() for c in line.strip().strip("|").split("|")]
                    ]
                    for family in [cells[0]]
                    if family in set(family_of.values())
                }
                self.assertEqual(set(family_of.values()), set(family_rows))
                for family, listed in family_rows.items():
                    self.assertEqual(
                        {case for case, owner in family_of.items() if owner == family},
                        {f"{slug} ({legacy_id})" for slug, legacy_id in listed},
                        f"the {family} row of the family table",
                    )

        # How each document spells a contract, and the phrase that introduces
        # a read-dependent scenario's second one.
        spellings = {
            "README.md": (
                3,
                "{band} · {status} · `{action}` · ",
                "none",
                "a read that finds every answer sound opens ",
            ),
            "docs/scenario-coverage.md": (
                -1,
                "`{band}` / `{status}` / `{action}` / ",
                "no caps",
                "for a read that finds every answer sound, ",
            ),
        }

        def assert_renders(text: str, contract: dict, empty: str) -> None:
            prefix = spelling.format(
                band=contract["band"],
                status=contract["status"],
                action=contract["recommended_action"],
            )
            self.assertTrue(text.startswith(prefix), f"{text!r} vs {prefix!r}")
            caps = re.split(r"[;(]", text[len(prefix) :], maxsplit=1)[0]
            if contract["caps"]:
                self.assertEqual(
                    {cap["condition"] for cap in contract["caps"]},
                    set(re.findall(r"`([^`]+)`", caps)),
                )
            else:
                self.assertEqual(empty, caps.strip())

        rendered = 0
        for document, (column, spelling, empty, second) in spellings.items():
            for case, found in rows(document).items():
                verifier = root / "scenarios" / case.split(" ")[0] / "verifier"
                manifest = json.loads((verifier.parent / "scenario.json").read_text())
                dependent = manifest["catalog"]["expected_route"].get("read_dependent")
                cell = found[0][column]
                with self.subTest(document=document, case=case):
                    assert_renders(
                        cell,
                        json.loads((verifier / "expected-opening.json").read_text()),
                        empty,
                    )
                    rendered += 1
                    self.assertEqual(dependent is not None, second in cell)
                    if dependent is not None:
                        assert_renders(
                            cell.split(second, 1)[1],
                            json.loads(
                                (
                                    verifier.parent / dependent["sound_read_contract"]
                                ).read_text()
                            ),
                            empty,
                        )
                        rendered += 1
        dependent_count = sum(
            "read_dependent"
            in json.loads(path.read_text())["catalog"]["expected_route"]
            for path in manifests
        )
        self.assertEqual(len(spellings) * (len(family_of) + dependent_count), rendered)

    def test_case_58_scorer_drops_only_an_outer_group_that_changes_nothing(
        self,
    ) -> None:
        """The redundant-group rule is the one place the scorer reads structure.

        It must see escapes and character classes, drop `(?:...)` groups and
        plain groups with no capture inside until none is left, keep any group
        whose removal would change what the rule captures or asserts, and keep
        whitespace inside a group, which the pattern matches literally.
        """

        path = (
            scenario.REPOSITORY_ROOT
            / "scenarios/regex-rule-authoring/project/evaluator.py"
        )
        specification = importlib.util.spec_from_file_location("case_58_scorer", path)
        assert specification is not None and specification.loader is not None
        scorer = importlib.util.module_from_spec(specification)
        # Loading it must not leave bytecode inside a published scenario.
        with mock.patch.object(sys, "dont_write_bytecode", True):
            specification.loader.exec_module(scorer)
        for written, recorded, score in (
            ("(?:\\d+)", "\\d+", 1.0),
            ("(\\d+)", "\\d+", 1.0),
            ("(\\d+\\))", "\\d+\\)", 1.0),
            ("([)])", "[)]", 1.0),
            ("  [0-9]{4}  ", "\\d{4}", 1.0),
            ('("token"\\s*:\\s*"([^"]*)")', '"token"\\s*:\\s*"([^"]*)"', 0.0),
            ("(?P<year>\\d{4})", "\\d{4}", 0.0),
            ("(?=a)", "a", 0.0),
            ("(a)|(b)", "a)|(b", 0.0),
            ("a|b", "[ab]", 0.0),
            ("( \\d{4} )", "\\d{4}", 0.0),
            ("(?:(a))", "a", 1.0),
            ("((a))", "a", 0.0),
        ):
            with self.subTest(written=written):
                self.assertEqual(score, scorer.score(written, recorded))

    def test_case_58_calls_no_answer_sound_that_its_own_note_contradicts(
        self,
    ) -> None:
        """A row whose recorded rule fails its own examples cannot be `sound`.

        Each row carries the strings its rule is claimed to find and to leave
        alone. The rules are searched over those strings here - they are this
        repository's own inputs, so compiling them is safe - and any row the
        rule contradicts must be classed unsound or contestable.
        """

        root = scenario.REPOSITORY_ROOT / "scenarios/regex-rule-authoring"
        classes = {
            row_id: entry["class"]
            for row_id, entry in json.loads(
                (root / "verifier/row-verdicts.json").read_text(encoding="utf-8")
            )["rows"].items()
        }
        contradicted = []
        for number, line in enumerate(
            (root / "project/dataset.jsonl").read_text(encoding="utf-8").splitlines(),
            start=1,
        ):
            row = json.loads(line)
            rule = re.compile(row["output"])
            if any(
                not rule.search(text) for text in row["metadata"]["must_match"]
            ) or any(rule.search(text) for text in row["metadata"]["must_reject"]):
                contradicted.append(f"line-{number}")
        self.assertEqual(["line-16", "line-21"], contradicted)
        for row_id in contradicted:
            self.assertNotEqual("sound", classes[row_id], row_id)

    def test_a_readme_sample_row_is_a_row_of_its_dataset(self) -> None:
        """The README's "equivalent object" is a claim about one line of data.

        Case 58's sample once carried example strings no row has. A sample is
        read as a row with each `...` standing for omitted text, and must match
        a row of the scenario's dataset in every key and every other character.
        """

        def matches(sample: object, row: object) -> bool:
            if isinstance(sample, str) and isinstance(row, str) and "..." in sample:
                pattern = ".*?".join(re.escape(part) for part in sample.split("..."))
                return re.fullmatch(pattern, row, re.DOTALL) is not None
            if isinstance(sample, dict) and isinstance(row, dict):
                return sample.keys() == row.keys() and all(
                    matches(sample[key], row[key]) for key in sample
                )
            if isinstance(sample, list) and isinstance(row, list):
                return len(sample) == len(row) and all(map(matches, sample, row))
            return sample == row

        samples = 0
        for manifest_path in sorted(
            (scenario.REPOSITORY_ROOT / "scenarios").glob("*/scenario.json")
        ):
            root = manifest_path.parent
            dataset = (
                root
                / json.loads(manifest_path.read_text(encoding="utf-8"))["catalog"][
                    "datasets"
                ][0]["path"]
            )
            if dataset.suffix != ".jsonl":
                continue
            rows = [
                json.loads(line)
                for line in dataset.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            readme = (root / "README.md").read_text(encoding="utf-8")
            for block in re.findall(r"```json\n(.*?)\n```", readme, re.DOTALL):
                sample = json.loads(block)
                if isinstance(sample, dict) and "input" in sample:
                    samples += 1
                    with self.subTest(scenario=root.name):
                        self.assertTrue(
                            any(matches(sample, row) for row in rows),
                            f"{root.name}: the README's sample is no row of {dataset.name}",
                        )
        self.assertGreater(samples, 0, "no README sample row was read")

    def test_the_rubric_check_reports_each_way_a_rubric_drifts(self) -> None:
        """The check has to fail, and for the reason under test.

        Each probe makes one edit to a copy of case 58 and asserts the edit
        applied, so a probe that silently changed nothing cannot pass. The
        first restores the defect that shipped.
        """

        source = scenario.REPOSITORY_ROOT / "scenarios" / "regex-rule-authoring"
        probes = (
            (
                "`\\d{4}`, `SID\\d{8}`.",
                "`\\d{4}`, `#(?:[0-9a-f]{3}|[0-9a-f]{6})`.",
                "which the dataset labels 'hard'",
            ),
            (
                "### Difficulty rubric",
                "### Difficulty Rubric",
                "is not in a recognised form",
            ),
            ("`SID\\d{8}`.", "`SID\\d{9}`.", "no single row of the dataset"),
            ("- **very-hard** -", "- **expert** -", "the manifest declares"),
        )
        for old, new, reason in probes:
            with self.subTest(edit=new), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                copy = root / "scenarios" / source.name
                shutil.copytree(source, copy)
                readme = copy / "README.md"
                text = readme.read_text(encoding="utf-8")
                self.assertEqual(1, text.count(old), "the probe edit did not apply")
                readme.write_text(text.replace(old, new), encoding="utf-8")
                problems, _, _ = _rubric_findings(root)
                self.assertTrue(
                    any(reason in problem for problem in problems),
                    f"expected a finding containing {reason!r}, got {problems}",
                )

    def test_every_shipped_scenario_names_the_guide_task_kind_it_was_measured_with(
        self,
    ) -> None:
        """The declared task kind changes what the readiness read reports.

        A contract that does not record it cannot be re-derived: the value
        lived only in the notes of the captain who measured it, while the
        catalog carried its own word for the same thing -- `tool-call-selection`
        where the guide was actually told `structured`. The key is optional in
        the schema because the first scenario's pinned manifest predates it;
        every scenario in the tree carries it, and that is this test's job.
        """

        root = scenario.REPOSITORY_ROOT / "scenarios"
        checked = 0
        missing = []
        for manifest_path in sorted(root.glob("*/scenario.json")):
            catalog = json.loads(manifest_path.read_text(encoding="utf-8"))["catalog"]
            for profile in catalog.get("datasets") or []:
                checked += 1
                kind = profile.get("guide_task_kind")
                if kind is None:
                    missing.append(manifest_path.parent.name)
                    continue
                self.assertIn(
                    kind,
                    scenario.GUIDE_TASK_KINDS,
                    f"{manifest_path.parent.name} names a kind the guide does not take",
                )
        self.assertEqual([], missing, "scenarios shipping no guide task kind")
        # Without this the whole test passes on an empty glob: no profile read,
        # no name missing, green.
        self.assertGreaterEqual(checked, 12, "no dataset profile was read")

    def test_a_declared_binary_record_is_read_as_no_label_surface(self) -> None:
        """A database file is a record this check cannot read as rows.

        The delimited-table reading takes the first decodable run of bytes
        holding a separator for a header. A SQLite page can decode, hold a tab,
        and carry a bare carriage return a few bytes later, which the CSV reader
        refuses with an exception rather than a verdict -- so `check` crashed on
        a scenario that shipped its database. The bytes below are that shape,
        reduced to the three properties that produced it.
        """

        root = self.create_scenario("database-record", 177)
        database = root / "project" / "stock.db"
        database.write_bytes(
            b"SQLite format 3\x00"
            + b"\x00" * 40
            + b"id\tname\tqty\n"
            + b"1\tbolt\r4\n"
            + b"\x00\xff\xfe" * 20
            + b"\n"
        )
        manifest = valid_manifest("database-record", 177)
        catalog = manifest["catalog"]
        assert isinstance(catalog, dict)
        catalog["non_dataset_files"] = ["project/stock.db"]
        self.write_manifest(root, manifest)
        self.commit_repository_paths(root, message="Ship a database")

        status, output, error = self.run_cli("check", "database-record")

        self.assertEqual(0, status, error)
        self.assertIn("OK: database-record", output)

    def test_a_stray_control_byte_does_not_hide_a_table_s_label_column(self) -> None:
        """One control character in a row is not a reason to drop the row.

        The database above is read as no label surface because the file is
        bytes. An earlier answer to it dropped any decoded line carrying a C0
        control byte, which is the same question asked one level too low: a
        text table with one vertical tab per line lost every data line and so
        reported no label column at all. A record could then ship its answer
        key past this check by carrying one stray byte per row.
        """

        root = self.create_scenario("noisy-table", 178)
        records = root / "project" / "traigent-runs" / "events.csv"
        records.parent.mkdir()
        rows = "".join(
            f"{index},note\x0b{index},{'SEV1' if index % 2 else 'SEV2'}\n"
            for index in range(20)
        )
        records.write_text("id,note,severity\n" + rows, encoding="utf-8")
        manifest = valid_manifest("noisy-table", 178)
        catalog = manifest["catalog"]
        assert isinstance(catalog, dict)
        catalog["non_dataset_files"] = ["project/traigent-runs/events.csv"]
        self.write_manifest(root, manifest)
        self.commit_repository_paths(root, message="Ship a noisy table")

        status, output, error = self.run_cli("check", "noisy-table")

        self.assertNotEqual(0, status, output)
        self.assertIn("carry a closed label surface", error)
        self.assertIn("severity", error)

    def test_a_quoted_field_spanning_lines_does_not_hide_the_column_after_it(
        self,
    ) -> None:
        """A table is parsed as a stream, because RFC4180 rows span lines.

        Parsing each physical line on its own survives a line the reader
        chokes on, and splits every quoted field that carries a newline. The
        column after such a field then lands in a record of the wrong width
        and is dropped -- so a labelled table whose note field wraps reported
        no label surface, and the record shipped its answer key.
        """

        root = self.create_scenario("wrapped-table", 179)
        records = root / "project" / "traigent-runs" / "events.csv"
        records.parent.mkdir()
        rows = "".join(
            f'{index},"line one of {index}\nline two of {index}",'
            f"{'SEV1' if index % 2 else 'SEV2'}\n"
            for index in range(20)
        )
        records.write_text("id,note,severity\n" + rows, encoding="utf-8")
        manifest = valid_manifest("wrapped-table", 179)
        catalog = manifest["catalog"]
        assert isinstance(catalog, dict)
        catalog["non_dataset_files"] = ["project/traigent-runs/events.csv"]
        self.write_manifest(root, manifest)
        self.commit_repository_paths(root, message="Ship a wrapped table")

        status, output, error = self.run_cli("check", "wrapped-table")

        self.assertNotEqual(0, status, output)
        self.assertIn("carry a closed label surface", error)
        self.assertIn("severity", error)

    def test_a_table_this_check_cannot_decode_is_refused_not_vouched_for(
        self,
    ) -> None:
        """ "I could not read this" may not be spelled "there is nothing here".

        The scan drops a line it cannot use in three places, and for a while
        nothing counted the drops, so a file whose every data line was dropped
        produced the empty list -- the same answer as a file with no labels.
        A latin-1 CSV, which is what every European spreadsheet exports by
        default, walked its answer key past the check that way: the ASCII
        header was read, all twenty data lines failed to decode, and the
        record was declared clean.
        """

        root = self.create_scenario("latin-one-table", 180)
        records = root / "project" / "traigent-runs" / "events.csv"
        records.parent.mkdir()
        rows = b"".join(
            b"%d,note\xe9%d,%s\n" % (index, index, b"SEV1" if index % 2 else b"SEV2")
            for index in range(20)
        )
        records.write_bytes(b"id,note,severity\n" + rows)
        manifest = valid_manifest("latin-one-table", 180)
        catalog = manifest["catalog"]
        assert isinstance(catalog, dict)
        catalog["non_dataset_files"] = ["project/traigent-runs/events.csv"]
        self.write_manifest(root, manifest)
        self.commit_repository_paths(root, message="Ship a latin-1 table")

        status, output, error = self.run_cli("check", "latin-one-table")

        self.assertNotEqual(0, status, output)
        self.assertIn("are not UTF-8", error)
        self.assertIn("cannot be ruled out", error)

    def test_a_quote_that_is_never_closed_is_refused(self) -> None:
        """The CSV reader raises nothing for this; it swallows the file.

        A quote opening a field and never closed makes every later line part
        of that one field. The reader reports no error, the single record it
        finally returns is the wrong width, and the table is silently empty.
        """

        root = self.create_scenario("swallowed-table", 181)
        records = root / "project" / "traigent-runs" / "events.csv"
        records.parent.mkdir()
        rows = "".join(
            f"{index},note{index},{'SEV1' if index % 2 else 'SEV2'}\n"
            for index in range(1, 21)
        )
        records.write_text('id,note,severity\n0,"open,SEV2\n' + rows, encoding="utf-8")
        manifest = valid_manifest("swallowed-table", 181)
        catalog = manifest["catalog"]
        assert isinstance(catalog, dict)
        catalog["non_dataset_files"] = ["project/traigent-runs/events.csv"]
        self.write_manifest(root, manifest)
        self.commit_repository_paths(root, message="Ship a swallowed table")

        status, output, error = self.run_cli("check", "swallowed-table")

        self.assertNotEqual(0, status, output)
        self.assertIn("never closed", error)

    def test_a_header_repeating_a_column_name_is_refused(self) -> None:
        """Stepping over it took a DATA line as the header instead.

        A table keyed by column name cannot be read when two columns share
        one. The search used to carry on to the next line that qualified --
        which was row one -- and then reported columns named after that row's
        values, so the answer was wrong rather than merely incomplete.
        """

        root = self.create_scenario("repeated-column", 182)
        records = root / "project" / "traigent-runs" / "events.csv"
        records.parent.mkdir()
        rows = "".join(
            f"{index},{'SEV1' if index % 2 else 'SEV2'},SEV1\n" for index in range(20)
        )
        records.write_text("id,severity,severity\n" + rows, encoding="utf-8")
        manifest = valid_manifest("repeated-column", 182)
        catalog = manifest["catalog"]
        assert isinstance(catalog, dict)
        catalog["non_dataset_files"] = ["project/traigent-runs/events.csv"]
        self.write_manifest(root, manifest)
        self.commit_repository_paths(root, message="Ship a repeated column name")

        status, output, error = self.run_cli("check", "repeated-column")

        self.assertNotEqual(0, status, output)
        self.assertIn("repeats a column name", error)

    def test_prose_that_reads_as_a_header_is_not_a_table_that_failed(self) -> None:
        """The refusal must not fire on a document that is simply not a table.

        One sentence carrying two commas reads as a three-column header, and
        the lines after it are prose of every other width. That is honestly
        "this file is not a table", not "this table could not be read" -- and
        the first draft of the refusal got it wrong, turning a shipped
        handbook page into a failed check.
        """

        root = self.create_scenario("handbook-page", 183)
        page = root / "project" / "handbook.md"
        page.write_text(
            "# Remote and hybrid working\n\n"
            "Office-based roles are hybrid: you must work at least 3 days per\n"
            "week from your contracted site. Operational roles, meaning\n"
            "drivers, warehouse operatives and yard staff, are not eligible\n"
            "for remote working because the work cannot be done away from the\n"
            "site.\n",
            encoding="utf-8",
        )
        manifest = valid_manifest("handbook-page", 183)
        catalog = manifest["catalog"]
        assert isinstance(catalog, dict)
        catalog["non_dataset_files"] = ["project/handbook.md"]
        self.write_manifest(root, manifest)
        self.commit_repository_paths(root, message="Ship a handbook page")

        status, output, error = self.run_cli("check", "handbook-page")

        self.assertEqual(0, status, error)
        self.assertIn("OK: handbook-page", output)

    def test_a_declared_record_with_a_line_too_long_to_read_is_refused(self) -> None:
        """A line this check cannot read is not a line it may vouch for."""

        root = self.create_scenario("unreadable-record", 176)
        records = root / "project" / "traigent-runs" / "events.jsonl"
        records.parent.mkdir()
        records.write_bytes(
            b'{"pad": "' + b"x" * (2 * scenario.MAX_DATASET_ROW_BYTES) + b'"}\n'
        )
        manifest = valid_manifest("unreadable-record", 176)
        catalog = manifest["catalog"]
        assert isinstance(catalog, dict)
        catalog["non_dataset_files"] = ["project/traigent-runs/events.jsonl"]
        self.write_manifest(root, manifest)
        self.commit_repository_paths(root, message="Ship an unreadable record")

        status, output, error = self.run_cli("check", "unreadable-record")

        self.assertNotEqual(0, status, output)
        self.assertEqual("", output)
        self.assertIn("carries a line longer than", error)

    def test_reading_a_declared_record_does_not_read_it_whole(self) -> None:
        """The scan costs the columns of one row, not the length of the file."""

        root = self.create_scenario("large-record", 136)
        records = root / "project" / "traigent-runs" / "events.jsonl"
        records.parent.mkdir()
        size = 16 * scenario.MAX_DATASET_ROW_BYTES
        line = json.dumps({"event": "step", "note": "x" * 200}) + "\n"
        records.write_text(line * (size // len(line)), encoding="utf-8")
        manifest = valid_manifest("large-record", 136)
        catalog = manifest["catalog"]
        assert isinstance(catalog, dict)
        catalog["non_dataset_files"] = ["project/traigent-runs/events.jsonl"]
        self.write_manifest(root, manifest)
        self.commit_repository_paths(root, message="Ship a large run record")

        tracemalloc.start()
        try:
            status, output, error = self.run_cli("check", "large-record")
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()

        self.assertEqual(0, status, error)
        self.assertIn("OK: large-record", output)
        self.assertLess(
            peak,
            4 * scenario.MAX_DATASET_ROW_BYTES,
            "scanning a declared record must cost the longest line the bank can "
            f"accept, not the size of the file; this one is {size} bytes",
        )

    def labelled_rows(self, count: int) -> list[dict[str, object]]:
        return [
            {
                "input": f"example-{index}",
                "output": "SEV1" if index % 2 else "SEV2",
                "metadata": {"split": "tuning", "difficulty": "easy"},
            }
            for index in range(count)
        ]

    def test_a_component_slot_may_not_name_a_file_that_is_not_source(self) -> None:
        """A slot has to describe what it names, and only the bytes settle that.

        ``agent.path`` and ``evaluator.path`` were checked for existing, for
        being a regular file, and for sitting under ``project/``. Nothing read
        what was in them, so a byte-identical copy of the labelled dataset
        under the name ``agent.py`` satisfied the slot and ``prepare`` shipped
        the answer key to a blinded worker as the agent.
        """

        for index, component in enumerate(("agent", "evaluator")):
            with self.subTest(component=component):
                slug = f"slot-{component}"
                root = self.create_scenario(slug, 300 + index)
                self.write_rows(root, self.labelled_rows(8))
                planted = root / "project" / f"{component}_impl.py"
                planted.write_bytes((root / "project" / "input.txt").read_bytes())
                manifest = self.labelled_manifest(
                    slug, 300 + index, rows=8, label_counts={"SEV1": 4, "SEV2": 4}
                )
                catalog = manifest["catalog"]
                assert isinstance(catalog, dict)
                catalog["components"][component][
                    "path"
                ] = f"project/{component}_impl.py"
                catalog["non_dataset_files"] = [f"project/{component}.py"]
                self.write_manifest(root, manifest)
                self.commit_repository_paths(root, message=f"Plant a {component}")

                status, output, error = self.run_cli("check", slug)

                self.assertNotEqual(
                    0,
                    status,
                    "the labelled dataset reaches the worker as the "
                    f"{component}, which the slot said would hold source",
                )
                self.assertEqual("", output)
                self.assertIn("do not read as Python source", error)
                self.assertIn(f"project/{component}_impl.py", error)

                self.assertEqual(
                    hashlib.sha256(planted.read_bytes()).hexdigest(),
                    hashlib.sha256(
                        (root / "project" / "input.txt").read_bytes()
                    ).hexdigest(),
                    "the planted slot file is the dataset byte for byte",
                )

                planted.write_text(AGENT_SOURCE, encoding="utf-8")
                self.commit_repository_paths(root, message="Ship real source")

                status, output, error = self.run_cli("check", slug)

                self.assertEqual(
                    0,
                    status,
                    f"a slot naming Python that does something is honest: {error}",
                )
                self.assertIn(f"OK: {slug}", output)

    def test_a_denied_component_may_not_ship_its_source_under_another_name(
        self,
    ) -> None:
        """The suffix is not what decides whether shipped bytes are a component.

        The gate asked ``path.suffix == ".py"``, so ``git mv evaluator.py
        evaluator.txt`` plus one ``non_dataset_files`` entry passed a catalog
        that declared the evaluator missing while ``prepare`` handed the
        blinded worker the byte-identical evaluator.
        """

        root = self.create_scenario("renamed-evaluator", 302)
        source = root / "project" / "evaluator.py"
        renamed = root / "project" / "evaluator.txt"
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        renamed.write_bytes(source.read_bytes())
        source.unlink()
        manifest = valid_manifest("renamed-evaluator", 302)
        catalog = manifest["catalog"]
        assert isinstance(catalog, dict)
        catalog["starting_condition"] = "gaps-present"
        catalog["components"]["evaluator"].update(
            {"state": "missing", "path": None, "method": None}
        )
        catalog["non_dataset_files"] = ["project/evaluator.txt"]
        self.write_manifest(root, manifest)
        self.remove_repository_paths(source, message="Rename the evaluator away")
        self.commit_repository_paths(root, message="Ship it under a data name")

        status, output, error = self.run_cli("check", "renamed-evaluator")

        self.assertNotEqual(0, status, output)
        self.assertEqual("", output)
        self.assertIn("declares this component missing", error)
        self.assertIn("project/evaluator.txt", error)
        self.assertEqual(
            digest,
            hashlib.sha256(renamed.read_bytes()).hexdigest(),
            "the renamed file is the evaluator byte for byte",
        )

        renamed.write_text("severity,count\nSEV1,3\nSEV2,4\n", encoding="utf-8")
        self.commit_repository_paths(root, message="Ship a real record instead")

        status, output, error = self.run_cli("check", "renamed-evaluator")

        self.assertEqual(
            0,
            status,
            f"a data file under a data name is what it says it is: {error}",
        )
        self.assertIn("OK: renamed-evaluator", output)

    def test_a_calibration_record_may_not_be_a_labelled_dataset(self) -> None:
        """A case that probes nothing said nothing, and was skipped rather than refused.

        Skipping it made the slot accept any array of objects, so the labelled
        rows shipped under the calibration name with a matching ``case_count``.
        """

        root = self.create_scenario("calibration-dataset", 303)
        record = root / "project" / "calibration.json"
        manifest = valid_manifest("calibration-dataset", 303)
        catalog = manifest["catalog"]
        assert isinstance(catalog, dict)
        catalog["components"]["evaluator"]["calibration"] = {
            "path": "project/calibration.json",
            "case_count": 8,
        }
        self.write_manifest(root, manifest)

        for name, cases, expected_error in (
            (
                "labelled dataset rows",
                self.labelled_rows(8),
                "needs a 'probes' object",
            ),
            (
                "cases whose probes are empty",
                [{"expected": "SEV1", "probes": {}} for _ in range(8)],
                "'probes' is empty",
            ),
        ):
            with self.subTest(shape=name):
                record.write_text(json.dumps(cases), encoding="utf-8")
                self.commit_repository_paths(root, message=f"Ship {name}")

                status, output, error = self.run_cli("check", "calibration-dataset")

                self.assertNotEqual(0, status, output)
                self.assertEqual("", output)
                self.assertIn(expected_error, error)

        record.write_text(
            json.dumps(
                [
                    {"expected": "SEV1", "probes": {"good": "SEV1", "bad": "SEV4"}}
                    for _ in range(8)
                ]
            ),
            encoding="utf-8",
        )
        self.commit_repository_paths(root, message="Ship real calibration cases")

        status, output, error = self.run_cli("check", "calibration-dataset")

        self.assertEqual(0, status, error)
        self.assertIn("OK: calibration-dataset", output)

    def test_one_row_does_not_settle_what_a_whole_record_carries(self) -> None:
        """A heterogeneous file is the case the scan was never given.

        The scan seeded its candidate columns from the first row and deleted a
        column globally on the first row whose value was not a short string, so
        a single junk row in front of a verbatim labelled dataset emptied the
        candidates and answered "no label surface" for the whole file. Every
        fixture it had was uniformly well formed, so nothing pinned it.
        """

        root = self.create_scenario("heterogeneous-record", 304)
        record = root / "project" / "traigent-runs" / "events.jsonl"
        record.parent.mkdir()
        manifest = valid_manifest("heterogeneous-record", 304)
        catalog = manifest["catalog"]
        assert isinstance(catalog, dict)
        catalog["non_dataset_files"] = ["project/traigent-runs/events.jsonl"]
        self.write_manifest(root, manifest)
        labelled = "".join(json.dumps(row) + "\n" for row in self.labelled_rows(8))

        for name, dressing in (
            ("an empty object", "{}\n"),
            ("a row whose label is a number", json.dumps({"output": 7}) + "\n"),
            ("a line of prose", "these are just some notes\n"),
            ("a bare scalar", "42\n"),
            ("a comment and a blank line", "# events\n\n"),
            ("an empty array", "[]\n"),
        ):
            with self.subTest(dressing=name):
                record.write_text(dressing + labelled, encoding="utf-8")
                self.commit_repository_paths(root, message=f"Dress with {name}")

                status, output, error = self.run_cli("check", "heterogeneous-record")

                self.assertNotEqual(
                    0,
                    status,
                    f"{name} in front of a labelled dataset is dressing, not an "
                    "answer about the rows behind it",
                )
                self.assertEqual("", output)
                self.assertIn("carry a closed label surface", error)

        record.write_bytes(
            "\ufeff# events\n".encode("utf-8") + labelled.encode("utf-8")
        )
        self.commit_repository_paths(root, message="Dress with a byte-order mark")

        status, output, error = self.run_cli("check", "heterogeneous-record")

        self.assertNotEqual(0, status, output)
        self.assertIn("carry a closed label surface", error)

        record.write_text(
            "# events\n"
            + "".join(
                json.dumps({"event": f"step-{index}", "sequence": index}) + "\n"
                for index in range(8)
            ),
            encoding="utf-8",
        )
        self.commit_repository_paths(root, message="Ship a real run record")

        status, output, error = self.run_cli("check", "heterogeneous-record")

        self.assertEqual(
            0,
            status,
            "counting rows rather than letting one veto must not start "
            f"refusing the run records this key exists for: {error}",
        )
        self.assertIn("OK: heterogeneous-record", output)

    def test_a_junk_row_does_not_suppress_the_oversized_line_refusal(self) -> None:
        """Abandoning on row one also threw away the refusal waiting on row two."""

        root = self.create_scenario("suppressed-refusal", 305)
        record = root / "project" / "traigent-runs" / "events.jsonl"
        record.parent.mkdir()
        record.write_bytes(
            b"{}\n"
            + b'{"pad": "'
            + b"x" * (2 * scenario.MAX_DATASET_ROW_BYTES)
            + b'"}\n'
        )
        manifest = valid_manifest("suppressed-refusal", 305)
        catalog = manifest["catalog"]
        assert isinstance(catalog, dict)
        catalog["non_dataset_files"] = ["project/traigent-runs/events.jsonl"]
        self.write_manifest(root, manifest)
        self.commit_repository_paths(
            root, message="Hide a long line behind a short one"
        )

        status, output, error = self.run_cli("check", "suppressed-refusal")

        self.assertNotEqual(0, status, output)
        self.assertEqual("", output)
        self.assertIn("carries a line longer than", error)

    def test_a_labelled_delimited_table_is_still_a_labelled_dataset(self) -> None:
        """A labelled CSV reaches a worker as readably as a labelled JSONL file."""

        root = self.create_scenario("delimited-record", 306)
        record = root / "project" / "traigent-runs" / "events.csv"
        record.parent.mkdir()
        manifest = valid_manifest("delimited-record", 306)
        catalog = manifest["catalog"]
        assert isinstance(catalog, dict)
        catalog["non_dataset_files"] = ["project/traigent-runs/events.csv"]
        self.write_manifest(root, manifest)
        rows = self.labelled_rows(8)

        for name, delimiter in (("commas", ","), ("tabs", "\t"), ("pipes", "|")):
            with self.subTest(separator=name):
                record.write_text(
                    f"report{delimiter}severity\n"
                    + "".join(
                        f"{row['input']}{delimiter}{row['output']}\n" for row in rows
                    ),
                    encoding="utf-8",
                )
                self.commit_repository_paths(root, message=f"Ship a table of {name}")

                status, output, error = self.run_cli("check", "delimited-record")

                self.assertNotEqual(0, status, output)
                self.assertEqual("", output)
                self.assertIn("carry a closed label surface", error)
                self.assertIn("severity", error)

        record.write_text(
            "Notes on the run\n"
            "The first attempt timed out, so we retried it.\n"
            "Then, after a while, it settled.\n"
            "Nothing else to report.\n"
            "Reviewed by the on-call engineer.\n"
            "Filed for the record.\n",
            encoding="utf-8",
        )
        self.commit_repository_paths(root, message="Ship prose instead")

        status, output, error = self.run_cli("check", "delimited-record")

        self.assertEqual(
            0,
            status,
            "lines that disagree about how many fields they have are not a "
            f"table, and prose is not a labelled dataset: {error}",
        )
        self.assertIn("OK: delimited-record", output)

    def test_a_label_nested_below_the_top_level_is_still_a_label(self) -> None:
        """Nesting the answer key one level down used to make it invisible.

        The scan named a row's top-level keys and the sweep compared roots, so
        an ``absent`` shape with the label at ``metadata.severity`` sat inside a
        ``metadata`` root the catalog already described and nothing looked
        further.
        """

        root = self.create_scenario("nested-label", 307)
        manifest = valid_manifest("nested-label", 307)
        catalog = manifest["catalog"]
        assert isinstance(catalog, dict)
        dataset = catalog["datasets"][0]
        dataset.update(
            {
                "label_field": None,
                "label_shape": {
                    "kind": "absent",
                    "surface_label_count": 0,
                    "label_counts": {},
                },
                "passthrough_fields": ["metadata.severity"],
                "rows": 8,
                "unique_inputs": 8,
                "splits": {"field": "metadata.split", "counts": {"tuning": 8}},
                "difficulty_strata": {
                    "field": "metadata.difficulty",
                    "counts": {"easy": 8},
                },
            }
        )
        self.write_manifest(root, manifest)
        self.write_rows(
            root,
            [
                {
                    "input": f"example-{index}",
                    "metadata": {
                        "split": "tuning",
                        "difficulty": "easy",
                        "severity": "SEV1" if index % 2 else "SEV2",
                    },
                }
                for index in range(8)
            ],
        )

        status, output, error = self.run_cli("check", "nested-label")

        self.assertNotEqual(
            0,
            status,
            "a label one level down is still a label, and declaring the object "
            "around it does not describe it",
        )
        self.assertEqual("", output)
        self.assertIn("the shape of a label", error)
        self.assertIn("metadata.severity", error)

        self.write_rows(
            root,
            [
                {
                    "input": f"example-{index}",
                    "metadata": {
                        "split": "tuning",
                        "difficulty": "easy",
                        "severity": f"ticket-{index}",
                    },
                }
                for index in range(8)
            ],
        )

        status, output, error = self.run_cli("check", "nested-label")

        self.assertEqual(
            0,
            status,
            "a nested column whose value is different in every row is an "
            f"identifier, which is what a passthrough is for: {error}",
        )
        self.assertIn("OK: nested-label", output)

    def test_every_column_a_row_carries_is_named_down_to_the_leaf(self) -> None:
        """The sweep compared roots, so a nested column shipped undescribed."""

        root = self.create_scenario("nested-column", 308)
        manifest = valid_manifest("nested-column", 308)
        self.write_manifest(root, manifest)
        self.write_rows(
            root,
            [
                {
                    "input": "example",
                    "output": "A",
                    "metadata": {
                        "split": "tuning",
                        "difficulty": "easy",
                        "note": "an aside the catalog never mentions",
                    },
                }
            ],
        )

        status, output, error = self.run_cli("check", "nested-column")

        self.assertNotEqual(0, status, output)
        self.assertEqual("", output)
        self.assertIn("metadata.note", error)
        self.assertIn("which the catalog does not describe", error)

        dataset = manifest["catalog"]["datasets"][0]
        dataset["passthrough_fields"] = ["metadata.note"]
        self.write_manifest(root, manifest)

        status, output, error = self.run_cli("check", "nested-column")

        self.assertEqual(0, status, error)
        self.assertIn("OK: nested-column", output)

        dataset["passthrough_fields"] = ["metadata.note", "metadata.absent"]
        self.write_manifest(root, manifest)

        status, output, error = self.run_cli("check", "nested-column")

        self.assertNotEqual(
            0,
            status,
            "a declaration naming a nested column no row carries outlives what "
            "it described, exactly as a top-level one does",
        )
        self.assertIn("metadata.absent", error)

    def test_a_structured_column_is_described_by_naming_it_once(self) -> None:
        """Declaring a field describes its subtree, not one key at a time."""

        root = self.create_scenario("structured-input", 309)
        manifest = valid_manifest("structured-input", 309)
        catalog = manifest["catalog"]
        assert isinstance(catalog, dict)
        catalog["datasets"][0]["input_field"] = "input"
        self.write_manifest(root, manifest)
        self.write_rows(
            root,
            [
                {
                    "input": {"report": "a page is down", "region": "eu-west"},
                    "output": "A",
                    "metadata": {"split": "tuning", "difficulty": "easy"},
                }
            ],
        )

        status, output, error = self.run_cli("check", "structured-input")

        self.assertEqual(
            0,
            status,
            "the catalog names `input`, so the keys inside it are described; "
            f"asking for `input.region` would be asking for the model's own "
            f"input shape: {error}",
        )
        self.assertIn("OK: structured-input", output)

    def test_reading_a_delimited_record_does_not_read_it_whole(self) -> None:
        """Falling back to a table must not give up the streaming read.

        The JSON row stream is read a line at a time. The delimited reading
        behind it has to be too, or a record that is not JSON costs its whole
        length: the separator is chosen from the header alone and the rest is
        streamed.
        """

        root = self.create_scenario("large-table", 310)
        record = root / "project" / "traigent-runs" / "events.csv"
        record.parent.mkdir()
        size = 16 * scenario.MAX_DATASET_ROW_BYTES
        # Long lines rather than many short ones: the property under test is
        # that the file is never held whole, and tracemalloc makes counting a
        # million tiny rows cost more than the read it is measuring.
        line = "step," + "x" * 900 + "\n"
        record.write_text("event,note\n" + line * (size // len(line)), encoding="utf-8")
        manifest = valid_manifest("large-table", 310)
        catalog = manifest["catalog"]
        assert isinstance(catalog, dict)
        catalog["non_dataset_files"] = ["project/traigent-runs/events.csv"]
        self.write_manifest(root, manifest)
        self.commit_repository_paths(root, message="Ship a large table")

        tracemalloc.start()
        try:
            status, output, error = self.run_cli("check", "large-table")
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()

        self.assertEqual(0, status, error)
        self.assertIn("OK: large-table", output)
        self.assertLess(
            peak,
            4 * scenario.MAX_DATASET_ROW_BYTES,
            "reading a delimited record must cost the longest line the bank can "
            f"accept, not the size of the file; this one is {size} bytes",
        )

    def test_a_ragged_line_does_not_hide_the_table_behind_it(self) -> None:
        """One line that is not a row is not an answer about the rows that are.

        This is the same defect as a junk row in front of a labelled JSONL file,
        one file format along: abandoning the whole table on a line that
        disagrees with the header would let a labelled CSV ship behind a single
        trailing note.
        """

        root = self.create_scenario("ragged-table", 311)
        record = root / "project" / "traigent-runs" / "events.csv"
        record.parent.mkdir()
        manifest = valid_manifest("ragged-table", 311)
        catalog = manifest["catalog"]
        assert isinstance(catalog, dict)
        catalog["non_dataset_files"] = ["project/traigent-runs/events.csv"]
        self.write_manifest(root, manifest)
        labelled = "".join(
            f"incident {index},{'SEV1' if index % 2 else 'SEV2'}\n"
            for index in range(8)
        )

        # The ragged line comes first, where abandoning on it hides everything
        # behind it -- the position a trailing one cannot test.
        record.write_text(
            "report,severity\n"
            + "a leading note with, two, extra, commas\n"
            + labelled
            + "a trailing note with, two, extra, commas\n",
            encoding="utf-8",
        )
        self.commit_repository_paths(root, message="Ship a labelled ragged table")

        status, output, error = self.run_cli("check", "ragged-table")

        self.assertNotEqual(0, status, output)
        self.assertEqual("", output)
        self.assertIn("carry a closed label surface", error)
        self.assertIn("severity", error)

        record.write_text(
            "report,severity\n"
            + "a leading note with, two, extra, commas\n"
            + "".join(f"incident {index},ticket-{index}\n" for index in range(8))
            + "a trailing note with, two, extra, commas\n",
            encoding="utf-8",
        )
        self.commit_repository_paths(root, message="Ship a ragged run record")

        status, output, error = self.run_cli("check", "ragged-table")

        self.assertEqual(
            0,
            status,
            "skipping the lines that are not rows must not start refusing the "
            f"records this key exists for: {error}",
        )
        self.assertIn("OK: ragged-table", output)

    def test_a_file_too_large_to_classify_is_refused_rather_than_assumed(
        self,
    ) -> None:
        """A file this check declines to read is not one it may vouch for."""

        root = self.create_scenario("huge-slot", 312)
        planted = root / "project" / "agent_impl.py"
        planted.write_bytes(b"# " + b"x" * scenario.MAX_SOURCE_CLASSIFY_BYTES + b"\n")
        manifest = valid_manifest("huge-slot", 312)
        catalog = manifest["catalog"]
        assert isinstance(catalog, dict)
        catalog["components"]["agent"]["path"] = "project/agent_impl.py"
        catalog["non_dataset_files"] = ["project/agent.py"]
        self.write_manifest(root, manifest)
        self.commit_repository_paths(root, message="Ship an unreadably large slot")

        status, output, error = self.run_cli("check", "huge-slot")

        self.assertNotEqual(
            0,
            status,
            "declining to read a file is not the same as establishing it is "
            "harmless, and the direction of the guess matters here",
        )
        self.assertEqual("", output)
        self.assertIn("larger than", error)
        self.assertIn("cannot vouch for", error)

    def test_a_record_with_more_columns_than_can_be_named_is_refused(self) -> None:
        """A record whose columns cannot be enumerated has a label surface no one ruled out."""

        root = self.create_scenario("wide-record", 313)
        record = root / "project" / "traigent-runs" / "events.jsonl"
        record.parent.mkdir()
        record.write_text(
            "".join(
                json.dumps(
                    {
                        f"column-{column}": f"value-{row}"
                        for column in range(scenario.MAX_ROW_COLUMNS + 8)
                    }
                )
                + "\n"
                for row in range(4)
            ),
            encoding="utf-8",
        )
        manifest = valid_manifest("wide-record", 313)
        catalog = manifest["catalog"]
        assert isinstance(catalog, dict)
        catalog["non_dataset_files"] = ["project/traigent-runs/events.jsonl"]
        self.write_manifest(root, manifest)
        self.commit_repository_paths(root, message="Ship a very wide record")

        status, output, error = self.run_cli("check", "wide-record")

        self.assertNotEqual(0, status, output)
        self.assertEqual("", output)
        self.assertIn("distinct columns", error)
        self.assertIn("cannot be ruled out", error)

    def test_a_stray_json_line_does_not_exempt_a_table_from_the_scan(self) -> None:
        """One JSON row inside a labelled CSV must not veto the table around it.

        The table reading used to run only when the whole file failed to be a
        JSON row stream, so a single ``{}`` line made the file "JSON rows" and
        the labelled table around it was never scanned -- the one-line-veto
        defect again, worn as a format choice.
        """

        root = self.create_scenario("json-dressed-table", 314)
        record = root / "project" / "traigent-runs" / "events.csv"
        record.parent.mkdir()
        manifest = valid_manifest("json-dressed-table", 314)
        catalog = manifest["catalog"]
        assert isinstance(catalog, dict)
        catalog["non_dataset_files"] = ["project/traigent-runs/events.csv"]
        self.write_manifest(root, manifest)
        record.write_text(
            "report,severity\n"
            + "{}\n"
            + "".join(
                f"incident {index},{'SEV1' if index % 2 else 'SEV2'}\n"
                for index in range(8)
            ),
            encoding="utf-8",
        )
        self.commit_repository_paths(root, message="Dress the table with a JSON row")

        status, output, error = self.run_cli("check", "json-dressed-table")

        self.assertNotEqual(
            0,
            status,
            "a stray JSON line is one row of the JSON reading, not an answer "
            "about the table around it",
        )
        self.assertEqual("", output)
        self.assertIn("carry a closed label surface", error)
        self.assertIn("severity", error)

        record.write_text(
            "report,severity\n"
            + "{}\n"
            + "".join(f"incident {index},ticket-{index}\n" for index in range(8)),
            encoding="utf-8",
        )
        self.commit_repository_paths(root, message="Ship an identifier table")

        status, output, error = self.run_cli("check", "json-dressed-table")

        self.assertEqual(
            0,
            status,
            f"an identifier table dressed with a JSON row is still a record: "
            f"{error}",
        )
        self.assertIn("OK: json-dressed-table", output)

    def test_a_note_above_the_header_does_not_hide_the_table(self) -> None:
        """The header is the first line that reads as one, not line one.

        Committing to line one re-created the one-line-veto defect in the last
        position the ragged-line fix could not reach: one prose note above the
        header and the whole labelled table was invisible.
        """

        root = self.create_scenario("noted-table", 315)
        record = root / "project" / "traigent-runs" / "events.csv"
        record.parent.mkdir()
        manifest = valid_manifest("noted-table", 315)
        catalog = manifest["catalog"]
        assert isinstance(catalog, dict)
        catalog["non_dataset_files"] = ["project/traigent-runs/events.csv"]
        self.write_manifest(root, manifest)
        record.write_text(
            "Ops notes from the run\n"
            + "report,severity\n"
            + "".join(
                f"incident {index},{'SEV1' if index % 2 else 'SEV2'}\n"
                for index in range(8)
            ),
            encoding="utf-8",
        )
        self.commit_repository_paths(root, message="Put a note above the header")

        status, output, error = self.run_cli("check", "noted-table")

        self.assertNotEqual(
            0,
            status,
            "a note above the header is the noise around the table, not a "
            "verdict about it",
        )
        self.assertEqual("", output)
        self.assertIn("carry a closed label surface", error)
        self.assertIn("severity", error)

        record.write_text(
            "Ops notes from the run\n"
            + "report,severity\n"
            + "".join(f"incident {index},ticket-{index}\n" for index in range(8)),
            encoding="utf-8",
        )
        self.commit_repository_paths(root, message="Ship an identifier table")

        status, output, error = self.run_cli("check", "noted-table")

        self.assertEqual(
            0,
            status,
            f"finding the header must not start refusing identifier tables: "
            f"{error}",
        )
        self.assertIn("OK: noted-table", output)

    def test_a_row_nested_past_the_walk_is_refused_not_invisible(self) -> None:
        """Depth overflow is a refusal, the same answer column overflow gives.

        A non-empty object at the walk's cap used to be yielded as an opaque
        cell, and an opaque cell is never a short string, so a label one level
        below the cap was invisible to the disguised-label scan -- the
        defeat-by-nesting defect again, one constant down. A declared field
        path deeper than the walk can reach is refused when the manifest is
        read, because a field the checks could never see is a field they may
        not vouch for.
        """

        def wrapped(value: object) -> dict[str, object]:
            wrapped_value: object = value
            for name in ("e", "d", "c", "b"):
                wrapped_value = {name: wrapped_value}
            assert isinstance(wrapped_value, dict)
            return wrapped_value

        root = self.create_scenario("deep-rows", 316)
        manifest = valid_manifest("deep-rows", 316)
        catalog = manifest["catalog"]
        assert isinstance(catalog, dict)
        dataset = catalog["datasets"][0]
        dataset.update(
            {
                "label_field": None,
                "label_shape": {
                    "kind": "absent",
                    "surface_label_count": 0,
                    "label_counts": {},
                },
                "passthrough_fields": ["a"],
                "rows": 8,
                "unique_inputs": 8,
                "splits": {"field": "metadata.split", "counts": {"tuning": 8}},
                "difficulty_strata": {
                    "field": "metadata.difficulty",
                    "counts": {"easy": 8},
                },
            }
        )
        self.write_manifest(root, manifest)
        self.write_rows(
            root,
            [
                {
                    "input": f"example-{index}",
                    "metadata": {"split": "tuning", "difficulty": "easy"},
                    "a": wrapped({"severity": "SEV1" if index % 2 else "SEV2"}),
                }
                for index in range(8)
            ],
        )

        status, output, error = self.run_cli("check", "deep-rows")

        self.assertNotEqual(
            0,
            status,
            "a label below the walk's cap is a label no one ruled out",
        )
        self.assertEqual("", output)
        self.assertIn("nests objects deeper than", error)
        self.assertIn("cannot be ruled out", error)

        dataset["passthrough_fields"] = ["a.b.c.d.e.f"]
        self.write_manifest(root, manifest)

        status, output, error = self.run_cli("check", "deep-rows")

        self.assertNotEqual(
            0,
            status,
            "a declared path the walk can never reach is unsupported, not "
            "quietly unenforced",
        )
        self.assertEqual("", output)
        self.assertIn("dotted segments, deeper than", error)

        dataset["passthrough_fields"] = ["a"]
        self.write_manifest(root, manifest)
        self.write_rows(
            root,
            [
                {
                    "input": f"example-{index}",
                    "metadata": {"split": "tuning", "difficulty": "easy"},
                    "a": wrapped(f"ticket-{index}"),
                }
                for index in range(8)
            ],
        )

        status, output, error = self.run_cli("check", "deep-rows")

        self.assertEqual(
            0,
            status,
            f"an identifier at the depth the walk does reach is what a "
            f"passthrough is for: {error}",
        )
        self.assertIn("OK: deep-rows", output)

    def test_an_empty_object_where_declared_leaves_live_is_not_a_column(
        self,
    ) -> None:
        """A row whose declared object is empty ships nothing undescribed.

        Enumerating to the leaf made ``"extra": {}`` a refused column when only
        ``extra.note`` was declared -- a regression from the root comparison,
        which passed it. An empty object where declared leaves live carries
        none of them, and no other column either; an empty object nothing
        declares is still a column the catalog has to name.
        """

        root = self.create_scenario("empty-extra", 317)
        manifest = self.labelled_manifest(
            "empty-extra", 317, rows=2, label_counts={"A": 2}
        )
        catalog = manifest["catalog"]
        assert isinstance(catalog, dict)
        dataset = catalog["datasets"][0]
        dataset["passthrough_fields"] = ["extra.note"]
        self.write_manifest(root, manifest)
        self.write_rows(
            root,
            [
                {
                    "input": "example-0",
                    "output": "A",
                    "metadata": {"split": "tuning", "difficulty": "easy"},
                    "extra": {"note": "an aside the catalog names"},
                },
                {
                    "input": "example-1",
                    "output": "A",
                    "metadata": {"split": "tuning", "difficulty": "easy"},
                    "extra": {},
                },
            ],
        )

        status, output, error = self.run_cli("check", "empty-extra")

        self.assertEqual(
            0,
            status,
            f"an empty object under a declared leaf carries no column: {error}",
        )
        self.assertIn("OK: empty-extra", output)

        dataset["passthrough_fields"] = []
        self.write_manifest(root, manifest)
        self.write_rows(
            root,
            [
                {
                    "input": f"example-{index}",
                    "output": "A",
                    "metadata": {"split": "tuning", "difficulty": "easy"},
                    "extra": {},
                }
                for index in range(2)
            ],
        )

        status, output, error = self.run_cli("check", "empty-extra")

        self.assertNotEqual(
            0,
            status,
            "an empty object nothing declares is still a column to name",
        )
        self.assertEqual("", output)
        self.assertIn("carries extra, which the catalog does not describe", error)

    def test_a_missing_dataset_refuses_a_passthrough_declaration(self) -> None:
        """A dataset that ships no rows has no columns for a declaration to describe.

        ``state: missing`` skipped all materialized dataset validation, so a
        ``passthrough_fields`` entry describing nothing -- against
        CONTRIBUTING's "an entry no row carries is refused" -- was accepted.
        """

        root = self.create_scenario("ghost-passthrough", 318)
        manifest = valid_manifest("ghost-passthrough", 318)
        catalog = manifest["catalog"]
        assert isinstance(catalog, dict)
        catalog["starting_condition"] = "gaps-present"
        catalog["components"]["data"] = {"state": "missing", "paths": []}
        catalog["datasets"][0].update(
            {
                "state": "missing",
                "path": None,
                "format": None,
                "label_field": None,
                "rows": 0,
                "unique_inputs": 0,
                "splits": {"field": None, "counts": {}},
                "difficulty_strata": {"field": None, "counts": {}},
                "label_shape": {
                    "kind": "absent",
                    "surface_label_count": 0,
                    "label_counts": {},
                },
                "passthrough_fields": ["ghost_column"],
            }
        )
        self.write_manifest(root, manifest)
        self.remove_repository_paths(
            root / "project" / "input.txt", message="Stop shipping the dataset"
        )

        status, output, error = self.run_cli("check", "ghost-passthrough")

        self.assertNotEqual(
            0,
            status,
            "a declaration describing nothing outlives what it described",
        )
        self.assertEqual("", output)
        self.assertIn("must be empty when state is missing", error)

        catalog["datasets"][0]["passthrough_fields"] = []
        self.write_manifest(root, manifest)

        status, output, error = self.run_cli("check", "ghost-passthrough")

        self.assertEqual(0, status, error)
        self.assertIn("OK: ghost-passthrough", output)

    def test_a_non_dataset_file_may_not_also_be_a_component_path(self) -> None:
        """The catalog's file categories are exclusive, as the error contract says.

        The exclusivity check compared ``non_dataset_files`` against dataset
        paths only, so the same file could be the evaluator and a "non-dataset
        file" in one catalog.
        """

        root = self.create_scenario("double-declared", 319)
        manifest = valid_manifest("double-declared", 319)
        catalog = manifest["catalog"]
        assert isinstance(catalog, dict)
        catalog["non_dataset_files"] = ["project/evaluator.py"]
        self.write_manifest(root, manifest)

        status, output, error = self.run_cli("check", "double-declared")

        self.assertNotEqual(
            0,
            status,
            "one file may not be a component and a non-dataset file at once",
        )
        self.assertEqual("", output)
        self.assertIn("also declared as component, data, or calibration paths", error)
        self.assertIn("project/evaluator.py", error)

        catalog["non_dataset_files"] = []
        self.write_manifest(root, manifest)

        status, output, error = self.run_cli("check", "double-declared")

        self.assertEqual(0, status, error)
        self.assertIn("OK: double-declared", output)

    def test_a_line_just_past_the_cap_is_refused_not_read(self) -> None:
        """The oversized-line refusal starts at the cap, not one read block later.

        The line reader length-checked only the tail still waiting for its
        newline, so a line up to 64KiB past ``MAX_DATASET_ROW_BYTES`` was
        yielded and parsed instead of refused -- a window one read chunk wide
        between the docstring and the loop.
        """

        root = self.create_scenario("window-line", 320)
        record = root / "project" / "traigent-runs" / "events.jsonl"
        record.parent.mkdir()
        manifest = valid_manifest("window-line", 320)
        catalog = manifest["catalog"]
        assert isinstance(catalog, dict)
        catalog["non_dataset_files"] = ["project/traigent-runs/events.jsonl"]
        self.write_manifest(root, manifest)
        framing = len(b'{"pad": ""}')
        record.write_bytes(
            b'{"pad": "'
            + b"x" * (scenario.MAX_DATASET_ROW_BYTES + 1 - framing)
            + b'"}\n'
        )
        self.commit_repository_paths(root, message="Ship a line one byte too long")

        status, output, error = self.run_cli("check", "window-line")

        self.assertNotEqual(
            0,
            status,
            "one byte past the cap is past the cap, not inside a 64KiB grace",
        )
        self.assertEqual("", output)
        self.assertIn("carries a line longer than", error)

        record.write_bytes(
            b'{"pad": "' + b"x" * (scenario.MAX_DATASET_ROW_BYTES - framing) + b'"}\n'
        )
        self.commit_repository_paths(root, message="Ship a line exactly at the cap")

        status, output, error = self.run_cli("check", "window-line")

        self.assertEqual(
            0,
            status,
            f"a line exactly at the cap is a line the bank accepts: {error}",
        )
        self.assertIn("OK: window-line", output)

    def test_a_denied_component_may_not_ship_as_an_interpreter_script(self) -> None:
        """A #! line marks an executable script whatever language follows.

        The byte sweep asked only whether shipped bytes parse as Python, so an
        evaluator rewritten as a shell script -- which no ``ast.parse`` will
        ever read -- shipped past a catalog declaring the evaluator missing.
        """

        root = self.create_scenario("shell-evaluator", 321)
        source = root / "project" / "evaluator.py"
        shell = root / "project" / "evaluator.sh"
        shell.write_text(
            '#!/bin/sh\nexec python3 -c "print(1.0)" "$@"\n', encoding="utf-8"
        )
        manifest = valid_manifest("shell-evaluator", 321)
        catalog = manifest["catalog"]
        assert isinstance(catalog, dict)
        catalog["starting_condition"] = "gaps-present"
        catalog["components"]["evaluator"].update(
            {"state": "missing", "path": None, "method": None}
        )
        catalog["non_dataset_files"] = ["project/evaluator.sh"]
        self.write_manifest(root, manifest)
        self.remove_repository_paths(source, message="Drop the Python evaluator")
        self.commit_repository_paths(root, message="Ship a shell evaluator")

        status, output, error = self.run_cli("check", "shell-evaluator")

        self.assertNotEqual(
            0,
            status,
            "an interpreter line is dressing over a component, not absence",
        )
        self.assertEqual("", output)
        self.assertIn("executable dressing", error)
        self.assertIn("an interpreter line", error)
        self.assertIn("project/evaluator.sh", error)

        shell.write_text('exec python3 -c "print(1.0)" "$@"\n', encoding="utf-8")
        self.commit_repository_paths(root, message="Ship a fragment instead")

        status, output, error = self.run_cli("check", "shell-evaluator")

        self.assertEqual(
            0,
            status,
            f"bytes that name no interpreter and read as no source pass: {error}",
        )
        self.assertIn("OK: shell-evaluator", output)

    def test_a_denied_component_may_not_ship_under_a_comment_prefix(self) -> None:
        """A uniform '# ' prefix is one editor command away from the source.

        Prefixing every line of the evaluator with ``# `` gave the sweep bytes
        with an empty parse -- data, it said -- while the worker received the
        component recoverable with a one-line strip.
        """

        root = self.create_scenario("commented-evaluator", 322)
        source = root / "project" / "evaluator.py"
        dressed = root / "project" / "evaluator-notes.txt"
        dressed.write_text(
            "".join(
                f"# {line}\n" if line else "#\n"
                for line in EVALUATOR_SOURCE.splitlines()
            ),
            encoding="utf-8",
        )
        manifest = valid_manifest("commented-evaluator", 322)
        catalog = manifest["catalog"]
        assert isinstance(catalog, dict)
        catalog["starting_condition"] = "gaps-present"
        catalog["components"]["evaluator"].update(
            {"state": "missing", "path": None, "method": None}
        )
        catalog["non_dataset_files"] = ["project/evaluator-notes.txt"]
        self.write_manifest(root, manifest)
        self.remove_repository_paths(source, message="Drop the Python evaluator")
        self.commit_repository_paths(root, message="Ship the evaluator as comments")

        status, output, error = self.run_cli("check", "commented-evaluator")

        self.assertNotEqual(
            0,
            status,
            "a comment prefix over Python source is dressing, not absence",
        )
        self.assertEqual("", output)
        self.assertIn("executable dressing", error)
        self.assertIn("uniform '# ' prefix", error)
        self.assertIn("project/evaluator-notes.txt", error)

        dressed.write_text(
            "# The evaluator is still being written.\n"
            "# Nothing here scores anything yet.\n",
            encoding="utf-8",
        )
        self.commit_repository_paths(root, message="Ship real notes instead")

        status, output, error = self.run_cli("check", "commented-evaluator")

        self.assertEqual(
            0,
            status,
            f"commented prose is notes, and notes are records: {error}",
        )
        self.assertIn("OK: commented-evaluator", output)

    def test_a_single_line_json_array_is_read_as_its_rows(self) -> None:
        """json.dumps of a labelled dataset is still that labelled dataset.

        A one-line JSON array used to be yielded as a single list-row, so
        every column had exactly one carrier and the scan found nothing -- the
        most common serialization of a dataset shipped the answer key.
        """

        root = self.create_scenario("array-record", 323)
        record = root / "project" / "traigent-runs" / "events.json"
        record.parent.mkdir()
        manifest = valid_manifest("array-record", 323)
        catalog = manifest["catalog"]
        assert isinstance(catalog, dict)
        catalog["non_dataset_files"] = ["project/traigent-runs/events.json"]
        self.write_manifest(root, manifest)
        record.write_text(json.dumps(self.labelled_rows(8)), encoding="utf-8")
        self.commit_repository_paths(root, message="Ship the dataset as one array")

        status, output, error = self.run_cli("check", "array-record")

        self.assertNotEqual(
            0,
            status,
            "an array of labelled rows on one line is those rows, not one row",
        )
        self.assertEqual("", output)
        self.assertIn("carry a closed label surface", error)
        self.assertIn("output", error)

        record.write_text(
            json.dumps(
                [{"event": f"step-{index}", "sequence": index} for index in range(8)]
            ),
            encoding="utf-8",
        )
        self.commit_repository_paths(root, message="Ship a real run record array")

        status, output, error = self.run_cli("check", "array-record")

        self.assertEqual(
            0,
            status,
            f"expanding an array must not refuse the run records this key "
            f"exists for: {error}",
        )
        self.assertIn("OK: array-record", output)

    def test_a_column_name_spelling_a_dot_is_refused_as_ambiguous(self) -> None:
        """A literal dotted key would inherit a declared nested path's exemption.

        The walk spells nesting with ``.``, so a top-level key literally named
        ``metadata.split`` produced the declared dimension field's path and
        was skipped by every check keyed on it -- a hidden column, and under
        an ``absent`` shape a hidden label surface.
        """

        root = self.create_scenario("dotted-column", 324)
        manifest = valid_manifest("dotted-column", 324)
        catalog = manifest["catalog"]
        assert isinstance(catalog, dict)
        dataset = catalog["datasets"][0]
        dataset.update(
            {
                "label_field": None,
                "label_shape": {
                    "kind": "absent",
                    "surface_label_count": 0,
                    "label_counts": {},
                },
                "rows": 8,
                "unique_inputs": 8,
                "splits": {"field": "metadata.split", "counts": {"tuning": 8}},
                "difficulty_strata": {
                    "field": "metadata.difficulty",
                    "counts": {"easy": 8},
                },
            }
        )
        self.write_manifest(root, manifest)
        self.write_rows(
            root,
            [
                {
                    "input": f"example-{index}",
                    "metadata": {"split": "tuning", "difficulty": "easy"},
                    "metadata.split": "SEV1" if index % 2 else "SEV2",
                }
                for index in range(8)
            ],
        )

        status, output, error = self.run_cli("check", "dotted-column")

        self.assertNotEqual(
            0,
            status,
            "a literal dotted key is ambiguous with the path it spells, and "
            "the collision is where a label hides",
        )
        self.assertEqual("", output)
        self.assertIn("literal '.'", error)
        self.assertIn("'metadata.split'", error)

        self.write_rows(
            root,
            [
                {
                    "input": f"example-{index}",
                    "metadata": {"split": "tuning", "difficulty": "easy"},
                }
                for index in range(8)
            ],
        )

        status, output, error = self.run_cli("check", "dotted-column")

        self.assertEqual(0, status, error)
        self.assertIn("OK: dotted-column", output)

    def test_the_missing_sweep_leaves_declared_data_and_config_alone(self) -> None:
        """An honest partially-prepared bundle ships datasets and config files.

        The sweep used to feed every unnamed shipped file through the source
        classifier, so a legal dataset past the 4MiB classify cap hard-failed
        with no possible declaration, and a flat YAML mapping or ``.env`` file
        -- both legal Python assignments -- read as smuggled component source.
        """

        root = self.create_scenario("prepared-bundle", 325)
        manifest = self.labelled_manifest(
            "prepared-bundle", 325, rows=8, label_counts={"A": 4, "B": 4}
        )
        catalog = manifest["catalog"]
        assert isinstance(catalog, dict)
        catalog["starting_condition"] = "gaps-present"
        catalog["components"]["evaluator"].update(
            {"state": "missing", "path": None, "method": None}
        )
        catalog["non_dataset_files"] = [
            "project/config.yml",
            "project/settings.env",
        ]
        self.write_manifest(root, manifest)
        padding = "x" * 550_000
        self.write_rows(
            root,
            [
                {
                    "input": f"example-{index}-{padding}",
                    "output": "A" if index % 2 else "B",
                    "metadata": {"split": "tuning", "difficulty": "easy"},
                }
                for index in range(8)
            ],
        )
        (root / "project" / "config.yml").write_text(
            "retries: 3\ntimeout_seconds: 30\nregion: eu-west-1\n",
            encoding="utf-8",
        )
        (root / "project" / "settings.env").write_text(
            "TRAIGENT_MODE=mock\nRETRIES=3\n", encoding="utf-8"
        )
        self.remove_repository_paths(
            root / "project" / "evaluator.py", message="Drop the evaluator"
        )
        self.commit_repository_paths(root, message="Ship a prepared bundle")

        dataset_size = (root / "project" / "input.txt").stat().st_size
        self.assertGreater(
            dataset_size,
            scenario.MAX_SOURCE_CLASSIFY_BYTES,
            "the fixture dataset must exceed the classify cap to pin the " "exemption",
        )

        status, output, error = self.run_cli("check", "prepared-bundle")

        self.assertEqual(
            0,
            status,
            f"a declared dataset and declared config are the honest bundle "
            f"this bank exists to ship: {error}",
        )
        self.assertIn("OK: prepared-bundle", output)

    def test_a_sparse_enum_in_a_run_log_is_telemetry_not_a_label(self) -> None:
        """A status field on six rows of two hundred is an honest record's shape.

        Counting only the carriers made the closed-label floor absolute, so
        the canonical run log -- most rows without a status, a few with
        ok/error -- read as a refused label surface with no way to declare it.
        The floor is relative now, and the dilution trade is stated in
        CONTRIBUTING.md.
        """

        root = self.create_scenario("sparse-enum", 326)
        record = root / "project" / "traigent-runs" / "events.jsonl"
        record.parent.mkdir()
        manifest = valid_manifest("sparse-enum", 326)
        catalog = manifest["catalog"]
        assert isinstance(catalog, dict)
        catalog["non_dataset_files"] = ["project/traigent-runs/events.jsonl"]
        self.write_manifest(root, manifest)

        def event_rows(total: int, carriers: int) -> str:
            rows: list[dict[str, object]] = []
            for index in range(total):
                row: dict[str, object] = {
                    "event": f"step-{index}",
                    "sequence": index,
                }
                if index < carriers:
                    row["status"] = "ok" if index % 2 else "error"
                rows.append(row)
            return "".join(json.dumps(row) + "\n" for row in rows)

        record.write_text(event_rows(200, 6), encoding="utf-8")
        self.commit_repository_paths(root, message="Ship a sparse run log")

        status, output, error = self.run_cli("check", "sparse-enum")

        self.assertEqual(
            0,
            status,
            f"six status cells in two hundred rows are telemetry: {error}",
        )
        self.assertIn("OK: sparse-enum", output)

        record.write_text(event_rows(200, 20), encoding="utf-8")
        self.commit_repository_paths(root, message="Thicken the enum to the floor")

        status, output, error = self.run_cli("check", "sparse-enum")

        self.assertNotEqual(
            0,
            status,
            "one carrier in ten is the floor, and the floor still refuses",
        )
        self.assertEqual("", output)
        self.assertIn("carry a closed label surface", error)
        self.assertIn("status", error)

    def test_check_rejects_shipped_python_that_does_not_parse(self) -> None:
        root = self.create_scenario("unparsable-code", 122)
        manifest = valid_manifest("unparsable-code", 122)
        catalog = manifest["catalog"]
        assert isinstance(catalog, dict)
        catalog["components"]["agent"]["path"] = "project/agent.py"
        self.write_manifest(root, manifest)
        agent = root / "project" / "agent.py"
        sentinel = Path(self.temporary_directory.name) / "agent-executed"
        agent.write_text(
            "from pathlib import Path\n"
            f"Path({str(sentinel)!r}).write_text('ran', encoding='utf-8')\n"
            "def broken(:\n",
            encoding="utf-8",
        )

        self.commit_repository_paths(agent, message="Ship unparsable Python")

        status, output, error = self.run_cli("check", "unparsable-code")

        self.assertNotEqual(0, status)
        self.assertEqual("", output)
        self.assertIn("ships Python that does not parse", error)
        self.assertIn("project/agent.py:3", error)
        self.assertFalse(sentinel.exists())

        agent.write_text(
            "from pathlib import Path\n"
            f"Path({str(sentinel)!r}).write_text('ran', encoding='utf-8')\n",
            encoding="utf-8",
        )
        self.commit_repository_paths(agent, message="Repair the shipped Python")

        status, output, error = self.run_cli("check", "unparsable-code")

        self.assertEqual(0, status, error)
        self.assertIn("OK: unparsable-code", output)
        self.assertFalse(sentinel.exists())

    def test_published_scenario_bank_passes_check(self) -> None:
        output = io.StringIO()
        error = io.StringIO()

        status = scenario.main(
            ["check"],
            scenarios_dir=scenario.DEFAULT_SCENARIOS_DIR,
            repository_root=scenario.REPOSITORY_ROOT,
            output=output,
            error=error,
        )

        self.assertEqual(0, status, error.getvalue())
        self.assertEqual("", error.getvalue())
        self.assertIn("OK: ", output.getvalue())

    def test_catalog_rejects_declared_dataset_facts_that_do_not_match_rows(
        self,
    ) -> None:
        root = self.create_scenario("fact-mismatch", 82)
        manifest_path = root / "scenario.json"

        mismatches: tuple[tuple[str, object, str], ...] = (
            (
                "rows",
                lambda manifest: (
                    manifest["catalog"]["datasets"][0].update(
                        {"rows": 2, "unique_inputs": 1}
                    ),
                    manifest["catalog"]["datasets"][0]["splits"].update(
                        {"counts": {"tuning": 2}}
                    ),
                    manifest["catalog"]["datasets"][0]["difficulty_strata"].update(
                        {"counts": {"easy": 2}}
                    ),
                ),
                "declares 2 but observed 1",
            ),
            (
                "split",
                lambda manifest: manifest["catalog"]["datasets"][0]["splits"].update(
                    {"counts": {"holdout": 1}}
                ),
                "do not match observed",
            ),
            (
                "difficulty",
                lambda manifest: manifest["catalog"]["datasets"][0][
                    "difficulty_strata"
                ].update({"counts": {"hard": 1}}),
                "do not match observed",
            ),
            (
                "surface labels",
                lambda manifest: manifest["catalog"]["datasets"][0].update(
                    {
                        "label_shape": {
                            "kind": "mapped-labels",
                            "surface_label_count": 1,
                            "label_counts": {"B": 1},
                        }
                    }
                ),
                "does not cover observed label 'A'",
            ),
        )
        for name, mutate, expected in mismatches:
            with self.subTest(name=name):
                manifest = valid_manifest("fact-mismatch", 82)
                mutate(manifest)
                manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
                status, output, error = self.run_cli("check", "fact-mismatch")
                self.assertNotEqual(0, status)
                self.assertEqual("", output)
                self.assertIn(expected, error)

    def test_catalog_validates_unique_inputs_and_surface_label_count(self) -> None:
        root = self.create_scenario("identity-facts", 83)
        manifest = valid_manifest("identity-facts", 83)
        dataset = manifest["catalog"]["datasets"][0]
        dataset["rows"] = 2
        dataset["unique_inputs"] = 2
        dataset["splits"]["counts"] = {"tuning": 2}
        dataset["difficulty_strata"]["counts"] = {"easy": 2}
        (root / "scenario.json").write_text(json.dumps(manifest), encoding="utf-8")
        (root / "project" / "input.txt").write_text(
            TEST_DATASET_ROW + TEST_DATASET_ROW,
            encoding="utf-8",
        )

        status, _, error = self.run_cli("check", "identity-facts")

        self.assertNotEqual(0, status)
        self.assertIn("unique_inputs", error)
        self.assertIn("declares 2 but observed 1", error)

        overstated = valid_manifest("identity-facts", 83)
        overstated["catalog"]["datasets"][0]["label_shape"]["surface_label_count"] = 2
        (root / "scenario.json").write_text(
            json.dumps(overstated),
            encoding="utf-8",
        )
        status, _, error = self.run_cli("list")
        self.assertNotEqual(0, status)
        self.assertIn("must equal the number of label_counts entries", error)

    def test_catalog_rejects_missing_paths_and_non_array_calibration(self) -> None:
        root = self.create_scenario("catalog-paths", 84)
        manifest = valid_manifest("catalog-paths", 84)
        manifest["catalog"]["components"]["agent"]["path"] = "project/missing-agent.py"
        (root / "scenario.json").write_text(json.dumps(manifest), encoding="utf-8")
        self.remove_repository_paths(
            root / "project" / "agent.py",
            message="Point the agent slot at a file that is not there",
        )

        status, _, error = self.run_cli("check", "catalog-paths")

        self.assertNotEqual(0, status)
        self.assertIn("catalog.components.agent.path", error)
        self.assertIn("cannot inspect", error)

        # The second half asks about the calibration slot, so the agent slot goes
        # back to naming a file that is there.
        (root / "project" / "agent.py").write_text(AGENT_SOURCE, encoding="utf-8")
        self.commit_repository_paths(
            root / "project" / "agent.py",
            message="Restore the agent source",
        )
        calibration_path = root / "project" / "calibration.json"
        calibration_path.write_text("{}\n", encoding="utf-8")
        manifest = valid_manifest("catalog-paths", 84)
        manifest["catalog"]["components"]["evaluator"]["calibration"] = {
            "path": "project/calibration.json",
            "case_count": 1,
        }
        (root / "scenario.json").write_text(json.dumps(manifest), encoding="utf-8")

        status, _, error = self.run_cli("check", "catalog-paths")

        self.assertNotEqual(0, status)
        self.assertIn("calibration root must be a JSON array", error)

    def test_catalog_jsonl_validation_is_strict_and_fail_closed(self) -> None:
        root = self.create_scenario("strict-jsonl", 85)
        dataset_path = root / "project" / "input.txt"
        invalid_rows = (
            ("\n", "must not be blank"),
            (
                '{"input":"first","input":"second","output":"A",'
                '"metadata":{"split":"tuning","difficulty":"easy"}}\n',
                "duplicate object key 'input'",
            ),
            ("[]\n", "must be a JSON object"),
            (
                '{"input":"example","metadata":'
                '{"split":"tuning","difficulty":"easy"}}\n',
                "is missing field 'output'",
            ),
        )
        for payload, expected in invalid_rows:
            with self.subTest(expected=expected):
                dataset_path.write_text(payload, encoding="utf-8")
                status, output, error = self.run_cli("check", "strict-jsonl")
                self.assertNotEqual(0, status)
                self.assertEqual("", output)
                self.assertIn(expected, error)

    def test_catalog_supports_declared_non_mapped_output_shapes(self) -> None:
        root = self.create_scenario("output-shapes", 86)
        cases = (
            (
                "unmapped-labels",
                "A",
                {
                    "kind": "unmapped-labels",
                    "surface_label_count": 1,
                    "label_counts": {},
                },
            ),
            (
                "free-text",
                "A detailed answer",
                {
                    "kind": "free-text",
                    "surface_label_count": 0,
                    "label_counts": {},
                },
            ),
            (
                "numeric",
                3.5,
                {
                    "kind": "numeric",
                    "surface_label_count": 0,
                    "label_counts": {},
                },
            ),
            (
                "structured",
                {"severity": "A"},
                {
                    "kind": "structured",
                    "surface_label_count": 0,
                    "label_counts": {},
                },
            ),
            (
                "absent",
                None,
                {
                    "kind": "absent",
                    "surface_label_count": 0,
                    "label_counts": {},
                },
            ),
        )
        for kind, output_value, label_shape in cases:
            with self.subTest(kind=kind):
                manifest = valid_manifest("output-shapes", 86)
                catalog = manifest["catalog"]
                dataset = catalog["datasets"][0]
                dataset["label_shape"] = label_shape
                row: dict[str, object] = {
                    "input": "example",
                    "metadata": {"split": "tuning", "difficulty": "easy"},
                }
                if kind == "absent":
                    catalog["starting_condition"] = "gaps-present"
                    catalog["components"]["data"]["state"] = "limited"
                    dataset["state"] = "limited"
                    dataset["label_field"] = None
                else:
                    row["output"] = output_value
                (root / "scenario.json").write_text(
                    json.dumps(manifest),
                    encoding="utf-8",
                )
                (root / "project" / "input.txt").write_text(
                    json.dumps(row) + "\n",
                    encoding="utf-8",
                )

                status, output, error = self.run_cli("check", "output-shapes")

                self.assertEqual(0, status, error)
                self.assertIn("OK: output-shapes", output)

    def test_check_requires_materialized_project_and_verifier_files(self) -> None:
        root = self.create_scenario("empty-content", 3, materialized=False)

        status, _, error = self.run_cli("check", "empty-content")
        self.assertNotEqual(0, status)
        self.assertIn("no regular files under project/", error)

        (root / "project" / "input.txt").write_text("input\n", encoding="utf-8")
        status, _, error = self.run_cli("check", "empty-content")
        self.assertNotEqual(0, status)
        self.assertIn("no regular files under verifier/", error)

    def test_check_requires_a_strict_expected_opening_contract(self) -> None:
        root = self.create_scenario("opening-contract", 30)
        expected_path = root / "verifier" / "expected-opening.json"
        (root / "verifier" / "README.md").write_text("contract\n", encoding="utf-8")
        expected_path.unlink()

        status, output, error = self.run_cli("check", "opening-contract")

        self.assertNotEqual(0, status)
        self.assertEqual("", output)
        self.assertIn("catalog.expected_route.verifier_contract", error)
        self.assertIn("cannot inspect", error)

        invalid_contracts: tuple[tuple[str, str, str], ...] = (
            (
                "duplicate key",
                '{"schema_version": 1, "schema_version": 1}',
                "duplicate object key",
            ),
            (
                "missing semantic field",
                json.dumps(
                    {
                        key: value
                        for key, value in expected_opening().items()
                        if key != "recommended_action"
                    }
                ),
                "missing required key(s): recommended_action",
            ),
            (
                "unknown top-level field",
                json.dumps({**expected_opening(), "unexpected": True}),
                "unknown key(s): unexpected",
            ),
            (
                "unknown display field",
                json.dumps(
                    {
                        **expected_opening(),
                        "display": {
                            **expected_opening()["display"],
                            "unexpected": True,
                        },
                    }
                ),
                "display: unknown key(s): unexpected",
            ),
            (
                "unknown scorecard field",
                json.dumps(
                    {
                        **expected_opening(),
                        "display": {
                            **expected_opening()["display"],
                            "overall": {
                                "score": 50,
                                "confidence": 0.5,
                                "unexpected": True,
                            },
                        },
                    }
                ),
                "display.overall: unknown key(s): unexpected",
            ),
            (
                "invalid caps",
                json.dumps({**expected_opening(), "caps": "none"}),
                "caps: must be an array",
            ),
            (
                "a condition slug where schema 2 records the whole cap",
                json.dumps({**expected_opening(), "caps": ["dataset-fully-synthetic"]}),
                "caps[0]: must be an object",
            ),
            (
                "a cap without its routing",
                json.dumps(
                    {
                        **expected_opening(),
                        "caps": [{"condition": "dataset-fully-synthetic"}],
                    }
                ),
                "caps[0]: missing required key(s): asks, blocks, ceiling",
            ),
            (
                "a cap ceiling that is not a score",
                json.dumps(
                    {
                        **expected_opening(),
                        "caps": [
                            {
                                "condition": "dataset-fully-synthetic",
                                "ceiling": "65",
                                "blocks": False,
                                "asks": False,
                            }
                        ],
                    }
                ),
                "caps[0].ceiling: must be null or an integer 0 to 100",
            ),
            (
                "a schema 1 contract in the tree",
                json.dumps(
                    {
                        **{
                            key: value
                            for key, value in expected_opening().items()
                            if key != "readiness_schema_version"
                        },
                        "schema_version": 1,
                    }
                ),
                "schema_version: must equal 2",
            ),
            (
                "a schema version written as a float",
                json.dumps({**expected_opening(), "schema_version": 2.0}),
                "schema_version: must equal 2",
            ),
            (
                "a band the guide does not print",
                json.dumps({**expected_opening(), "band": "GOOD"}),
                "band: must be one of NOT READY, PARTIAL, WORKABLE, STRONG",
            ),
            (
                "no readiness schema",
                json.dumps({**expected_opening(), "readiness_schema_version": True}),
                "readiness_schema_version: must be a positive integer",
            ),
            (
                "empty pillars",
                json.dumps(
                    {
                        **expected_opening(),
                        "display": {
                            "overall": {"score": 50, "confidence": 0.5},
                            "pillars": {},
                        },
                    }
                ),
                "display.pillars: must contain at least one pillar",
            ),
            (
                "score out of range",
                json.dumps(
                    {
                        **expected_opening(),
                        "display": {
                            **expected_opening()["display"],
                            "overall": {"score": 101, "confidence": 0.5},
                        },
                    }
                ),
                "display.overall.score: must be between 0 and 100",
            ),
            (
                "pillar confidence out of range",
                json.dumps(
                    {
                        **expected_opening(),
                        "display": {
                            "overall": {"score": 50, "confidence": 0.5},
                            "pillars": {
                                "novel-pillar": {
                                    "score": 50,
                                    "confidence": -0.1,
                                }
                            },
                        },
                    }
                ),
                "display.pillars.novel-pillar.confidence: must be between 0 and 1",
            ),
        )
        for label, payload, expected_error in invalid_contracts:
            with self.subTest(label=label):
                expected_path.write_text(payload, encoding="utf-8")
                status, output, error = self.run_cli("check", "opening-contract")
                self.assertNotEqual(0, status)
                self.assertEqual("", output)
                self.assertIn(expected_error, error)

    def test_check_rejects_symlinks_anywhere_in_scenario(self) -> None:
        root = self.create_scenario("linked", 4)
        (root / "project" / "linked.txt").symlink_to(root / "project" / "input.txt")

        status, output, error = self.run_cli("check", "linked")

        self.assertNotEqual(0, status)
        self.assertEqual("", output)
        self.assertIn("contains a symbolic link", error)

    def test_check_holds_the_replay_record_to_the_first_run(self) -> None:
        """`check` passed a record whose first step was `/usr/bin/touch`."""
        root = self.create_scenario("tampered-replay", 9)
        measurement = root / "verifier" / "measurement"
        measurement.mkdir()
        script = "$GUIDE/skills/traigent-first-run/scripts/readiness.py"
        readiness = ["$PYTHON", "-S", script, "--json"]
        record: dict[str, object] = {
            "guide_revision": "d07b62cd4abb6ecb6d2edcdcb2d535f02bb2c199",
            "steps": {"readiness": readiness},
        }
        (measurement / "invocation.json").write_text(json.dumps(record))
        status, output, error = self.run_cli("check", "tampered-replay")
        self.assertEqual(0, status, error)

        record["steps"] = {
            "preflight": ["/usr/bin/touch", "/tmp/ran"],
            "readiness": readiness,
        }
        (measurement / "invocation.json").write_text(json.dumps(record))
        status, output, error = self.run_cli("check", "tampered-replay")
        self.assertNotEqual(0, status)
        self.assertEqual("", output)
        self.assertIn("scenario 'tampered-replay'", error)
        self.assertIn("steps.preflight[0]", error)
        self.assertIn("'/usr/bin/touch'", error)

    def test_check_refuses_a_project_that_names_its_own_test(self) -> None:
        root = self.create_scenario("told-apart", 10)
        capped = {**expected_opening(), "caps": [SYNTHETIC_CAP]}
        (root / "verifier" / "expected-opening.json").write_text(json.dumps(capped))
        (root / "verifier" / "intended-opening.json").write_text(
            json.dumps(intended_opening(capped))
        )
        evaluator = root / "project" / "evaluator.py"
        status, _, error = self.run_cli("check", "told-apart")
        self.assertEqual(0, status, error)
        # The file is read a block at a time; these place a tell across the
        # first block boundary.
        straddle = scenario._FILE_READ_BLOCK_BYTES - 4 - len(EVALUATOR_SOURCE) - 1
        block = scenario._FILE_READ_BLOCK_BYTES
        for label, tell, written in (
            ("slug", "told-apart", "# case told-apart\n"),
            ("slug in a path", "told-apart", "# runs/told_apart/latest.json\n"),
            ("slug in camelCase", "told-apart", "toldApart = None\n"),
            ("cap", "dataset-fully-synthetic", "# expect DATASET_FULLY_SYNTHETIC\n"),
            (
                "cap in camelCase",
                "dataset-fully-synthetic",
                "datasetFullySynthetic = 1\n",
            ),
            ("contract", "expected-opening", "# compare with expected_opening.json\n"),
            ("contract as a constant", "expected-opening", "EXPECTED_OPENING = 1\n"),
            (
                "contract inside an identifier",
                "expected-opening",
                "expected_opening_balance = 0.0\n",
            ),
            ("directory after =", "verifier/", "CHECKS = 'x'\nCHECKS=verifier/rules\n"),
            ("directory after (", "verifier/", "# open(verifier/x)\n"),
            ("directory after :", "verifier/", "# rules:verifier/x\n"),
            ("directory after ,", "verifier/", "# a,verifier/x\n"),
            ("contract in camelCase", "expected-opening", "expectedOpening = {}\n"),
            ("contract dotted", "expected-opening", "# config.expected.opening\n"),
            ("contract joined", "expected-opening", "expectedopening = {}\n"),
            ("directory", "verifier/", "# see ../verifier/answers.json\n"),
            (
                "across a read",
                "verifier/",
                "#" + "x" * (straddle - 1) + "/verifier/x\n",
            ),
        ):
            with self.subTest(label=label):
                evaluator.write_text(EVALUATOR_SOURCE + written, encoding="utf-8")
                status, output, error = self.run_cli("check", "told-apart")
                self.assertNotEqual(0, status)
                self.assertEqual("", output)
                self.assertIn("ships project/evaluator.py, which names", error)
                self.assertIn(tell, error)
        # A token split inside a word, where the carried text meets the next
        # read's first letter, at the first boundary and at the second.
        for label, tell, written in (
            (
                "upper case across a read",
                "told-apart",
                tell_at(block - 2, "TOLD-APART"),
            ),
            ("constant across a read", "told-apart", tell_at(block - 2, "TOLD_APART")),
            (
                "upper case across a second read",
                "told-apart",
                tell_at(2 * block - 2, "TOLD-APART"),
            ),
            (
                "cap in upper case across a read",
                "dataset-fully-synthetic",
                tell_at(block - 3, "DATASET_FULLY_SYNTHETIC"),
            ),
            ("camelCase across a read", "told-apart", tell_at(block - 4, "toldApart")),
            (
                "a long separator run across a read",
                "told-apart",
                tell_at(block - 104, "told" + "_" * 200 + "apart"),
            ),
        ):
            with self.subTest(label=label):
                evaluator.write_text(written, encoding="utf-8")
                status, output, error = self.run_cli("check", "told-apart")
                self.assertNotEqual(0, status)
                self.assertEqual("", output)
                self.assertIn("ships project/evaluator.py, which names", error)
                self.assertIn(tell, error)

    def test_check_refuses_a_file_that_is_exactly_a_tell(self) -> None:
        """No newline after it and nothing before it: the whole file is the tell."""
        root = self.create_scenario("told-apart", 12)
        notes = root / "project" / "notes.txt"
        notes.write_bytes(b"notes\n")
        self.commit_repository_paths(notes, message="Ship notes")
        manifest = valid_manifest("told-apart", 12)
        catalog = manifest["catalog"]
        assert isinstance(catalog, dict)
        catalog["non_dataset_files"] = ["project/notes.txt"]
        self.write_manifest(root, manifest)
        status, _, error = self.run_cli("check", "told-apart")
        self.assertEqual(0, status, error)
        for label, tell, content in (
            ("slug", "told-apart", b"told-apart"),
            ("slug as a constant", "told-apart", b"TOLD_APART"),
            ("contract in camelCase", "expected-opening", b"expectedOpening"),
        ):
            with self.subTest(label=label):
                notes.write_bytes(content)
                status, output, error = self.run_cli("check", "told-apart")
                self.assertNotEqual(0, status)
                self.assertEqual("", output)
                self.assertIn("ships project/notes.txt, which names", error)
                self.assertIn(tell, error)

    def test_check_reads_prose_about_the_task_as_prose(self) -> None:
        """Words a real project uses for itself are not the names of its test."""
        root = self.create_scenario("told-apart", 11)
        capped = {**expected_opening(), "caps": [SYNTHETIC_CAP]}
        (root / "verifier" / "expected-opening.json").write_text(json.dumps(capped))
        (root / "verifier" / "intended-opening.json").write_text(
            json.dumps(intended_opening(capped))
        )
        evaluator = root / "project" / "evaluator.py"
        # `told-apart` ends exactly where the first read ends, and the word
        # goes on in the next one.
        ends_a_read = scenario._FILE_READ_BLOCK_BYTES - len(EVALUATOR_SOURCE) - 12
        for label, written in (
            (
                "a longer token across a read",
                "#" + "x" * ends_a_read + " told-apartment\n",
            ),
            ("the project's own name", "# Told apart: the agent entry point\n"),
            ("a common word", "# a verifier pass re-checks each rule\n"),
            ("a cap's words", "# every dataset row is fully synthetic\n"),
            ("a longer word", "# the unexpected opening move\n"),
            ("the contract's words", "# the expected opening balance\n"),
            ("the contract's words again", "# EXPECTED OPENING hours\n"),
            ("a longer token", "expected_openings = 3\n"),
            ("a directory named for a checker", "# rules live in sql_verifier/\n"),
            ("another such directory", "# see answer-verifier/output.txt\n"),
            ("a slug inside a longer token", "# the untold-apart story\n"),
        ):
            with self.subTest(label=label):
                evaluator.write_text(EVALUATOR_SOURCE + written, encoding="utf-8")
                status, output, error = self.run_cli("check", "told-apart")
                self.assertEqual(0, status, error)

    def test_check_fails_closed_when_tree_walk_cannot_read_an_entry(self) -> None:
        self.create_scenario("unreadable", 8)

        def fail_walk(*args: object, **kwargs: object) -> list[object]:
            onerror = kwargs["onerror"]
            self.assertTrue(callable(onerror))
            onerror(PermissionError("permission denied"))
            return []

        with mock.patch("scenario.os.walk", side_effect=fail_walk):
            status, output, error = self.run_cli("check", "unreadable")

        self.assertNotEqual(0, status)
        self.assertEqual("", output)
        self.assertIn("cannot inspect scenario 'unreadable'", error)

    def test_commands_never_execute_scenario_code(self) -> None:
        root = self.create_scenario("untrusted-code", 5)
        sentinel = Path(self.temporary_directory.name) / "executed"
        payload = (
            "from pathlib import Path\n"
            f"Path({str(sentinel)!r}).write_text('executed', encoding='utf-8')\n"
        )
        (root / "project" / "candidate.py").write_text(payload, encoding="utf-8")
        (root / "verifier" / "verify.py").write_text(payload, encoding="utf-8")

        for command in (("list",), ("show", "untrusted-code"), ("check", "5")):
            with self.subTest(command=command):
                status, _, error = self.run_cli(*command)
                self.assertEqual(0, status, error)
                self.assertFalse(sentinel.exists())

    def test_prepare_copies_only_worker_project_and_allowlisted_guide(self) -> None:
        root = self.create_scenario("prepared-case", 46)
        manifest = valid_manifest("prepared-case", 46)
        catalog = manifest["catalog"]
        assert isinstance(catalog, dict)
        catalog["non_dataset_files"] = ["project/run-check.sh"]
        self.write_manifest(root, manifest)
        tracked_runner = root / "project" / "run-check.sh"
        tracked_runner.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        tracked_runner.chmod(0o755)
        tracked_runner_path = os.fspath(
            tracked_runner.relative_to(self.repository_root)
        )
        subprocess.run(
            [
                "git",
                "-C",
                os.fspath(self.repository_root),
                "add",
                "--",
                tracked_runner_path,
                os.fspath((root / "scenario.json").relative_to(self.repository_root)),
            ],
            check=True,
        )
        subprocess.run(
            [
                "git",
                "-C",
                os.fspath(self.repository_root),
                "update-index",
                "--chmod=+x",
                "--",
                tracked_runner_path,
            ],
            check=True,
        )
        subprocess.run(
            [
                "git",
                "-C",
                os.fspath(self.repository_root),
                "-c",
                "user.name=Scenario Tests",
                "-c",
                "user.email=scenario-tests@example.invalid",
                "commit",
                "-qm",
                "Add tracked executable project file",
            ],
            check=True,
        )
        (root / "project" / "empty-directory").mkdir()
        untracked_cache = root / "project" / "__pycache__"
        untracked_cache.mkdir()
        (untracked_cache / "candidate.pyc").write_bytes(b"local cache")
        (root / "project" / "local-payload.py").write_text(
            "raise RuntimeError('must not be copied')\n", encoding="utf-8"
        )
        guide_source = self.create_guide_source()
        first_output = Path(self.temporary_directory.name) / "run-one"
        second_output = Path(self.temporary_directory.name) / "run-two"

        status, output, error = self.run_cli(
            "prepare",
            "46",
            "--guide-src",
            str(guide_source),
            "--output",
            str(first_output),
        )
        second_status, _, second_error = self.run_cli(
            "prepare",
            "prepared-case",
            "--guide-src",
            str(guide_source),
            "--output",
            str(second_output),
        )

        self.assertEqual(0, status, error)
        self.assertEqual(0, second_status, second_error)
        self.assertEqual("", error)
        self.assertIn("Prepared: prepared-case", output)
        self.assertIn(f"Worker directory: {first_output / 'customer-project'}", output)
        self.assertIn(f"Captain record: {first_output / 'run.json'}", output)
        self.assertIn("Fresh-agent handoff:\n" + scenario.LOCAL_WORKER_HANDOFF, output)

        worker = first_output / "customer-project"
        self.assertEqual(
            TEST_DATASET_ROW,
            (worker / "input.txt").read_text(encoding="utf-8"),
        )
        self.assertFalse((worker / "empty-directory").exists())
        self.assertFalse((worker / "__pycache__").exists())
        self.assertFalse((worker / "local-payload.py").exists())
        guide_copy = worker / "traigent-first-run"
        self.assertTrue((guide_copy / "GUIDE.md").is_file())
        self.assertTrue(
            (guide_copy / "skills" / "traigent-first-run" / "SKILL.md").is_file()
        )
        self.assertTrue(
            os.access(
                guide_copy
                / "skills"
                / "traigent-first-run"
                / "scripts"
                / "readiness.py",
                os.X_OK,
            )
        )
        for copied_optional in scenario.OPTIONAL_GUIDE_FILES:
            self.assertTrue((guide_copy / copied_optional).is_file())
        self.assertEqual(
            "Test guide\nCopyright 2026 Traigent Ltd\n",
            (guide_copy / "NOTICE").read_text(encoding="utf-8"),
        )
        self.assertFalse((guide_copy / ".env").exists())
        self.assertFalse((guide_copy / "private-notes.md").exists())
        self.assertFalse(
            (
                guide_copy / "skills" / "traigent-first-run" / "scripts" / "__pycache__"
            ).exists()
        )
        self.assertFalse((worker / "scenario.json").exists())
        self.assertFalse((worker / "verifier").exists())

        first_manifest = json.loads(
            (first_output / "run.json").read_text(encoding="utf-8")
        )
        second_manifest = json.loads(
            (second_output / "run.json").read_text(encoding="utf-8")
        )
        self.assertEqual(first_manifest, second_manifest)
        self.assertEqual(1, first_manifest["schema_version"])
        self.assertEqual("phase-a-opening", first_manifest["phase"])
        self.assertEqual(
            {"legacy_id": 46, "slug": "prepared-case"},
            first_manifest["scenario"],
        )
        self.assertEqual(
            {
                "directory": "customer-project",
                "handoff": scenario.LOCAL_WORKER_HANDOFF,
            },
            first_manifest["worker"],
        )
        project_file = next(
            item
            for item in first_manifest["inputs"]["scenario_project"]["files"]
            if item["path"] == "input.txt"
        )
        expected_project_bytes = TEST_DATASET_ROW.encode("utf-8")
        self.assertEqual(
            hashlib.sha256(expected_project_bytes).hexdigest(),
            project_file["sha256"],
        )
        self.assertEqual(len(expected_project_bytes), project_file["size"])
        self.assertFalse(project_file["executable"])
        self.assertRegex(
            first_manifest["inputs"]["scenario_project"]["sha256"],
            r"^[0-9a-f]{64}$",
        )
        project_files = {
            item["path"]: item
            for item in first_manifest["inputs"]["scenario_project"]["files"]
        }
        contract_files = {
            item["path"]: item
            for item in first_manifest["inputs"]["scenario_contract"]["files"]
        }
        self.assertIn("scenario.json", contract_files)
        self.assertIn("verifier/expected-opening.json", contract_files)
        self.assertNotIn("verifier/expected-opening.json", project_files)
        self.assertFalse(project_files["input.txt"]["executable"])
        self.assertTrue(project_files["run-check.sh"]["executable"])
        expected_scenario_sha = subprocess.run(
            [
                "git",
                "-C",
                os.fspath(self.repository_root),
                "rev-parse",
                "HEAD",
            ],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        self.assertEqual(
            expected_scenario_sha,
            first_manifest["inputs"]["scenario_project"]["git_sha"],
        )
        self.assertEqual(
            expected_scenario_sha,
            first_manifest["inputs"]["scenario_contract"]["git_sha"],
        )
        expected_guide_sha = subprocess.run(
            ["git", "-C", os.fspath(guide_source), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        self.assertEqual(
            expected_guide_sha,
            first_manifest["inputs"]["guide_bundle"]["git_sha"],
        )
        guide_files = {
            item["path"]: item
            for item in first_manifest["inputs"]["guide_bundle"]["files"]
        }
        self.assertTrue(
            guide_files["skills/traigent-first-run/scripts/readiness.py"]["executable"]
        )
        self.assertFalse(guide_files["GUIDE.md"]["executable"])
        self.assertEqual(
            hashlib.sha256(b"Test guide\nCopyright 2026 Traigent Ltd\n").hexdigest(),
            guide_files["NOTICE"]["sha256"],
        )

    def test_prepare_requires_complete_guide_bundle_before_creating_output(
        self,
    ) -> None:
        self.create_scenario("needs-guide", 10)
        guide_source = self.create_guide_source()
        output_path = Path(self.temporary_directory.name) / "not-created"
        subprocess.run(
            ["git", "-C", os.fspath(guide_source), "rm", "-q", "GUIDE.md"],
            check=True,
        )
        subprocess.run(
            [
                "git",
                "-C",
                os.fspath(guide_source),
                "-c",
                "user.name=Scenario Tests",
                "-c",
                "user.email=scenario-tests@example.invalid",
                "commit",
                "-qm",
                "Remove required guide",
            ],
            check=True,
        )

        status, output, error = self.run_cli(
            "prepare",
            "needs-guide",
            "--guide-src",
            str(guide_source),
            "--output",
            str(output_path),
        )

        self.assertNotEqual(0, status)
        self.assertEqual("", output)
        self.assertIn("required guide file is not tracked", error)
        self.assertFalse(output_path.exists())

    def test_prepare_rejects_dirty_tracked_guide_content(self) -> None:
        self.create_scenario("dirty-guide", 14)
        guide_source = self.create_guide_source()
        tracked_skill = guide_source / "skills" / "traigent-first-run" / "SKILL.md"
        tracked_skill.write_text("locally changed\n", encoding="utf-8")
        output_path = Path(self.temporary_directory.name) / "dirty-output"

        status, output, error = self.run_cli(
            "prepare",
            "dirty-guide",
            "--guide-src",
            str(guide_source),
            "--output",
            str(output_path),
        )

        self.assertNotEqual(0, status)
        self.assertEqual("", output)
        self.assertIn("tracked allowlisted guide content has local changes", error)
        self.assertFalse(output_path.exists())

    def test_prepare_rejects_dirty_tracked_scenario_content(self) -> None:
        root = self.create_scenario("dirty-scenario", 15)
        guide_source = self.create_guide_source()
        (root / "project" / "input.txt").write_text(
            TEST_DATASET_ROW.replace('"example"', '"locally changed"'),
            encoding="utf-8",
        )
        output_path = Path(self.temporary_directory.name) / "dirty-scenario-output"

        status, output, error = self.run_cli(
            "prepare",
            "dirty-scenario",
            "--guide-src",
            str(guide_source),
            "--output",
            str(output_path),
        )

        self.assertNotEqual(0, status)
        self.assertEqual("", output)
        self.assertIn("tracked selected scenario content has local changes", error)
        self.assertFalse(output_path.exists())

    def test_prepare_fails_closed_when_sources_change_after_clean_check(self) -> None:
        original_run_git = scenario._run_git

        for target in ("scenario", "guide"):
            with self.subTest(target=target):
                root = self.create_scenario(f"racing-{target}", 30 + self.guide_counter)
                guide_source = self.create_guide_source()
                if target == "scenario":
                    changed_path = root / "project" / "input.txt"
                    clean_action = "check tracked scenario content"
                else:
                    changed_path = (
                        guide_source / "skills" / "traigent-first-run" / "SKILL.md"
                    )
                    clean_action = "check tracked guide content"
                output_path = (
                    Path(self.temporary_directory.name) / f"racing-{target}-output"
                )
                mutation_count = 0

                def mutate_after_clean_check(
                    repository_root: Path,
                    arguments: tuple[str, ...],
                    action: str,
                ) -> bytes:
                    nonlocal mutation_count
                    result = original_run_git(repository_root, arguments, action)
                    if action == clean_action and mutation_count == 0:
                        changed_path.write_text(
                            "changed after clean check\n", encoding="utf-8"
                        )
                        mutation_count += 1
                    return result

                with mock.patch(
                    "scenario._run_git", side_effect=mutate_after_clean_check
                ):
                    status, output, error = self.run_cli(
                        "prepare",
                        f"racing-{target}",
                        "--guide-src",
                        str(guide_source),
                        "--output",
                        str(output_path),
                    )

                self.assertEqual(1, mutation_count)
                self.assertNotEqual(0, status)
                self.assertEqual("", output)
                self.assertIn("has local changes", error)
                self.assertFalse(output_path.exists())

    def test_prepare_rejects_stage_zero_index_not_at_recorded_head(self) -> None:
        root = self.create_scenario("staged-scenario", 32)
        guide_source = self.create_guide_source()
        changed_path = root / "project" / "input.txt"
        changed_path.write_text(
            TEST_DATASET_ROW.replace('"example"', '"staged change"'),
            encoding="utf-8",
        )
        subprocess.run(
            [
                "git",
                "-C",
                os.fspath(self.repository_root),
                "add",
                os.fspath(changed_path.relative_to(self.repository_root)),
            ],
            check=True,
        )
        output_path = Path(self.temporary_directory.name) / "staged-output"

        status, output, error = self.run_cli(
            "prepare",
            "staged-scenario",
            "--guide-src",
            str(guide_source),
            "--output",
            str(output_path),
        )

        self.assertNotEqual(0, status)
        self.assertEqual("", output)
        self.assertIn(
            "stage-zero index does not match the recorded Git revision", error
        )
        self.assertFalse(output_path.exists())

    def test_prepare_binds_manifest_fields_to_the_recorded_revision(self) -> None:
        root = self.create_scenario("manifest-race", 33)
        guide_source = self.create_guide_source()
        manifest_path = root / "scenario.json"
        recorded_manifest = manifest_path.read_bytes()
        manifest_path.write_text(
            json.dumps(valid_manifest("manifest-race", 999)),
            encoding="utf-8",
        )
        output_path = Path(self.temporary_directory.name) / "manifest-race-output"
        original_validate_materialized = scenario.validate_materialized
        restore_count = 0

        def restore_recorded_manifest(selected: scenario.Scenario) -> dict[str, object]:
            nonlocal restore_count
            result = original_validate_materialized(selected)
            manifest_path.write_bytes(recorded_manifest)
            restore_count += 1
            return result

        with mock.patch(
            "scenario.validate_materialized", side_effect=restore_recorded_manifest
        ):
            status, output, error = self.run_cli(
                "prepare",
                "manifest-race",
                "--guide-src",
                str(guide_source),
                "--output",
                str(output_path),
            )

        self.assertEqual(1, restore_count)
        self.assertNotEqual(0, status)
        self.assertEqual("", output)
        self.assertIn(
            "scenario manifest changed between discovery and the recorded Git revision",
            error,
        )
        self.assertFalse(output_path.exists())

    def test_prepare_rejects_links_special_files_and_unreadable_files(self) -> None:
        scenario_root = self.create_scenario("unsafe-guide", 11)

        with self.subTest(kind="symbolic link"):
            guide_source = self.create_guide_source()
            linked = guide_source / "skills" / "traigent-first-run" / "linked.py"
            linked.symlink_to(guide_source / "GUIDE.md")
            subprocess.run(
                [
                    "git",
                    "-C",
                    os.fspath(guide_source),
                    "add",
                    "skills/traigent-first-run/linked.py",
                ],
                check=True,
            )
            subprocess.run(
                [
                    "git",
                    "-C",
                    os.fspath(guide_source),
                    "-c",
                    "user.name=Scenario Tests",
                    "-c",
                    "user.email=scenario-tests@example.invalid",
                    "commit",
                    "-qm",
                    "Track unsafe link",
                ],
                check=True,
            )
            output_path = Path(self.temporary_directory.name) / "linked-output"
            status, _, error = self.run_cli(
                "prepare",
                "unsafe-guide",
                "--guide-src",
                str(guide_source),
                "--output",
                str(output_path),
            )
            self.assertNotEqual(0, status)
            self.assertIn("contains a tracked symbolic link", error)
            self.assertFalse(output_path.exists())

        with self.subTest(kind="special file"):
            guide_source = self.create_guide_source()
            fifo = scenario_root / "project" / "pipe"
            os.mkfifo(fifo)
            output_path = Path(self.temporary_directory.name) / "fifo-output"
            status, _, error = self.run_cli(
                "prepare",
                "unsafe-guide",
                "--guide-src",
                str(guide_source),
                "--output",
                str(output_path),
            )
            self.assertNotEqual(0, status)
            self.assertIn("scenario 'unsafe-guide' contains a non-regular file", error)
            self.assertFalse(output_path.exists())
            fifo.unlink()

        with self.subTest(kind="unreadable file"):
            guide_source = self.create_guide_source()
            blocked = guide_source / "skills" / "traigent-first-run" / "SKILL.md"
            original_hash = scenario._hash_regular_file

            def reject_blocked(path: Path, label: str) -> tuple[str, int]:
                if path == blocked:
                    raise scenario.PrepareError(f"cannot read {label} {path}")
                return original_hash(path, label)

            output_path = Path(self.temporary_directory.name) / "blocked-output"
            with mock.patch("scenario._hash_regular_file", side_effect=reject_blocked):
                status, _, error = self.run_cli(
                    "prepare",
                    "unsafe-guide",
                    "--guide-src",
                    str(guide_source),
                    "--output",
                    str(output_path),
                )
            self.assertNotEqual(0, status)
            self.assertIn("cannot read tracked guide file", error)
            self.assertFalse(output_path.exists())

    def test_prepare_never_overwrites_and_cleans_only_its_new_output(self) -> None:
        self.create_scenario("safe-output", 12)
        guide_source = self.create_guide_source()
        existing = Path(self.temporary_directory.name) / "existing-output"
        existing.mkdir()
        marker = existing / "keep.txt"
        marker.write_text("keep\n", encoding="utf-8")

        status, _, error = self.run_cli(
            "prepare",
            "safe-output",
            "--guide-src",
            str(guide_source),
            "--output",
            str(existing),
        )

        self.assertNotEqual(0, status)
        self.assertIn("refusing to overwrite", error)
        self.assertEqual("keep\n", marker.read_text(encoding="utf-8"))

        newly_created = Path(self.temporary_directory.name) / "failed-output"
        with mock.patch(
            "scenario._copy_prepared_file", side_effect=OSError("copy failed")
        ):
            status, _, error = self.run_cli(
                "prepare",
                "safe-output",
                "--guide-src",
                str(guide_source),
                "--output",
                str(newly_created),
            )
        self.assertNotEqual(0, status)
        self.assertIn("cannot prepare output", error)
        self.assertFalse(newly_created.exists())
        self.assertEqual("keep\n", marker.read_text(encoding="utf-8"))

    def test_prepare_cleans_output_and_preserves_control_flow_exceptions(self) -> None:
        self.create_scenario("interrupted-output", 16)
        guide_source = self.create_guide_source()

        for label, interruption in (
            ("keyboard", KeyboardInterrupt()),
            ("system-exit", SystemExit(7)),
        ):
            with self.subTest(label=label):
                output_path = Path(self.temporary_directory.name) / f"{label}-output"
                with mock.patch(
                    "scenario._copy_prepared_file", side_effect=interruption
                ):
                    with self.assertRaises(type(interruption)) as raised:
                        self.run_cli(
                            "prepare",
                            "interrupted-output",
                            "--guide-src",
                            str(guide_source),
                            "--output",
                            str(output_path),
                        )
                if isinstance(interruption, SystemExit):
                    self.assertEqual(7, raised.exception.code)
                self.assertFalse(output_path.exists())

    def test_prepare_rejects_output_inside_a_source_tree(self) -> None:
        root = self.create_scenario("nested-output", 13)
        guide_source = self.create_guide_source()

        for output_path, expected in (
            (root / "run", "scenario source"),
            (guide_source / "run", "guide source"),
        ):
            with self.subTest(output_path=output_path):
                status, _, error = self.run_cli(
                    "prepare",
                    "nested-output",
                    "--guide-src",
                    str(guide_source),
                    "--output",
                    str(output_path),
                )
                self.assertNotEqual(0, status)
                self.assertIn(f"output must not be inside {expected}", error)
                self.assertFalse(output_path.exists())

    def test_prepare_rejects_a_dirty_verifier_contract(self) -> None:
        root = self.create_scenario("dirty-contract", 14)
        guide_source = self.create_guide_source()
        output_path = Path(self.temporary_directory.name) / "dirty-contract-run"
        changed = {**expected_opening(), "band": "PARTIAL"}
        (root / "verifier" / "expected-opening.json").write_text(
            json.dumps(changed) + "\n",
            encoding="utf-8",
        )
        (root / "verifier" / "intended-opening.json").write_text(
            json.dumps(intended_opening(changed)) + "\n",
            encoding="utf-8",
        )

        status, output, error = self.run_cli(
            "prepare",
            "dirty-contract",
            "--guide-src",
            str(guide_source),
            "--output",
            str(output_path),
        )

        self.assertNotEqual(0, status)
        self.assertEqual("", output)
        self.assertIn("tracked selected scenario content has local changes", error)
        self.assertFalse(output_path.exists())

    def test_verify_uses_the_contract_recorded_at_prepare_time(self) -> None:
        root = self.create_scenario("recorded-contract", 15)
        run_record = self.prepare_run_record(
            "recorded-contract",
            name="recorded-contract-run",
        )
        changed = {**expected_opening(), "band": "GOOD"}
        (root / "verifier" / "expected-opening.json").write_text(
            json.dumps(changed) + "\n",
            encoding="utf-8",
        )
        original_result = self.write_result(readiness_result(expected_opening()))

        status, output, error = self.run_cli(
            "verify",
            "recorded-contract",
            "--run-record",
            str(run_record),
            "--result",
            str(original_result),
        )

        self.assertEqual(0, status, error)
        self.assertIn("PASS: recorded-contract", output)

    def test_verify_rejects_a_run_record_inventory_not_matching_git(self) -> None:
        self.create_scenario("tampered-record", 16)
        run_record = self.prepare_run_record(
            "tampered-record",
            name="tampered-record-run",
        )
        value = json.loads(run_record.read_text(encoding="utf-8"))
        contract = value["inputs"]["scenario_contract"]
        contract["files"][0]["sha256"] = "0" * 64
        canonical = json.dumps(
            contract["files"],
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        contract["sha256"] = hashlib.sha256(canonical).hexdigest()
        run_record.write_text(json.dumps(value) + "\n", encoding="utf-8")
        result_path = self.write_result(readiness_result(expected_opening()))

        status, output, error = self.run_cli(
            "verify",
            "tampered-record",
            "--run-record",
            str(run_record),
            "--result",
            str(result_path),
        )

        self.assertNotEqual(0, status)
        self.assertEqual("", output)
        self.assertIn("does not match the recorded Git revision", error)

    def test_verify_accepts_matching_strict_opening_json(self) -> None:
        self.create_scenario("verified-case", 20)
        run_record = self.prepare_run_record(
            "verified-case",
            name="verified-case-run",
        )
        result_path = self.write_result(readiness_result(expected_opening()))

        status, output, error = self.run_cli(
            "verify",
            "verified-case",
            "--run-record",
            str(run_record),
            "--result",
            str(result_path),
        )

        self.assertEqual(0, status, error)
        self.assertEqual("", error)
        self.assertEqual(
            "PASS: verified-case opening result matches "
            "band, status, recommended_action, caps (condition, ceiling, blocks, "
            "asks) at readiness schema_version 6 in the captain-recorded contract\n"
            "intended opening: AGREES - the result matches the hand-written "
            "intended opening, which equals the measured contract\n",
            output,
        )

    def write_contract(
        self, root: Path, contract: dict[str, object], *, message: str
    ) -> None:
        """Commit a contract with the intended opening that agrees with it."""
        for name, value in (
            ("expected-opening.json", contract),
            ("intended-opening.json", intended_opening(contract)),
        ):
            (root / "verifier" / name).write_text(
                json.dumps(value) + "\n", encoding="utf-8"
            )
        self.commit_repository_paths(
            root / "verifier" / "expected-opening.json",
            root / "verifier" / "intended-opening.json",
            message=message,
        )

    def test_verify_compares_whole_caps_from_readiness_objects(self) -> None:
        """A cap is its condition and how readiness routes it, and both compare.

        Schema 1 contracts recorded the condition alone, so a result whose cap
        stopped the run matched a contract whose cap only bounded the claim.
        """
        root = self.create_scenario("capped-case", 25)
        expected = {
            **expected_opening(),
            "band": "WORKABLE",
            "caps": [
                {
                    "condition": "evaluator-unvalidated",
                    "ceiling": 45,
                    "blocks": False,
                    "asks": False,
                },
                {
                    "condition": "dataset-fully-synthetic",
                    "ceiling": 65,
                    "blocks": False,
                    "asks": False,
                },
            ],
        }
        self.write_contract(root, expected, message="Add capped opening contract")
        run_record = self.prepare_run_record(
            "capped-case",
            name="capped-case-run",
        )
        result = readiness_result(expected)
        assert isinstance(result["caps"], list)
        result["caps"].reverse()

        def verify(value: dict[str, object]) -> tuple[int, str, str]:
            return self.run_cli(
                "verify",
                "capped-case",
                "--run-record",
                str(run_record),
                "--result",
                str(self.write_result(value)),
            )

        status, output, error = verify(result)
        self.assertEqual(0, status, error)
        self.assertIn("PASS: capped-case", output)
        self.assertIn("caps (condition, ceiling, blocks, asks)", output)

        for field, value in (("blocks", True), ("asks", True), ("ceiling", None)):
            with self.subTest(field=field):
                changed = json.loads(json.dumps(result))
                changed["caps"][0][field] = value
                status, output, error = verify(changed)
                self.assertEqual(1, status, error)
                self.assertEqual("", output)
                self.assertIn("- caps: expected [dataset-fully-synthetic", error)

        conditions_only = {
            **result,
            "caps": ["dataset-fully-synthetic", "evaluator-unvalidated"],
        }
        status, output, error = verify(conditions_only)
        self.assertEqual(1, status)
        self.assertIn("caps[0]: must be an object", error)

        for schema in (5, None):
            with self.subTest(schema=schema):
                status, output, error = verify({**result, "schema_version": schema})
                self.assertEqual(1, status)
                self.assertIn(
                    "schema_version: the contract was measured at readiness "
                    f"schema_version 6, got {schema!r}",
                    error,
                )

    def test_verify_rejects_a_cap_object_without_a_condition(self) -> None:
        self.create_scenario("malformed-cap", 26)
        run_record = self.prepare_run_record(
            "malformed-cap",
            name="malformed-cap-run",
        )
        result_path = self.write_result(
            {**expected_opening(), "caps": [{"ceiling": 65}]}
        )

        status, output, error = self.run_cli(
            "verify",
            "malformed-cap",
            "--run-record",
            str(run_record),
            "--result",
            str(result_path),
        )

        self.assertNotEqual(0, status)
        self.assertEqual("", output)
        self.assertIn("caps[0].condition: must be a non-empty string", error)

    def test_verify_reports_every_semantic_mismatch(self) -> None:
        self.create_scenario("mismatched-case", 21)
        run_record = self.prepare_run_record(
            "21",
            name="mismatched-case-run",
        )
        result_path = self.write_result({"band": "GOOD"})

        status, output, error = self.run_cli(
            "verify",
            "21",
            "--run-record",
            str(run_record),
            "--result",
            str(result_path),
        )

        self.assertNotEqual(0, status)
        self.assertEqual("", output)
        self.assertIn("FAIL: mismatched-case", error)
        self.assertIn("band: expected 'EXCELLENT', got 'GOOD'", error)
        self.assertIn("status: expected 'OK', got <missing>", error)
        self.assertIn("recommended_action: expected 'proceed', got <missing>", error)
        self.assertIn("caps: expected [], got <missing>", error)
        self.assertIn(
            "schema_version: the contract was measured at readiness "
            "schema_version 6, got <missing>",
            error,
        )
        self.assertEqual(5, error.count("\n- "))

    def test_verify_rejects_duplicate_keys_nan_and_non_object_roots(self) -> None:
        self.create_scenario("strict-json", 22)
        run_record = self.prepare_run_record(
            "strict-json",
            name="strict-json-run",
        )
        result_path = Path(self.temporary_directory.name) / "strict-result.json"

        for payload, expected in (
            ('{"band": "EXCELLENT", "band": "GOOD"}', "duplicate object key"),
            ('{"band": NaN}', "non-standard JSON numeric value"),
            ('["EXCELLENT"]', "root must be a JSON object"),
        ):
            with self.subTest(payload=payload):
                result_path.write_text(payload, encoding="utf-8")
                status, output, error = self.run_cli(
                    "verify",
                    "strict-json",
                    "--run-record",
                    str(run_record),
                    "--result",
                    str(result_path),
                )
                self.assertNotEqual(0, status)
                self.assertEqual("", output)
                self.assertIn(expected, error)

    def test_verify_rejects_result_symlink(self) -> None:
        self.create_scenario("linked-result", 23)
        run_record = self.prepare_run_record(
            "linked-result",
            name="linked-result-run",
        )
        target = self.write_result(
            readiness_result(expected_opening()), name="target-result.json"
        )
        linked = Path(self.temporary_directory.name) / "linked-result.json"
        linked.symlink_to(target)

        status, output, error = self.run_cli(
            "verify",
            "linked-result",
            "--run-record",
            str(run_record),
            "--result",
            str(linked),
        )

        self.assertNotEqual(0, status)
        self.assertEqual("", output)
        self.assertIn("opening result must not be a symbolic link", error)

    def test_prepare_and_verify_treat_python_payloads_as_inert_bytes(self) -> None:
        root = self.create_scenario("inert-code", 24)
        guide_source = self.create_guide_source()
        sentinel = Path(self.temporary_directory.name) / "must-not-exist"
        payload = (
            "from pathlib import Path\n"
            f"Path({str(sentinel)!r}).write_text('executed', encoding='utf-8')\n"
        )
        candidate_payload = root / "project" / "candidate.py"
        verifier_payload = root / "verifier" / "verifier.py"
        candidate_payload.write_text(payload, encoding="utf-8")
        verifier_payload.write_text(payload, encoding="utf-8")
        manifest = valid_manifest("inert-code", 24)
        catalog = manifest["catalog"]
        assert isinstance(catalog, dict)
        catalog["non_dataset_files"] = ["project/candidate.py"]
        self.write_manifest(root, manifest)
        self.commit_repository_paths(
            root / "scenario.json",
            candidate_payload,
            verifier_payload,
            message="Track inert scenario payloads",
        )
        guide_payload = (
            guide_source / "skills" / "traigent-first-run" / "scripts" / "payload.py"
        )
        guide_payload.write_text(payload, encoding="utf-8")
        subprocess.run(
            [
                "git",
                "-C",
                os.fspath(guide_source),
                "add",
                "skills/traigent-first-run/scripts/payload.py",
            ],
            check=True,
        )
        subprocess.run(
            [
                "git",
                "-C",
                os.fspath(guide_source),
                "-c",
                "user.name=Scenario Tests",
                "-c",
                "user.email=scenario-tests@example.invalid",
                "commit",
                "-qm",
                "Track inert payload",
            ],
            check=True,
        )
        output_path = Path(self.temporary_directory.name) / "inert-output"

        prepare_status, _, prepare_error = self.run_cli(
            "prepare",
            "inert-code",
            "--guide-src",
            str(guide_source),
            "--output",
            str(output_path),
        )
        result_path = self.write_result(readiness_result(expected_opening()))
        verify_status, _, verify_error = self.run_cli(
            "verify",
            "inert-code",
            "--run-record",
            str(output_path / "run.json"),
            "--result",
            str(result_path),
        )

        self.assertEqual(0, prepare_status, prepare_error)
        self.assertEqual(0, verify_status, verify_error)
        self.assertFalse(sentinel.exists())

    def copy_read_dependent_scenario(self) -> Path:
        """The published case 58, committed into this test's repository."""
        source = scenario.REPOSITORY_ROOT / "scenarios" / "regex-rule-authoring"
        root = self.scenarios_dir / source.name
        shutil.copytree(source, root, ignore=shutil.ignore_patterns("__pycache__"))
        self.commit_repository_paths(root, message="Copy regex-rule-authoring")
        return root

    def write_read(self, verdicts: dict[str, str], *, name: str) -> Path:
        return self.write_result(
            {
                "reviewer": "assistant",
                "rows": [
                    {
                        "id": row_id,
                        "origin": "collected",
                        "verdict": verdict,
                        "note": "read",
                    }
                    for row_id, verdict in verdicts.items()
                ],
            },
            name=name,
        )

    def test_verify_compares_with_the_contract_for_the_read_the_worker_gave(
        self,
    ) -> None:
        root = self.copy_read_dependent_scenario()
        run_record = self.prepare_run_record("58", name="read-dependent-run")
        published = json.loads((root / "verifier/expected-opening.json").read_text())
        sound = json.loads(
            (root / "verifier/expected-opening-sound-read.json").read_text()
        )
        finds_one = self.write_read(
            {
                "line-3": "yes",
                "line-13": "no",
                "line-14": "unsure",
                "line-26": "yes",
                "line-29": "yes",
            },
            name="finds-one.json",
        )
        finds_none = self.write_read(
            {
                "line-4": "yes",
                "line-9": "yes",
                "line-14": "no",
                "line-17": "yes",
                "line-30": "yes",
            },
            name="finds-none.json",
        )
        finds_none_and_unsure = self.write_read(
            {
                "line-4": "yes",
                "line-9": "yes",
                "line-14": "unsure",
                "line-17": "yes",
                "line-30": "yes",
            },
            name="finds-none-unsure.json",
        )
        cases = (
            (finds_one, published, 0, "marks an answer unsound"),
            (finds_none_and_unsure, sound, 0, "finds every answer sound"),
            # A contestable row marked `no` is a finding the guide acts on.
            (finds_none, published, 0, "marks an answer unsound"),
            (finds_none_and_unsure, published, 1, "band: expected 'STRONG'"),
        )
        for read, contract, want, message in cases:
            with self.subTest(read=read.name, band=contract["band"]):
                status, output, error = self.run_cli(
                    "verify",
                    "58",
                    "--run-record",
                    str(run_record),
                    "--result",
                    str(self.write_result(readiness_result(contract))),
                    "--row-review",
                    str(read),
                )
                self.assertEqual(want, status, error)
                self.assertIn(message, output + error)

    def test_verify_fails_a_read_the_row_verdicts_disagree_with(self) -> None:
        root = self.copy_read_dependent_scenario()
        run_record = self.prepare_run_record("58", name="graded-read-run")
        published = self.write_result(
            readiness_result(
                json.loads((root / "verifier/expected-opening.json").read_text())
            )
        )
        sound = self.write_result(
            readiness_result(
                json.loads(
                    (root / "verifier/expected-opening-sound-read.json").read_text()
                )
            ),
            name="sound.json",
        )
        reads = (
            (
                {
                    "line-13": "yes",
                    "line-3": "yes",
                    "line-4": "yes",
                    "line-9": "yes",
                    "line-17": "yes",
                },
                sound,
                "line-13: its answer does not answer",
            ),
            (
                {
                    "line-13": "unsure",
                    "line-3": "yes",
                    "line-4": "yes",
                    "line-9": "yes",
                    "line-17": "yes",
                },
                sound,
                "line-13: its answer does not answer",
            ),
            (
                {
                    "line-4": "no",
                    "line-3": "yes",
                    "line-9": "yes",
                    "line-17": "yes",
                    "line-30": "yes",
                },
                published,
                "line-4: its answer is sound",
            ),
            (
                {"line-4": "yes", "line-9": "yes", "line-17": "yes", "line-30": "yes"},
                sound,
                "measured for the 5-row opening read, and this read has 4",
            ),
            (
                {
                    "line-4": "yes",
                    "line-9": "yes",
                    "line-17": "yes",
                    "line-30": "yes",
                    "line-99": "yes",
                },
                sound,
                "line-99: not a row",
            ),
        )
        for index, (verdicts, result, reason) in enumerate(reads):
            with self.subTest(reason=reason):
                status, output, error = self.run_cli(
                    "verify",
                    "58",
                    "--run-record",
                    str(run_record),
                    "--result",
                    str(result),
                    "--row-review",
                    str(self.write_read(verdicts, name=f"r{index}.json")),
                )
                self.assertEqual(1, status)
                self.assertEqual("", output)
                self.assertIn(reason, error)

    def test_verify_reads_the_opening_read_the_way_readiness_does(self) -> None:
        root = self.copy_read_dependent_scenario()
        run_record = self.prepare_run_record("58", name="read-shape-run")
        sound = self.write_result(
            readiness_result(
                json.loads(
                    (root / "verifier/expected-opening-sound-read.json").read_text()
                )
            )
        )
        verdicts = {
            " line-4 ": "yes",
            "line-9": "yes",
            "line-15": "yes",
            "line-17": "yes",
            "line-30": "yes",
        }
        padded = self.write_read(verdicts, name="padded.json")
        status, output, error = self.run_cli(
            "verify",
            "58",
            "--run-record",
            str(run_record),
            "--result",
            str(sound),
            "--row-review",
            str(padded),
        )
        self.assertEqual(0, status, error)
        self.assertIn("finds every answer sound", output)

        declared = json.loads(padded.read_text())
        for row in declared["rows"]:
            row["in_run"] = True
        membership = self.write_result(declared, name="membership.json")
        status, output, error = self.run_cli(
            "verify",
            "58",
            "--run-record",
            str(run_record),
            "--result",
            str(sound),
            "--row-review",
            str(membership),
        )
        self.assertEqual(1, status)
        self.assertIn("declares in_run", error)

    def test_verify_grades_the_read_against_the_recorded_verdicts(self) -> None:
        root = self.copy_read_dependent_scenario()
        run_record = self.prepare_run_record("58", name="recorded-verdicts-run")
        published = self.write_result(
            readiness_result(
                json.loads((root / "verifier/expected-opening.json").read_text())
            )
        )
        key = root / "verifier" / "row-verdicts.json"
        text = key.read_text(encoding="utf-8")
        self.assertEqual(3, text.count('"class": "unsound"'))
        key.write_text(text.replace('"class": "unsound"', '"class": "sound"'))
        self.commit_repository_paths(key, message="Change the verdicts later")
        read = self.write_read(
            {
                "line-3": "yes",
                "line-13": "no",
                "line-14": "unsure",
                "line-26": "yes",
                "line-29": "yes",
            },
            name="published-read.json",
        )
        status, output, error = self.run_cli(
            "verify",
            "58",
            "--run-record",
            str(run_record),
            "--result",
            str(published),
            "--row-review",
            str(read),
        )
        self.assertEqual(0, status, error)
        self.assertIn("marks an answer unsound", output)

    def test_verify_requires_the_read_exactly_where_the_contract_depends_on_it(
        self,
    ) -> None:
        root = self.copy_read_dependent_scenario()
        self.create_scenario("one-contract", 20)
        dependent_record = self.prepare_run_record("58", name="dependent-run")
        plain_record = self.prepare_run_record("one-contract", name="plain-run")
        read = self.write_read(
            {
                "line-4": "yes",
                "line-9": "yes",
                "line-15": "yes",
                "line-17": "yes",
                "line-30": "yes",
            },
            name="read.json",
        )
        published = self.write_result(
            readiness_result(
                json.loads((root / "verifier/expected-opening.json").read_text())
            )
        )
        for arguments, reason in (
            (
                (
                    "58",
                    "--run-record",
                    str(dependent_record),
                    "--result",
                    str(published),
                ),
                "pass the read the worker gave readiness as --row-review",
            ),
            (
                (
                    "one-contract",
                    "--run-record",
                    str(plain_record),
                    "--result",
                    str(
                        self.write_result(
                            readiness_result(expected_opening()), name="p.json"
                        )
                    ),
                    "--row-review",
                    str(read),
                ),
                "--row-review is not read for it",
            ),
        ):
            with self.subTest(case=arguments[0]):
                status, output, error = self.run_cli("verify", *arguments)
                self.assertEqual(1, status)
                self.assertEqual("", output)
                self.assertIn(reason, error)

    def test_check_refuses_row_verdicts_that_do_not_hold_the_reads_or_the_rows(
        self,
    ) -> None:
        edits = (
            (
                "verifier/row-verdicts.json",
                '"line-32": {',
                '"line-99": {',
                "must give a verdict for every row",
            ),
            (
                "verifier/row-verdicts.json",
                '"class": "unsound"',
                '"class": "sound"',
                "its answer is sound, and the read says 'no'",
            ),
            (
                "verifier/measurement/row-review-sound-read.json",
                '"id": "line-4",\n      "origin": "collected",\n      "verdict": "yes"',
                '"id": "line-14",\n      "origin": "collected",\n      "verdict": "no"',
                "must mark no answer 'no'",
            ),
            (
                "verifier/row-verdicts.json",
                '"class": "contestable"',
                '"class": "maybe"',
                "must be one of sound, unsound, contestable",
            ),
        )
        root = self.copy_read_dependent_scenario()
        status, output, error = self.run_cli("check", "58")
        self.assertEqual(0, status, error)
        self.assertIn("OK: regex-rule-authoring", output)
        for index, (relative, old, new, reason) in enumerate(edits):
            with self.subTest(reason=reason):
                target = root / relative
                original = target.read_text(encoding="utf-8")
                self.assertGreaterEqual(
                    original.count(old), 1, "the edit did not apply"
                )
                target.write_text(original.replace(old, new, 1), encoding="utf-8")
                self.commit_repository_paths(target, message=f"Break {index}")
                status, _, error = self.run_cli("check", "58")
                target.write_text(original, encoding="utf-8")
                self.commit_repository_paths(target, message=f"Restore {index}")
                self.assertEqual(1, status, error)
                self.assertIn(reason, error)

    # --- Hand-written answers: agent read, intended opening, project, ask ---

    def copy_bank_scenario(self, slug: str) -> Path:
        """A published scenario, committed into this test's repository."""
        source = scenario.REPOSITORY_ROOT / "scenarios" / slug
        root = self.scenarios_dir / source.name
        shutil.copytree(source, root, ignore=shutil.ignore_patterns("__pycache__"))
        self.commit_repository_paths(root, message=f"Copy {slug}")
        return root

    def write_agent_read(self, names: list[str], *, name: str) -> Path:
        return self.write_result(
            {
                "source": "agent.py",
                "knobs": {knob: {"evidence": "read"} for knob in names},
            },
            name=name,
        )

    def verify_plain(
        self, slug: str, run_record: Path, *extra: str
    ) -> tuple[int, str, str]:
        contract = json.loads(
            (
                self.scenarios_dir / slug / "verifier" / "expected-opening.json"
            ).read_text()
        )
        return self.run_cli(
            "verify",
            slug,
            "--run-record",
            str(run_record),
            "--result",
            str(
                self.write_result(
                    readiness_result(contract), name=f"{slug}-result.json"
                )
            ),
            *extra,
        )

    def test_verify_grades_the_agent_read_against_the_declared_controls(self) -> None:
        self.create_scenario("agent-graded", 31)
        run_record = self.prepare_run_record("agent-graded", name="agent-graded-run")
        for names, want, reasons in (
            (["model"], 0, ["its agent read names exactly the 1 setting"]),
            (
                ["model", "temperature"],
                1,
                [
                    "agent read: names setting(s) the scenario does not declare: temperature"
                ],
            ),
            ([], 1, ["agent read: omits setting(s) the scenario declares: model"]),
            (
                ["temperature"],
                1,
                [
                    "does not declare: temperature",
                    "omits setting(s) the scenario declares: model",
                ],
            ),
        ):
            with self.subTest(names=names):
                status, output, error = self.verify_plain(
                    "agent-graded",
                    run_record,
                    "--agent-read",
                    str(self.write_agent_read(names, name="read.json")),
                )
                self.assertEqual(want, status, output + error)
                for reason in reasons:
                    self.assertIn(reason, output + error)
                if want:
                    self.assertIn(
                        "matches band, status, recommended_action, caps "
                        "(condition, ceiling, blocks, asks) at readiness "
                        "schema_version 6 in the captain-recorded contract, and an "
                        "additional grade failed",
                        error,
                    )

    def test_verify_grades_a_read_of_an_agent_with_no_settings(self) -> None:
        """Case 52 declares no control, so the only passing read names none."""
        self.copy_bank_scenario("tool-dispatch-selector")
        run_record = self.prepare_run_record("52", name="no-knobs-run")
        status, output, error = self.verify_plain(
            "tool-dispatch-selector",
            run_record,
            "--agent-read",
            str(self.write_agent_read([], name="empty.json")),
        )
        self.assertEqual(0, status, error)
        self.assertIn(
            "its agent read names no setting, as the scenario declares none", output
        )
        status, output, error = self.verify_plain(
            "tool-dispatch-selector",
            run_record,
            "--agent-read",
            str(self.write_agent_read(["model"], name="model.json")),
        )
        self.assertEqual(1, status)
        self.assertIn("names setting(s) the scenario does not declare: model", error)

    def test_verify_fails_an_agent_read_where_no_agent_exists(self) -> None:
        """The guide gives readiness no agent read where it found no agent."""
        self.copy_bank_scenario("chatbot-on-vendor-flow")
        run_record = self.prepare_run_record("57", name="no-agent-run")
        status, output, error = self.verify_plain(
            "chatbot-on-vendor-flow",
            run_record,
            "--agent-read",
            str(self.write_agent_read([], name="none.json")),
        )
        self.assertEqual(1, status)
        self.assertEqual("", output)
        self.assertIn(
            "- agent read: the scenario has no agent, and the guide gives readiness "
            "no agent read where the inventory found none",
            error,
        )
        self.assertIn("and an additional grade failed", error)

    def test_check_holds_the_committed_agent_read_to_the_declared_controls(
        self,
    ) -> None:
        root = self.create_scenario("agent-read-check", 32)
        measurement = root / "verifier" / "measurement"
        measurement.mkdir()
        read = measurement / "agent-read.json"
        for names, error_text in (
            (["model"], None),
            (["model", "temperature"], "does not declare: temperature"),
            ([], "omits setting(s) the scenario declares: model"),
        ):
            with self.subTest(names=names):
                read.write_text(
                    json.dumps({"knobs": {name: {} for name in names}}),
                    encoding="utf-8",
                )
                status, _, error = self.run_cli("check", "agent-read-check")
                if error_text is None:
                    self.assertEqual(0, status, error)
                else:
                    self.assertEqual(1, status)
                    self.assertIn(error_text, error)
                    self.assertIn("catalog.components.agent.controls", error)

    def test_every_committed_agent_read_names_the_declared_controls(self) -> None:
        """The measured read and the hand-declared controls are one list.

        `check` holds a committed read to the controls; this holds that every
        scenario with an agent commits one, so the grade has a measured read
        behind it everywhere a worker's read can be graded.
        """
        with_agent = 0
        for manifest_path in sorted(
            (scenario.REPOSITORY_ROOT / "scenarios").glob("*/scenario.json")
        ):
            agent = json.loads(manifest_path.read_text())["catalog"]["components"][
                "agent"
            ]
            read_path = (
                manifest_path.parent / "verifier" / "measurement" / "agent-read.json"
            )
            with self.subTest(scenario=manifest_path.parent.name):
                self.assertEqual(agent["state"] != "missing", read_path.is_file())
                if read_path.is_file():
                    with_agent += 1
                    self.assertEqual(
                        set(agent["controls"]),
                        set(json.loads(read_path.read_text())["knobs"]),
                    )
        self.assertEqual(12, with_agent)

    def test_check_holds_the_intended_opening_to_the_measured_contract(self) -> None:
        root = self.create_scenario("intended-check", 33)
        intended_path = root / "verifier" / "intended-opening.json"
        contract = expected_opening()
        departing = {
            **intended_opening(contract),
            "recommended_action": "repair-evaluator",
        }
        declared = {
            "issue": None,
            "reason": "the guide routes this finding nowhere",
            "fields": {
                "recommended_action": {
                    "intended": "repair-evaluator",
                    "measured": "proceed",
                }
            },
        }
        cases = (
            (intended_opening(contract), None),
            (
                departing,
                "differs from expected-opening.json on recommended_action and declares no divergence",
            ),
            ({**departing, "divergence": declared}, None),
            (
                {**intended_opening(contract), "divergence": declared},
                "declares a divergence that no longer holds",
            ),
            (
                {
                    **departing,
                    "divergence": {**declared, "issue": "https://example.invalid/1"},
                },
                "divergence.issue: must be null or a traigent-first-run issue URL",
            ),
            (
                {
                    **departing,
                    "divergence": {
                        **declared,
                        "issue": "https://github.com/Traigent/traigent-first-run/issues/7",
                    },
                },
                None,
            ),
            (
                {**intended_opening(contract), "caps": ["dataset-coarse-resolution"]},
                "caps[0]: must be an object",
            ),
            ({**intended_opening(contract), "band": "GOOD"}, "band: must be one of"),
            (
                {**intended_opening(contract), "schema_version": 1.0},
                "schema_version: must equal 1",
            ),
            (
                {**departing, "divergence": {**declared, "fields": {}}},
                "divergence.fields: must name at least one field",
            ),
            (
                {
                    **departing,
                    "band": "STRONG",
                    "divergence": declared,
                },
                "declares a divergence on recommended_action, and "
                "expected-opening.json now differs on band, recommended_action",
            ),
            (
                {
                    **departing,
                    "divergence": {
                        **declared,
                        "fields": {
                            "recommended_action": {
                                "intended": "repair-evaluator",
                                "measured": "resplit-dataset",
                            }
                        },
                    },
                },
                "divergence.fields.recommended_action.measured: records "
                "'resplit-dataset', and the measured opening has 'proceed'",
            ),
        )
        for value, reason in cases:
            with self.subTest(reason=reason, value=value.get("divergence")):
                intended_path.write_text(json.dumps(value), encoding="utf-8")
                status, _, error = self.run_cli("check", "intended-check")
                if reason is None:
                    self.assertEqual(0, status, error)
                else:
                    self.assertEqual(1, status)
                    self.assertIn(reason, error)
        intended_path.unlink()
        status, _, error = self.run_cli("check", "intended-check")
        self.assertEqual(1, status)
        self.assertIn("intended opening", error)

    def test_a_declared_divergence_covers_only_the_fields_it_names(self) -> None:
        """Re-measuring case 49 onto anything but its declared gap fails check."""
        root = self.copy_bank_scenario("warehouse-text-to-sql")
        contract_path = root / "verifier" / "expected-opening.json"
        original = contract_path.read_text(encoding="utf-8")
        status, _, error = self.run_cli("check", "49")
        self.assertEqual(0, status, error)
        for label, change, reason in (
            (
                "blocked",
                {"band": "PARTIAL", "status": "BLOCKED"},
                "now differs on band, caps, recommended_action, status",
            ),
            (
                "another action",
                {"recommended_action": "review-answer-key"},
                "divergence.fields.recommended_action.measured: records 'proceed'",
            ),
            (
                "the guide adopts the finding",
                {
                    "recommended_action": "repair-evaluator",
                    "caps": [
                        {
                            "condition": "evaluator-task-mismatch",
                            "ceiling": None,
                            "blocks": False,
                            "asks": True,
                        }
                    ],
                },
                "declares a divergence that no longer holds",
            ),
        ):
            with self.subTest(label=label):
                contract_path.write_text(
                    json.dumps({**json.loads(original), **change}), encoding="utf-8"
                )
                status, _, error = self.run_cli("check", "49")
                contract_path.write_text(original, encoding="utf-8")
                self.assertEqual(1, status, error)
                self.assertIn(reason, error)

    def test_check_requires_an_intended_opening_for_each_contract(self) -> None:
        root = self.copy_read_dependent_scenario()
        status, _, error = self.run_cli("check", "58")
        self.assertEqual(0, status, error)
        (root / "verifier" / "intended-opening-sound-read.json").unlink()
        status, _, error = self.run_cli("check", "58")
        self.assertEqual(1, status)
        self.assertIn("intended-opening-sound-read.json", error)

    def test_check_refuses_an_intended_opening_that_answers_no_contract(
        self,
    ) -> None:
        root = self.copy_bank_scenario("warehouse-text-to-sql")
        intended = root / "verifier" / "intended-opening.json"
        for relative in (
            "intended-opening-sound-read.json",
            "notes/intended-opening.json",
        ):
            with self.subTest(relative=relative):
                orphan = root / "verifier" / relative
                orphan.parent.mkdir(parents=True, exist_ok=True)
                orphan.write_bytes(intended.read_bytes())
                status, _, error = self.run_cli("check", "49")
                orphan.unlink()
                self.assertEqual(1, status, error)
                self.assertIn(f"verifier/{relative}", error)
                self.assertIn("answers no contract", error)

    def test_check_refuses_a_project_naming_the_intended_opening_or_its_caps(
        self,
    ) -> None:
        """An intended opening is captain-side, so its name and a cap only it
        names tell a worker what is being measured, as the contract's do."""
        root = self.copy_bank_scenario("warehouse-text-to-sql")
        agent = root / "project" / "agent.py"
        original = agent.read_text(encoding="utf-8")
        for tell, line in (
            ("intended-opening", "# see intended_opening.json\n"),
            ("evaluator-task-mismatch", "# EVALUATOR_TASK_MISMATCH\n"),
        ):
            with self.subTest(tell=tell):
                agent.write_text(original + line, encoding="utf-8")
                status, output, error = self.run_cli("check", "49")
                agent.write_text(original, encoding="utf-8")
                self.assertEqual(1, status, output)
                self.assertIn("ships project/agent.py, which names", error)
                self.assertIn(tell, error)

    def test_every_contract_has_its_own_hand_written_intended_opening(self) -> None:
        """One intended opening per measured contract, and the bank's divergence.

        Warehouse text-to-SQL is the one scenario whose intent departs from its
        measurement: the guide documents a text-comparing SQL scorer as a
        finding to repair, and its readiness script has no cap for it.
        """
        departing = []
        for manifest_path in sorted(
            (scenario.REPOSITORY_ROOT / "scenarios").glob("*/scenario.json")
        ):
            verifier = manifest_path.parent / "verifier"
            contracts = sorted(
                path.name for path in verifier.glob("expected-opening*.json")
            )
            intended = sorted(
                path.name for path in verifier.glob("intended-opening*.json")
            )
            self.assertEqual(
                [name.replace("expected-", "intended-") for name in contracts], intended
            )
            for name in intended:
                if json.loads((verifier / name).read_text())["divergence"] is not None:
                    departing.append(f"{manifest_path.parent.name}/{name}")
        self.assertEqual(["warehouse-text-to-sql/intended-opening.json"], departing)

    def test_verify_notes_whether_the_result_agrees_with_the_intended_opening(
        self,
    ) -> None:
        root = self.create_scenario("intended-note", 34)
        contract = expected_opening()
        intended = {
            **intended_opening(contract),
            "recommended_action": "repair-evaluator",
            "divergence": {
                "issue": None,
                "reason": "the guide routes it nowhere",
                "fields": {
                    "recommended_action": {
                        "intended": "repair-evaluator",
                        "measured": "proceed",
                    }
                },
            },
        }
        (root / "verifier" / "intended-opening.json").write_text(
            json.dumps(intended), encoding="utf-8"
        )
        self.commit_repository_paths(
            root / "verifier" / "intended-opening.json", message="Depart"
        )
        run_record = self.prepare_run_record("intended-note", name="intended-note-run")

        status, output, error = self.verify_plain("intended-note", run_record)
        self.assertEqual(0, status, error)
        self.assertIn(
            "intended opening: DIVERGES on recommended_action - the result differs "
            "from the hand-written intended opening, which departs from the "
            "measured contract as declared: the guide routes it nowhere (issue: none)",
            output,
        )
        follows_intent = {
            **readiness_result(contract),
            "recommended_action": "repair-evaluator",
        }
        status, output, error = self.run_cli(
            "verify",
            "intended-note",
            "--run-record",
            str(run_record),
            "--result",
            str(self.write_result(follows_intent)),
        )
        self.assertEqual(1, status, "PASS means the measured contract matched")
        self.assertIn("recommended_action: expected 'proceed'", error)
        self.assertIn("intended opening: AGREES - the result matches", error)

    def test_verify_rehashes_the_worker_project_against_its_inventory(self) -> None:
        self.create_scenario("project-graded", 35)
        run_record = self.prepare_run_record("project-graded", name="project-run")
        project = run_record.parent / "customer-project"

        def verify() -> tuple[int, str, str]:
            return self.verify_plain(
                "project-graded", run_record, "--project-dir", str(project)
            )

        status, output, error = verify()
        self.assertEqual(0, status, error)
        self.assertIn("its project matches the prepared inventory apart from 0", output)

        writes = (
            "traigent-runs/readiness/20260923T101500Z/row-review.json",
            "traigent-runs/readiness/20260923T101500Z/preflight.json",
            "traigent-runs/calibration-results.json",
            "traigent-runs/run-plan.md",
            "traigent-runs/run-log.jsonl",
        )
        for relative in writes:
            (project / relative).parent.mkdir(parents=True, exist_ok=True)
            (project / relative).write_text("{}\n", encoding="utf-8")
        status, output, error = verify()
        self.assertEqual(0, status, error)
        self.assertIn("apart from 5 of the guide's opening writes", output)
        self.assertIn(
            "project: opening writes found: " + ", ".join(sorted(writes)), output
        )

        agent = project / "agent.py"
        original = agent.read_bytes()
        guide_file = project / "traigent-first-run" / "GUIDE.md"
        guide_original = guide_file.read_bytes()
        probes = (
            (
                "modified",
                lambda: agent.write_bytes(original + b"# edited\n"),
                "agent.py: modified",
            ),
            ("deleted", agent.unlink, "agent.py: deleted"),
            ("mode", lambda: agent.chmod(0o755), "agent.py: executable bit changed"),
            (
                "guide edited",
                lambda: guide_file.write_bytes(b"# another guide\n"),
                "traigent-first-run/GUIDE.md: modified",
            ),
            (
                "undocumented write",
                lambda: (project / "traigent-runs" / "row-review.json").write_text(
                    "{}"
                ),
                "traigent-runs/row-review.json: added, and not one of the guide's opening writes",
            ),
            (
                "stamp not a UTC name",
                lambda: (project / "traigent-runs" / "readiness" / "latest").mkdir()
                or (
                    project / "traigent-runs" / "readiness" / "latest" / "x.json"
                ).write_text("{}"),
                "traigent-runs/readiness/latest/x.json: added",
            ),
            (
                "link",
                lambda: (project / "linked.py").symlink_to(agent),
                "linked.py: a symbolic link or special file",
            ),
        )
        for label, damage, reason in probes:
            with self.subTest(label=label):
                damage()
                status, output, error = verify()
                self.assertEqual(1, status, output)
                self.assertIn(f"- project: {reason}", error)
                for extra in ("linked.py", "traigent-runs/row-review.json"):
                    if (project / extra).is_symlink() or (project / extra).is_file():
                        (project / extra).unlink()
                shutil.rmtree(project / "traigent-runs" / "readiness" / "latest", True)
                agent.write_bytes(original)
                agent.chmod(0o644)
                guide_file.write_bytes(guide_original)
        status, output, error = verify()
        self.assertEqual(0, status, error)

    def test_verify_allows_every_documented_opening_write_and_no_other(self) -> None:
        self.copy_bank_scenario("incident-severity-triage")
        run_record = self.prepare_run_record("46", name="writes-run")
        project = run_record.parent / "customer-project"
        cases_file = project / "traigent-runs" / "calibration-cases.json"
        original_cases = cases_file.read_bytes()

        def verify() -> tuple[int, str, str]:
            return self.verify_plain(
                "incident-severity-triage", run_record, "--project-dir", str(project)
            )

        (project / "traigent-runs" / "calibration.log").write_text("ran\n")
        cases_file.write_bytes(original_cases.replace(b"[", b"[ ", 1))
        status, output, error = verify()
        self.assertEqual(0, status, error)
        self.assertIn(
            "project: opening writes found: traigent-runs/calibration-cases.json "
            "(rewritten), traigent-runs/calibration.log",
            output,
        )

        # This test's temporary directory is a Git work tree, so the guide adds
        # its one ignore line to the project root, and nothing else.
        gitignore = project / ".gitignore"
        for content, want, reason in (
            ("/traigent-runs/\n", 0, "opening writes found: .gitignore"),
            (
                "/traigent-runs/\n*.db\n",
                1,
                ".gitignore: holds something other than the guide's /traigent-runs/",
            ),
        ):
            with self.subTest(content=content):
                gitignore.write_text(content, encoding="utf-8")
                status, output, error = verify()
                self.assertEqual(want, status, output + error)
                self.assertIn(reason, output + error)
        gitignore.unlink()

        cases_file.unlink()
        status, output, error = verify()
        self.assertEqual(1, status)
        self.assertIn("- project: traigent-runs/calibration-cases.json: deleted", error)

    def test_verify_reports_the_bytecode_python_writes_for_a_prepared_module(
        self,
    ) -> None:
        """The guide's calibration imports modules without `-B`, so Python
        writes their bytecode. Only a file that reads as the bytecode of a file
        `prepare` copied passes: a CPython cache tag the guide runs on, an
        optimization level Python writes, that Python's header over the
        prepared source's size, and - where verify runs that same Python - a
        body that unmarshals to a code object."""
        self.copy_bank_scenario("incident-severity-triage")
        run_record = self.prepare_run_record("46", name="bytecode-run")
        project = run_record.parent / "customer-project"
        evaluator = (project / "evaluator.py").read_bytes()
        readiness = (
            project
            / "traigent-first-run/skills/traigent-first-run/scripts/readiness.py"
        ).read_bytes()
        running = sys.implementation.cache_tag
        other = "cpython-313" if running != "cpython-313" else "cpython-311"

        def pyc(
            tag: str,
            source: bytes,
            *,
            flags: int = 0,
            size: int | None = None,
            body: bytes | None = None,
        ) -> bytes:
            code = marshal.dumps(compile(source, "module.py", "exec"))
            return (
                scenario.BYTECODE_MAGIC[tag]
                + flags.to_bytes(4, "little")
                + (0).to_bytes(4, "little")
                + (len(source) if size is None else size).to_bytes(4, "little")
                + (code if body is None else body)
            )

        def verify() -> tuple[int, str, str]:
            return self.verify_plain(
                "incident-severity-triage", run_record, "--project-dir", str(project)
            )

        allowed = {
            f"__pycache__/evaluator.{running}.pyc": pyc(running, evaluator),
            f"__pycache__/evaluator.{other}.opt-1.pyc": pyc(other, evaluator),
            "traigent-first-run/skills/traigent-first-run/scripts/__pycache__/"
            f"readiness.{running}.opt-2.pyc": pyc(running, readiness),
        }
        for relative, content in allowed.items():
            (project / relative).parent.mkdir(parents=True, exist_ok=True)
            (project / relative).write_bytes(content)
        status, output, error = verify()
        self.assertEqual(0, status, error)
        self.assertIn("apart from 3 of the guide's opening writes", output)
        self.assertIn(
            f"__pycache__/evaluator.{running}.pyc (bytecode of evaluator.py)", output
        )
        self.assertIn(
            f"scripts/__pycache__/readiness.{running}.opt-2.pyc (bytecode of "
            "traigent-first-run/skills/traigent-first-run/scripts/readiness.py)",
            output,
        )

        named = f"__pycache__/evaluator.{running}.pyc"
        for relative, content, reason in (
            (
                "__pycache__/stash.cpython-312.pyc",
                pyc("cpython-312", evaluator),
                "__pycache__/stash.cpython-312.pyc: added, and not one of the "
                "guide's opening writes",
            ),
            (
                "__pycache__/evaluator.pyc",
                pyc(running, evaluator),
                "__pycache__/evaluator.pyc: added",
            ),
            (
                "evaluator.cpython-312.pyc",
                pyc("cpython-312", evaluator),
                "evaluator.cpython-312.pyc: added",
            ),
            (
                "__pycache__/agent.evil9.pyc",
                pyc(running, evaluator),
                "__pycache__/agent.evil9.pyc: added",
            ),
            (
                "__pycache__/agent.cpython-310.pyc",
                pyc(running, evaluator),
                "__pycache__/agent.cpython-310.pyc: added",
            ),
            (
                f"__pycache__/agent.{running}.opt-7.pyc",
                pyc(running, evaluator),
                f"__pycache__/agent.{running}.opt-7.pyc: added",
            ),
            (named, b"arbitrary bytes", "shorter than a bytecode header"),
            (
                named,
                pyc(running, evaluator)[:16],
                "a bytecode header with no body",
            ),
            (
                f"__pycache__/evaluator.{other}.pyc",
                pyc(other, evaluator)[:16],
                "a bytecode header with no body",
            ),
            (
                named,
                pyc(running, evaluator) + b"payload",
                "its body carries bytes after the code object",
            ),
            (
                named,
                pyc(running, evaluator) + b"N",
                "its body carries bytes after the code object",
            ),
            (
                named,
                pyc(running, evaluator, body=b"[" + (1 << 30).to_bytes(4, "little")),
                "does not unmarshal to a code object",
            ),
            (named, pyc(other, evaluator), f"does not open with {running}'s magic"),
            (named, pyc(running, evaluator, flags=1), "not the timestamp-based"),
            (
                named,
                pyc(running, evaluator, size=len(evaluator) + 1),
                f"records a source of {len(evaluator) + 1} bytes",
            ),
            (
                named,
                pyc(running, evaluator, body=b"\xff not marshal"),
                "does not unmarshal to a code object",
            ),
            (
                named,
                pyc(running, evaluator, body=marshal.dumps(42)),
                "does not unmarshal to a code object",
            ),
            (
                named,
                pyc(running, evaluator) + b"\0" * scenario.MAX_BYTECODE_BYTES,
                "larger than",
            ),
            (
                "traigent-runs/__pycache__/calibration.cpython-312.pyc",
                pyc("cpython-312", evaluator),
                "traigent-runs/__pycache__: a directory the opening does not create",
            ),
        ):
            with self.subTest(relative=relative, reason=reason):
                path = project / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                original = path.read_bytes() if path.is_file() else None
                path.write_bytes(content)
                status, output, error = verify()
                if original is None:
                    path.unlink()
                else:
                    path.write_bytes(original)
                if path.parent.name == "__pycache__" and not any(path.parent.iterdir()):
                    path.parent.rmdir()
                self.assertEqual(1, status, output)
                self.assertIn(f"- project: {relative}", error)
                self.assertIn(reason, error)

    def test_a_bytecode_body_that_cannot_be_read_is_reported_not_raised(
        self,
    ) -> None:
        """marshal runs out of memory or overflows on a crafted count; that is
        a body that does not unmarshal, never a traceback. A body that does not
        open on marshal's code type is refused before it is read at all."""
        tag = sys.implementation.cache_tag
        source = b"x = 1\n"
        header = (
            scenario.BYTECODE_MAGIC[tag] + bytes(8) + len(source).to_bytes(4, "little")
        )
        path = Path(self.temporary_directory.name) / "module.pyc"
        path.write_bytes(header + marshal.dumps(compile(source, "m.py", "exec")))
        for error in (MemoryError, OverflowError):
            with self.subTest(error=error.__name__):
                with mock.patch.object(scenario.marshal, "loads", side_effect=error):
                    self.assertEqual(
                        "its body does not unmarshal to a code object",
                        scenario._bytecode_problem(path, tag, len(source)),
                    )
        path.write_bytes(header + b"[" + (1 << 30).to_bytes(4, "little"))
        with mock.patch.object(scenario.marshal, "loads") as loads:
            self.assertEqual(
                "its body does not unmarshal to a code object",
                scenario._bytecode_problem(path, tag, len(source)),
            )
        loads.assert_not_called()

    def test_the_bytecode_magic_table_matches_this_python(self) -> None:
        """Each magic number is the one CPython writes; this interpreter vouches
        for its own entry, on each Python the suite runs on."""
        tag = sys.implementation.cache_tag
        self.assertIn(tag, scenario.BYTECODE_MAGIC)
        self.assertEqual(importlib.util.MAGIC_NUMBER, scenario.BYTECODE_MAGIC[tag])

    def test_verify_fails_a_directory_the_opening_does_not_create(self) -> None:
        self.copy_bank_scenario("incident-severity-triage")
        run_record = self.prepare_run_record("46", name="directory-run")
        project = run_record.parent / "customer-project"

        def verify() -> tuple[int, str, str]:
            return self.verify_plain(
                "incident-severity-triage", run_record, "--project-dir", str(project)
            )

        # The directories the guide's opening documents, even left empty.
        for relative in (
            "traigent-runs/readiness/20260923T120000Z",
            "__pycache__",
            "traigent-first-run/skills/traigent-first-run/scripts/__pycache__",
        ):
            (project / relative).mkdir(parents=True, exist_ok=True)
        status, output, error = verify()
        self.assertEqual(0, status, error)
        for relative, reason in (
            ("notes", "notes: a directory the opening does not create"),
            (
                "traigent-runs/readiness/latest",
                "traigent-runs/readiness/latest: a directory the opening does not "
                "create",
            ),
            (
                "traigent-first-run/skills/__pycache__",
                "traigent-first-run/skills/__pycache__: a directory the opening "
                "does not create",
            ),
        ):
            with self.subTest(relative=relative):
                (project / relative).mkdir()
                status, output, error = verify()
                (project / relative).rmdir()
                self.assertEqual(1, status, output)
                self.assertIn(f"- project: {reason}", error)

    def test_verify_refuses_a_gitignore_outside_a_git_work_tree(self) -> None:
        self.create_scenario("outside-tree", 41)
        guide_source = self.create_guide_source()
        outside = tempfile.TemporaryDirectory()
        self.addCleanup(outside.cleanup)
        output_path = Path(outside.name) / "run"
        status, _, error = self.run_cli(
            "prepare",
            "outside-tree",
            "--guide-src",
            str(guide_source),
            "--output",
            str(output_path),
        )
        self.assertEqual(0, status, error)
        project = output_path / "customer-project"
        (project / ".gitignore").write_text("/traigent-runs/\n", encoding="utf-8")
        status, output, error = self.verify_plain(
            "outside-tree",
            output_path / "run.json",
            "--project-dir",
            str(project),
        )
        self.assertEqual(1, status, output)
        self.assertIn(
            ".gitignore: the project is not inside a Git work tree, where the guide "
            "creates no .gitignore",
            error,
        )

    @unittest.skipIf(os.geteuid() == 0, "root reads a directory whatever its mode")
    def test_verify_fails_loudly_on_a_project_it_cannot_read(self) -> None:
        self.create_scenario("unreadable", 42)
        run_record = self.prepare_run_record("unreadable", name="unreadable-run")
        project = run_record.parent / "customer-project"
        hidden = project / "traigent-runs" / "hidden"
        hidden.mkdir(parents=True)
        (hidden / "stash.py").write_text("print('hidden')\n")
        hidden.chmod(0o000)
        self.addCleanup(hidden.chmod, 0o755)
        status, output, error = self.verify_plain(
            "unreadable", run_record, "--project-dir", str(project)
        )
        self.assertEqual(1, status, output)
        self.assertEqual("", output)
        self.assertIn("cannot read", error)
        self.assertIn("traigent-runs/hidden", error)
        hidden.chmod(0o755)

        original_lstat = Path.lstat

        def vanishing(path: Path) -> os.stat_result:
            if path.name == "stash.py":
                raise FileNotFoundError(2, "No such file or directory", str(path))
            return original_lstat(path)

        with mock.patch.object(Path, "lstat", autospec=True, side_effect=vanishing):
            status, output, error = self.verify_plain(
                "unreadable", run_record, "--project-dir", str(project)
            )
        self.assertEqual(1, status, output)
        self.assertIn("cannot inspect traigent-runs/hidden/stash.py", error)

    def test_verify_grades_the_final_message_for_the_guides_ask_shape(self) -> None:
        self.create_scenario("ask-graded", 36)
        run_record = self.prepare_run_record(
            "ask-graded", name="ask-run", skill_text=SKILL_WITH_ASK_RULES
        )

        def verify(text: str) -> tuple[int, str, str]:
            return self.verify_plain(
                "ask-graded",
                run_record,
                "--response",
                str(self.write_response(text)),
            )

        status, output, error = verify(WELL_SHAPED_ASK)
        self.assertEqual(0, status, error)
        self.assertIn("its final message raises no hard ask-shape finding", output)
        self.assertNotIn("response note:", output)
        for text, reason in (
            (
                WELL_SHAPED_ASK.replace(
                    "B. Pause", "B. `I have it` - give me a path.\nC. Pause"
                ),
                "route B opens on `I have it`",
            ),
            (
                WELL_SHAPED_ASK.replace(" (recommended)", ""),
                "none of the 2 routes is marked recommended",
            ),
            (
                WELL_SHAPED_ASK.replace("B. Pause", "C. Pause"),
                "options are labelled A, C",
            ),
        ):
            with self.subTest(reason=reason):
                status, output, error = verify(text)
                self.assertEqual(1, status, output)
                self.assertIn(f"- response: {reason}", error)
        # What the grader reads heuristically is a note beside the verdict: it
        # is printed on a PASS and on a FAIL, and never changes either.
        for text, note, want in (
            (
                WELL_SHAPED_ASK + "\nShall I also add rows?\n",
                "a question follows `I have it`",
                0,
            ),
            (
                WELL_SHAPED_ASK.replace(
                    "B. Pause", "B. I have it - give me a path.\nC. Pause"
                ),
                "route B offers `I have it` inside its text",
                0,
            ),
            (
                WELL_SHAPED_ASK.replace(
                    "then carry on.", "then carry on - redraw the split too?"
                ),
                "route A asks something of its own",
                0,
            ),
            (
                WELL_SHAPED_ASK.replace("B. Pause", "C. Pause").replace(
                    "then carry on.", "then carry on - redraw the split too?"
                ),
                "route A asks something of its own",
                1,
            ),
        ):
            with self.subTest(note=note, want=want):
                status, output, error = verify(text)
                self.assertEqual(want, status, output + error)
                self.assertIn(f"response note: {note}", output + error)

    def write_response(self, text: str) -> Path:
        path = Path(self.temporary_directory.name) / "response.md"
        path.write_text(text, encoding="utf-8")
        return path

    def test_verify_requires_i_have_it_where_a_cap_asks(self) -> None:
        """An unblocked opening with an asking cap stops on the one ask too."""
        root = self.create_scenario("asking-cap", 43)
        asking = {
            **expected_opening(),
            "band": "STRONG",
            "recommended_action": "add-examples",
            "caps": [
                {
                    "condition": "dataset-coarse-resolution",
                    "ceiling": 89,
                    "blocks": False,
                    "asks": True,
                }
            ],
        }
        self.write_contract(root, asking, message="Ask")
        run_record = self.prepare_run_record(
            "asking-cap", name="asking-cap-run", skill_text=SKILL_WITH_ASK_RULES
        )
        without = WELL_SHAPED_ASK.split("\nOr reply")[0]
        for text, want in ((WELL_SHAPED_ASK, 0), (without, 1)):
            with self.subTest(want=want):
                status, output, error = self.verify_plain(
                    "asking-cap",
                    run_record,
                    "--response",
                    str(self.write_response(text)),
                )
                self.assertEqual(want, status, output + error)
        self.assertIn("does not end on `I have it` with a path", error)

    def assert_one_ask_cap_requires_i_have_it(
        self, condition: str, number: int
    ) -> None:
        """An unblocked opening whose one asking cap is `condition` stops on the
        one ask, so its final message must end on `I have it`."""
        slug = condition.replace("dataset-", "one-ask-")
        root = self.create_scenario(slug, number)
        asking = {
            **expected_opening(),
            "band": "STRONG",
            "recommended_action": "add-examples",
            "caps": [
                {"condition": condition, "ceiling": 89, "blocks": False, "asks": True}
            ],
        }
        self.write_contract(root, asking, message=f"Ask on {condition}")
        run_record = self.prepare_run_record(
            slug, name=f"{slug}-run", skill_text=SKILL_WITH_ASK_RULES
        )
        without = WELL_SHAPED_ASK.split("\nOr reply")[0]
        for text, want in ((WELL_SHAPED_ASK, 0), (without, 1)):
            with self.subTest(condition=condition, want=want):
                status, output, error = self.verify_plain(
                    slug, run_record, "--response", str(self.write_response(text))
                )
                self.assertEqual(want, status, output + error)
        self.assertIn("does not end on `I have it` with a path", error)

    def test_verify_requires_i_have_it_where_the_dataset_is_too_small(
        self,
    ) -> None:
        """The top-up for a dataset below measurable size rides on the one ask."""
        self.assert_one_ask_cap_requires_i_have_it("dataset-below-measurable-size", 48)

    def test_verify_requires_i_have_it_where_no_dataset_asks_without_blocking(
        self,
    ) -> None:
        """The routing reference puts both ways out of an absent dataset on the
        one ask ("put both ways out on the one ask"), so the condition is a
        member. At guide d07b62cd readiness always blocks on it, and a blocked
        opening needs `I have it` on its status alone; this contract, with the
        cap asking and not blocking, holds the membership itself, which is
        what a readiness that stopped blocking on it would reach."""
        self.assert_one_ask_cap_requires_i_have_it("dataset-absent", 49)

    def test_verify_requires_i_have_it_where_rows_repeat(self) -> None:
        """component-creation.md puts the repeated-rows question on the one ask."""
        self.assert_one_ask_cap_requires_i_have_it("dataset-repeated-rows", 45)

    def test_verify_requires_i_have_it_where_the_split_follows_task_families(
        self,
    ) -> None:
        """A split drawn by task family is disclosed on the one ask, whose
        question it rides on."""
        self.assert_one_ask_cap_requires_i_have_it("dataset-split-by-task-family", 47)

    def test_verify_requires_i_have_it_only_where_the_guide_routes_the_one_ask(
        self,
    ) -> None:
        """Which bank openings stop on the one ask, from the guide's routing.

        Case 50's asking cap is put at the pre-spend approval, so the guide's own
        copied-actor question, which offers no `I have it`, passes there; case
        58's is settled where the answer-key review says. Case 51 is blocked, and
        case 56's top-up rides on the one ask.
        """
        copied_actor = (
            "Your evaluator sets its connection target at evaluator.py:12 "
            "(clinic.db). This run can calibrate a copy of it against a target that "
            "is not the one your original uses. A. This run copies that database "
            "file byte for byte into traigent-runs/calibration/ and calibrates the "
            "evaluator copy against the file copy (recommended). B. Paste a "
            "read-only connection into .env under TRAIGENT_CALIBRATION_TARGET and "
            "reply B. C. Skip the calibration; the run continues on the disclosure "
            "above.\n"
        )
        response = self.write_response(copied_actor)
        for slug, case, extra, want in (
            ("clinic-scheduling-sql-exec", "50", (), 0),
            ("contract-clause-extractor", "54", (), 0),
            (
                "regex-rule-authoring",
                "58",
                (
                    "--row-review",
                    str(
                        scenario.REPOSITORY_ROOT
                        / "scenarios/regex-rule-authoring/verifier/measurement"
                        / "row-review.json"
                    ),
                ),
                0,
            ),
            ("booking-assistant-next-action", "51", (), 1),
            ("freight-quote-estimator", "56", (), 1),
        ):
            with self.subTest(case=case):
                self.copy_bank_scenario(slug)
                record = self.prepare_run_record(
                    case, name=f"one-ask-{case}", skill_text=SKILL_WITH_ASK_RULES
                )
                status, output, error = self.verify_plain(
                    slug, record, *extra, "--response", str(response)
                )
                self.assertEqual(want, status, output + error)
                if want:
                    self.assertIn("does not end on `I have it` with a path", error)

    def test_verify_fails_a_final_message_with_no_readable_ask(self) -> None:
        self.create_scenario("no-ask", 44)
        run_record = self.prepare_run_record(
            "no-ask", name="no-ask-run", skill_text=SKILL_WITH_ASK_RULES
        )
        for text, reason in (
            ("", "the message is empty"),
            ("Here is your readiness card.\n", "no ask was found"),
            ("1. Build it (recommended).\n2. Pause.\n", "options are labelled 1, 2"),
        ):
            with self.subTest(reason=reason):
                status, output, error = self.verify_plain(
                    "no-ask", run_record, "--response", str(self.write_response(text))
                )
                self.assertEqual(1, status, output)
                self.assertIn(f"- response: {reason}", error)

    def test_verify_requires_i_have_it_on_a_blocked_opening(self) -> None:
        """A blocked opening stops on the one ask, which ends on `I have it`."""
        root = self.create_scenario("blocked-ask", 37)
        blocked = {
            **expected_opening(),
            "band": "PARTIAL",
            "status": "BLOCKED",
            "recommended_action": "repair-evaluator",
            "caps": [
                {
                    "condition": "evaluator-invalid",
                    "ceiling": 25,
                    "blocks": True,
                    "asks": False,
                }
            ],
        }
        self.write_contract(root, blocked, message="Block")
        run_record = self.prepare_run_record(
            "blocked-ask", name="blocked-ask-run", skill_text=SKILL_WITH_ASK_RULES
        )
        without = WELL_SHAPED_ASK.split("\nOr reply")[0]
        for slug_text, want in ((WELL_SHAPED_ASK, 0), (without, 1)):
            with self.subTest(want=want):
                status, output, error = self.verify_plain(
                    "blocked-ask",
                    run_record,
                    "--response",
                    str(self.write_response(slug_text)),
                )
                self.assertEqual(want, status, output + error)
        self.assertIn("does not end on `I have it` with a path", error)

        self.create_scenario("open-ask", 38)
        open_record = self.prepare_run_record(
            "open-ask", name="open-ask-run", skill_text=SKILL_WITH_ASK_RULES
        )
        status, output, error = self.verify_plain(
            "open-ask", open_record, "--response", str(self.write_response(without))
        )
        self.assertEqual(0, status, error)

    def test_verify_reads_the_ask_rules_from_the_guide_the_run_was_given(self) -> None:
        self.create_scenario("ask-rules", 39)
        missing = self.prepare_run_record("ask-rules", name="rules-missing-run")
        status, output, error = self.verify_plain(
            "ask-rules",
            missing,
            "--response",
            str(self.write_response(WELL_SHAPED_ASK)),
        )
        self.assertEqual(1, status)
        self.assertIn("no longer states a rule --response grades", error)

        stated = self.prepare_run_record(
            "ask-rules", name="rules-stated-run", skill_text=SKILL_WITH_ASK_RULES
        )
        skill = (
            stated.parent
            / "customer-project/traigent-first-run/skills/traigent-first-run/SKILL.md"
        )
        skill.write_text(SKILL_WITH_ASK_RULES + "\nedited\n", encoding="utf-8")
        status, output, error = self.verify_plain(
            "ask-rules", stated, "--response", str(self.write_response(WELL_SHAPED_ASK))
        )
        self.assertEqual(1, status)
        self.assertIn(
            "is not the skills/traigent-first-run/SKILL.md the run record lists", error
        )

    def test_every_verify_option_works_alone_and_with_the_others(self) -> None:
        """The mode by option cross-product: one contract or two, each subset of flags."""
        root = self.copy_read_dependent_scenario()
        self.create_scenario("combined", 40)
        plain = self.prepare_run_record(
            "combined", name="combined-run", skill_text=SKILL_WITH_ASK_RULES
        )
        dependent = self.prepare_run_record(
            "58", name="dependent-combined-run", skill_text=SKILL_WITH_ASK_RULES
        )
        sound = json.loads(
            (root / "verifier" / "expected-opening-sound-read.json").read_text()
        )
        read = self.write_read(
            {
                "line-4": "yes",
                "line-9": "yes",
                "line-15": "yes",
                "line-17": "yes",
                "line-30": "yes",
            },
            name="sound-read.json",
        )
        modes = (
            ("combined", plain, readiness_result(expected_opening()), ["model"], ()),
            (
                "58",
                dependent,
                readiness_result(sound),
                ["model", "prompt_style", "flavour", "temperature"],
                ("--row-review", str(read)),
            ),
        )
        flags = ("--agent-read", "--project-dir", "--response")
        for case, record, result, controls, base in modes:
            options = {
                "--agent-read": str(
                    self.write_agent_read(controls, name=f"{case}-agent.json")
                ),
                "--project-dir": str(record.parent / "customer-project"),
                "--response": str(self.write_response(WELL_SHAPED_ASK)),
            }
            for size in range(len(flags) + 1):
                for chosen in itertools.combinations(flags, size):
                    with self.subTest(case=case, flags=chosen):
                        extra = [
                            item for flag in chosen for item in (flag, options[flag])
                        ]
                        status, output, error = self.run_cli(
                            "verify",
                            case,
                            "--run-record",
                            str(record),
                            "--result",
                            str(self.write_result(result, name=f"{case}.json")),
                            *base,
                            *extra,
                        )
                        self.assertEqual(0, status, error)
                        self.assertEqual(
                            len(chosen), output.split("\n")[0].count("; its ")
                        )


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_MATCH_EXAMPLE_ROOT = (
    REPOSITORY_ROOT
    / "scenarios"
    / "incident-severity-triage"
    / "verifier"
    / "contract-match-example"
)


class CommittedContractMatchExampleTests(unittest.TestCase):
    def test_example_is_minimal_and_matches_pinned_opening_contract(self) -> None:
        result_path = CONTRACT_MATCH_EXAMPLE_ROOT / "result.json"
        self.assertEqual(
            {
                "band": "EXCELLENT",
                "caps": [],
                "recommended_action": "proceed",
                "status": "OK",
            },
            json.loads(result_path.read_text(encoding="utf-8")),
        )

        process = subprocess.run(
            [
                sys.executable,
                os.fspath(REPOSITORY_ROOT / "scenario.py"),
                "verify",
                "46",
                "--run-record",
                os.fspath(CONTRACT_MATCH_EXAMPLE_ROOT / "run-record.json"),
                "--result",
                os.fspath(result_path),
            ],
            cwd=REPOSITORY_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(0, process.returncode, process.stderr)
        # The example records a revision whose contract is schema 1, so verify
        # compares what that revision recorded and says what it left out.
        self.assertEqual(
            "PASS: incident-severity-triage opening result matches band, status, "
            "recommended_action, caps in the captain-recorded contract\n"
            "note: the recorded contract is schema 1, which records cap "
            "conditions only; ceilings, blocks and asks were not compared, and no "
            "readiness schema_version was required\n"
            "intended opening: none is recorded at this revision\n",
            process.stdout,
        )


if __name__ == "__main__":
    unittest.main()
