# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import hashlib
import io
import json
import os
import subprocess
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

# The shipped evaluator's own lookup table is what `check` reads to establish
# which labels it can tell apart, so a fixture scenario has to ship one.
TEST_EVALUATOR_TABLE: dict[str, object] = {"a": "class-a"}
CALIBRATION_TABLE: dict[str, object] = {"sev1": 1, "p1": 1, "sev2": 2}


def evaluator_source(table: dict[str, object]) -> str:
    return (
        "# SPDX-License-Identifier: Apache-2.0\n"
        '"""A deterministic label evaluator for fixture scenarios."""\n'
        "\n"
        f"LABEL_LEVELS = {table!r}\n"
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
                        "normalized_class_count": 1,
                        "normalization_map": {"A": "class-a"},
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
        evaluator_table: dict[str, object] | None = None,
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
                evaluator_source(
                    TEST_EVALUATOR_TABLE if evaluator_table is None else evaluator_table
                ),
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
                    "normalized_class_count": 0,
                    "normalization_map": {},
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
            "normalized_class_count": 0,
            "normalization_map": {},
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
                    "normalized_class_count": 0,
                    "normalization_map": {},
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
        normalization_map: dict[str, str],
        surface_label_count: int,
        normalized_class_count: int,
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
                    "surface_label_count": surface_label_count,
                    "normalized_class_count": normalized_class_count,
                    "normalization_map": normalization_map,
                },
            }
        )
        return manifest

    def write_evaluator(self, root: Path, table: dict[str, object]) -> None:
        """Reship the fixture's evaluator with the table these labels need."""
        (root / "project" / "evaluator.py").write_text(
            evaluator_source(table), encoding="utf-8"
        )

    def write_manifest(self, root: Path, manifest: dict[str, object]) -> None:
        (root / "scenario.json").write_text(json.dumps(manifest), encoding="utf-8")

    def test_declared_labels_must_be_ones_the_evaluator_can_tell_apart(self) -> None:
        root = self.create_scenario("collapsing-labels", 90)
        self.write_dataset(root, "SEV1", "sev1")
        self.write_manifest(
            root,
            self.labelled_manifest(
                "collapsing-labels",
                90,
                rows=2,
                normalization_map={"SEV1": "class-a", "sev1": "class-b"},
                surface_label_count=2,
                normalized_class_count=2,
            ),
        )

        status, output, error = self.run_cli("check", "collapsing-labels")

        self.assertNotEqual(0, status)
        self.assertEqual("", output)
        self.assertIn("are one label to the 'normalized-exact-match' evaluator", error)

    def test_label_identity_follows_the_declared_evaluator_method(self) -> None:
        root = self.create_scenario("byte-exact-labels", 91)
        self.write_evaluator(root, {"SEV1": 1, "sev1": 2})
        self.write_dataset(root, "SEV1", "sev1")
        manifest = self.labelled_manifest(
            "byte-exact-labels",
            91,
            rows=2,
            normalization_map={"SEV1": "class-a", "sev1": "class-b"},
            surface_label_count=2,
            normalized_class_count=2,
        )
        catalog = manifest["catalog"]
        assert isinstance(catalog, dict)
        catalog["components"]["evaluator"]["method"] = "exact-match"
        self.write_manifest(root, manifest)

        status, output, error = self.run_cli("check", "byte-exact-labels")

        self.assertEqual(0, status, error)
        self.assertIn("OK: byte-exact-labels", output)

    def label_table_scenario(
        self,
        slug: str,
        legacy_id: int,
        *,
        table: dict[str, object],
        labels: tuple[str, ...],
        normalization_map: dict[str, str],
        method: str = "normalized-exact-match",
    ) -> Path:
        root = self.create_scenario(slug, legacy_id)
        self.write_evaluator(root, table)
        self.write_dataset(root, *labels)
        manifest = self.labelled_manifest(
            slug,
            legacy_id,
            rows=len(labels),
            normalization_map=normalization_map,
            surface_label_count=len(set(normalization_map)),
            normalized_class_count=len(set(normalization_map.values())),
        )
        catalog = manifest["catalog"]
        assert isinstance(catalog, dict)
        catalog["components"]["evaluator"]["method"] = method
        self.write_manifest(root, manifest)
        return root

    def test_the_shipped_evaluator_settles_label_identity_not_the_declaration(
        self,
    ) -> None:
        """Changing one declared word must not switch the label gate off."""

        colliding = ("SEV1", "P1", "S1", "Critical")
        normalizing_table: dict[str, object] = {
            "sev1": 1,
            "p1": 1,
            "s1": 1,
            "critical": 1,
        }
        overstated = {
            label: f"severity-{index + 1}" for index, label in enumerate(colliding)
        }

        self.label_table_scenario(
            "declared-byte-exact",
            140,
            table=normalizing_table,
            labels=colliding,
            normalization_map=overstated,
            method="exact-match",
        )

        status, output, error = self.run_cli("check", "declared-byte-exact")

        self.assertNotEqual(
            0,
            status,
            "the table the evaluator ships is keyed in resolved form, so a "
            "manifest declaring byte-exact comparison is contradicted by the "
            "source rather than believed",
        )
        self.assertEqual("", output)
        self.assertIn(
            "is the table of a 'normalized-exact-match' evaluator",
            error,
        )

    def test_declared_classes_the_shipped_evaluator_merges_are_refused(self) -> None:
        """Four spellings that all score alike are not four classes."""

        merged = ("sev1", "p1", "s1", "critical")
        one_class_table: dict[str, object] = {label: 1 for label in merged}
        four_classes = {
            label: f"severity-{index + 1}" for index, label in enumerate(merged)
        }

        self.label_table_scenario(
            "merged-classes",
            141,
            table=one_class_table,
            labels=merged,
            normalization_map=four_classes,
        )

        status, output, error = self.run_cli("check", "merged-classes")

        self.assertNotEqual(0, status, output)
        self.assertEqual("", output)
        self.assertIn("but the shipped evaluator scores them alike", error)

        four_class_table: dict[str, object] = {
            label: index + 1 for index, label in enumerate(merged)
        }
        self.write_evaluator(self.scenarios_dir / "merged-classes", four_class_table)

        status, output, error = self.run_cli("check", "merged-classes")

        self.assertEqual(
            0,
            status,
            "the same manifest over a table that really does split the four "
            "spellings describes the dataset it has, and must be accepted",
        )
        self.assertIn("OK: merged-classes", output)

    def test_a_class_the_shipped_evaluator_splits_is_refused(self) -> None:
        """Two spellings the evaluator scores differently are not one class."""

        self.label_table_scenario(
            "merged-declaration",
            142,
            table={"sev1": 1, "p1": 2},
            labels=("SEV1", "P1"),
            normalization_map={"SEV1": "severity-1", "P1": "severity-1"},
        )

        status, output, error = self.run_cli("check", "merged-declaration")

        self.assertNotEqual(0, status, output)
        self.assertEqual("", output)
        self.assertIn("but the shipped evaluator scores them as different", error)

    def test_a_label_the_shipped_evaluator_cannot_score_is_refused(self) -> None:
        """A row the evaluator would raise on is not a row the catalog may claim."""

        self.label_table_scenario(
            "unscoreable-label",
            143,
            table={"sev1": 1},
            labels=("SEV1", "SEV9"),
            normalization_map={"SEV1": "severity-1", "SEV9": "severity-9"},
        )

        status, output, error = self.run_cli("check", "unscoreable-label")

        self.assertNotEqual(0, status, output)
        self.assertEqual("", output)
        self.assertIn("the shipped evaluator's table does not contain", error)

    def test_an_unreadable_label_table_fails_loud_rather_than_falling_back(
        self,
    ) -> None:
        """Falling back to the declaration would restore the trust this withdraws."""

        unreadable: tuple[tuple[str, str, str, str], ...] = (
            (
                "no table",
                "project/evaluator.py",
                "def score(output, expected):\n    return 0.0\n",
                "carries no module-level label table",
            ),
            (
                "two tables",
                "project/evaluator.py",
                'FIRST = {"sev1": 1}\nSECOND = {"sev1": 2}\n',
                "carries more than one module-level label table",
            ),
            (
                "not Python",
                "project/evaluator.txt",
                "not: python: at all!\n",
                "does not parse as Python",
            ),
        )
        for index, (name, relative, source, expected) in enumerate(unreadable):
            with self.subTest(case=name):
                slug = f"unreadable-table-{index}"
                root = self.create_scenario(slug, 150 + index)
                (root / Path(relative)).write_text(source, encoding="utf-8")
                manifest = valid_manifest(slug, 150 + index)
                catalog = manifest["catalog"]
                assert isinstance(catalog, dict)
                catalog["components"]["evaluator"]["path"] = relative
                self.write_manifest(root, manifest)
                self.commit_repository_paths(root, message=f"Ship {relative}")

                status, output, error = self.run_cli("check", slug)

                self.assertNotEqual(0, status, output)
                self.assertEqual("", output)
                self.assertIn(expected, error)

    def test_a_dataset_that_claims_no_label_surface_needs_no_label_table(
        self,
    ) -> None:
        """A gap scenario models a broken evaluator; it does not owe a table."""

        root = self.create_scenario("free-text-task", 161)
        (root / "project" / "evaluator.py").write_text(
            "def score(output, expected):\n    raise NotImplementedError\n",
            encoding="utf-8",
        )
        manifest = valid_manifest("free-text-task", 161)
        catalog = manifest["catalog"]
        assert isinstance(catalog, dict)
        catalog["datasets"][0]["label_shape"] = {
            "kind": "free-text",
            "surface_label_count": 0,
            "normalized_class_count": 0,
            "normalization_map": {},
        }
        self.write_manifest(root, manifest)

        status, output, error = self.run_cli("check", "free-text-task")

        self.assertEqual(
            0,
            status,
            "no dataset here claims a label surface, so there is no count the "
            f"evaluator's table could contradict: {error}",
        )
        self.assertIn("OK: free-text-task", output)

    def test_a_component_state_does_not_excuse_a_missing_label_table(self) -> None:
        """Declaring the evaluator broken must not switch the label gate off."""

        root = self.create_scenario("repairable-evaluator", 162)
        (root / "project" / "evaluator.py").write_text(
            "def score(output, expected):\n    raise NotImplementedError\n",
            encoding="utf-8",
        )
        manifest = valid_manifest("repairable-evaluator", 162)
        catalog = manifest["catalog"]
        assert isinstance(catalog, dict)
        catalog["starting_condition"] = "gaps-present"
        catalog["components"]["evaluator"]["state"] = "needs-repair"
        self.write_manifest(root, manifest)

        status, output, error = self.run_cli("check", "repairable-evaluator")

        self.assertNotEqual(
            0,
            status,
            "the dataset still claims one mapped class, and a scenario that "
            "ships an evaluator file ships an evaluator file",
        )
        self.assertIn("carries no module-level label table", error)

    def test_label_resolution_drops_punctuation_as_well_as_case(self) -> None:
        """'SEV1' and 'Sev-1' are one label, which is what the evaluator does."""

        root = self.create_scenario("punctuated-labels", 160)
        self.write_evaluator(root, {"sev1": 1})
        self.write_dataset(root, "SEV1", "Sev-1")
        self.write_manifest(
            root,
            self.labelled_manifest(
                "punctuated-labels",
                160,
                rows=2,
                normalization_map={"SEV1": "severity-1"},
                surface_label_count=1,
                normalized_class_count=1,
            ),
        )

        status, output, error = self.run_cli("check", "punctuated-labels")

        self.assertEqual(
            0,
            status,
            "the evaluator drops the punctuation that separates a code from "
            "its number, so the catalog has to count the two spellings as one "
            f"label: {error}",
        )
        self.assertIn("OK: punctuated-labels", output)

    def test_a_label_the_evaluator_resolves_to_a_declared_one_is_accepted(self) -> None:
        root = self.create_scenario("resolved-labels", 92)
        self.write_evaluator(root, {"sev1": 1, "p1": 1})
        self.write_dataset(root, "SEV1", "sev1", "P1")
        self.write_manifest(
            root,
            self.labelled_manifest(
                "resolved-labels",
                92,
                rows=3,
                normalization_map={"SEV1": "severity-1", "P1": "severity-1"},
                surface_label_count=2,
                normalized_class_count=1,
            ),
        )

        status, output, error = self.run_cli("check", "resolved-labels")

        self.assertEqual(0, status, error)
        self.assertIn("OK: resolved-labels", output)

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
            normalization_map={
                "SEV1": "severity-1",
                "P1": "severity-1",
                "SEV2": "severity-2",
            },
            surface_label_count=3,
            normalized_class_count=2,
        )
        catalog = manifest["catalog"]
        assert isinstance(catalog, dict)
        catalog["components"]["evaluator"]["calibration"] = {
            "path": "project/calibration.json",
            "case_count": case_count,
        }
        return manifest

    def test_calibration_probes_must_agree_with_the_declared_label_classes(
        self,
    ) -> None:
        contradictions: tuple[tuple[str, dict[str, object], str], ...] = (
            (
                "equivalent probe in another class",
                {"expected": "SEV1", "probes": {"equivalent_good": "SEV2"}},
                "scores like 'SEV1'",
            ),
            (
                "wrong-answer probe in the same class",
                {"expected": "SEV1", "probes": {"bad": "P1"}},
                "must not score like 'SEV1'",
            ),
            (
                "probe label outside the map",
                {"expected": "SEV1", "probes": {"good": "SEV9"}},
                "does not cover",
            ),
            (
                "recorded label outside every map",
                {"expected": "SEV9", "probes": {"good": "SEV9"}},
                "which no mapped-labels dataset in this catalog covers",
            ),
        )
        for index, (name, case, expected_error) in enumerate(contradictions):
            with self.subTest(contradiction=name):
                slug = f"calibration-{index}"
                root = self.create_scenario(slug, 100 + index)
                self.write_evaluator(root, CALIBRATION_TABLE)
                self.write_dataset(root, "SEV1", "P1", "SEV2")
                self.write_calibration(root, case)
                self.write_manifest(
                    root, self.calibrated_manifest(slug, 100 + index, case_count=1)
                )

                status, output, error = self.run_cli("check", slug)

                self.assertNotEqual(0, status)
                self.assertEqual("", output)
                self.assertIn(expected_error, error)

    def test_calibration_probes_consistent_with_the_label_map_are_accepted(
        self,
    ) -> None:
        root = self.create_scenario("calibration-ok", 110)
        self.write_evaluator(root, CALIBRATION_TABLE)
        self.write_dataset(root, "SEV1", "P1", "SEV2")
        self.write_calibration(
            root,
            {
                "expected": "SEV1",
                "probes": {
                    "good": "SEV1",
                    "equivalent_good": "sev1",
                    "partial": "SEV2",
                    "bad": "SEV2",
                },
            },
        )
        self.write_manifest(
            root, self.calibrated_manifest("calibration-ok", 110, case_count=1)
        )

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
                    "normalized_class_count": 0,
                    "normalization_map": {},
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
            "normalized_class_count": 0,
            "normalization_map": {},
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

    def test_dataset_rows_that_ship_must_be_declared(self) -> None:
        root = self.create_scenario("denied-dataset", 121)
        rows = "".join(
            json.dumps({"input": f"example-{index}", "output": "A"}) + "\n"
            for index in range(2)
        )
        rows_path = root / "project" / "rows.jsonl"
        rows_path.write_text(rows, encoding="utf-8")
        self.commit_repository_paths(rows_path, message="Ship undeclared rows")

        status, output, error = self.run_cli("check", "denied-dataset")

        self.assertNotEqual(0, status)
        self.assertEqual("", output)
        self.assertIn("ships dataset rows no dataset profile declares", error)
        self.assertIn("project/rows.jsonl", error)

        rows_path.unlink()
        notes = root / "project" / "notes.md"
        notes.write_text("# notes\n", encoding="utf-8")
        self.commit_repository_paths(root, message="Replace rows with prose")

        status, output, error = self.run_cli("check", "denied-dataset")

        self.assertEqual(0, status, error)
        self.assertIn("OK: denied-dataset", output)

    def test_undeclared_rows_survive_a_blank_line_and_a_foreign_suffix(self) -> None:
        """A blank line is what an editor adds on save, not a way out of the sweep."""

        root = self.create_scenario("blank-line-dataset", 133)
        rows = [
            json.dumps({"input": f"example-{index}", "output": "A"})
            for index in range(3)
        ]
        variants = {
            "project/spaced.jsonl": "\n".join(rows[:1] + [""] + rows[1:]) + "\n",
            "project/trailing.jsonl": "\n".join(rows) + "\n\n",
            "project/leading.jsonl": "\n" + "\n".join(rows) + "\n",
            "project/renamed.txt": "\n".join(rows) + "\n",
        }

        for relative, content in variants.items():
            with self.subTest(path=relative):
                shipped = root / Path(relative)
                shipped.write_text(content, encoding="utf-8")
                self.commit_repository_paths(shipped, message=f"Ship {relative}")

                status, output, error = self.run_cli("check", "blank-line-dataset")

                self.assertNotEqual(0, status, output)
                self.assertIn("ships dataset rows no dataset profile declares", error)
                self.assertIn(relative, error)

                shipped.unlink()
                self.commit_repository_paths(root, message=f"Withdraw {relative}")

        status, output, error = self.run_cli("check", "blank-line-dataset")
        self.assertEqual(0, status, error)

    def test_undeclared_rows_nested_below_the_project_directory(self) -> None:
        """`prepare` copies the whole project tree, not only its top level."""

        root = self.create_scenario("nested-dataset", 134)
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

        status, output, error = self.run_cli("check", "nested-dataset")

        self.assertNotEqual(0, status, output)
        self.assertIn("ships dataset rows no dataset profile declares", error)
        self.assertIn("project/extra/rows.jsonl", error)

    def test_untracked_scratch_rows_are_not_refused(self) -> None:
        """`prepare` copies recorded Git blobs, so a worker never sees these."""

        root = self.create_scenario("scratch-dataset", 135)
        scratch = root / "project" / "scratch.jsonl"
        scratch.write_text(
            "".join(
                json.dumps({"input": f"example-{index}", "output": "A"}) + "\n"
                for index in range(2)
            ),
            encoding="utf-8",
        )

        status, output, error = self.run_cli("check", "scratch-dataset")

        self.assertEqual(0, status, error)
        self.assertIn("OK: scratch-dataset", output)

        self.commit_repository_paths(scratch, message="Track the scratch rows")

        status, output, error = self.run_cli("check", "scratch-dataset")

        self.assertNotEqual(
            0,
            status,
            "tracking the same bytes puts them in the worker's checkout, so the "
            "sweep that was right to ignore them must now refuse them",
        )
        self.assertIn("project/scratch.jsonl", error)

    def test_classifying_a_large_file_does_not_read_it_whole(self) -> None:
        """The sweep visits every project file, so its cost is per line, not per file."""

        root = self.create_scenario("large-payload", 136)
        payload = root / "project" / "payload.bin"
        size = 16 * scenario.MAX_DATASET_ROW_BYTES
        payload.write_bytes(b"\x00\xff" * (size // 2))
        self.commit_repository_paths(payload, message="Ship a binary payload")

        tracemalloc.start()
        try:
            classified = scenario._ships_dataset_rows(payload)
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()

        self.assertFalse(classified)
        self.assertLess(
            peak,
            4 * scenario.MAX_DATASET_ROW_BYTES,
            "classifying a project file must cost the longest line it can accept, "
            "not the size of the file; the sweep reads every file under project/, "
            f"and this one is {size} bytes",
        )

        status, output, error = self.run_cli("check", "large-payload")

        self.assertEqual(0, status, error)
        self.assertIn("OK: large-payload", output)

    def test_check_rejects_shipped_python_that_does_not_parse(self) -> None:
        root = self.create_scenario("unparsable-code", 122)
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
        root = self.create_scenario(
            "fact-mismatch", 82, evaluator_table={"a": "class-a", "b": "class-b"}
        )
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
                            "normalized_class_count": 1,
                            "normalization_map": {"B": "class-b"},
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

    def test_catalog_validates_unique_inputs_and_normalized_class_count(self) -> None:
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

        invalid_classes = valid_manifest("identity-facts", 83)
        invalid_classes["catalog"]["datasets"][0]["label_shape"][
            "normalized_class_count"
        ] = 2
        (root / "scenario.json").write_text(
            json.dumps(invalid_classes),
            encoding="utf-8",
        )
        status, _, error = self.run_cli("list")
        self.assertNotEqual(0, status)
        self.assertIn("must equal the number of distinct normalized classes", error)

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
                    "normalized_class_count": 0,
                    "normalization_map": {},
                },
            ),
            (
                "free-text",
                "A detailed answer",
                {
                    "kind": "free-text",
                    "surface_label_count": 0,
                    "normalized_class_count": 0,
                    "normalization_map": {},
                },
            ),
            (
                "numeric",
                3.5,
                {
                    "kind": "numeric",
                    "surface_label_count": 0,
                    "normalized_class_count": 0,
                    "normalization_map": {},
                },
            ),
            (
                "structured",
                {"severity": "A"},
                {
                    "kind": "structured",
                    "surface_label_count": 0,
                    "normalized_class_count": 0,
                    "normalization_map": {},
                },
            ),
            (
                "absent",
                None,
                {
                    "kind": "absent",
                    "surface_label_count": 0,
                    "normalized_class_count": 0,
                    "normalization_map": {},
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
        self.commit_repository_paths(
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


if __name__ == "__main__":
    unittest.main()
