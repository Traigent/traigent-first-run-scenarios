# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import hashlib
import io
import json
import os
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
                    "path": "project/input.txt",
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
        "schema_version": 1,
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
            (root / "project" / "evaluator.py").write_text(
                EVALUATOR_SOURCE,
                encoding="utf-8",
            )
            (root / "verifier" / "expected-opening.json").write_text(
                json.dumps(expected_opening()) + "\n", encoding="utf-8"
            )
        self.commit_repository_paths(root, message=f"Create {slug}")
        return root

    def create_guide_source(self) -> Path:
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
        (skill / "SKILL.md").write_text("# Skill\n", encoding="utf-8")
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
    ) -> Path:
        guide_source = self.create_guide_source()
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

        status, _, error = self.run_cli("check", "catalog-paths")

        self.assertNotEqual(0, status)
        self.assertIn("catalog.components.agent.path", error)
        self.assertIn("cannot inspect", error)

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
                "expected cap object instead of condition slug",
                json.dumps(
                    {
                        **expected_opening(),
                        "caps": [{"condition": "dataset-fully-synthetic"}],
                    }
                ),
                "caps[0]: must be a non-empty string",
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
        changed = {**expected_opening(), "band": "GOOD"}
        (root / "verifier" / "expected-opening.json").write_text(
            json.dumps(changed) + "\n",
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
        original_result = self.write_result(expected_opening())

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
        result_path = self.write_result(expected_opening())

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
        result_path = self.write_result(expected_opening())

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
            "band, status, recommended_action, caps in the "
            "captain-recorded contract\n",
            output,
        )

    def test_verify_compares_cap_conditions_from_readiness_objects(self) -> None:
        root = self.create_scenario("capped-case", 25)
        expected = {
            **expected_opening(),
            "caps": ["dataset-fully-synthetic", "evaluator-unvalidated"],
        }
        (root / "verifier" / "expected-opening.json").write_text(
            json.dumps(expected) + "\n",
            encoding="utf-8",
        )
        self.commit_repository_paths(
            root / "verifier" / "expected-opening.json",
            message="Add capped opening contract",
        )
        run_record = self.prepare_run_record(
            "capped-case",
            name="capped-case-run",
        )
        result = {
            **expected,
            "caps": [
                {
                    "condition": "evaluator-unvalidated",
                    "ceiling": 45,
                    "reason": "the scorer is not calibrated",
                    "blocks": True,
                    "asks": False,
                    "action_kind": "repair-evaluator",
                },
                {
                    "condition": "dataset-fully-synthetic",
                    "ceiling": 65,
                    "reason": "comparison rows are generated",
                    "blocks": False,
                    "asks": False,
                    "action_kind": "proceed",
                },
            ],
        }
        result_path = self.write_result(result)

        status, output, error = self.run_cli(
            "verify",
            "capped-case",
            "--run-record",
            str(run_record),
            "--result",
            str(result_path),
        )

        self.assertEqual(0, status, error)
        self.assertIn("PASS: capped-case", output)

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
        self.assertEqual(4, error.count("\n- "))

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
        target = self.write_result(expected_opening(), name="target-result.json")
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
        result_path = self.write_result(expected_opening())
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
        self.assertEqual(
            "PASS: incident-severity-triage opening result matches band, status, "
            "recommended_action, caps in the captain-recorded contract\n",
            process.stdout,
        )


if __name__ == "__main__":
    unittest.main()
